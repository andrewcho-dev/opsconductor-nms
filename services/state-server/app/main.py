from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import Depends, FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from .config import settings
from .database import async_session_factory, init_db
from .schemas import GraphResponse, PatchEventResponse, PatchRequest
from .service import GraphService


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
