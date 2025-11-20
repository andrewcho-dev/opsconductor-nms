from dataclasses import dataclass
from typing import Optional, List
import logging
from pysnmp.hlapi import (
    getCmd, bulkCmd, SnmpEngine, CommunityData, UdpTransportTarget,
    ContextData, ObjectType, ObjectIdentity, usmHMACMD5AuthProtocol,
    usmDESPrivProtocol, UsmUserData
)
from pysnmp.smi import builder, view

logger = logging.getLogger(__name__)


class SnmpError(Exception):
    """Custom exception for SNMP errors."""
    pass


@dataclass
class SystemInfo:
    hostname: Optional[str] = None
    sys_descr: Optional[str] = None
    sys_object_id: Optional[str] = None


@dataclass
class InterfaceAddress:
    ip: str
    netmask: str


@dataclass
class RouteEntry:
    destination_ip: str
    netmask: str
    next_hop: Optional[str] = None
    protocol: Optional[str] = None


class SnmpAdapter:
    """Thin wrapper around SNMP operations."""
    
    def __init__(self, timeout: int = 5, retries: int = 2):
        self.timeout = timeout
        self.retries = retries
        self.snmp_engine = SnmpEngine()
        self.mib_view = view.MibViewController(builder.MibBuilder())
    
    def _create_transport_target(self, target_ip: str) -> UdpTransportTarget:
        """Create UDP transport target."""
        return UdpTransportTarget((target_ip, 161), timeout=self.timeout, retries=self.retries)
    
    def _create_community_data(self, community: str, version: str) -> CommunityData:
        """Create community data for SNMPv2c."""
        if version == "2c":
            return CommunityData(community, mpModel=1)  # SNMPv2c
        elif version == "3":
            # For now, assume SNMPv3 uses authPriv with MD5/DES
            return UsmUserData('initial', authKey=community, privKey=community,
                             authProtocol=usmHMACMD5AuthProtocol,
                             privProtocol=usmDESPrivProtocol)
        else:
            raise SnmpError(f"Unsupported SNMP version: {version}")
    
    def get_system_info(self, target_ip: str, community: str, version: str) -> SystemInfo:
        """
        Query system information (hostname, description, object ID).
        OIDs: sysName=1.3.6.1.2.1.1.5, sysDescr=1.3.6.1.2.1.1.1, sysObjectID=1.3.6.1.2.1.1.2
        """
        try:
            transport = self._create_transport_target(target_ip)
            community_data = self._create_community_data(community, version)
            
            hostname = None
            sys_descr = None
            sys_object_id = None
            
            # Get sysName
            for error_indication, error_status, error_index, var_binds in getCmd(
                self.snmp_engine, community_data, transport, ContextData(),
                ObjectType(ObjectIdentity('SNMPv2-MIB', 'sysName', 0))
            ):
                if error_indication:
                    logger.warning(f"SNMP sysName query failed: {error_indication}")
                else:
                    for name, val in var_binds:
                        hostname = str(val)
            
            # Get sysDescr
            for error_indication, error_status, error_index, var_binds in getCmd(
                self.snmp_engine, community_data, transport, ContextData(),
                ObjectType(ObjectIdentity('SNMPv2-MIB', 'sysDescr', 0))
            ):
                if error_indication:
                    logger.warning(f"SNMP sysDescr query failed: {error_indication}")
                else:
                    for name, val in var_binds:
                        sys_descr = str(val)
            
            # Get sysObjectID
            for error_indication, error_status, error_index, var_binds in getCmd(
                self.snmp_engine, community_data, transport, ContextData(),
                ObjectType(ObjectIdentity('SNMPv2-MIB', 'sysObjectID', 0))
            ):
                if error_indication:
                    logger.warning(f"SNMP sysObjectID query failed: {error_indication}")
                else:
                    for name, val in var_binds:
                        sys_object_id = str(val)
            
            return SystemInfo(hostname=hostname, sys_descr=sys_descr, sys_object_id=sys_object_id)
        
        except Exception as e:
            raise SnmpError(f"Failed to get system info from {target_ip}: {str(e)}")
    
    def get_ip_forwarding(self, target_ip: str, community: str, version: str) -> Optional[bool]:
        """
        Query IP forwarding status (OID: 1.3.6.1.2.1.4.1.0).
        Returns: True if forwarding enabled, False if disabled, None if not available.
        """
        try:
            transport = self._create_transport_target(target_ip)
            community_data = self._create_community_data(community, version)
            
            for error_indication, error_status, error_index, var_binds in getCmd(
                self.snmp_engine, community_data, transport, ContextData(),
                ObjectType(ObjectIdentity('IP-MIB', 'ipForwarding', 0))
            ):
                if error_indication:
                    logger.debug(f"IP forwarding query unavailable on {target_ip}")
                    return None
                else:
                    for name, val in var_binds:
                        # 1 = forwarding, 2 = not forwarding
                        return int(val) == 1
            
            return None
        
        except Exception as e:
            logger.debug(f"Failed to get IP forwarding from {target_ip}: {str(e)}")
            return None
    
    def get_interfaces_and_addresses(self, target_ip: str, community: str, version: str) -> List[InterfaceAddress]:
        """
        Query interface IP addresses and netmasks.
        Walks the IP address table (RFC 1213).
        """
        addresses = []
        try:
            transport = self._create_transport_target(target_ip)
            community_data = self._create_community_data(community, version)
            
            # Walk ipAddrTable (1.3.6.1.2.1.4.20.1)
            for error_indication, error_status, error_index, var_binds in bulkCmd(
                self.snmp_engine, community_data, transport, ContextData(),
                0, 25,
                ObjectType(ObjectIdentity('IP-MIB', 'ipAddrEntry'))
            ):
                if error_indication:
                    logger.warning(f"SNMP bulk query failed: {error_indication}")
                    break
                else:
                    for name, val in var_binds:
                        # ipAddrTable contains: ipAddrAddress, ipAddrIfIndex, ipAddrNetMask, ipAddrBcastAddr, ipAddrReasmMaxSize
                        # We're interested in ipAddrAddress (col 1) and ipAddrNetMask (col 3)
                        oid_str = name.prettyPrint()
                        
                        if 'ipAddrAddress' in oid_str:
                            ip = str(val)
                            # Skip link-local, loopback, etc.
                            if not ip.startswith('127.') and not ip.startswith('169.254'):
                                # Now we need to find the netmask for this IP
                                # For simplicity in Phase 0, we'll try to fetch it
                                pass
                        elif 'ipAddrNetMask' in oid_str:
                            netmask = str(val)
                            # Pair this with the IP we found earlier (simplified)
                            if addresses and addresses[-1].netmask is None:
                                addresses[-1].netmask = netmask
            
            # If bulk walk didn't work well, try a simpler approach
            if not addresses:
                addresses = self._get_interfaces_simple(target_ip, community, version)
            
            return addresses
        
        except Exception as e:
            logger.warning(f"Failed to get interfaces from {target_ip}: {str(e)}")
            return []
    
    def _get_interfaces_simple(self, target_ip: str, community: str, version: str) -> List[InterfaceAddress]:
        """Fallback method to get interfaces with a /24 assumption."""
        try:
            transport = self._create_transport_target(target_ip)
            community_data = self._create_community_data(community, version)
            
            addresses = []
            for error_indication, error_status, error_index, var_binds in bulkCmd(
                self.snmp_engine, community_data, transport, ContextData(),
                0, 25,
                ObjectType(ObjectIdentity('IP-MIB', 'ipAddrTable'))
            ):
                if error_indication:
                    break
                
                for name, val in var_binds:
                    oid_parts = name.prettyPrint().split('.')
                    if len(oid_parts) > 10:
                        ip = '.'.join(oid_parts[-4:])
                        if not ip.startswith('127.') and not ip.startswith('169.254'):
                            # Default to /24 for now (Phase 0)
                            addresses.append(InterfaceAddress(ip=ip, netmask='255.255.255.0'))
            
            return addresses
        
        except Exception as e:
            logger.debug(f"Simple interface fetch failed: {str(e)}")
            return []
    
    def get_routing_entries(self, target_ip: str, community: str, version: str) -> List[RouteEntry]:
        """
        Query routing table entries.
        Walks ipRouteTable (RFC 1213) or ipCidrRouteTable (RFC 2096).
        """
        routes = []
        try:
            transport = self._create_transport_target(target_ip)
            community_data = self._create_community_data(community, version)
            
            # Try ipCidrRouteTable first (1.3.6.1.2.1.4.24.4)
            for error_indication, error_status, error_index, var_binds in bulkCmd(
                self.snmp_engine, community_data, transport, ContextData(),
                0, 25,
                ObjectType(ObjectIdentity('IP-FORWARD-MIB', 'ipCidrRouteEntry'))
            ):
                if error_indication:
                    logger.debug(f"ipCidrRouteTable walk failed, trying ipRouteTable")
                    break
                
                for name, val in var_binds:
                    oid_str = name.prettyPrint()
                    # Parse OID to extract destination, mask, protocol, metric
                    # Simplified parsing for Phase 0
                    pass
            
            # Fallback to ipRouteTable
            if not routes:
                routes = self._get_routes_legacy(target_ip, community, version)
            
            return routes
        
        except Exception as e:
            logger.warning(f"Failed to get routes from {target_ip}: {str(e)}")
            return []
    
    def _get_routes_legacy(self, target_ip: str, community: str, version: str) -> List[RouteEntry]:
        """Fallback method to get routes from ipRouteTable."""
        routes = []
        try:
            transport = self._create_transport_target(target_ip)
            community_data = self._create_community_data(community, version)
            
            route_data = {}
            
            for error_indication, error_status, error_index, var_binds in bulkCmd(
                self.snmp_engine, community_data, transport, ContextData(),
                0, 25,
                ObjectType(ObjectIdentity('IP-MIB', 'ipRouteTable'))
            ):
                if error_indication:
                    break
                
                for name, val in var_binds:
                    oid_str = name.prettyPrint()
                    oid_parts = oid_str.split('.')
                    
                    # OID format: 1.3.6.1.2.1.4.21.1.<col>.<dest_ip>
                    if len(oid_parts) >= 15:
                        dest_ip = '.'.join(oid_parts[-4:])
                        col = int(oid_parts[-5])
                        
                        if dest_ip not in route_data:
                            route_data[dest_ip] = {}
                        
                        # Column mapping: 1=dest, 2=ifIndex, 3=metric1, 7=nextHop, 9=protocol, 11=netMask
                        if col == 11:  # netMask
                            route_data[dest_ip]['netmask'] = str(val)
                        elif col == 7:  # nextHop
                            route_data[dest_ip]['next_hop'] = str(val)
                        elif col == 9:  # protocol
                            route_data[dest_ip]['protocol'] = str(val)
                        elif col == 3:  # metric
                            route_data[dest_ip]['metric'] = int(val)
            
            # Convert to RouteEntry objects
            for dest_ip, data in route_data.items():
                route = RouteEntry(
                    destination_ip=dest_ip,
                    netmask=data.get('netmask', '255.255.255.0'),
                    next_hop=data.get('next_hop'),
                    protocol=data.get('protocol')
                )
                routes.append(route)
            
            return routes
        
        except Exception as e:
            logger.debug(f"Legacy route fetch failed: {str(e)}")
            return []
