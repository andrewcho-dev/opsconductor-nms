import asyncio
import os
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional

import httpx
from pysnmp.hlapi.asyncio import (
    CommunityData,
    ContextData,
    ObjectIdentity,
    ObjectType,
    SnmpEngine,
    UdpTransportTarget,
    getCmd,
)


STATE_SERVER_URL = os.getenv("STATE_SERVER_URL", "http://127.0.0.1:8080")
SCAN_INTERVAL_SECONDS = int(os.getenv("SCAN_INTERVAL_SECONDS", "300"))
SNMP_COMMUNITY = os.getenv("SNMP_COMMUNITY", "public")
SNMP_TIMEOUT = float(os.getenv("SNMP_TIMEOUT", "2.0"))
SNMP_RETRIES = int(os.getenv("SNMP_RETRIES", "1"))
HEALTH_PORT = int(os.getenv("HEALTH_PORT", "9300"))

stop_event = asyncio.Event()


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


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
            
            snmpEngine.closeDispatcher()
            
            if results:
                vendor, model = parse_vendor_model(results.get("sysDescr", ""), results.get("sysObjectID", ""))
                if vendor:
                    results["vendor"] = vendor
                if model:
                    results["model"] = model
                return (results, version)
            
        except Exception:
            continue
    
    return None


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
        elif "qfx" in descr_lower:
            model = "QFX"
    elif "arista" in descr_lower:
        vendor = "Arista"
        if "7050" in descr_lower:
            model = "7050"
        elif "7280" in descr_lower:
            model = "7280"
    elif "linux" in descr_lower:
        vendor = "Linux"
        if "ubuntu" in descr_lower:
            model = "Ubuntu"
        elif "debian" in descr_lower:
            model = "Debian"
        elif "centos" in descr_lower:
            model = "CentOS"
        elif "rhel" in descr_lower or "red hat" in descr_lower:
            model = "RHEL"
    elif "windows" in descr_lower:
        vendor = "Microsoft"
        model = "Windows"
    elif "hp" in descr_lower or "hewlett" in descr_lower:
        vendor = "HP"
    elif "dell" in descr_lower:
        vendor = "Dell"
    
    if sys_oid.startswith("1.3.6.1.4.1.9"):
        vendor = vendor or "Cisco"
    elif sys_oid.startswith("1.3.6.1.4.1.2636"):
        vendor = vendor or "Juniper"
    elif sys_oid.startswith("1.3.6.1.4.1.30065"):
        vendor = vendor or "Arista"
    
    return vendor, model


async def fetch_inventory(client: httpx.AsyncClient) -> List[Dict]:
    try:
        resp = await client.get(f"{STATE_SERVER_URL}/api/inventory", timeout=10.0)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(f"[SNMP] Error fetching inventory: {e}", flush=True)
        return []


async def update_snmp_data(client: httpx.AsyncClient, ip: str, snmp_data: Dict[str, str], version: str):
    try:
        current_resp = await client.get(f"{STATE_SERVER_URL}/api/inventory/{ip}", timeout=10.0)
        if current_resp.status_code == 200:
            current = current_resp.json()
            existing_snmp_data = current.get("snmp_data", {})
            merged_snmp_data = {**existing_snmp_data, **snmp_data}
        else:
            merged_snmp_data = snmp_data
        
        payload = {
            "snmp_data": merged_snmp_data,
            "snmp_enabled": True,
            "snmp_version": version,
            "snmp_community": SNMP_COMMUNITY,
            "last_probed": now_iso()
        }








        }
        
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
            print(f"[SNMP] Updated {ip}: {vendor_model}", flush=True)
        else:
            print(f"[SNMP] Failed to update {ip}: {resp.status_code}", flush=True)
    except Exception as e:
        print(f"[SNMP] Error updating {ip}: {e}", flush=True)


async def health_server():
    from aiohttp import web
    
    async def handle_health(_):
        return web.json_response({
            "status": "ok",
            "scan_interval": SCAN_INTERVAL_SECONDS,
            "snmp_community": SNMP_COMMUNITY
        })
    
    app = web.Application()
    app.router.add_get("/health", handle_health)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", HEALTH_PORT)
    await site.start()
    
    while not stop_event.is_set():
        await asyncio.sleep(0.5)


async def discovery_loop():
    print(f"[SNMP] Starting SNMP discovery (interval={SCAN_INTERVAL_SECONDS}s, community={SNMP_COMMUNITY})", flush=True)
    
    async with httpx.AsyncClient() as client:
        while not stop_event.is_set():
            try:
                start_time = time.monotonic()
                inventory = await fetch_inventory(client)
                
                if not inventory:
                    print("[SNMP] No devices in inventory, waiting...", flush=True)
                    await asyncio.sleep(SCAN_INTERVAL_SECONDS)
                    continue
                
                snmp_devices = [item for item in inventory if (item.get("open_ports") or {}).get("161") is not None]
                
                if not snmp_devices:
                    print("[SNMP] No SNMP-capable devices found, waiting...", flush=True)
                    await asyncio.sleep(SCAN_INTERVAL_SECONDS)
                    continue
                
                print(f"[SNMP] Querying {len(snmp_devices)} SNMP devices", flush=True)
                
                for item in snmp_devices:
                    if stop_event.is_set():
                        break
                    
                    ip = item.get("ip_address")
                    if not ip:
                        continue
                    
                    result = await query_snmp(ip)
                    if result:
                        snmp_data, version = result
                        await update_snmp_data(client, ip, snmp_data, version)
                
                elapsed = time.monotonic() - start_time
                print(f"[SNMP] Discovery completed in {elapsed:.1f}s", flush=True)
                
                wait_time = max(1, SCAN_INTERVAL_SECONDS - int(elapsed))
                await asyncio.sleep(wait_time)
                
            except Exception as e:
                print(f"[SNMP] Discovery loop error: {e}", flush=True)
                await asyncio.sleep(10)


async def main():
    import signal
    
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop_event.set)
    
    await asyncio.gather(
        health_server(),
        discovery_loop()
    )


if __name__ == "__main__":
    asyncio.run(main())
