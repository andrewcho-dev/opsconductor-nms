# OpsConductor NMS

**IP-Based Network Topology Discovery & Visualization**

OpsConductor NMS is a network management system that discovers and visualizes network topology using IP addresses instead of hostnames. It combines LLDP/CDP discovery with SNMP-based ARP/MAC table correlation to map devices that don't support traditional discovery protocols.

---

## Quick Start

```bash
# Start all services
docker compose up -d

# Access the UI
open http://localhost:8089

# Access API documentation
open http://localhost:8088/docs
```

**Services will be available at:**
- **UI**: http://localhost:8089 (Topology visualization)
- **API**: http://localhost:8088 (REST endpoints)
- **API Docs**: http://localhost:8088/docs (Swagger/OpenAPI)

---

## Key Features

✅ **IP-Only Topology** - Displays devices by IP address, not hostname  
✅ **SNMP Discovery** - Uses standard MIBs (IP-MIB, BRIDGE-MIB) for ARP/MAC correlation  
✅ **Multi-Method Discovery** - LLDP/CDP + ARP/MAC correlation  
✅ **Vendor-Agnostic** - Works with Cisco, Juniper, Arista, Axis, Planet, FS.com, D-Link, etc.  
✅ **Confidence Scoring** - Each connection has a 0.0-1.0 confidence score  
✅ **Auto-Layout Graph** - React + ELK layout algorithm  
✅ **Path Analysis** - Find Layer 2/3 paths between devices  
✅ **Impact Analysis** - Determine blast radius of failures  

---

## How It Works

### Traditional Discovery Problem

- Requires DNS/hostname resolution
- Breaks when hostnames are inconsistent  
- Needs LLDP/CDP on every device
- Can't discover cameras, IoT devices, embedded switches

### OpsConductor Solution

1. **LLDP/CDP** for devices that support it (confidence: 1.0)
2. **SNMP ARP+MAC correlation** for everything else (confidence: 0.9)
   - Collect ARP table: `IP → MAC`
   - Collect MAC table: `MAC → Port`
   - Join them: `IP → Port`
3. **Display by IP address** - No hostname dependency
4. **Filter link-local addresses** - No 169.254.x.x clutter

---

## Architecture

```
┌────────────────────────────────────────────────────────┐
│  Data Collectors                                       │
│  ┌──────────────┐  ┌──────────────────────────────┐  │
│  │   SuzieQ     │  │      SNMP Poller             │  │
│  │  (SSH/API)   │  │  (ARP/MAC via SNMP)          │  │
│  │  - LLDP/CDP  │  │  - IP-MIB (ARP table)        │  │
│  │  - Interfaces│  │  - BRIDGE-MIB (MAC table)    │  │
│  └──────────────┘  └──────────────────────────────┘  │
└────────────┬───────────────────┬───────────────────────┘
             │                   │
             v                   v
┌────────────────────────────────────────────────────────┐
│  PostgreSQL Database                                   │
│  - devices, interfaces, edges                          │
│  - facts_lldp, facts_arp, facts_mac                   │
└────────────┬───────────────────────────────────────────┘
             │
             v
┌────────────────────────────────────────────────────────┐
│  Topology Normalizer (Python)                          │
│  - Processes LLDP facts → edges                        │
│  - Correlates ARP+MAC → IP-to-port mappings            │
│  - Computes confidence scores                          │
│  - Auto-creates device nodes for discovered IPs        │
└────────────┬───────────────────────────────────────────┘
             │
             v
┌────────────────────────────────────────────────────────┐
│  FastAPI REST Service                                  │
│  /topology/nodes, /topology/edges, /topology/path      │
└────────────┬───────────────────────────────────────────┘
             │
             v
┌────────────────────────────────────────────────────────┐
│  React Web UI (ReactFlow + ELK Layout)                │
│  - Real-time topology visualization                    │
│  - Path queries, impact analysis                       │
└────────────────────────────────────────────────────────┘
```

---

## Configuration

### 1. Configure SSH-Based Devices (SuzieQ)

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

**Supported platforms**: Arista EOS, Cisco IOS/IOS-XE/NX-OS, Juniper JunOS, Cumulus Linux, SONiC

### 2. Configure SNMP-Based Devices

Edit `services/snmp-poller/poller.py`:

```python
DEVICES = [
    {'hostname': 'axis-switch', 'ip': '10.121.19.21', 'community': 'public', 'vendor': 'Axis'},
    {'hostname': 'camera-switch', 'ip': '10.121.20.1', 'community': 'public', 'vendor': 'Planet'},
]
```

Restart the service:

```bash
docker compose restart snmp-poller
```

### 3. Security Setup

Create secrets directory:

```bash
mkdir -p secrets
echo "oc" > secrets/db_user.txt
echo "your-secure-password" > secrets/db_password.txt
```

For SSH key authentication:

```bash
cp ~/.ssh/id_rsa secrets/
chmod 600 secrets/id_rsa
```

---

## Services

| Service | Container | Port | Purpose |
|---------|-----------|------|---------|
| **ui** | opsconductor-nms-ui-1 | 8089 | React web interface |
| **api** | opsconductor-nms-api-1 | 8088 | FastAPI REST API |
| **db** | opsconductor-nms-db-1 | 5432 | PostgreSQL database |
| **topo-normalizer** | opsconductor-nms-topo-normalizer-1 | - | Topology computation (runs every 5 min) |
| **suzieq** | opsconductor-nms-suzieq-1 | 8000 | SSH/API data collector |
| **snmp-poller** | opsconductor-nms-snmp-poller-1 | - | SNMP data collector (runs every 60 sec) |

---

## API Examples

### List Devices

```bash
curl "http://localhost:8088/topology/nodes"
```

### List Connections

```bash
curl "http://localhost:8088/topology/edges?min_conf=0.8"
```

### Find Path Between Devices

```bash
curl "http://localhost:8088/topology/path?src_dev=10.121.19.101&dst_dev=10.121.19.1"
```

### Calculate Impact of Failure

```bash
curl "http://localhost:8088/topology/impact?node=10.121.19.21"
```

---

## Discovery Methods

### LLDP/CDP (Confidence: 1.0)

- **Source**: SuzieQ collector via SSH
- **Best for**: Modern switches and routers
- **Requires**: LLDP or CDP enabled, SSH access

### ARP+MAC Correlation (Confidence: 0.9)

- **Source**: SNMP poller
- **Best for**: Cameras, IoT, embedded switches without LLDP
- **How it works**:
  1. Collect ARP table (IP→MAC) via SNMP
  2. Collect MAC table (MAC→Port) via SNMP
  3. Join: IP→MAC→Port
  4. Create edge: DeviceIP → SwitchIP:Port

**SNMP OIDs used**:
- `1.3.6.1.2.1.4.35.1.4` - IP-MIB::ipNetToPhysicalPhysAddress (ARP)
- `1.3.6.1.2.1.17.4.3.1.2` - BRIDGE-MIB::dot1dTpFdbPort (MAC table)

---

## Makefile Commands

```bash
make build      # Build all containers
make up         # Start all services
make down       # Stop all services
make ps         # Show service status
make logs       # View logs
make test       # Run test suite
make clean      # Remove containers and volumes
```

---

## Database Access

```bash
# Connect to database
docker exec -it opsconductor-nms-db-1 psql -U oc -d opsconductor

# Example queries
SELECT * FROM devices;
SELECT * FROM edges WHERE confidence > 0.8;
SELECT * FROM facts_arp WHERE device = 'axis-switch';
```

---

## Troubleshooting

### Device not appearing in topology

1. Check if device is reachable: `ping <device-ip>`
2. Verify credentials in `inventory/devices.yaml`
3. Check collector logs: `docker compose logs suzieq` or `docker compose logs snmp-poller`
4. Check database: `docker exec -it opsconductor-nms-db-1 psql -U oc -d opsconductor -c "SELECT * FROM devices;"`

### Missing connections between devices

1. Verify LLDP/CDP is enabled (for SSH-based discovery)
2. Verify SNMP is enabled with correct community string (for SNMP-based discovery)
3. Check facts tables:
   ```sql
   SELECT * FROM facts_lldp WHERE device = 'device-name';
   SELECT * FROM facts_arp WHERE device = 'switch-name';
   SELECT * FROM facts_mac WHERE device = 'switch-name';
   ```

### SNMP poller not collecting data

1. Test SNMP manually:
   ```bash
   docker exec -it opsconductor-nms-snmp-poller-1 \
     snmpwalk -v2c -c public 10.121.19.21 1.3.6.1.2.1.4.35.1.4
   ```
2. Verify community string is correct
3. Check firewall allows SNMP (UDP 161)
4. View poller logs: `docker compose logs snmp-poller`

---

## Documentation

- **[REPO.md](REPO.md)** - Complete repository documentation (READ THIS FIRST)
- **[ARCHITECTURE.md](docs/ARCHITECTURE.md)** - System architecture and design
- **[TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md)** - Detailed troubleshooting guide
- **[STATUS.md](STATUS.md)** - Current implementation status
- **[Inventory README](inventory/README.md)** - Device configuration guide

---

## Development

### Project Structure

```
opsconductor-nms/
├── docker-compose.yml          # Service orchestration
├── inventory/
│   ├── devices.yaml           # SuzieQ device inventory
│   └── sq.yaml                # SuzieQ configuration
├── services/
│   ├── api/                   # FastAPI REST service
│   ├── topo-normalizer/       # Topology computation engine
│   ├── snmp-poller/           # SNMP data collector
│   └── ui/                    # React web interface
├── secrets/                   # Credentials (gitignored)
├── docs/                      # Documentation
└── tests/                     # Test suite
```

### Running Tests

```bash
make test
```

### Adding a Device

**For SSH-capable devices**: Add to `inventory/devices.yaml`  
**For SNMP-only devices**: Add to `services/snmp-poller/poller.py`

---

## Example Deployment

### Home Lab with Mixed Devices

```yaml
# inventory/devices.yaml (SSH-based)
- name: core-switch
  transport: ssh
  address: 10.0.1.1
  username: admin
  password: admin
  devtype: iosxe
```

```python
# services/snmp-poller/poller.py (SNMP-based)
DEVICES = [
    {'hostname': 'axis-camera-switch', 'ip': '10.0.2.1', 'community': 'public', 'vendor': 'Axis'},
    {'hostname': 'poe-switch', 'ip': '10.0.2.2', 'community': 'public', 'vendor': 'Planet'},
]
```

**Result**: Topology map showing:
- Core switch (via LLDP)
- Cameras connected to Axis switch (via ARP+MAC correlation)
- All devices displayed by IP address

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development guidelines.

---

## License

MIT License

---

## Support

- **Issues**: https://github.com/andrewcho-dev/opsconductor-nms/issues
- **Full Documentation**: See [REPO.md](REPO.md)
- **Architecture Details**: See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
