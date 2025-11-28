"""
Cradlepoint-specific discovery implementation.
"""

import re
import logging
from typing import List, Dict, Optional, Any
from .base import VendorDiscoveryBase
from ..types import SystemInfo, RouteEntry

logger = logging.getLogger(__name__)


class CradlepointDiscovery(VendorDiscoveryBase):
    """Cradlepoint/ERG router discovery implementation."""
    
    @property
    def vendor_name(self) -> str:
        return "Cradlepoint"
    
    @property
    def supported_patterns(self) -> List[str]:
        return [
            'cradlepoint',
            'ergos',
            'cor',
            'ibm'
        ]
    
    @property
    def _supported_features(self) -> List[str]:
        return ['cellular', 'wan_failover', 'vpn', 'ethernet']
    
    def identify_vendor(self, system_info: SystemInfo) -> bool:
        """Identify Cradlepoint devices from system description."""
        if not system_info or not system_info.sys_descr:
            return False
        
        descr = system_info.sys_descr.lower()
        return any(pattern in descr for pattern in self.supported_patterns)
    
    def get_ssh_commands(self) -> List[str]:
        """Return Cradlepoint-specific SSH commands."""
        return [
            "get route info",                   # Cradlepoint route command
            "show route",                       # Alternative route command
            "show ip route",                    # Cisco-compatible fallback
            "get interface info",               # Interface information
            "show interface",                   # Alternative interface command
            "get config",                       # Configuration
            "show running-config",             # Cisco-compatible fallback
            "get system info",                  # System information
            "show version",                     # Version information
            "get wan info",                     # WAN status
            "get cellular info",                # Cellular status
        ]
    
    def parse_route_output(self, output: str, command: str) -> List[RouteEntry]:
        """Parse Cradlepoint routing table output."""
        routes = []
        
        if 'route' in command:
            routes.extend(self._parse_cradlepoint_routes(output))
        
        return routes
    
    def parse_interface_output(self, output: str) -> List[Dict[str, Any]]:
        """Parse Cradlepoint interface output."""
        interfaces = []
        
        for line in output.splitlines():
            interface = self._parse_interface_line(line)
            if interface:
                interfaces.append(interface)
        
        return interfaces
    
    def _parse_cradlepoint_routes(self, output: str) -> List[RouteEntry]:
        """Parse Cradlepoint route output."""
        routes = []
        
        for line in output.splitlines():
            route = self._parse_cradlepoint_route_line(line)
            if route:
                routes.append(route)
        
        return routes
    
    def _parse_cradlepoint_route_line(self, line: str) -> Optional[RouteEntry]:
        """Parse a single Cradlepoint route line."""
        line = line.strip()
        if not line or line.startswith("Destination") or line.startswith("---"):
            return None
        
        # Cradlepoint route formats vary, try to match common patterns
        # "192.168.0.0/24 dev eth0  proto kernel  scope link  src 192.168.0.1"
        # "0.0.0.0/0 via 192.168.0.254 dev eth0"
        # "10.0.0.0/8 via 10.1.1.1 dev wan1"
        
        parts = line.split()
        if len(parts) < 2:
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
        
        # Extract protocol
        protocol = 'connected'
        if 'static' in line.lower():
            protocol = 'static'
        elif 'kernel' in line.lower():
            protocol = 'connected'
        elif 'dhcp' in line.lower():
            protocol = 'dhcp'
        
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
    
    def _parse_interface_line(self, line: str) -> Optional[Dict[str, Any]]:
        """Parse interface line."""
        parts = line.split()
        if len(parts) < 3:
            return None
        
        # Skip header lines
        if parts[0] in ['Interface', 'Name', 'Device']:
            return None
        
        interface = parts[0]
        
        # Find IP address in the line
        ip = None
        for part in parts:
            if self._is_valid_ip(part):
                ip = part
                break
        
        if not ip:
            return None
        
        # Determine interface type
        status = 'up'  # Default to up for Cradlepoint
        
        return {
            'name': interface,
            'ip_address': ip,
            'status': status,
            'interface_type': self._classify_interface_type(interface)
        }
    
    def _classify_interface_type(self, interface: str) -> str:
        """Classify Cradlepoint interface type."""
        interface_lower = interface.lower()
        
        if 'eth' in interface_lower:
            return 'ethernet'
        elif 'wan' in interface_lower:
            return 'wan'
        elif 'lan' in interface_lower:
            return 'lan'
        elif 'wifi' in interface_lower or 'wlan' in interface_lower:
            return 'wireless'
        elif 'cell' in interface_lower or 'modem' in interface_lower:
            return 'cellular'
        elif 'usb' in interface_lower:
            return 'usb'
        elif 'lo' in interface_lower:
            return 'loopback'
        else:
            return 'unknown'
    
    def _extract_model_from_description(self, description: str) -> Optional[str]:
        """Extract Cradlepoint model from description."""
        # Cradlepoint model patterns
        model_patterns = [
            r'(cor\s+\w+)',                     # COR series (e.g., COR IBR1100)
            r'(ibr\d+\w*)',                     # IBR series (e.g., IBR1700)
            r'(arc\s+\w+)',                     # ARC series
            r'(cba\d+\w*)',                     # CBA series
            r'(ergos)',                         # ERGOS operating system
        ]
        
        for pattern in model_patterns:
            match = re.search(pattern, description, re.IGNORECASE)
            if match:
                return match.group(1).upper()
        
        # Generic detection
        if 'cor' in description.lower():
            return 'COR Series'
        elif 'ibr' in description.lower():
            return 'IBR Series'
        elif 'arc' in description.lower():
            return 'ARC Series'
        elif 'ergos' in description.lower():
            return 'ERGOS Router'
        
        return 'Cradlepoint'
    
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
