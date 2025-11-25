import os
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .database import init_db
from .api import router as discovery_router

# Setup logging
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title="Network Discovery Service",
    description="Simplified network router discovery and topology mapping",
    version="1.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize database
@app.on_event("startup")
async def startup():
    logger.info("Initializing database...")
    init_db()
    logger.info("Database ready")

# Include routes
app.include_router(discovery_router, prefix="/api/v1", tags=["discovery"])

# Include inventory routes without /api/v1 prefix for frontend compatibility
from .api import router as inventory_router
app.include_router(inventory_router, prefix="/api", tags=["inventory"])

# Health check endpoint
@app.get("/health")
def health_check():
    """Simple health check endpoint."""
    return {"status": "healthy", "service": "network-discovery-simplified"}

# Root endpoint
@app.get("/")
def root():
    """Root endpoint."""
    return {
        "service": "network-discovery-simplified", 
        "version": "1.0.0",
        "description": "Simplified network router discovery and topology mapping"
    }

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
