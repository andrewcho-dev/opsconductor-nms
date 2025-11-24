import os
import re
import asyncio
import ipaddress
from datetime import datetime, timezone
from typing import Dict, List, Optional, Set
from pysnmp.hlapi.asyncio import (
    walkCmd, SnmpEngine, CommunityData, UdpTransportTarget, ContextData,
    ObjectType, ObjectIdentity
)
import httpx


STATE_SERVER_URL = os.getenv("STATE_SERVER_URL", "http://state-server:8080")
GATEWAY_IP = os.getenv("GATEWAY_IP", "")
SNMP_COMMUNITY = os.getenv("SNMP_COMMUNITY", "public")
SNMP_TIMEOUT = float(os.getenv("SNMP_TIMEOUT", "2.0"))
SNMP_RETRIES = int(os.getenv("SNMP_RETRIES", "1"))
DISCOVERY_INTERVAL_SECONDS = int(os.getenv("DISCOVERY_INTERVAL_SECONDS", "1800"))
HEALTH_PORT = int(os.getenv("HEALTH_PORT", "9700"))


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def normalize_ip_address(value) -> str:
    """Convert SNMP IP address value to dotted decimal format."""
    try:
        print(f"[DEBUG] normalize_ip_address called with type={type(value).__name__}, value={repr(value)[:100]}, hasattr asNumbers={hasattr(value, 'asNumbers')}", flush=True)
        
        if isinstance(value, str) and re.match(r'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$', value):
            return value
        
        if hasattr(value, 'asNumbers'):
            octets = list(value.asNumbers())
            if len(octets) == 4:
                return '.'.join(str(octet) for octet in octets)
        
        if isinstance(value, str):
            byte_values = [ord(c) for c in value]
            if len(byte_values) == 4:
                return '.'.join(str(b) for b in byte_values)
        
        return str(value)
    except Exception as e:
        print(f"[DEBUG] Failed to normalize IP address: {e}", flush=True)
        return str(value)

async def query_routing_table(ip: str, version: str = "2c") -> List[Dict]:
    print(f"\n╔═══════════════════════════════════════════════════════════╗")
    print(f"║  Querying routing table from gateway: {ip:15s}    ║")
    print(f"╚═══════════════════════════════════════════════════════════╝\n")
    
    routing_table = []
    mpModel = 1 if version == "2c" else 0
    
    try:
        snmpEngine = SnmpEngine()
        
        route_count = 0
        async for errorIndication, errorStatus, errorIndex, varBinds in walkCmd(
            snmpEngine,
            CommunityData(SNMP_COMMUNITY, mpModel=mpModel),
            UdpTransportTarget((ip, 161), timeout=SNMP_TIMEOUT, retries=SNMP_RETRIES),
            ContextData(),
            ObjectType(ObjectIdentity("1.3.6.1.2.1.4.21.1.1")),
            ObjectType(ObjectIdentity("1.3.6.1.2.1.4.21.1.7")),
            ObjectType(ObjectIdentity("1.3.6.1.2.1.4.21.1.11")),
            ObjectType(ObjectIdentity("1.3.6.1.2.1.4.21.1.2"))
        ):
            if errorIndication or errorStatus:
                break
            
            if len(varBinds) >= 4:
                oid_str = str(varBinds[0][0])
                
                if not oid_str.startswith('1.3.6.1.2.1.4.21.1'):
                    break
                
                oid_parts = oid_str.split('.')
                dest = '.'.join(oid_parts[-4:])
                
                next_hop = normalize_ip_address(varBinds[1][1])
                mask = normalize_ip_address(varBinds[2][1])
                if_index = str(varBinds[3][1])
                
                route_count += 1
                
                routing_table.append({
                    "destination": dest,
                    "mask": mask,
                    "next_hop": next_hop,
                    "interface": if_index
                })
                
                if route_count == 1:
                    print(f"[DEBUG] First route: dest={dest}, mask={mask}, next_hop={next_hop}, table_len={len(routing_table)}", flush=True)
                
                if route_count % 10 == 0:
                    print(f"  ├─ Retrieved {route_count} routes... (table size: {len(routing_table)})", flush=True)
        
        snmpEngine.closeDispatcher()
        
        print(f"  └─ ✓ Total routes retrieved: {len(routing_table)}\n")
        
        return routing_table
        
    except Exception as e:
        print(f"  └─ ✗ Error querying routing table: {e}\n", flush=True)
        try:
            snmpEngine.closeDispatcher()
        except:
            pass
        return []


def parse_networks_from_routing_table(routing_table: List[Dict]) -> List[Dict]:
    print(f"╔═══════════════════════════════════════════════════════════╗")
    print(f"║  Parsing networks from routing table                     ║")
    print(f"╚═══════════════════════════════════════════════════════════╝\n")
    
    print(f"DEBUG: Total routes to process: {len(routing_table)}")
    if routing_table:
        print(f"DEBUG: Sample routes (first 3):")
        for idx, route in enumerate(routing_table[:3]):
            print(f"  Route {idx}: dest={route.get('destination')}, mask={route.get('mask')}, next_hop={route.get('next_hop')}")

    networks = []
    seen_networks = set()
    
    for route in routing_table:
        dest = route.get("destination", "")
        mask = route.get("mask", "")
        next_hop = route.get("next_hop", "")
        
        if dest == "0.0.0.0":
            continue
        
        try:
            network = ipaddress.IPv4Network(f"{dest}/{mask}", strict=False)
            network_str = str(network.with_prefixlen)
            
            if network.is_private and network_str not in seen_networks:
                seen_networks.add(network_str)
                is_directly_connected = (next_hop == "0.0.0.0" or next_hop == dest)
                
                networks.append({
                    "network": network_str,
                    "destination": dest,
                    "netmask": mask,
                    "next_hop": next_hop,
                    "prefix_len": network.prefixlen,
                    "num_addresses": network.num_addresses,
                    "directly_connected": is_directly_connected,
                    "discovered_at": now_iso()
                })
                
                status = "DIRECTLY CONNECTED" if is_directly_connected else f"via {next_hop}"
                print(f"  ├─ 🌐 {network_str:20s} [{status}]", flush=True)
        
        except (ValueError, ipaddress.AddressValueError) as e:
            continue
    
    print(f"\n  └─ ✓ Discovered {len(networks)} unique private networks\n")
    
    return networks


async def store_discovered_networks(client: httpx.AsyncClient, networks: List[Dict]):
    print(f"╔═══════════════════════════════════════════════════════════╗")
    print(f"║  Storing discovered networks                             ║")
    print(f"╚═══════════════════════════════════════════════════════════╝\n")
    
    try:
        payload = {
            "discovered_networks": networks,
            "last_discovery": now_iso(),
            "gateway_ip": GATEWAY_IP
        }
        
        resp = await client.post(
            f"{STATE_SERVER_URL}/api/networks/discovered",
            json=payload,
            timeout=10.0
        )
        
        if resp.status_code < 300:
            print(f"  └─ ✓ Successfully stored {len(networks)} networks\n")
        else:
            print(f"  └─ ✗ Failed to store networks: HTTP {resp.status_code}\n", flush=True)
    
    except Exception as e:
        print(f"  └─ ✗ Error storing networks: {e}\n", flush=True)


async def generate_scan_targets(networks: List[Dict]) -> List[str]:
    print(f"╔═══════════════════════════════════════════════════════════╗")
    print(f"║  Networks queued for detailed scanning                   ║")
    print(f"╚═══════════════════════════════════════════════════════════╝\n")
    
    for network in networks:
        net_str = network["network"]
        num_hosts = network["num_addresses"]
        status = "DIRECT" if network["directly_connected"] else "ROUTED"
        print(f"  ├─ 📊 {net_str:20s} ({num_hosts:,} addresses) [{status}]", flush=True)
    
    print(f"\n  └─ ✓ {len(networks)} networks ready for scanning\n")
    
    return [n["network"] for n in networks]


async def health_server():
    from aiohttp import web
    
    async def handle_health(_):
        return web.json_response({
            "status": "ok",
            "service": "network-discovery",
            "gateway_ip": GATEWAY_IP,
            "discovery_interval": DISCOVERY_INTERVAL_SECONDS,
            "timestamp": now_iso()
        })
    
    app = web.Application()
    app.router.add_get("/health", handle_health)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", HEALTH_PORT)
    await site.start()
    print(f"[NETWORK-DISCOVERY] Health check server started on port {HEALTH_PORT}", flush=True)


async def discovery_loop():
    print("[NETWORK-DISCOVERY] DISABLED - Discovery service is disabled. Exiting.", flush=True)
    return


async def main():
    await asyncio.gather(
        health_server(),
        discovery_loop()
    )


if __name__ == "__main__":
    asyncio.run(main())
