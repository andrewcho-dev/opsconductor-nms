import asyncio
import os
import socket
import time
from datetime import datetime, timezone
from typing import Dict, List

import httpx


STATE_SERVER_URL = os.getenv("STATE_SERVER_URL", "http://127.0.0.1:8080")
SCAN_INTERVAL_SECONDS = int(os.getenv("SCAN_INTERVAL_SECONDS", "300"))
SCAN_PORTS = [int(p) for p in os.getenv("SCAN_PORTS", "22,23,80,443,554,1883,5060,8080,8443,161,179,3389").split(",")]
CONNECTION_TIMEOUT = float(os.getenv("CONNECTION_TIMEOUT", "2.0"))
HEALTH_PORT = int(os.getenv("HEALTH_PORT", "9200"))

stop_event = asyncio.Event()


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class SNMPProtocol(asyncio.DatagramProtocol):
    def __init__(self):
        self.response_received = asyncio.Event()
        self.transport = None
    
    def connection_made(self, transport):
        self.transport = transport
    
    def datagram_received(self, data, addr):
        if len(data) > 10 and data[0] == 0x30:
            self.response_received.set()
    
    def error_received(self, exc):
        pass


async def scan_udp_snmp(ip: str, port: int = 161, timeout: float = 2.0) -> bool:
    try:
        loop = asyncio.get_event_loop()
        protocol = SNMPProtocol()
        
        transport, _ = await asyncio.wait_for(
            loop.create_datagram_endpoint(
                lambda: protocol,
                remote_addr=(ip, port)
            ),
            timeout=timeout
        )
        
        snmp_get_request = bytes.fromhex(
            "302902010004067075626c6963a01c02047a053bb302010002010030"
            "0e300c06082b060102010105000500"
        )
        
        transport.sendto(snmp_get_request)
        
        try:
            await asyncio.wait_for(protocol.response_received.wait(), timeout=1.5)
            transport.close()
            return True
        except asyncio.TimeoutError:
            transport.close()
            return False
    except Exception:
        return False


async def scan_port(ip: str, port: int, timeout: float = 2.0) -> tuple[bool, str | None]:
    if port == 161:
        is_open = await scan_udp_snmp(ip, port, timeout)
        return is_open, None
    
    try:
        conn = asyncio.open_connection(ip, port)
        reader, writer = await asyncio.wait_for(conn, timeout=timeout)
        
        try:
            banner_data = await asyncio.wait_for(reader.read(1024), timeout=1.0)
            banner = banner_data.decode('utf-8', errors='ignore').strip()[:200]
        except (asyncio.TimeoutError, Exception):
            banner = None
        
        writer.close()
        await writer.wait_closed()
        
        return True, banner
    except (asyncio.TimeoutError, ConnectionRefusedError, OSError):
        return False, None


async def scan_host(ip: str, ports: List[int]) -> Dict[int, str]:
    open_ports = {}
    
    for port in ports:
        is_open, banner = await scan_port(ip, port, timeout=CONNECTION_TIMEOUT)
        if is_open:
            service_name = get_service_name(port)
            port_info = {"service": service_name}
            if banner:
                port_info["banner"] = banner
            open_ports[str(port)] = port_info
            if ip == "192.168.10.128":
                print(f"[DEBUG] {ip}:{port} is OPEN (service: {service_name})", flush=True)
        elif ip == "192.168.10.128" and port == 161:
            print(f"[DEBUG] {ip}:161 SNMP scan returned FALSE", flush=True)
    
    return open_ports


def get_service_name(port: int) -> str:
    common_ports = {
        22: "ssh",
        23: "telnet",
        80: "http",
        443: "https",
        554: "rtsp",
        1883: "mqtt",
        5060: "sip",
        8080: "http-alt",
        8443: "https-alt",
        161: "snmp",
        179: "bgp",
        3389: "rdp",
        21: "ftp",
        25: "smtp",
        53: "dns",
        110: "pop3",
        143: "imap",
        3306: "mysql",
        5432: "postgresql",
        6379: "redis"
    }
    return common_ports.get(port, "unknown")


async def fetch_inventory(client: httpx.AsyncClient) -> List[Dict]:
    try:
        resp = await client.get(f"{STATE_SERVER_URL}/api/inventory", timeout=10.0)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(f"[SCANNER] Error fetching inventory: {e}", flush=True)
        return []


async def update_scan_results(client: httpx.AsyncClient, ip: str, open_ports: Dict[int, str]):
    try:
        payload = {
            "open_ports": open_ports,
            "last_probed": now_iso()
        }
        
        resp = await client.put(
            f"{STATE_SERVER_URL}/api/inventory/{ip}",
            json=payload,
            timeout=10.0
        )
        
        if resp.status_code < 300:
            print(f"[SCANNER] Updated {ip}: {len(open_ports)} open ports", flush=True)
        else:
            print(f"[SCANNER] Failed to update {ip}: {resp.status_code}", flush=True)
    except Exception as e:
        print(f"[SCANNER] Error updating {ip}: {e}", flush=True)


async def health_server():
    from aiohttp import web
    
    async def handle_health(_):
        return web.json_response({
            "status": "ok",
            "scan_interval": SCAN_INTERVAL_SECONDS,
            "scan_ports": SCAN_PORTS
        })
    
    app = web.Application()
    app.router.add_get("/health", handle_health)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", HEALTH_PORT)
    await site.start()
    
    while not stop_event.is_set():
        await asyncio.sleep(0.5)


async def scan_loop():
    print(f"[SCANNER] Starting port scanner (interval={SCAN_INTERVAL_SECONDS}s, ports={SCAN_PORTS})", flush=True)
    
    async with httpx.AsyncClient() as client:
        while not stop_event.is_set():
            try:
                start_time = time.monotonic()
                inventory = await fetch_inventory(client)
                
                if not inventory:
                    print("[SCANNER] No devices in inventory, waiting...", flush=True)
                    await asyncio.sleep(SCAN_INTERVAL_SECONDS)
                    continue
                
                print(f"[SCANNER] Scanning {len(inventory)} devices", flush=True)
                
                for item in inventory:
                    if stop_event.is_set():
                        break
                    
                    ip = item.get("ip_address")
                    if not ip:
                        continue
                    
                    open_ports = await scan_host(ip, SCAN_PORTS)
                    await update_scan_results(client, ip, open_ports)
                
                elapsed = time.monotonic() - start_time
                print(f"[SCANNER] Scan completed in {elapsed:.1f}s", flush=True)
                
                wait_time = max(1, SCAN_INTERVAL_SECONDS - int(elapsed))
                await asyncio.sleep(wait_time)
                
            except Exception as e:
                print(f"[SCANNER] Scan loop error: {e}", flush=True)
                await asyncio.sleep(10)


async def main():
    import signal
    
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop_event.set)
    
    await asyncio.gather(
        health_server(),
        scan_loop()
    )


if __name__ == "__main__":
    asyncio.run(main())
