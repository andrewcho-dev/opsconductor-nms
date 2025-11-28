"""
Cisco-specific discovery implementation.
"""

import re
import logging
from typing import List, Dict, Optional, Any
from .base import VendorDiscoveryBase
from ..types import SystemInfo, RouteEntry

logger = logging.getLogger(__name__)


class CiscoDiscovery(VendorDiscoveryBase):
    """Cisco IOS/IOS-XE discovery implementation."""
    
    @property
    def vendor_name(self) -> str:
        return "Cisco"
    
    @property
    def supported_patterns(self) -> List[str]:
        return [
            'cisco',
            'ios',
            'cisco systems',
            'internetwork operating system'
        ]
    
    @property
    def _supported_features(self) -> List[str]:
        return ['vrf', 'multiple_contexts', 'extended_ping']
    
    def identify_vendor(self, system_info: SystemInfo) -> bool:
        """Identify Cisco devices from system description."""
        if not system_info or not system_info.sys_descr:
            return False
        
        descr = system_info.sys_descr.lower()
        return any(pattern in descr for pattern in self.supported_patterns)
    
    def get_ssh_commands(self) -> List[str]:
        """Return Cisco-specific SSH commands."""
        return [
            "show ip route",                    # Standard routing table
            "show ip route static",            # Static routes only
            "show ip route connected",         # Connected routes only
            "show running-config",             # Full configuration
            "show running-config | include ip route",  # Static routes from config
            "show ip interface brief",         # Interface summary
            "show version",                    # System version
            "show ip protocols summary",       # Routing protocols
            "show cdp neighbors detail",       # Discovery protocol
        ]
    
    def parse_route_output(self, output: str, command: str) -> List[RouteEntry]:
        """Parse Cisco routing table output."""
        routes = []
        
        if 'route' in command:
            routes.extend(self._parse_standard_routes(output))
        elif 'config' in command:
            routes.extend(self._parse_config_routes(output))
        
        return routes
    
    def parse_interface_output(self, output: str) -> List[Dict[str, Any]]:
        """Parse Cisco interface output."""
        interfaces = []
        
        for line in output.splitlines():
            interface = self._parse_interface_line(line)
            if interface:
                interfaces.append(interface)
        
        return interfaces
    
    def _parse_standard_routes(self, output: str) -> List[RouteEntry]:
        """Parse standard 'show ip route' output."""
        routes = []
        
        for line in output.splitlines():
            route = self._parse_cisco_route_line(line)
            if route:
                routes.append(route)
        
        return routes
    
    def _parse_config_routes(self, output: str) -> List[RouteEntry]:
        """Parse static routes from running configuration."""
        routes = []
        
        for line in output.splitlines():
            route = self._parse_config_route_line(line)
            if route:
                routes.append(route)
        
        return routes
    
    def _parse_cisco_route_line(self, line: str) -> Optional[RouteEntry]:
        """Parse a single Cisco route line."""
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
            "R": "rip",
            "O": "ospf",
            "E": "egp",
            "B": "bgp",
            "I": "igrp",
            "M": "mobile",
            "P": "periodic",
            "D": "eigrp",
            "EX": "eigrp_external",
            "N": "ospf_inter_area",
            "O": "ospf_intra_area",
            "IA": "ospf_inter_area",
            "E1": "ospf_external_type1",
            "E2": "ospf_external_type2",
            "L1": "isis_level1",
            "L2": "isis_level2",
        }
        
        # Extract protocol code
        protocol_code = parts[0]
        protocol = protocol_map.get(protocol_code, protocol_code)
        
        # Find destination network
        destination = None
        next_hop = None
        
        for i, part in enumerate(parts):
            if '/' in part and self._is_valid_ip(part.split('/')[0]):
                destination = part
                if 'via' in parts and i + 1 < len(parts):
                    via_index = parts.index('via')
                    if via_index + 1 < len(parts):
                        next_hop = parts[via_index + 1]
                break
        
        if not destination:
            return None
        
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
    
    def _parse_config_route_line(self, line: str) -> Optional[RouteEntry]:
        """Parse static route from configuration."""
        line = line.strip()
        if not line.startswith('ip route '):
            return None
        
        parts = line.split()
        if len(parts) < 4:
            return None
        
        # Format: ip route <destination> <mask> <next-hop>
        destination = parts[2]
        netmask = parts[3]
        next_hop = parts[4] if len(parts) > 4 else None
        
        return RouteEntry(
            destination=destination,
            netmask=netmask,
            next_hop=next_hop,
            protocol='static'
        )
    
    def _parse_interface_line(self, line: str) -> Optional[Dict[str, Any]]:
        """Parse interface line from 'show ip interface brief'."""
        parts = line.split()
        if len(parts) < 5:
            return None
        
        # Skip header lines
        if parts[0] in ['Interface', 'IP-Address']:
            return None
        
        interface = parts[0]
        ip = parts[1] if parts[1] != 'unassigned' else None
        status = parts[4] if len(parts) > 4 else 'unknown'
        
        if not ip or not self._is_valid_ip(ip):
            return None
        
        return {
            'name': interface,
            'ip_address': ip,
            'status': 'up' if status == 'up' else 'down',
            'interface_type': self._classify_interface_type(interface)
        }
    
    def _extract_model_from_description(self, description: str) -> Optional[str]:
        """Extract Cisco model from description."""
        # Common Cisco model patterns
        model_patterns = [
            r'(\d+)(?:-[A-Z]+)?\s+router',  # 2900 router
            r'(CISCO\s+\d+)(?:[A-Z]*)',     # CISCO2901
            r'(ISR\s+\d+)',                  # ISR 4000
            r'(ASR\s+\d+)',                  # ASR 1000
            r'(Catalyst\s+\d+)',             # Catalyst switches
            r'(Nexus\s+\d+)',                # Nexus switches
            r'(ASA\d+)',                     # ASA firewalls
            r'(FirePower\s+\d+)',            # Firepower
        ]
        
        for pattern in model_patterns:
            match = re.search(pattern, description, re.IGNORECASE)
            if match:
                return match.group(1).strip()
        
        # Generic detection
        if 'asa' in description:
            return 'ASA'
        elif 'router' in description:
            return 'Router'
        elif 'switch' in description:
            return 'Switch'
        elif 'firepower' in description:
            return 'Firepower'
        
        return None
    
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
    
    def _classify_interface_type(self, interface: str) -> str:
        """Classify interface type from name."""
        interface_lower = interface.lower()
        
        if 'gigabitethernet' in interface_lower or 'gi' in interface_lower:
            return 'ethernet'
        elif 'fastethernet' in interface_lower or 'fa' in interface_lower:
            return 'ethernet'
        elif 'serial' in interface_lower or 'se' in interface_lower:
            return 'serial'
        elif 'loopback' in interface_lower or 'lo' in interface_lower:
            return 'loopback'
        elif 'vlan' in interface_lower:
            return 'vlan'
        elif 'tunnel' in interface_lower:
            return 'tunnel'
        else:
            return 'unknown'
