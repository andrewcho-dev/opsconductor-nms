import logging
import paramiko
from typing import List, Dict, Optional, Set, Tuple
from ipaddress import IPv4Address, IPv4Network, ip_network
from sqlalchemy.orm import Session
from datetime import datetime

from .models import DiscoveryRun, Router, Route, Network, TopologyLink
from .snmp_simple import SimpleSnmpClient
from .types import SystemInfo, RouteEntry
from .vendors import vendor_factory

logger = logging.getLogger(__name__)


class NetworkDiscovery:
    """Simplified network discovery service with SSH/CLI and SNMP support."""
    
    def __init__(self, db_session: Session):
        self.db = db_session
        self.snmp_client = SimpleSnmpClient(timeout=5, retries=2)
        self.vendor_factory = vendor_factory
    
    def start_discovery(self, root_ip: str, snmp_community: str = 'public', 
                       ssh_credentials: Optional[Dict[str, str]] = None) -> int:
        """Start network discovery from root IP."""
        logger.info(f"Starting discovery from {root_ip}")
        
        # Create discovery run
        run = DiscoveryRun(
            status='RUNNING',
            root_ip=root_ip,
            started_at=datetime.utcnow()
        )
        self.db.add(run)
        self.db.commit()
        
        try:
            # Perform BFS discovery
            discovered_routers = self._discover_network_bfs(
                root_ip, snmp_community, ssh_credentials, run.id
            )
            
            # Build topology links
            self._build_topology_links(run.id)
            
            # Update run with results
            run.status = 'COMPLETED'
            run.finished_at = datetime.utcnow()
            run.routers_found = len(discovered_routers)
            run.routes_found = self.db.query(Route).filter(Route.discovery_run_id == run.id).count()
            run.networks_found = self.db.query(Network).filter(Network.discovery_run_id == run.id).count()
            
            self.db.commit()
            logger.info(f"Discovery completed: {run.routers_found} routers, {run.routes_found} routes, {run.networks_found} networks")
            
            return run.id
            
        except Exception as e:
            logger.error(f"Discovery failed: {e}")
            run.status = 'FAILED'
            run.error_message = str(e)
            run.finished_at = datetime.utcnow()
            self.db.commit()
            raise
    
    def _discover_network_bfs(self, root_ip: str, snmp_community: str, 
                             ssh_credentials: Optional[Dict[str, str]], run_id: int) -> List[str]:
        """Discover network using optimized BFS from root IP - SNMP-first approach."""
        queue = [root_ip]
        visited = set()
        discovered_routers = []
        
        while queue:
            current_ip = queue.pop(0)
            if current_ip in visited:
                continue
                
            visited.add(current_ip)
            logger.info(f"Processing {current_ip}")
            
            # Try to discover routes from this device
            routes = []
            system_info = None
            interfaces = []
            discovery_method = 'snmp'
            
            # OPTIMIZED: Try SNMP first with fast timeout
            try:
                logger.info(f"  Trying SNMP discovery for {current_ip}")
                system_info = self.snmp_client.get_system_info(current_ip, snmp_community)
                routes = self.snmp_client.get_routes(current_ip, snmp_community)
                interfaces = self.snmp_client.get_interfaces(current_ip, snmp_community)
                logger.info(f"  SNMP discovery SUCCESS: {len(routes)} routes, {len(interfaces)} interfaces")
                
                # For edge routers, SNMP is usually sufficient and much faster
                # Only try SSH if SNMP found no routes and we have credentials
                if not routes and ssh_credentials:
                    logger.info(f"  SNMP found no routes, trying SSH as fallback")
                    discovery_method = 'cli'
                    ssh_routes = self._get_routes_ssh_optimized(current_ip, ssh_credentials, system_info)
                    if ssh_routes:
                        routes = ssh_routes
                        logger.info(f"  SSH fallback found {len(routes)} routes")
                
            except Exception as snmp_e:
                logger.info(f"  SNMP failed: {snmp_e}")
                
                # Only try SSH if SNMP failed and we have credentials
                if ssh_credentials:
                    logger.info(f"  SNMP failed, trying SSH discovery")
                    discovery_method = 'cli'
                    try:
                        # Attempt to gather minimal system info over SSH to help vendor detection
                        system_info_cli = self._get_system_info_ssh(current_ip, ssh_credentials)
                        system_info = system_info or system_info_cli
                        ssh_routes = self._get_routes_ssh_optimized(current_ip, ssh_credentials, system_info)
                        if ssh_routes:
                            routes = ssh_routes
                            logger.info(f"  SSH discovery found {len(routes)} routes")
                    except Exception as ssh_e:
                        logger.warning(f"  SSH also failed: {ssh_e}")
                        continue  # Skip this device and move to next
                else:
                    logger.info(f"  No SSH credentials, skipping {current_ip}")
                    continue
            
            # If we found routes or interfaces, save the device
            if routes or interfaces or system_info:
                router = self._save_router(current_ip, system_info, routes, interfaces, discovery_method, run_id)
                if router:
                    discovered_routers.append(current_ip)
                    
                    # Extract next hops and add to queue for BFS expansion
                    next_hops = set()
                    for route in routes:
                        if route.next_hop and route.next_hop != '0.0.0.0':
                            next_hops.add(route.next_hop)
                    
                    # Also extract network IPs for edge discovery
                    for interface in interfaces:
                        if hasattr(interface, 'ip_address') and interface.ip_address:
                            next_hops.add(interface.ip_address)
                    
                    for next_hop in next_hops:
                        if next_hop not in visited:
                            queue.append(next_hop)
                            logger.info(f"  Added next hop to queue: {next_hop}")
            else:
                logger.info(f"  No discovery data for {current_ip}, skipping")
        
        return discovered_routers
    
    def _get_routes_ssh_optimized(self, ip: str, credentials: Dict[str, str], system_info: Optional[SystemInfo] = None) -> List[Route]:
        """Optimized SSH route discovery with faster timeouts and edge router focus."""
        routes = []
        
        commands = self._get_cli_command_list(system_info)
        
        for command in commands:
            try:
                logger.info(f"  Executing optimized SSH command: {command}")
                
                # Use faster SSH connection with shorter timeout for edge routers
                client = paramiko.SSHClient()
                client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                
                # For older Cisco ASA, we need to enable the old key exchange algorithms
                paramiko.Transport._preferred_kex = (
                    'diffie-hellman-group14-sha1',
                    'diffie-hellman-group-exchange-sha1',
                    'diffie-hellman-group1-sha1'
                )
                
                client.connect(
                    ip,
                    username=credentials['username'],
                    password=credentials['password'],
                    timeout=10,  # Faster timeout: 10 seconds instead of 15
                    banner_timeout=10,
                    auth_timeout=10,
                    look_for_keys=False,
                    allow_agent=False
                )
                
                stdin, stdout, stderr = client.exec_command(command, timeout=30)  # 30 sec timeout instead of 60
                
                output = stdout.read().decode('utf-8', errors='ignore')
                error_output = stderr.read().decode('utf-8', errors='ignore')
                
                if error_output and not error_output.strip().startswith('%'):
                    logger.warning(f"  SSH command stderr: {error_output}")
                
                logger.info(f"  SSH command output ({len(output)} chars): {output[:1000]}...")
                
                parsed_routes: List[RouteEntry] = []
                if system_info and self.vendor_factory:
                    parsed_routes = self.vendor_factory.auto_parse_routes(output, command, system_info)

                if not parsed_routes:
                    parsed_routes = self._parse_routes_from_output(output, command)

                if parsed_routes:
                    routes.extend(parsed_routes)
                
                if routes:  # Found routes, don't try more commands
                    logger.info(f"  Found {len(routes)} routes with optimized SSH, stopping")
                    break
                    
                client.close()
                
            except Exception as cmd_e:
                logger.warning(f"  Optimized SSH command '{command}' failed: {cmd_e}")
                try:
                    client.close()
                except:
                    pass
                continue
        
        return routes

    def _get_cli_command_list(self, system_info: Optional[SystemInfo]) -> List[str]:
        """Return ordered list of CLI commands with vendor-specific preference."""
        default_commands = self._default_cli_commands()
        if system_info and self.vendor_factory:
            vendor_commands = self.vendor_factory.auto_detect_commands(system_info)
            if vendor_commands:
                # Append defaults that weren't included to ensure broad coverage
                fallback = [cmd for cmd in default_commands if cmd not in vendor_commands]
                return vendor_commands + fallback
        return default_commands

    def _default_cli_commands(self) -> List[str]:
        """Default set of CLI commands for generic devices."""
        return [
            "show ip route",           # Standard Cisco
            "show route",              # Generic
            "show ip route static",    # Static routes only
            "show ip route connected", # Connected routes only  
            "get route info",          # Some edge routers
            "ip route show",           # Linux-style
            # L3 Switch specific commands
            "show routing-table",      # Some L3 switches
            "show ip route summary",   # Route summary
            "display ip routing-table", # Huawei/H3C style
            # ASA-specific commands for NAT/VPN tunnels
            "show crypto map",         # VPN tunnel information
            "show nat",                # NAT translations
            "show run | include tunnel", # Tunnel configurations
            "show run | include nat",   # NAT configurations
            "show vpn-sessiondb",      # Active VPN sessions
            "show crypto ipsec sa",    # IPSec security associations
            "show access-list",        # ACLs that might reveal networks
        ]

    def _parse_routes_from_output(self, output: str, command: str) -> List[RouteEntry]:
        """Fallback parser that reuses legacy Cisco/ASA parsing logic."""
        routes: List[RouteEntry] = []

        if any(keyword in command for keyword in ['crypto', 'nat', 'tunnel', 'vpn', 'access-list']):
            crypto_routes = self._parse_asa_crypto_nat_info(output)
            if crypto_routes:
                routes.extend(crypto_routes)

        if routes:
            return routes

        for line in output.splitlines():
            route = self._parse_cisco_route_line(line)
            if route:
                routes.append(route)
                continue

            config_route = self._parse_config_route_line(line)
            if config_route:
                routes.append(config_route)
                continue

            asa_route = self._parse_asa_route_line(line)
            if asa_route:
                routes.append(asa_route)

        return routes
    
    def _save_router(self, ip: str, system_info, routes: List[Route], interfaces, discovery_method: str, run_id: int):
        """Save router information to database."""
        try:
            # Classify device
            is_router = self._classify_router(system_info, routes, interfaces)
            if not is_router:
                logger.info(f"  Not classified as router, skipping")
                return None
            
            # Store router - check if already exists
            existing_router = self.db.query(Router).filter(Router.ip_address == ip).first()
            if existing_router:
                # Update existing router with new discovery info
                existing_router.discovery_run_id = run_id
                existing_router.hostname = system_info.hostname if system_info else existing_router.hostname
                existing_router.vendor = self._extract_vendor(system_info) or existing_router.vendor
                existing_router.model = self._extract_model(system_info) or existing_router.model
                existing_router.is_router = True
                existing_router.router_score = 1.0
                existing_router.classification_reason = "has_routing_table" if routes else "router_classification"
                existing_router.discovered_via = discovery_method
                existing_router.created_at = datetime.utcnow()
                logger.info(f"  Updated existing router {ip}")
                router = existing_router
            else:
                # Create new router
                router = Router(
                    discovery_run_id=run_id,
                    ip_address=ip,
                    hostname=system_info.hostname if system_info else None,
                    vendor=self._extract_vendor(system_info),
                    model=self._extract_model(system_info),
                    is_router=True,
                    router_score=1.0
                )
                router.classification_reason = "has_routing_table" if routes else "router_classification"
                router.discovered_via = discovery_method
                self.db.add(router)
                logger.info(f"  Created new router {ip}")
            
            self.db.commit()
            
            # Save routes
            for route in routes:
                # Convert RouteEntry to CIDR format for database
                if hasattr(route, 'destination') and hasattr(route, 'netmask'):
                    # Convert IP/Netmask to proper CIDR notation
                    dest_ip = route.destination
                    netmask = route.netmask
                    
                    # Calculate network address and CIDR prefix
                    destination_cidr = self._ip_and_mask_to_cidr(dest_ip, netmask)
                    
                    existing_route = self.db.query(Route).filter(Route.router_id == router.id, Route.destination == destination_cidr).first()
                    if not existing_route:
                        db_route = Route(
                            router_id=router.id,
                            discovery_run_id=run_id,
                            destination=destination_cidr,
                            next_hop=route.next_hop,
                            protocol=route.protocol if hasattr(route, 'protocol') else 'connected',
                            discovered_via=discovery_method
                        )
                        self.db.add(db_route)
                else:
                    # Handle legacy route format
                    destination_cidr = route.destination if '/' in route.destination else f"{route.destination}/24"
                    existing_route = self.db.query(Route).filter(Route.router_id == router.id, Route.destination == destination_cidr).first()
                    if not existing_route:
                        db_route = Route(
                            router_id=router.id,
                            discovery_run_id=run_id,
                            destination=destination_cidr,
                            next_hop=getattr(route, 'next_hop', None),
                            protocol=getattr(route, 'protocol', 'connected'),
                            discovered_via=discovery_method
                        )
                        self.db.add(db_route)
            
            # Save networks/interfaces
            for interface in interfaces:
                network_str = f"{interface.network}/{interface.netmask}" if hasattr(interface, 'network') else f"{ip}/24"
                existing_network = self.db.query(Network).filter(Network.router_id == router.id, Network.network == network_str).first()
                if not existing_network:
                    network = Network(
                        discovery_run_id=run_id,  # Add missing discovery_run_id
                        router_id=router.id,
                        network=network_str,
                        interface=getattr(interface, 'name', 'unknown'),
                        is_connected=True
                    )
                    self.db.add(network)
            
            self.db.commit()
            return router
            
        except Exception as e:
            logger.error(f"  Failed to save router {ip}: {e}")
            self.db.rollback()
            return None
    
    def _extract_vendor(self, system_info) -> str:
        """Extract vendor from system info."""
        if not system_info:
            return None
        
        description = getattr(system_info, 'sys_descr', '').lower()
        if 'cisco' in description:
            return 'Cisco'
        elif 'juniper' in description:
            return 'Juniper'
        elif 'cradlepoint' in description or 'rgos' in description:
            return 'Cradlepoint'
        elif 'mikrotik' in description or 'routeros' in description:
            return 'Mikrotik'
        else:
            return None
    
    def _extract_model(self, system_info) -> str:
        """Extract model from system info."""
        if not system_info:
            return None
        
        description = getattr(system_info, 'sys_descr', '')
        # Simple model extraction - can be enhanced
        if 'asa' in description.lower():
            return 'ASA'
        elif 'router' in description.lower():
            return 'Router'
        else:
            return None
    
    def _get_system_info_snmp(self, ip: str, community: str) -> SystemInfo:
        """Get system info via SNMP."""
        try:
            # Get system description
            error_indication, error_status, error_index, var_binds = next(
                getCmd(SnmpEngine(),
                       CommunityData(community),
                       UdpTransportTarget((ip, 161), timeout=self.snmp_timeout, retries=self.snmp_retries),
                       ContextData(),
                       ObjectType(ObjectIdentity('SNMPv2-MIB', 'sysDescr', 0)),
                       ObjectType(ObjectIdentity('SNMPv2-MIB', 'sysName', 0)),
                       ObjectType(ObjectIdentity('SNMPv2-MIB', 'sysObjectID', 0)))
            )
            
            if error_indication:
                raise Exception(f"SNMP error: {error_indication}")
            
            sys_descr = str(var_binds[0][1])
            hostname = str(var_binds[1][1]) if len(var_binds) > 1 else None
            sys_object_id = str(var_binds[2][1]) if len(var_binds) > 2 else None
            
            return SystemInfo(hostname=hostname, sys_descr=sys_descr, sys_object_id=sys_object_id)
            
        except Exception as e:
            raise Exception(f"SNMP system info failed: {e}")
    
    def _get_routes_snmp(self, ip: str, community: str) -> List[RouteEntry]:
        """Get routing table via SNMP."""
        routes = []
        
        try:
            # Walk the IP route table
            for (error_indication, error_status, error_index, var_binds) in nextCmd(
                SnmpEngine(),
                CommunityData(community),
                UdpTransportTarget((ip, 161), timeout=self.snmp_timeout, retries=self.snmp_retries),
                ContextData(),
                ObjectType(ObjectIdentity('IP-FORWARD-MIB', 'ipCidrRouteDest')),
                lexicographicMode=False):
                
                if error_indication:
                    break
                
                for var_bind in var_binds:
                    route_dest = str(var_bind[1])
                    if route_dest == '0.0.0.0':  # Skip default route for now
                        continue
                    
                    # Get corresponding route info
                    try:
                        error_indication, error_status, error_index, var_binds = next(
                            getCmd(SnmpEngine(),
                                   CommunityData(community),
                                   UdpTransportTarget((ip, 161)),
                                   ContextData(),
                                   ObjectType(ObjectIdentity('IP-FORWARD-MIB', 'ipCidrRouteMask', route_dest, '0.0.0.0', 0, 0)),
                                   ObjectType(ObjectIdentity('IP-FORWARD-MIB', 'ipCidrRouteNextHop', route_dest, '0.0.0.0', 0, 0)),
                                   ObjectType(ObjectIdentity('IP-FORWARD-MIB', 'ipCidrRouteProto', route_dest, '0.0.0.0', 0, 0)))
                        )
                        
                        if not error_indication and len(var_binds) >= 3:
                            netmask = str(var_binds[0][1])
                            next_hop = str(var_binds[1][1])
                            protocol = str(var_binds[2][1])
                            
                            routes.append(RouteEntry(
                                destination=route_dest,
                                netmask=netmask,
                                next_hop=next_hop if next_hop != '0.0.0.0' else None,
                                protocol=self._map_snmp_protocol(protocol)
                            ))
                    except:
                        continue
                        
        except Exception as e:
            logger.warning(f"SNMP route discovery failed: {e}")
        
        return routes
    
    def _get_interfaces_snmp(self, ip: str, community: str) -> List[Dict]:
        """Get interface information via SNMP."""
        interfaces = []
        
        try:
            # Get interface descriptions and IP addresses
            for (error_indication, error_status, error_index, var_binds) in nextCmd(
                SnmpEngine(),
                CommunityData(community),
                UdpTransportTarget((ip, 161)),
                ContextData(),
                ObjectType(ObjectIdentity('IP-MIB', 'ipAdEntAddr')),
                lexicographicMode=False):
                
                if error_indication:
                    break
                
                for var_bind in var_binds:
                    ip_addr = str(var_bind[1])
                    if not self._is_valid_ip(ip_addr):
                        continue
                    
                    try:
                        # Get netmask for this IP
                        error_indication, error_status, error_index, var_binds = next(
                            getCmd(SnmpEngine(),
                                   CommunityData(community),
                                   UdpTransportTarget((ip, 161)),
                                   ContextData(),
                                   ObjectType(ObjectIdentity('IP-MIB', 'ipAdEntNetMask', ip_addr)))
                        )
                        
                        if not error_indication and var_binds:
                            netmask = str(var_binds[0][1])
                            interfaces.append({
                                'ip': ip_addr,
                                'netmask': netmask,
                                'name': f'if_{len(interfaces)}'
                            })
                    except:
                        continue
                        
        except Exception as e:
            logger.warning(f"SNMP interface discovery failed: {e}")
        
        return interfaces
    
    def _get_routes_ssh(self, ip: str, credentials: Dict[str, str]) -> List[RouteEntry]:
        """Get routes via SSH/CLI fallback - using system SSH for ASA compatibility."""
        routes = []
        
        try:
            # Try system SSH first for ASA compatibility
            routes = self._get_routes_ssh_system(ip, credentials)
            if routes:
                return routes
        except Exception as e:
            logger.warning(f"  System SSH failed, trying Paramiko: {e}")
        
        # Fall back to Paramiko for other devices
        try:
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            client.connect(
                hostname=ip,
                username=credentials['username'],
                password=credentials['password'],
                timeout=10
            )
            
            # Try to get routes from different VRFs - reconnect for each command
            commands = [
                'show ip route', 
                'show route',  # ASA specific command
                'show ip route static',
                'show ip route connected',
                'show running-config',  # L3 switch friendly
                'show running-config | include ip route',
                'show running-config | route',
                'show run | include 10.121',
                'show run | include 10.120.0.2',
                'show ip route vrf MGMT', 
                'show ip route vrf EXTERNAL',
                'show ip protocols summary'
            ]
            
            for command in commands:
                try:
                    # Reconnect for each command since session drops
                    client = paramiko.SSHClient()
                    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                    client.connect(
                        hostname=ip,
                        username=credentials['username'],
                        password=credentials['password'],
                        timeout=15
                    )
                    
                    logger.info(f"  Executing SSH command: {command}")
                    stdin, stdout, stderr = client.exec_command(command, timeout=60)
                    
                    # Simple direct output reading - just like you do manually
                    output = stdout.read().decode('utf-8', errors='ignore')
                    error_output = stderr.read().decode('utf-8', errors='ignore')
                    
                    if error_output and not error_output.strip().startswith('%'):
                        logger.warning(f"  SSH command stderr: {error_output}")
                    
                    logger.info(f"  SSH command output ({len(output)} chars): {output[:2000]}")
                    
                    for line in output.splitlines():
                        route = self._parse_cisco_route_line(line)
                        if route:
                            logger.info(f"  Parsed route: {route.destination}/{route.netmask} via {route.next_hop}")
                            routes.append(route)
                        else:
                            # Try to parse static route from config
                            config_route = self._parse_config_route_line(line)
                            if config_route:
                                logger.info(f"  Parsed config route: {config_route.destination}/{config_route.netmask} via {config_route.next_hop}")
                                routes.append(config_route)
                            else:
                                # Try ASA-specific route parsing
                                asa_route = self._parse_asa_route_line(line)
                                if asa_route:
                                    logger.info(f"  Parsed ASA route: {asa_route.destination}/{asa_route.netmask} via {asa_route.next_hop}")
                                    routes.append(asa_route)
                    
                    if routes:  # If we found routes, don't try more commands
                        logger.info(f"  Found {len(routes)} routes, stopping")
                        break
                        
                    client.close()
                except Exception as cmd_e:
                    logger.warning(f"  SSH command '{command}' failed: {cmd_e}")
                    try:
                        client.close()
                    except:
                        pass
                    continue  # Try next command
                    
        except Exception as e:
            try:
                # Get system info
                system_info = self._get_system_info(ip, request.snmp_community)
                
                # Get interfaces/networks
                interfaces = self._get_interfaces(ip, request.snmp_community)
                
                # Get routes
                routes = self._get_routes(ip, request.snmp_community, ssh_credentials_list)
                
                # Store router
                router = self._store_router(db, ip, system_info, routes, interfaces)
                
                # Store networks and routes
                self._store_networks(db, router, interfaces)
                self._store_routes(db, router, routes)
                
                # Store topology connection
                if discovered_from:
                    self._store_topology_edge(db, discovered_from, ip)
                
                # BFS expansion - add connected networks to queue
                for route in routes:
                    if route.next_hop and route.next_hop not in visited:
                        queue.append((route.next_hop, ip))
                
                # Also add directly connected networks
                for interface in interfaces:
                    if interface.get('ip') and interface['ip'] not in visited:
                        queue.append((interface['ip'], ip))
                        
            except Exception as e:
                logger.error(f"Failed to discover {ip}: {e}")
                # Skip this device and continue with next one in queue
        
        # Mark as completed
        run.status = 'COMPLETED'
        run.finished_at = datetime.now(timezone.utc)
        db.commit()
        """Get interfaces via SSH/CLI."""
        interfaces = []
        
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        
        try:
            client.connect(
                hostname=ip,
                username=credentials['username'],
                password=credentials['password'],
                timeout=10
            )
            
            stdin, stdout, stderr = client.exec_command('show ip interface brief', timeout=10)
            output = stdout.read().decode('utf-8', errors='ignore')
            
            for line in output.splitlines():
                interface = self._parse_cisco_interface_line(line)
                if interface:
                    interfaces.append(interface)
                    
        except Exception as e:
            logger.warning(f"SSH interface discovery failed: {e}")
        finally:
            client.close()
        
        return interfaces
    
    def _get_system_info_ssh(self, ip: str, credentials: Dict[str, str]) -> SystemInfo:
        """Get system info via SSH/CLI."""
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        
        try:
            client.connect(
                hostname=ip,
                username=credentials['username'],
                password=credentials['password'],
                timeout=10
            )
            
            # Get hostname
            stdin, stdout, stderr = client.exec_command('show running-config | include hostname', timeout=10)
            hostname_output = stdout.read().decode('utf-8', errors='ignore').strip()
            hostname = hostname_output.replace('hostname ', '') if hostname_output else None
            
            # Get version info
            stdin, stdout, stderr = client.exec_command('show version', timeout=10)
            version_output = stdout.read().decode('utf-8', errors='ignore')
            
            return SystemInfo(hostname=hostname, sys_descr=version_output[:500])  # Truncate for storage
            
        except Exception as e:
            logger.warning(f"SSH system info discovery failed: {e}")
            # Even if system info fails, return a basic SystemInfo to indicate we connected via SSH
            return SystemInfo(hostname="SSH-Connected", sys_descr="Cisco IOS Device")
        finally:
            try:
                client.close()
            except:
                pass
    
    def _parse_cisco_route_line(self, line: str) -> Optional[RouteEntry]:
        """Parse a Cisco route line."""
        line = line.strip()
        if not line or line.startswith("Gateway of last resort") or line.startswith("Codes:"):
            return None
        
        # Expected formats:
        # "S    10.65.8.0/22 [1/0] via 10.66.0.97"
        # "C    10.120.0.0/16 is directly connected, GigabitEthernet0/0/0"
        # "O*   0.0.0.0/0 [110/2] via 10.66.0.1, 00:00:12, Ethernet0/0"
        
        parts = line.split()
        if len(parts) < 2:
            return None
        
        protocol_map = {
            "C": "connected",
            "S": "static", 
            "O": "ospf",
            "E": "egp",
            "i": "isis",
            "D": "eigrp",
            "B": "bgp",
            "R": "rip",
        }
        
        try:
            # Get protocol (first character of first part)
            protocol_char = parts[0][0]
            protocol = protocol_map.get(protocol_char, protocol_char)
            
            # Find the destination (second part usually)
            dest_with_mask = parts[1]
            if '/' not in dest_with_mask:
                return None
            
            dest, mask_len = dest_with_mask.split('/')
            
            next_hop = None
            if "via" in parts:
                via_idx = parts.index("via")
                if via_idx + 1 < len(parts):
                    next_hop = parts[via_idx + 1].rstrip(',')
            elif "directly connected" in line:
                next_hop = "0.0.0.0"  # Directly connected
            
            # Calculate netmask from prefix length
            try:
                netmask = self._prefix_to_netmask(int(mask_len))
            except:
                netmask = "255.255.255.255"
            
            return RouteEntry(
                destination=dest,
                netmask=netmask,
                next_hop=next_hop,
                protocol=protocol
            )
            
        except Exception as e:
            logger.debug(f"Failed to parse route line '{line}': {e}")
            return None
    
    def _parse_config_route_line(self, line: str) -> Optional[RouteEntry]:
        """Parse static route from running-config."""
        line = line.strip()
        
        # Expected formats:
        # "ip route 10.121.1.0 255.255.255.0 10.120.0.2"
        # "ip route vrf vss-network 10.121.1.0 255.255.255.0 10.120.0.2"
        
        if not line.startswith('ip route '):
            return None
        
        parts = line.split()
        if len(parts) < 4:
            return None
        
        try:
            # Handle VRF routes: ip route vrf <name> <dest> <mask> <next_hop>
            if parts[2] == 'vrf' and len(parts) >= 6:
                dest = parts[4]
                netmask = parts[5]
                next_hop = parts[6] if len(parts) > 6 else None
            # Handle regular routes: ip route <dest> <mask> <next_hop>
            else:
                dest = parts[2]
                netmask = parts[3]
                next_hop = parts[4] if len(parts) > 4 else None
            
            return RouteEntry(
                destination=dest,
                netmask=netmask,
                next_hop=next_hop,
                protocol='static'
            )
            
        except Exception as e:
            logger.debug(f"Failed to parse config route line '{line}': {e}")
            return None
    
    def _parse_asa_route_line(self, line: str) -> Optional[RouteEntry]:
        """Parse ASA route output."""
        line = line.strip()
        
        # ASA route formats:
        # "S   10.0.0.0 255.0.0.0 [1/0] via 10.120.0.1, outside"
        # "C   10.120.0.0 255.255.255.0 is directly connected, inside"
        # "S   0.0.0.0 0.0.0.0 [1/0] via 10.120.0.1"
        
        if not line or len(line) < 10:
            return None
            
        # Skip header lines
        if any(header in line for header in ['Codes:', 'Gateway', 'Legend', 'Flags']):
            return None
            
        parts = line.split()
        if len(parts) < 3:
            return None
            
        try:
            # ASA format: [protocol] [destination] [mask] [metric] via [next_hop] [interface]
            protocol_code = parts[0]
            
            if len(parts) >= 5 and 'via' in parts:
                dest = parts[1]
                netmask = parts[2] 
                via_index = parts.index('via')
                next_hop = parts[via_index + 1] if via_index + 1 < len(parts) else None
                
                # Convert ASA protocol codes
                protocol_map = {
                    'S': 'static', 'C': 'connected', 'O': 'ospf', 
                    'R': 'rip', 'B': 'bgp', 'D': 'eigrp'
                }
                protocol = protocol_map.get(protocol_code[0], protocol_code[0])
                
                return RouteEntry(
                    destination=dest,
                    netmask=netmask,
                    next_hop=next_hop,
                    protocol=protocol
                )
                
        except Exception as e:
            logger.debug(f"Failed to parse ASA route line '{line}': {e}")
            return None
    
    def _parse_cisco_interface_line(self, line: str) -> Optional[Dict]:
        """Parse a Cisco 'show ip interface brief' line."""
        parts = line.split()
        if len(parts) < 5:
            return None
        
        try:
            interface_name = parts[0]
            ip = parts[1]
            status = parts[4]
            
            if not self._is_valid_ip(ip) or status.lower() == 'administratively':
                return None
            
            # Assume /24 mask for simplicity - could be enhanced
            return {
                'name': interface_name,
                'ip': ip,
                'netmask': '255.255.255.0'
            }
            
        except Exception:
            return None
    
    def _build_topology_links(self, run_id: int):
        """Build topology links based on shared networks."""
        routers = self.db.query(Router).filter(Router.discovery_run_id == run_id, Router.is_router == True).all()
        
        for router in routers:
            networks = self.db.query(Network).filter(Network.router_id == router.id).all()
            
            for network in networks:
                # Find other routers on the same network
                other_networks = self.db.query(Network).filter(
                    Network.discovery_run_id == run_id,
                    Network.router_id != router.id,
                    Network.network == network.network
                ).all()
                
                for other_net in other_networks:
                    # Check if link already exists
                    existing = self.db.query(TopologyLink).filter(
                        TopologyLink.discovery_run_id == run_id,
                        TopologyLink.from_router_id == min(router.id, other_net.router_id),
                        TopologyLink.to_router_id == max(router.id, other_net.router_id)
                    ).first()
                    
                    if not existing:
                        link = TopologyLink(
                            discovery_run_id=run_id,
                            from_router_id=min(router.id, other_net.router_id),
                            to_router_id=max(router.id, other_net.router_id),
                            shared_network=network.network,
                            link_type='direct'
                        )
                        self.db.add(link)
        
        self.db.commit()
    
    def _classify_router(self, system_info: SystemInfo, routes: List[RouteEntry], interfaces: List[Dict]) -> bool:
        """Simple router classification."""
        if len(routes) > 0:
            return True
        if len(interfaces) > 2:  # More than 2 interfaces likely a router
            return True
        if system_info and system_info.sys_descr:
            descr = system_info.sys_descr.lower()
            if any(keyword in descr for keyword in ['router', 'ios', 'junos', 'nx-os', 'cisco']):
                return True
        # If we have system info via SSH, it's likely a manageable router
        if system_info and (system_info.hostname or system_info.sys_descr):
            return True
        return False
    
    def _extract_vendor(self, system_info: SystemInfo) -> Optional[str]:
        """Extract vendor from system description."""
        if not system_info or not system_info.sys_descr:
            return None
        
        descr = system_info.sys_descr.lower()
        vendors = ['cisco', 'juniper', 'arista', 'ubiquiti', 'mikrotik', 'fortinet']
        
        for vendor in vendors:
            if vendor in descr:
                return vendor.capitalize()
        
        return None
    
    def _extract_model(self, system_info: SystemInfo) -> Optional[str]:
        """Extract model from system description."""
        if not system_info or not system_info.sys_descr:
            return None
        
        descr = system_info.sys_descr
        # Simple pattern matching for common models
        import re
        
        # Cisco patterns
        cisco_patterns = [
            r'(ISR \d+)',
            r'(ASR \d+)',
            r'(Catalyst \d+)',
            r'(\d+系列)',
        ]
        
        for pattern in cisco_patterns:
            match = re.search(pattern, descr)
            if match:
                return match.group(1)
        
        return None
    
    def _ip_and_mask_to_cidr(self, ip: str, netmask: str) -> str:
        """Convert IP and netmask to proper CIDR notation."""
        try:
            # Convert netmask to CIDR prefix length
            mask_parts = netmask.split('.')
            prefix_length = 0
            for part in mask_parts:
                octet = int(part)
                while octet > 0:
                    prefix_length += octet & 1
                    octet >>= 1
            
            # Calculate network address
            ip_parts = [int(part) for part in ip.split('.')]
            mask_parts = [int(part) for part in netmask.split('.')]
            network_parts = []
            for i in range(4):
                network_parts.append(ip_parts[i] & mask_parts[i])
            
            network_ip = '.'.join(str(part) for part in network_parts)
            return f"{network_ip}/{prefix_length}"
        except Exception:
            return f"{ip}/24"  # Fallback
    
    def _is_valid_ip(self, ip: str) -> bool:
        """Check if IP address is valid."""
        try:
            IPv4Address(ip)
            return ip != '0.0.0.0'
        except:
            return False
    
    def _prefix_to_netmask(self, prefix: int) -> str:
        """Convert prefix length to netmask."""
        try:
            network = ip_network(f"0.0.0.0/{prefix}")
            return str(network.netmask)
        except:
            return "255.255.255.255"
    
    def _map_snmp_protocol(self, protocol_num: str) -> str:
        """Map SNMP protocol number to protocol name."""
        protocol_map = {
            '1': 'other',
            '2': 'local', 
            '3': 'netmgmt',
            '4': 'icmp',
            '5': 'egp',
            '6': 'ggp',
            '7': 'hello',
            '8': 'rip',
            '9': 'isIs',
            '10': 'esIs',
            '11': 'ciscoIgrp',
            '12': 'bbnSpfIgp',
            '13': 'ospf',
            '14': 'bgp',
        }
        
        return protocol_map.get(protocol_num, 'unknown')

    def _parse_asa_crypto_nat_info(self, output: str) -> List[RouteEntry]:
        """Parse ASA crypto map and NAT information to discover internal networks."""
        routes = []
        
        try:
            for line in output.splitlines():
                line = line.strip()
                
                # Parse crypto map entries for remote networks
                if 'Crypto Map' in line and 'access-list' in line:
                    # Example: Crypto Map "VPN-CRYPTO" 10 set access-list VPN-ACL
                    if 'access-list' in line:
                        acl_name = line.split('access-list')[-1].strip().strip('"')
                        # We'll need to look up the ACL to get the actual networks
                        logger.info(f"Found crypto map using ACL: {acl_name}")
                
                # Parse access-list entries for network information
                elif 'access-list' in line and 'permit' in line and 'ip' in line:
                    # Example: access-list VPN-ACL extended permit ip 192.168.0.0 255.255.0.0 10.0.0.0 255.0.0.0
                    parts = line.split()
                    if len(parts) >= 8:
                        try:
                            src_network = parts[4]  # Source network
                            src_mask = parts[5]     # Source mask
                            dst_network = parts[6]  # Destination network  
                            dst_mask = parts[7]     # Destination mask
                            
                            # Add routes for both source and destination networks
                            routes.append(RouteEntry(
                                destination=src_network,
                                netmask=src_mask,
                                next_hop="VPN_TUNNEL",
                                protocol="vpn"
                            ))
                            
                            routes.append(RouteEntry(
                                destination=dst_network,
                                netmask=dst_mask,
                                next_hop="VPN_TUNNEL", 
                                protocol="vpn"
                            ))
                            
                            logger.info(f"Found VPN network: {src_network}/{src_mask} -> {dst_network}/{dst_mask}")
                            
                        except (IndexError, ValueError):
                            continue
                
                # Parse NAT statements
                elif ('nat' in line and ('inside' in line or 'outside' in line)) or 'static' in line:
                    # Example: nat (inside) 10.121.225.0 255.255.255.0
                    parts = line.split()
                    if len(parts) >= 4:
                        try:
                            network = parts[2]
                            netmask = parts[3] if len(parts) > 3 else '255.255.255.0'
                            
                            routes.append(RouteEntry(
                                destination=network,
                                netmask=netmask,
                                next_hop="NAT_GATEWAY",
                                protocol="nat"
                            ))
                            
                            logger.info(f"Found NAT network: {network}/{netmask}")
                            
                        except (IndexError, ValueError):
                            continue
                
                # Parse tunnel interface configurations
                elif 'interface Tunnel' in line or 'Tunnel' in line:
                    # Example: interface Tunnel0
                    #          ip address 10.255.255.1 255.255.255.252
                    #          tunnel source 10.120.0.2
                    #          tunnel destination 10.66.0.97
                    logger.info(f"Found tunnel interface: {line}")
                
                # Parse IPSec peer information
                elif 'peer' in line and ('10.' in line or '192.168.' in line or '172.' in line):
                    # Example: peer 10.66.0.97
                    peer_ip = line.split()[-1]
                    logger.info(f"Found IPSec peer: {peer_ip}")
                    
                    # Add the peer as a potential router to discover
                    routes.append(RouteEntry(
                        destination=peer_ip,
                        netmask="255.255.255.255",
                        next_hop="IPSEC_PEER",
                        protocol="vpn"
                    ))
        
        except Exception as e:
            logger.debug(f"Failed to parse ASA crypto/NAT info: {e}")
        
        return routes
