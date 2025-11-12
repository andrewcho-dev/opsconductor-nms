import asyncio
import copy
from typing import Any, Dict, List

import jsonpatch
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import GraphState, PatchEvent
from .schemas import GraphResponse, GraphStatePayload, PatchEventResponse, PatchOperation, PatchRequest


DEFAULT_GRAPH: Dict[str, Any] = {"nodes": {}, "edges": []}


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
