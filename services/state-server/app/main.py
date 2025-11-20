from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import Depends, FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from .config import settings
from .database import async_session_factory, init_db
from .schemas import (
    DeviceConfirmationCreate,
    DeviceConfirmationResponse,
    GraphResponse,
    IpInventoryCreate,
    IpInventoryResponse,
    IpInventoryUpdate,
    MibCreate,
    MibResponse,
    PatchEventResponse,
    PatchRequest,
    SeedConfigRequest,
    FileSystemItem,
    TerminalLaunchRequest,
)
from .service import GraphService, InventoryService


@asynccontextmanager
async def lifespan(application: FastAPI):
    await init_db()
    yield


app = FastAPI(title="state-server", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.ui_ws_origin] if settings.ui_ws_origin != "*" else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
service = GraphService()
inventory_service = InventoryService()


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_factory() as session:
        try:
            yield session
        finally:
            await session.close()


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.get("/graph", response_model=GraphResponse)
async def fetch_graph(session: AsyncSession = Depends(get_session)) -> GraphResponse:
    return await service.get_graph(session)


@app.get("/patches", response_model=list[PatchEventResponse])
async def fetch_patches(limit: int = 50, session: AsyncSession = Depends(get_session)) -> list[PatchEventResponse]:
    if limit < 1 or limit > 500:
        raise HTTPException(status_code=422, detail="limit must be between 1 and 500")
    return await service.list_patches(session, limit=limit)


@app.post("/patch", response_model=GraphResponse)
async def apply_patch(request: PatchRequest, session: AsyncSession = Depends(get_session)) -> GraphResponse:
    try:
        return await service.apply_patch(session, request)
    except (SQLAlchemyError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/seed")
async def save_seed_config(request: SeedConfigRequest, session: AsyncSession = Depends(get_session)) -> dict:
    try:
        config = await service.save_seed_config(session, request)
        return {"status": "ok", "config": config}
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/seed")
async def get_seed_config(session: AsyncSession = Depends(get_session)) -> dict:
    try:
        config = await service.get_seed_config(session)
        return config
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.websocket("/ws")
async def stream_updates(websocket: WebSocket) -> None:
    await websocket.accept()
    queue = await service.subscribe()
    try:
        async with async_session_factory() as session:
            snapshot = await service.get_graph(session)
            await websocket.send_json({
                "graph": snapshot.graph.model_dump(mode="json"),
                "updated_at": snapshot.updated_at.isoformat(),
                "patch": [],
                "rationale": "initial",
                "warnings": [],
            })
        while True:
            payload = await queue.get()
            await websocket.send_json(payload)
    except WebSocketDisconnect:
        pass
    finally:
        service.unsubscribe(queue)


@app.get("/api/inventory", response_model=list[IpInventoryResponse])
async def list_inventory(
    status: str | None = None,
    device_type: str | None = None,
    confirmed: bool | None = None,
    session: AsyncSession = Depends(get_session)
) -> list[IpInventoryResponse]:
    return await inventory_service.list_ips(session, status=status, device_type=device_type, confirmed=confirmed)


@app.get("/api/inventory/{ip_address}", response_model=IpInventoryResponse)
async def get_inventory_item(ip_address: str, session: AsyncSession = Depends(get_session)) -> IpInventoryResponse:
    item = await inventory_service.get_ip(session, ip_address)
    if not item:
        raise HTTPException(status_code=404, detail="IP not found")
    return item


@app.get("/api/topology/layer2")
async def get_layer2_topology(session: AsyncSession = Depends(get_session)):
    from sqlalchemy import select
    from .models import IpInventory, GraphState
    from .stp_calculator import STPTopologyCalculator
    
    result = await session.execute(select(IpInventory))
    all_devices = result.scalars().all()
    
    graph_result = await session.execute(select(GraphState).limit(1))
    graph_state = graph_result.scalars().first()
    graph_nodes_map = {}
    if graph_state and graph_state.graph:
        graph_nodes = graph_state.graph.get("nodes", {})
        if isinstance(graph_nodes, dict):
            graph_nodes_map = graph_nodes
    
    nodes_dict = {}
    edges = []
    seen_edges = set()
    
    for device in all_devices:
        device_ip = str(device.ip_address)
        
        node_kind = device.network_role or "unknown"
        if node_kind == "unknown":
            if device_ip in graph_nodes_map:
                graph_node = graph_nodes_map[device_ip]
                if isinstance(graph_node, dict):
                    node_kind = graph_node.get("kind", "unknown")
        
        snmp_data = device.snmp_data or {}
        stp_data = snmp_data.get("stp", {})
        
        bridge_addr = stp_data.get("bridge_address")
        designated_root = stp_data.get("designated_root")
        root_cost = stp_data.get("root_cost", "")
        
        is_root = False
        if bridge_addr and designated_root:
            is_root = (bridge_addr == designated_root) or (root_cost == "0")
        
        nodes_dict[device_ip] = {
            "id": device_ip,
            "label": device.device_name or device_ip,
            "ip": device_ip,
            "mac": str(device.mac_address) if device.mac_address else None,
            "device_type": device.device_type,
            "network_role": device.network_role,
            "kind": node_kind,
            "vendor": device.vendor,
            "model": device.model,
            "is_root_bridge": is_root,
            "bridge_address": bridge_addr,
            "designated_root": designated_root,
            "root_cost": root_cost
        }
        
        snmp_data = device.snmp_data or {}
        lldp_data = snmp_data.get("lldp", {})
        
        if not lldp_data or not lldp_data.get("neighbors"):
            continue
        
        for neighbor in lldp_data.get("neighbors", []):
            remote_chassis = neighbor.get("remote_chassis_id", "")
            remote_sysname = neighbor.get("remote_sysname", "")
            
            if not remote_chassis and not remote_sysname:
                continue
            
            from sqlalchemy import or_, func, String
            import ipaddress
            query = select(IpInventory)
            conditions = []
            if remote_chassis:
                try:
                    ipaddress.ip_address(remote_chassis)
                    conditions.append(func.host(IpInventory.ip_address) == remote_chassis)
                except ValueError:
                    chassis_normalized = remote_chassis.replace('-', ':').lower()
                    conditions.append(func.lower(func.replace(IpInventory.mac_address.cast(String), '-', ':')) == chassis_normalized)
            if remote_sysname:
                conditions.append(IpInventory.device_name == remote_sysname)
            
            if conditions:
                result = await session.execute(query.where(or_(*conditions)))
                remote_device = result.scalars().first()
                
                if remote_device:
                    source_ip = str(device.ip_address)
                    target_ip = str(remote_device.ip_address)
                    
                    local_port = neighbor.get("local_port", "")
                    port_state = "unknown"
                    
                    stp_ports = stp_data.get("ports", {})
                    if local_port in stp_ports:
                        port_state = stp_ports[local_port].get("state", "unknown")
                    
                    edge_key = tuple(sorted([source_ip, target_ip]))
                    if edge_key not in seen_edges:
                        seen_edges.add(edge_key)
                        edges.append({
                            "from": source_ip,
                            "to": target_ip,
                            "label": f"{neighbor.get('local_port', '')} ↔ {neighbor.get('remote_port_id', '')}",
                            "local_port": neighbor.get("local_port"),
                            "remote_port": neighbor.get("remote_port_id"),
                            "remote_port_desc": neighbor.get("remote_port_desc"),
                            "stp_state": port_state
                        })
    
    calculator = STPTopologyCalculator(nodes_dict, edges)
    filtered_nodes, tree_edges, root_bridge = calculator.calculate_tree_topology()
    
    return {
        "nodes": filtered_nodes,
        "edges": tree_edges,
        "root_bridge": root_bridge
    }


@app.get("/api/topology/l3")
async def get_l3_topology(session: AsyncSession = Depends(get_session)):
    from sqlalchemy import select
    from .models import IpInventory
    import ipaddress
    
    result = await session.execute(select(IpInventory).where(IpInventory.network_role == "L3"))
    l3_devices = result.scalars().all()
    
    nodes = []
    edges = []
    subnets = {}
    seen_edges = set()
    
    for device in l3_devices:
        device_ip = str(device.ip_address)
        
        nodes.append({
            "id": device_ip,
            "label": device.device_name or device_ip,
            "ip": device_ip,
            "network_role": "L3",
            "vendor": device.vendor,
            "model": device.model,
            "connected_subnets": []
        })
        
        snmp_data = device.snmp_data or {}
        routing_table = snmp_data.get("routing_table", [])
        
        device_subnets = set()
        for route in routing_table:
            dest = route.get("destination", "")
            mask = route.get("mask", "")
            next_hop = route.get("next_hop", "")
            
            try:
                if dest and mask and dest != "0.0.0.0":
                    network = ipaddress.IPv4Network(f"{dest}/{mask}", strict=False)
                    subnet_str = str(network.with_prefixlen)
                    
                    if next_hop == "0.0.0.0" or next_hop == dest:
                        device_subnets.add(subnet_str)
                        if subnet_str not in subnets:
                            subnets[subnet_str] = []
                        subnets[subnet_str].append(device_ip)
            except (ValueError, ipaddress.AddressValueError):
                continue
        
        for node in nodes:
            if node["id"] == device_ip:
                node["connected_subnets"] = list(device_subnets)
                break
    
    for device in l3_devices:
        device_ip = str(device.ip_address)
        snmp_data = device.snmp_data or {}
        lldp_data = snmp_data.get("lldp", {})
        
        if not lldp_data or not lldp_data.get("neighbors"):
            continue
        
        for neighbor in lldp_data.get("neighbors", []):
            remote_chassis = neighbor.get("remote_chassis_id", "")
            remote_sysname = neighbor.get("remote_sysname", "")
            
            if not remote_chassis and not remote_sysname:
                continue
            
            from sqlalchemy import or_, func, String
            query = select(IpInventory).where(IpInventory.network_role == "L3")
            conditions = []
            if remote_chassis:
                try:
                    ipaddress.ip_address(remote_chassis)
                    conditions.append(func.host(IpInventory.ip_address) == remote_chassis)
                except ValueError:
                    chassis_normalized = remote_chassis.replace('-', ':').lower()
                    conditions.append(func.lower(func.replace(IpInventory.mac_address.cast(String), '-', ':')) == chassis_normalized)
            if remote_sysname:
                conditions.append(IpInventory.device_name == remote_sysname)
            
            if conditions:
                result = await session.execute(query.where(or_(*conditions)))
                remote_device = result.scalars().first()
                
                if remote_device:
                    source_ip = str(device.ip_address)
                    target_ip = str(remote_device.ip_address)
                    
                    edge_key = tuple(sorted([source_ip, target_ip]))
                    if edge_key not in seen_edges:
                        seen_edges.add(edge_key)
                        edges.append({
                            "from": source_ip,
                            "to": target_ip,
                            "label": "L3 Link",
                            "local_port": neighbor.get("local_port"),
                            "remote_port": neighbor.get("remote_port_id")
                        })
    
    return {
        "nodes": nodes,
        "edges": edges,
        "subnets": subnets
    }


@app.get("/api/topology/l2")
async def get_l2_topology(session: AsyncSession = Depends(get_session)):
    from sqlalchemy import select
    from .models import IpInventory
    from .stp_calculator import STPTopologyCalculator
    
    result = await session.execute(select(IpInventory).where(IpInventory.network_role == "L2"))
    l2_devices = result.scalars().all()
    
    nodes_dict = {}
    edges = []
    seen_edges = set()
    
    for device in l2_devices:
        device_ip = str(device.ip_address)
        snmp_data = device.snmp_data or {}
        stp_data = snmp_data.get("stp", {})
        
        bridge_addr = stp_data.get("bridge_address")
        designated_root = stp_data.get("designated_root")
        root_cost = stp_data.get("root_cost", "")
        
        is_root = False
        if bridge_addr and designated_root:
            is_root = (bridge_addr == designated_root) or (root_cost == "0")
        
        nodes_dict[device_ip] = {
            "id": device_ip,
            "label": device.device_name or device_ip,
            "ip": device_ip,
            "network_role": "L2",
            "vendor": device.vendor,
            "model": device.model,
            "is_root_bridge": is_root,
            "bridge_address": bridge_addr,
            "designated_root": designated_root,
            "root_cost": root_cost
        }
    
    for device in l2_devices:
        device_ip = str(device.ip_address)
        snmp_data = device.snmp_data or {}
        lldp_data = snmp_data.get("lldp", {})
        stp_data = snmp_data.get("stp", {})
        
        if not lldp_data or not lldp_data.get("neighbors"):
            continue
        
        for neighbor in lldp_data.get("neighbors", []):
            remote_chassis = neighbor.get("remote_chassis_id", "")
            remote_sysname = neighbor.get("remote_sysname", "")
            
            if not remote_chassis and not remote_sysname:
                continue
            
            from sqlalchemy import or_, func, String
            import ipaddress
            query = select(IpInventory).where(IpInventory.network_role == "L2")
            conditions = []
            if remote_chassis:
                try:
                    ipaddress.ip_address(remote_chassis)
                    conditions.append(func.host(IpInventory.ip_address) == remote_chassis)
                except ValueError:
                    chassis_normalized = remote_chassis.replace('-', ':').lower()
                    conditions.append(func.lower(func.replace(IpInventory.mac_address.cast(String), '-', ':')) == chassis_normalized)
            if remote_sysname:
                conditions.append(IpInventory.device_name == remote_sysname)
            
            if conditions:
                result = await session.execute(query.where(or_(*conditions)))
                remote_device = result.scalars().first()
                
                if remote_device:
                    source_ip = str(device.ip_address)
                    target_ip = str(remote_device.ip_address)
                    
                    local_port = neighbor.get("local_port", "")
                    port_state = "unknown"
                    
                    stp_ports = stp_data.get("ports", {})
                    if local_port in stp_ports:
                        port_state = stp_ports[local_port].get("state", "unknown")
                    
                    edge_key = tuple(sorted([source_ip, target_ip]))
                    if edge_key not in seen_edges:
                        seen_edges.add(edge_key)
                        edges.append({
                            "from": source_ip,
                            "to": target_ip,
                            "label": f"{neighbor.get('local_port', '')} ({port_state})",
                            "local_port": local_port,
                            "remote_port": neighbor.get("remote_port_id"),
                            "stp_state": port_state
                        })
    
    calculator = STPTopologyCalculator(nodes_dict, edges)
    filtered_nodes, tree_edges, root_bridge = calculator.calculate_tree_topology()
    
    return {
        "nodes": filtered_nodes,
        "edges": tree_edges,
        "root_bridge": root_bridge
    }


@app.get("/api/inventory/{ip_address}/neighbors")
async def get_device_neighbors(ip_address: str, session: AsyncSession = Depends(get_session)):
    from sqlalchemy import or_, func, select, String
    from .models import IpInventory
    
    item = await inventory_service.get_ip(session, ip_address)
    if not item:
        raise HTTPException(status_code=404, detail="IP not found")
    
    snmp_data = item.snmp_data or {}
    lldp_data = snmp_data.get("lldp", {})
    
    if not lldp_data:
        return {
            "ip_address": ip_address,
            "neighbors": [],
            "local_system": {},
            "message": "No LLDP neighbor data available"
        }
    
    neighbors_with_details = []
    for neighbor in lldp_data.get("neighbors", []):
        neighbor_info = {
            "local_port": neighbor.get("local_port"),
            "remote_chassis_id": neighbor.get("remote_chassis_id"),
            "remote_port_id": neighbor.get("remote_port_id"),
            "remote_port_desc": neighbor.get("remote_port_desc"),
            "remote_sysname": neighbor.get("remote_sysname"),
            "remote_sysdesc": neighbor.get("remote_sysdesc"),
        }
        
        remote_chassis = neighbor.get("remote_chassis_id", "")
        remote_sysname = neighbor.get("remote_sysname", "")
        
        if remote_chassis or remote_sysname:
            import ipaddress
            conditions = []
            
            if remote_chassis:
                try:
                    ipaddress.ip_address(remote_chassis)
                    conditions.append(func.host(IpInventory.ip_address) == remote_chassis)
                except ValueError:
                    chassis_normalized = remote_chassis.replace('-', ':').lower()
                    conditions.append(func.lower(func.replace(IpInventory.mac_address.cast(String), '-', ':')) == chassis_normalized)
            
            if remote_sysname:
                conditions.append(IpInventory.device_name == remote_sysname)
            
            if conditions:
                result = await session.execute(select(IpInventory).where(or_(*conditions)))
                remote_device = result.scalars().first()
                if remote_device:
                    neighbor_info["remote_ip"] = str(remote_device.ip_address)
                    neighbor_info["remote_device_type"] = remote_device.device_type
        
        neighbors_with_details.append(neighbor_info)
    
    return {
        "ip_address": ip_address,
        "local_system": lldp_data.get("local_system", {}),
        "neighbors": neighbors_with_details
    }


@app.post("/api/inventory", response_model=IpInventoryResponse)
async def create_inventory_item(
    data: IpInventoryCreate,
    session: AsyncSession = Depends(get_session)
) -> IpInventoryResponse:
    try:
        return await inventory_service.create_or_update_ip(session, data)
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.put("/api/inventory/{ip_address}", response_model=IpInventoryResponse)
async def update_inventory_item(
    ip_address: str,
    data: IpInventoryUpdate,
    session: AsyncSession = Depends(get_session)
) -> IpInventoryResponse:
    try:
        return await inventory_service.update_ip(session, ip_address, data)
    except SQLAlchemyError as exc:
        import traceback
        error_detail = f"{str(exc)}\n{traceback.format_exc()}"
        print(f"[STATE-SERVER] SQL Error updating {ip_address}: {error_detail}", flush=True)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        import traceback
        error_detail = f"{str(exc)}\n{traceback.format_exc()}"
        print(f"[STATE-SERVER] General Error updating {ip_address}: {error_detail}", flush=True)
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/inventory/{ip_address}/confirm", response_model=DeviceConfirmationResponse)
async def confirm_device_type(
    ip_address: str,
    data: DeviceConfirmationCreate,
    session: AsyncSession = Depends(get_session)
) -> DeviceConfirmationResponse:
    try:
        return await inventory_service.confirm_device(session, ip_address, data)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/mibs", response_model=list[MibResponse])
async def list_mibs(session: AsyncSession = Depends(get_session)) -> list[MibResponse]:
    return await inventory_service.list_mibs(session)


@app.get("/api/mibs/{mib_id}")
async def get_mib(
    mib_id: int,
    session: AsyncSession = Depends(get_session)
) -> dict:
    try:
        import os
        from sqlalchemy import select
        from .models import Mib
        
        result = await session.execute(select(Mib).where(Mib.id == mib_id))
        mib = result.scalar_one_or_none()
        
        if not mib:
            raise HTTPException(status_code=404, detail=f"MIB with ID {mib_id} not found")
        
        content = None
        if mib.file_path and os.path.exists(mib.file_path):
            with open(mib.file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
        
        return {
            "id": mib.id,
            "name": mib.name,
            "vendor": mib.vendor,
            "device_types": mib.device_types,
            "version": mib.version,
            "description": mib.description,
            "oid_prefix": mib.oid_prefix,
            "file_path": mib.file_path,
            "uploaded_at": mib.uploaded_at,
            "content": content
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/mibs", response_model=MibResponse)
async def create_mib(
    data: MibCreate,
    session: AsyncSession = Depends(get_session)
) -> MibResponse:
    try:
        return await inventory_service.create_mib(session, data)
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.delete("/api/mibs/{mib_id}")
async def delete_mib(
    mib_id: int,
    session: AsyncSession = Depends(get_session)
) -> dict:
    try:
        await inventory_service.delete_mib(session, mib_id)
        return {"status": "ok"}
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/inventory/{ip_address}/mibs/suggestions", response_model=list[MibResponse])
async def suggest_mibs_for_device(
    ip_address: str,
    session: AsyncSession = Depends(get_session)
) -> list[MibResponse]:
    return await inventory_service.suggest_mibs(session, ip_address)


@app.post("/api/inventory/{ip_address}/mibs/reassign", response_model=IpInventoryResponse)
async def reassign_device_mib(
    ip_address: str,
    session: AsyncSession = Depends(get_session)
) -> IpInventoryResponse:
    try:
        return await inventory_service.reassign_mib(session, ip_address)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/inventory/{ip_address}/mibs/walk")
async def trigger_device_mib_walk(
    ip_address: str,
    session: AsyncSession = Depends(get_session)
) -> dict:
    try:
        print(f"[STATE-SERVER] Walk MIB request received for {ip_address}", flush=True)
        result = await inventory_service.trigger_mib_walk(session, ip_address)
        print(f"[STATE-SERVER] Walk MIB succeeded for {ip_address}", flush=True)
        return result
    except ValueError as exc:
        print(f"[STATE-SERVER] Walk MIB failed for {ip_address}: {str(exc)}", flush=True)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        import traceback
        print(f"[STATE-SERVER] Walk MIB error for {ip_address}: {str(exc)}\n{traceback.format_exc()}", flush=True)
        raise HTTPException(status_code=500, detail=str(exc)) from exc




@app.post("/api/networks/discovered")
async def store_discovered_networks(
    request: dict,
    session: AsyncSession = Depends(get_session)
) -> dict:
    from sqlalchemy import select
    from .models import DiscoveredNetwork
    
    try:
        networks = request.get("discovered_networks", [])
        gateway_ip = request.get("gateway_ip", "")
        
        stored_count = 0
        updated_count = 0
        
        for network_data in networks:
            network_cidr = network_data.get("network")
            
            result = await session.execute(
                select(DiscoveredNetwork).where(DiscoveredNetwork.network == network_cidr)
            )
            existing = result.scalars().first()
            
            if existing:
                existing.last_seen = func.now()
                existing.next_hop = network_data.get("next_hop")
                existing.directly_connected = network_data.get("directly_connected", False)
                updated_count += 1
            else:
                new_network = DiscoveredNetwork(
                    network=network_cidr,
                    destination=network_data.get("destination"),
                    netmask=network_data.get("netmask"),
                    next_hop=network_data.get("next_hop"),
                    prefix_len=network_data.get("prefix_len"),
                    num_addresses=network_data.get("num_addresses"),
                    directly_connected=network_data.get("directly_connected", False),
                    gateway_ip=gateway_ip,
                    metadata=network_data
                )
                session.add(new_network)
                stored_count += 1
        
        await session.commit()
        
        return {
            "status": "ok",
            "stored": stored_count,
            "updated": updated_count,
            "total": len(networks)
        }
    except Exception as e:
        await session.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to store networks: {str(e)}")


@app.get("/api/networks/discovered")
async def list_discovered_networks(session: AsyncSession = Depends(get_session)) -> list:
    from sqlalchemy import select
    from .models import DiscoveredNetwork
    
    result = await session.execute(select(DiscoveredNetwork).order_by(DiscoveredNetwork.prefix_len))
    networks = result.scalars().all()
    
    return [
        {
            "id": n.id,
            "network": n.network,
            "destination": str(n.destination) if n.destination else None,
            "netmask": str(n.netmask) if n.netmask else None,
            "next_hop": str(n.next_hop) if n.next_hop else None,
            "prefix_len": n.prefix_len,
            "num_addresses": n.num_addresses,
            "directly_connected": n.directly_connected,
            "gateway_ip": str(n.gateway_ip) if n.gateway_ip else None,
            "discovered_at": n.discovered_at.isoformat() if n.discovered_at else None,
            "last_seen": n.last_seen.isoformat() if n.last_seen else None
        }
        for n in networks
    ]


@app.post("/api/launch-terminal")
async def launch_terminal(request: TerminalLaunchRequest) -> dict:
    import subprocess
    import shlex
    import re
    try:
        print(f"[TERMINAL-LAUNCH] Received request: terminal_path={request.terminal_path}, "
              f"command_template={request.command_template}, host={request.host}, "
              f"port={request.port}, protocol={request.protocol}", flush=True)
        
        command = request.command_template
        command = command.replace("{host}", request.host)
        command = command.replace("{port}", str(request.port))
        command = command.replace("{protocol}", request.protocol)
        
        if "{terminal}" in request.terminal_path:
            terminal_path = request.terminal_path.replace("{terminal}", request.terminal_path)
        else:
            terminal_path = request.terminal_path
        
        full_command = shlex.split(f'{terminal_path} {command}')
        print(f"[TERMINAL-LAUNCH] Executing command: {full_command}", flush=True)
        
        subprocess.Popen(full_command, start_new_session=True, 
                        stdin=subprocess.DEVNULL, 
                        stdout=subprocess.DEVNULL, 
                        stderr=subprocess.DEVNULL)
        
        print(f"[TERMINAL-LAUNCH] Successfully launched terminal", flush=True)
        return {
            "status": "ok", 
            "message": f"Launched terminal: {terminal_path} with command: {command}"
        }
    except Exception as exc:
        print(f"[TERMINAL-LAUNCH] Error: {str(exc)}", flush=True)
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Failed to launch terminal: {str(exc)}") from exc



@app.get("/api/browse-filesystem")
async def browse_filesystem(path: str = "/") -> dict:
    import os
    from datetime import datetime
    
    try:
        if not os.path.exists(path):
            raise HTTPException(status_code=404, detail=f"Path does not exist: {path}")
        
        if not os.path.isdir(path):
            raise HTTPException(status_code=400, detail=f"Path is not a directory: {path}")
        
        items = []
        try:
            entries = os.listdir(path)
        except PermissionError:
            raise HTTPException(status_code=403, detail=f"Permission denied: {path}")
        
        for entry in sorted(entries):
            full_path = os.path.join(path, entry)
            try:
                stat_info = os.stat(full_path)
                is_dir = os.path.isdir(full_path)
                items.append({
                    "name": entry,
                    "path": full_path,
                    "is_dir": is_dir,
                    "size": stat_info.st_size if not is_dir else None,
                    "modified": datetime.fromtimestamp(stat_info.st_mtime).isoformat()
                })
            except (OSError, PermissionError):
                continue
        
        parent_path = os.path.dirname(path) if path != "/" else None
        
        return {
            "current_path": path,
            "parent_path": parent_path,
            "items": items
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to browse filesystem: {str(exc)}") from exc
