import asyncio, os, json, signal, time, threading, queue
from datetime import datetime, timezone
from typing import Dict, Tuple

import httpx
from pydantic import BaseModel
from scapy.all import sniff, ARP, IP, IPv6, TCP, UDP, Ether

from .switch_detector import SwitchDetector

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
raw_pkt_q: "queue.Queue" = queue.Queue(maxsize=5000)
stop_event = threading.Event()
switch_detector = SwitchDetector()

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
        try:
            raw_pkt_q.put_nowait(pkt)
        except queue.Full:
            pass
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

async def switch_detection_loop():
    """
    SECONDARY DETECTION: Switch probability analysis
    Runs every 60 seconds, separate from primary discovery
    Can be easily disabled/removed if needed
    """
    print("[SWITCH_DETECTOR] Starting secondary switch detection loop (60s interval)", flush=True)
    
    async with httpx.AsyncClient(timeout=10.0) as client:
        last_analysis = time.monotonic()
        packet_count = 0
        
        while not stop_event.is_set():
            try:
                pkt = raw_pkt_q.get(timeout=0.01)
                switch_detector.process_raw_packet(pkt)
                packet_count += 1
            except queue.Empty:
                pass
            
            now = time.monotonic()
            if (now - last_analysis) >= 60.0:
                print(f"[SWITCH_DETECTOR] Running analysis (processed {packet_count} packets)", flush=True)
                
                try:
                    candidates = switch_detector.get_switch_candidates(min_score=0.35)
                    
                    if candidates:
                        print(f"[SWITCH_DETECTOR] Found {len(candidates)} switch candidates", flush=True)
                        for mac, data in candidates.items():
                            print(f"  - {mac}: {data['classification']} (score={data['score']:.2f})", flush=True)
                        
                        patch_ops = []
                        for mac, data in candidates.items():
                            ip_candidates = []
                            for ip, features in switch_detector.device_features.items():
                                if features.mac == mac:
                                    ip_candidates.append(ip)
                            
                            if ip_candidates:
                                for ip in ip_candidates[:1]:
                                    patch_ops.append({
                                        "op": "replace",
                                        "path": f"/nodes/{ip}/switch_probability",
                                        "value": {
                                            "score": data["score"],
                                            "classification": data["classification"],
                                            "evidence": data["evidence"]
                                        }
                                    })
                        
                        if patch_ops:
                            patch_payload = {
                                "version": "1.0",
                                "patch": patch_ops[:10],
                                "rationale": f"Secondary switch detection identified {len(candidates)} probable switches",
                                "warnings": ["secondary_detection"]
                            }
                            
                            try:
                                resp = await client.post(f"{STATE_SERVER_URL}/patch", json=patch_payload, timeout=5.0)
                                if resp.status_code < 300:
                                    print(f"[SWITCH_DETECTOR] Applied {len(patch_ops)} updates to graph", flush=True)
                                else:
                                    print(f"[SWITCH_DETECTOR] Failed to apply patch: {resp.status_code}", flush=True)
                            except Exception as e:
                                print(f"[SWITCH_DETECTOR] Error applying patch: {e}", flush=True)
                    
                    switch_detector.clear_old_data(max_age_seconds=1800)
                    
                except Exception as e:
                    print(f"[SWITCH_DETECTOR] Analysis error: {e}", flush=True)
                
                last_analysis = now
                packet_count = 0
            
            await asyncio.sleep(0.01)

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
    t = threading.Thread(target=sniff_worker, daemon=True)
    t.start()

    class FlowAgg(BaseModel):
        packets: int = 0
        bytes: int = 0
        first_ts: str | None = None
        last_ts: str | None = None

    def flow_key(d: dict) -> str:
        return json.dumps([d.get("src_ip"), d.get("dst_ip"), d.get("protocol"),
                           d.get("src_port"), d.get("dst_port")], separators=(",", ":"))

    async with httpx.AsyncClient(timeout=5.0) as client:
        last_flush = time.monotonic()
        flows: Dict[str, dict] = {}
        arps: list[dict] = []

        while not stop_event.is_set():
            try:
                kind, data = pkt_q.get(timeout=0.01)
                if kind == "arp":
                    if len(arps) < MAX_EVIDENCE_ITEMS: arps.append(data)
                else:
                    k = flow_key(data)
                    agg = flows.get(k)
                    if not agg:
                        agg = FlowAgg(packets=0, bytes=0, first_ts=data["timestamp"], last_ts=data["timestamp"]).model_dump()
                        flows[k] = agg
                    agg["packets"] += 1
                    agg["bytes"] += int(data.get("bytes", 0))
                    agg["last_ts"] = data["timestamp"]
            except queue.Empty:
                pass

            now = time.monotonic()
            if (now - last_flush) * 1000.0 >= BATCH_MS:
                window_id = now_iso()
                flow_items = []
                unique_src_ips = set()
                for k, agg in list(flows.items()):
                    sip, dip, protocol, sport, dport = json.loads(k)
                    unique_src_ips.add(sip)
                    flow_items.append({
                        "timestamp": agg["last_ts"],
                        "src_ip": sip, "dst_ip": dip,
                        "src_port": sport, "dst_port": dport,
                        "protocol": protocol,
                        "packets": agg["packets"], "bytes": agg["bytes"]
                    })
                    if len(flow_items) >= MAX_EVIDENCE_ITEMS:
                        break
                print(f"[TICK] flows={len(flows)} arps={len(arps)} src_ips={sorted(unique_src_ips)}", flush=True)

                seed_facts = {}
                if SEED_GATEWAY_IP: seed_facts["gateway_ip"] = SEED_GATEWAY_IP
                if SEED_FIREWALL_IP: seed_facts["firewall_ip"] = SEED_FIREWALL_IP

                payload = {
                    "evidence_window": {
                        "window_id": window_id,
                        "arp": arps[:MAX_EVIDENCE_ITEMS],
                        "flows": flow_items
                    },
                    "hypothesis_digest": await fetch_digest(client),
                    "seed_facts": seed_facts,
                    "previous_rationales": []
                }

                try:
                    resp = await client.post(ANALYST_URL, json=payload)
                    if resp.status_code >= 300:
                        raise RuntimeError(f"analyst {resp.status_code} {resp.text[:200]}")
                except Exception as e:
                    try:
                        os.makedirs("/data/dlq", exist_ok=True)
                        with open(f"/data/dlq/{window_id}.json", "w") as f:
                            json.dump(payload, f)
                    except Exception:
                        pass

                last_flush = now
                flows.clear()
                arps.clear()

            await asyncio.sleep(0.001)

async def main():
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop_event.set)
    await asyncio.gather(
        health_server(),
        tick_loop(),
        switch_detection_loop(),
        inventory_update_loop()
    )

if __name__ == "__main__":
    try:
        import uvloop; uvloop.install()
    except Exception:
        pass
    asyncio.run(main())
