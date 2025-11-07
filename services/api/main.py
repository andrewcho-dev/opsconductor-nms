from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
import os
import asyncpg
from routers import topology, sflow, netbox

limiter = Limiter(key_func=get_remote_address, default_limits=["100/minute"])

app = FastAPI(
    title="OpsConductor NMS Topology API",
    description="Network topology and troubleshooting API",
    version="0.1.0"
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(topology.router)
app.include_router(sflow.router)
app.include_router(netbox.router)

db_pool = None

@app.on_event("startup")
async def startup():
    global db_pool
    dsn = os.getenv('PG_DSN', 'postgresql://oc:oc@localhost/opsconductor')
    min_pool_size = int(os.getenv('DB_POOL_MIN_SIZE', '5'))
    max_pool_size = int(os.getenv('DB_POOL_MAX_SIZE', '20'))
    command_timeout = int(os.getenv('DB_COMMAND_TIMEOUT', '30'))
    
    db_pool = await asyncpg.create_pool(
        dsn, 
        min_size=min_pool_size, 
        max_size=max_pool_size,
        command_timeout=command_timeout
    )

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
