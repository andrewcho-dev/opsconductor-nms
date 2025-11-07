# OPSCONDUCTOR-NMS — Topology & Troubleshooting Architecture

## 0) Objectives

* **Accurately show how things are connected** (L2 & L3) for rapid downstream/blast-radius troubleshooting—even when devices don't support SNMP.
* Ingest from **SSH/API** first (via SuzieQ), with optional SNMP/gNMI/sFlow add-ons.
* Store **raw facts**, compute **edges with confidence**, render a **clean auto-layout** map, and expose **A→B path** and **impact** queries.

---

## 1) High-level architecture

```
[Collectors]
   ├─ suzieq-collector (SSH/API; optional SNMP/gNMI)
   ├─ sflow-ingest (optional)
   └─ adapters (future: PRTG, NetBox)
        ↓
[Normalizer]
   ├─ Parses facts → (neighbors, mac, arp, routes)
   ├─ Emits edges {a_dev,a_if,b_dev,b_if,method,confidence}
   └─ Keeps raw snapshots for evidence/debug
        ↓
[Graph Store]
   ├─ Postgres (edges/devices/interfaces; history)
   └─ Materialized views for "current" topology
        ↓
[API]
   ├─ /topology/nodes, /topology/edges
   ├─ /topology/path?src=...&dst=...
   └─ /topology/impact?node=...&port=...
        ↓
[UI]
   ├─ React + elkjs (ELK layered auto-layout)
   └─ Filters (site/role/vlan), badges (method, confidence)
```

**Why this stack**

* SuzieQ normalizes multi-vendor data over **SSH/HTTP APIs**, so you're not blocked by SNMP.
* Postgres keeps it simple, diff-friendly, and easy to join with your other OpsConductor data.
* elkjs gives you **deterministic, clean auto-layout**, solving the React Flow auto-layout pain.

---

## 2) Data model (source-of-truth inside OpsConductor)

### 2.1 Raw facts (append-only)

* `facts_lldp`, `facts_cdp`, `facts_mac`, `facts_arp`, `facts_routing`
* Common columns: `collected_at`, `device`, `ifname`, `peer_device`, `peer_ifname`, `vlan`, `vrf`, `protocol_payload JSONB`

### 2.2 Edges (computed)

Each edge represents a **claim** that two interfaces connect.

```sql
create table edges (
  edge_id bigserial primary key,
  a_dev text not null,
  a_if  text not null,
  b_dev text not null,
  b_if  text not null,
  method text not null,         -- lldp|cdp|mac_arp|ospf|bgp|inferred_flow
  confidence numeric not null,  -- 0.0–1.0
  first_seen timestamptz not null,
  last_seen  timestamptz not null,
  evidence jsonb not null       -- minimal proof snippet(s)
);
create index on edges (a_dev, a_if);
create index on edges (b_dev, b_if);
```

### 2.3 Devices & interfaces

```sql
create table devices (
  name text primary key,
  mgmt_ip inet,
  vendor text, model text, os_version text,
  role text, site text, last_seen timestamptz
);

create table interfaces (
  device text references devices(name),
  ifname text,
  admin_up bool, oper_up bool, speed_mbps int, vlan text,
  l3_addr inet, l2_mac macaddr,
  primary key (device, ifname)
);
```

### 2.4 Views

* `vw_edges_current` – latest edge per (a_dev,a_if,b_dev,b_if,method).
* `vw_links_canonical` – **one** edge per link chosen by score (see §3).

---

## 3) Edge confidence scoring (deterministic)

```
method weights:
  lldp/cdp = 1.00
  mac_arp  = 0.85  (same VLAN, symmetric MAC location)
  ospf/bgp = 0.70  (L3 adjacency only; not physical)
  inferred_flow (sFlow) = 0.60 (path corroboration)

bonuses:
  interface-name match pattern (Eth1/1 <-> xe-0/0/1) +0.05
  speed parity/duplex match +0.03
  stable across ≥3 collections +0.07
caps at 1.00
```

Tie-breaker: prefer methods in order `lldp/cdp > mac_arp > ospf/bgp > inferred_flow`.

---

## 4) Collectors (default = SNMP-optional)

* **suzieq-collector** (Docker): pulls `lldp/cdp`, `mac`, `arp`, and routing neighbors over SSH/API.
* **sflow-ingest** (optional): listens for sFlow and decorates edges & path queries.
* **gnmi-subscriber** (optional): if some platforms support OpenConfig.

Inventory seed: **static YAML** of mgmt subnets or device list (no PRTG export).
Credentials: read-only SSH per vendor; store in Docker secrets.

---

## 5) API surface

```
GET  /topology/nodes?site=&role=
GET  /topology/edges?site=&role=&min_conf=0.75
GET  /topology/path?src_dev=&src_if=&dst_dev=&dst_if=&layer=2|3
GET  /topology/impact?node=&port=&layer=2|3
POST /adapters/netbox/push   (optional)
```

* **/path** chooses canonical edges (by layer) and returns ordered hops with evidence.
* **/impact** returns all downstream nodes (L2 by MAC/VLAN; L3 by routing adjacency).

---

## 6) UI (fix the layout pain)

* **React + elkjs** for layout; keep React Flow or plain SVG—ELK handles auto-layout.
* Per-edge badges: `method` + confidence bar.
* Filters: site, role, VLAN, layer (L2/L3), min-confidence.
* Quick tools:

  * "What's on this port?" → MAC/ARP leaf list.
  * "Path A→B" → live hops + likely bottleneck (if sFlow present).
  * "Blast radius" → nodes lost if `(device|port)` fails.

---

## 7) Operational loop (how it works in practice)

1. Collector snapshots facts.
2. Normalizer computes/updates edges + evidence + scores.
3. API serves canonical links; UI renders with ELK.
4. Operator picks device/port → sees **downstream blast radius** and **current path**.

---

## 8) Optional integrations (later)

* **PRTG adapter** (read-only): pull device names/roles/sites to enrich UI (no exports required now).
* **NetBox** as external SoT: push links for pretty/exportable diagrams.
* **gNMI/OpenConfig** where supported for faster interface/LLDP churn detection.

---

## 9) Risks & mitigations

* **Sparse LLDP/CDP** → fall back to **MAC/ARP correlation** and lift confidence once stable across polls.
* **Naming mismatches** → maintain a `name_map` table (aliases, FQDN ↔ shortname).
* **Multi-path/port-channels** → treat bundles as group nodes; keep member edges as evidence.

---

## 10) Key recommendations & confidence

* Use **SuzieQ + ELK layout + Postgres** as the baseline (no PRTG export). **Confidence: 0.9**
* Keep **edges + evidence + scores** (don't collapse too early). **Confidence: 0.85**
* Add **sFlow** only if you want real-time path corroboration. **Confidence: 0.7**
* NetBox sync is **optional** for pretty exports; don't block on it. **Confidence: 0.8**
