"""
Juniper-specific discovery implementation.
"""

import re
import logging
from typing import List, Dict, Optional, Any
from .base import VendorDiscoveryBase
from ..types import SystemInfo, RouteEntry

logger = logging.getLogger(__name__)


class JuniperDiscovery(VendorDiscoveryBase):
    """Juniper JunOS discovery implementation."""
    
    @property
    def vendor_name(self) -> str:
        return "Juniper"
    
    @property
    def supported_patterns(self) -> List[str]:
        return [
            'juniper',
            'junos',
            'juniper networks'
        ]
    
    @property
    def _supported_features(self) -> List[str]:
        return ['routing_instances', 'vrf', 'logical_systems']
    
    def identify_vendor(self, system_info: SystemInfo) -> bool:
        """Identify Juniper devices from system description."""
        if not system_info or not system_info.sys_descr:
            return False
        
        descr = system_info.sys_descr.lower()
        return any(pattern in descr for pattern in self.supported_patterns)
    
    def get_ssh_commands(self) -> List[str]:
        """Return Juniper-specific SSH commands."""
        return [
            "show route",                       # JunOS routing table
            "show route terse",                 # Compact routing table
            "show route inet.0",                # Main routing table
            "show configuration | display set | match route",  # Static routes
            "show interfaces terse",            # Interface summary
            "show version",                     # System version
            "show system information",          # System info
            "show chassis hardware",            # Hardware info
            "show logical-systems",             # Logical systems
            "show routing-instances",           # Routing instances
        ]
    
    def parse_route_output(self, output: str, command: str) -> List[RouteEntry]:
        """Parse Juniper routing table output."""
        routes = []
        
        if 'route' in command:
            routes.extend(self._parse_juniper_routes(output))
        elif 'configuration' in command:
            routes.extend(self._parse_config_routes(output))
        
        return routes
    
    def parse_interface_output(self, output: str) -> List[Dict[str, Any]]:
        """Parse Juniper interface output."""
        interfaces = []
        
        for line in output.splitlines():
            interface = self._parse_interface_line(line)
            if interface:
                interfaces.append(interface)
        
        return interfaces
    
    def _parse_juniper_routes(self, output: str) -> List[RouteEntry]:
        """Parse JunOS 'show route' output."""
        routes = []
        
        for line in output.splitlines():
            route = self._parse_juniper_route_line(line)
            if route:
                routes.append(route)
        
        return routes
    
    def _parse_juniper_route_line(self, line: str) -> Optional[RouteEntry]:
        """Parse a single Juniper route line."""
        line = line.strip()
        if not line or line.startswith("inet.") or line.startswith("mpls."):
            return None
        
        # JunOS route formats:
        # "10.0.0.0/24  *[Direct/0] 2w0d  via ge-0/0/0.0"
        # "192.168.1.0/24  *[Static/1] 1w3d  via 10.1.1.1"
        # "0.0.0.0/0          *[Static/1] 1w3d  via 10.1.1.1"
        
        parts = line.split()
        if len(parts) < 3:
            return None
        
        # Extract destination network
        destination = None
        for part in parts:
            if '/' in part and self._is_valid_ip(part.split('/')[0]):
                destination = part
                break
        
        if not destination:
            return None
        
        # Extract next hop
        next_hop = None
        if 'via' in parts:
            via_index = parts.index('via')
            if via_index + 1 < len(parts):
                next_hop = parts[via_index + 1]
                # Remove interface suffix if present (e.g., ge-0/0/0.0)
                next_hop = next_hop.split('.')[0] if '.' in next_hop else next_hop
        
        # Extract protocol from preference
        protocol = 'connected'  # default
        for part in parts:
            if '[' in part and '/' in part:
                protocol_part = part.split('[')[1].split('/')[0]
                protocol_map = {
                    'Direct': 'connected',
                    'Static': 'static',
                    'OSPF': 'ospf',
                    'BGP': 'bgp',
                    'RIP': 'rip',
                    'ISIS': 'isis',
                    'LDP': 'ldp',
                    'L2VPN': 'l2vpn'
                }
                protocol = protocol_map.get(protocol_part, protocol_part.lower())
                break
        
        # Convert CIDR to IP + netmask format
        if '/' in destination:
            ip, prefix = destination.split('/')
            netmask = self._cidr_to_netmask(int(prefix))
        else:
            ip = destination
            netmask = "255.255.255.0"
        
        return RouteEntry(
            destination=ip,
            netmask=netmask,
            next_hop=next_hop if next_hop and next_hop != '0.0.0.0' else None,
            protocol=protocol
        )
    
    def _parse_config_routes(self, output: str) -> List[RouteEntry]:
        """Parse static routes from JunOS configuration."""
        routes = []
        
        # Match set routing-options static route commands
        route_pattern = r'set routing-options static route (\d+\.\d+\.\d+\.\d+)/(\d+) next-hop (\d+\.\d+\.\d+\.\d+)'
        for match in re.finditer(route_pattern, output):
            destination = match.group(1)
            prefix = int(match.group(2))
            next_hop = match.group(3)
            netmask = self._cidr_to_netmask(prefix)
            
            routes.append(RouteEntry(
                destination=destination,
                netmask=netmask,
                next_hop=next_hop,
                protocol='static'
            ))
        
        return routes
    
    def _parse_interface_line(self, line: str) -> Optional[Dict[str, Any]]:
        """Parse interface line from 'show interfaces terse'."""
        parts = line.split()
        if len(parts) < 4:
            return None
        
        # Skip header lines
        if parts[0] in ['Interface', 'Admin', 'Link', 'Proto']:
            return None
        
        interface = parts[0]
        # Skip logical interfaces (those with dots)
        if '.' in interface:
            return None
        
        # Find IP address in the line
        ip = None
        for part in parts:
            if self._is_valid_ip(part):
                ip = part
                break
        
        if not ip:
            return None
        
        # Extract status from protocol field
        status = 'up' if len(parts) > 3 and parts[3] == 'up' else 'down'
        
        return {
            'name': interface,
            'ip_address': ip,
            'status': status,
            'interface_type': self._classify_interface_type(interface)
        }
    
    def _classify_interface_type(self, interface: str) -> str:
        """Classify Juniper interface type from name."""
        interface_lower = interface.lower()
        
        if 'ge-' in interface_lower:  # Gigabit Ethernet
            return 'ethernet'
        elif 'xe-' in interface_lower:  # 10 Gigabit Ethernet
            return 'ethernet'
        elif 'et-' in interface_lower:  # 40/100 Gigabit Ethernet
            return 'ethernet'
        elif 'fe-' in interface_lower:  # Fast Ethernet
            return 'ethernet'
        elif 'lo0' in interface_lower:  # Loopback
            return 'loopback'
        elif 'st0' in interface_lower:  # Secure tunnel
            return 'tunnel'
        elif 'gr-' in interface_lower:  # GRE tunnel
            return 'tunnel'
        elif 'vt-' in interface_lower:  # Virtual tunnel
            return 'tunnel'
        elif 'vlan' in interface_lower:
            return 'vlan'
        elif 'irb' in interface_lower:  # Integrated routing and bridging
            return 'irb'
        else:
            return 'unknown'
    
    def _extract_model_from_description(self, description: str) -> Optional[str]:
        """Extract Juniper model from description."""
        # Juniper model patterns
        model_patterns = [
            r'(mx\d+)',                        # MX series routers
            r'(ex\d+)',                        # EX series switches
            r'(qfx\d+)',                       # QFX series switches
            r'(srx\d+)',                       # SRX series firewalls
            r'(ptx\d+)',                       # PTX series routers
            r'(acx\d+)',                       # ACX series routers
            r'(vrr\d+)',                       # Virtual routers
        ]
        
        for pattern in model_patterns:
            match = re.search(pattern, description, re.IGNORECASE)
            if match:
                return match.group(1).upper()
        
        # Generic detection
        if 'mx' in description.lower():
            return 'MX Router'
        elif 'srx' in description.lower():
            return 'SRX Firewall'
        elif 'ex' in description.lower():
            return 'EX Switch'
        elif 'qfx' in description.lower():
            return 'QFX Switch'
        
        return 'Juniper'
    
    def _is_valid_ip(self, ip: str) -> bool:
        """Validate IP address format."""
        try:
            parts = ip.split('.')
            return len(parts) == 4 and all(0 <= int(part) <= 255 for part in parts)
        except:
            return False
    
    def _cidr_to_netmask(self, prefix: int) -> str:
        """Convert CIDR prefix to netmask."""
        if prefix < 0 or prefix > 32:
            return "255.255.255.0"
        
        mask = (0xffffffff >> (32 - prefix)) << (32 - prefix)
        netmask_parts = [
            str((mask >> 24) & 0xff),
            str((mask >> 16) & 0xff),
            str((mask >> 8) & 0xff),
            str(mask & 0xff)
        ]
        return '.'.join(netmask_parts)
