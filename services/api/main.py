from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import os
import asyncpg
from routers import topology

app = FastAPI(
    title="OpsConductor NMS Topology API",
    description="Network topology and troubleshooting API",
    version="0.1.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(topology.router)

db_pool = None

@app.on_event("startup")
async def startup():
    global db_pool
    dsn = os.getenv('PG_DSN', 'postgresql://oc:oc@db/opsconductor')
    db_pool = await asyncpg.create_pool(dsn, min_size=2, max_size=10)

@app.on_event("shutdown")
async def shutdown():
    global db_pool
    if db_pool:
        await db_pool.close()

@app.get("/healthz")
async def healthz():
    if db_pool is None:
        raise HTTPException(status_code=503, detail="Database not connected")
    
    try:
        async with db_pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
        return {"status": "ok", "database": "connected"}
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Database error: {str(e)}")

@app.get("/")
async def root():
    return {
        "service": "OpsConductor NMS Topology API",
        "version": "0.1.0",
        "docs": "/docs"
    }
