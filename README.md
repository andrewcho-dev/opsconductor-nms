# OpsConductor NMS: AI-Powered Network Management System

A comprehensive network management system that automatically discovers, classifies, and monitors network devices using a combination of passive packet observation, active scanning, and AI-powered analysis.

[![Status](https://img.shields.io/badge/status-production--ready-green)]()
[![License](https://img.shields.io/badge/license-MIT-blue)]()

---

## What It Does

OpsConductor NMS automatically:

1. **Discovers Devices** - Finds all devices on your network through passive packet capture and active scanning
2. **Identifies Device Types** - Classifies devices as routers, switches, firewalls, hosts, etc. using port scanning, SNMP, and AI
3. **Enriches Information** - Gathers vendor info, model numbers, open ports, SNMP data, and detailed device metrics
4. **Manages MIBs** - Maintains vendor-specific MIB libraries and automatically assigns them to appropriate devices
5. **Provides Real-Time UI** - Web interface for viewing, filtering, and managing your complete network inventory

---

## Features

- **Automated Discovery**: Passive network observation + active scanning
- **AI Classification**: LLM (Phi-3) analyzes evidence to classify device types
- **SNMP Integration**: Automatic SNMP discovery and detailed metric collection
- **Human-Readable OID Labels**: Resolves numeric SNMP OIDs to text labels (e.g., "prtMarkerLifeCount.1.1")
- **MAC Vendor Lookup**: IEEE OUI database for vendor identification
- **MIB Management**: Built-in MIB library with auto-assignment and remote MIB fetching
- **Real-Time Updates**: WebSocket streaming for live inventory changes
- **IP Inventory Grid**: Searchable, filterable web UI with manual MIB walk triggers
- **Admin Panel**: MIB library management interface with search and filter capabilities
- **PostgreSQL Backend**: Persistent storage with full audit history

---

## Architecture Overview

```
Network Devices
       │
       ├─────────────────┬─────────────────┐
       │                 │                 │
   [Passive]         [Active]         [SNMP]
       │                 │                 │
       ▼                 ▼                 ▼
Packet Collector → Port Scanner → SNMP Discovery
       │                 │                 │
       └─────────┬───────┴─────────────────┘
                 │
                 ▼
         State Server (API + DB)
                 │
       ┌─────────┼─────────┬──────────┐
       ▼         ▼         ▼          ▼
MAC Enricher  MIB      MIB      LLM
              Assigner Walker   Analyst
       │         │         │          │
       └─────────┴─────────┴──────────┘
                 │
                 ▼
         Web UI (Inventory Grid)
```

### Services

| Service | Purpose | Status |
|---------|---------|--------|
| **State Server** | API, database, WebSocket streaming | ✅ Running |
| **Packet Collector** | Passive packet capture (ARP, flows) | ✅ Running |
| **Port Scanner** | Active TCP/UDP port scanning | ✅ Running |
| **SNMP Discovery** | SNMP queries for device info | ✅ Running |
| **MAC Enricher** | MAC OUI vendor lookup | ✅ Running |
| **MIB Assigner** | Automatic MIB assignment | ✅ Running |
| **MIB Walker** | SNMP tree walking with OID text label resolution | ✅ Running |
| **LLM Analyst** | AI-powered device classification | ✅ Running |
| **vLLM** | LLM inference engine (Phi-3) | ✅ Running |
| **UI** | React-based inventory grid | ✅ Running |

---

## Prerequisites

### Hardware

- **CPU**: Modern multi-core processor
- **GPU**: NVIDIA GPU with 8GB+ VRAM (for AI features)
- **RAM**: 16GB minimum, 32GB recommended
- **Storage**: 20GB for models + Docker volumes
- **Network**: Access to network interface in promiscuous mode

### Software

- **Docker** 24.0+ with Docker Compose v2
- **NVIDIA Container Toolkit** (for GPU support)
- **Linux** (tested on Ubuntu 22.04, should work on other distros)

---

## Quick Start

### 1. Clone Repository

```bash
git clone <repository-url>
cd opsconductor-nms
```

### 2. Configure Environment

```bash
cp .env.example .env
nano .env
```

**Required Configuration**:

```bash
# Network interface for packet capture (IMPORTANT!)
PCAP_IFACE=eth0                     # Change to your interface (ip addr show)

# LLM Model
MODEL_NAME=microsoft/Phi-3-mini-4k-instruct
VLLM_MAX_CONTEXT_LEN=8192

# Network seeds (optional but recommended)
GATEWAY_IP=192.168.1.1              # Your default gateway
FIREWALL_IP=                        # Your firewall IP (if known)

# Scanning configuration
SCAN_PORTS=22,23,80,443,554,1883,5060,8080,8443,161,179,3389
SNMP_COMMUNITY=public               # Default SNMP community string
```

### 3. Start Services

```bash
# Start all services in background
docker compose up -d

# View logs (all services)
docker compose logs -f

# View specific service logs
docker compose logs -f port-scanner
docker compose logs -f snmp-discovery

# Check service health
docker compose ps
```

### 4. Access Web UI

Open your browser to:

```
http://localhost:3000
```

You should see the IP Inventory grid, which will populate as devices are discovered.

### 5. Verify Services

```bash
# Check API health
curl http://localhost:8080/health

# View discovered devices
curl http://localhost:8080/api/inventory | jq

# View MIB library
curl http://localhost:8080/api/mibs | jq
```

---

## Usage

### Viewing Inventory

The web UI (http://localhost:3000) provides:

- **Complete Device List**: All discovered IPs with details
- **Column Sorting**: Click column headers to sort
- **Filtering**: Filter by status, device type, vendor, etc.
- **Device Details**: Click row to expand full information
- **Confirmation**: Mark device types as confirmed

### API Access

#### List All Devices

```bash
curl http://localhost:8080/api/inventory | jq
```

#### Filter Devices

```bash
# Active devices only
curl http://localhost:8080/api/inventory?status=active | jq

# Routers only
curl http://localhost:8080/api/inventory?device_type=router | jq

# Confirmed devices
curl http://localhost:8080/api/inventory?confirmed=true | jq
```

#### Get Single Device

```bash
curl http://localhost:8080/api/inventory/192.168.10.50 | jq
```

#### Update Device Information

```bash
curl -X PUT http://localhost:8080/api/inventory/192.168.10.50 \
  -H "Content-Type: application/json" \
  -d '{
    "device_name": "Main Router",
    "device_type": "router",
    "device_type_confirmed": true
  }'
```

#### Confirm Device Type

```bash
curl -X POST http://localhost:8080/api/inventory/192.168.10.50/confirm \
  -H "Content-Type: application/json" \
  -d '{
    "confirmed_by": "admin",
    "confirmed_type": "router",
    "confidence": 1.0,
    "evidence": "Manual verification via console access"
  }'
```

### Managing MIBs

#### List All MIBs

```bash
curl http://localhost:8080/api/mibs | jq
```

#### Get MIB Content

```bash
curl http://localhost:8080/api/mibs/1 | jq
```

#### Add New MIB

```bash
curl -X POST http://localhost:8080/api/mibs \
  -H "Content-Type: application/json" \
  -d '{
    "name": "CISCO-PRODUCTS-MIB",
    "vendor": "Cisco",
    "device_types": ["router", "switch"],
    "version": "1.0",
    "file_path": "/path/to/mib/file",
    "oid_prefix": "1.3.6.1.4.1.9",
    "description": "Cisco product identification MIB"
  }'
```

#### Delete MIB

```bash
curl -X DELETE http://localhost:8080/api/mibs/1
```

#### Trigger Manual MIB Walk

```bash
curl -X POST http://localhost:8080/api/inventory/192.168.10.50/walk-mib
```

**Note**: The MIB walker automatically resolves numeric OIDs to human-readable text labels using PySNMP's MIB resolution. Standard MIBs (SNMPv2-MIB, IF-MIB, Printer-MIB, etc.) are loaded automatically from http://mibs.pysnmp.com.

---

## Configuration

### Service Ports

| Service | Port | Purpose |
|---------|------|---------|
| UI | 3000 | Web interface |
| State Server | 8080 | REST API + WebSocket |
| vLLM | 8000 | LLM inference API |
| LLM Analyst | 8100 | Internal analysis service |
| Packet Collector | 9100 | Health check |
| Port Scanner | 9200 | Health check |
| SNMP Discovery | 9300 | Health check |
| MAC Enricher | 9400 | Health check |
| MIB Assigner | 9500 | Health check |
| MIB Walker | 9600 | Health check |

### Scanning Configuration

Configure in `.env`:

```bash
# Port scanning
SCAN_INTERVAL_SECONDS=300           # Scan every 5 minutes
SCAN_PORTS=22,23,80,443,161,179,3389
CONNECTION_TIMEOUT=2.0              # 2 second timeout per port

# SNMP discovery
SNMP_SCAN_INTERVAL_SECONDS=300      # Discover every 5 minutes
SNMP_COMMUNITY=public               # Community string to try
SNMP_TIMEOUT=2.0
SNMP_RETRIES=1

# MAC enrichment
MAC_SCAN_INTERVAL_SECONDS=3600      # Update every hour

# MIB assignment
MIB_ASSIGN_INTERVAL_SECONDS=600     # Assign every 10 minutes

# MIB walking
MIB_WALK_INTERVAL_SECONDS=1800      # Walk every 30 minutes
```

### Network Interface

**IMPORTANT**: Set the correct network interface in `.env`:

```bash
# Find your interface name
ip addr show
# or
ifconfig

# Set in .env
PCAP_IFACE=eth0  # Change to your actual interface
```

Common interface names:
- `eth0`, `eth1` - Wired Ethernet
- `wlan0`, `wlan1` - Wireless
- `enp0s3`, `enp0s8` - Modern predictable names
- `ens33` - VMware virtual interfaces

---

## Troubleshooting

### No Devices Discovered

**Check**:

1. Network interface is correct:
   ```bash
   docker compose logs packet-collector | grep "interface"
   ```

2. Packet collector has permissions:
   ```bash
   docker compose logs packet-collector
   ```

3. Generate some network traffic:
   ```bash
   ping 8.8.8.8
   ```

### Port Scanner Not Finding Ports

**Check**:

1. Firewall isn't blocking scans
2. Timeout isn't too short (increase `CONNECTION_TIMEOUT`)
3. Logs for errors:
   ```bash
   docker compose logs port-scanner
   ```

### SNMP Not Working

**Check**:

1. SNMP is enabled on devices
2. Community string is correct (`SNMP_COMMUNITY`)
3. Firewall allows UDP 161
4. Logs:
   ```bash
   docker compose logs snmp-discovery
   ```

### LLM Out of Memory

**Solutions**:

```bash
# Reduce context length
VLLM_MAX_CONTEXT_LEN=4096

# Reduce evidence batch size
MAX_EVIDENCE_ITEMS=256
```

Or edit `docker-compose.yml`:
```yaml
services:
  vllm:
    command: >
      --gpu-memory-utilization 0.8  # Reduce from 0.9
```

### UI Not Loading

**Check**:

1. State server is running:
   ```bash
   curl http://localhost:8080/health
   ```

2. Correct API URLs in UI config:
   ```bash
   echo $VITE_API_BASE
   echo $VITE_WS_BASE
   ```

3. CORS configuration in `docker-compose.yml`

---

## API Documentation

### REST API

Full API documentation: See [repo.md](./repo.md#api-endpoints)

**Base URL**: `http://localhost:8080`

**Key Endpoints**:
- `GET /health` - Health check
- `GET /api/inventory` - List devices
- `GET /api/inventory/{ip}` - Get device details
- `PUT /api/inventory/{ip}` - Update device
- `POST /api/inventory/{ip}/confirm` - Confirm device type
- `POST /api/inventory/{ip}/walk-mib` - Trigger manual MIB walk
- `GET /api/mibs` - List MIBs
- `GET /api/mibs/{mib_id}` - Get MIB content
- `POST /api/mibs` - Add MIB
- `DELETE /api/mibs/{mib_id}` - Delete MIB
- `GET /graph` - Get topology graph
- `WS /ws` - WebSocket updates

### WebSocket

Connect to `ws://localhost:8080/ws` for real-time updates.

**Initial message** (snapshot):
```json
{
  "graph": {...},
  "updated_at": "2025-11-14T10:00:00Z",
  "patch": [],
  "rationale": "initial",
  "warnings": []
}
```

**Update messages**:
```json
{
  "graph": {...},
  "updated_at": "2025-11-14T10:00:01Z",
  "patch": [{...}],
  "rationale": "Added new device 192.168.10.100",
  "warnings": []
}
```

---

## Performance

### Typical Performance

- **Discovery Rate**: 30-50 devices in 5-10 minutes
- **Port Scan**: ~2 minutes for 50 devices (12 ports each)
- **SNMP Query**: ~10 seconds per device
- **MIB Walk**: ~30-60 seconds per device
- **AI Classification**: ~500ms per analysis

### Resource Usage

- **CPU**: 10-30% during active scanning
- **RAM**: 8-12GB total (including vLLM)
- **GPU**: 6-8GB VRAM for Phi-3-mini-4k
- **Disk**: ~10GB for models, ~1GB for database (1000 devices)
- **Network**: Minimal (SNMP queries + HTTP API)

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
docker compose logs -f packet-collector
docker compose logs -f port-scanner
docker compose logs -f snmp-discovery
docker compose logs -f state-server
```

### Restarting Services

```bash
# Restart all
docker compose restart

# Restart specific service
docker compose restart port-scanner
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
docker compose exec postgres pg_dump -U topo topology > backup.sql

# Restore
cat backup.sql | docker compose exec -T postgres psql -U topo topology
```

---

## Advanced Configuration

### Custom Prompts

Edit LLM behavior by modifying:

```bash
nano prompts/system_topologist.txt
```

Restart analyst service:
```bash
docker compose restart analyst
```

### Custom JSON Schema

Edit topology patch schema:

```bash
nano schemas/topology_patch.schema.json
```

Restart analyst service:
```bash
docker compose restart analyst
```

### Adding Custom Ports to Scan

Edit `.env`:

```bash
SCAN_PORTS=22,23,80,443,161,179,3389,8080,8443,9000
```

Restart port-scanner:
```bash
docker compose restart port-scanner
```

### Multiple SNMP Communities

Currently supports one community string. For multiple communities, modify:

```bash
services/snmp-discovery/app/main.py
```

Add loop to try multiple community strings.

---

## Development

For development and technical details, see [repo.md](./repo.md).

### Project Structure

```
opsconductor-nms/
├── docker-compose.yml          # Service orchestration
├── .env                        # Configuration
├── README.md                   # This file
├── repo.md                     # Technical documentation
├── CONTRIBUTING.md             # Contribution guide
├── services/                   # Microservices
│   ├── state-server/           # API + Database
│   ├── packet-collector/       # Packet capture
│   ├── port-scanner/           # Port scanning
│   ├── snmp-discovery/         # SNMP queries
│   ├── mac-enricher/           # MAC lookup
│   ├── mib-assigner/           # MIB assignment
│   ├── mib-walker/             # SNMP walking
│   └── llm-analyst/            # AI analysis
├── ui/                         # React frontend
├── schemas/                    # JSON schemas
└── prompts/                    # LLM prompts
```

---

## Contributing

Contributions welcome! Please see [CONTRIBUTING.md](./CONTRIBUTING.md).

---

## Recent Updates

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
- [ ] Topology visualization
- [ ] Configuration backup
- [ ] Anomaly detection

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
