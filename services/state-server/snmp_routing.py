"""SNMP routing table fetcher - Standards-compliant implementation."""
import asyncio
from dataclasses import dataclass
from typing import List, Optional, Dict, Any
from ipaddress import IPv4Address
from pysnmp.hlapi.v1arch.asyncio import (
    walk_cmd, SnmpDispatcher, CommunityData, UdpTransportTarget,
    ObjectType, ObjectIdentity
)

VALID_INET_TYPES = {0, 1, 2, 3, 4, 16}

PROTO_MAP = {
    2: "local",
    3: "netmgmt",
    4: "icmp",
    5: "egp",
    6: "ggp",
    7: "hello",
    8: "rip",
    9: "is-is",
    10: "es-is",
    11: "ciscoIgrp",
    12: "bbnSpfIgp",
    13: "ospf",
    14: "bgp",
}


@dataclass
class RouteEntry:
    destination_ip: str
    netmask: str
    next_hop: Optional[str] = None
    protocol: Optional[str] = None


@dataclass
class RouteRecord:
    destination: str
    prefix_length: int
    next_hop: Optional[str]
    out_if_index: Optional[int]
    protocol: Optional[str]
    metric: Optional[int]
    source: str = "inetCidrRouteTable"


def mask_to_prefix(mask_str: str) -> int:
    """Convert netmask string to prefix length."""
    try:
        octets = [int(x) for x in mask_str.split(".")]
        bits = "".join(f"{o:08b}" for o in octets)
        return bits.count("1")
    except:
        return 24


def prefix_to_mask(prefix_len: int) -> str:
    """Convert prefix length to netmask string."""
    if prefix_len == 0:
        return '0.0.0.0'
    mask_bits = ['1'] * prefix_len + ['0'] * (32 - prefix_len)
    octets = [int(''.join(mask_bits[i:i+8]), 2) for i in range(0, 32, 8)]
    return '.'.join(map(str, octets))


def inet_address_to_string(addr_type: int, octets: List[int]) -> Optional[str]:
    """
    Convert InetAddressType + octets to a human-readable string.

    - For addr_type in {1,3}: treat as IPv4 (or IPv4z, but IPv4 is first 4 bytes)
    - For addr_type in {2,4}: treat as IPv6 (or IPv6z)
    - For addr_type 0 or empty octets: return None (no address)
    - For addr_type 16 (dns) and others: return None (not needed for routing)
    """
    if addr_type == 0 or not octets:
        return None

    if addr_type in (1, 3):
        if len(octets) < 4:
            return None
        return ".".join(str(b) for b in octets[:4])

    if addr_type in (2, 4):
        if len(octets) < 16:
            return None
        groups = []
        for i in range(0, 16, 2):
            group = (octets[i] << 8) | octets[i + 1]
            groups.append(f"{group:x}")
        return ":".join(groups)

    return None


def parse_inet_cidr_index(index_suffix: List[int]) -> Dict[str, Any]:
    """
    Decode inetCidrRouteTable index to structured fields.

    inetCidrRoute INDEX is:
      { destType, dest, pfxLen, policy, nextHopType, nextHop }

    Encoding in OID (simplified):

      destType . destLen . destOctets... . prefixLen .
      policyArcs... . nextHopType . nextHopLen . nextHopOctets...

    Returns a dict with:
      - dest_type: int
      - dest_octets: List[int]
      - prefix_len: int
      - next_type: int
      - next_octets: List[int]
    """
    s = index_suffix
    if len(s) < 4:
        raise ValueError(f"Index too short to be inetCidrRoute index: {s}")

    pos = 0

    dest_type = s[pos]
    pos += 1
    dest_len = s[pos]
    pos += 1

    if dest_len < 0 or pos + dest_len > len(s):
        raise ValueError(f"Invalid dest_len in inetCidr index: {dest_len}, {s}")

    dest_octets = s[pos:pos + dest_len]
    pos += dest_len

    if pos >= len(s):
        raise ValueError(f"Missing prefix_len in inetCidr index: {s}")
    prefix_len = s[pos]
    pos += 1

    rest = s[pos:]
    if len(rest) < 2:
        raise ValueError(f"Too short for policy/nextHop in inetCidr index: {s}")

    policy_arcs: List[int] = []
    next_type: int = 0
    next_len: int = 0
    next_octets: List[int] = []

    found = False

    for start in range(0, len(rest) - 1):
        T = rest[start]
        N = rest[start + 1]
        end = start + 2 + N

        if end != len(rest):
            continue

        if T not in VALID_INET_TYPES:
            continue

        if T in (1, 3) and N not in (0, 4, 8):
            continue
        if T in (2, 4) and N not in (0, 16, 20):
            continue

        policy_arcs = rest[0:start]
        next_type = T
        next_len = N
        next_octets = rest[start + 2:end]
        found = True
        break

    if not found:
        raise ValueError(f"Cannot locate nextHopType boundary in inetCidr index: {s}")

    return {
        "dest_type": dest_type,
        "dest_octets": dest_octets,
        "prefix_len": prefix_len,
        "next_type": next_type,
        "next_octets": next_octets,
        "policy_arcs": policy_arcs,
    }


async def walk_column(snmp_dispatcher, community_data, transport, base_oid: tuple) -> Dict[tuple, Any]:
    """
    Walk a single SNMP column and return a mapping:
      index_suffix_tuple -> value
    
    Adapted for pysnmp.hlapi.v1arch.asyncio
    """
    result: Dict[tuple, Any] = {}
    base_oid_str = ".".join(str(x) for x in base_oid)
    done = False
    
    async for error_indication, error_status, error_index, var_binds in walk_cmd(
        snmp_dispatcher,
        community_data,
        transport,
        ObjectType(ObjectIdentity(base_oid_str)),
    ):
        if error_indication or error_status or done:
            break
        
        for var_bind in var_binds:
            oid, value = var_bind
            oid_str = str(oid)
            
            if not oid_str.startswith(base_oid_str):
                done = True
                break
            
            index_suffix_str = oid_str[len(base_oid_str)+1:]
            if not index_suffix_str:
                continue
                
            index_suffix = tuple(int(x) for x in index_suffix_str.split('.'))
            result[index_suffix] = value
    
    return result


OID_INETCIDR_IFINDEX = (1, 3, 6, 1, 2, 1, 4, 24, 7, 1, 7)
OID_INETCIDR_TYPE = (1, 3, 6, 1, 2, 1, 4, 24, 7, 1, 8)
OID_INETCIDR_PROTO = (1, 3, 6, 1, 2, 1, 4, 24, 7, 1, 9)
OID_INETCIDR_METRIC1 = (1, 3, 6, 1, 2, 1, 4, 24, 7, 1, 12)


async def fetch_inet_cidr_routes(snmp_dispatcher, community_data, transport) -> List[RouteRecord]:
    """
    Fetch routing table from inetCidrRouteTable using the reference implementation.
    
    This follows the reference parsing semantics exactly.
    """
    ifindex_map = await walk_column(snmp_dispatcher, community_data, transport, OID_INETCIDR_IFINDEX)
    type_map = await walk_column(snmp_dispatcher, community_data, transport, OID_INETCIDR_TYPE)
    proto_map = await walk_column(snmp_dispatcher, community_data, transport, OID_INETCIDR_PROTO)
    metric_map = await walk_column(snmp_dispatcher, community_data, transport, OID_INETCIDR_METRIC1)
    
    routes: List[RouteRecord] = []
    
    for index_suffix, ifindex_value in ifindex_map.items():
        index_list = list(index_suffix)
        
        try:
            idx = parse_inet_cidr_index(index_list)
        except ValueError as e:
            print(f"[inetCidrRoute] skip row index={index_list}: {e}")
            continue
        
        dest_addr = inet_address_to_string(idx["dest_type"], idx["dest_octets"])
        prefix_len = idx["prefix_len"]
        next_hop_addr = inet_address_to_string(idx["next_type"], idx["next_octets"])
        
        if dest_addr is None:
            continue
        if prefix_len < 0 or prefix_len > 128:
            continue
        
        route_type_val = type_map.get(index_suffix, None)
        proto_val = proto_map.get(index_suffix, None)
        metric_val = metric_map.get(index_suffix, None)
        
        proto_str = None
        if isinstance(proto_val, int):
            proto_str = PROTO_MAP.get(proto_val, None)
        
        out_if_index = int(ifindex_value) if ifindex_value is not None else None
        
        record = RouteRecord(
            destination=dest_addr,
            prefix_length=int(prefix_len),
            next_hop=next_hop_addr,
            out_if_index=out_if_index,
            protocol=proto_str,
            metric=int(metric_val) if isinstance(metric_val, int) else None,
            source="inetCidrRouteTable",
        )
        routes.append(record)
    
    return routes


async def try_inet_cidr_route_table(snmp_dispatcher, community_data, transport):
    """Try inetCidrRouteTable (modern, IP-version neutral) - OID: 1.3.6.1.2.1.4.24.7"""
    print(f"Trying inetCidrRouteTable...")
    
    columns = {
        '7': 'ifIndex',
        '8': 'type',
        '9': 'proto',
        '12': 'metric1'
    }
    
    route_rows = {}
    base_oid = '1.3.6.1.2.1.4.24.7.1'
    
    for col_num in columns.keys():
        col_oid = f"{base_oid}.{col_num}"
        count = 0
        done = False
        
        async for error_indication, error_status, error_index, var_binds in walk_cmd(
            snmp_dispatcher,
            community_data,
            transport,
            ObjectType(ObjectIdentity(col_oid)),
        ):
            if error_indication or error_status or done:
                break
            
            for var_bind in var_binds:
                oid, value = var_bind
                oid_str = str(oid)
                
                if not oid_str.startswith(col_oid):
                    done = True
                    break
                
                count += 1
                
                try:
                    index_suffix_str = oid_str[len(col_oid)+1:]
                    index_suffix = [int(x) for x in index_suffix_str.split('.')]
                    
                    parsed_idx = parse_inet_cidr_index(index_suffix)
                    
                    destination_ip = inet_address_to_string(parsed_idx["dest_type"], parsed_idx["dest_octets"])
                    next_hop_ip = inet_address_to_string(parsed_idx["next_type"], parsed_idx["next_octets"])
                    prefix_len = parsed_idx["prefix_len"]
                    
                    if destination_ip is None:
                        continue
                    
                    row_key = f"{parsed_idx['dest_type']}:{destination_ip}/{prefix_len}:{parsed_idx['next_type']}:{next_hop_ip if next_hop_ip else 'None'}"
                    
                    if row_key not in route_rows:
                        route_rows[row_key] = {
                            'destination': destination_ip,
                            'prefixLength': prefix_len,
                            'nextHop': next_hop_ip if next_hop_ip and next_hop_ip not in ['0.0.0.0', '::'] else None,
                            'source': 'inetCidrRouteTable'
                        }
                    
                    if col_num == '7':
                        route_rows[row_key]['ifIndex'] = int(value)
                    elif col_num == '9':
                        try:
                            proto_int = int(value)
                            route_rows[row_key]['protocol'] = PROTO_MAP.get(proto_int, str(proto_int))
                        except (ValueError, TypeError):
                            route_rows[row_key]['protocol'] = str(value)
                    elif col_num == '12':
                        route_rows[row_key]['metric'] = int(value)
                        
                except Exception as e:
                    pass
        
        if count > 0:
            print(f"  Column {col_num} ({columns[col_num]}): {count} entries")
    
    if len(route_rows) > 0:
        print(f"  inetCidrRouteTable: Found {len(route_rows)} routes")
        return route_rows
    
    print(f"  inetCidrRouteTable: No routes found")
    return None


async def try_ip_cidr_route_table(snmp_dispatcher, community_data, transport):
    """Try ipCidrRouteTable (IPv4 + CIDR) - OID: 1.3.6.1.2.1.4.24.4"""
    print(f"Trying ipCidrRouteTable...")
    
    columns = {
        '1': 'dest',
        '2': 'mask',
        '4': 'nextHop',
        '5': 'ifIndex',
        '7': 'proto',
        '11': 'metric1'
    }
    
    route_rows = {}
    base_oid = '1.3.6.1.2.1.4.24.4.1'
    
    for col_num in columns.keys():
        col_oid = f"{base_oid}.{col_num}"
        count = 0
        done = False
        
        async for error_indication, error_status, error_index, var_binds in walk_cmd(
            snmp_dispatcher,
            community_data,
            transport,
            ObjectType(ObjectIdentity(col_oid)),
        ):
            if error_indication or error_status or done:
                break
            
            for var_bind in var_binds:
                oid, value = var_bind
                oid_str = str(oid)
                
                if not oid_str.startswith(col_oid):
                    done = True
                    break
                
                count += 1
                
                try:
                    index_suffix = oid_str[len(col_oid)+1:]
                    
                    if index_suffix not in route_rows:
                        route_rows[index_suffix] = {'source': 'ipCidrRouteTable'}
                    
                    if col_num == '1':
                        route_rows[index_suffix]['destination'] = str(value)
                    elif col_num == '2':
                        route_rows[index_suffix]['mask'] = str(value)
                    elif col_num == '4':
                        nh = str(value)
                        route_rows[index_suffix]['nextHop'] = nh if nh != '0.0.0.0' else None
                    elif col_num == '5':
                        route_rows[index_suffix]['ifIndex'] = int(value)
                    elif col_num == '7':
                        route_rows[index_suffix]['protocol'] = str(value)
                    elif col_num == '11':
                        route_rows[index_suffix]['metric'] = int(value)
                        
                except Exception as e:
                    pass
        
        if count > 0:
            print(f"  Column {col_num} ({columns[col_num]}): {count} entries")
    
    complete_routes = {}
    for idx, route in route_rows.items():
        if 'destination' in route and 'mask' in route:
            prefix_len = mask_to_prefix(route['mask'])
            complete_routes[idx] = {
                'destination': route['destination'],
                'prefixLength': prefix_len,
                'mask': route['mask'],
                'nextHop': route.get('nextHop'),
                'ifIndex': route.get('ifIndex'),
                'protocol': route.get('protocol'),
                'metric': route.get('metric'),
                'source': 'ipCidrRouteTable'
            }
    
    if len(complete_routes) > 0:
        print(f"  ipCidrRouteTable: Found {len(complete_routes)} routes")
        return complete_routes
    
    print(f"  ipCidrRouteTable: No routes found")
    return None


async def try_ip_route_table(snmp_dispatcher, community_data, transport):
    """Try ipRouteTable (old MIB-II IPv4 routes) - OID: 1.3.6.1.2.1.4.21.1"""
    print(f"Trying ipRouteTable...")
    
    columns = {
        '1': 'dest',
        '2': 'ifIndex',
        '3': 'metric1',
        '7': 'nextHop',
        '8': 'type',
        '9': 'proto',
        '11': 'mask'
    }
    
    route_rows = {}
    base_oid = '1.3.6.1.2.1.4.21.1'
    
    for col_num in columns.keys():
        col_oid = f"{base_oid}.{col_num}"
        count = 0
        done = False
        
        async for error_indication, error_status, error_index, var_binds in walk_cmd(
            snmp_dispatcher,
            community_data,
            transport,
            ObjectType(ObjectIdentity(col_oid)),
        ):
            if error_indication or error_status or done:
                break
            
            for var_bind in var_binds:
                oid, value = var_bind
                oid_str = str(oid)
                
                if not oid_str.startswith(col_oid):
                    done = True
                    break
                
                count += 1
                
                try:
                    index_suffix = oid_str[len(col_oid)+1:]
                    
                    if index_suffix not in route_rows:
                        route_rows[index_suffix] = {'source': 'ipRouteTable'}
                    
                    if col_num == '1':
                        route_rows[index_suffix]['destination'] = str(value)
                    elif col_num == '2':
                        route_rows[index_suffix]['ifIndex'] = int(value)
                    elif col_num == '3':
                        route_rows[index_suffix]['metric'] = int(value)
                    elif col_num == '7':
                        nh = str(value)
                        route_rows[index_suffix]['nextHop'] = nh if nh != '0.0.0.0' else None
                    elif col_num == '9':
                        route_rows[index_suffix]['protocol'] = str(value)
                    elif col_num == '11':
                        route_rows[index_suffix]['mask'] = str(value)
                        
                except Exception as e:
                    pass
        
        if count > 0:
            print(f"  Column {col_num} ({columns[col_num]}): {count} entries")
    
    complete_routes = {}
    for idx, route in route_rows.items():
        if 'destination' in route and 'mask' in route:
            prefix_len = mask_to_prefix(route['mask'])
            complete_routes[idx] = {
                'destination': route['destination'],
                'prefixLength': prefix_len,
                'mask': route['mask'],
                'nextHop': route.get('nextHop'),
                'ifIndex': route.get('ifIndex'),
                'protocol': route.get('protocol'),
                'metric': route.get('metric'),
                'source': 'ipRouteTable'
            }
    
    if len(complete_routes) > 0:
        print(f"  ipRouteTable: Found {len(complete_routes)} routes")
        return complete_routes
    
    print(f"  ipRouteTable: No routes found")
    return None


async def get_routing_entries_async(target_ip: str, community: str, version: str) -> List[RouteEntry]:
    """Query routing table - tries tables in standard order."""
    routes = []
    try:
        if version != "2c":
            raise ValueError(f"Unsupported SNMP version: {version}")
        
        snmp_dispatcher = SnmpDispatcher()
        community_data = CommunityData(community, mpModel=1)
        transport = await UdpTransportTarget.create((target_ip, 161), timeout=5.0, retries=3)
        
        print(f"Attempting inetCidrRouteTable using reference implementation...")
        route_records = await fetch_inet_cidr_routes(snmp_dispatcher, community_data, transport)

        # Current routing UI and downstream logic are IPv4-only. If inetCidrRouteTable
        # returns only IPv6 routes (common on some devices), treat that as "no usable
        # routes" so we can fall back to ipCidrRouteTable/ipRouteTable.
        ipv4_records: List[RouteRecord] = [
            r for r in (route_records or [])
            if ":" not in r.destination
        ]

        if ipv4_records:
            print(f"  Found {len(ipv4_records)} IPv4 routes from inetCidrRouteTable")
            for record in ipv4_records:
                mask = prefix_to_mask(record.prefix_length)
                routes.append(
                    RouteEntry(
                        destination_ip=record.destination,
                        netmask=mask,
                        next_hop=record.next_hop,
                        protocol=record.protocol
                    )
                )
        else:
            if route_records:
                print(f"  inetCidrRouteTable returned only non-IPv4 routes; trying fallback tables...")
            else:
                print(f"  No routes from inetCidrRouteTable, trying fallback tables...")
            route_data = None
            
            route_data = await try_ip_cidr_route_table(snmp_dispatcher, community_data, transport)
            
            if not route_data:
                route_data = await try_ip_route_table(snmp_dispatcher, community_data, transport)
            
            if not route_data:
                raise Exception(f"No routing table data found (tried inetCidrRouteTable, ipCidrRouteTable, ipRouteTable)")
            
            for route_key, route_info in route_data.items():
                if 'destination' not in route_info:
                    continue
                
                dest = route_info.get('destination', '')
                try:
                    IPv4Address(dest)
                except ValueError:
                    continue
                
                mask = route_info.get('mask')
                if not mask:
                    prefix_len = route_info.get('prefixLength', 32)
                    mask = prefix_to_mask(prefix_len)
                
                try:
                    mask = str(IPv4Address(mask))
                except ValueError:
                    mask = '255.255.255.255'
                
                nexthop_str = route_info.get('nextHop', '')
                nexthop = None
                if nexthop_str and nexthop_str != '0.0.0.0':
                    try:
                        nexthop = str(IPv4Address(nexthop_str))
                    except ValueError:
                        nexthop = None
                
                routes.append(
                    RouteEntry(
                        destination_ip=dest,
                        netmask=mask,
                        next_hop=nexthop,
                        protocol=route_info.get('protocol')
                    )
                )
        
        snmp_dispatcher.transport_dispatcher.close_dispatcher()
        return routes
    except Exception as e:
        raise Exception(f"Failed to get routes from {target_ip}: {str(e)}")


def get_routing_entries(target_ip: str, community: str, version: str) -> List[RouteEntry]:
    """Synchronous wrapper for async SNMP query."""
    return asyncio.run(get_routing_entries_async(target_ip, community, version))
