import asyncio, os, json, signal, time, threading, queue
from datetime import datetime, timezone
from typing import Dict, Tuple

import httpx
from pydantic import BaseModel
from scapy.all import sniff, ARP, IP, IPv6, TCP, UDP

IFACE = os.getenv("IFACE", "eth0")
BATCH_MS = int(os.getenv("BATCH_MS", "250"))
MAX_EVIDENCE_ITEMS = int(os.getenv("MAX_EVIDENCE_ITEMS", "1024"))
FILTER_BPF = os.getenv("FILTER_BPF", "arp or ip or ip6")
ANALYST_URL = os.getenv("ANALYST_URL", "http://127.0.0.1:8100/tick")
STATE_SERVER_URL = os.getenv("STATE_SERVER_URL", "http://127.0.0.1:8080")
SEED_GATEWAY_IP = os.getenv("SEED_GATEWAY_IP", "")
SEED_FIREWALL_IP = os.getenv("SEED_FIREWALL_IP", "")
HEALTH_PORT = int(os.getenv("HEALTH_PORT", "9100"))

pkt_q: "queue.Queue" = queue.Queue(maxsize=10000)
stop_event = threading.Event()

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

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
        item = parse_packet(pkt)
        if item:
            try: pkt_q.put_nowait(item)
            except queue.Full: pass
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
        return {"node_count": len(nodes), "edge_count": len(edges), "top_edges": top}
    except Exception:
        return {"node_count": 0, "edge_count": 0, "top_edges": []}

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
                for k, agg in list(flows.items()):
                    sip, dip, protocol, sport, dport = json.loads(k)
                    flow_items.append({
                        "timestamp": agg["last_ts"],
                        "src_ip": sip, "dst_ip": dip,
                        "src_port": sport, "dst_port": dport,
                        "protocol": protocol,
                        "packets": agg["packets"], "bytes": agg["bytes"]
                    })
                    if len(flow_items) >= MAX_EVIDENCE_ITEMS:
                        break

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
    await asyncio.gather(health_server(), tick_loop())

if __name__ == "__main__":
    try:
        import uvloop; uvloop.install()
    except Exception:
        pass
    asyncio.run(main())
