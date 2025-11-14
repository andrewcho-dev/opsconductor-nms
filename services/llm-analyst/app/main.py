import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException

from .schemas import AnalystResponse, InferenceInput
from .service import AnalystService

service = AnalystService()
classification_task = None


async def periodic_classification():
    import logging
    logger = logging.getLogger(__name__)
    while True:
        try:
            await asyncio.sleep(60)
            count = await service.classify_inventory_devices()
            if count > 0:
                logger.info(f"Classified {count} devices")
        except Exception as e:
            logger.error(f"Classification error: {e}")


@asynccontextmanager
async def lifespan(application: FastAPI):
    global classification_task
    await service.startup()
    classification_task = asyncio.create_task(periodic_classification())
    try:
        yield
    finally:
        if classification_task:
            classification_task.cancel()
            try:
                await classification_task
            except asyncio.CancelledError:
                pass
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
        import logging
        logging.error(f"Tick processing failed: {exc}", exc_info=True)
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/classify")
async def classify() -> dict:
    try:
        count = await service.classify_inventory_devices()
        return {"classified": count}
    except Exception as exc:
        import logging
        logging.error(f"Classification failed: {exc}", exc_info=True)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
