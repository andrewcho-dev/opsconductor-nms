import logging
from typing import Dict, Set, Tuple, Optional, List
from ipaddress import IPv4Address, IPv4Network
from datetime import datetime, timezone
from collections import deque

from sqlalchemy.orm import Session
from sqlalchemy import and_

from .snmp_adapter import SnmpAdapter, SnmpError, RouteEntry
from .cli_routing import fetch_vrf_routes_via_ssh
from .router_classifier import RouterClassifier
from .models import DiscoveryRun, Router, RouterNetwork, RouterRoute, TopologyEdge

logger = logging.getLogger(__name__)


class RouterDiscoveryCrawler:
    """Single-threaded BFS crawler for router topology discovery."""
    
    def __init__(self, db_session_factory, snmp_adapter: SnmpAdapter, classifier: RouterClassifier, logger_instance=None):
        self.db_session_factory = db_session_factory
        self.snmp_adapter = snmp_adapter
        self.classifier = classifier
        self.logger = logger_instance or logger
        self.default_cli_credentials: List[Dict[str, Optional[str]]] = []
    
    def start_run(self, root_ip: str, snmp_community: str, snmp_version: str, cli_default_credentials: Optional[List[Dict[str, Optional[str]]]] = None) -> int:
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
            cli_defaults = cli_default_credentials or []
            self.default_cli_credentials = cli_defaults

            run = DiscoveryRun(
                status='RUNNING',
                root_ip=root_ip,
                snmp_community=snmp_community,
                snmp_version=snmp_version,
                started_at=datetime.now(timezone.utc),
                cli_default_credentials=cli_defaults,
            )
            db.add(run)
            db.commit()
            run_id = run.id
            self.logger.info(f"Started discovery run {run_id} from {root_ip}")
            
            # Execute BFS
            self._execute_bfs(
                db,
                run_id,
                queue_seed=[root_ip],
                snmp_community=snmp_community,
                snmp_version=snmp_version,
                cli_credentials=self.default_cli_credentials,
            )
            
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
    
    def resume_run(self, run_id: int, seed_ips: Optional[List[str]] = None) -> int:
        """Resume a discovery run with additional seed IPs (e.g., from CLI discovery)."""
        if not seed_ips:
            return run_id
        db = self.db_session_factory()
        try:
            run = db.query(DiscoveryRun).filter(DiscoveryRun.id == run_id).first()
            if not run:
                raise RuntimeError(f"Discovery run {run_id} not found")
            run.status = 'RUNNING'
            run.finished_at = None
            db.commit()

            existing_ips = {
                str(row[0])
                for row in db.query(Router.primary_ip).filter(Router.run_id == run_id).all()
                if row[0] is not None
            }

            cli_credentials = run.cli_default_credentials or []

            self._execute_bfs(
                db,
                run_id,
                queue_seed=seed_ips,
                snmp_community=run.snmp_community,
                snmp_version=run.snmp_version,
                cli_credentials=cli_credentials,
                visited_seed=existing_ips,
            )

            run = db.query(DiscoveryRun).filter(DiscoveryRun.id == run_id).first()
            run.status = 'COMPLETED'
            run.finished_at = datetime.now(timezone.utc)
            db.commit()
            return run_id

        except Exception as e:
            db.rollback()
            self.logger.error(f"Failed to resume discovery run {run_id}: {e}")
            raise
        finally:
            db.close()

    def _get_routes_via_snmp(self, target_ip: str, community: str, version: str) -> List[RouteEntry]:
        try:
            return self.snmp_adapter.get_routing_entries(target_ip, community, version)
        except Exception as exc:
            self.logger.warning(f"Failed SNMP route fetch on {target_ip}: {exc}")
            return []

    def _get_routes_via_cli(self, target_ip: str, credentials: List[Dict[str, Optional[str]]]) -> List[RouteEntry]:
        for cred in credentials:
            username = cred.get("username")
            password = cred.get("password")
            if not username or not password:
                continue
            try:
                cli_routes = fetch_vrf_routes_via_ssh(target_ip, username=username, password=password)
            except Exception as exc:
                self.logger.debug(
                    "CLI route fetch failed",
                    extra={"target": target_ip, "username": username, "error": str(exc)},
                )
                continue

            if cli_routes:
                return self._convert_cli_routes(cli_routes)
        return []

    def _convert_cli_routes(self, cli_routes) -> List[RouteEntry]:
        converted: List[RouteEntry] = []
        for entry in cli_routes:
            try:
                network = IPv4Network(f"{entry.destination}/{entry.prefix_length}", strict=False)
                converted.append(
                    RouteEntry(
                        destination_ip=str(network.network_address),
                        netmask=str(network.netmask),
                        next_hop=entry.next_hop,
                        protocol=entry.protocol,
                    )
                )
            except Exception as exc:
                self.logger.debug(
                    "Failed to convert CLI route",
                    extra={"route": entry.destination, "prefix": entry.prefix_length, "error": str(exc)},
                )
        return converted
    
    def _execute_bfs(
        self,
        db: Session,
        run_id: int,
        queue_seed: List[str],
        snmp_community: str,
        snmp_version: str,
        cli_credentials: Optional[List[Dict[str, Optional[str]]]] = None,
        visited_seed: Optional[Set[str]] = None,
    ):
        """Execute BFS crawl starting from provided queue seed."""
        queue = deque(queue_seed)
        visited: Set[str] = set(visited_seed or [])
        ip_to_router_id: Dict[str, int] = {}
        
        while queue:
            current_ip = queue.popleft()
            
            if current_ip in visited:
                continue
            
            visited.add(current_ip)
            self.logger.info(f"Processing router: {current_ip}")
            
            # Query SNMP for classification info
            try:
                system_info = self.snmp_adapter.get_system_info(current_ip, snmp_community, snmp_version)
                ip_forwarding = self.snmp_adapter.get_ip_forwarding(current_ip, snmp_community, snmp_version)
                interfaces = self.snmp_adapter.get_interfaces_and_addresses(current_ip, snmp_community, snmp_version)
            except SnmpError as e:
                self.logger.warning(f"SNMP error on {current_ip}: {e}")
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

            routes = self._get_routes_via_snmp(current_ip, snmp_community, snmp_version)
            if not routes and cli_credentials:
                cli_routes = self._get_routes_via_cli(current_ip, cli_credentials)
                if cli_routes:
                    routes = cli_routes
                    self.logger.info(f"  Retrieved {len(routes)} routes via CLI fallback for {current_ip}")

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
                    network = IPv4Network((ip, str(netmask)), strict=False)
                    
                    net = RouterNetwork(
                        run_id=run_id,
                        router_id=router_id,
                        network=str(network),
                        is_local=True
                    )
                    db.add(net)
                except Exception as e:
                    self.logger.error(f"Failed to store interface {iface.ip}/{iface.netmask}: {e}", exc_info=True)
            
            # Store routes
            for route in routes:
                try:
                    dest_ip = IPv4Address(route.destination_ip)
                    netmask = IPv4Address(route.netmask)
                    dest_network = IPv4Network((dest_ip, str(netmask)), strict=False)
                    
                    cidr_str = f"{dest_network.network_address}/{dest_network.prefixlen}"
                    
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
                        destination=cidr_str,
                        next_hop=next_hop_inet,
                        protocol=route.protocol,
                        admin_distance=None,
                        metric=None
                    )
                    db.add(rt)
                except Exception as e:
                    self.logger.error(f"Failed to store route {route.destination_ip}/{route.netmask}: {e}", exc_info=True)
            
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
            self.logger.error(f"Failed to create topology edges for {current_ip}: {e}", exc_info=True)
    
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
