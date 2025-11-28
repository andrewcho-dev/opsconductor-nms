"""
Vendor discovery factory for managing vendor-specific implementations.
"""

import logging
from typing import List, Dict, Optional, Type
from .base import VendorDiscoveryBase
from .cisco import CiscoDiscovery
from .asa import AsaDiscovery
from ..types import SystemInfo, RouteEntry

logger = logging.getLogger(__name__)


class VendorDiscoveryFactory:
    """Factory class for managing vendor discovery implementations."""
    
    def __init__(self):
        self._vendors: List[VendorDiscoveryBase] = []
        self._vendor_map: Dict[str, VendorDiscoveryBase] = {}
        self._register_default_vendors()
    
    def _register_default_vendors(self):
        """Register default vendor implementations."""
        self.register_vendor(CiscoDiscovery())
        self.register_vendor(AsaDiscovery())
    
    def register_vendor(self, vendor: VendorDiscoveryBase):
        """Register a new vendor implementation."""
        self._vendors.append(vendor)
        self._vendor_map[vendor.vendor_name.lower()] = vendor
        
        # Sort by priority (higher priority first)
        self._vendors.sort(key=lambda v: v.get_priority(), reverse=True)
        
        logger.info(f"Registered vendor: {vendor.vendor_name}")
    
    def identify_vendor(self, system_info: SystemInfo) -> Optional[VendorDiscoveryBase]:
        """Identify vendor from system information."""
        if not system_info or not system_info.sys_descr:
            return None
        
        # Try each vendor in priority order
        for vendor in self._vendors:
            if vendor.identify_vendor(system_info):
                logger.info(f"Identified vendor: {vendor.vendor_name}")
                return vendor
        
        logger.warning(f"Unknown vendor for system: {system_info.sys_descr[:100]}...")
        return None
    
    def get_vendor_by_name(self, vendor_name: str) -> Optional[VendorDiscoveryBase]:
        """Get vendor implementation by name."""
        return self._vendor_map.get(vendor_name.lower())
    
    def get_all_vendors(self) -> List[VendorDiscoveryBase]:
        """Get all registered vendor implementations."""
        return self._vendors.copy()
    
    def get_supported_vendors(self) -> List[str]:
        """Get list of supported vendor names."""
        return [vendor.vendor_name for vendor in self._vendors]
    
    def auto_detect_commands(self, system_info: SystemInfo) -> List[str]:
        """Get appropriate SSH commands based on vendor detection."""
        vendor = self.identify_vendor(system_info)
        if vendor:
            return vendor.get_ssh_commands()
        
        # Fallback to generic commands
        return [
            "show ip route",
            "show route", 
            "show ip route static",
            "show ip route connected",
            "show running-config | include ip route",
            "show ip interface brief",
            "show version"
        ]
    
    def auto_parse_routes(self, output: str, command: str, system_info: SystemInfo) -> List[RouteEntry]:
        """Parse routes using appropriate vendor parser."""
        vendor = self.identify_vendor(system_info)
        if vendor:
            return vendor.parse_route_output(output, command)
        
        # Fallback to generic parsing
        return self._generic_route_parser(output)
    
    def auto_parse_interfaces(self, output: str, system_info: SystemInfo) -> List[Dict]:
        """Parse interfaces using appropriate vendor parser."""
        vendor = self.identify_vendor(system_info)
        if vendor:
            return vendor.parse_interface_output(output)
        
        # Fallback to generic parsing
        return self._generic_interface_parser(output)
    
    def _generic_route_parser(self, output: str) -> List[RouteEntry]:
        """Generic route parser for unknown vendors."""
        routes = []
        
        for line in output.splitlines():
            # Very basic pattern matching
            if '/' in line and '.' in line:
                parts = line.split()
                for part in parts:
                    if '/' in part and self._is_valid_ip(part.split('/')[0]):
                        ip, prefix = part.split('/')
                        if prefix.isdigit():
                            netmask = self._cidr_to_netmask(int(prefix))
                            routes.append(RouteEntry(
                                destination=ip,
                                netmask=netmask,
                                next_hop=None,
                                protocol='unknown'
                            ))
                        break
        
        return routes
    
    def _generic_interface_parser(self, output: str) -> List[Dict]:
        """Generic interface parser for unknown vendors."""
        interfaces = []
        
        for line in output.splitlines():
            parts = line.split()
            # Look for lines with IP addresses
            for part in parts:
                if self._is_valid_ip(part):
                    interfaces.append({
                        'name': f'interface_{len(interfaces)}',
                        'ip_address': part,
                        'status': 'unknown',
                        'interface_type': 'unknown'
                    })
                    break
        
        return interfaces
    
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


# Global factory instance
vendor_factory = VendorDiscoveryFactory()
