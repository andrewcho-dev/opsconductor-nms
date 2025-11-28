"""
Mikrotik-specific discovery implementation.
"""

import re
import logging
from typing import List, Dict, Optional, Any
from .base import VendorDiscoveryBase
from ..types import SystemInfo, RouteEntry

logger = logging.getLogger(__name__)


class MikrotikDiscovery(VendorDiscoveryBase):
    """Mikrotik RouterOS discovery implementation."""
    
    @property
    def vendor_name(self) -> str:
        return "Mikrotik"
    
    @property
    def supported_patterns(self) -> List[str]:
        return [
            'mikrotik',
            'routeros',
            'router os',
            'mikrotik routeros'
        ]
    
    @property
    def _supported_features(self) -> List[str]:
        return ['wireless', 'routing_tables', 'bridges', 'vlans']
    
    def identify_vendor(self, system_info: SystemInfo) -> bool:
        """Identify Mikrotik devices from system description."""
        if not system_info or not system_info.sys_descr:
            return False
        
        descr = system_info.sys_descr.lower()
        return any(pattern in descr for pattern in self.supported_patterns)
    
    def get_ssh_commands(self) -> List[str]:
        """Return Mikrotik-specific SSH commands."""
        return [
            "/ip route print",                  # RouterOS routing table
            "/ip route print detail",           # Detailed routing table
            "/interface print",                 # Interface list
            "/interface print detail",          # Detailed interface info
            "/system resource print",           # System resources
            "/system routerboard print",        # Hardware info
            "/ip address print",                # IP addresses
            "/routing table print",             # Routing tables
            "/export",                          # Configuration export
        ]
    
    def parse_route_output(self, output: str, command: str) -> List[RouteEntry]:
        """Parse Mikrotik routing table output."""
        routes = []
        
        if 'route' in command:
            routes.extend(self._parse_mikrotik_routes(output))
        
        return routes
    
    def parse_interface_output(self, output: str) -> List[Dict[str, Any]]:
        """Parse Mikrotik interface output."""
        interfaces = []
        
        for line in output.splitlines():
            interface = self._parse_interface_line(line)
            if interface:
                interfaces.append(interface)
        
        return interfaces
    
    def _parse_mikrotik_routes(self, output: str) -> List[RouteEntry]:
        """Parse Mikrotik /ip route print output."""
        routes = []
        
        for line in output.splitlines():
            route = self._parse_mikrotik_route_line(line)
            if route:
                routes.append(route)
        
        return routes
    
    def _parse_mikrotik_route_line(self, line: str) -> Optional[RouteEntry]:
        """Parse a single Mikrotik route line."""
        line = line.strip()
        if not line or line.startswith("Flags:") or line.startswith("DST-ADDRESS"):
            return None
        
        # Mikrotik route formats:
        # "0.0.0.0/0  ether1  10.0.0.1"
        # "192.168.1.0/24  bridge1  connected"
        # "10.0.0.0/24  ether2  10.0.0.254"
        
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
        
        # Extract next hop (typically the gateway)
        next_hop = None
        for i, part in enumerate(parts):
            if self._is_valid_ip(part) and i > 0:  # Skip the destination IP
                next_hop = part
                break
        
        # Determine protocol
        protocol = 'connected'
        if 'connected' in line.lower():
            protocol = 'connected'
        elif 'static' in line.lower():
            protocol = 'static'
        elif 'rip' in line.lower():
            protocol = 'rip'
        elif 'ospf' in line.lower():
            protocol = 'ospf'
        elif 'bgp' in line.lower():
            protocol = 'bgp'
        
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
        """Parse interface line from /interface print."""
        parts = line.split()
        if len(parts) < 2:
            return None
        
        # Skip header lines
        if parts[0] in ['Flags:', 'NAME', '#']:
            return None
        
        interface = parts[0]
        
        # Find IP address - Mikrotik interfaces don't show IP in interface print
        # We'll need to check /ip address print output
        ip = None  # Will be populated from separate IP address query
        
        # Determine interface type from name
        interface_type = self._classify_interface_type(interface)
        
        return {
            'name': interface,
            'ip_address': ip,
            'status': 'unknown',  # Will be determined from interface detail
            'interface_type': interface_type
        }
    
    def _classify_interface_type(self, interface: str) -> str:
        """Classify Mikrotik interface type from name."""
        interface_lower = interface.lower()
        
        if 'ether' in interface_lower:
            return 'ethernet'
        elif 'wlan' in interface_lower or 'wifi' in interface_lower:
            return 'wireless'
        elif 'bridge' in interface_lower:
            return 'bridge'
        elif 'vlan' in interface_lower:
            return 'vlan'
        elif 'pppoe' in interface_lower:
            return 'pppoe'
        elif 'pptp' in interface_lower:
            return 'pptp'
        elif 'l2tp' in interface_lower:
            return 'l2tp'
        elif 'gre' in interface_lower:
            return 'gre'
        elif 'eoip' in interface_lower:
            return 'eoip'
        elif 'vrrp' in interface_lower:
            return 'vrrp'
        elif 'loopback' in interface_lower:
            return 'loopback'
        else:
            return 'unknown'
    
    def _extract_model_from_description(self, description: str) -> Optional[str]:
        """Extract Mikrotik model from description."""
        # Mikrotik model patterns
        model_patterns = [
            r'(rb\d+\w*)',                      # RouterBoard models (RB750, RB2011, etc.)
            r'(crs\d+\w*)',                     # Cloud Router Switch series
            r'(ccr\d+\w*)',                     # Cloud Core Router series
            r'(hEX\s+\w*)',                     # hEX series
            r'(hAP\s+\w*)',                     # hAP series
            r'(wAP\s+\w*)',                     # wAP series
            r'(mAP\s+\w*)',                     # mAP series
            r'(cAP\s+\w*)',                     # cAP series
            r'(LDF\s+\w*)',                     # LDF series
            r'(RBD\s+\w*)',                     # RBD series (Diskless)
            r'(RBM\d+\w*)',                     # RBM series (Mikrotik OS)
        ]
        
        for pattern in model_patterns:
            match = re.search(pattern, description, re.IGNORECASE)
            if match:
                return match.group(1).upper()
        
        # Generic detection
        if 'routerboard' in description.lower():
            return 'RouterBoard'
        elif 'routeros' in description.lower():
            return 'RouterOS'
        
        return 'Mikrotik'
    
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
