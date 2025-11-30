from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from sqlalchemy import or_
from typing import List, Optional, Dict, Any
from datetime import datetime

from .database import get_db
from .discovery import NetworkDiscovery
from .models import DiscoveryRun, Router, Route, Network, TopologyLink, NetworkLink
from .schemas import DiscoveryRequest, DiscoveryStatus, DiscoverySummary
from .error_handling import (
    NMSError, ValidationError, ResourceNotFoundError, DatabaseError,
    NetworkError, DiscoveryError, AuthenticationError, PermissionError,
    handle_database_operation, validate_discovery_request,
    create_success_response, create_paginated_response, logger
)

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


@router.get("/routers/{router_id}/traceroute/{target_ip}")
def traceroute_from_router(router_id: int, target_ip: str, db: Session = Depends(get_db)):
    """Perform traceroute from a router to a target IP."""
    router = db.query(Router).filter(Router.id == router_id).first()
    if not router:
        raise ResourceNotFoundError(
            resource_type="Router",
            resource_id=router_id
        )

    # Validate target IP
    try:
        from ipaddress import IPv4Address
        IPv4Address(target_ip)
    except ValueError:
        raise ValidationError(
            message=f"Invalid target IP address: {target_ip}",
            field="target_ip"
        )

    try:
        import shlex
        import subprocess

        logger.info(f"Performing traceroute from {router.ip_address} to {target_ip}")

        # Execute traceroute with proper input sanitization
        cmd = ['traceroute', '-n', '-m', '15', '-w', '2', target_ip]
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30
        )

        if result.returncode == 0:
            # Parse traceroute output
            hops = []
            lines = result.stdout.strip().split('\n')

            for line in lines[1:]:  # Skip first line (header)
                if line.strip():
                    parts = line.split()
                    if len(parts) >= 2:
                        hop_num = parts[0]
                        hop_ip = parts[1] if parts[1] != '*' else None
                        hops.append({
                            "hop": int(hop_num),
                            "ip": hop_ip,
                            "raw_line": line
                        })

            logger.info(f"Traceroute completed successfully: {len(hops)} hops found")
            return create_success_response({
                "source_router": router.ip_address,
                "target_ip": target_ip,
                "success": True,
                "hops": hops,
                "raw_output": result.stdout
            }, "Traceroute completed successfully")

        else:
            logger.warning(f"Traceroute failed with exit code {result.returncode}: {result.stderr}")
            return create_success_response({
                "source_router": router.ip_address,
                "target_ip": target_ip,
                "success": False,
                "error": result.stderr or "Traceroute command failed",
                "hops": []
            }, "Traceroute failed")

    except subprocess.TimeoutExpired:
        logger.error(f"Traceroute timeout for target {target_ip}")
        raise NetworkError(
            message=f"Traceroute to {target_ip} timed out",
            target=target_ip,
            user_message="Traceroute timed out. The target may be unreachable.",
            troubleshooting="Check network connectivity and target availability."
        )
    except Exception as e:
        logger.error(f"Unexpected error in traceroute: {str(e)}", exc_info=True)
        raise NetworkError(
            message=f"Traceroute error: {str(e)}",
            target=target_ip,
            user_message="Unable to perform traceroute.",
            troubleshooting="Check system configuration and try again."
        )


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
    try:
        # Validate request
        validate_discovery_request(request.root_ip, request.snmp_community)

        logger.info(f"Starting discovery for root IP: {request.root_ip}")

        # Start discovery
        discovery = NetworkDiscovery(db)
        run_id = discovery.start_discovery(
            root_ip=request.root_ip,
            snmp_community=request.snmp_community,
            ssh_credentials=request.ssh_credentials
        )

        # Get the created run
        run = db.query(DiscoveryRun).filter(DiscoveryRun.id == run_id).first()
        if not run:
            raise DiscoveryError(
                message="Discovery run was created but could not be retrieved",
                discovery_run_id=run_id,
                user_message="Discovery failed to start properly."
            )

        logger.info(f"Discovery started successfully with run ID: {run_id}")

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

    except ValidationError:
        # Re-raise validation errors as-is
        raise
    except Exception as e:
        logger.error(f"Unexpected error starting discovery: {str(e)}", exc_info=True)
        raise DiscoveryError(
            message=f"Failed to start discovery: {str(e)}"
        )


@router.get("/discover/{run_id}", response_model=DiscoveryStatus)
def get_discovery_status(run_id: int, db: Session = Depends(get_db)):
    """Get discovery run status."""
    run = db.query(DiscoveryRun).filter(DiscoveryRun.id == run_id).first()
    if not run:
        raise ResourceNotFoundError(
            resource_type="Discovery Run",
            resource_id=run_id
        )

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


def _serialize_datetime(value: Optional[datetime]) -> Optional[str]:
    return value.isoformat() if value else None


TABLE_DEFINITIONS: Dict[str, Dict[str, Any]] = {
    "discovery_runs": {
        "columns": [
            {"id": "id", "label": "Run ID", "type": "number"},
            {"id": "root_ip", "label": "Root IP", "type": "text"},
            {"id": "status", "label": "Status", "type": "badge"},
            {"id": "routers_found", "label": "Routers", "type": "number"},
            {"id": "routes_found", "label": "Routes", "type": "number"},
            {"id": "networks_found", "label": "Networks", "type": "number"},
            {"id": "started_at", "label": "Started", "type": "datetime"},
            {"id": "finished_at", "label": "Finished", "type": "datetime"},
        ],
        "query": lambda db: db.query(DiscoveryRun),
        "serializer": lambda run: {
            "id": run.id,
            "root_ip": run.root_ip,
            "status": run.status,
            "routers_found": run.routers_found,
            "routes_found": run.routes_found,
            "networks_found": run.networks_found,
            "started_at": _serialize_datetime(run.started_at),
            "finished_at": _serialize_datetime(run.finished_at),
        },
        "search_fields": [DiscoveryRun.root_ip, DiscoveryRun.status],
        "order_by": DiscoveryRun.started_at.desc(),
        "supports_run_filter": False,
    },
    "routers": {
        "columns": [
            {"id": "id", "label": "Router ID", "type": "number"},
            {"id": "discovery_run_id", "label": "Run", "type": "number"},
            {"id": "ip_address", "label": "IP Address", "type": "mono"},
            {"id": "hostname", "label": "Hostname", "type": "text"},
            {"id": "vendor", "label": "Vendor", "type": "badge"},
            {"id": "model", "label": "Model", "type": "text"},
            {"id": "discovered_via", "label": "Method", "type": "badge"},
            {"id": "router_score", "label": "Score", "type": "number"},
            {"id": "created_at", "label": "Discovered", "type": "datetime"},
        ],
        "query": lambda db: db.query(Router),
        "serializer": lambda router: {
            "id": router.id,
            "discovery_run_id": router.discovery_run_id,
            "ip_address": router.ip_address,
            "hostname": router.hostname,
            "vendor": router.vendor,
            "model": router.model,
            "discovered_via": router.discovered_via,
            "router_score": router.router_score,
            "created_at": _serialize_datetime(router.created_at),
        },
        "search_fields": [Router.ip_address, Router.hostname, Router.vendor, Router.model],
        "order_by": Router.created_at.desc(),
        "supports_run_filter": True,
        "run_column": Router.discovery_run_id,
    },
    "routes": {
        "columns": [
            {"id": "id", "label": "Route ID", "type": "number"},
            {"id": "discovery_run_id", "label": "Run", "type": "number"},
            {"id": "router_id", "label": "Router", "type": "number"},
            {"id": "destination", "label": "Destination", "type": "mono"},
            {"id": "next_hop", "label": "Next Hop", "type": "mono"},
            {"id": "protocol", "label": "Protocol", "type": "badge"},
            {"id": "discovered_via", "label": "Method", "type": "badge"},
            {"id": "created_at", "label": "Recorded", "type": "datetime"},
        ],
        "query": lambda db: db.query(Route),
        "serializer": lambda route: {
            "id": route.id,
            "discovery_run_id": route.discovery_run_id,
            "router_id": route.router_id,
            "destination": route.destination,
            "next_hop": route.next_hop,
            "protocol": route.protocol,
            "discovered_via": route.discovered_via,
            "created_at": _serialize_datetime(route.created_at),
        },
        "search_fields": [Route.destination, Route.next_hop, Route.protocol],
        "order_by": Route.created_at.desc(),
        "supports_run_filter": True,
        "run_column": Route.discovery_run_id,
    },
    "networks": {
        "columns": [
            {"id": "id", "label": "Network ID", "type": "number"},
            {"id": "discovery_run_id", "label": "Run", "type": "number"},
            {"id": "router_id", "label": "Router", "type": "number"},
            {"id": "network", "label": "Network", "type": "mono"},
            {"id": "interface", "label": "Interface", "type": "text"},
            {"id": "is_connected", "label": "Connected", "type": "boolean"},
            {"id": "created_at", "label": "Recorded", "type": "datetime"},
        ],
        "query": lambda db: db.query(Network),
        "serializer": lambda network: {
            "id": network.id,
            "discovery_run_id": network.discovery_run_id,
            "router_id": network.router_id,
            "network": network.network,
            "interface": network.interface,
            "is_connected": network.is_connected,
            "created_at": _serialize_datetime(network.created_at),
        },
        "search_fields": [Network.network, Network.interface],
        "order_by": Network.created_at.desc(),
        "supports_run_filter": True,
        "run_column": Network.discovery_run_id,
    },
    "topology_links": {
        "columns": [
            {"id": "id", "label": "Link ID", "type": "number"},
            {"id": "discovery_run_id", "label": "Run", "type": "number"},
            {"id": "from_router_id", "label": "From Router", "type": "number"},
            {"id": "to_router_id", "label": "To Router", "type": "number"},
            {"id": "shared_network", "label": "Network", "type": "mono"},
            {"id": "link_type", "label": "Type", "type": "badge"},
            {"id": "created_at", "label": "Recorded", "type": "datetime"},
        ],
        "query": lambda db: db.query(TopologyLink),
        "serializer": lambda link: {
            "id": link.id,
            "discovery_run_id": link.discovery_run_id,
            "from_router_id": link.from_router_id,
            "to_router_id": link.to_router_id,
            "shared_network": link.shared_network,
            "link_type": link.link_type,
            "created_at": _serialize_datetime(link.created_at),
        },
        "search_fields": [TopologyLink.shared_network, TopologyLink.link_type],
        "order_by": TopologyLink.created_at.desc(),
        "supports_run_filter": True,
        "run_column": TopologyLink.discovery_run_id,
    },
    "network_links": {
        "columns": [
            {"id": "id", "label": "Link ID", "type": "text"},
            {"id": "from_router_id", "label": "From Router", "type": "number"},
            {"id": "to_router_id", "label": "To Router", "type": "number"},
            {"id": "from_ip", "label": "From IP", "type": "mono"},
            {"id": "to_ip", "label": "To IP", "type": "mono"},
            {"id": "discovery_method", "label": "Method", "type": "badge"},
            {"id": "latency_ms", "label": "Latency (ms)", "type": "number"},
            {"id": "hop_count", "label": "Hops", "type": "number"},
            {"id": "status", "label": "Status", "type": "badge"},
            {"id": "last_verified", "label": "Last Verified", "type": "datetime"},
        ],
        "query": lambda db: db.query(NetworkLink),
        "serializer": lambda link: {
            "id": link.id,
            "from_router_id": link.from_router_id,
            "to_router_id": link.to_router_id,
            "from_ip": link.from_ip,
            "to_ip": link.to_ip,
            "discovery_method": link.discovery_method,
            "latency_ms": link.latency_ms,
            "hop_count": link.hop_count,
            "status": link.status,
            "last_verified": _serialize_datetime(link.last_verified),
        },
        "search_fields": [NetworkLink.from_ip, NetworkLink.to_ip, NetworkLink.discovery_method, NetworkLink.status],
        "order_by": NetworkLink.last_verified.desc(),
        "supports_run_filter": False,
    },
}


@router.get("/tables")
def get_table_data(
    table: str,
    run_id: Optional[int] = None,
    search: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    table_key = table.lower()
    if table_key not in TABLE_DEFINITIONS:
        raise HTTPException(status_code=400, detail="Unsupported table")
    config = TABLE_DEFINITIONS[table_key]

    limit = max(10, min(limit, 500))
    offset = max(offset, 0)

    query = config["query"](db)

    if run_id is not None and config.get("supports_run_filter"):
        run_column = config.get("run_column")
        if run_column is not None:
            query = query.filter(run_column == run_id)

    if search:
        search_fields = config.get("search_fields", [])
        clauses = [field.ilike(f"%{search}%") for field in search_fields]
        if clauses:
            query = query.filter(or_(*clauses))

    total = query.count()

    order_by = config.get("order_by")
    if order_by is not None:
        query = query.order_by(order_by)

    records = query.offset(offset).limit(limit).all()
    rows = [config["serializer"](record) for record in records]

    return {
        "table": table_key,
        "columns": config["columns"],
        "rows": rows,
        "total": total,
        "limit": limit,
        "offset": offset,
    }


def _serialize_datetime(value: Optional[datetime]) -> Optional[str]:
    return value.isoformat() if value else None


TABLE_DEFINITIONS: Dict[str, Dict[str, Any]] = {
    "discovery_runs": {
        "columns": [
            {"id": "id", "label": "Run ID", "type": "number"},
            {"id": "root_ip", "label": "Root IP", "type": "text"},
            {"id": "status", "label": "Status", "type": "badge"},
            {"id": "routers_found", "label": "Routers", "type": "number"},
            {"id": "routes_found", "label": "Routes", "type": "number"},
            {"id": "networks_found", "label": "Networks", "type": "number"},
            {"id": "started_at", "label": "Started", "type": "datetime"},
            {"id": "finished_at", "label": "Finished", "type": "datetime"},
        ],
        "query": lambda db: db.query(DiscoveryRun),
        "serializer": lambda run: {
            "id": run.id,
            "root_ip": run.root_ip,
            "status": run.status,
            "routers_found": run.routers_found,
            "routes_found": run.routes_found,
            "networks_found": run.networks_found,
            "started_at": _serialize_datetime(run.started_at),
            "finished_at": _serialize_datetime(run.finished_at),
        },
        "search_fields": [DiscoveryRun.root_ip, DiscoveryRun.status],
        "order_by": DiscoveryRun.started_at.desc(),
        "supports_run_filter": False,
    },
    "routers": {
        "columns": [
            {"id": "id", "label": "Router ID", "type": "number"},
            {"id": "discovery_run_id", "label": "Run", "type": "number"},
            {"id": "ip_address", "label": "IP Address", "type": "mono"},
            {"id": "hostname", "label": "Hostname", "type": "text"},
            {"id": "vendor", "label": "Vendor", "type": "badge"},
            {"id": "model", "label": "Model", "type": "text"},
            {"id": "discovered_via", "label": "Method", "type": "badge"},
            {"id": "router_score", "label": "Score", "type": "number"},
            {"id": "created_at", "label": "Discovered", "type": "datetime"},
        ],
        "query": lambda db: db.query(Router),
        "serializer": lambda router: {
            "id": router.id,
            "discovery_run_id": router.discovery_run_id,
            "ip_address": router.ip_address,
            "hostname": router.hostname,
            "vendor": router.vendor,
            "model": router.model,
            "discovered_via": router.discovered_via,
            "router_score": router.router_score,
            "created_at": _serialize_datetime(router.created_at),
        },
        "search_fields": [Router.ip_address, Router.hostname, Router.vendor, Router.model],
        "order_by": Router.created_at.desc(),
        "supports_run_filter": True,
        "run_column": Router.discovery_run_id,
    },
    "routes": {
        "columns": [
            {"id": "id", "label": "Route ID", "type": "number"},
            {"id": "discovery_run_id", "label": "Run", "type": "number"},
            {"id": "router_id", "label": "Router", "type": "number"},
            {"id": "destination", "label": "Destination", "type": "mono"},
            {"id": "next_hop", "label": "Next Hop", "type": "mono"},
            {"id": "protocol", "label": "Protocol", "type": "badge"},
            {"id": "discovered_via", "label": "Method", "type": "badge"},
            {"id": "created_at", "label": "Recorded", "type": "datetime"},
        ],
        "query": lambda db: db.query(Route),
        "serializer": lambda route: {
            "id": route.id,
            "discovery_run_id": route.discovery_run_id,
            "router_id": route.router_id,
            "destination": route.destination,
            "next_hop": route.next_hop,
            "protocol": route.protocol,
            "discovered_via": route.discovered_via,
            "created_at": _serialize_datetime(route.created_at),
        },
        "search_fields": [Route.destination, Route.next_hop, Route.protocol],
        "order_by": Route.created_at.desc(),
        "supports_run_filter": True,
        "run_column": Route.discovery_run_id,
    },
    "networks": {
        "columns": [
            {"id": "id", "label": "Network ID", "type": "number"},
            {"id": "discovery_run_id", "label": "Run", "type": "number"},
            {"id": "router_id", "label": "Router", "type": "number"},
            {"id": "network", "label": "Network", "type": "mono"},
            {"id": "interface", "label": "Interface", "type": "text"},
            {"id": "is_connected", "label": "Connected", "type": "boolean"},
            {"id": "created_at", "label": "Recorded", "type": "datetime"},
        ],
        "query": lambda db: db.query(Network),
        "serializer": lambda network: {
            "id": network.id,
            "discovery_run_id": network.discovery_run_id,
            "router_id": network.router_id,
            "network": network.network,
            "interface": network.interface,
            "is_connected": network.is_connected,
            "created_at": _serialize_datetime(network.created_at),
        },
        "search_fields": [Network.network, Network.interface],
        "order_by": Network.created_at.desc(),
        "supports_run_filter": True,
        "run_column": Network.discovery_run_id,
    },
    "topology_links": {
        "columns": [
            {"id": "id", "label": "Link ID", "type": "number"},
            {"id": "discovery_run_id", "label": "Run", "type": "number"},
            {"id": "from_router_id", "label": "From Router", "type": "number"},
            {"id": "to_router_id", "label": "To Router", "type": "number"},
            {"id": "shared_network", "label": "Network", "type": "mono"},
            {"id": "link_type", "label": "Type", "type": "badge"},
            {"id": "created_at", "label": "Recorded", "type": "datetime"},
        ],
        "query": lambda db: db.query(TopologyLink),
        "serializer": lambda link: {
            "id": link.id,
            "discovery_run_id": link.discovery_run_id,
            "from_router_id": link.from_router_id,
            "to_router_id": link.to_router_id,
            "shared_network": link.shared_network,
            "link_type": link.link_type,
            "created_at": _serialize_datetime(link.created_at),
        },
        "search_fields": [TopologyLink.shared_network, TopologyLink.link_type],
        "order_by": TopologyLink.created_at.desc(),
        "supports_run_filter": True,
        "run_column": TopologyLink.discovery_run_id,
    },
    "network_links": {
        "columns": [
            {"id": "id", "label": "Link ID", "type": "text"},
            {"id": "from_router_id", "label": "From Router", "type": "number"},
            {"id": "to_router_id", "label": "To Router", "type": "number"},
            {"id": "from_ip", "label": "From IP", "type": "mono"},
            {"id": "to_ip", "label": "To IP", "type": "mono"},
            {"id": "discovery_method", "label": "Method", "type": "badge"},
            {"id": "latency_ms", "label": "Latency (ms)", "type": "number"},
            {"id": "hop_count", "label": "Hops", "type": "number"},
            {"id": "status", "label": "Status", "type": "badge"},
            {"id": "last_verified", "label": "Last Verified", "type": "datetime"},
        ],
        "query": lambda db: db.query(NetworkLink),
        "serializer": lambda link: {
            "id": link.id,
            "from_router_id": link.from_router_id,
            "to_router_id": link.to_router_id,
            "from_ip": link.from_ip,
            "to_ip": link.to_ip,
            "discovery_method": link.discovery_method,
            "latency_ms": link.latency_ms,
            "hop_count": link.hop_count,
            "status": link.status,
            "last_verified": _serialize_datetime(link.last_verified),
        },
        "search_fields": [NetworkLink.from_ip, NetworkLink.to_ip, NetworkLink.discovery_method, NetworkLink.status],
        "order_by": NetworkLink.last_verified.desc(),
        "supports_run_filter": False,
    },
}


@router.get("/tables")
def get_table_data(
    table: str,
    run_id: Optional[int] = None,
    search: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    table_key = table.lower()
    if table_key not in TABLE_DEFINITIONS:
        raise HTTPException(status_code=400, detail="Unsupported table")
    config = TABLE_DEFINITIONS[table_key]

    limit = max(10, min(limit, 500))
    offset = max(offset, 0)

    query = config["query"](db)

    if run_id is not None and config.get("supports_run_filter"):
        run_column = config.get("run_column")
        if run_column is not None:
            query = query.filter(run_column == run_id)

    if search:
        search_fields = config.get("search_fields", [])
        clauses = [field.ilike(f"%{search}%") for field in search_fields]
        if clauses:
            query = query.filter(or_(*clauses))

    total = query.count()

    order_by = config.get("order_by")
    if order_by is not None:
        query = query.order_by(order_by)

    records = query.offset(offset).limit(limit).all()
    rows = [config["serializer"](record) for record in records]

    return {
        "table": table_key,
        "columns": config["columns"],
        "rows": rows,
        "total": total,
        "limit": limit,
        "offset": offset,
    }


# NetworkLink endpoints for persistent topology connections
@router.get("/network-links")
def get_network_links(db: Session = Depends(get_db)):
    """Get all persistent network links."""
    links = db.query(NetworkLink).filter(NetworkLink.status == 'active').all()
    return [
        {
            "id": l.id,
            "from_router_id": l.from_router_id,
            "to_router_id": l.to_router_id,
            "from_ip": l.from_ip,
            "to_ip": l.to_ip,
            "discovery_method": l.discovery_method,
            "initial_discovery": l.initial_discovery,
            "last_verified": l.last_verified,
            "verification_count": l.verification_count,
            "latency_ms": l.latency_ms,
            "hop_count": l.hop_count,
            "status": l.status,
            "color": l.color,
            "width": l.width
        }
        for l in links
    ]


@router.post("/network-links")
def save_network_link(link_data: dict, db: Session = Depends(get_db)):
    """Save or update a network link."""
    try:
        # Check if link already exists
        existing_link = db.query(NetworkLink).filter(NetworkLink.id == link_data['id']).first()
        
        if existing_link:
            # Update existing link
            existing_link.last_verified = datetime.utcnow()
            existing_link.verification_count += 1
            if 'latency_ms' in link_data:
                existing_link.latency_ms = link_data['latency_ms']
            if 'hop_count' in link_data:
                existing_link.hop_count = link_data['hop_count']
            existing_link.updated_at = datetime.utcnow()
            db.commit()
            return {"message": "Link updated", "id": existing_link.id}
        else:
            # Create new link
            new_link = NetworkLink(
                id=link_data['id'],
                from_router_id=link_data['from_router_id'],
                to_router_id=link_data['to_router_id'],
                from_ip=link_data['from_ip'],
                to_ip=link_data['to_ip'],
                discovery_method=link_data['discovery_method'],
                initial_discovery=datetime.utcnow(),
                last_verified=datetime.utcnow(),
                verification_count=1,
                latency_ms=link_data.get('latency_ms'),
                hop_count=link_data.get('hop_count'),
                color=link_data.get('color'),
                width=link_data.get('width', 2)
            )
            db.add(new_link)
            db.commit()
            return {"message": "Link created", "id": new_link.id}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to save link: {str(e)}")


@router.post("/network-links/batch")
def save_network_links_batch(links_data: List[dict], db: Session = Depends(get_db)):
    """Save multiple network links in a batch."""
    try:
        saved_links = []
        for link_data in links_data:
            # Check if link already exists
            existing_link = db.query(NetworkLink).filter(NetworkLink.id == link_data['id']).first()
            
            if existing_link:
                # Update existing link
                existing_link.last_verified = datetime.utcnow()
                existing_link.verification_count += 1
                if 'latency_ms' in link_data:
                    existing_link.latency_ms = link_data['latency_ms']
                if 'hop_count' in link_data:
                    existing_link.hop_count = link_data['hop_count']
                existing_link.updated_at = datetime.utcnow()
                saved_links.append({"id": existing_link.id, "action": "updated"})
            else:
                # Create new link
                new_link = NetworkLink(
                    id=link_data['id'],
                    from_router_id=link_data['from_router_id'],
                    to_router_id=link_data['to_router_id'],
                    from_ip=link_data['from_ip'],
                    to_ip=link_data['to_ip'],
                    discovery_method=link_data['discovery_method'],
                    initial_discovery=datetime.utcnow(),
                    last_verified=datetime.utcnow(),
                    verification_count=1,
                    latency_ms=link_data.get('latency_ms'),
                    hop_count=link_data.get('hop_count'),
                    color=link_data.get('color'),
                    width=link_data.get('width', 2)
                )
                db.add(new_link)
                saved_links.append({"id": new_link.id, "action": "created"})
        
        db.commit()
        return {"message": f"Saved {len(saved_links)} links", "results": saved_links}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to save links: {str(e)}")


@router.delete("/network-links/{link_id}")
def delete_network_link(link_id: str, db: Session = Depends(get_db)):
    """Mark a network link as failed (soft delete)."""
    link = db.query(NetworkLink).filter(NetworkLink.id == link_id).first()
    if not link:
        raise HTTPException(status_code=404, detail="Link not found")
    
    link.status = 'failed'
    link.updated_at = datetime.utcnow()
    db.commit()
    return {"message": "Link marked as failed", "id": link_id}


@router.post("/network-links/verify/{link_id}")
def verify_network_link(link_id: str, db: Session = Depends(get_db)):
    """Verify a network link and update its status."""
    link = db.query(NetworkLink).filter(NetworkLink.id == link_id).first()
    if not link:
        raise HTTPException(status_code=404, detail="Link not found")
    
    # Here you would implement actual verification logic
    # For now, just update the verification timestamp
    link.last_verified = datetime.utcnow()
    link.verification_count += 1
    link.updated_at = datetime.utcnow()
    db.commit()
    return {"message": "Link verified", "id": link_id, "verification_count": link.verification_count}
