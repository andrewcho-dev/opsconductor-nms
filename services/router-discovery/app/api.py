import logging

from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel, Field
from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import and_
from datetime import datetime, timezone
from ipaddress import ip_network

from .models import DiscoveryRun, Router, RouterNetwork, RouterRoute, TopologyEdge
from .database import get_db

router = APIRouter(prefix="/api/router-discovery", tags=["discovery"])


# Request/Response models
class CredentialPair(BaseModel):
    username: str
    password: str
    vrf: Optional[str] = None


class StartDiscoveryRequest(BaseModel):
    root_ip: str
    snmp_community: str
    snmp_version: str = Field(default="2c", pattern="^(2c|3)$")
    cli_default_credentials: Optional[List[CredentialPair]] = None


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


class RouterRouteResponse(BaseModel):
    cidr: str
    network: str
    netmask: str
    prefix_len: int
    next_hop: Optional[str]
    protocol: Optional[str]


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
    routes: List[RouterRouteResponse]
    
    class Config:
        from_attributes = True


class StartDiscoveryResponse(BaseModel):
    run_id: int


class ErrorResponse(BaseModel):
    error: str
    detail: Optional[str]


DEFAULT_CLI_CREDENTIALS: List[CredentialPair] = [
    CredentialPair(username="admin", password="Metrolink222"),
    CredentialPair(username="root", password="Metrolink222"),
    CredentialPair(username="admin", password="admin"),
    CredentialPair(username="admin", password="password"),
    CredentialPair(username="admin", password="Metrolink96$"),
]


class CliDefaultsRequest(BaseModel):
    credentials: List[CredentialPair]


# Endpoints


@router.get("/default-cli-credentials", response_model=List[CredentialPair])
def get_default_cli_credentials():
    """Return the built-in default CLI credential list."""
    return DEFAULT_CLI_CREDENTIALS


@router.put("/default-cli-credentials", response_model=List[CredentialPair])
def update_default_cli_credentials(payload: CliDefaultsRequest):
    """Replace the global default credential list used for CLI fallbacks."""
    if not payload.credentials:
        raise HTTPException(status_code=422, detail="At least one credential must be provided")

    for cred in payload.credentials:
        if not cred.username or not cred.password:
            raise HTTPException(status_code=422, detail="Credentials must include username and password")

    # Update in-place so existing references continue to see latest list
    DEFAULT_CLI_CREDENTIALS.clear()
    DEFAULT_CLI_CREDENTIALS.extend(payload.credentials)
    return DEFAULT_CLI_CREDENTIALS


@router.get("/runs", response_model=List[DiscoveryRunResponse])
def list_runs(
    status: Optional[str] = Query(None, description="Filter by run status"),
    limit: int = Query(50, ge=1, le=200, description="Maximum number of runs to return"),
    db: Session = Depends(get_db),
):
    """List discovery runs, newest first."""
    query = db.query(DiscoveryRun).order_by(DiscoveryRun.started_at.desc())
    if status:
        query = query.filter(DiscoveryRun.status == status)

    runs = query.limit(limit).all()
    return [
        DiscoveryRunResponse(
            id=run.id,
            started_at=run.started_at.isoformat() if run.started_at else None,
            finished_at=run.finished_at.isoformat() if run.finished_at else None,
            status=run.status,
            root_ip=str(run.root_ip),
            snmp_community=run.snmp_community,
            snmp_version=run.snmp_version,
            error_message=run.error_message,
        )
        for run in runs
    ]

@router.post("/start", response_model=StartDiscoveryResponse, status_code=201)
def start_discovery(request: StartDiscoveryRequest, db: Session = Depends(get_db)):
    """Start a new discovery run."""
    from .crawler import RouterDiscoveryCrawler
    from .snmp_adapter import SnmpAdapter
    from .router_classifier import RouterClassifier
    
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
        from .database import engine
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        
        snmp_adapter = SnmpAdapter(timeout=15, retries=3)
        classifier = RouterClassifier()
        crawler = RouterDiscoveryCrawler(SessionLocal, snmp_adapter, classifier)
        
        logger = logging.getLogger(__name__)
        cli_defaults = request.cli_default_credentials or DEFAULT_CLI_CREDENTIALS
        # Convert to primitive dicts for storage
        cli_defaults_dicts = [cred.model_dump() for cred in cli_defaults]

        run_id = crawler.start_run(
            request.root_ip,
            request.snmp_community,
            request.snmp_version,
            cli_default_credentials=cli_defaults_dicts,
        )
        
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
    
    networks = db.query(RouterNetwork).filter(
        and_(RouterNetwork.run_id == run_id, RouterNetwork.router_id == router_id)
    ).all()
    network_list = [str(n.network) for n in networks]
    
    routes = db.query(RouterRoute).filter(
        and_(RouterRoute.run_id == run_id, RouterRoute.router_id == router_id)
    ).all()
    route_list = []
    for r in routes:
        try:
            cidr = ip_network(str(r.destination))
            route_list.append(RouterRouteResponse(
                cidr=str(cidr),
                network=str(cidr.network_address),
                netmask=str(cidr.netmask),
                prefix_len=cidr.prefixlen,
                next_hop=str(r.next_hop) if r.next_hop else None,
                protocol=r.protocol
            ))
        except ValueError:
            route_list.append(RouterRouteResponse(
                cidr=str(r.destination),
                network=str(r.destination),
                netmask="",
                prefix_len=0,
                next_hop=str(r.next_hop) if r.next_hop else None,
                protocol=r.protocol
            ))
    
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


@router.post("/runs/{run_id}/cancel", status_code=200)
def cancel_discovery(run_id: int, db: Session = Depends(get_db)):
    """Cancel a discovery run."""
    run = db.query(DiscoveryRun).filter(DiscoveryRun.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail=f"Discovery run {run_id} not found")
    
    if run.status not in ["RUNNING", "PAUSED", "PENDING"]:
        raise HTTPException(status_code=400, detail=f"Cannot cancel run with status {run.status}")
    
    run.status = "CANCELLED"
    run.finished_at = datetime.now(timezone.utc)
    db.commit()
    
    return {"status": "CANCELLED", "run_id": run_id}


@router.post("/runs/{run_id}/pause", status_code=200)
def pause_discovery(run_id: int, db: Session = Depends(get_db)):
    """Pause a discovery run."""
    run = db.query(DiscoveryRun).filter(DiscoveryRun.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail=f"Discovery run {run_id} not found")
    
    if run.status != "RUNNING":
        raise HTTPException(status_code=400, detail=f"Can only pause RUNNING runs, current status: {run.status}")
    
    run.status = "PAUSED"
    db.commit()
    
    return {"status": "PAUSED", "run_id": run_id}


@router.post("/runs/{run_id}/resume", status_code=200)
def resume_discovery(run_id: int, db: Session = Depends(get_db)):
    """Resume a paused discovery run."""
    run = db.query(DiscoveryRun).filter(DiscoveryRun.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail=f"Discovery run {run_id} not found")
    
    if run.status != "PAUSED":
        raise HTTPException(status_code=400, detail=f"Can only resume PAUSED runs, current status: {run.status}")
    
    run.status = "RUNNING"
    db.commit()
    
    return {"status": "RUNNING", "run_id": run_id}


class CLIRouteRequest(BaseModel):
    username: str
    password: str
    vrf: Optional[str] = None


class CLIRouteResponse(BaseModel):
    routes_added: int
    message: str


@router.post("/runs/{run_id}/routers/{router_id}/cli-routes", response_model=CLIRouteResponse)
def collect_cli_routes(
    run_id: int,
    router_id: int,
    request: CLIRouteRequest,
    db: Session = Depends(get_db),
):
    """Collect IPv4 routes for a router via SSH/CLI when SNMP routes are unavailable."""
    from .cli_routing import fetch_vrf_routes_via_ssh
    from .crawler import RouterDiscoveryCrawler
    from .snmp_adapter import SnmpAdapter
    from .router_classifier import RouterClassifier
    from sqlalchemy.orm import sessionmaker
    from .database import engine

    router = db.query(Router).filter(
        and_(Router.run_id == run_id, Router.id == router_id)
    ).first()

    if not router:
        raise HTTPException(status_code=404, detail="Router not found")

    try:
        cli_routes = fetch_vrf_routes_via_ssh(
            host=str(router.primary_ip),
            username=request.username,
            password=request.password,
            vrf=request.vrf,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"CLI route fetch failed: {exc}")

    routes_added = 0
    for entry in cli_routes:
        cidr_str = f"{entry.destination}/{entry.prefix_length}"
        db_route = RouterRoute(
            run_id=run_id,
            router_id=router_id,
            destination=cidr_str,
            next_hop=entry.next_hop,
            protocol=entry.protocol,
            admin_distance=None,
            metric=None,
        )
        db.add(db_route)
        routes_added += 1

    db.commit()

    # Kick off additional discovery for newly learned next hops
    neighbor_candidates = {
        entry.next_hop
        for entry in cli_routes
        if entry.next_hop
    }

    if neighbor_candidates:
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        snmp_adapter = SnmpAdapter(timeout=15, retries=3)
        classifier = RouterClassifier()
        crawler = RouterDiscoveryCrawler(SessionLocal, snmp_adapter, classifier)
        try:
            crawler.resume_run(run_id, list(neighbor_candidates))
        except Exception as exc:
            logger = logging.getLogger(__name__)
            logger.error("Failed to resume discovery after CLI routes: %s", exc)

    return CLIRouteResponse(
        routes_added=routes_added,
        message=f"Added {routes_added} routes via CLI for router {router_id}",
    )
