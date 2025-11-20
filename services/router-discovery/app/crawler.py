import logging
from typing import Dict, Set, Tuple, Optional
from ipaddress import IPv4Address, IPv4Network
from datetime import datetime, timezone
from collections import deque

from sqlalchemy.orm import Session
from sqlalchemy import and_

from snmp_adapter import SnmpAdapter, SnmpError
from router_classifier import RouterClassifier
from models import DiscoveryRun, Router, RouterNetwork, RouterRoute, TopologyEdge

logger = logging.getLogger(__name__)


class RouterDiscoveryCrawler:
    """Single-threaded BFS crawler for router topology discovery."""
    
    def __init__(self, db_session_factory, snmp_adapter: SnmpAdapter, classifier: RouterClassifier, logger_instance=None):
        self.db_session_factory = db_session_factory
        self.snmp_adapter = snmp_adapter
        self.classifier = classifier
        self.logger = logger_instance or logger
    
    def start_run(self, root_ip: str, snmp_community: str, snmp_version: str) -> int:
        """
        Start a discovery run from root_ip using BFS.
        Returns the run_id.
        """
        db = self.db_session_factory()
        try:
            # Check if a run is already RUNNING
            running_run = db.query(DiscoveryRun).filter(
                DiscoveryRun.status == 'RUNNING'
            ).first()
            if running_run:
                raise RuntimeError(f"Discovery run {running_run.id} is already RUNNING")
            
            # Create new run record
            run = DiscoveryRun(
                status='RUNNING',
                root_ip=root_ip,
                snmp_community=snmp_community,
                snmp_version=snmp_version,
                started_at=datetime.now(timezone.utc)
            )
            db.add(run)
            db.commit()
            run_id = run.id
            self.logger.info(f"Started discovery run {run_id} from {root_ip}")
            
            # Execute BFS
            self._execute_bfs(db, run_id, root_ip, snmp_community, snmp_version)
            
            # Mark run as COMPLETED
            run = db.query(DiscoveryRun).filter(DiscoveryRun.id == run_id).first()
            run.status = 'COMPLETED'
            run.finished_at = datetime.now(timezone.utc)
            db.commit()
            self.logger.info(f"Completed discovery run {run_id}")
            
            return run_id
        
        except Exception as e:
            # Mark run as FAILED
            try:
                run = db.query(DiscoveryRun).filter(DiscoveryRun.status == 'RUNNING').first()
                if run:
                    run.status = 'FAILED'
                    run.error_message = str(e)
                    run.finished_at = datetime.now(timezone.utc)
                    db.commit()
                    self.logger.error(f"Discovery run {run.id} failed: {e}")
            except Exception as db_err:
                self.logger.error(f"Failed to update run status: {db_err}")
            
            raise
        
        finally:
            db.close()
    
    def _execute_bfs(self, db: Session, run_id: int, root_ip: str, snmp_community: str, snmp_version: str):
        """Execute BFS crawl starting from root_ip."""
        queue = deque([root_ip])
        visited: Set[str] = set()
        ip_to_router_id: Dict[str, int] = {}
        
        while queue:
            current_ip = queue.popleft()
            
            if current_ip in visited:
                continue
            
            visited.add(current_ip)
            self.logger.info(f"Processing router: {current_ip}")
            
            # Query SNMP
            try:
                system_info = self.snmp_adapter.get_system_info(current_ip, snmp_community, snmp_version)
                ip_forwarding = self.snmp_adapter.get_ip_forwarding(current_ip, snmp_community, snmp_version)
                interfaces = self.snmp_adapter.get_interfaces_and_addresses(current_ip, snmp_community, snmp_version)
                routes = self.snmp_adapter.get_routing_entries(current_ip, snmp_community, snmp_version)
                
                self.logger.debug(f"  System: {system_info.hostname}, IP forwarding: {ip_forwarding}")
                self.logger.debug(f"  Interfaces: {len(interfaces)}, Routes: {len(routes)}")
            
            except SnmpError as e:
                self.logger.warning(f"SNMP error on {current_ip}: {e}")
                # Record as non-router
                router = Router(
                    run_id=run_id,
                    primary_ip=current_ip,
                    hostname=None,
                    sys_descr=None,
                    sys_object_id=None,
                    vendor=None,
                    model=None,
                    is_router=False,
                    router_score=0,
                    classification_reason=f"snmp_error: {str(e)}"
                )
                db.add(router)
                db.commit()
                continue
            
            # Classify device
            classification = self.classifier.classify_router(system_info, ip_forwarding, interfaces, routes)
            
            # Store router
            router = Router(
                run_id=run_id,
                primary_ip=current_ip,
                hostname=system_info.hostname,
                sys_descr=system_info.sys_descr,
                sys_object_id=system_info.sys_object_id,
                vendor=self._extract_vendor(system_info),
                model=self._extract_model(system_info),
                is_router=classification.is_router,
                router_score=classification.score,
                classification_reason=classification.reason
            )
            db.add(router)
            db.flush()  # Get the router ID
            router_id = router.id
            ip_to_router_id[current_ip] = router_id
            
            self.logger.info(f"  Classified as {'router' if classification.is_router else 'non-router'} (score: {classification.score})")
            
            # Store interfaces as networks
            for iface in interfaces:
                try:
                    ip = IPv4Address(iface.ip)
                    netmask = IPv4Address(iface.netmask)
                    network = IPv4Network((ip, netmask), strict=False)
                    
                    net = RouterNetwork(
                        run_id=run_id,
                        router_id=router_id,
                        network=str(network),
                        is_local=True
                    )
                    db.add(net)
                except Exception as e:
                    self.logger.debug(f"Failed to store interface {iface.ip}/{iface.netmask}: {e}")
            
            # Store routes
            for route in routes:
                try:
                    dest_ip = IPv4Address(route.destination_ip)
                    netmask = IPv4Address(route.netmask)
                    dest_network = IPv4Network((dest_ip, netmask), strict=False)
                    
                    # Parse next hop
                    next_hop_inet = None
                    if route.next_hop:
                        try:
                            IPv4Address(route.next_hop)
                            next_hop_inet = route.next_hop
                        except Exception:
                            pass
                    
                    rt = RouterRoute(
                        run_id=run_id,
                        router_id=router_id,
                        destination=str(dest_network),
                        next_hop=next_hop_inet,
                        protocol=route.protocol,
                        admin_distance=None,  # Phase 0: not extracted yet
                        metric=None
                    )
                    db.add(rt)
                except Exception as e:
                    self.logger.debug(f"Failed to store route {route.destination_ip}/{route.netmask}: {e}")
            
            db.commit()
            
            # Collect next-hop IPs to queue
            neighbor_candidates = set()
            for route in routes:
                if route.next_hop:
                    try:
                        IPv4Address(route.next_hop)
                        neighbor_candidates.add(route.next_hop)
                    except Exception:
                        pass
            
            # Add neighbors to queue
            for neighbor_ip in neighbor_candidates:
                if neighbor_ip not in visited:
                    queue.append(neighbor_ip)
                    self.logger.debug(f"  Enqueued neighbor: {neighbor_ip}")
            
            # Create topology edges from shared subnets
            if classification.is_router:
                self._create_topology_edges(db, run_id, router_id, current_ip)
        
        db.commit()
    
    def _create_topology_edges(self, db: Session, run_id: int, current_router_id: int, current_ip: str):
        """Create topology edges based on shared subnets."""
        try:
            # Get current router's networks
            current_networks = db.query(RouterNetwork).filter(
                and_(RouterNetwork.run_id == run_id, RouterNetwork.router_id == current_router_id)
            ).all()
            
            for net_entry in current_networks:
                current_network = IPv4Network(net_entry.network)
                
                # Find other routers with overlapping networks
                other_networks = db.query(RouterNetwork).filter(
                    and_(
                        RouterNetwork.run_id == run_id,
                        RouterNetwork.router_id != current_router_id,
                        RouterNetwork.network.op('<<')(str(current_network))  # Contained in
                    )
                ).all()
                
                for other_net in other_networks:
                    other_router = db.query(Router).filter(Router.id == other_net.router_id).first()
                    if other_router and other_router.is_router:
                        # Create undirected edge (normalize: smaller id first)
                        from_id = min(current_router_id, other_net.router_id)
                        to_id = max(current_router_id, other_net.router_id)
                        
                        # Check if edge already exists
                        existing = db.query(TopologyEdge).filter(
                            and_(
                                TopologyEdge.run_id == run_id,
                                TopologyEdge.from_router_id == from_id,
                                TopologyEdge.to_router_id == to_id
                            )
                        ).first()
                        
                        if not existing:
                            edge = TopologyEdge(
                                run_id=run_id,
                                from_router_id=from_id,
                                to_router_id=to_id,
                                reason='shared_subnet'
                            )
                            db.add(edge)
                            self.logger.debug(f"  Created edge: {current_ip} -> router_{to_id}")
        
        except Exception as e:
            self.logger.debug(f"Failed to create topology edges for {current_ip}: {e}")
    
    def _extract_vendor(self, system_info) -> Optional[str]:
        """Extract vendor name from system description (simple heuristic)."""
        if not system_info.sys_descr:
            return None
        
        text = system_info.sys_descr.lower()
        vendors = ['cisco', 'juniper', 'arista', 'cradlepoint', 'ubiquiti', 'mikrotik', 'fortigate']
        for vendor in vendors:
            if vendor in text:
                return vendor.capitalize()
        
        return None
    
    def _extract_model(self, system_info) -> Optional[str]:
        """Extract model from system description (simple heuristic)."""
        if not system_info.sys_descr:
            return None
        
        # Extract common patterns like "ISR 4431", "ASR 9010", etc.
        parts = system_info.sys_descr.split()
        for i, part in enumerate(parts):
            if part in ['ISR', 'ASR', 'IOS', 'JUNOS']:
                if i + 1 < len(parts):
                    return f"{part} {parts[i + 1]}"
                return part
        
        return None
