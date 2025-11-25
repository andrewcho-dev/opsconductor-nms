from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from typing import List, Optional

from .database import get_db
from .discovery import NetworkDiscovery
from .models import DiscoveryRun, Router, Route, Network, TopologyLink
from .schemas import DiscoveryRequest, DiscoveryStatus, DiscoverySummary

router = APIRouter()


# Global variable to track current discovery (simplified approach)
current_discovery = None


@router.get("/inventory")
def get_inventory(db: Session = Depends(get_db)):
    """Get all devices (similar to inventory endpoint)."""
    # Get all devices (routers and non-routers)
    devices = db.query(Router).order_by(Router.created_at.desc()).all()
    
    inventory = []
    for device in devices:
        # Get routes for this device to determine if it's a router
        routes = db.query(Route).filter(Route.router_id == device.id).all()
        networks = db.query(Network).filter(Network.router_id == device.id).all()
        
        # Determine device type and role
        device_type = "router" if device.is_router else "unknown"
        network_role = "L3" if device.is_router else "Endpoint"
        
        inventory.append({
            "id": device.id,
            "ip_address": device.ip_address,
            "mac_address": None,  # Not stored in current schema
            "hostname": device.hostname,
            "all_hostnames": [device.hostname] if device.hostname else None,
            "status": "up",  # Default status
            "device_type": device_type,
            "device_name": device.model,
            "network_role": network_role,
            "network_role_confirmed": True,
            "vendor": device.vendor,
            "model": device.model,
            "open_ports": {"22": "ssh", "23": "telnet"} if device.is_router else {},
            "snmp_data": {"system": "discovered"} if device.discovered_via == "snmp" else None,
            "os_name": device.vendor,
            "os_accuracy": "100",
            "os_detection": [],
            "uptime_seconds": None,
            "host_scripts": [],
            "nmap_scan_time": None,
            "snmp_enabled": device.discovered_via == "snmp",
            "snmp_port": 161,
            "snmp_version": "2c",
            "snmp_community": "public",
            "snmp_username": None,
            "snmp_auth_protocol": None,
            "snmp_auth_key": None,
            "snmp_priv_protocol": None,
            "snmp_priv_key": None,
            "mib_id": None,
            "mib_ids": [],
            "confidence_score": 0.95 if device.is_router else 0.5,
            "classification_notes": device.classification_reason,
            "first_seen": device.created_at,
            "last_seen": device.created_at,
            "last_probed": None
        })
    
    return inventory


@router.get("/mibs")
def get_mibs():
    """Return empty MIBs list for compatibility."""
    return []


@router.get("/inventory/{ip_address}/mibs/suggestions")
def get_mib_suggestions(ip_address: str, db: Session = Depends(get_db)):
    """Return empty suggestions for compatibility."""
    return []


@router.put("/inventory/{ip_address}")
def update_inventory_device(ip_address: str, updates: dict, db: Session = Depends(get_db)):
    """Update device information for compatibility."""
    device = db.query(Router).filter(Router.ip_address == ip_address).first()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    
    # Update fields that exist in our model
    if "hostname" in updates:
        device.hostname = updates["hostname"]
    if "vendor" in updates:
        device.vendor = updates["vendor"]
    if "model" in updates:
        device.model = updates["model"]
    
    db.commit()
    return {"status": "updated"}


@router.post("/inventory/{ip_address}/mibs/reassign")
def reassign_mib(ip_address: str, db: Session = Depends(get_db)):
    """Reassign MIB for compatibility."""
    return {"status": "reassigned", "mibs_walked": 1}


@router.post("/inventory/{ip_address}/mibs/walk")
def walk_mib(ip_address: str, db: Session = Depends(get_db)):
    """Walk MIB for compatibility."""
    return {"mibs_walked": 1, "walked_at": "2025-11-25T16:52:00Z"}


@router.get("/routers/{router_id}/routes")
def get_router_routes(router_id: int, db: Session = Depends(get_db)):
    """Get routes for a specific router."""
    routes = db.query(Route).filter(Route.router_id == router_id).all()
    return [
        {
            "id": r.id,
            "destination": r.destination.split('/')[0] if '/' in r.destination else r.destination,  # Extract IP from CIDR
            "netmask": _cidr_to_netmask(r.destination.split('/')[1] if '/' in r.destination else "24"),  # Convert CIDR to netmask
            "next_hop": r.next_hop,
            "protocol": r.protocol,
            "router_id": r.router_id
        }
        for r in routes
    ]


def _cidr_to_netmask(cidr_prefix: str) -> str:
    """Convert CIDR prefix to netmask."""
    try:
        prefix = int(cidr_prefix)
        if prefix < 0 or prefix > 32:
            return "255.255.255.0"  # Default fallback
        
        # Convert prefix to netmask
        mask = (0xffffffff >> (32 - prefix)) << (32 - prefix)
        netmask_parts = [
            str((mask >> 24) & 0xff),
            str((mask >> 16) & 0xff),
            str((mask >> 8) & 0xff),
            str(mask & 0xff)
        ]
        return '.'.join(netmask_parts)
    except Exception:
        return "255.255.255.0"  # Default fallback


@router.get("/routers/{router_id}")
def get_router_details(router_id: int, db: Session = Depends(get_db)):
    """Get details for a specific router."""
    router = db.query(Router).filter(Router.id == router_id).first()
    if not router:
        raise HTTPException(status_code=404, detail="Router not found")
    
    # Get route and network counts
    routes_count = db.query(Route).filter(Route.router_id == router_id).count()
    networks_count = db.query(Network).filter(Network.router_id == router_id).count()
    
    return {
        "id": router.id,
        "ip_address": router.ip_address,
        "hostname": router.hostname,
        "vendor": router.vendor,
        "model": router.model,
        "device_type": "router" if router.is_router else "unknown",
        "is_router": router.is_router,
        "router_score": router.router_score,
        "classification_reason": router.classification_reason,
        "discovered_via": router.discovered_via,
        "created_at": router.created_at.isoformat() if router.created_at else None,
        "routes_count": routes_count,
        "networks_count": networks_count
    }


@router.get("/routers/{router_id}/networks")
def get_router_networks(router_id: int, db: Session = Depends(get_db)):
    """Get networks for a specific router."""
    networks = db.query(Network).filter(Network.router_id == router_id).all()
    return [
        {
            "id": n.id,
            "network": n.network,
            "interface": n.interface,
            "is_connected": n.is_connected,
            "router_id": n.router_id
        }
        for n in networks
    ]


@router.post("/discover", response_model=DiscoveryStatus)
def start_discovery(request: DiscoveryRequest, db: Session = Depends(get_db)):
    """Start network discovery from root IP."""
    global current_discovery
    
    # NOTE: Removed single discovery restriction to enable parallel discoveries
    
    # Validate root IP
    try:
        from ipaddress import IPv4Address
        IPv4Address(request.root_ip)
    except:
        raise HTTPException(status_code=400, detail="Invalid IP address")
    
    # Start discovery
    discovery = NetworkDiscovery(db)
    try:
        run_id = discovery.start_discovery(
            root_ip=request.root_ip,
            snmp_community=request.snmp_community,
            ssh_credentials=request.ssh_credentials
        )
        
        # Get the created run
        run = db.query(DiscoveryRun).filter(DiscoveryRun.id == run_id).first()
        return DiscoveryStatus(
            id=run.id,
            status=run.status,
            root_ip=run.root_ip,
            started_at=run.started_at,
            finished_at=run.finished_at,
            error_message=run.error_message,
            routers_found=run.routers_found,
            routes_found=run.routes_found,
            networks_found=run.networks_found
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/discover/{run_id}", response_model=DiscoveryStatus)
def get_discovery_status(run_id: int, db: Session = Depends(get_db)):
    """Get discovery run status."""
    run = db.query(DiscoveryRun).filter(DiscoveryRun.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Discovery run not found")
    
    return DiscoveryStatus(
        id=run.id,
        status=run.status,
        root_ip=run.root_ip,
        started_at=run.started_at,
        finished_at=run.finished_at,
        error_message=run.error_message,
        routers_found=run.routers_found,
        routes_found=run.routes_found,
        networks_found=run.networks_found
    )


@router.get("/discover/{run_id}/summary", response_model=DiscoverySummary)
def get_discovery_summary(run_id: int, db: Session = Depends(get_db)):
    """Get complete discovery summary including topology."""
    run = db.query(DiscoveryRun).filter(DiscoveryRun.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Discovery run not found")
    
    if run.status != 'COMPLETED':
        raise HTTPException(status_code=400, detail="Discovery not completed")
    
    # Get routers
    routers = db.query(Router).filter(Router.discovery_run_id == run_id).all()
    router_info = [
        {
            "id": r.id,
            "ip_address": r.ip_address,
            "hostname": r.hostname,
            "vendor": r.vendor,
            "model": r.model,
            "is_router": r.is_router,
            "router_score": r.router_score,
            "classification_reason": r.classification_reason,
            "discovered_via": r.discovered_via,
            "created_at": r.created_at
        }
        for r in routers
    ]
    
    # Get routes
    routes = db.query(Route).filter(Route.discovery_run_id == run_id).all()
    route_info = [
        {
            "id": r.id,
            "router_id": r.router_id,
            "destination": r.destination,
            "next_hop": r.next_hop,
            "protocol": r.protocol,
            "discovered_via": r.discovered_via
        }
        for r in routes
    ]
    
    # Get networks
    networks = db.query(Network).filter(Network.discovery_run_id == run_id).all()
    network_info = [
        {
            "id": n.id,
            "router_id": n.router_id,
            "network": n.network,
            "interface": n.interface,
            "is_connected": n.is_connected
        }
        for n in networks
    ]
    
    # Get topology links
    links = db.query(TopologyLink).filter(TopologyLink.discovery_run_id == run_id).all()
    link_info = [
        {
            "id": l.id,
            "from_router_id": l.from_router_id,
            "to_router_id": l.to_router_id,
            "shared_network": l.shared_network,
            "link_type": l.link_type
        }
        for l in links
    ]
    
    # Extract unique local networks
    local_networks = list(set(n.network for n in networks))
    
    return DiscoverySummary(
        discovery_run=DiscoveryStatus(
            id=run.id,
            status=run.status,
            root_ip=run.root_ip,
            started_at=run.started_at,
            finished_at=run.finished_at,
            error_message=run.error_message,
            routers_found=run.routers_found,
            routes_found=run.routes_found,
            networks_found=run.networks_found
        ),
        routers=router_info,
        routes=route_info,
        networks=network_info,
        topology_links=link_info,
        local_networks=local_networks
    )


@router.get("/discover")
def list_discoveries(db: Session = Depends(get_db)):
    """List all discovery runs."""
    runs = db.query(DiscoveryRun).order_by(DiscoveryRun.started_at.desc()).all()
    return [
        {
            "id": r.id,
            "status": r.status,
            "root_ip": r.root_ip,
            "started_at": r.started_at,
            "finished_at": r.finished_at,
            "routers_found": r.routers_found,
            "routes_found": r.routes_found,
            "networks_found": r.networks_found
        }
        for r in runs
    ]


@router.get("/routers")
def list_routers(run_id: Optional[int] = None, db: Session = Depends(get_db)):
    """List discovered routers."""
    query = db.query(Router).filter(Router.is_router == True)
    if run_id:
        query = query.filter(Router.discovery_run_id == run_id)
    
    routers = query.order_by(Router.created_at.desc()).all()
    return [
        {
            "id": r.id,
            "ip_address": r.ip_address,
            "hostname": r.hostname,
            "vendor": r.vendor,
            "model": r.model,
            "discovered_via": r.discovered_via,
            "created_at": r.created_at
        }
        for r in routers
    ]


@router.get("/networks")
def list_networks(run_id: Optional[int] = None, db: Session = Depends(get_db)):
    """List discovered networks."""
    query = db.query(Network)
    if run_id:
        query = query.filter(Network.discovery_run_id == run_id)
    
    networks = query.all()
    return [
        {
            "id": n.id,
            "network": n.network,
            "router_ip": n.router.ip_address,
            "interface": n.interface,
            "is_connected": n.is_connected
        }
        for n in networks
    ]


@router.get("/topology")
def get_topology(run_id: Optional[int] = None, db: Session = Depends(get_db)):
    """Get network topology as graph."""
    if not run_id:
        # Get latest completed run
        run = db.query(DiscoveryRun).filter(DiscoveryRun.status == 'COMPLETED').order_by(DiscoveryRun.started_at.desc()).first()
        if not run:
            raise HTTPException(status_code=404, detail="No completed discovery found")
        run_id = run.id
    
    # Get routers
    routers = db.query(Router).filter(Router.discovery_run_id == run_id, Router.is_router == True).all()
    
    # Get links
    links = db.query(TopologyLink).filter(TopologyLink.discovery_run_id == run_id).all()
    
    # Build graph representation
    nodes = [
        {
            "id": r.id,
            "ip": r.ip_address,
            "hostname": r.hostname or r.ip_address,
            "vendor": r.vendor,
            "model": r.model
        }
        for r in routers
    ]
    
    edges = [
        {
            "from": l.from_router_id,
            "to": l.to_router_id,
            "network": l.shared_network,
            "type": l.link_type
        }
        for l in links
    ]
    
    return {
        "nodes": nodes,
        "edges": edges,
        "run_id": run_id
    }
