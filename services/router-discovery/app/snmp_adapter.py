from dataclasses import dataclass
from typing import Optional, List
import logging
from ipaddress import IPv4Address, IPv4Network
from pysnmp.hlapi import (
    getCmd, bulkCmd, nextCmd, SnmpEngine, CommunityData, UdpTransportTarget,
    ContextData, ObjectType, ObjectIdentity, usmHMACMD5AuthProtocol,
    usmDESPrivProtocol, UsmUserData
)

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
    """Thin wrapper around SNMP operations using raw OIDs (no MIB compilation needed)."""
    
    def __init__(self, timeout: int = 5, retries: int = 2):
        self.timeout = timeout
        self.retries = retries
        self.snmp_engine = SnmpEngine()
    
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
    
    def _is_valid_interface_ip(self, ip_str: str) -> bool:
        """Check if IP is a valid interface address (not network/broadcast/special)."""
        try:
            ip = IPv4Address(ip_str)
            
            if ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_reserved:
                return False
            if ip_str in ['0.0.0.0', '255.255.255.255']:
                return False
            
            return True
        except ValueError:
            return False
    
    def get_system_info(self, target_ip: str, community: str, version: str) -> SystemInfo:
        """
        Query system information (hostname, description, object ID).
        OIDs: sysName=1.3.6.1.2.1.1.5.0, sysDescr=1.3.6.1.2.1.1.1.0, sysObjectID=1.3.6.1.2.1.1.2.0
        """
        try:
            transport = self._create_transport_target(target_ip)
            community_data = self._create_community_data(community, version)
            
            hostname = None
            sys_descr = None
            sys_object_id = None
            
            for error_indication, error_status, error_index, var_binds in getCmd(
                self.snmp_engine, community_data, transport, ContextData(),
                ObjectType(ObjectIdentity('1.3.6.1.2.1.1.1.0')),
                ObjectType(ObjectIdentity('1.3.6.1.2.1.1.5.0')),
                ObjectType(ObjectIdentity('1.3.6.1.2.1.1.2.0'))
            ):
                if error_indication:
                    logger.warning(f"SNMP system info query failed: {error_indication}")
                else:
                    for name, val in var_binds:
                        oid_str = str(name.prettyPrint())
                        if '1.3.6.1.2.1.1.1.0' in oid_str:
                            sys_descr = str(val)
                        elif '1.3.6.1.2.1.1.5.0' in oid_str:
                            hostname = str(val)
                        elif '1.3.6.1.2.1.1.2.0' in oid_str:
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
                ObjectType(ObjectIdentity('1.3.6.1.2.1.4.1.0'))
            ):
                if error_indication:
                    logger.debug(f"IP forwarding query unavailable on {target_ip}")
                    return None
                else:
                    for name, val in var_binds:
                        try:
                            val_int = int(val)
                            return val_int == 1
                        except (ValueError, TypeError):
                            return None
            
            return None
        
        except Exception as e:
            logger.debug(f"Failed to get IP forwarding from {target_ip}: {str(e)}")
            return None
    
    def get_interfaces_and_addresses(self, target_ip: str, community: str, version: str) -> List[InterfaceAddress]:
        """
        Query interface IP addresses and netmasks.
        Walks the IP address table (RFC 1213) using OID 1.3.6.1.2.1.4.20.1
        """
        addresses = []
        try:
            transport = self._create_transport_target(target_ip)
            community_data = self._create_community_data(community, version)
            
            address_data = {}
            walk_count = 0
            for error_indication, error_status, error_index, var_binds in bulkCmd(
                self.snmp_engine, community_data, transport, ContextData(),
                0, 25,
                ObjectType(ObjectIdentity('1.3.6.1.2.1.4.20.1'))
            ):
                if error_indication:
                    logger.warning(f"SNMP ipAddrTable walk failed: {error_indication}")
                    break
                
                for name, val in var_binds:
                    walk_count += 1
                    oid_str = str(name)
                    oid_parts = oid_str.split('.')
                    if len(oid_parts) >= 14:
                        try:
                            col = int(oid_parts[-5])
                            if col not in [1, 3]:
                                continue
                            ip = '.'.join(oid_parts[-4:])
                            
                            if not self._is_valid_interface_ip(ip):
                                continue
                            
                            octets = [int(o) for o in ip.split('.')]
                            if all(0 <= o <= 255 for o in octets):
                                if ip not in address_data:
                                    address_data[ip] = {}
                                if col == 1:
                                    address_data[ip]['ip'] = ip
                                elif col == 3:
                                    netmask_str = str(val).strip()
                                    if netmask_str:
                                        try:
                                            IPv4Address(netmask_str)
                                            address_data[ip]['netmask'] = netmask_str
                                        except ValueError:
                                            pass
                        except (ValueError, IndexError):
                            pass
            
            for ip, data in address_data.items():
                netmask = data.get('netmask', '255.255.255.0')
                if not netmask or str(netmask).strip() == '':
                    netmask = '255.255.255.0'
                addresses.append(InterfaceAddress(ip=ip, netmask=netmask))
            
            logger.info(f"ipAddrTable walk from {target_ip}: received {walk_count} entries, found {len(address_data)} unique IPs, {len(addresses)} valid addresses")
            return addresses
        
        except Exception as e:
            logger.warning(f"Failed to get interfaces from {target_ip}: {str(e)}")
            return []
    
    def get_routing_entries(self, target_ip: str, community: str, version: str) -> List[RouteEntry]:
        """
        Query routing table entries from ipRouteTable (OID 1.3.6.1.2.1.4.21.1).
        """
        routes = []
        try:
            transport = self._create_transport_target(target_ip)
            community_data = self._create_community_data(community, version)
            
            walk_count = 0
            for error_indication, error_status, error_index, var_binds in nextCmd(
                self.snmp_engine,
                community_data,
                transport,
                ContextData(),
                ObjectType(ObjectIdentity('1.3.6.1.2.1.4.21.1.1')),
                ObjectType(ObjectIdentity('1.3.6.1.2.1.4.21.1.7')),
                ObjectType(ObjectIdentity('1.3.6.1.2.1.4.21.1.9')),
                ObjectType(ObjectIdentity('1.3.6.1.2.1.4.21.1.11')),
                lexicographicMode=False
            ):
                if error_indication:
                    logger.warning(f"ipRouteTable walk failed: {error_indication}")
                    break
                if error_status:
                    logger.warning(
                        f"ipRouteTable walk error at {error_index}: {error_status.prettyPrint()}"
                    )
                    break
                if len(var_binds) < 4:
                    continue
                walk_count += 1
                dest_raw = var_binds[0][1].prettyPrint().strip()
                mask_raw = var_binds[3][1].prettyPrint().strip()
                next_hop_raw = var_binds[1][1].prettyPrint().strip()
                proto_raw = str(var_binds[2][1]).strip()
                try:
                    IPv4Address(dest_raw)
                except ValueError:
                    logger.debug(
                        "Skipping route row due to invalid destination",
                        extra={
                            "dest_raw": dest_raw,
                            "mask_raw": mask_raw,
                            "next_hop_raw": next_hop_raw,
                            "proto_raw": proto_raw,
                        },
                    )
                    continue
                try:
                    mask_val = str(IPv4Address(mask_raw))
                except ValueError:
                    logger.debug(
                        "Using fallback mask for route row",
                        extra={
                            "dest_raw": dest_raw,
                            "mask_raw": mask_raw,
                            "next_hop_raw": next_hop_raw,
                            "proto_raw": proto_raw,
                        },
                    )
                    mask_val = '255.255.255.0'
                next_hop_val = None
                if next_hop_raw and next_hop_raw != '0.0.0.0':
                    try:
                        next_hop_val = str(IPv4Address(next_hop_raw))
                    except ValueError:
                        logger.debug(
                            "Dropping non-IP next hop",
                            extra={
                                "dest_raw": dest_raw,
                                "mask_raw": mask_raw,
                                "next_hop_raw": next_hop_raw,
                                "proto_raw": proto_raw,
                            },
                        )
                        next_hop_val = None
                logger.debug(
                    "Parsed route row",
                    extra={
                        "dest_raw": dest_raw,
                        "mask_raw": mask_raw,
                        "next_hop_raw": next_hop_raw,
                        "proto_raw": proto_raw,
                        "dest": dest_raw,
                        "mask": mask_val,
                        "next_hop": next_hop_val,
                    },
                )
                routes.append(
                    RouteEntry(
                        destination_ip=dest_raw,
                        netmask=mask_val,
                        next_hop=next_hop_val,
                        protocol=proto_raw if proto_raw else None
                    )
                )
            logger.info(
                f"ipRouteTable walk from {target_ip}: processed {walk_count} rows, returned {len(routes)} routes"
            )
            return routes
        
        except Exception as e:
            logger.warning(f"Failed to get routes from {target_ip}: {str(e)}")
            return []
