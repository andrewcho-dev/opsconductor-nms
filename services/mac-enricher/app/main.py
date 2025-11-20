import asyncio
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional
import concurrent.futures

import httpx
import requests


STATE_SERVER_URL = os.getenv("STATE_SERVER_URL", "http://127.0.0.1:8080")
SCAN_INTERVAL_SECONDS = int(os.getenv("SCAN_INTERVAL_SECONDS", "300"))
HEALTH_PORT = int(os.getenv("HEALTH_PORT", "9400"))
OUI_URL = "https://standards-oui.ieee.org/oui/oui.txt"
OUI_FILE = Path(os.getenv("OUI_FILE", "/data/oui.txt"))

stop_event = asyncio.Event()
oui_map: Dict[str, str] = {}
update_trigger = asyncio.Event()


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_oui_data(text: str) -> Dict[str, str]:
    result = {}
    for line in text.split('\n'):
        if '(hex)' in line:
            parts = line.split('(hex)')
            if len(parts) >= 2:
                oui = parts[0].strip().replace('-', '').upper()
                vendor = parts[1].strip()
                if oui and vendor:
                    result[oui] = vendor
    return result


def download_oui_sync() -> Dict[str, str]:
    print("[MAC] Downloading OUI database from IEEE...", flush=True)
    try:
        headers = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"}
        resp = requests.get(OUI_URL, headers=headers, timeout=120)
        resp.raise_for_status()
        
        result = parse_oui_data(resp.text)
        
        OUI_FILE.parent.mkdir(parents=True, exist_ok=True)
        OUI_FILE.write_text(resp.text)
        
        print(f"[MAC] Downloaded and saved {len(result)} OUI entries to {OUI_FILE}", flush=True)
        return result
    except Exception as e:
        print(f"[MAC] Error downloading OUI: {e}", flush=True)
        return {}


def load_oui_from_file() -> Dict[str, str]:
    try:
        if not OUI_FILE.exists():
            print(f"[MAC] OUI file not found at {OUI_FILE}", flush=True)
            return {}
        
        stat = OUI_FILE.stat()
        age_days = (datetime.now().timestamp() - stat.st_mtime) / 86400
        
        print(f"[MAC] Loading OUI database from {OUI_FILE} (age: {age_days:.1f} days)", flush=True)
        
        text = OUI_FILE.read_text()
        result = parse_oui_data(text)
        
        print(f"[MAC] Loaded {len(result)} OUI entries from file", flush=True)
        
        if age_days > 90:
            print(f"[MAC] WARNING: OUI database is {age_days:.0f} days old. Consider updating.", flush=True)
        
        return result
    except Exception as e:
        print(f"[MAC] Error loading OUI from file: {e}", flush=True)
        return {}


def load_or_download_oui() -> Dict[str, str]:
    result = load_oui_from_file()
    if result:
        return result
    
    print("[MAC] No cached OUI database found, downloading...", flush=True)
    return download_oui_sync()


def normalize_mac(mac: str) -> str:
    return mac.replace(":", "").replace("-", "").upper()[:6]


def lookup_vendor(mac: str) -> Optional[str]:
    oui = normalize_mac(mac)
    return oui_map.get(oui)


async def fetch_inventory(client: httpx.AsyncClient) -> List[Dict]:
    try:
        resp = await client.get(f"{STATE_SERVER_URL}/api/inventory", timeout=10.0)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(f"[MAC] Error fetching inventory: {e}", flush=True)
        return []


async def update_device_vendor(client: httpx.AsyncClient, ip: str, vendor: str):
    try:
        payload = {"vendor": vendor, "last_probed": now_iso()}
        resp = await client.put(f"{STATE_SERVER_URL}/api/inventory/{ip}", json=payload, timeout=10.0)
        
        if resp.status_code < 300:
            print(f"[MAC] {ip}: {vendor}", flush=True)
    except Exception as e:
        print(f"[MAC] Error updating {ip}: {e}", flush=True)


async def health_server():
    from aiohttp import web
    
    @web.middleware
    async def cors_middleware(request, handler):
        if request.method == "OPTIONS":
            response = web.Response()
        else:
            response = await handler(request)
        
        response.headers['Access-Control-Allow-Origin'] = '*'
        response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
        response.headers['Access-Control-Allow-Headers'] = '*'
        return response
    
    async def handle_health(_):
        stat = OUI_FILE.stat() if OUI_FILE.exists() else None
        age_days = (datetime.now().timestamp() - stat.st_mtime) / 86400 if stat else None
        
        return web.json_response({
            "status": "ok",
            "oui_entries": len(oui_map),
            "oui_file": str(OUI_FILE),
            "oui_exists": OUI_FILE.exists(),
            "oui_age_days": round(age_days, 1) if age_days is not None else None
        })
    
    async def handle_update(_):
        global oui_map
        print("[MAC] Manual OUI update triggered via API", flush=True)
        
        loop = asyncio.get_event_loop()
        with concurrent.futures.ThreadPoolExecutor() as executor:
            new_map = await loop.run_in_executor(executor, download_oui_sync)
        
        if new_map:
            oui_map = new_map
            return web.json_response({"status": "updated", "entries": len(oui_map)})
        else:
            return web.json_response({"status": "failed", "entries": len(oui_map)}, status=500)
    
    app = web.Application(middlewares=[cors_middleware])
    
    app.router.add_get("/health", handle_health)
    app.router.add_post("/update", handle_update)
    
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", HEALTH_PORT)
    await site.start()
    
    while not stop_event.is_set():
        await asyncio.sleep(0.5)


async def enrichment_loop():
    print("[MAC] DISABLED - MAC enrichment service is disabled. Exiting.", flush=True)
    stop_event.set()
    return


async def main():
    import signal
    
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop_event.set)
    
    await asyncio.gather(health_server(), enrichment_loop())


if __name__ == "__main__":
    asyncio.run(main())
