# OpsConductor NMS - Complete Repository Documentation

## Table of Contents

1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Services](#services)
4. [Data Model](#data-model)
5. [Topology Discovery Methods](#topology-discovery-methods)
6. [Installation & Configuration](#installation--configuration)
7. [API Reference](#api-reference)
8. [Database Schema](#database-schema)
9. [Development](#development)
10. [Troubleshooting](#troubleshooting)

---

## Overview

OpsConductor NMS is a network management system that provides **IP-address-based topology discovery** without relying on device hostnames. It combines data from multiple sources (LLDP, CDP, SNMP ARP/MAC tables) to build an accurate Layer 2/Layer 3 network topology map.

### Key Features

- **IP-Only Topology**: Displays devices by IP address, not hostname
- **SNMP-Based Discovery**: Uses standard MIBs (IP-MIB, BRIDGE-MIB) for ARP/MAC correlation
- **Multi-Method Discovery**: LLDP/CDP for direct neighbors, ARP+MAC for non-LLDP devices
- **Confidence Scoring**: Each edge has a 0.0-1.0 confidence score based on discovery method
- **Auto-Layout Visualization**: React-based UI with ELK graph layout
- **Path Analysis**: Find Layer 2/3 paths between any two devices
- **Impact Analysis**: Determine blast radius of device/port failures
- **Vendor-Agnostic**: Works with Cisco, Juniper, Arista, Axis, Planet, FS.com, D-Link, Ciena, and more

### Design Philosophy

**Traditional approach (hostname-based):**
- Requires DNS/hostname resolution
- Breaks when hostnames are inconsistent
- Needs LLDP/CDP on all devices

**OpsConductor approach (IP-based):**
- Uses IP addresses as primary identifiers
- Correlates ARP tables (IP→MAC) with MAC tables (MAC→Port)
- Works even when LLDP/CDP is unavailable
- Filters out link-local addresses (169.254.0.0/16)
- No /32 netmask clutter in display

---

## Architecture

### High-Level Components

```
┌─────────────────────────────────────────────────────────────┐
│                    DATA COLLECTORS                          │
├─────────────────────┬───────────────────────────────────────┤
│  SuzieQ (SSH/API)   │  SNMP Poller (ARP/MAC Tables)        │
│  - LLDP/CDP facts   │  - IP-MIB (ARP)                      │
│  - Interface data   │  - BRIDGE-MIB (MAC)                  │
│  - Device info      │  - IF-MIB (interfaces)               │
└──────────┬──────────┴───────────────┬───────────────────────┘
           │                          │
           v                          v
┌──────────────────────────────────────────────────────────────┐
│                    POSTGRESQL DATABASE                       │
│  ┌────────────┐  ┌──────────────┐  ┌────────────────────┐  │
│  │  devices   │  │  interfaces  │  │  facts_arp         │  │
│  │  edges     │  │  facts_lldp  │  │  facts_mac         │  │
│  └────────────┘  └──────────────┘  └────────────────────┘  │
└──────────┬───────────────────────────────────────────────────┘
           │
           v
┌──────────────────────────────────────────────────────────────┐
│               TOPOLOGY NORMALIZER SERVICE                    │
│  - Processes LLDP/CDP facts → edges                         │
│  - Correlates ARP+MAC tables → IP→Port mappings             │
│  - Computes confidence scores                                │
│  - Auto-creates device nodes for discovered IPs             │
│  - Runs every 5 minutes                                     │
└──────────┬───────────────────────────────────────────────────┘
           │
           v
┌──────────────────────────────────────────────────────────────┐
│                      FASTAPI REST API                        │
│  GET /topology/nodes      - List devices                    │
│  GET /topology/edges      - List connections                │
│  GET /topology/path       - Find path A→B                   │
│  GET /topology/impact     - Blast radius analysis           │
│  GET /topology/interface  - Interface details               │
└──────────┬───────────────────────────────────────────────────┘
           │
           v
┌──────────────────────────────────────────────────────────────┐
│                  REACT WEB UI (Port 8089)                   │
│  - Real-time topology visualization                         │
│  - ELK graph auto-layout                                    │
│  - Path query interface                                     │
│  - Impact analysis                                          │
│  - Edge confidence indicators                               │
└──────────────────────────────────────────────────────────────┘
```

### Why This Stack?

- **PostgreSQL**: Relational database with excellent JSON support, temporal queries, and CTEs for path finding
- **SuzieQ**: Multi-vendor SSH/API collector that normalizes data from Cisco, Juniper, Arista, etc.
- **SNMP**: Universal protocol supported by all network devices, uses standard MIBs
- **FastAPI**: Modern async Python framework with automatic OpenAPI documentation
- **React + ELK**: Deterministic graph layout that scales to 100+ nodes

---

## Services

### 1. Database (PostgreSQL 16)

**Purpose**: Central data store for topology facts and computed edges

**Container**: `opsconductor-nms-db-1`
**Port**: 5432 (internal only)
**Volume**: `db-data` (persistent storage)
**Credentials**: Docker secrets (`secrets/db_user.txt`, `secrets/db_password.txt`)

**Tables**:
- `devices` - Network device inventory
- `interfaces` - Interface status and configuration
- `edges` - Computed topology connections
- `facts_lldp` - LLDP neighbor data
- `facts_cdp` - CDP neighbor data
- `facts_arp` - ARP table entries (IP→MAC)
- `facts_mac` - MAC address table (MAC→Port)
- `facts_routing` - Routing protocol adjacencies

### 2. SuzieQ Collector

**Purpose**: Collects network data via SSH/API from traditional network devices

**Container**: `opsconductor-nms-suzieq-1`
**Port**: 8000 (internal API)
**Configuration**: `inventory/devices.yaml`, `inventory/sq.yaml`
**Data Sources**: SSH, NETCONF, REST APIs

**Collected Data**:
- LLDP/CDP neighbors
- Interface status (admin/oper up/down, speed, VLAN)
- Device information (vendor, model, OS version)
- Routing tables and protocol neighbors

**Supported Platforms**: Arista EOS, Cisco IOS/IOS-XE/NX-OS, Juniper JunOS, Cumulus Linux, SONiC

**Polling Interval**: 5 minutes (configurable in `inventory/sq.yaml`)

### 3. SNMP Poller

**Purpose**: Collects ARP and MAC tables from switches that don't support SSH (e.g., Axis cameras, embedded switches)

**Container**: `opsconductor-nms-snmp-poller-1`
**Protocol**: SNMPv2c
**Polling Interval**: 60 seconds (configurable via `POLL_INTERVAL` env var)

**SNMP OIDs Used**:
- `1.3.6.1.2.1.4.35.1.4` - IP-MIB::ipNetToPhysicalPhysAddress (ARP table)
- `1.3.6.1.2.1.17.4.3.1.2` - BRIDGE-MIB::dot1dTpFdbPort (MAC address table)
- `1.3.6.1.2.1.31.1.1.1.1` - IF-MIB::ifName (interface names)
- `1.3.6.1.2.1.17.1.4.1.2` - BRIDGE-MIB::dot1dBasePortIfIndex (bridge port mapping)

**Configuration**: Edit `services/snmp-poller/poller.py` and modify the `DEVICES` array:

```python
DEVICES = [
    {'hostname': 'axis-switch', 'ip': '10.121.19.21', 'community': 'public', 'vendor': 'Axis'},
]
```

**Device Identity & Hostname Mapping**:
- Devices are created with **IP address** as the canonical `name` field (e.g., `10.121.19.21`)
- If a hostname is provided, creates a `hostname_mappings` entry: `axis-switch` → `10.121.19.21`
- This allows LLDP neighbors reporting "axis-switch" to be resolved to the IP address for consistent topology
- Prevents duplicate device nodes (one by hostname, one by IP)

**Vendor Compatibility**: Any SNMP-capable switch (Cisco, HP, Dell, Axis, Planet, FS.com, D-Link, Ciena, etc.)

### 4. Topology Normalizer

**Purpose**: Processes raw facts and computes topology edges with confidence scores

**Container**: `opsconductor-nms-topo-normalizer-1`
**Language**: Python 3
**Run Interval**: 300 seconds (5 minutes)

**Processing Pipeline**:

1. **Update Devices** - Sync device inventory from SuzieQ
2. **Update Interfaces** - Sync interface status from SuzieQ
3. **Process LLDP Facts** - Extract LLDP neighbor relationships
4. **Ensure LLDP Peer Nodes** - Auto-create devices for discovered peers
5. **Compute LLDP Edges** - Create edges from LLDP data (confidence: 1.0)
6. **Compute MAC Correlation Edges** - Join ARP+MAC tables to map IP→Port (confidence: 0.9)
7. **Ensure IP Device Nodes** - Auto-create device entries for IPs in edges

**MAC Correlation Algorithm**:

```sql
-- Step 1: Join ARP table (IP→MAC) with MAC table (MAC→Port)
SELECT 
    arp.ip_addr AS device_ip,
    mac.ifname AS switch_port,
    switch.mgmt_ip AS switch_ip
FROM facts_arp arp
JOIN facts_mac mac ON arp.mac_addr = mac.mac_addr AND arp.device = mac.device
JOIN devices switch ON switch.name = arp.device
WHERE arp.ip_addr NOT IN ('169.254.0.0/16')  -- Filter link-local
  AND switch.mgmt_ip IS NOT NULL

-- Step 2: Create edge from device_ip → switch_ip:switch_port
INSERT INTO edges (a_dev, a_if, b_dev, b_if, method, confidence)
VALUES (device_ip, 'arp-inferred', switch_ip, switch_port, 'mac_arp', 0.9)
```

**IP Address Handling**:
- Uses PostgreSQL `host()` function to strip /32 netmask
- Filters out link-local addresses (169.254.0.0/16)
- Auto-creates device nodes for all discovered IPs

### 5. REST API

**Purpose**: Exposes topology data via HTTP REST endpoints

**Container**: `opsconductor-nms-api-1`
**Framework**: FastAPI (Python async)
**Port**: 8088
**Documentation**: http://localhost:8088/docs (Swagger UI)

**Endpoints**:

- `GET /topology/nodes` - List devices with optional filters (site, role)
- `GET /topology/edges` - List edges with optional filters (site, role, min_confidence)
- `GET /topology/path` - Find shortest path between two devices using recursive CTE
- `GET /topology/impact` - Calculate downstream impact of device/port failure
- `GET /topology/interface` - Get interface details (status, speed, VLAN, IP, MAC)
- `GET /healthz` - Health check endpoint
- `POST /netbox/sync/devices` - Sync devices to NetBox (optional)
- `POST /netbox/sync/cables` - Sync edges to NetBox as cables (optional)

**Database Connection**:
- Uses asyncpg for async PostgreSQL queries
- Connection pooling (min=5, max=20, timeout=30s)
- Automatic retry on connection failure

### 6. Web UI

**Purpose**: Interactive topology visualization and query interface

**Container**: `opsconductor-nms-ui-1`
**Framework**: React 18 + Vite
**Port**: 8089
**Graph Library**: ReactFlow + elkjs (ELK Layered Layout)

**Features**:

- **Topology Map**: Auto-laid-out graph with nodes (devices) and edges (connections)
- **Color Coding**: Edges colored by confidence (green=high, yellow=medium, red=low)
- **Auto-Refresh**: Polls API every 60 seconds for topology updates
- **Path Query**: Select source/destination devices to find path
- **Impact Analysis**: Click device to see downstream dependencies
- **Port Details**: Click edge to see interface details and discovery evidence

**UI Components**:
- `TopologyMap.jsx` - Main topology visualization
- `App.jsx` - Root component with tabs

---

## Data Model

### Core Tables

#### devices

```sql
CREATE TABLE devices (
    name TEXT PRIMARY KEY,              -- IP address or hostname
    mgmt_ip INET,                       -- Management IP address
    vendor TEXT,                        -- Vendor name (Cisco, Juniper, etc.)
    model TEXT,                         -- Device model
    os_version TEXT,                    -- OS version
    role TEXT,                          -- Device role (switch, router, endpoint)
    site TEXT,                          -- Site/location
    last_seen TIMESTAMPTZ               -- Last poll time
);
```

**Purpose**: Central device inventory
**Auto-Populated By**: SuzieQ collector, SNMP poller, normalizer (for discovered IPs)
**Device Identity**: All devices use **IP addresses** as their canonical `name` field. Hostnames are stored separately in `hostname_mappings` table.

#### hostname_mappings

```sql
CREATE TABLE hostname_mappings (
    hostname TEXT PRIMARY KEY,              -- Device hostname
    ip_address TEXT NOT NULL                -- Canonical IP address
);

CREATE INDEX idx_hostname_mappings_ip ON hostname_mappings (ip_address);
```

**Purpose**: Maps device hostnames to their canonical IP addresses
**Why Needed**: LLDP/CDP neighbors report system names (hostnames), but we need to resolve them to IP addresses for consistent topology
**Populated By**: 
- SNMP poller: Creates mappings when polling devices with both hostname and IP
- Topology normalizer: Correlates LLDP peer hostnames with IPs from ARP/MAC tables

**Example Mapping**:
```sql
INSERT INTO hostname_mappings (hostname, ip_address) VALUES 
    ('axis-switch', '10.121.19.21'),
    ('cam-cam01', '10.121.19.101'),
    ('cam-cam02', '10.121.19.102');
```

**Usage**: When LLDP reports a peer device as "cam-cam01", the normalizer resolves it to "10.121.19.101" before creating edges, preventing duplicate device nodes.

#### interfaces

```sql
CREATE TABLE interfaces (
    device TEXT REFERENCES devices(name) ON DELETE CASCADE,
    ifname TEXT,                        -- Interface name (e.g., GigabitEthernet0/0)
    admin_up BOOLEAN,                   -- Administratively up
    oper_up BOOLEAN,                    -- Operationally up
    speed_mbps INTEGER,                 -- Interface speed in Mbps
    vlan TEXT,                          -- VLAN ID
    l3_addr INET,                       -- Layer 3 IP address
    l2_mac MACADDR,                     -- Layer 2 MAC address
    last_seen TIMESTAMPTZ,              -- Last poll time
    PRIMARY KEY (device, ifname)
);
```

**Purpose**: Interface status and configuration
**Populated By**: SuzieQ collector, SNMP poller

#### edges

```sql
CREATE TABLE edges (
    edge_id BIGSERIAL PRIMARY KEY,
    a_dev TEXT NOT NULL,                -- Source device (IP or hostname)
    a_if TEXT NOT NULL,                 -- Source interface
    b_dev TEXT NOT NULL,                -- Target device (IP or hostname)
    b_if TEXT NOT NULL,                 -- Target interface
    method TEXT NOT NULL CHECK (method IN ('lldp', 'cdp', 'mac_arp', 'ospf', 'bgp')),
    confidence NUMERIC NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
    evidence JSONB NOT NULL,            -- Proof of connection
    first_seen TIMESTAMPTZ NOT NULL,    -- First discovery time
    last_seen TIMESTAMPTZ NOT NULL,     -- Most recent confirmation
    UNIQUE (a_dev, a_if, b_dev, b_if)
);

CREATE INDEX idx_edges_a ON edges (a_dev, a_if);
CREATE INDEX idx_edges_b ON edges (b_dev, b_if);
CREATE INDEX idx_edges_method ON edges (method);
```

**Purpose**: Topology connections with confidence scoring
**Populated By**: Topology normalizer

**Edge Methods**:
- `lldp` - LLDP neighbor discovery (confidence: 1.0)
- `cdp` - CDP neighbor discovery (confidence: 1.0)
- `mac_arp` - ARP+MAC correlation (confidence: 0.9)
- `ospf` - OSPF adjacency (confidence: 0.7)
- `bgp` - BGP peering (confidence: 0.7)

### Facts Tables

#### facts_arp

```sql
CREATE TABLE facts_arp (
    device TEXT NOT NULL,               -- Device that has this ARP entry
    ip_addr INET NOT NULL,              -- IP address
    mac_addr MACADDR NOT NULL,          -- MAC address
    vlan TEXT,                          -- VLAN ID
    collected_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_facts_arp_device ON facts_arp (device);
CREATE INDEX idx_facts_arp_mac ON facts_arp (mac_addr);
CREATE INDEX idx_facts_arp_collected ON facts_arp (collected_at);
```

**Purpose**: ARP table snapshots (IP→MAC mappings)
**Populated By**: SNMP poller
**Retention**: Older entries retained for historical analysis

#### facts_mac

```sql
CREATE TABLE facts_mac (
    device TEXT NOT NULL,               -- Switch device name
    ifname TEXT NOT NULL,               -- Switch port
    mac_addr MACADDR NOT NULL,          -- MAC address
    vlan TEXT,                          -- VLAN ID
    collected_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_facts_mac_device ON facts_mac (device);
CREATE INDEX idx_facts_mac_mac ON facts_mac (mac_addr);
CREATE INDEX idx_facts_mac_collected ON facts_mac (collected_at);
```

**Purpose**: MAC address table snapshots (MAC→Port mappings)
**Populated By**: SNMP poller
**Correlation**: Joined with facts_arp to determine IP→Port mappings

#### facts_lldp

```sql
CREATE TABLE facts_lldp (
    device TEXT NOT NULL,               -- Local device
    ifname TEXT NOT NULL,               -- Local interface
    peer_device TEXT NOT NULL,          -- Remote device
    peer_ifname TEXT NOT NULL,          -- Remote interface
    peer_type TEXT,                     -- Chassis type
    protocol_payload JSONB,             -- Full LLDP TLVs
    collected_at TIMESTAMPTZ DEFAULT NOW()
);
```

**Purpose**: LLDP neighbor data
**Populated By**: SuzieQ collector (from network device LLDP tables)

### Views

#### vw_edges_current

```sql
CREATE VIEW vw_edges_current AS
SELECT DISTINCT ON (a_dev, a_if, b_dev, b_if, method)
    edge_id, a_dev, a_if, b_dev, b_if, method, confidence, evidence, first_seen, last_seen
FROM edges
ORDER BY a_dev, a_if, b_dev, b_if, method, last_seen DESC;
```

**Purpose**: Latest edge per unique connection/method combination
**Used By**: API queries, UI visualization

#### vw_links_canonical

```sql
CREATE OR REPLACE VIEW vw_links_canonical AS
WITH scored_edges AS (
  SELECT
    *,
    ROW_NUMBER() OVER (
      PARTITION BY 
        LEAST(a_dev, b_dev),
        GREATEST(a_dev, b_dev)
      ORDER BY 
        confidence DESC,
        CASE method
          WHEN 'lldp' THEN 1
          WHEN 'cdp' THEN 2
          WHEN 'mac_arp' THEN 3
          WHEN 'ospf' THEN 4
          WHEN 'bgp' THEN 5
          WHEN 'inferred_flow' THEN 6
        END,
        last_seen DESC
    ) AS rn
  FROM vw_edges_current
)
SELECT
  edge_id, a_dev, a_if, b_dev, b_if, method, confidence, first_seen, last_seen, evidence
FROM scored_edges
WHERE rn = 1;
```

**Purpose**: Single highest-confidence edge per device pair (deduplicates LLDP vs MAC_ARP)
**Key Change**: Partitions by **device pair only** (not interface pair), ensuring only one edge is shown between any two devices
**Example**: If both LLDP (confidence 1.0) and MAC_ARP (confidence 0.9) edges exist between the same device pair, only the LLDP edge is returned
**Used By**: `/topology/edges` API endpoint, UI visualization, path queries, impact analysis

---

## Topology Discovery Methods

### Method 1: LLDP/CDP Discovery

**Confidence**: 1.0 (highest)
**Source**: SuzieQ collector via SSH/API
**Best For**: Modern network devices with LLDP/CDP enabled

**How It Works**:
1. SuzieQ polls devices via SSH
2. Executes vendor-specific commands (e.g., `show lldp neighbors` on Cisco)
3. Normalizes output to standard format
4. Writes to `facts_lldp` table with peer device **hostnames** (e.g., "cam-cam01")
5. Normalizer resolves peer hostnames to IP addresses using:
   - `hostname_mappings` table (populated by SNMP poller)
   - ARP/MAC correlation (matches LLDP chassis_id MAC with ARP table)
6. Creates edges with resolved IP addresses: method='lldp', confidence=1.0

**Hostname Resolution**: LLDP peers are reported by system name (hostname), but all edges use IP addresses as device identifiers. The normalizer performs hostname→IP resolution **before** creating edges to prevent duplicate device nodes.

**Requirements**:
- LLDP or CDP must be enabled on devices
- SSH access required
- Device must be in `inventory/devices.yaml`

**Example Edge Evidence**:
```json
{
  "source": "lldp",
  "local_device": "switch1",
  "local_port": "GigabitEthernet0/1",
  "remote_device": "switch2",
  "remote_port": "GigabitEthernet0/2",
  "chassis_id": "00:1a:2b:3c:4d:5e"
}
```

### Method 2: ARP+MAC Correlation (IP-Only Topology)

**Confidence**: 0.9
**Source**: SNMP poller
**Best For**: Devices without LLDP/CDP (cameras, IoT, embedded switches)

**How It Works**:
1. SNMP poller collects ARP table from switch: `IP → MAC`
2. SNMP poller collects MAC table from switch: `MAC → Port`
3. Normalizer joins tables: `IP → MAC → Port`
4. Creates edge from `IP` to `Switch:Port`
5. Uses `host()` function to strip /32 netmask

**SQL Algorithm**:
```sql
-- Collect switch port mappings
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
      AND NOT (a.ip_addr <<= '169.254.0.0/16'::inet)  -- Exclude link-local
      AND d.mgmt_ip IS NOT NULL
)
-- Create edges
INSERT INTO edges (a_dev, a_if, b_dev, b_if, method, confidence, evidence)
SELECT DISTINCT
    sp.device_ip,           -- Source: device IP
    'arp-inferred',         -- Source interface (virtual)
    sp.switch_ip,           -- Target: switch IP
    sp.switch_port,         -- Target interface (physical port)
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
WHERE sp.device_ip != sp.switch_ip  -- Don't create self-loop
```

**Link-Local Filtering**:
Link-local addresses (169.254.0.0/16) are automatically filtered because:
- They're auto-assigned, not meaningful network addresses
- Create visual clutter
- Don't represent real network topology

**Example Edge Evidence**:
```json
{
  "source": "switch_arp_mac",
  "device_ip": "10.121.19.101",
  "device_mac": "00:40:8c:12:34:56",
  "switch_ip": "10.121.19.21",
  "switch_port": "Port  1"
}
```

**Real-World Example**:

Switch ARP table shows:
```
10.121.19.101 → 00:40:8c:12:34:56
10.121.19.102 → 00:40:8c:78:9a:bc
```

Switch MAC table shows:
```
00:40:8c:12:34:56 → Port 1
00:40:8c:78:9a:bc → Port 2
```

Result: Two edges created:
- `10.121.19.101` → `10.121.19.21:Port 1`
- `10.121.19.102` → `10.121.19.21:Port 2`

### Method 3: OSPF/BGP Adjacency

**Confidence**: 0.7
**Source**: SuzieQ collector
**Best For**: Layer 3 router peering relationships

**How It Works**:
1. SuzieQ polls routing protocols
2. Extracts neighbor relationships
3. Creates Layer 3 edges (not physical topology)

**Limitation**: Shows routing adjacency, not physical cabling

---

## Installation & Configuration

### Prerequisites

- Docker 20.10+
- Docker Compose 2.0+
- 4GB RAM minimum
- 20GB disk space

### Quick Start

```bash
# Clone repository
git clone https://github.com/andrewcho-dev/opsconductor-nms.git
cd opsconductor-nms

# Create secrets
mkdir -p secrets
echo "oc" > secrets/db_user.txt
echo "your-secure-password" > secrets/db_password.txt

# Start all services
docker compose up -d

# Check status
docker compose ps

# View logs
docker compose logs -f
```

**Access Points**:
- UI: http://localhost:8089
- API: http://localhost:8088
- API Docs: http://localhost:8088/docs

### Configure SuzieQ (SSH-Based Devices)

Edit `inventory/devices.yaml`:

```yaml
---
- name: core-router
  transport: ssh
  address: 10.120.0.1
  username: admin
  password: admin123
  devtype: iosxe

- name: dist-switch
  transport: ssh
  address: 10.120.0.2
  username: admin
  keyfile: /secrets/id_rsa
  devtype: nxos
```

**Supported Device Types**: `eos`, `iosxe`, `ios`, `nxos`, `junos`, `cumulus`, `sonic`

### Configure SNMP Poller (Non-SSH Devices)

Edit `services/snmp-poller/poller.py`:

```python
DEVICES = [
    {'hostname': 'axis-switch', 'ip': '10.121.19.21', 'community': 'public', 'vendor': 'Axis'},
    {'hostname': 'camera-switch', 'ip': '10.121.20.1', 'community': 'public', 'vendor': 'Planet'},
]
```

Restart the SNMP poller:

```bash
docker compose restart snmp-poller
```

### Environment Variables

Create `.env` file:

```bash
# Database
DB_HOST=db
DB_NAME=opsconductor
DB_USER=oc
DB_PASS=<read-from-secrets>

# SuzieQ
SUZIEQ_URL=http://suzieq:8000
SUZIEQ_API_KEY=opsconductor-dev-key-12345

# SNMP Poller
POLL_INTERVAL=60

# NetBox Integration (optional)
NETBOX_URL=https://netbox.example.com
NETBOX_API_TOKEN=your-netbox-token
```

### Security Best Practices

1. **Use Docker Secrets** for sensitive data:
   ```yaml
   secrets:
     db_password:
       file: ./secrets/db_password.txt
     ssh_key:
       file: ./secrets/id_rsa
   ```

2. **Use SSH keys** instead of passwords:
   ```yaml
   - name: prod-router
     keyfile: /run/secrets/ssh_key
   ```

3. **Restrict SNMP communities** - Change from "public" to secure strings

4. **Enable TLS** for production deployments

5. **Implement authentication** on API endpoints (not included in baseline)

---

## API Reference

### GET /topology/nodes

List all network devices.

**Query Parameters**:
- `site` (optional) - Filter by site
- `role` (optional) - Filter by device role

**Example**:
```bash
curl "http://localhost:8088/topology/nodes?site=datacenter1"
```

**Response**:
```json
[
  {
    "name": "10.121.19.21",
    "mgmt_ip": "10.121.19.21",
    "vendor": "Axis",
    "model": "Unknown",
    "role": "switch",
    "site": "default"
  }
]
```

### GET /topology/edges

List all topology connections.

**Query Parameters**:
- `site` (optional) - Filter by site
- `role` (optional) - Filter by device role
- `min_conf` (optional) - Minimum confidence (0.0-1.0)

**Example**:
```bash
curl "http://localhost:8088/topology/edges?min_conf=0.8"
```

**Response**:
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

### GET /topology/path

Find shortest path between two devices.

**Query Parameters**:
- `src_dev` (required) - Source device name/IP
- `dst_dev` (required) - Destination device name/IP
- `layer` (optional) - Layer 2 or Layer 3 (default: 2)

**Example**:
```bash
curl "http://localhost:8088/topology/path?src_dev=10.121.19.101&dst_dev=10.121.19.1"
```

**Response**:
```json
{
  "path": [
    {
      "device": "10.121.19.101",
      "interface": "arp-inferred",
      "method": "mac_arp",
      "confidence": 0.9
    },
    {
      "device": "10.121.19.21",
      "interface": "Port  1",
      "method": "mac_arp",
      "confidence": 0.9
    },
    {
      "device": "10.121.19.21",
      "interface": "Port 17",
      "method": "mac_arp",
      "confidence": 0.9
    },
    {
      "device": "10.121.19.1",
      "interface": "arp-inferred",
      "method": "mac_arp",
      "confidence": 0.9
    }
  ],
  "total_hops": 4
}
```

### GET /topology/impact

Calculate blast radius of device/port failure.

**Query Parameters**:
- `node` (required) - Device name/IP
- `port` (optional) - Specific interface name

**Example**:
```bash
curl "http://localhost:8088/topology/impact?node=10.121.19.21"
```

**Response**:
```json
{
  "affected_devices": [
    "10.121.19.101",
    "10.121.19.102",
    "10.121.19.103",
    "10.121.19.104",
    "10.121.19.71",
    "10.121.19.81"
  ],
  "affected_count": 6
}
```

### GET /topology/interface

Get interface details.

**Query Parameters**:
- `device` (required) - Device name/IP
- `ifname` (required) - Interface name

**Example**:
```bash
curl "http://localhost:8088/topology/interface?device=10.121.19.21&ifname=Port%201"
```

**Response**:
```json
{
  "device": "10.121.19.21",
  "ifname": "Port  1",
  "admin_up": true,
  "oper_up": true,
  "speed_mbps": null,
  "vlan": null,
  "l3_addr": null,
  "l2_mac": null,
  "last_seen": "2025-11-07T16:30:00Z"
}
```

---

## Database Schema

### Complete DDL

See `services/api/migrations/0001_init.sql` for the complete schema definition.

### Key Indexes

```sql
-- Edge lookups
CREATE INDEX idx_edges_a ON edges (a_dev, a_if);
CREATE INDEX idx_edges_b ON edges (b_dev, b_if);
CREATE INDEX idx_edges_method ON edges (method);
CREATE INDEX idx_edges_confidence ON edges (confidence);

-- Facts lookups
CREATE INDEX idx_facts_arp_device ON facts_arp (device);
CREATE INDEX idx_facts_arp_mac ON facts_arp (mac_addr);
CREATE INDEX idx_facts_mac_device ON facts_mac (device);
CREATE INDEX idx_facts_mac_mac ON facts_mac (mac_addr);
CREATE INDEX idx_facts_lldp_device ON facts_lldp (device, ifname);
```

### Useful Queries

**Find all devices on a switch**:
```sql
SELECT DISTINCT b_dev AS device, b_if AS port, confidence
FROM edges
WHERE a_dev = '10.121.19.21' AND method = 'mac_arp'
ORDER BY b_if;
```

**Find device by MAC address**:
```sql
SELECT device, ip_addr
FROM facts_arp
WHERE mac_addr = '00:40:8c:12:34:56'
ORDER BY collected_at DESC
LIMIT 1;
```

**Show topology by confidence**:
```sql
SELECT method, COUNT(*), AVG(confidence)
FROM edges
GROUP BY method
ORDER BY AVG(confidence) DESC;
```

**Recent ARP changes**:
```sql
SELECT device, ip_addr, mac_addr, collected_at
FROM facts_arp
WHERE collected_at > NOW() - INTERVAL '1 hour'
ORDER BY collected_at DESC;
```

---

## Development

### Project Structure

```
opsconductor-nms/
├── docker-compose.yml          # Service orchestration
├── Makefile                    # Common commands
├── secrets/                    # Sensitive credentials (gitignored)
│   ├── db_user.txt
│   └── db_password.txt
├── inventory/                  # Network device inventory
│   ├── devices.yaml           # SuzieQ device list
│   ├── sq.yaml                # SuzieQ configuration
│   └── README.md
├── services/
│   ├── api/                   # FastAPI REST service
│   │   ├── Dockerfile
│   │   ├── main.py
│   │   ├── requirements.txt
│   │   └── migrations/
│   │       └── 0001_init.sql
│   ├── topo-normalizer/       # Topology computation service
│   │   ├── Dockerfile
│   │   ├── normalizer.py
│   │   └── requirements.txt
│   ├── snmp-poller/           # SNMP data collector
│   │   ├── Dockerfile
│   │   ├── poller.py
│   │   └── requirements.txt
│   └── ui/                    # React web interface
│       ├── Dockerfile
│       ├── nginx.conf
│       ├── package.json
│       └── src/
│           ├── App.jsx
│           └── components/
│               └── TopologyMap.jsx
├── docs/
│   ├── ARCHITECTURE.md
│   ├── IMPLEMENTATION_PLAN.md
│   └── TROUBLESHOOTING.md
├── tests/                     # Pytest test suite
│   ├── conftest.py
│   └── test_topology.py
├── STATUS.md                  # Implementation status
├── README.md                  # Quick start guide
└── REPO.md                    # This file
```

### Running Tests

```bash
# Install test dependencies
pip install pytest pytest-asyncio

# Run tests
make test

# Or directly
pytest tests/ -v
```

### Adding a New Device

1. **For SSH-capable devices**: Add to `inventory/devices.yaml`
2. **For SNMP-only devices**: Add to `services/snmp-poller/poller.py`
3. Restart appropriate service
4. Wait 5 minutes for normalizer cycle
5. Check UI for new device

### Adding a New Discovery Method

1. Create new facts table: `facts_<method>`
2. Add collector logic (SuzieQ or custom poller)
3. Add normalizer method: `compute_edges_from_<method>()`
4. Update `run_cycle()` to call new method
5. Add new method to `edges.method` CHECK constraint
6. Set appropriate confidence score

### Debugging

**Check service logs**:
```bash
docker compose logs -f topo-normalizer
docker compose logs -f snmp-poller
docker compose logs -f api
```

**Access database**:
```bash
docker exec -it opsconductor-nms-db-1 psql -U oc -d opsconductor
```

**Check normalizer processing**:
```sql
SELECT method, COUNT(*), MIN(last_seen), MAX(last_seen)
FROM edges
GROUP BY method;
```

**Verify SNMP poller**:
```sql
SELECT device, COUNT(*) AS arp_entries
FROM facts_arp
WHERE collected_at > NOW() - INTERVAL '5 minutes'
GROUP BY device;
```

---

## Troubleshooting

### Device Not Appearing

**Symptom**: Device in inventory but not in topology

**Checks**:
1. Verify device is reachable: `ping <device-ip>`
2. Check collector logs: `docker compose logs suzieq` or `docker compose logs snmp-poller`
3. Verify credentials in `inventory/devices.yaml`
4. Check database: `SELECT * FROM devices WHERE name = '<device-name>';`
5. Check normalizer logs: `docker compose logs topo-normalizer`

### Missing Edges

**Symptom**: Devices appear but no connections between them

**Checks**:
1. Verify LLDP/CDP is enabled on devices
2. Check facts tables:
   ```sql
   SELECT * FROM facts_lldp WHERE device = '<device-name>';
   SELECT * FROM facts_arp WHERE device = '<switch-name>';
   SELECT * FROM facts_mac WHERE device = '<switch-name>';
   ```
3. Check if edges exist but confidence too low:
   ```sql
   SELECT * FROM edges WHERE a_dev = '<device>' OR b_dev = '<device>';
   ```
4. Verify switch has ARP/MAC entries (for SNMP-based discovery)

### Link-Local Addresses Appearing

**Symptom**: 169.254.x.x addresses in topology

**Solution**: These should be filtered automatically. If appearing:
1. Check normalizer code has link-local filter:
   ```sql
   WHERE NOT (a.ip_addr <<= '169.254.0.0/16'::inet)
   ```
2. Delete existing link-local edges:
   ```sql
   DELETE FROM edges WHERE a_dev LIKE '169.254%';
   ```
3. Restart normalizer: `docker compose restart topo-normalizer`

### SNMP Poller Not Working

**Symptom**: No ARP/MAC data from SNMP devices

**Checks**:
1. Verify SNMP is enabled on device
2. Test SNMP manually:
   ```bash
   docker exec -it opsconductor-nms-snmp-poller-1 \
     snmpwalk -v2c -c public 10.121.19.21 1.3.6.1.2.1.4.35.1.4
   ```
3. Check community string is correct
4. Verify firewall allows SNMP (UDP 161)
5. Check poller logs:
   ```bash
   docker compose logs snmp-poller
   ```

### Database Connection Errors

**Symptom**: API returns 503 or "Database not connected"

**Checks**:
1. Verify database is running: `docker compose ps db`
2. Check database logs: `docker compose logs db`
3. Test connection:
   ```bash
   docker exec -it opsconductor-nms-db-1 psql -U oc -d opsconductor -c "SELECT 1"
   ```
4. Verify secrets exist:
   ```bash
   cat secrets/db_user.txt
   cat secrets/db_password.txt
   ```

### Duplicate Devices

**Symptom**: Same device appears multiple times with different names (e.g., both "axis-switch" and "10.121.19.21")

**Cause**: Device created with both hostname and IP address before hostname resolution was implemented

**Solution** (Now Prevented Automatically):
- SNMP poller creates devices with **IP address only** as the canonical name
- Hostnames are stored in `hostname_mappings` table
- Topology normalizer resolves LLDP peer hostnames to IPs before creating edges
- This ensures only one device node per physical device

**Manual Cleanup** (if duplicates exist from old data):
```sql
-- Find duplicates
SELECT name, mgmt_ip FROM devices WHERE mgmt_ip IS NOT NULL;

-- Check hostname mappings
SELECT * FROM hostname_mappings;

-- Delete hostname-based duplicates (keep IP-based)
DELETE FROM devices WHERE name = '<hostname>' AND EXISTS (
    SELECT 1 FROM hostname_mappings WHERE hostname = '<hostname>'
);

-- Delete edges referencing old hostname-based devices
DELETE FROM edges WHERE a_dev = '<hostname>' OR b_dev = '<hostname>';
```

### Duplicate Edges (Multiple Connections Between Same Devices)

**Symptom**: Two lines shown between the same device pair in topology visualization (e.g., both LLDP and MAC_ARP edges)

**Cause**: Before fix, `vw_links_canonical` partitioned by interface pairs, not device pairs

**Solution** (Now Fixed Automatically):
- `/topology/edges` API endpoint uses `vw_links_canonical` view
- View partitions by **device pair only** (not interfaces)
- Returns only the highest-confidence edge per device pair
- LLDP edges (confidence 1.0) automatically preferred over MAC_ARP edges (confidence 0.9)

**Example**:
```sql
-- Before fix: Both edges returned
10.121.19.21 (GigabitEthernet 1/1) → 10.121.19.101 (eth0)         [LLDP, 1.0]
10.121.19.101 (arp-inferred)       → 10.121.19.21 (Port 1)        [MAC_ARP, 0.9]

-- After fix: Only highest confidence returned
10.121.19.21 (GigabitEthernet 1/1) → 10.121.19.101 (eth0)         [LLDP, 1.0]
```

**Note**: The lower-confidence edges still exist in the database for historical/debugging purposes, but are not displayed in the UI.

### Performance Issues

**Symptom**: Slow API responses or UI lag

**Optimizations**:
1. Add indexes on frequently queried columns
2. Increase database connection pool size
3. Enable query result caching
4. Prune old facts data:
   ```sql
   DELETE FROM facts_arp WHERE collected_at < NOW() - INTERVAL '7 days';
   DELETE FROM facts_mac WHERE collected_at < NOW() - INTERVAL '7 days';
   ```
5. Vacuum database:
   ```sql
   VACUUM ANALYZE;
   ```

---

## References

- [SuzieQ Documentation](https://suzieq.readthedocs.io/)
- [SNMP MIBs Reference](http://www.oid-info.com/)
- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [ReactFlow Documentation](https://reactflow.dev/)
- [ELK Layout Algorithm](https://www.eclipse.org/elk/)

---

## License

MIT License - See LICENSE file for details

## Contributing

See CONTRIBUTING.md for development guidelines

## Support

- GitHub Issues: https://github.com/andrewcho-dev/opsconductor-nms/issues
- Documentation: See docs/ directory
