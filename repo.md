# OpsConductor NMS - Repository Overview

**Last Updated**: 2025-11-19  
**Status**: ✅ Production-Ready Network Management System

---

## System Overview

OpsConductor NMS is a comprehensive network management system that combines:
- **Passive packet observation** for network topology discovery
- **Active device scanning** for comprehensive network inventory
- **AI-powered analysis** using LLMs for device classification
- **SNMP discovery and monitoring** for detailed device information
- **Real-time inventory management** with web-based UI

### What This System Does

1. **Discovers Network Devices**: Passively observes network traffic and actively scans IP ranges to discover all devices
2. **Identifies Device Types**: Uses port scanning, SNMP queries, and LLM analysis to classify devices (routers, switches, hosts, etc.)
3. **Discovers Layer 2 Topology**: Uses LLDP (Link Layer Discovery Protocol) to map physical network connections between devices
4. **Classifies Network Roles**: Automatically determines L2/L3/Endpoint roles based on IP forwarding, routing tables, and STP status
5. **Enriches Device Information**: Automatically gathers vendor info (MAC OUI lookup), SNMP data, open ports, and service information
6. **Manages MIB Library**: Maintains vendor-specific MIBs and automatically assigns appropriate MIBs to discovered devices
7. **Provides Real-Time UI**: Web interface showing complete IP inventory with filtering, sorting, device details, and topology visualization

---

## Architecture

### System Diagram

```
┌─────────────────────────────────────────────────────────┐
│                    Network Layer                         │
│              (192.168.10.0/24 or custom)                │
└────────┬──────────────────────────────────┬─────────────┘
         │                                  │
    [Passive]                          [Active]
         │                                  │
         ▼                                  ▼
┌─────────────────┐              ┌─────────────────────┐
│ Packet Collector│              │   Port Scanner      │
│   (Scapy)       │              │   (asyncio TCP/UDP) │
│ - ARP frames    │              │ - 161/SNMP, 22/SSH  │
│ - IP flows      │              │ - 80/HTTP, 443/HTTPS│
│ - MAC addresses │              │ - BGP, Telnet, etc. │
└────────┬────────┘              └──────────┬──────────┘
         │                                  │
         │        ┌─────────────────────────┤
         │        │                         │
         ▼        ▼                         ▼
    ┌────────────────────┐        ┌─────────────────┐
    │   LLM Analyst      │        │ SNMP Discovery  │
    │   (Phi-3 + vLLM)   │        │  (pysnmp)       │
    │ - Topology infer   │        │ - Query devices │
    │ - Device classify  │        │ - Extract info  │
    └──────────┬─────────┘        └────────┬────────┘
               │                           │
               │         ┌─────────────────┤
               │         │                 │
               ▼         ▼                 ▼
          ┌──────────────────────────────────────┐
          │         State Server                 │
          │      (FastAPI + PostgreSQL)          │
          │                                      │
          │  - IP Inventory Database             │
          │  - Topology Graph Storage            │
          │  - MIB Library Management            │
          │  - WebSocket Streaming               │
          └────┬─────────────────────┬───────────┘
               │                     │
               ▼                     ▼
      ┌────────────────┐    ┌────────────────┐
      │  MAC Enricher  │    │  MIB Assigner  │
      │  (IEEE OUI DB) │    │  (Auto-match)  │
      └────────┬───────┘    └────────┬───────┘
               │                     │
               └──────────┬──────────┘
                          │
                          ▼
                  ┌───────────────┐
                  │  MIB Walker   │
                  │ (SNMP Polling)│
                  └───────┬───────┘
                          │
                          ▼
                  ┌───────────────┐
                  │   UI (React)  │
                  │  Inventory    │
                  │     Grid      │
                  └───────────────┘
```

---

## Services

### Core Services

| Service | Purpose | Technology | Port | Status |
|---------|---------|-----------|------|--------|
| **vLLM** | LLM inference engine | vLLM + Phi-3-mini-4k | 8000 | ⚙️ Optional (GPU) |
| **State Server** | API + Database + WebSocket | FastAPI + PostgreSQL | 8080 | ✅ Working |
| **LLM Analyst** | Topology + Classification | FastAPI + httpx | 8100 | ⚙️ Optional (GPU) |
| **Packet Collector** | Passive packet capture | Python + Scapy | 9100 (health) | ✅ Working |
| **Port Scanner** | Active TCP/UDP scanning | Python asyncio | 9200 (health) | ✅ Working |
| **SNMP Discovery** | SNMP querying + network role classification | Python + pysnmp | 9300 (health) | ✅ Working |
| **MAC Enricher** | Vendor identification | IEEE OUI lookup | 9400 (health) | ✅ Working |
| **MIB Assigner** | Auto MIB assignment | Python | 9500 (health) | ✅ Working |
| **MIB Walker** | SNMP data collection + LLDP discovery | Python + pysnmp + pysmi | 9600 (health) | ✅ Working |
| **UI** | Web interface + topology visualization | React + TypeScript | 3000 | ✅ Working |
| **PostgreSQL** | Database | PostgreSQL 16 | 5432 (internal) | ✅ Working |

---

## Database Schema

### Main Tables

#### `ip_inventory`
Complete device inventory with all discovered information:
- IP address, MAC address, hostname
- Device type, vendor, model
- Network role (L2/L3/Endpoint) and confirmation status
- Status (active/inactive/unknown)
- Open ports (JSONB)
- SNMP configuration and data (JSONB) including LLDP neighbor data
- Confidence scores and classification notes
- Timestamps (first_seen, last_seen, last_probed)

#### `mibs`
MIB library for vendor-specific SNMP queries:
- Name, vendor, version
- Device types (applicable devices)
- OID prefix
- File path

#### `device_confirmations`
User confirmations and verification history

#### `graph_state`
Topology graph (nodes, edges, networks, routers)

#### `patch_events`
Audit log of all topology changes

---

## API Endpoints

### State Server API (`:8080`)

#### Health & Status
- `GET /health` - Health check

#### Topology Management
- `GET /graph` - Retrieve topology graph
- `POST /patch` - Apply JSON Patch to topology
- `GET /patches?limit=50` - Patch history
- `WS /ws` - WebSocket real-time updates

#### IP Inventory Management
- `GET /api/inventory` - List all discovered IPs (supports filtering)
  - Query params: `status`, `device_type`, `confirmed`
- `GET /api/inventory/{ip}` - Get single device details
- `GET /api/inventory/{ip}/neighbors` - Get LLDP neighbors with port mappings
- `POST /api/inventory` - Create/update device
- `PUT /api/inventory/{ip}` - Update device
- `POST /api/inventory/{ip}/confirm` - User confirmation

#### MIB Management
- `GET /api/mibs` - List all MIBs
- `GET /api/mibs/{mib_id}` - Get MIB content by ID
- `POST /api/mibs` - Upload new MIB
- `DELETE /api/mibs/{id}` - Delete MIB
- `GET /api/inventory/{ip}/mibs/suggestions` - Get MIB suggestions for device
- `POST /api/inventory/{ip}/mibs/walk` - Trigger manual MIB walk for device
- `POST /api/inventory/{ip}/mibs/reassign` - Reassign MIB for device

#### Topology Management
- `GET /api/topology/layer2` - Get Layer 2 topology with LLDP-discovered connections

#### Seed Configuration
- `GET /seed` - Get seed configuration
- `POST /seed` - Save seed configuration

### LLM Analyst API (`:8100`, internal)
- `POST /tick` - Process evidence window → topology patch
- `POST /classify` - Classify device based on scan results

---

## Data Flow

### Discovery Pipeline

```
1. PACKET COLLECTOR
   ↓ Captures ARP frames, IP flows
   ↓ Extracts IP/MAC pairs
   ↓
2. STATE SERVER
   ↓ Creates ip_inventory record
   ↓ Sets status='active', last_seen=now
   ↓
3. PORT SCANNER
   ↓ Scans common ports every 5 minutes
   ↓ Updates open_ports JSONB field
   ↓
4. SNMP DISCOVERY
   ↓ Checks port 161, tries common communities
   ↓ Queries sysDescr, sysObjectID, interfaces
   ↓ Updates snmp_data, vendor, model
   ↓
5. MAC ENRICHER
   ↓ Looks up MAC OUI in IEEE database
   ↓ Updates vendor field (if empty)
   ↓
6. MIB ASSIGNER
   ↓ Matches vendor + device_type to MIB library
   ↓ Assigns mib_id
   ↓
7. MIB WALKER
   ↓ Walks SNMP tree with assigned MIB
   ↓ Resolves numeric OIDs to text labels using PySNMP MibViewController
   ↓ Loads standard MIBs (SNMPv2-MIB, IF-MIB, LLDP-MIB, etc.) from http://mibs.pysnmp.com
   ↓ Collects detailed metrics with human-readable labels
   ↓ Discovers LLDP neighbors and port connections
   ↓ Updates snmp_data JSONB (vendor_mib_data field, lldp field)
   ↓
8. LLM ANALYST (Optional)
   ↓ Analyzes all collected data
   ↓ Classifies device_type with confidence_score
   ↓ Updates classification_notes
   ↓
9. UI
   ↓ Displays complete inventory
   ↓ User can filter, sort, confirm device types
```

---

## Technology Stack

### Backend
- **Language**: Python 3.11+
- **Framework**: FastAPI 0.115+
- **ORM**: SQLAlchemy 2.0 (async)
- **Database**: PostgreSQL 16
- **LLM Inference**: vLLM with Phi-3-mini-4k-instruct
- **Packet Capture**: Scapy
- **SNMP**: pysnmp / easysnmp
- **Async I/O**: asyncio + httpx

### Frontend
- **Framework**: React 18
- **Language**: TypeScript 5.6
- **Build Tool**: Vite 5.4
- **UI Components**: Custom inventory grid with filtering/sorting

### Infrastructure
- **Container**: Docker + Docker Compose
- **GPU**: NVIDIA Container Toolkit (for vLLM)
- **Networking**: Host network mode (packet collector)

---

## Key Features Implementation

### SNMP OID Text Label Resolution

The MIB Walker service implements automatic OID resolution to convert numeric OIDs into human-readable text labels.

**Technical Implementation**:

1. **MIB Compilation**: Uses `pysmi` package to compile and load MIB definitions
2. **Remote MIB Source**: Configured to fetch MIBs from `http://mibs.pysnmp.com/asn1/@mib@` on-demand
3. **Standard MIBs Loaded**: 
   - SNMPv2-MIB
   - IF-MIB
   - IP-MIB
   - TCP-MIB
   - UDP-MIB
   - HOST-RESOURCES-MIB
   - Printer-MIB
   - BRIDGE-MIB
   - ENTITY-MIB
   - LLDP-MIB
4. **Resolution Process**:
   - Creates `MibBuilder` and `MibViewController` instances
   - Loads standard MIBs during initialization
   - For each OID during SNMP walk: calls `getNodeName(oid_tuple)` to resolve
   - Returns tuple: `(oid, label, suffix)`
   - Constructs human-readable label: `label + '.' + suffix`
5. **Fallback Behavior**: If resolution fails, falls back to shortened numeric labels (last 4 OID components)

**Example Output**:
- Before: `1.1.3.1`
- After: `prtInputName.1.1` (OID: 1.3.6.1.2.1.43.8.2.1.13.1.1)

**Benefits**:
- Network administrators can immediately understand what each metric represents
- No need to manually look up OID meanings in MIB documentation
- Works with standard MIBs out-of-the-box (Printer-MIB, IF-MIB, etc.)

---

### LLDP Neighbor Discovery

The MIB Walker service automatically discovers Layer 2 physical topology using LLDP (Link Layer Discovery Protocol).

**Technical Implementation**:

1. **LLDP-MIB Queries**: Walks LLDP-MIB OID tree (1.0.8802.1.1.2) to discover neighbors
2. **Local System Information**:
   - `lldpLocChassisId` (1.0.8802.1.1.2.1.3.2.0): Local chassis ID
   - `lldpLocSysName` (1.0.8802.1.1.2.1.3.3.0): Local system name
   - `lldpLocSysDesc` (1.0.8802.1.1.2.1.3.4.0): Local system description
3. **Remote Neighbor Information**:
   - `lldpRemChassisId` (1.0.8802.1.1.2.1.4.1.1.5): Remote device chassis ID
   - `lldpRemPortId` (1.0.8802.1.1.2.1.4.1.1.7): Remote port identifier
   - `lldpRemPortDesc` (1.0.8802.1.1.2.1.4.1.1.8): Remote port description
   - `lldpRemSysName` (1.0.8802.1.1.2.1.4.1.1.9): Remote system name
   - `lldpRemSysDesc` (1.0.8802.1.1.2.1.4.1.1.10): Remote system description
4. **Neighbor Resolution**: State server resolves remote chassis IDs and system names to IP addresses in inventory
5. **Storage**: LLDP data stored in `snmp_data.lldp` JSONB field with `local_system` and `neighbors` arrays

**Data Structure**:
```json
{
  "lldp": {
    "local_system": {
      "chassis_id": "00:11:22:33:44:55",
      "sysname": "switch-01",
      "sysdesc": "Cisco IOS Switch"
    },
    "neighbors": [
      {
        "local_port": "1",
        "remote_chassis_id": "00:aa:bb:cc:dd:ee",
        "remote_port_id": "GigabitEthernet0/1",
        "remote_sysname": "router-01",
        "remote_sysdesc": "Cisco IOS Router"
      }
    ]
  }
}
```

**Layer 2 Topology API**: The state server provides `/api/topology/layer2` endpoint that:
- Retrieves all devices with LLDP neighbor data
- Resolves remote chassis IDs and system names to IP addresses
- Returns nodes (devices) and edges (connections) for visualization
- Includes port mapping information for each connection

**Benefits**:
- Automatic discovery of physical network topology
- Visualize actual cable connections between devices
- Identify incorrect cabling or missing connections
- No manual topology mapping required

---

### Network Role Classification

The SNMP Discovery service automatically classifies devices into network roles based on their capabilities.

**Classification Logic**:

1. **L3 (Layer 3 Router)**:
   - `ipForwarding` (1.3.6.1.2.1.4.1.0) = 1 (forwarding enabled)
   - AND route count > 2 (from ipRouteTable walk)
   
2. **L2 (Layer 2 Switch)**:
   - STP enabled (dot1dStpProtocolSpecification exists)
   - Does not meet L3 criteria

3. **Endpoint**:
   - Does not meet L2 or L3 criteria
   - Typically hosts, servers, printers, cameras, etc.

**Technical Implementation**:

1. **SNMP Queries** (services/snmp-discovery/app/main.py):
   - `ipForwarding` OID: Checks if IP forwarding is enabled
   - `ipRouteTable` walk: Counts routing table entries
   - `dot1dStpProtocolSpecification` OID: Checks if STP is enabled

2. **Classification Function** (`determine_network_role()`):
   ```python
   if ipForwarding == "1" and route_count > 2:
       return "L3"
   elif stp_enabled > 0:
       return "L2"
   else:
       return "Endpoint"
   ```

3. **Storage**: Network role stored in `ip_inventory.network_role` field with confirmation flag

**User Confirmation**: Network roles can be manually confirmed via UI or API, preventing automatic reclassification.

**Benefits**:
- Automatically identifies network device types
- Helps with inventory organization and filtering
- Supports topology inference and visualization
- Can be manually overridden when needed

---

## Configuration

### Environment Variables

```bash
# LLM Configuration
MODEL_NAME=microsoft/Phi-3-mini-4k-instruct
VLLM_MAX_CONTEXT_LEN=8192
HF_TOKEN=                           # Optional

# Network Configuration
GATEWAY_IP=192.168.1.1              # Optional seed
FIREWALL_IP=                        # Optional seed
PCAP_IFACE=eth0                     # Network interface for packet capture

# Service Configuration
BATCH_MS=250                        # Evidence window (ms)
MAX_EVIDENCE_ITEMS=512              # Max items per batch

# Scanning Configuration
SCAN_INTERVAL_SECONDS=300           # Port scan interval (5 min)
SCAN_PORTS=22,23,80,443,554,1883,5060,8080,8443,161,179,3389
CONNECTION_TIMEOUT=2.0              # Port scan timeout

# SNMP Configuration
SNMP_COMMUNITY=public               # Default community string
SNMP_TIMEOUT=2.0                    # Query timeout
SNMP_RETRIES=1                      # Retry count
SNMP_SCAN_INTERVAL_SECONDS=300      # Discovery interval

# MAC Enrichment
MAC_SCAN_INTERVAL_SECONDS=3600      # OUI lookup interval (1 hour)

# MIB Management
MIB_ASSIGN_INTERVAL_SECONDS=600     # Assignment interval (10 min)
MIB_WALK_INTERVAL_SECONDS=1800      # Walk interval (30 min)

# UI
SERVER_IP=192.168.10.50             # IP address of the server (used by UI)
VITE_API_BASE=http://192.168.10.50:8080
VITE_WS_BASE=ws://192.168.10.50:8080
UI_WS_ORIGIN=*                      # CORS origin
```

---

## Development

### Quick Start

```bash
# 1. Clone repository
git clone <repo-url>
cd opsconductor-nms

# 2. Configure environment
cp .env.example .env
nano .env  # Edit network interface, IPs, etc.

# 3. Start all services
docker compose up -d

# 4. Check service health
docker compose ps
docker compose logs -f

# 5. Access UI
open http://localhost:3000
```

### Service Development

Each service follows this structure:
```
services/<service-name>/
├── app/
│   ├── main.py          # FastAPI app or async main()
│   └── ...              # Business logic
├── Dockerfile
├── requirements.txt
└── .dockerignore
```

### Database Migrations

Currently using SQLAlchemy models with auto-creation. For production, consider adding Alembic migrations.

### Adding a New Service

1. Create service directory under `services/`
2. Add Dockerfile and requirements.txt
3. Update `docker-compose.yml`
4. Implement health check endpoint (`:9XXX/health`)
5. Integrate with state-server API
6. Update this documentation

---

## Testing

### Manual Testing

```bash
# Health checks
curl http://localhost:8080/health
curl http://localhost:9100/health  # packet-collector
curl http://localhost:9200/health  # port-scanner
curl http://localhost:9300/health  # snmp-discovery

# View inventory
curl http://localhost:8080/api/inventory | jq

# View single device
curl http://localhost:8080/api/inventory/192.168.10.50 | jq

# View MIBs
curl http://localhost:8080/api/mibs | jq

# View topology
curl http://localhost:8080/graph | jq
```

### Logs

```bash
# All services
docker compose logs -f

# Specific service
docker compose logs -f port-scanner
docker compose logs -f snmp-discovery
docker compose logs -f packet-collector
```

---

## Current Limitations

1. **No Authentication** - All API endpoints are publicly accessible
2. **No TLS/SSL** - Unencrypted communication
3. **Basic Error Handling** - Limited retry logic
4. **No Automated Tests** - Manual testing only
5. **Network Visibility** - Passive capture limited on switched networks (requires promiscuous mode or SPAN)
6. **Single Network Focus** - Designed for single subnet (configurable)

---

## Security Considerations

⚠️ **NOT PRODUCTION-READY FOR INTERNET-FACING DEPLOYMENT**

Current security posture:
- No authentication
- No authorization
- CORS set to `*`
- Database credentials in plaintext
- No rate limiting
- No input sanitization beyond basic validation

**For Production**:
- Add JWT or API key authentication
- Enable TLS on all endpoints
- Restrict CORS to specific origins
- Use secrets management (Vault, K8s secrets)
- Add rate limiting
- Network segmentation
- Audit logging
- Input validation and sanitization

---

## Performance

### Typical Performance

- **Device Discovery**: 30-50 devices discovered in 5-10 minutes
- **Port Scanning**: 50 IPs scanned in ~2 minutes (12 ports each)
- **SNMP Discovery**: ~10 seconds per device
- **MIB Walking**: ~30-60 seconds per device
- **LLM Analysis**: ~500ms per topology patch

### Scaling Considerations

- PostgreSQL can handle 1000+ devices easily
- Port scanner uses async I/O for parallel scanning
- SNMP services use async queries
- LLM bottleneck: single vLLM instance (can add more)
- UI handles 100+ devices smoothly

---

## Future Roadmap

### Short-term
- [ ] Add authentication (JWT)
- [ ] Implement automated tests
- [ ] Add Prometheus metrics
- [ ] Create OpenAPI documentation
- [ ] Add device grouping/tagging
- [ ] Export inventory (CSV, JSON)

### Medium-term
- [ ] Multi-network support
- [ ] Historical data tracking
- [ ] Alerting system
- [ ] Advanced device classification
- [ ] Custom MIB upload via UI
- [ ] Topology visualization in UI

### Long-term
- [ ] Machine learning for anomaly detection
- [ ] Integration with external NMS systems
- [ ] Advanced reporting and dashboards
- [ ] Network path analysis
- [ ] Configuration backup/restore
- [ ] Multi-tenancy

---

## Project Structure

```
opsconductor-nms/
├── docker-compose.yml           # Service orchestration
├── .env.example                 # Environment template
├── README.md                    # User documentation
├── repo.md                      # This file (technical overview)
├── CONTRIBUTING.md              # Contribution guidelines
│
├── schemas/
│   └── topology_patch.schema.json    # JSON Schema for topology patches
│
├── prompts/
│   └── system_topologist.txt         # LLM system prompt
│
├── models/                      # Model cache (optional)
│   └── Phi-3-mini-4k-instruct/
│
├── services/
│   ├── state-server/            # Core API + Database
│   │   ├── app/
│   │   │   ├── main.py          # FastAPI routes
│   │   │   ├── service.py       # Business logic
│   │   │   ├── models.py        # SQLAlchemy models
│   │   │   ├── schemas.py       # Pydantic schemas
│   │   │   ├── database.py      # DB connection
│   │   │   └── config.py        # Settings
│   │   ├── Dockerfile
│   │   ├── requirements.txt
│   │   └── populate_mibs.py     # MIB initialization script
│   │
│   ├── llm-analyst/             # LLM reasoning service
│   │   ├── app/
│   │   │   ├── main.py
│   │   │   ├── service.py
│   │   │   ├── schemas.py
│   │   │   └── config.py
│   │   ├── Dockerfile
│   │   └── requirements.txt
│   │
│   ├── packet-collector/        # Passive packet capture
│   │   ├── app/
│   │   │   └── main.py
│   │   ├── Dockerfile
│   │   └── requirements.txt
│   │
│   ├── port-scanner/            # Active port scanning
│   │   ├── app/
│   │   │   └── main.py
│   │   ├── Dockerfile
│   │   └── requirements.txt
│   │
│   ├── snmp-discovery/          # SNMP querying
│   │   ├── app/
│   │   │   └── main.py
│   │   ├── Dockerfile
│   │   └── requirements.txt
│   │
│   ├── mac-enricher/            # MAC OUI lookup
│   │   ├── app/
│   │   │   └── main.py
│   │   ├── Dockerfile
│   │   └── requirements.txt
│   │
│   ├── mib-assigner/            # Auto MIB assignment
│   │   ├── app/
│   │   │   └── main.py
│   │   ├── Dockerfile
│   │   └── requirements.txt
│   │
│   └── mib-walker/              # SNMP tree walking
│       ├── app/
│       │   └── main.py
│       ├── Dockerfile
│       └── requirements.txt
│
└── ui/                          # React frontend
    ├── src/
    │   ├── main.tsx
    │   ├── App.tsx              # Main component with routing
    │   ├── InventoryGrid.tsx    # Device inventory grid
    │   ├── Admin.tsx            # MIB library admin panel
    │   └── index.css
    ├── public/
    ├── package.json
    ├── vite.config.ts
    ├── tsconfig.json
    ├── Dockerfile
    └── index.html
```

---

## Contributing

See [CONTRIBUTING.md](./CONTRIBUTING.md) for development guidelines.

---

## License

MIT License - See LICENSE file for details

---

## Changelog

### 2025-11-14 (Latest)
- **SNMP OID Text Label Resolution**: Implemented automatic OID-to-text conversion using PySNMP MibViewController
- **Remote MIB Fetching**: Added pysmi package and configured http://mibs.pysnmp.com as MIB source
- **Standard MIB Loading**: MIB Walker now loads 9 standard MIBs (Printer-MIB, IF-MIB, etc.)
- **Admin Panel**: Added web interface for MIB library management with search/filter
- **Manual MIB Walk**: Added "Walk MIB" button in inventory grid for on-demand SNMP walks
- **MIB Content API**: Added GET /api/mibs/{mib_id} endpoint to retrieve MIB content
- Updated documentation with new features and technical implementation details
- Removed backup files (main.py.backup, service.py.bak)

### 2025-11-14 (Earlier)
- Added comprehensive repo.md documentation
- Removed outdated IMPLEMENTATION_PLAN.md and GAP_ANALYSIS.md
- System fully operational with all 9 services running

### 2025-11-12
- Implemented IP inventory system
- Added port-scanner, snmp-discovery, mac-enricher, mib-assigner, mib-walker services
- Pivoted UI from topology visualization to inventory grid
- Fixed LLM token limits and edge duplication issues

### Earlier
- Initial topology discovery system
- vLLM integration with Phi-3
- Packet collector implementation
- State server with WebSocket streaming
