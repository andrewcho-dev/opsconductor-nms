# OPSCONDUCTOR-NMS — Topology & Troubleshooting Architecture

## 0) Objectives

* **Accurately show how things are connected** (L2 & L3) using **IP addresses**, not hostnames
* Discover devices that **don't support LLDP/CDP** using SNMP-based ARP+MAC correlation
* Ingest from **SSH/API** (via SuzieQ) and **SNMP** (custom poller) - no DNS dependency
* Store **raw facts**, compute **edges with confidence**, render a **clean auto-layout** map, and expose **A→B path** and **impact** queries

---

## 1) High-level architecture

```
[Collectors]
   ├─ suzieq-collector (SSH/API for LLDP/CDP/interfaces)
   ├─ snmp-poller (SNMP for ARP/MAC tables) **NEW**
   └─ adapters (future: PRTG, NetBox)
        ↓
[Normalizer]
   ├─ Parses LLDP/CDP facts → edges (confidence: 1.0)
   ├─ Correlates ARP+MAC tables → IP→Port mappings (confidence: 0.9) **NEW**
   ├─ Auto-creates device nodes for discovered IPs **NEW**
   ├─ Filters out link-local addresses (169.254.0.0/16) **NEW**
   └─ Keeps raw snapshots for evidence/debug
        ↓
[Graph Store]
   ├─ Postgres (edges/devices/interfaces; history)
   └─ Views for "current" topology (vw_edges_current, vw_links_canonical)
        ↓
[API]
   ├─ /topology/nodes, /topology/edges
   ├─ /topology/path?src_dev=...&dst_dev=...
   ├─ /topology/impact?node=...&port=...
   └─ /topology/interface?device=...&ifname=...
        ↓
[UI]
   ├─ React + elkjs (ELK layered auto-layout)
   └─ Filters (site/role), badges (method, confidence)
```

**Why this stack**

* **SuzieQ** normalizes multi-vendor data over SSH/HTTP APIs for traditional network devices
* **SNMP poller** uses standard MIBs (IP-MIB, BRIDGE-MIB) for universal device support
* **IP-based topology** removes hostname dependency and DNS issues
* **Postgres** keeps it simple, diff-friendly, and easy to join with other data
* **elkjs** gives you **deterministic, clean auto-layout**, solving React Flow auto-layout challenges

---

## 2) Data model (source-of-truth inside OpsConductor)

### 2.1 Raw facts (append-only)

* `facts_lldp`, `facts_cdp` - Link Layer Discovery Protocol data
* `facts_mac` - MAC address table (MAC→Port) **← SNMP poller**
* `facts_arp` - ARP table (IP→MAC) **← SNMP poller**
* `facts_routing` - Routing protocol adjacencies

Common columns: `collected_at`, `device`, `ifname`, `peer_device`, `peer_ifname`, `vlan`, `protocol_payload JSONB`

### 2.2 Edges (computed)

Each edge represents a **claim** that two interfaces connect.

```sql
create table edges (
  edge_id bigserial primary key,
  a_dev text not null,           -- Source device (IP or hostname)
  a_if  text not null,            -- Source interface
  b_dev text not null,            -- Target device (IP or hostname)
  b_if  text not null,            -- Target interface
  method text not null,           -- lldp|cdp|mac_arp|ospf|bgp
  confidence numeric not null,    -- 0.0–1.0
  first_seen timestamptz not null,
  last_seen  timestamptz not null,
  evidence jsonb not null         -- Minimal proof snippet(s)
);
create index on edges (a_dev, a_if);
create index on edges (b_dev, b_if);
create index on edges (method);
```

**Edge Methods & Confidence Scores**:
- `lldp` / `cdp` = 1.0 (direct neighbor protocol)
- `mac_arp` = 0.9 (ARP+MAC correlation) **← Primary discovery for non-LLDP devices**
- `ospf` / `bgp` = 0.7 (Layer 3 adjacency only)

### 2.3 Devices & interfaces

```sql
create table devices (
  name text primary key,          -- IP address or hostname
  mgmt_ip inet,                   -- Management IP address
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

**Device Auto-Creation**: The normalizer automatically creates device nodes for:
- IPs discovered in LLDP/CDP peer fields
- IPs discovered in ARP+MAC correlation (both endpoints)

### 2.4 Views

* `vw_edges_current` – latest edge per (a_dev, a_if, b_dev, b_if, method)
* `vw_links_canonical` – **one** edge per link chosen by highest confidence, with tie-breaking by method priority (lldp > cdp > mac_arp > ospf > bgp)

---

## 3) Edge confidence scoring (deterministic)

```
method weights:
  lldp/cdp = 1.00  (explicit neighbor protocol)
  mac_arp  = 0.90  (ARP+MAC correlation - very reliable)
  ospf/bgp = 0.70  (L3 adjacency only; not physical)
  inferred_flow (sFlow) = 0.60 (path corroboration)

bonuses (future):
  interface-name match pattern (Eth1/1 <-> xe-0/0/1) +0.05
  speed parity/duplex match +0.03
  stable across ≥3 collections +0.07
caps at 1.00
```

Tie-breaker: prefer methods in order `lldp/cdp > mac_arp > ospf/bgp > inferred_flow`.

---

## 4) Collectors

### 4.1 SuzieQ Collector (SSH/API)

**Container**: `opsconductor-nms-suzieq-1`  
**Port**: 8000 (internal REST API)  
**Protocol**: SSH, NETCONF, REST APIs  
**Polling Interval**: 5 minutes (configurable)

**Collected Data**:
- LLDP/CDP neighbors
- Interface status (admin/oper, speed, VLAN)
- Device information (vendor, model, OS)
- Routing tables and protocol neighbors

**Supported Platforms**: Arista EOS, Cisco IOS/IOS-XE/NX-OS, Juniper JunOS, Cumulus Linux, SONiC

**Configuration**: `inventory/devices.yaml`, `inventory/sq.yaml`

### 4.2 SNMP Poller (Universal Device Support) **NEW**

**Container**: `opsconductor-nms-snmp-poller-1`  
**Protocol**: SNMPv2c  
**Polling Interval**: 60 seconds (configurable via `POLL_INTERVAL`)

**Purpose**: Collect ARP and MAC tables from switches that don't support SSH or LLDP/CDP

**SNMP OIDs**:
- `1.3.6.1.2.1.4.35.1.4` - IP-MIB::ipNetToPhysicalPhysAddress (ARP table)
- `1.3.6.1.2.1.17.4.3.1.2` - BRIDGE-MIB::dot1dTpFdbPort (MAC address table)
- `1.3.6.1.2.1.31.1.1.1.1` - IF-MIB::ifName (interface names)
- `1.3.6.1.2.1.17.1.4.1.2` - BRIDGE-MIB::dot1dBasePortIfIndex (bridge port mapping)

**Collected Data**:
- ARP table: IP address → MAC address mappings
- MAC table: MAC address → Switch port mappings
- Interface names: Index → Interface name mappings

**Vendor Compatibility**: Any switch supporting standard SNMP MIBs (Cisco, HP, Dell, Axis, Planet, FS.com, D-Link, Ciena, etc.)

**Configuration**: Edit `services/snmp-poller/poller.py`:

```python
DEVICES = [
    {'hostname': 'axis-switch', 'ip': '10.121.19.21', 'community': 'public', 'vendor': 'Axis'},
]
```

**How It Works**:
1. Poll ARP table from switch: Get all IP→MAC mappings
2. Poll MAC table from switch: Get all MAC→Port mappings
3. Poll interface table: Map bridge port numbers to interface names
4. Write to `facts_arp` and `facts_mac` tables
5. Normalizer correlates: IP→MAC→Port = IP→Port edge

### 4.3 Optional Collectors (future)

* **sflow-ingest**: Listen for sFlow and decorates edges & path queries
* **gnmi-subscriber**: For platforms supporting OpenConfig
* **PRTG adapter**: Pull device names/roles/sites to enrich UI

**Inventory seed**: Static YAML of management subnets or device list  
**Credentials**: Read-only SSH/SNMP; store in Docker secrets

---

## 5) Normalizer Processing Pipeline

The topology normalizer runs every 5 minutes and executes the following steps:

### 5.1 Update Devices

```python
def update_devices(self):
    # Fetch device list from SuzieQ
    # INSERT/UPDATE devices table
    # Track last_seen timestamp
```

Populates: `devices` table

### 5.2 Update Interfaces

```python
def update_interfaces(self):
    # Fetch interface status from SuzieQ
    # INSERT/UPDATE interfaces table
    # Track admin_up, oper_up, speed, VLAN, IP, MAC
```

Populates: `interfaces` table

### 5.3 Process LLDP Facts

```python
def process_lldp_facts(self):
    # Fetch LLDP data from SuzieQ
    # INSERT into facts_lldp table
    # Store peer device, peer interface, chassis ID
```

Populates: `facts_lldp` table

### 5.4 Ensure LLDP Peer Nodes

```python
def ensure_lldp_peer_nodes(self):
    # Auto-create device entries for LLDP peers
    # INSERT devices discovered via LLDP but not in inventory
```

Auto-creates: Devices discovered through LLDP

### 5.5 Compute LLDP Edges

```python
def compute_edges_from_lldp(self):
    # Create edges from LLDP facts
    # Confidence: 1.0
    # Method: 'lldp'
```

Creates edges with evidence:
```json
{
  "source": "lldp",
  "local_device": "switch1",
  "local_port": "GigabitEthernet0/1",
  "remote_device": "switch2",
  "remote_port": "GigabitEthernet0/2"
}
```

### 5.6 Compute MAC Correlation Edges **NEW**

```python
def compute_edges_from_mac_correlation(self):
    # Join facts_arp + facts_mac tables
    # Correlate IP→MAC→Port
    # Create edges: DeviceIP → SwitchIP:Port
    # Confidence: 0.9
    # Method: 'mac_arp'
```

**SQL Algorithm**:
```sql
WITH switch_ports AS (
    SELECT DISTINCT
        host(d.mgmt_ip) AS switch_ip,        -- Switch IP (no /32)
        host(a.ip_addr) AS device_ip,        -- Device IP (no /32)
        a.mac_addr,
        m.ifname AS switch_port
    FROM facts_arp a
    JOIN facts_mac m ON a.mac_addr = m.mac_addr AND a.device = m.device
    JOIN devices d ON d.name = a.device
    WHERE a.collected_at > NOW() - INTERVAL '1 hour'
      AND m.collected_at > NOW() - INTERVAL '1 hour'
      AND NOT (a.ip_addr <<= '169.254.0.0/16'::inet)  -- Filter link-local
      AND d.mgmt_ip IS NOT NULL
)
INSERT INTO edges (a_dev, a_if, b_dev, b_if, method, confidence, evidence)
SELECT DISTINCT
    sp.device_ip,
    'arp-inferred',
    sp.switch_ip,
    sp.switch_port,
    'mac_arp',
    0.9,
    jsonb_build_object(
        'source', 'switch_arp_mac',
        'device_ip', sp.device_ip,
        'device_mac', sp.mac_addr::text,
        'switch_ip', sp.switch_ip,
        'switch_port', sp.switch_port
    )
FROM switch_ports sp
WHERE sp.device_ip != sp.switch_ip
```

**Key Features**:
- Uses `host()` function to strip /32 netmask from IPs
- Filters out link-local addresses (169.254.0.0/16)
- Only considers recent data (last 1 hour)
- Creates bidirectional relationship inference

### 5.7 Ensure IP Device Nodes **NEW**

```python
def ensure_ip_device_nodes(self):
    # Auto-create device entries for IPs in mac_arp edges
    # INSERT devices for both a_dev and b_dev
    # Set role='endpoint' for a_dev, role='switch' for b_dev
```

Auto-creates: Devices discovered via ARP+MAC correlation

### 5.8 Compute ARP Correlation (Disabled) **DEPRECATED**

The hostname-based ARP correlation method has been disabled in favor of the IP-only MAC correlation approach. The old method attempted to match devices by hostname, which caused issues with:
- Hostname inconsistencies
- DNS dependencies
- Duplicate device entries

---

## 6) IP-Based Topology Discovery **NEW**

### Traditional Problem

Most topology tools rely on:
1. Device hostnames from LLDP/CDP
2. DNS resolution for hostname→IP mapping
3. Consistent hostname formatting across devices

This breaks when:
- Hostnames are inconsistent (cam-cam01 vs 10.121.19.101)
- DNS is unavailable or misconfigured
- Devices don't support LLDP/CDP (cameras, IoT, embedded switches)

### OpsConductor Solution: IP-Only Discovery

**Core Insight**: Every switch maintains two tables that can be joined:
1. **ARP Table**: Maps IP addresses to MAC addresses (Layer 3→Layer 2)
2. **MAC Table**: Maps MAC addresses to switch ports (Layer 2→Layer 1)

**Join Operation**: IP → MAC → Port

**Example**:

Switch ARP table (from SNMP OID 1.3.6.1.2.1.4.35.1.4):
```
10.121.19.101 → 00:40:8c:12:34:56
10.121.19.102 → 00:40:8c:78:9a:bc
10.121.19.103 → 00:40:8c:de:f0:12
```

Switch MAC table (from SNMP OID 1.3.6.1.2.1.17.4.3.1.2):
```
00:40:8c:12:34:56 → Port 1
00:40:8c:78:9a:bc → Port 2
00:40:8c:de:f0:12 → Port 3
```

Join result:
```
10.121.19.101 → Port 1 (confidence: 0.9, method: mac_arp)
10.121.19.102 → Port 2 (confidence: 0.9, method: mac_arp)
10.121.19.103 → Port 3 (confidence: 0.9, method: mac_arp)
```

**Advantages**:
- No DNS dependency
- No hostname consistency requirement
- Works with any SNMP-capable device
- Standard MIBs supported by all vendors
- Discovers cameras, IoT devices, embedded switches

**Data Hygiene**:
- Link-local addresses (169.254.0.0/16) are filtered out
- /32 netmask is stripped for clean display
- Self-loops (device ARP entry for switch itself) are excluded

---

## 7) API surface

```
GET  /topology/nodes?site=&role=
GET  /topology/edges?site=&role=&min_conf=0.75
GET  /topology/path?src_dev=&dst_dev=&layer=2|3
GET  /topology/impact?node=&port=&layer=2|3
GET  /topology/interface?device=&ifname=
POST /netbox/sync/devices (optional)
POST /netbox/sync/cables (optional)
```

* **/nodes** returns all devices (auto-created from edges or SuzieQ)
* **/edges** returns connections with confidence filtering
* **/path** uses recursive CTE to find shortest path via canonical edges
* **/impact** performs downstream traversal to find affected devices
* **/interface** returns interface status, speed, VLAN, IP, MAC

**Response Format Example**:

`GET /topology/edges`:
```json
[
  {
    "a_dev": "10.121.19.101",
    "a_if": "arp-inferred",
    "b_dev": "10.121.19.21",
    "b_if": "Port  1",
    "method": "mac_arp",
    "confidence": 0.9,
    "evidence": {
      "source": "switch_arp_mac",
      "device_ip": "10.121.19.101",
      "device_mac": "00:40:8c:12:34:56",
      "switch_ip": "10.121.19.21",
      "switch_port": "Port  1"
    }
  }
]
```

---

## 8) UI (fix the layout pain)

* **React + elkjs** for layout; ReactFlow for rendering
* Per-edge badges: `method` + confidence color-coding
* Filters: site, role, min-confidence
* Quick tools:

  * "What's on this port?" → Click edge → Show MAC/ARP/interface details
  * "Path A→B" → Device selectors → Live hop-by-hop path
  * "Blast radius" → Click device → Show downstream dependencies

**Color Coding**:
- Green edges: confidence ≥ 0.95 (LLDP/CDP)
- Yellow edges: confidence ≥ 0.85 (ARP+MAC)
- Red edges: confidence < 0.85 (routing protocols)

**Auto-Refresh**: Topology updates every 60 seconds from API

---

## 9) Operational loop (how it works in practice)

1. **SNMP poller** snapshots ARP/MAC tables every 60 seconds → `facts_arp`, `facts_mac`
2. **SuzieQ** polls devices every 5 minutes → `facts_lldp`, `devices`, `interfaces`
3. **Normalizer** runs every 5 minutes:
   - Processes LLDP → edges (confidence: 1.0)
   - Correlates ARP+MAC → edges (confidence: 0.9)
   - Auto-creates device nodes for discovered IPs
   - Updates confidence scores and evidence
4. **API** serves latest edges via `vw_edges_current` and canonical links via `vw_links_canonical`
5. **UI** renders topology with ELK auto-layout
6. **Operator** picks device/port → sees:
   - Downstream blast radius (impact analysis)
   - Current path to destination (path query)
   - Interface details with evidence

---

## 10) Optional integrations (later)

* **sFlow collector** (read-only): Annotate edges with utilization, confirm active paths
* **PRTG adapter** (read-only): Pull device names/roles/sites to enrich UI
* **NetBox** as external SoT: Push links for exportable diagrams
* **gNMI/OpenConfig** where supported for faster interface/LLDP churn detection

---

## 11) Risks & mitigations

* **Sparse LLDP/CDP** → ✅ **Mitigated** via SNMP-based ARP+MAC correlation
* **Naming mismatches** → ✅ **Mitigated** by using IP addresses as primary identifiers
* **Link-local addresses** → ✅ **Mitigated** by filtering 169.254.0.0/16
* **Stale ARP/MAC entries** → Use 1-hour time window for correlation
* **Multi-path/port-channels** → Treat bundles as group nodes; keep member edges as evidence
* **ARP/MAC table churn** → Confidence degrades if not seen in recent polls

---

## 12) Key recommendations & confidence

* Use **SuzieQ + SNMP poller + ELK layout + Postgres** as the baseline. **Confidence: 0.95**
* **IP-only topology** removes DNS dependency and hostname issues. **Confidence: 0.95**
* Keep **edges + evidence + scores** (don't collapse too early). **Confidence: 0.90**
* **ARP+MAC correlation** works universally across all switch vendors. **Confidence: 0.90**
* Add **sFlow** only if you want real-time path corroboration. **Confidence: 0.70**
* NetBox sync is **optional** for pretty exports; don't block on it. **Confidence: 0.80**

---

## 13) Performance Considerations

**Database Indexing**:
```sql
CREATE INDEX idx_facts_arp_collected ON facts_arp (collected_at);
CREATE INDEX idx_facts_mac_collected ON facts_mac (collected_at);
CREATE INDEX idx_facts_arp_mac ON facts_arp (mac_addr);
CREATE INDEX idx_facts_mac_mac ON facts_mac (mac_addr);
```

**Data Retention**:
- Keep facts for 7 days (configurable)
- Edges retained indefinitely (historical analysis)
- Prune old facts with cron job: `DELETE FROM facts_arp WHERE collected_at < NOW() - INTERVAL '7 days'`

**Query Optimization**:
- Use `vw_edges_current` for latest topology
- Use `vw_links_canonical` for path/impact queries
- Index on `(a_dev, a_if, b_dev, b_if)` for fast edge lookups

---

## 14) Security Best Practices

1. **SNMP Community Strings**: Change from "public" to secure strings
2. **Docker Secrets**: Store credentials in `/run/secrets/`, not environment variables
3. **SSH Keys**: Use key-based auth instead of passwords for SuzieQ
4. **Read-Only Access**: Collectors only need read-only SNMP/SSH access
5. **Network Segmentation**: Run collectors in management VLAN
6. **Rate Limiting**: API has 100 requests/minute limit (configurable)
7. **TLS**: Enable HTTPS for production deployments
8. **Authentication**: Add OAuth2/JWT for API access (not included in baseline)

---

## 15) Troubleshooting Decision Tree

**Device not in topology?**
1. Is it in `inventory/devices.yaml`? → Add it
2. Is it reachable via SSH? → Check credentials
3. Is it SNMP-capable? → Add to `snmp-poller/poller.py`
4. Check `SELECT * FROM devices WHERE name LIKE '%device%'`

**Missing edges?**
1. LLDP/CDP enabled? → Check `SELECT * FROM facts_lldp`
2. SNMP poller running? → Check `docker compose logs snmp-poller`
3. Recent ARP/MAC data? → Check `SELECT * FROM facts_arp WHERE collected_at > NOW() - INTERVAL '1 hour'`
4. Check `SELECT * FROM edges WHERE a_dev = 'device' OR b_dev = 'device'`

**Low confidence edges?**
- Expected for routing protocols (OSPF/BGP = 0.7)
- ARP+MAC correlation should be 0.9
- LLDP/CDP should be 1.0
- Check evidence JSONB for details

---

## 16) Future Enhancements

* **Multi-VLAN support**: Track VLAN membership in ARP/MAC correlation
* **Historical playback**: Show topology at specific point in time
* **Change detection**: Alert on new devices, removed edges, port status changes
* **Port-channel handling**: Detect LAG/MLAG and represent as single logical link
* **Automated testing**: Pytest fixtures for ARP/MAC correlation edge cases
* **Metrics export**: Prometheus metrics for polling success rate, edge counts, confidence distribution
* **Webhook notifications**: Alert external systems when topology changes

---

## Appendix A: SNMP MIB Reference

### IP-MIB (RFC 4293)

**OID**: `1.3.6.1.2.1.4.35.1.4` - ipNetToPhysicalPhysAddress  
**Purpose**: ARP table (IP→MAC mapping)  
**Type**: OCTET STRING (MAC address in hex)

### BRIDGE-MIB (RFC 4188)

**OID**: `1.3.6.1.2.1.17.4.3.1.2` - dot1dTpFdbPort  
**Purpose**: MAC address table (MAC→Port mapping)  
**Type**: INTEGER (bridge port number)

**OID**: `1.3.6.1.2.1.17.1.4.1.2` - dot1dBasePortIfIndex  
**Purpose**: Bridge port to interface index mapping  
**Type**: INTEGER (interface index)

### IF-MIB (RFC 2863)

**OID**: `1.3.6.1.2.1.31.1.1.1.1` - ifName  
**Purpose**: Interface names  
**Type**: DisplayString (interface name like "GigabitEthernet0/1")

---

## Appendix B: Database Schema Cheat Sheet

**Find all devices on a switch**:
```sql
SELECT DISTINCT a_dev AS device, a_if AS port, confidence
FROM edges
WHERE b_dev = '10.121.19.21' AND method = 'mac_arp'
ORDER BY a_if;
```

**Find switch port for specific IP**:
```sql
SELECT b_dev AS switch, b_if AS port, confidence, evidence
FROM edges
WHERE a_dev = '10.121.19.101' AND method = 'mac_arp';
```

**Show topology by discovery method**:
```sql
SELECT method, COUNT(*) AS edge_count, AVG(confidence) AS avg_confidence
FROM edges
GROUP BY method
ORDER BY avg_confidence DESC;
```

**Recent ARP changes**:
```sql
SELECT device, ip_addr, mac_addr, collected_at
FROM facts_arp
WHERE collected_at > NOW() - INTERVAL '1 hour'
ORDER BY collected_at DESC;
```

**Find MAC address location**:
```sql
SELECT m.device AS switch, m.ifname AS port, a.ip_addr
FROM facts_mac m
LEFT JOIN facts_arp a ON m.mac_addr = a.mac_addr AND m.device = a.device
WHERE m.mac_addr = '00:40:8c:12:34:56'
ORDER BY m.collected_at DESC
LIMIT 1;
```
