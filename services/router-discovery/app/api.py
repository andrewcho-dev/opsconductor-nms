from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import and_

from models import DiscoveryRun, Router, RouterNetwork, RouterRoute, TopologyEdge
from database import get_db

router = APIRouter(prefix="/api/router-discovery", tags=["discovery"])


# Request/Response models
class StartDiscoveryRequest(BaseModel):
    root_ip: str
    snmp_community: str
    snmp_version: str = Field(default="2c", pattern="^(2c|3)$")


class DiscoveryRunResponse(BaseModel):
    id: int
    started_at: str
    finished_at: Optional[str]
    status: str
    root_ip: str
    snmp_community: str
    snmp_version: str
    error_message: Optional[str]
    
    class Config:
        from_attributes = True


class RouterNodeResponse(BaseModel):
    id: int
    ip: str
    hostname: Optional[str]
    is_router: bool
    router_score: int
    classification_reason: str
    vendor: Optional[str]
    model: Optional[str]
    
    class Config:
        from_attributes = True


class TopologyEdgeResponse(BaseModel):
    from_id: int
    to_id: int
    reason: str
    
    class Config:
        from_attributes = True


class TopologyResponse(BaseModel):
    nodes: List[RouterNodeResponse]
    edges: List[TopologyEdgeResponse]


class RouterDetailResponse(BaseModel):
    id: int
    ip: str
    hostname: Optional[str]
    is_router: bool
    router_score: int
    classification_reason: str
    vendor: Optional[str]
    model: Optional[str]
    networks: List[str]
    routes: List[dict]
    
    class Config:
        from_attributes = True


class StartDiscoveryResponse(BaseModel):
    run_id: int


class ErrorResponse(BaseModel):
    error: str
    detail: Optional[str]


# Endpoints

@router.post("/start", response_model=StartDiscoveryResponse, status_code=201)
def start_discovery(request: StartDiscoveryRequest, db: Session = Depends(get_db)):
    """Start a new discovery run."""
    from crawler import RouterDiscoveryCrawler
    from snmp_adapter import SnmpAdapter
    from router_classifier import RouterClassifier
    import logging
    
    # Validate input
    try:
        from ipaddress import IPv4Address
        IPv4Address(request.root_ip)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid IPv4 address")
    
    if request.snmp_version not in ["2c", "3"]:
        raise HTTPException(status_code=422, detail="snmp_version must be '2c' or '3'")
    
    # Check if a run is already running
    running_run = db.query(DiscoveryRun).filter(DiscoveryRun.status == "RUNNING").first()
    if running_run:
        raise HTTPException(
            status_code=409,
            detail=f"Discovery run {running_run.id} is already running"
        )
    
    try:
        # Create crawler and start run
        from sqlalchemy.orm import sessionmaker
        from database import engine
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        
        snmp_adapter = SnmpAdapter(timeout=5, retries=2)
        classifier = RouterClassifier()
        crawler = RouterDiscoveryCrawler(SessionLocal, snmp_adapter, classifier)
        
        logger = logging.getLogger(__name__)
        run_id = crawler.start_run(request.root_ip, request.snmp_community, request.snmp_version)
        
        return StartDiscoveryResponse(run_id=run_id)
    
    except Exception as e:
        logger.error(f"Failed to start discovery: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/runs/{run_id}/state", response_model=DiscoveryRunResponse)
def get_run_state(run_id: int, db: Session = Depends(get_db)):
    """Get the current state of a discovery run."""
    run = db.query(DiscoveryRun).filter(DiscoveryRun.id == run_id).first()
    
    if not run:
        raise HTTPException(status_code=404, detail=f"Discovery run {run_id} not found")
    
    return DiscoveryRunResponse(
        id=run.id,
        started_at=run.started_at.isoformat() if run.started_at else None,
        finished_at=run.finished_at.isoformat() if run.finished_at else None,
        status=run.status,
        root_ip=str(run.root_ip),
        snmp_community=run.snmp_community,
        snmp_version=run.snmp_version,
        error_message=run.error_message
    )


@router.get("/runs/{run_id}/topology", response_model=TopologyResponse)
def get_topology(run_id: int, db: Session = Depends(get_db)):
    """Get the topology graph for a discovery run."""
    # Verify run exists
    run = db.query(DiscoveryRun).filter(DiscoveryRun.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail=f"Discovery run {run_id} not found")
    
    # Fetch nodes (routers)
    routers = db.query(Router).filter(Router.run_id == run_id).all()
    nodes = [
        RouterNodeResponse(
            id=r.id,
            ip=str(r.primary_ip),
            hostname=r.hostname,
            is_router=r.is_router,
            router_score=r.router_score,
            classification_reason=r.classification_reason,
            vendor=r.vendor,
            model=r.model
        )
        for r in routers
    ]
    
    # Fetch edges
    edges_db = db.query(TopologyEdge).filter(TopologyEdge.run_id == run_id).all()
    edges = [
        TopologyEdgeResponse(
            from_id=e.from_router_id,
            to_id=e.to_router_id,
            reason=e.reason
        )
        for e in edges_db
    ]
    
    return TopologyResponse(nodes=nodes, edges=edges)


@router.get("/runs/{run_id}/routers/{router_id}", response_model=RouterDetailResponse)
def get_router_detail(run_id: int, router_id: int, db: Session = Depends(get_db)):
    """Get detailed information about a specific router."""
    router = db.query(Router).filter(
        and_(Router.run_id == run_id, Router.id == router_id)
    ).first()
    
    if not router:
        raise HTTPException(status_code=404, detail="Router not found")
    
    # Fetch networks
    networks = db.query(RouterNetwork).filter(RouterNetwork.router_id == router_id).all()
    network_list = [str(n.network) for n in networks]
    
    # Fetch routes
    routes = db.query(RouterRoute).filter(RouterRoute.router_id == router_id).all()
    route_list = [
        {
            "destination": str(r.destination),
            "next_hop": str(r.next_hop) if r.next_hop else None,
            "protocol": r.protocol,
            "admin_distance": r.admin_distance,
            "metric": r.metric
        }
        for r in routes
    ]
    
    return RouterDetailResponse(
        id=router.id,
        ip=str(router.primary_ip),
        hostname=router.hostname,
        is_router=router.is_router,
        router_score=router.router_score,
        classification_reason=router.classification_reason,
        vendor=router.vendor,
        model=router.model,
        networks=network_list,
        routes=route_list
    )
