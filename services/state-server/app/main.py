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
