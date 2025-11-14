import asyncio
import os
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any

import httpx
from pysnmp.hlapi.asyncio import (
    CommunityData,
    ContextData,
    ObjectIdentity,
    ObjectType,
    SnmpEngine,
    UdpTransportTarget,
    walk_cmd,
    get_cmd,
)


STATE_SERVER_URL = os.getenv("STATE_SERVER_URL", "http://state-server:8080")
WALK_INTERVAL_SECONDS = int(os.getenv("WALK_INTERVAL_SECONDS", "1800"))
SNMP_TIMEOUT = float(os.getenv("SNMP_TIMEOUT", "3.0"))
SNMP_RETRIES = int(os.getenv("SNMP_RETRIES", "2"))
HEALTH_PORT = int(os.getenv("HEALTH_PORT", "9600"))

stop_event = asyncio.Event()


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


async def fetch_devices_with_mibs(client: httpx.AsyncClient) -> List[Dict]:
    try:
        resp = await client.get(f"{STATE_SERVER_URL}/api/inventory", timeout=10.0)
        resp.raise_for_status()
        inventory = resp.json()
        return [
            device for device in inventory
            if device.get("snmp_enabled") and device.get("mib_id")
        ]
    except Exception as e:
        print(f"[MIB-WALKER] Error fetching devices: {e}", flush=True)
        return []


async def walk_oid_tree(ip: str, community: str, version: str, base_oid: str, max_results: int = 100) -> List[tuple]:
    try:
        snmpEngine = SnmpEngine()
        results = []
        mpModel = 0 if version == "1" else 1
        
        async for errorIndication, errorStatus, errorIndex, varBinds in walk_cmd(
            snmpEngine,
            CommunityData(community, mpModel=mpModel),
            await UdpTransportTarget.create((ip, 161), timeout=SNMP_TIMEOUT, retries=SNMP_RETRIES),
            ContextData(),
            ObjectType(ObjectIdentity(base_oid)),
            lexicographicMode=False
        ):
            if errorIndication or errorStatus:
                break
            
            for varBind in varBinds:
                oid = str(varBind[0])
                value = str(varBind[1])
                
                if not oid.startswith(base_oid):
                    snmpEngine.close_dispatcher()
                    return results
                
                results.append((oid, value))
                
                if len(results) >= max_results:
                    snmpEngine.close_dispatcher()
                    return results
        
        snmpEngine.close_dispatcher()
        return results
        
    except Exception as e:
        print(f"[MIB-WALKER] Walk error for {ip} OID {base_oid}: {e}", flush=True)
        return []


async def get_single_oid(ip: str, community: str, version: str, oid: str) -> Optional[str]:
    try:
        snmpEngine = SnmpEngine()
        mpModel = 0 if version == "1" else 1
        
        errorIndication, errorStatus, errorIndex, varBinds = await get_cmd(
            snmpEngine,
            CommunityData(community, mpModel=mpModel),
            await UdpTransportTarget.create((ip, 161), timeout=SNMP_TIMEOUT, retries=SNMP_RETRIES),
            ContextData(),
            ObjectType(ObjectIdentity(oid))
        )
        
        snmpEngine.close_dispatcher()
        
        if errorIndication or errorStatus:
            return None
        
        if varBinds:
            return str(varBinds[0][1])
        
        return None
        
    except Exception:
        return None


async def walk_interfaces(ip: str, community: str, version: str) -> Dict[str, Any]:
    interface_data = {}
    
    if_descr = await walk_oid_tree(ip, community, version, "1.3.6.1.2.1.2.2.1.2", max_results=50)
    if_type = await walk_oid_tree(ip, community, version, "1.3.6.1.2.1.2.2.1.3", max_results=50)
    if_speed = await walk_oid_tree(ip, community, version, "1.3.6.1.2.1.2.2.1.5", max_results=50)
    if_admin_status = await walk_oid_tree(ip, community, version, "1.3.6.1.2.1.2.2.1.7", max_results=50)
    if_oper_status = await walk_oid_tree(ip, community, version, "1.3.6.1.2.1.2.2.1.8", max_results=50)
    
    descr_map = {oid.split('.')[-1]: val for oid, val in if_descr}
    type_map = {oid.split('.')[-1]: val for oid, val in if_type}
    speed_map = {oid.split('.')[-1]: val for oid, val in if_speed}
    admin_map = {oid.split('.')[-1]: val for oid, val in if_admin_status}
    oper_map = {oid.split('.')[-1]: val for oid, val in if_oper_status}
    
    for idx in descr_map.keys():
        interface_data[idx] = {
            "description": descr_map.get(idx, ""),
            "type": type_map.get(idx, ""),
            "speed": speed_map.get(idx, "0"),
            "admin_status": admin_map.get(idx, ""),
            "oper_status": oper_map.get(idx, "")
        }
    
    return interface_data


async def walk_system_info(ip: str, community: str, version: str) -> Dict[str, Any]:
    system_data = {}
    
    uptime = await get_single_oid(ip, community, version, "1.3.6.1.2.1.1.3.0")
    if uptime:
        system_data["uptime"] = uptime
    
    num_users = await get_single_oid(ip, community, version, "1.3.6.1.2.1.25.1.5.0")
    if num_users:
        system_data["num_users"] = num_users
    
    processes = await get_single_oid(ip, community, version, "1.3.6.1.2.1.25.1.6.0")
    if processes:
        system_data["num_processes"] = processes
    
    return system_data


async def walk_storage(ip: str, community: str, version: str) -> Dict[str, Any]:
    storage_data = {}
    
    hr_storage_descr = await walk_oid_tree(ip, community, version, "1.3.6.1.2.1.25.2.3.1.3", max_results=30)
    hr_storage_units = await walk_oid_tree(ip, community, version, "1.3.6.1.2.1.25.2.3.1.4", max_results=30)
    hr_storage_size = await walk_oid_tree(ip, community, version, "1.3.6.1.2.1.25.2.3.1.5", max_results=30)
    hr_storage_used = await walk_oid_tree(ip, community, version, "1.3.6.1.2.1.25.2.3.1.6", max_results=30)
    
    descr_map = {oid.split('.')[-1]: val for oid, val in hr_storage_descr}
    units_map = {oid.split('.')[-1]: val for oid, val in hr_storage_units}
    size_map = {oid.split('.')[-1]: val for oid, val in hr_storage_size}
    used_map = {oid.split('.')[-1]: val for oid, val in hr_storage_used}
    
    for idx in descr_map.keys():
        storage_data[idx] = {
            "description": descr_map.get(idx, ""),
            "units": units_map.get(idx, ""),
            "size": size_map.get(idx, "0"),
            "used": used_map.get(idx, "0")
        }
    
    return storage_data


async def walk_device(ip: str, community: str, version: str, mib_name: str, oid_prefix: Optional[str] = None) -> Dict[str, Any]:
    print(f"[MIB-WALKER] Walking device {ip} with MIB {mib_name} (SNMP v{version})", flush=True)
    
    mib_data = {
        "walked_at": now_iso(),
        "mib_used": mib_name
    }
    
    try:
        interfaces = await walk_interfaces(ip, community, version)
        if interfaces:
            mib_data["interfaces"] = interfaces
            print(f"[MIB-WALKER] Found {len(interfaces)} interfaces on {ip}", flush=True)
        
        system_info = await walk_system_info(ip, community, version)
        if system_info:
            mib_data["system"] = system_info
        
        storage = await walk_storage(ip, community, version)
        if storage:
            mib_data["storage"] = storage
            print(f"[MIB-WALKER] Found {len(storage)} storage entries on {ip}", flush=True)
        
        if oid_prefix:
            vendor_data = await walk_oid_tree(ip, community, version, oid_prefix, max_results=500)
            if vendor_data:
                mib_data["VENDOR_MIB_DATA"] = {oid: value for oid, value in vendor_data}
                print(f"[MIB-WALKER] Found {len(vendor_data)} vendor-specific OIDs on {ip}", flush=True)
        
        return mib_data
        
    except Exception as e:
        print(f"[MIB-WALKER] Error walking {ip}: {e}", flush=True)
        return {}


async def update_device_mib_data(client: httpx.AsyncClient, ip: str, mib_data: Dict[str, Any]):
    try:
        current_resp = await client.get(f"{STATE_SERVER_URL}/api/inventory/{ip}", timeout=10.0)
        if current_resp.status_code != 200:
            print(f"[MIB-WALKER] Failed to fetch current data for {ip}", flush=True)
            return
        
        current = current_resp.json()
        existing_snmp_data = current.get("snmp_data", {})
        
        merged_data = {**existing_snmp_data, **mib_data}
        
        payload = {
            "snmp_data": merged_data,
            "last_probed": now_iso()
        }
        
        resp = await client.put(
            f"{STATE_SERVER_URL}/api/inventory/{ip}",
            json=payload,
            timeout=10.0
        )
        
        if resp.status_code < 300:
            print(f"[MIB-WALKER] Updated MIB data for {ip}", flush=True)
        else:
            print(f"[MIB-WALKER] Failed to update {ip}: {resp.status_code}", flush=True)
            
    except Exception as e:
        print(f"[MIB-WALKER] Error updating {ip}: {e}", flush=True)


async def health_server():
    from aiohttp import web
    
    async def handle_health(_):
        return web.json_response({
            "status": "ok",
            "walk_interval": WALK_INTERVAL_SECONDS
        })
    
    app = web.Application()
    app.router.add_get("/health", handle_health)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", HEALTH_PORT)
    await site.start()
    
    while not stop_event.is_set():
        await asyncio.sleep(0.5)


async def walker_loop():
    print(f"[MIB-WALKER] Starting MIB walker (interval={WALK_INTERVAL_SECONDS}s)", flush=True)
    
    async with httpx.AsyncClient() as client:
        while not stop_event.is_set():
            try:
                start_time = time.monotonic()
                
                devices = await fetch_devices_with_mibs(client)
                
                if not devices:
                    print("[MIB-WALKER] No devices with MIBs assigned, waiting...", flush=True)
                    await asyncio.sleep(WALK_INTERVAL_SECONDS)
                    continue
                
                print(f"[MIB-WALKER] Walking {len(devices)} devices with MIBs", flush=True)
                
                for device in devices:
                    if stop_event.is_set():
                        break
                    
                    ip = device.get("ip_address")
                    community = device.get("snmp_community", "public")
                    version = device.get("snmp_version", "2c")
                    mib_id = device.get("mib_id")
                    
                    if not ip:
                        continue
                    
                    try:
                        mibs_resp = await client.get(f"{STATE_SERVER_URL}/api/mibs", timeout=10.0)
                        if mibs_resp.status_code == 200:
                            all_mibs = mibs_resp.json()
                            mib = next((m for m in all_mibs if m["id"] == mib_id), None)
                            mib_name = mib["name"] if mib else "Unknown"
                            oid_prefix = mib.get("oid_prefix") if mib else None
                        else:
                            mib_name = f"MIB-{mib_id}"
                            oid_prefix = None
                    except:
                        mib_name = f"MIB-{mib_id}"
                        oid_prefix = None
                    
                    mib_data = await walk_device(ip, community, version, mib_name, oid_prefix)
                    if mib_data:
                        await update_device_mib_data(client, ip, mib_data)
                    
                    await asyncio.sleep(1)
                
                elapsed = time.monotonic() - start_time
                print(f"[MIB-WALKER] Walk completed in {elapsed:.1f}s", flush=True)
                
                wait_time = max(60, WALK_INTERVAL_SECONDS - int(elapsed))
                await asyncio.sleep(wait_time)
                
            except Exception as e:
                print(f"[MIB-WALKER] Walker loop error: {e}", flush=True)
                await asyncio.sleep(60)


async def main():
    import signal
    
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop_event.set)
    
    await asyncio.gather(
        health_server(),
        walker_loop()
    )


if __name__ == "__main__":
    asyncio.run(main())
