from dataclasses import dataclass
from ipaddress import IPv4Address, IPv4Network
import logging
from typing import Set, Optional
from .snmp_adapter import SystemInfo, InterfaceAddress, RouteEntry

logger = logging.getLogger(__name__)


@dataclass
class RouterClassification:
    is_router: bool
    score: int
    reason: str


class RouterClassifier:
    """Classify whether a device behaves like a router."""
    
    # Keywords that suggest a device is a router
    ROUTER_KEYWORDS = {
        'router', 'isr', 'asr', 'cradlepoint', 'l3 switch',
        'mikrotik', 'ubiquiti', 'opnsense', 'pfsense',
        'fortigate', 'cisco', 'juniper', 'arista'
    }
    
    SCORE_THRESHOLD = 3
    
    def classify_router(
        self,
        system_info: SystemInfo,
        ip_forwarding: Optional[bool],
        interfaces: list[InterfaceAddress],
        routes: list[RouteEntry],
    ) -> RouterClassification:
        """
        Classify a device as router or not using a scoring heuristic.
        
        Scoring logic:
        1. IP forwarding enabled: +3
        2. Multiple unique L3 networks: +2
        3. At least one remote route: +3
        4. Vendor/description hints: +1
        
        Result: is_router if score >= 3
        """
        score = 0
        reason_parts = []
        
        # 1. IP forwarding check
        if ip_forwarding is True:
            score += 3
            reason_parts.append("ipForwarding=1")
        elif ip_forwarding is False:
            score -= 1
            reason_parts.append("ipForwarding=0")
        else:
            reason_parts.append("ipForwarding=unknown")
        
        # 2. Multiple unique networks on interfaces
        unique_networks = self._get_unique_networks(interfaces)
        num_networks = len(unique_networks)
        if num_networks >= 2:
            score += 2
            reason_parts.append(f"{num_networks}_networks")
        else:
            reason_parts.append(f"{num_networks}_network")
        
        # 3. Remote routes
        directly_connected = self._get_unique_networks(interfaces)
        remote_routes = self._count_remote_routes(routes, directly_connected)
        if remote_routes > 0:
            score += 3
            reason_parts.append(f"{remote_routes}_remote_routes")
        else:
            reason_parts.append("0_remote_routes")
        
        # 4. Vendor/description hints
        if system_info.sys_descr and self._has_router_keywords(system_info.sys_descr):
            score += 1
            reason_parts.append("router_keywords_in_descr")
        
        if system_info.sys_object_id and self._has_router_keywords(system_info.sys_object_id):
            score += 1
            reason_parts.append("router_keywords_in_oid")
        
        is_router = score >= self.SCORE_THRESHOLD
        reason = ", ".join(reason_parts)
        
        return RouterClassification(
            is_router=is_router,
            score=score,
            reason=reason
        )
    
    def _get_unique_networks(self, interfaces: list[InterfaceAddress]) -> Set[str]:
        """Extract unique networks from interface addresses."""
        networks = set()
        for iface in interfaces:
            try:
                ip = IPv4Address(iface.ip)
                netmask = IPv4Address(iface.netmask)
                network = IPv4Network((ip, netmask), strict=False)
                networks.add(str(network))
            except Exception as e:
                logger.debug(f"Failed to parse interface {iface.ip}/{iface.netmask}: {e}")
        return networks
    
    def _count_remote_routes(self, routes: list[RouteEntry], directly_connected: Set[str]) -> int:
        """Count routes that are not directly connected."""
        remote_count = 0
        for route in routes:
            try:
                dest_ip = IPv4Address(route.destination_ip)
                netmask = IPv4Address(route.netmask)
                dest_network = IPv4Network((dest_ip, netmask), strict=False)
                dest_network_str = str(dest_network)
                
                if dest_network_str not in directly_connected:
                    remote_count += 1
            except Exception as e:
                logger.debug(f"Failed to parse route {route.destination_ip}/{route.netmask}: {e}")
        
        return remote_count
    
    def _has_router_keywords(self, text: str) -> bool:
        """Check if text contains router-related keywords."""
        text_lower = text.lower()
        for keyword in self.ROUTER_KEYWORDS:
            if keyword in text_lower:
                return True
        return False
