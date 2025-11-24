# OpsConductor NMS - Repository Technical Documentation

**Last Updated**: 2025-11-20  
**Status**: ✅ Production-Ready Network Management System

---

## System Overview

OpsConductor NMS is a network management system that provides:

1. **Router Topology Discovery** - Recursively discover routers via SNMP routing table analysis
2. **Device Inventory Management** - Track discovered devices with comprehensive metadata
3. **Topology Visualization** - Visualize Layer 2 (LLDP), Layer 3 (routing), and router topologies
4. **MIB Library Management** - Manage vendor-specific SNMP MIB files
5. **Real-Time UI** - Web interface for discovery, inventory, and topology visualization

---

## Architecture

### System Diagram

```
┌────────────────────────────────────────────────────────┐
│                   Web UI (React)                       │
│  - Inventory Grid     - Discovery Page                 │
│  - Topology Map       - Admin MIB Panel                │
└───────────┬────────────────────────────────┬───────────┘
            │                                │
            ▼                                ▼
┌──────────────────────────┐    ┌──────────────────────────┐
│     State Server         │    │   Router Discovery       │
│   (FastAPI + AsyncIO)    │    │   (FastAPI + SNMP)       │
│  Port: 8080              │    │   Port: 8200             │
│  - IP Inventory API      │    │   - Router crawl API     │
│  - Topology APIs         │    │   - Discovery runs       │
│  - MIB Management        │    │   - Topology edges       │
│  - WebSocket Stream      │    │   - BFS router search    │
│  - WebSocket: /ws        │    │                          │
└─────┬──────────┬─────────┘    └──────────┬──────────────┘
      │          │                         │
      ▼          ▼                         ▼
┌──────────────────────────────────────────────────────┐
│        PostgreSQL 16                                 │
│  Tables:                                             │
│  - ip_inventory (state-server)                       │
│  - device_confirmations, mibs, graph_state          │
│  - patch_events (audit log)                          │
│  - discovery_runs, routers, routes, networks, edges │
│    (router-discovery)                                │
└──────────────────────────────────────────────────────┘
```

---

## Services

### Running Services

| Service | Port | Purpose | Technology |
|---------|------|---------|-----------|
| **PostgreSQL** | 5432 | Database | PostgreSQL 16 |
| **State Server** | 8080 | IP Inventory + Topology API | FastAPI + AsyncIO |
| **Router Discovery** | 8200 | SNMP Router Topology Crawler | FastAPI + pysnmp |
| **UI** | 3000 | Web Interface | React + TypeScript + Vite |

### Disabled/Optional Services

These services are included in the codebase but disabled by default in docker-compose.yml:
- **Packet Collector** - Passive packet capture (requires network interface access)
- **Port Scanner** - Active TCP/UDP port scanning
- **SNMP Discovery** - Device SNMP queries
- **MAC Enricher** - MAC OUI vendor lookup
- **MIB Assigner** - Automatic MIB assignment
- **MIB Walker** - SNMP tree walking
- **LLM Analyst** - AI-powered device classification (requires GPU)
- **vLLM** - LLM inference engine (requires GPU)

---

## Database Schema

### State Server Tables

#### `ip_inventory`
Device inventory with all discovered information:
- `id` (PK): Integer
- `ip_address` (INET, unique): Device IP
- `mac_address` (MACADDR): Device MAC
- `status` (String): active/inactive/unknown
- `device_type` (String): router/switch/firewall/host/etc
- `device_type_confirmed` (Boolean): User verification flag
- `network_role` (String): L2/L3/Endpoint
- `device_name` (String): Hostname or user-assigned name
- `vendor` (String): Equipment vendor
- `model` (String): Equipment model
- `snmp_data` (JSONB): SNMP-collected metrics and LLDP neighbors
- `open_ports` (JSONB): Open ports from scanning
- `confidence_score` (Float): Classification confidence
- `first_seen` (DateTime): First discovery time
- `last_seen` (DateTime): Last activity time
- `mib_ids` (Array of Integers): Associated MIB library IDs

#### `mibs`
SNMP MIB library:
- `id` (PK): Integer
- `name` (String, unique): MIB name
- `vendor` (String): Vendor (Cisco, Juniper, etc.)
- `device_types` (Array): Applicable device types
- `version` (String): MIB version
- `file_path` (Text): Path to MIB file
- `oid_prefix` (Text): Root OID for this MIB
- `description` (Text): MIB description
- `uploaded_at` (DateTime): Upload timestamp

#### `device_confirmations`
User verification history:
- `id` (PK): Integer
- `ip_inventory_id` (FK): Device reference
- `confirmed_by` (String): User who confirmed
- `confirmed_type` (String): Confirmed device type
- `confidence` (Float): User confidence (0-1)
- `evidence` (Text): Verification evidence notes
- `confirmed_at` (DateTime): Confirmation time

#### `graph_state`
Topology graph storage (single row):
- `id` (Integer, PK=1): Singleton key
- `graph` (JSONB): Complete topology graph structure
- `seed_config` (JSONB): Saved discovery seed configuration
- `updated_at` (DateTime): Last update time

#### `patch_events`
Audit log of topology changes:
- `id` (PK): Integer
- `patch` (JSONB): JSON Patch operations
- `rationale` (String): Change reason
- `warnings` (JSONB): Associated warnings
- `created_at` (DateTime): Change timestamp

#### `discovered_networks`
Network discovery tracking:
- `id` (PK): Integer
- `network` (String, unique): CIDR notation
- `destination` (INET): Network address
- `netmask` (INET): Network mask
- `gateway_ip` (INET): Gateway address
- `prefix_len` (Integer): CIDR prefix length
- `discovered_at` (DateTime): Discovery time
- `network_metadata` (JSONB): Additional metadata

### Router Discovery Tables

All router-discovery tables include `run_id` (FK) to partition by discovery run.

#### `discovery_runs`
Discovery operation tracking:
- `id` (PK): Integer
- `started_at` (DateTime): Start time
- `finished_at` (DateTime, nullable): Completion time
- `status` (String): PENDING/RUNNING/COMPLETED/FAILED/CANCELLED
- `root_ip` (INET): Starting router IP
- `snmp_community` (String): SNMP community string used
- `snmp_version` (String): "2c" or "3"
- `error_message` (Text, nullable): Error details if FAILED

#### `routers`
Discovered routers:
- `id` (PK): Integer
- `run_id` (FK): Discovery run reference
- `primary_ip` (INET): Router IP address
- `hostname` (String): SNMP sysName
- `sys_descr` (Text): SNMP sysDescr
- `sys_object_id` (String): SNMP sysObjectID
- `vendor` (String): Extracted vendor name
- `model` (String): Extracted model number
- `is_router` (Boolean): Classification result
- `router_score` (Integer): Classification score
- `classification_reason` (Text): Why classified as router
- `created_at` (DateTime): Discovery time
- Unique constraint: `(run_id, primary_ip)`

#### `router_networks`
Networks attached to routers:
- `id` (PK): Integer
- `run_id` (FK): Discovery run reference
- `router_id` (FK): Router reference
- `network` (CIDR): Network in CIDR notation
- `is_local` (Boolean): True if local interface, false if route

#### `router_routes`
Routing table entries:
- `id` (PK): Integer
- `run_id` (FK): Discovery run reference
- `router_id` (FK): Router reference
- `destination` (CIDR): Route destination in CIDR
- `next_hop` (INET, nullable): Next hop IP
- `protocol` (String): Routing protocol (static, bgp, ospf, etc.)
- `admin_distance` (Integer, nullable): Administrative distance
- `metric` (Integer, nullable): Route metric

#### `topology_edges`
Connections between routers:
- `id` (PK): Integer
- `run_id` (FK): Discovery run reference
- `from_router_id` (FK): Source router
- `to_router_id` (FK): Destination router
- `reason` (String): Edge reason (e.g., "shared_subnet")
- Unique constraint: `(run_id, from_router_id, to_router_id)`

---

## API Endpoints

### State Server (port 8080)

#### Health
```
GET /health
```
Returns: `{"status": "ok"}`

#### Graph/Topology
```
GET /graph
```
Returns: Complete topology graph with nodes, edges, networks

```
POST /patch
Body: {"op": "add"/"remove"/"replace", "path": "/...", "value": {...}}
```
Apply JSON Patch to topology graph

```
GET /patches?limit=50
```
Returns: List of past patch operations

#### Inventory
```
GET /api/inventory
Query params: status, device_type, confirmed
```
Returns: Array of devices

```
GET /api/inventory/{ip_address}
```
Returns: Single device details

```
POST /api/inventory
Body: IpInventoryCreate
```
Create new inventory entry

```
PUT /api/inventory/{ip_address}
Body: IpInventoryUpdate
```
Update device information

```
GET /api/inventory/{ip_address}/neighbors
```
Returns: LLDP neighbor information

```
POST /api/inventory/{ip_address}/confirm
Body: {confirmed_by, confirmed_type, confidence, evidence}
```
Record user confirmation of device type

#### Topology
```
GET /api/topology/layer2
```
Returns: Layer 2 topology (LLDP-based with STP tree calculation)

```
GET /api/topology/l2
```
Returns: L2 switch topology

```
GET /api/topology/l3
```
Returns: Layer 3 routing topology

#### MIBs
```
GET /api/mibs
```
Returns: All MIB library entries

```
GET /api/mibs/{mib_id}
```
Returns: MIB content by ID

```
POST /api/mibs
Body: MibCreate
```
Add new MIB to library

```
DELETE /api/mibs/{mib_id}
```
Remove MIB from library

```
GET /api/inventory/{ip_address}/mibs/suggestions
```
Returns: Suggested MIBs for device

```
POST /api/inventory/{ip_address}/mibs/reassign
Body: {mib_id}
```
Assign MIB to device

```
POST /api/inventory/{ip_address}/mibs/walk
```
Trigger manual SNMP MIB walk

#### WebSocket
```
WS /ws
```
Real-time topology updates. Initial message sends snapshot, subsequent messages send patches.

#### Seed Configuration
```
GET /seed
```
Returns: Last saved seed configuration

```
POST /seed
Body: SeedConfigRequest
```
Save seed configuration for future discoveries

#### Other
```
POST /api/networks/discovered
```
Record discovered network

```
GET /api/networks/discovered
```
Get discovered networks

```
POST /api/launch-terminal
```
Terminal launcher (host filesystem access)

```
GET /api/browse-filesystem
```
File browser for admin operations

### Router Discovery (port 8200)

#### Discovery Control
```
POST /api/router-discovery/start
Body: {
  "root_ip": "192.168.1.1",
  "snmp_community": "public",
  "snmp_version": "2c"
}
```
Response: `{"run_id": 1}`

```
GET /api/router-discovery/runs/{run_id}/state
```
Returns: Discovery run status, timing, and progress metrics

```
POST /api/router-discovery/runs/{run_id}/pause
```
Pause ongoing discovery

```
POST /api/router-discovery/runs/{run_id}/resume
```
Resume paused discovery

```
POST /api/router-discovery/runs/{run_id}/cancel
```
Cancel discovery

#### Data Retrieval
```
GET /api/router-discovery/runs/{run_id}/topology
```
Returns: Discovered routers (nodes) and connections (edges)

```
GET /api/router-discovery/runs/{run_id}/routers/{router_id}
```
Returns: Detailed router information including networks and routes

#### Health
```
GET /health
```
Returns: `{"status": "healthy"}`

---

## Core Services Implementation

### State Server (services/state-server/)

**Key Files**:
- `main.py` - FastAPI application with all endpoints
- `models.py` - SQLAlchemy database models
- `schemas.py` - Pydantic request/response schemas
- `service.py` - Business logic for graph operations
- `database.py` - Database initialization and async session factory
- `stp_calculator.py` - STP spanning tree calculation for L2 topology

**Key Dependencies**:
- FastAPI 0.115+
- SQLAlchemy 2.0 (async)
- Pydantic 2.x
- PostgreSQL driver (asyncpg)
- asyncio

**Key Features**:
- Asynchronous request handling with FastAPI
- Real-time WebSocket updates to clients
- JSON Patch operations for topology modifications
- LLDP neighbor resolution to IP addresses
- STP tree calculation for Layer 2 topology
- Device confirmation and verification tracking

### Router Discovery (services/router-discovery/)

**Key Files**:
- `main.py` - FastAPI application initialization
- `api.py` - REST API endpoints
- `crawler.py` - Main BFS router discovery crawler
- `snmp_adapter.py` - SNMP client wrapper (pysnmp)
- `router_classifier.py` - Router classification heuristics
- `models.py` - SQLAlchemy database models
- `database.py` - Database initialization

**Key Components**:

#### Crawler (crawler.py)
- **Algorithm**: Breadth-First Search (BFS)
- **Process**:
  1. Start with root router IP
  2. Query SNMP: system info, IP forwarding, interfaces, routing table
  3. Classify device as router or non-router
  4. Extract next-hop IPs from routing table
  5. Add undiscovered next-hops to queue
  6. Build topology edges based on shared subnets
  7. Repeat until queue empty

#### SNMP Adapter (snmp_adapter.py)
- Wraps pysnmp library for SNMPv2c and SNMPv3
- Provides high-level methods:
  - `get_system_info()` - sysDescr, sysObjectID, sysName
  - `get_ip_forwarding()` - ipForwarding status
  - `get_interfaces_and_addresses()` - IP/mask per interface
  - `get_routing_entries()` - Routing table with protocol info
- Error handling for timeouts, auth failures, unreachable hosts

#### Router Classifier (router_classifier.py)
Scoring-based router classification:
- **Scoring Logic**:
  - IP forwarding enabled: +3 points
  - Multiple unique L3 networks on interfaces: +2 points
  - At least one remote route: +3 points
  - Router keywords in sysDescr/sysObjectID: +1 point each
- **Result**: Router if score >= 3

**Key Dependencies**:
- FastAPI 0.115+
- SQLAlchemy 2.0 (async)
- pysnmp 4.4+ (SNMP client)
- Pydantic 2.x

**Key Features**:
- Single-threaded BFS crawler (prevents duplicate processing)
- Classifies devices as routers vs endpoints using heuristics
- Extracts vendor/model from system descriptions
- Creates topology edges based on shared subnets
- Full audit trail via discovery runs table
- Support for pause/resume operations
- Graceful error handling and logging

### UI (ui/src/)

**Key Files**:
- `App.tsx` - Main app with tab navigation
- `InventoryGrid.tsx` - Device inventory table with filters
- `DiscoveryPage.tsx` - Router discovery interface
- `TopologyMap.tsx` - Topology visualization
- `Admin.tsx` - MIB library management

**Key Features**:
- Multi-page SPA with tab-based navigation
- Real-time device list with sorting/filtering
- Live topology visualization for routers
- Discovery progress monitoring
- Drag-and-drop MIB management
- WebSocket connection for live updates

**Technology Stack**:
- React 18
- TypeScript 5.6
- Vite 5.4 (build tool)
- CSS Grid for responsive layout

---

## Data Flow

### Router Discovery Flow

```
1. User clicks "Start Discovery" on Discovery Page
   │
   ├─ UI POST /api/router-discovery/start
   │   {root_ip: "192.168.1.1", snmp_community: "public"}
   │
   ├─ Router Discovery Service
   │   │
   │   ├─ Create DiscoveryRun (status=RUNNING)
   │   │
   │   ├─ Start BFS Crawler
   │   │   ├─ Queue root_ip
   │   │   │
   │   │   └─ While queue not empty:
   │   │       ├─ Pop router_ip from queue
   │   │       │
   │   │       ├─ Query SNMP
   │   │       │   ├─ System info (sysDescr, hostname)
   │   │       │   ├─ IP forwarding status
   │   │       │   ├─ Interfaces & IP addresses
   │   │       │   └─ Routing table
   │   │       │
   │   │       ├─ Classify router (score >= 3?)
   │   │       │
   │   │       ├─ Store Router record
   │   │       ├─ Store RouterNetwork records (interfaces)
   │   │       ├─ Store RouterRoute records (routes)
   │   │       │
   │   │       ├─ Extract next-hop IPs
   │   │       │
   │   │       ├─ Create TopologyEdge (shared subnets)
   │   │       │
   │   │       └─ Enqueue new next-hops
   │   │
   │   └─ Mark DiscoveryRun as COMPLETED
   │
   └─ UI polls /api/router-discovery/runs/{run_id}/state
      Displays progress and status
```

### Topology Visualization Flow

```
1. User views Topology Map page
   │
   ├─ UI GET /api/topology/layer2
   │   ├─ State Server queries ip_inventory
   │   ├─ Extracts LLDP neighbors from snmp_data.lldp
   │   ├─ Resolves remote chassis IDs to IP addresses
   │   ├─ Calculates STP spanning tree
   │   └─ Returns nodes and edges
   │
   └─ UI renders interactive topology graph
```

---

## Technology Stack

### Backend
- **Language**: Python 3.11+
- **Async Framework**: FastAPI 0.115+
- **Async ORM**: SQLAlchemy 2.0+
- **Database**: PostgreSQL 16
- **SNMP**: pysnmp 4.4+
- **Async HTTP**: httpx
- **Serialization**: Pydantic 2.x

### Frontend
- **Framework**: React 18
- **Language**: TypeScript 5.6
- **Build Tool**: Vite 5.4
- **Styling**: CSS Grid

### Infrastructure
- **Containerization**: Docker + Docker Compose
- **Database**: PostgreSQL 16 (Docker volume)
- **Networking**: Docker network bridge

---

## Configuration

### Environment Variables

**Common Settings** (see .env.example):
```
# Database
DB_URL=postgresql://opsconductor:opsconductor@postgres:5432/opsconductor

# API
API_PORT=8080
UI_WS_ORIGIN=*

# UI
VITE_API_BASE=http://localhost:8080
VITE_WS_BASE=ws://localhost:8080

# Model (optional, for GPU services)
MODEL_NAME=microsoft/Phi-3-mini-4k-instruct
VLLM_MAX_CONTEXT_LEN=8192
```

---

## Development Notes

### Adding New API Endpoints

1. Define Pydantic schema in `schemas.py`
2. Define request handler in `main.py` or dedicated router file
3. Implement business logic in `service.py` if needed
4. Test with curl or API client

### Extending Router Classification

Edit `services/router-discovery/app/router_classifier.py`:
- Add new score criteria to `classify_router()` method
- Adjust `SCORE_THRESHOLD` if needed
- Rebuild service: `docker compose build router-discovery`

### Database Migrations

Router Discovery uses SQLAlchemy with migrations:
```bash
# Create new migration
alembic revision --autogenerate -m "Add new column"

# Apply migrations
alembic upgrade head
```

State Server uses raw SQL migrations in `services/state-server/`.

---

## Performance Characteristics

### Router Discovery
- **BFS Crawl**: 5-20 routers/minute (SNMP timeout dependent)
- **SNMP Query Time**: 1-5 seconds per device
- **Network Overhead**: ~100-500 bytes per device
- **Memory**: ~10-50MB per 100 routers

### State Server
- **Request Latency**: <100ms typical
- **WebSocket Updates**: <500ms propagation
- **Database Query**: <50ms for most queries

### Database
- **Disk Space**: ~1MB per 100 routers with routing tables
- **Index Coverage**: Optimized for run_id, status, IP address queries

---

## Security Considerations

⚠️ **System Design**: This is for **internal network use only**

**Current Limitations**:
- ❌ No authentication on API endpoints
- ❌ No TLS/SSL encryption
- ❌ CORS allows all origins
- ❌ Database credentials in plaintext .env
- ✅ Services in isolated Docker network
- ✅ No data leaves internal network

**For Production**:
1. Add JWT or OAuth authentication
2. Enable TLS/SSL on all endpoints
3. Restrict CORS to specific origins
4. Use secrets management (Vault, K8s secrets)
5. Implement rate limiting and audit logging
6. Run behind reverse proxy with auth
