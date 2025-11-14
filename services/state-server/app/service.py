import asyncio
import copy
from typing import Any, Dict, List

import jsonpatch
from sqlalchemy import select, cast
from sqlalchemy.dialects.postgresql import INET
from sqlalchemy.ext.asyncio import AsyncSession

from .models import DeviceConfirmation, GraphState, IpInventory, Mib, PatchEvent
from .schemas import (
    DeviceConfirmationCreate,
    DeviceConfirmationResponse,
    GraphResponse,
    GraphStatePayload,
    IpInventoryCreate,
    IpInventoryResponse,
    IpInventoryUpdate,
    MibCreate,
    MibResponse,
    PatchEventResponse,
    PatchOperation,
    PatchRequest,
    SeedConfigRequest,
)


DEFAULT_GRAPH: Dict[str, Any] = {
    "networks": {},
    "routers": {},
    "edges": [],
    "nodes": {},
    "legacy_edges": []
}


class GraphService:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._subscribers: set[asyncio.Queue] = set()

    async def subscribe(self) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=8)
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        self._subscribers.discard(queue)

    async def get_graph(self, session: AsyncSession) -> GraphResponse:
        state = await self._get_or_create_state(session)
        payload = GraphStatePayload.model_validate(state.graph or DEFAULT_GRAPH)
        return GraphResponse(graph=payload, updated_at=state.updated_at)

    async def list_patches(self, session: AsyncSession, limit: int = 50) -> List[PatchEventResponse]:
        result = await session.execute(select(PatchEvent).order_by(PatchEvent.id.desc()).limit(limit))
        rows = result.scalars().all()
        return [self._to_patch_event_response(row) for row in rows]

    async def apply_patch(self, session: AsyncSession, request: PatchRequest) -> GraphResponse:
        async with self._lock:
            state = await self._get_or_create_state(session)
            source = copy.deepcopy(state.graph or DEFAULT_GRAPH)
            ops = [self._operation_to_dict(op) for op in request.patch]
            patch = jsonpatch.JsonPatch(ops)
            target = patch.apply(source, in_place=False)

            for edge in target.get("legacy_edges", []):
                for ip_key in ["src", "dst"]:
                    ip = edge.get(ip_key)
                    if ip and ip not in target.get("nodes", {}):
                        target.setdefault("nodes", {})[ip] = {"ip": ip, "kind": "host"}
            
            for edge in target.get("edges", []):
                src_net = edge.get("src_network")
                dst_net = edge.get("dst_network")
                if src_net and src_net not in target.get("networks", {}):
                    target.setdefault("networks", {})[src_net] = {
                        "cidr": src_net,
                        "label": src_net,
                        "members": [],
                        "kind": "unknown"
                    }
                if dst_net and dst_net not in target.get("networks", {}):
                    target.setdefault("networks", {})[dst_net] = {
                        "cidr": dst_net,
                        "label": dst_net,
                        "members": [],
                        "kind": "unknown"
                    }

            payload = GraphStatePayload.model_validate(target)
            state.graph = payload.model_dump(mode="json")
            await session.flush()
            event = PatchEvent(patch=ops, rationale=request.rationale, warnings=request.warnings or None)
            session.add(event)
            await session.commit()
            await session.refresh(state)
            response = GraphResponse(graph=payload, updated_at=state.updated_at)
            await self._broadcast({
                "graph": response.graph.model_dump(mode="json"),
                "updated_at": response.updated_at.isoformat(),
                "patch": ops,
                "rationale": request.rationale,
                "warnings": request.warnings,
            })
            return response

    async def _broadcast(self, payload: Dict[str, Any]) -> None:
        stale: List[asyncio.Queue] = []
        for queue in self._subscribers:
            try:
                queue.put_nowait(payload)
            except asyncio.QueueFull:
                stale.append(queue)
        for queue in stale:
            self._subscribers.discard(queue)

    @staticmethod
    def _operation_to_dict(operation) -> Dict[str, Any]:
        data = operation.model_dump(exclude_none=True)
        if operation.op == "remove" and "value" in data:
            data.pop("value")
        return data

    @staticmethod
    def _to_patch_event_response(event: PatchEvent) -> PatchEventResponse:
        raw_ops = event.patch or []
        ops = [PatchOperation.model_validate(entry) for entry in raw_ops]
        return PatchEventResponse(id=event.id, patch=ops, rationale=event.rationale, warnings=event.warnings or [], created_at=event.created_at)

    async def _get_or_create_state(self, session: AsyncSession) -> GraphState:
        result = await session.execute(select(GraphState).limit(1))
        instance = result.scalars().first()
        if instance is None:
            instance = GraphState(id=1, graph=copy.deepcopy(DEFAULT_GRAPH))
            session.add(instance)
            await session.commit()
            await session.refresh(instance)
        return instance

    async def save_seed_config(self, session: AsyncSession, config: SeedConfigRequest) -> Dict[str, Any]:
        async with self._lock:
            state = await self._get_or_create_state(session)
            state.seed_config = config.model_dump(mode="json")
            await session.commit()
            await session.refresh(state)
            return state.seed_config

    async def get_seed_config(self, session: AsyncSession) -> Dict[str, Any]:
        state = await self._get_or_create_state(session)
        return state.seed_config or {}


class InventoryService:
    async def list_ips(
        self,
        session: AsyncSession,
        status: str | None = None,
        device_type: str | None = None,
        confirmed: bool | None = None
    ) -> List[IpInventoryResponse]:
        query = select(IpInventory)
        if status:
            query = query.where(IpInventory.status == status)
        if device_type:
            query = query.where(IpInventory.device_type == device_type)
        if confirmed is not None:
            query = query.where(IpInventory.device_type_confirmed == confirmed)
        query = query.order_by(IpInventory.ip_address)
        result = await session.execute(query)
        rows = result.scalars().all()
        return [IpInventoryResponse.model_validate(row) for row in rows]

    async def get_ip(self, session: AsyncSession, ip_address: str) -> IpInventoryResponse | None:
        result = await session.execute(
            select(IpInventory).where(IpInventory.ip_address == cast(ip_address, INET))
        )
        row = result.scalars().first()
        return IpInventoryResponse.model_validate(row) if row else None

    async def create_or_update_ip(self, session: AsyncSession, data: IpInventoryCreate) -> IpInventoryResponse:
        result = await session.execute(
            select(IpInventory).where(IpInventory.ip_address == cast(data.ip_address, INET))
        )
        existing = result.scalars().first()
        
        if existing:
            for key, value in data.model_dump(exclude_unset=True).items():
                if key != 'ip_address':
                    setattr(existing, key, value)
            existing.last_seen = func.now()
            item = existing
        else:
            item = IpInventory(**data.model_dump())
        
        session.add(item)
        await session.commit()
        await session.refresh(item)
        return IpInventoryResponse.model_validate(item)

    async def update_ip(self, session: AsyncSession, ip_address: str, data: IpInventoryUpdate) -> IpInventoryResponse:
        result = await session.execute(
            select(IpInventory).where(IpInventory.ip_address == cast(ip_address, INET))
        )
        item = result.scalars().first()
        
        if not item:
            raise ValueError(f"IP {ip_address} not found")
        
        for key, value in data.model_dump(exclude_unset=True).items():
            setattr(item, key, value)
        
        await session.commit()
        await session.refresh(item)
        return IpInventoryResponse.model_validate(item)

    async def confirm_device(
        self,
        session: AsyncSession,
        ip_address: str,
        data: DeviceConfirmationCreate
    ) -> DeviceConfirmationResponse:
        result = await session.execute(
            select(IpInventory).where(IpInventory.ip_address == cast(ip_address, INET))
        )
        item = result.scalars().first()
        
        if not item:
            raise ValueError(f"IP {ip_address} not found")
        
        item.device_type = data.confirmed_type
        item.device_type_confirmed = True
        
        confirmation = DeviceConfirmation(
            ip_inventory_id=item.id,
            **data.model_dump()
        )
        session.add(confirmation)
        await session.commit()
        await session.refresh(confirmation)
        return DeviceConfirmationResponse.model_validate(confirmation)

    async def list_mibs(self, session: AsyncSession) -> List[MibResponse]:
        result = await session.execute(select(Mib).order_by(Mib.vendor, Mib.name))
        rows = result.scalars().all()
        return [MibResponse.model_validate(row) for row in rows]

    async def create_mib(self, session: AsyncSession, data: MibCreate) -> MibResponse:
        mib = Mib(**data.model_dump())
        session.add(mib)
        await session.commit()
        await session.refresh(mib)
        return MibResponse.model_validate(mib)

    async def delete_mib(self, session: AsyncSession, mib_id: int) -> None:
        result = await session.execute(select(Mib).where(Mib.id == mib_id))
        mib = result.scalars().first()
        
        if not mib:
            raise ValueError(f"MIB {mib_id} not found")
        
        await session.delete(mib)
        await session.commit()

    async def suggest_mibs(self, session: AsyncSession, ip_address: str) -> List[MibResponse]:
        result = await session.execute(
            select(IpInventory).where(IpInventory.ip_address == cast(ip_address, INET))
        )
        device = result.scalars().first()
        
        if not device:
            return []
        
        vendor = device.vendor
        device_type = device.device_type
        
        vendor_normalized = self._normalize_vendor(vendor)
        
        result = await session.execute(select(Mib).order_by(Mib.vendor, Mib.name))
        all_mibs = result.scalars().all()
        
        scored_mibs = []
        device_type_lower = device_type.lower() if device_type else None
        
        for mib in all_mibs:
            score = 0
            
            if mib.vendor == "IETF":
                score = 10
            elif vendor_normalized and mib.vendor and vendor_normalized.lower() in mib.vendor.lower():
                score = 100
            else:
                continue
            
            if device_type_lower and mib.device_types:
                device_types_lower = [dt.lower() for dt in mib.device_types]
                if device_type_lower in device_types_lower:
                    score += 50
            
            scored_mibs.append((score, mib))
        
        scored_mibs.sort(key=lambda x: x[0], reverse=True)
        
        return [MibResponse.model_validate(mib) for _, mib in scored_mibs]
    
    def _normalize_vendor(self, vendor: str | None) -> str | None:
        if not vendor:
            return None
        
        vendor_lower = vendor.lower()
        
        mappings = {
            "hewlett": "HP",
            "hewlett packard": "HP",
            "hewlett-packard": "HP",
            "tp-link": "TP-Link",
            "tplink": "TP-Link",
            "axis communications": "Axis",
            "juniper networks": "Juniper",
            "arista networks": "Arista",
            "cisco systems": "Cisco",
            "d-link": "D-Link",
            "dlink": "D-Link",
            "canon inc": "Canon",
            "yealink": "Yealink",
            "cradlepoint": "Cradlepoint",
            "razberi": "Razberi",
            "ciena": "Ciena",
        }
        
        for key, normalized in mappings.items():
            if key in vendor_lower:
                return normalized
        
        return vendor.split()[0].title()
    
    async def reassign_mib(self, session: AsyncSession, ip_address: str) -> IpInventoryResponse:
        result = await session.execute(
            select(IpInventory).where(IpInventory.ip_address == cast(ip_address, INET))
        )
        device = result.scalars().first()
        
        if not device:
            raise ValueError(f"Device {ip_address} not found")
        
        if not device.snmp_data:
            raise ValueError(f"Device {ip_address} has no SNMP data")
        
        suggestions = await self.suggest_mibs(session, ip_address)
        if not suggestions:
            raise ValueError(f"No MIB suggestions found for {ip_address}")
        
        vendor_mibs = [s for s in suggestions if s.vendor.upper() != "IETF"]
        best_mib = vendor_mibs[0] if vendor_mibs else suggestions[0]
        
        device.mib_id = best_mib.id
        await session.commit()
        await session.refresh(device)
        
        return IpInventoryResponse.model_validate(device)
    
    async def trigger_mib_walk(self, session: AsyncSession, ip_address: str) -> dict:
        import httpx
        
        result = await session.execute(
            select(IpInventory).where(IpInventory.ip_address == cast(ip_address, INET))
        )
        device = result.scalars().first()
        
        if not device:
            raise ValueError(f"Device {ip_address} not found")
        
        if not device.mib_id:
            raise ValueError(f"Device {ip_address} has no MIB assigned")
        
        if not device.snmp_enabled:
            raise ValueError(f"Device {ip_address} does not have SNMP enabled")
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                resp = await client.post(
                    "http://mib-walker:9600/walk",
                    json={"ip_address": ip_address}
                )
                if resp.status_code == 200:
                    return resp.json()
                else:
                    raise ValueError(f"MIB walk failed with status {resp.status_code}: {resp.text}")
            except httpx.ConnectError:
                raise ValueError("Cannot connect to mib-walker service")
            except Exception as e:
                raise ValueError(f"MIB walk request failed: {str(e)}")
