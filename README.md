# OpsConductor NMS: Network Management System

A comprehensive network management system for managing network device inventory and discovering router topologies via SNMP.

[![Status](https://img.shields.io/badge/status-production--ready-green)]()
[![License](https://img.shields.io/badge/license-MIT-blue)]()

---

## What It Does

OpsConductor NMS provides:

1. **IP Inventory Management** - Track all discovered network devices with full device details and metadata
2. **Router Topology Discovery** - Recursively discover router networks by crawling SNMP routing tables starting from a root IP
3. **Device Classification** - Classify routers vs non-routers using SNMP and routing heuristics
4. **Layer 2 & L3 Topology** - Visualize physical (LLDP-based) and logical (routing-based) network connections
5. **SNMP Data Collection** - Gather vendor info, LLDP neighbors, and SNMP metrics per device
6. **MIB Library Management** - Maintain and manage SNMP MIB files for device-specific queries
7. **Real-Time UI** - Web interface for inventory management, topology visualization, and discovery operations

---

## Features

- **Router Discovery Service**: Independent service that crawls router topologies via SNMP with BFS algorithm
- **Device Inventory**: Complete IP/MAC/vendor/model tracking with status and timestamps
- **Discovery Runs**: Track multiple discovery operations with state (PENDING, RUNNING, COMPLETED, FAILED, CANCELLED)
- **Topology Visualization**: Layer 2 (LLDP-based), Layer 3 (routing-based), and router topology graphs
- **SNMP Integration**: SNMPv2c and SNMPv3 support for device queries and metrics
- **MIB Management**: Library management UI for vendor-specific MIB files
- **Multi-tab UI**: Inventory Grid, Admin Panel, Topology Map, and Discovery Page
- **Real-Time Updates**: WebSocket streaming for live inventory and topology changes
- **PostgreSQL Backend**: Persistent storage with full audit history

---

## Architecture Overview

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
│  - ip_inventory                                      │
│  - device_confirmations                              │
│  - mibs                                              │
│  - graph_state & patch_events                        │
│  - discovery_runs, routers, routes, networks, edges  │
└──────────────────────────────────────────────────────┘
```

### Services

| Service | Purpose | Port | Status |
|---------|---------|------|--------|
| **State Server** | IP Inventory API, topology, WebSocket, MIB management | 8080 | ✅ Running |
| **Router Discovery** | SNMP-based router topology crawler with BFS | 8200 | ✅ Running |
| **PostgreSQL** | Database (ip_inventory, discovery_runs, routes, topologies) | 5432 | ✅ Running |
| **UI** | React web interface (inventory, discovery, topology, admin) | 3000 | ✅ Running |

---

## Prerequisites

### Hardware

- **CPU**: Modern multi-core processor
- **RAM**: 4GB minimum, 8GB recommended
- **Storage**: 5GB for Docker volumes
- **Network**: Network connectivity to devices to be scanned (SNMP on port 161)

### Software

- **Docker** 24.0+ with Docker Compose v2
- **Linux** (tested on Ubuntu 22.04, should work on other distros)

---

## Quick Start

### 1. Clone Repository

```bash
git clone https://github.com/andrewcho-dev/opsconductor-nms.git
cd opsconductor-nms
```

### 2. Configure Environment (Optional)

Default configuration should work out of the box. To customize:

```bash
cp .env.example .env
# Edit .env if needed
```

### 3. Start Services

```bash
# Start all services in background
docker compose up -d

# View logs
docker compose logs -f

# View specific service logs
docker compose logs -f state-server
docker compose logs -f router-discovery

# Check service health
docker compose ps
```

### 4. Access Web UI

Open your browser to:

```
http://localhost:3000
```

You'll see the **Inventory Grid** with an empty device list initially. Use the **Discovery Page** to crawl router topologies.

### 5. Verify Services

```bash
# Check State Server health
curl http://localhost:8080/health

# Check Router Discovery health
curl http://localhost:8200/health

# List inventory (empty initially)
curl http://localhost:8080/api/inventory | jq

# List MIBs
curl http://localhost:8080/api/mibs | jq
```

### 6. Perform Router Discovery

Use the **Discovery Page** in the UI:
1. Enter a root router IP (e.g., your gateway)
2. Set SNMP community string (default: `public`)
3. Click "Start Discovery"
4. Monitor progress as routers are discovered
5. View resulting topology graph

Or use the API:
```bash
# Start discovery
curl -X POST http://localhost:8200/api/router-discovery/start \
  -H "Content-Type: application/json" \
  -d '{
    "root_ip": "192.168.1.1",
    "snmp_community": "public",
    "snmp_version": "2c"
  }'

# Check run state
curl http://localhost:8200/api/router-discovery/runs/1/state | jq

# Get topology
curl http://localhost:8200/api/router-discovery/runs/1/topology | jq
```

---

## Usage

### Web UI

The web UI (http://localhost:3000) has four main pages:

#### Inventory Grid
- View all discovered IP addresses with device details
- Column sorting and filtering by status, device type, vendor, etc.
- Click rows to expand device information
- Mark device types as confirmed manually

#### Discovery Page
- Input root router IP and SNMP community string
- Start/pause/resume/cancel discovery runs
- Monitor router crawl progress in real-time
- View discovered router topology graph

#### Topology Map
- Visualize Layer 2 topology (physical connections via LLDP)
- Visualize Layer 3 topology (logical routing connections)
- Interactive node/edge visualization
- Identify root bridge and STP spanning tree

#### Admin Panel
- Manage MIB library
- Add/delete MIB files
- Search and filter MIBs by vendor and device type

### API Access

#### State Server API (port 8080)

**Inventory Management**
```bash
# List all devices
curl http://localhost:8080/api/inventory | jq

# Filter devices
curl "http://localhost:8080/api/inventory?status=active" | jq
curl "http://localhost:8080/api/inventory?device_type=router" | jq

# Get single device
curl http://localhost:8080/api/inventory/192.168.1.50 | jq

# Get device neighbors (LLDP)
curl http://localhost:8080/api/inventory/192.168.1.50/neighbors | jq

# Update device
curl -X PUT http://localhost:8080/api/inventory/192.168.1.50 \
  -H "Content-Type: application/json" \
  -d '{
    "device_name": "Core Router",
    "device_type": "router"
  }'

# Confirm device type
curl -X POST http://localhost:8080/api/inventory/192.168.1.50/confirm \
  -H "Content-Type: application/json" \
  -d '{
    "confirmed_by": "admin",
    "confirmed_type": "router",
    "confidence": 1.0,
    "evidence": "Verified via console"
  }'
```

**Topology APIs**
```bash
# Get Layer 2 topology (LLDP-based, with STP tree)
curl http://localhost:8080/api/topology/layer2 | jq

# Get Layer 3 topology (routing-based)
curl http://localhost:8080/api/topology/l3 | jq

# Get Layer 2 switches topology
curl http://localhost:8080/api/topology/l2 | jq
```

**MIB Management**
```bash
# List all MIBs
curl http://localhost:8080/api/mibs | jq

# Get MIB by ID
curl http://localhost:8080/api/mibs/1 | jq

# Add new MIB
curl -X POST http://localhost:8080/api/mibs \
  -H "Content-Type: application/json" \
  -d '{
    "name": "CISCO-PRODUCTS-MIB",
    "vendor": "Cisco",
    "device_types": ["router"],
    "version": "1.0",
    "file_path": "/path/to/mib",
    "oid_prefix": "1.3.6.1.4.1.9"
  }'

# Delete MIB
curl -X DELETE http://localhost:8080/api/mibs/1
```

#### Router Discovery API (port 8200)

**Discovery Operations**
```bash
# Start discovery from root IP
curl -X POST http://localhost:8200/api/router-discovery/start \
  -H "Content-Type: application/json" \
  -d '{
    "root_ip": "192.168.1.1",
    "snmp_community": "public",
    "snmp_version": "2c"
  }'

# Get discovery run state
curl http://localhost:8200/api/router-discovery/runs/1/state | jq

# Get discovered topology
curl http://localhost:8200/api/router-discovery/runs/1/topology | jq

# Get specific router details
curl http://localhost:8200/api/router-discovery/runs/1/routers/1 | jq

# Pause/resume/cancel discovery
curl -X POST http://localhost:8200/api/router-discovery/runs/1/pause
curl -X POST http://localhost:8200/api/router-discovery/runs/1/resume
curl -X POST http://localhost:8200/api/router-discovery/runs/1/cancel
```

**Real-time Updates**
```bash
# WebSocket connection for live updates
wscat -c ws://localhost:8080/ws
```

---

## Configuration

### Service Ports

| Service | Port | Purpose |
|---------|------|---------|
| **UI** | 3000 | Web interface (React) |
| **State Server** | 8080 | REST API + WebSocket |
| **Router Discovery** | 8200 | Router topology crawler API |
| **PostgreSQL** | 5432 | Database (internal) |

### Environment Variables

See `.env.example` for all available options. Common settings:

```bash
# UI configuration
VITE_API_BASE=http://localhost:8080
VITE_WS_BASE=ws://localhost:8080

# Server configuration
DB_URL=postgresql://opsconductor:opsconductor@postgres:5432/opsconductor
API_PORT=8080
UI_WS_ORIGIN=*  # CORS for WebSocket

# Model configuration (if enabling GPU services)
MODEL_NAME=microsoft/Phi-3-mini-4k-instruct
VLLM_MAX_CONTEXT_LEN=8192
HF_TOKEN=  # HuggingFace token for model downloads
```

---

## Troubleshooting

### Discovery Not Starting

**Check logs**:
```bash
docker compose logs router-discovery
```

**Common issues**:
- Invalid root IP address (must be reachable and have SNMP enabled)
- SNMP community string incorrect (default: `public`)
- Firewall blocking UDP 161 to target devices
- Already running discovery (only one discovery at a time)

### SNMP Queries Failing

**Check**:
1. SNMP is enabled on target devices
2. Community string is correct
3. Firewall allows UDP 161 (SNMP)
4. Try manual query:
   ```bash
   snmpwalk -v2c -c public 192.168.1.1 sysDescr
   ```

### UI Not Loading

**Check**:
1. State server is running:
   ```bash
   curl http://localhost:8080/health
   ```
2. View UI logs:
   ```bash
   docker compose logs ui
   ```
3. Check browser console for errors

### Database Connection Failed

**Check**:
1. PostgreSQL is running:
   ```bash
   docker compose ps postgres
   ```
2. Connection string in state-server logs:
   ```bash
   docker compose logs state-server | grep "database"
   ```
3. Verify credentials in `docker-compose.yml`

### Topology Map Is Empty

**Likely causes**:
- No devices have LLDP neighbor data (SNMP not configured yet)
- LLDP data not populated in `snmp_data.lldp` field
- Try adding devices to inventory first

---

## API Documentation

Full API documentation with all endpoints: See [repo.md](./repo.md#api-endpoints)

### State Server (port 8080)

**Health & Status**:
- `GET /health` - Service health check

**Graph/Topology**:
- `GET /graph` - Get topology graph
- `POST /patch` - Apply JSON patch to topology
- `GET /patches` - Get patch history

**Inventory**:
- `GET /api/inventory` - List all devices
- `GET /api/inventory/{ip}` - Get device details
- `GET /api/inventory/{ip}/neighbors` - Get LLDP neighbors
- `POST /api/inventory` - Create device
- `PUT /api/inventory/{ip}` - Update device
- `POST /api/inventory/{ip}/confirm` - Confirm device type

**Topology**:
- `GET /api/topology/layer2` - Get Layer 2 topology (LLDP + STP)
- `GET /api/topology/l2` - Get L2 switch topology
- `GET /api/topology/l3` - Get Layer 3 routing topology

**MIBs**:
- `GET /api/mibs` - List MIBs
- `GET /api/mibs/{id}` - Get MIB content
- `POST /api/mibs` - Add MIB
- `DELETE /api/mibs/{id}` - Delete MIB
- `GET /api/inventory/{ip}/mibs/suggestions` - Get MIB suggestions
- `POST /api/inventory/{ip}/mibs/reassign` - Reassign MIB
- `POST /api/inventory/{ip}/mibs/walk` - Trigger MIB walk

**WebSocket**:
- `WS /ws` - Real-time topology updates

### Router Discovery (port 8200)

**Discovery Control**:
- `POST /api/router-discovery/start` - Start new discovery run
- `GET /api/router-discovery/runs/{run_id}/state` - Get run state
- `POST /api/router-discovery/runs/{run_id}/pause` - Pause run
- `POST /api/router-discovery/runs/{run_id}/resume` - Resume run
- `POST /api/router-discovery/runs/{run_id}/cancel` - Cancel run

**Data Retrieval**:
- `GET /api/router-discovery/runs/{run_id}/topology` - Get router topology
- `GET /api/router-discovery/runs/{run_id}/routers/{router_id}` - Get router details

**Health**:
- `GET /health` - Service health check

---

## Performance

### Router Discovery Performance

- **BFS Crawl Rate**: 5-20 routers per minute (SNMP response time dependent)
- **SNMP Query**: ~1-5 seconds per device (timeout configurable)
- **Network Analysis**: Per-device networking heuristic ~50-100ms
- **Topology Graph**: Real-time updates as routers discovered

### Resource Usage

- **CPU**: 5-15% during discovery crawl
- **RAM**: 2-4GB typical (mostly PostgreSQL)
- **Disk**: ~500MB database for 500 routers + routes
- **Network**: SNMP queries only (UDP 161)

---

## Security

⚠️ **IMPORTANT**: This system is designed for **internal network use only**.

### Current Security Posture

- ❌ No authentication on API endpoints
- ❌ No authorization/RBAC
- ❌ No TLS/SSL encryption
- ❌ CORS set to `*` (allow all)
- ❌ Database credentials in plaintext `.env`
- ❌ No rate limiting
- ✅ Network segmentation (Docker networks)
- ✅ No data transmitted externally

### Production Recommendations

**Do NOT expose to the internet without**:

1. **Adding authentication** (JWT, OAuth, API keys)
2. **Enabling TLS/SSL** on all endpoints
3. **Restricting CORS** to specific trusted origins
4. **Using secrets management** (HashiCorp Vault, Kubernetes secrets)
5. **Implementing rate limiting**
6. **Adding audit logging**
7. **Network segmentation and firewalling**
8. **Regular security updates**

---

## Maintenance

### Viewing Logs

```bash
# All services
docker compose logs -f

# Specific service
docker compose logs -f state-server
docker compose logs -f router-discovery
docker compose logs -f postgres
```

### Restarting Services

```bash
# Restart all
docker compose restart

# Restart specific service
docker compose restart state-server
docker compose restart router-discovery
```

### Stopping Services

```bash
# Stop all (preserves data)
docker compose down

# Stop and remove volumes (DELETES DATABASE)
docker compose down -v
```

### Updating

```bash
# Pull latest changes
git pull

# Rebuild containers
docker compose build

# Restart with new images
docker compose up -d
```

### Database Backup

```bash
# Backup PostgreSQL database
docker compose exec postgres pg_dump -U opsconductor opsconductor > backup.sql

# Restore
cat backup.sql | docker compose exec -T postgres psql -U opsconductor opsconductor
```

---

## Advanced Configuration

### Multiple SNMP Versions

Router discovery supports both SNMPv2c and SNMPv3. Use the Discovery Page to specify:
- SNMP version: `2c` or `3`
- Community string (SNMPv2c) or credentials (SNMPv3)

### Adjusting Discovery Timeout

Edit `services/router-discovery/app/api.py`:
```python
snmp_adapter = SnmpAdapter(timeout=5, retries=2)  # Change timeout/retries
```

Then rebuild:
```bash
docker compose build router-discovery
docker compose up -d router-discovery
```

---

## Development

For development and technical details, see [repo.md](./repo.md).

### Project Structure

```
opsconductor-nms/
├── docker-compose.yml               # Service orchestration
├── .env.example                    # Configuration template
├── README.md                       # This file
├── repo.md                         # Technical documentation
├── CONTRIBUTING.md                 # Contribution guide
├── services/                       # Microservices
│   ├── state-server/               # IP Inventory API + Topology
│   │   ├── app/
│   │   │   ├── main.py            # FastAPI app
│   │   │   ├── models.py          # Database models
│   │   │   ├── schemas.py         # Request/response schemas
│   │   │   └── service.py         # Business logic
│   │   └── requirements.txt
│   ├── router-discovery/           # Router topology crawler
│   │   ├── app/
│   │   │   ├── main.py            # FastAPI app
│   │   │   ├── api.py             # API endpoints
│   │   │   ├── crawler.py         # BFS router crawler
│   │   │   ├── snmp_adapter.py    # SNMP client wrapper
│   │   │   ├── router_classifier.py # Router classification heuristics
│   │   │   └── models.py          # Database models
│   │   ├── migrations/            # Database migrations
│   │   └── requirements.txt
│   └── init-db/                   # Database initialization
├── ui/                            # React frontend
│   ├── src/
│   │   ├── App.tsx               # Main app component
│   │   ├── InventoryGrid.tsx     # Device inventory
│   │   ├── DiscoveryPage.tsx     # Router discovery UI
│   │   ├── TopologyMap.tsx       # Topology visualization
│   │   └── Admin.tsx             # MIB management
│   └── package.json
└── prompts/                       # System prompts (legacy)
```

---

## Contributing

Contributions welcome! Please see [CONTRIBUTING.md](./CONTRIBUTING.md).

---

## Recent Updates

### 2025-11-19

- ✅ **LLDP Neighbor Discovery**: Automatically discovers Layer 2 physical connections using LLDP-MIB
- ✅ **Layer 2 Topology API**: New endpoint for retrieving LLDP-based network topology
- ✅ **Network Role Classification**: Automatic L2/L3/Endpoint classification based on IP forwarding and STP
- ✅ **Device Neighbor API**: View LLDP neighbors with port mappings for any device
- ✅ **Topology Visualization**: Interactive topology map in UI showing physical connections

### 2025-11-14

- ✅ **SNMP OID Text Label Resolution**: OIDs now display as human-readable labels (e.g., "prtInputName.1.1" instead of "1.1.3.1")
- ✅ **Remote MIB Fetching**: Automatic MIB download from http://mibs.pysnmp.com for standard MIBs
- ✅ **Admin Panel**: Web interface for managing MIB library with search and filtering
- ✅ **Manual MIB Walk**: Trigger on-demand SNMP walks from inventory grid
- ✅ **MIB Content API**: GET endpoint to retrieve MIB content by ID

## Roadmap

### Next Release

- [ ] Authentication (JWT)
- [ ] Export inventory (CSV, JSON)
- [ ] Device grouping/tagging
- [ ] Advanced filtering in UI
- [ ] Automated testing

### Future

- [ ] Multi-network support
- [ ] Historical tracking
- [ ] Alerting system
- [ ] Enhanced topology visualization (geographic layout, custom grouping)
- [ ] Configuration backup
- [ ] Anomaly detection
- [ ] CDP (Cisco Discovery Protocol) support alongside LLDP

---

## FAQ

**Q: Why do I need a GPU?**  
A: The AI classification feature uses vLLM with Phi-3, which requires a GPU. You can disable the LLM analyst service if you don't have a GPU (you'll lose AI classification but keep scanning and discovery).

**Q: Can I run this on Windows/Mac?**  
A: Docker Desktop works on Windows/Mac, but packet capture in host network mode may not work properly. Linux is strongly recommended.

**Q: How do I change the network range?**  
A: The system discovers devices automatically. To focus on a specific range, you can filter in the UI or configure BPF filters in packet-collector.

**Q: Does this work with IPv6?**  
A: Partial support. Database supports IPv6, but some services are IPv4-focused. Full IPv6 support is planned.

**Q: Can I add custom device types?**  
A: Yes. Edit the database schema and LLM prompts to add new device types.

**Q: How do I integrate with existing NMS?**  
A: Use the REST API to export inventory data. Integration plugins for specific NMS systems are planned.

---

## License

MIT License - See [LICENSE](./LICENSE) for details.

---

## Support

- **Issues**: [GitHub Issues](https://github.com/yourusername/opsconductor-nms/issues)
- **Documentation**: [Technical Docs](./repo.md)
- **Contributing**: [Contribution Guide](./CONTRIBUTING.md)

---

## Acknowledgments

- **vLLM Team** - Fast LLM inference
- **Microsoft** - Phi-3 model family
- **FastAPI** - Modern Python web framework
- **PostgreSQL** - Reliable database
- **Scapy** - Packet manipulation library
- **React** - UI framework

---

**Built with ❤️ for network administrators everywhere**
