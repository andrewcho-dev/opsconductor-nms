from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException

from .schemas import AnalystResponse, InferenceInput
from .service import AnalystService

service = AnalystService()


@asynccontextmanager
async def lifespan(application: FastAPI):
    await service.startup()
    try:
        yield
    finally:
        await service.shutdown()


app = FastAPI(title="llm-analyst", lifespan=lifespan)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.post("/tick", response_model=AnalystResponse)
async def tick(request: InferenceInput) -> AnalystResponse:
    try:
        return await service.process(request)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
