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


async def assign_mibs(client: httpx.AsyncClient, ip: str, mib_id: int, mib_ids: List[int]):
    try:
        payload = {
            "mib_id": mib_id,
            "mib_ids": mib_ids,
            "last_probed": now_iso()
        }
        
        resp = await client.put(
            f"{STATE_SERVER_URL}/api/inventory/{ip}",
            json=payload,
            timeout=10.0
        )
        
        if resp.status_code < 300:
            print(f"[MIB-ASSIGN] Assigned {len(mib_ids)} MIBs to {ip} (primary: {mib_id})", flush=True)
            return True
        else:
            print(f"[MIB-ASSIGN] Failed to assign MIBs to {ip}: {resp.status_code}", flush=True)
            return False
    except Exception as e:
        print(f"[MIB-ASSIGN] Error assigning MIBs to {ip}: {e}", flush=True)
        return False


async def select_mibs(client: httpx.AsyncClient, ip: str, suggestions: List[Dict]) -> tuple[int | None, List[int]]:
    if not suggestions:
        return None, []
    
    if len(suggestions) == 1:
        mib_id = suggestions[0]["id"]
        return mib_id, [mib_id]
    
    mib_ids = [s["id"] for s in suggestions]
    score_threshold = 20
    
    try:
        resp = await client.post(
            "http://mib-walker:9600/test-mibs",
            json={"ip_address": ip, "mib_ids": mib_ids},
            timeout=60.0
        )
        
        if resp.status_code == 200:
            result = resp.json()
            all_results = result.get("results", [])
            
            passing_mibs = [r for r in all_results if r.get("score", 0) > score_threshold]
            
            if passing_mibs:
                passing_ids = [r["mib_id"] for r in passing_mibs]
                best = passing_mibs[0]
                print(f"[MIB-ASSIGN] Selected {len(passing_ids)} MIBs for {ip}, primary: {best['mib_name']} (score={best['score']})", flush=True)
                return best["mib_id"], passing_ids
    except Exception as e:
        print(f"[MIB-ASSIGN] Error testing MIBs for {ip}: {e}, using first suggestion", flush=True)
    
    vendor_mibs = [s for s in suggestions if s.get("vendor", "").upper() != "IETF"]
    if vendor_mibs:
        fallback_id = vendor_mibs[0]["id"]
        return fallback_id, [fallback_id]
    
    fallback_id = suggestions[0]["id"]
    return fallback_id, [fallback_id]


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
                    
                    best_mib_id, mib_ids = await select_mibs(client, ip, suggestions)
                    
                    if best_mib_id and mib_ids:
                        success = await assign_mibs(client, ip, best_mib_id, mib_ids)
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
