import asyncio
import os
from datetime import datetime, timezone
from typing import Dict, List

import httpx


STATE_SERVER_URL = os.getenv("STATE_SERVER_URL", "http://127.0.0.1:8080")
SCAN_INTERVAL_SECONDS = int(os.getenv("SCAN_INTERVAL_SECONDS", "600"))
HEALTH_PORT = int(os.getenv("HEALTH_PORT", "9500"))

stop_event = asyncio.Event()


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


async def fetch_inventory(client: httpx.AsyncClient) -> List[Dict]:
    try:
        resp = await client.get(f"{STATE_SERVER_URL}/api/inventory", timeout=10.0)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(f"[MIB-ASSIGN] Error fetching inventory: {e}", flush=True)
        return []


async def get_mib_suggestions(client: httpx.AsyncClient, ip: str) -> List[Dict]:
    try:
        resp = await client.get(
            f"{STATE_SERVER_URL}/api/inventory/{ip}/mibs/suggestions",
            timeout=10.0
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(f"[MIB-ASSIGN] Error getting MIB suggestions for {ip}: {e}", flush=True)
        return []


async def assign_mib(client: httpx.AsyncClient, ip: str, mib_id: int):
    try:
        payload = {
            "mib_id": mib_id,
            "last_probed": now_iso()
        }
        
        resp = await client.put(
            f"{STATE_SERVER_URL}/api/inventory/{ip}",
            json=payload,
            timeout=10.0
        )
        
        if resp.status_code < 300:
            print(f"[MIB-ASSIGN] Assigned MIB {mib_id} to {ip}", flush=True)
            return True
        else:
            print(f"[MIB-ASSIGN] Failed to assign MIB to {ip}: {resp.status_code}", flush=True)
            return False
    except Exception as e:
        print(f"[MIB-ASSIGN] Error assigning MIB to {ip}: {e}", flush=True)
        return False


def select_best_mib(suggestions: List[Dict], vendor: str, device_type: str) -> int | None:
    if not suggestions:
        return None
    
    vendor_mibs = [s for s in suggestions if s.get("vendor", "").upper() != "IETF"]
    
    if vendor_mibs:
        return vendor_mibs[0]["id"]
    
    return suggestions[0]["id"]


async def health_server():
    from aiohttp import web
    
    async def handle_health(_):
        return web.json_response({
            "status": "ok",
            "scan_interval": SCAN_INTERVAL_SECONDS
        })
    
    app = web.Application()
    app.router.add_get("/health", handle_health)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", HEALTH_PORT)
    await site.start()
    
    while not stop_event.is_set():
        await asyncio.sleep(0.5)


async def assignment_loop():
    print(f"[MIB-ASSIGN] Starting MIB assignment (interval={SCAN_INTERVAL_SECONDS}s)", flush=True)
    
    async with httpx.AsyncClient() as client:
        while not stop_event.is_set():
            try:
                inventory = await fetch_inventory(client)
                
                if not inventory:
                    print("[MIB-ASSIGN] No devices in inventory, waiting...", flush=True)
                    await asyncio.sleep(SCAN_INTERVAL_SECONDS)
                    continue
                
                devices_needing_mibs = [
                    d for d in inventory
                    if d.get("snmp_data") and not d.get("mib_id")
                ]
                
                if not devices_needing_mibs:
                    print("[MIB-ASSIGN] No devices need MIB assignment, waiting...", flush=True)
                    await asyncio.sleep(SCAN_INTERVAL_SECONDS)
                    continue
                
                print(f"[MIB-ASSIGN] Assigning MIBs to {len(devices_needing_mibs)} devices", flush=True)
                
                assigned_count = 0
                for device in devices_needing_mibs:
                    if stop_event.is_set():
                        break
                    
                    ip = device.get("ip_address")
                    if not ip:
                        continue
                    
                    suggestions = await get_mib_suggestions(client, ip)
                    if not suggestions:
                        continue
                    
                    best_mib_id = select_best_mib(
                        suggestions,
                        device.get("vendor", ""),
                        device.get("device_type", "")
                    )
                    
                    if best_mib_id:
                        success = await assign_mib(client, ip, best_mib_id)
                        if success:
                            assigned_count += 1
                
                print(f"[MIB-ASSIGN] Assigned MIBs to {assigned_count} devices", flush=True)
                await asyncio.sleep(SCAN_INTERVAL_SECONDS)
                
            except Exception as e:
                print(f"[MIB-ASSIGN] Assignment loop error: {e}", flush=True)
                await asyncio.sleep(10)


async def main():
    import signal
    
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop_event.set)
    
    await asyncio.gather(
        health_server(),
        assignment_loop()
    )


if __name__ == "__main__":
    asyncio.run(main())
