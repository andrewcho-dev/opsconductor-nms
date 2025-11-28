"""
Cisco ASA-specific discovery implementation.
"""

import re
import logging
from typing import List, Dict, Optional, Any
from .base import VendorDiscoveryBase
from ..types import SystemInfo, RouteEntry

logger = logging.getLogger(__name__)


class AsaDiscovery(VendorDiscoveryBase):
    """Cisco ASA firewall discovery implementation."""
    
    @property
    def vendor_name(self) -> str:
        return "Cisco ASA"
    
    @property
    def supported_patterns(self) -> List[str]:
        return [
            'asa',
            'adaptive security appliance',
            'firepower',
            'cisco security appliance'
        ]
    
    @property
    def _supported_features(self) -> List[str]:
        return ['vpn', 'nat', 'crypto', 'security_contexts', 'failover']
    
    def identify_vendor(self, system_info: SystemInfo) -> bool:
        """Identify ASA devices from system description."""
        if not system_info or not system_info.sys_descr:
            return False
        
        descr = system_info.sys_descr.lower()
        return any(pattern in descr for pattern in self.supported_patterns)
    
    def get_ssh_commands(self) -> List[str]:
        """Return ASA-specific SSH commands."""
        return [
            "show route",                       # ASA routing table
            "show crypto map",                  # VPN tunnel information
            "show nat",                         # NAT translations
            "show run | include tunnel",        # Tunnel configurations
            "show run | include nat",           # NAT configurations
            "show vpn-sessiondb",               # Active VPN sessions
            "show crypto ipsec sa",             # IPSec security associations
            "show access-list",                 # ACLs that might reveal networks
            "show interface",                   # Interface status
            "show failover",                    # Failover status
        ]
    
    def parse_route_output(self, output: str, command: str) -> List[RouteEntry]:
        """Parse ASA routing table output."""
        routes = []
        
        if 'route' in command:
            routes.extend(self._parse_asa_routes(output))
        elif any(asa_cmd in command for asa_cmd in ['crypto', 'nat', 'tunnel', 'vpn', 'access-list']):
            routes.extend(self._parse_asa_crypto_nat_info(output))
        
        return routes
    
    def parse_interface_output(self, output: str) -> List[Dict[str, Any]]:
        """Parse ASA interface output."""
        interfaces = []
        
        for line in output.splitlines():
            interface = self._parse_asa_interface_line(line)
            if interface:
                interfaces.append(interface)
        
        return interfaces
    
    def _parse_asa_routes(self, output: str) -> List[RouteEntry]:
        """Parse ASA 'show route' output."""
        routes = []
        
        for line in output.splitlines():
            route = self._parse_asa_route_line(line)
            if route:
                routes.append(route)
        
        return routes
    
    def _parse_asa_route_line(self, line: str) -> Optional[RouteEntry]:
        """Parse ASA route output."""
        line = line.strip()
        if not line or line.startswith("Gateway of last resort") or line.startswith("Codes:"):
            return None
        
        # ASA route formats:
        # "S 10.0.0.0 255.255.255.0 [1/0] via 10.1.1.1, outside"
        # "C 10.1.1.0 255.255.255.0 is directly connected, outside"
        # "D 192.168.1.0 255.255.255.0 [90/0] via 10.1.1.2, 0:00:00, inside"
        
        parts = line.split()
        if len(parts) < 3:
            return None
        
        protocol_map = {
            "C": "connected",
            "S": "static",
            "R": "rip",
            "O": "ospf",
            "B": "bgp",
            "D": "eigrp",
            "I": "igrp",
            "M": "mobile",
            "E": "egp",
        }
        
        protocol_code = parts[0]
        protocol = protocol_map.get(protocol_code, protocol_code)
        
        # Extract destination and mask
        destination = None
        netmask = None
        next_hop = None
        
        try:
            if len(parts) >= 3 and self._is_valid_ip(parts[1]) and self._is_valid_ip(parts[2]):
                destination = parts[1]
                netmask = parts[2]
                
                # Find next hop
                if 'via' in parts:
                    via_index = parts.index('via')
                    if via_index + 1 < len(parts):
                        next_hop = parts[via_index + 1]
        except (ValueError, IndexError):
            return None
        
        if not destination or not netmask:
            return None
        
        return RouteEntry(
            destination=destination,
            netmask=netmask,
            next_hop=next_hop if next_hop and next_hop != '0.0.0.0' else None,
            protocol=protocol
        )
    
    def _parse_asa_crypto_nat_info(self, output: str) -> List[RouteEntry]:
        """Parse ASA crypto map and NAT information to discover internal networks."""
        routes = []
        
        # Extract networks from crypto maps
        crypto_networks = self._extract_crypto_networks(output)
        for network in crypto_networks:
            routes.append(RouteEntry(
                destination=network,
                netmask="255.255.255.0",
                next_hop=None,
                protocol="vpn"
            ))
        
        # Extract networks from NAT statements
        nat_networks = self._extract_nat_networks(output)
        for network in nat_networks:
            routes.append(RouteEntry(
                destination=network,
                netmask="255.255.255.0",
                next_hop=None,
                protocol="nat"
            ))
        
        return routes
    
    def _extract_crypto_networks(self, output: str) -> List[str]:
        """Extract network information from crypto map output."""
        networks = []
        
        # Match ACL entries in crypto maps
        acl_pattern = r'access-list\s+(\d+)\s+permit\s+ip\s+(\d+\.\d+\.\d+\.\d+)\s+(\d+\.\d+\.\d+\.\d+)'
        for match in re.finditer(acl_pattern, output, re.IGNORECASE):
            network = match.group(2)
            if self._is_valid_ip(network):
                networks.append(network)
        
        # Match network-object statements
        network_obj_pattern = r'network-object\s+host\s+(\d+\.\d+\.\d+\.\d+)'
        for match in re.finditer(network_obj_pattern, output, re.IGNORECASE):
            network = match.group(1)
            if self._is_valid_ip(network):
                networks.append(network)
        
        return list(set(networks))  # Remove duplicates
    
    def _extract_nat_networks(self, output: str) -> List[str]:
        """Extract network information from NAT configuration."""
        networks = []
        
        # Match nat statements
        nat_pattern = r'nat\s+\([^)]+\)\s+(\d+\.\d+\.\d+\.\d+)\s+(\d+\.\d+\.\d+\.\d+)'
        for match in re.finditer(nat_pattern, output, re.IGNORECASE):
            network = match.group(1)
            if self._is_valid_ip(network):
                networks.append(network)
        
        # Match global statements
        global_pattern = r'global\s+\([^)]+\)\s+(\d+\.\d+\.\d+\.\d+)'
        for match in re.finditer(global_pattern, output, re.IGNORECASE):
            network = match.group(1)
            if self._is_valid_ip(network):
                networks.append(network)
        
        return list(set(networks))  # Remove duplicates
    
    def _parse_asa_interface_line(self, line: str) -> Optional[Dict[str, Any]]:
        """Parse ASA interface line."""
        parts = line.split()
        if len(parts) < 5:
            return None
        
        # Skip header lines
        if parts[0] in ['Interface', 'IP-Address', 'Name']:
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
            'interface_type': self._classify_asa_interface_type(interface)
        }
    
    def _classify_asa_interface_type(self, interface: str) -> str:
        """Classify ASA interface type."""
        interface_lower = interface.lower()
        
        if 'outside' in interface_lower:
            return 'external'
        elif 'inside' in interface_lower:
            return 'internal'
        elif 'dmz' in interface_lower:
            return 'dmz'
        elif 'management' in interface_lower:
            return 'management'
        elif 'tunnel' in interface_lower:
            return 'tunnel'
        elif 'backup' in interface_lower:
            return 'backup'
        else:
            return 'unknown'
    
    def _extract_model_from_description(self, description: str) -> Optional[str]:
        """Extract ASA model from description."""
        # ASA model patterns
        model_patterns = [
            r'ASA(\d+)',                       # ASA5506, ASA5515, etc.
            r'FirePower\s+(\d+)',              # FirePower 1000 series
            r'Adaptive\s+Security\s+Appliance',
        ]
        
        for pattern in model_patterns:
            match = re.search(pattern, description, re.IGNORECASE)
            if match:
                return f"ASA {match.group(1)}" if match.groups() else "ASA"
        
        return "ASA"
    
    def _is_valid_ip(self, ip: str) -> bool:
        """Validate IP address format."""
        try:
            parts = ip.split('.')
            return len(parts) == 4 and all(0 <= int(part) <= 255 for part in parts)
        except:
            return False
