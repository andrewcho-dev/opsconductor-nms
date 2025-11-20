import os
import asyncio
import re
from datetime import datetime, timezone
from typing import Optional, Dict
from pysnmp.hlapi.asyncio import (
    getCmd, nextCmd, bulkCmd, walkCmd,
    SnmpEngine, CommunityData, UdpTransportTarget, ContextData,
    ObjectType, ObjectIdentity
)
import httpx


STATE_SERVER_URL = os.environ.get("STATE_SERVER_URL", "http://state-server:8080")
SNMP_COMMUNITY = os.environ.get("SNMP_COMMUNITY", "public")
SNMP_TIMEOUT = float(os.environ.get("SNMP_TIMEOUT", "1.0"))
SNMP_RETRIES = int(os.environ.get("SNMP_RETRIES", "0"))
SCAN_INTERVAL_SECONDS = int(os.environ.get("SCAN_INTERVAL_SECONDS", "300"))


async def fetch_inventory(client: httpx.AsyncClient) -> list:
    try:
        resp = await client.get(f"{STATE_SERVER_URL}/api/inventory", timeout=10.0)
        if resp.status_code == 200:
            return resp.json()
    except Exception as e:
        print(f"[SNMP] Failed to fetch inventory: {e}", flush=True)
    return []


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


def determine_network_role(snmp_data: Dict[str, str]) -> str:
    import ipaddress
    
    ip_forwarding_str = snmp_data.get("ipForwarding", "").strip()
    stp_enabled_str = snmp_data.get("stp_enabled", "0")
    
    try:
        stp_enabled = int(stp_enabled_str)
    except (ValueError, TypeError):
        stp_enabled = 0
    
    if ip_forwarding_str == "1":
        routing_table = snmp_data.get("routing_table", [])
        
        if routing_table:
            inter_subnet_routes = 0
            seen_networks = set()
            
            for route in routing_table:
                dest = route.get("destination", "")
                mask = route.get("mask", "")
                next_hop = route.get("next_hop", "")
                
                if dest == "0.0.0.0":
                    continue
                
                if next_hop == "0.0.0.0" or next_hop == dest:
                    continue
                
                try:
                    network = ipaddress.IPv4Network(f"{dest}/{mask}", strict=False)
                    network_str = str(network.with_prefixlen)
                    
                    if network_str not in seen_networks:
                        seen_networks.add(network_str)
                        inter_subnet_routes += 1
                except (ValueError, ipaddress.AddressValueError):
                    continue
            
            print(f"[SNMP] L3 Detection: ipForwarding={ip_forwarding_str}, total_routes={len(routing_table)}, inter_subnet_routes={inter_subnet_routes}", flush=True)
            
            if inter_subnet_routes > 0:
                return "L3"
    
    if stp_enabled > 0:
        return "L2"
    
    return "Endpoint"


def parse_vendor_model(sys_descr: str, sys_oid: str) -> tuple[Optional[str], Optional[str]]:
    vendor = None
    model = None
    
    descr_lower = sys_descr.lower()
    
    if "cisco" in descr_lower:
        vendor = "Cisco"
        if "catalyst" in descr_lower:
            model = "Catalyst"
        elif "nexus" in descr_lower:
            model = "Nexus"
        elif "asr" in descr_lower:
            model = "ASR"
        elif "isr" in descr_lower:
            model = "ISR"
    elif "juniper" in descr_lower or "junos" in descr_lower:
        vendor = "Juniper"
        if "mx" in descr_lower:
            model = "MX"
        elif "ex" in descr_lower:
            model = "EX"
        elif "srx" in descr_lower:
            model = "SRX"
    elif "arista" in descr_lower:
        vendor = "Arista"
    elif "dell" in descr_lower or "powerconnect" in descr_lower:
        vendor = "Dell"
    elif "hp" in descr_lower or "hewlett" in descr_lower:
        vendor = "HP"
    elif "microsoft" in descr_lower or "windows" in descr_lower:
        vendor = "Microsoft"
        model = "Windows"
    elif "eaton" in descr_lower or "ups" in descr_lower.lower():
        vendor = "Eaton"
        model = "UPS"
    elif "axis" in descr_lower:
        vendor = "Axis"
        model = "Camera"
    elif "tc communication" in descr_lower or "tc comm" in descr_lower:
        vendor = "TC Communication"
    elif "planet" in descr_lower:
        vendor = "Planet"
    
    return vendor, model


async def query_snmp(ip: str) -> Optional[tuple[Dict[str, str], str]]:
    for version, mpModel in [("2c", 1), ("1", 0)]:
        try:
            snmpEngine = SnmpEngine()
            
            oids = [
                ("sysDescr", "1.3.6.1.2.1.1.1.0"),
                ("sysObjectID", "1.3.6.1.2.1.1.2.0"),
                ("sysName", "1.3.6.1.2.1.1.5.0"),
                ("sysContact", "1.3.6.1.2.1.1.4.0"),
                ("sysLocation", "1.3.6.1.2.1.1.6.0"),
                ("sysServices", "1.3.6.1.2.1.1.7.0"),
                ("ipForwarding", "1.3.6.1.2.1.4.1.0"),
                ("stpProtocol", "1.3.6.1.2.1.17.2.1.0"),
            ]
            
            results = {}
            
            for name, oid in oids:
                try:
                    errorIndication, errorStatus, errorIndex, varBinds = await getCmd(
                        snmpEngine,
                        CommunityData(SNMP_COMMUNITY, mpModel=mpModel),
                        UdpTransportTarget((ip, 161), timeout=SNMP_TIMEOUT, retries=SNMP_RETRIES),
                        ContextData(),
                        ObjectType(ObjectIdentity(oid))
                    )
                    
                    if errorIndication:
                        continue
                    if errorStatus:
                        continue
                    
                    for varBind in varBinds:
                        value = str(varBind[1])
                        if value and value != "":
                            results[name] = value
                            
                except Exception:
                    continue
            
            if not results:
                snmpEngine.closeDispatcher()
                continue
            
            vendor, model = parse_vendor_model(results.get("sysDescr", ""), results.get("sysObjectID", ""))
            if vendor:
                results["vendor"] = vendor
            if model:
                results["model"] = model
            
            stp_protocol = results.get("stpProtocol", "")
            if stp_protocol and stp_protocol != "":
                results["stp_enabled"] = "1"
            else:
                results["stp_enabled"] = "0"
            
            route_count = 0
            try:
                walk_timeout = min(0.5, SNMP_TIMEOUT)
                async for errorIndication, errorStatus, errorIndex, varBinds in walkCmd(
                    snmpEngine,
                    CommunityData(SNMP_COMMUNITY, mpModel=mpModel),
                    UdpTransportTarget((ip, 161), timeout=walk_timeout, retries=0),
                    ContextData(),
                    ObjectType(ObjectIdentity("1.3.6.1.2.1.4.21.1.1"))
                ):
                    if not errorIndication and not errorStatus:
                        route_count += 1
                        if route_count > 3:
                            break
            except Exception:
                pass
            
            results["route_count"] = str(route_count)
            
            snmpEngine.closeDispatcher()
            return results, version
            
        except Exception:
            try:
                snmpEngine.closeDispatcher()
            except:
                pass
            continue
    
    return None


async def query_routing_table(ip: str, version: str) -> list:
    routing_table = []
    mpModel = 1 if version == "2c" else 0
    
    try:
        snmpEngine = SnmpEngine()
        
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
                dest = normalize_ip_address(varBinds[0][1])
                mask = normalize_ip_address(varBinds[1][1])
                next_hop = normalize_ip_address(varBinds[2][1])
                if_index = str(varBinds[3][1])
                
                routing_table.append({
                    "destination": dest,
                    "mask": mask,
                    "next_hop": next_hop,
                    "interface": if_index
                })
        
        snmpEngine.closeDispatcher()
        
        if routing_table:
            print(f"[SNMP] Retrieved {len(routing_table)} routing table entries from {ip}", flush=True)
        
        return routing_table
        
    except Exception as e:
        print(f"[SNMP] Error querying routing table for {ip}: {e}", flush=True)
        try:
            snmpEngine.closeDispatcher()
        except:
            pass
        return []


async def update_device(client: httpx.AsyncClient, ip: str, snmp_data: Dict[str, str], version: str):
    try:
        current_resp = await client.get(f"{STATE_SERVER_URL}/api/inventory/{ip}", timeout=10.0)
        if current_resp.status_code == 200:
            current = current_resp.json()
            existing_snmp_data = current.get("snmp_data") or {}
            merged_snmp_data = {**existing_snmp_data, **snmp_data}
            network_role_confirmed = current.get("network_role_confirmed", False)
        else:
            merged_snmp_data = snmp_data
            network_role_confirmed = False
        
        if snmp_data.get("ipForwarding") == "1":
            routing_table = await query_routing_table(ip, version)
            if routing_table:
                merged_snmp_data["routing_table"] = routing_table
        
        network_role = determine_network_role(merged_snmp_data)
        
        payload = {
            "snmp_data": merged_snmp_data,
            "snmp_enabled": True,
            "snmp_version": version,
            "snmp_community": SNMP_COMMUNITY,
            "last_probed": now_iso()
        }
        
        if not network_role_confirmed:
            payload["network_role"] = network_role
        
        if "vendor" in snmp_data:
            payload["vendor"] = snmp_data["vendor"]
        if "model" in snmp_data:
            payload["model"] = snmp_data["model"]
        
        resp = await client.put(
            f"{STATE_SERVER_URL}/api/inventory/{ip}",
            json=payload,
            timeout=10.0
        )
        
        if resp.status_code < 300:
            vendor_model = f"{snmp_data.get('vendor', 'Unknown')}/{snmp_data.get('model', 'Unknown')}"
            ip_fwd = snmp_data.get('ipForwarding', '?')
            print(f"[SNMP] Updated {ip}: {vendor_model} (network_role={network_role}, ipForwarding={ip_fwd}, stp={snmp_data.get('stp_enabled', '?')}, routes={snmp_data.get('route_count', '?')})", flush=True)
        else:
            print(f"[SNMP] Failed to update {ip}: {resp.status_code}", flush=True)
    except Exception as e:
        print(f"[SNMP] Error updating {ip}: {e}", flush=True)


async def reprocess_existing_snmp_data(client: httpx.AsyncClient):
    try:
        inventory = await fetch_inventory(client)
        processed = 0
        for item in inventory:
            ip = item.get("ip_address")
            snmp_data = item.get("snmp_data") or {}
            network_role_confirmed = item.get("network_role_confirmed", False)
            
            if ip and snmp_data and not network_role_confirmed:
                detected = determine_network_role(snmp_data)
                current_role = item.get("network_role", "unknown")
                
                if detected != current_role:
                    try:
                        await client.put(f"{STATE_SERVER_URL}/api/inventory/{ip}", json={"network_role": detected}, timeout=10.0)
                        processed += 1
                        print(f"[SNMP] Reclassified {ip}: {current_role} -> {detected}", flush=True)
                    except Exception as e:
                        print(f"[SNMP] Failed to reclassify {ip}: {e}", flush=True)
        if processed > 0:
            print(f"[SNMP] Reprocessed {processed} devices with existing SNMP data", flush=True)
    except Exception as e:
        print(f"[SNMP] Error reprocessing: {e}", flush=True)


async def health_server():
    from aiohttp import web
    
    async def handle_health(request):
        return web.json_response({
            "status": "healthy",
            "service": "snmp-discovery",
            "timestamp": now_iso()
        })
    
    app = web.Application()
    app.router.add_get("/health", handle_health)
    
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', 9300)
    await site.start()
    print("[SNMP] Health check server started on port 9300", flush=True)


async def main():
    print(f"[SNMP] DISABLED - SNMP discovery service is disabled. Exiting.", flush=True)
    return


if __name__ == "__main__":
    asyncio.run(main())
