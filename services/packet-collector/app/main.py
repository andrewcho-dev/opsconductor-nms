import asyncio, os, json, signal, time, threading, queue
from datetime import datetime, timezone
from typing import Dict, Tuple

import httpx
from pydantic import BaseModel
from scapy.all import sniff, ARP, IP, IPv6, TCP, UDP, Ether

IFACE = os.getenv("IFACE", "eth0")
BATCH_MS = int(os.getenv("BATCH_MS", "250"))
MAX_EVIDENCE_ITEMS = int(os.getenv("MAX_EVIDENCE_ITEMS", "1024"))
FILTER_BPF = os.getenv("FILTER_BPF", "arp or ip or ip6")
ANALYST_URL = os.getenv("ANALYST_URL", "http://127.0.0.1:8100/tick")
STATE_SERVER_URL = os.getenv("STATE_SERVER_URL", "http://127.0.0.1:8080")
SEED_GATEWAY_IP = os.getenv("SEED_GATEWAY_IP", "")
SEED_FIREWALL_IP = os.getenv("SEED_FIREWALL_IP", "")
HEALTH_PORT = int(os.getenv("HEALTH_PORT", "9100"))
INTERNAL_NETWORK_PREFIX = os.getenv("INTERNAL_NETWORK_PREFIX", "192.168.10.")
INVENTORY_UPDATE_INTERVAL = int(os.getenv("INVENTORY_UPDATE_INTERVAL", "30"))

pkt_q: "queue.Queue" = queue.Queue(maxsize=10000)
stop_event = threading.Event()

ip_inventory: Dict[str, dict] = {}
ip_inventory_lock = threading.Lock()

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

def is_internal_ip(ip: str) -> bool:
    return ip.startswith(INTERNAL_NETWORK_PREFIX)

def extract_ip_mac_from_packet(pkt):
    global ip_inventory, ip_inventory_lock
    try:
        pairs = []
        
        if ARP in pkt:
            src_ip = pkt[ARP].psrc
            src_mac = pkt[ARP].hwsrc
            if is_internal_ip(src_ip):
                pairs.append((src_ip, src_mac))
        
        if Ether in pkt and (IP in pkt or IPv6 in pkt):
            src_mac = pkt[Ether].src
            if IP in pkt:
                src_ip = pkt[IP].src
                if is_internal_ip(src_ip):
                    pairs.append((src_ip, src_mac))
        
        if pairs:
            timestamp = now_iso()
            with ip_inventory_lock:
                for ip, mac in pairs:
                    if ip not in ip_inventory:
                        ip_inventory[ip] = {
                            "ip_address": ip,
                            "mac_address": mac,
                            "first_seen": timestamp,
                            "last_seen": timestamp
                        }
                    else:
                        ip_inventory[ip]["last_seen"] = timestamp
                        if ip_inventory[ip]["mac_address"] != mac:
                            ip_inventory[ip]["mac_address"] = mac
    except Exception:
        pass

def parse_packet(pkt) -> Tuple[str, dict] | None:
    ts = now_iso()
    try:
        if ARP in pkt:
            op = "request" if pkt[ARP].op == 1 else ("reply" if pkt[ARP].op == 2 else str(pkt[ARP].op))
            return ("arp", {
                "timestamp": ts,
                "src_ip": pkt[ARP].psrc,
                "src_mac": pkt[ARP].hwsrc,
                "dst_ip": pkt[ARP].pdst,
                "operation": op,
            })
        elif IP in pkt or IPv6 in pkt:
            if IP in pkt:
                sip, dip = pkt[IP].src, pkt[IP].dst
                proto = pkt[IP].proto
            else:
                sip, dip = pkt[IPv6].src, pkt[IPv6].dst
                proto = pkt[IPv6].nh

            protocol = {6: "tcp", 17: "udp", 1: "icmp"}.get(proto, str(proto))
            sport = int(pkt[TCP].sport) if TCP in pkt else (int(pkt[UDP].sport) if UDP in pkt else None)
            dport = int(pkt[TCP].dport) if TCP in pkt else (int(pkt[UDP].dport) if UDP in pkt else None)
            length = int(len(pkt))
            return ("flow", {
                "timestamp": ts,
                "src_ip": sip,
                "dst_ip": dip,
                "src_port": sport,
                "dst_port": dport,
                "protocol": protocol,
                "packets": 1,
                "bytes": length
            })
    except Exception:
        return None
    return None

def sniff_worker():
    def _cb(pkt):
        extract_ip_mac_from_packet(pkt)
        
        item = parse_packet(pkt)
        if item:
            try: pkt_q.put_nowait(item)
            except queue.Full: pass
        if not item:
            if IP in pkt and "192.168.10.10" in str(pkt[IP].src):
                print(f"[PARSE_FAIL] ICMP from 192.168.10.10 failed to parse", flush=True)
    sniff(iface=IFACE, prn=_cb, store=False, filter=FILTER_BPF,
          stop_filter=lambda _: stop_event.is_set())

async def health_server():
    from aiohttp import web
    async def handle_health(_):
        return web.json_response({"status": "ok", "iface": IFACE, "batch_ms": BATCH_MS})
    app = web.Application()
    app.router.add_get("/health", handle_health)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", HEALTH_PORT)
    await site.start()
    while not stop_event.is_set():
        await asyncio.sleep(0.5)

async def fetch_digest(client: httpx.AsyncClient) -> dict:
    try:
        r = await client.get(f"{STATE_SERVER_URL}/graph", timeout=2.0)
        r.raise_for_status()
        g = r.json().get("graph", {})
        nodes = g.get("nodes", {})
        edges = g.get("edges", [])
        top = [f"{e.get('src','?')}->{e.get('dst','?')}" for e in edges[:10]]
        existing_ips = sorted(list(nodes.keys()))[:50]
        return {
            "node_count": len(nodes), 
            "edge_count": len(edges), 
            "top_edges": top,
            "existing_nodes": existing_ips
        }
    except Exception:
        return {"node_count": 0, "edge_count": 0, "top_edges": [], "existing_nodes": []}

async def inventory_update_loop():
    print(f"[INVENTORY] Starting IP inventory update loop ({INVENTORY_UPDATE_INTERVAL}s interval)", flush=True)
    
    async with httpx.AsyncClient(timeout=10.0) as client:
        while not stop_event.is_set():
            try:
                await asyncio.sleep(INVENTORY_UPDATE_INTERVAL)
                
                with ip_inventory_lock:
                    if not ip_inventory:
                        continue
                    
                    inventory_snapshot = list(ip_inventory.values())
                
                print(f"[INVENTORY] Updating {len(inventory_snapshot)} IPs to state-server", flush=True)
                
                for item in inventory_snapshot:
                    try:
                        payload = {
                            "ip_address": item["ip_address"],
                            "mac_address": item["mac_address"],
                            "status": "active",
                            "last_seen": item["last_seen"]
                        }
                        
                        resp = await client.get(f"{STATE_SERVER_URL}/api/inventory/{item['ip_address']}", timeout=5.0)
                        
                        if resp.status_code == 404:
                            resp = await client.post(f"{STATE_SERVER_URL}/api/inventory", json=payload, timeout=5.0)
                            if resp.status_code < 300:
                                print(f"[INVENTORY] Created new entry for {item['ip_address']}", flush=True)
                        elif resp.status_code == 200:
                            resp = await client.put(f"{STATE_SERVER_URL}/api/inventory/{item['ip_address']}", 
                                                   json=payload, timeout=5.0)
                            if resp.status_code < 300:
                                pass
                    except Exception as e:
                        print(f"[INVENTORY] Error updating {item['ip_address']}: {e}", flush=True)
                
            except Exception as e:
                print(f"[INVENTORY] Update loop error: {e}", flush=True)

async def tick_loop():
    print("[PACKET-COLLECTOR] DISABLED - Packet collector service is disabled. Exiting.", flush=True)
    stop_event.set()
    return

async def main():
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop_event.set)
    await asyncio.gather(
        health_server(),
        tick_loop(),
        inventory_update_loop()
    )

if __name__ == "__main__":
    try:
        import uvloop; uvloop.install()
    except Exception:
        pass
    asyncio.run(main())
