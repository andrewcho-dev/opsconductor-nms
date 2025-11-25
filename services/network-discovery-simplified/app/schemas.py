from pydantic import BaseModel
from typing import Optional, List, Dict
from datetime import datetime


class DiscoveryRequest(BaseModel):
    root_ip: str
    snmp_community: str = 'public'
    ssh_credentials: Optional[Dict[str, str]] = None


class DiscoveryStatus(BaseModel):
    id: int
    status: str
    root_ip: str
    started_at: datetime
    finished_at: Optional[datetime]
    error_message: Optional[str]
    routers_found: int
    routes_found: int
    networks_found: int


class RouterInfo(BaseModel):
    id: int
    ip_address: str
    hostname: Optional[str]
    vendor: Optional[str]
    model: Optional[str]
    is_router: bool
    router_score: float
    classification_reason: str
    discovered_via: str
    created_at: datetime


class RouteInfo(BaseModel):
    id: int
    router_id: int
    destination: str
    next_hop: Optional[str]
    protocol: Optional[str]
    discovered_via: str


class NetworkInfo(BaseModel):
    id: int
    router_id: int
    network: str
    interface: Optional[str]
    is_connected: bool


class TopologyLinkInfo(BaseModel):
    id: int
    from_router_id: int
    to_router_id: int
    shared_network: str
    link_type: str


class DiscoverySummary(BaseModel):
    discovery_run: DiscoveryStatus
    routers: List[RouterInfo]
    routes: List[RouteInfo]
    networks: List[NetworkInfo]
    topology_links: List[TopologyLinkInfo]
    local_networks: List[str]  # Extracted local network ranges
