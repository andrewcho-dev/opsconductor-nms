# Nmap Scanner Migration

## Overview
Replaced custom Python port scanner with **full nmap integration** to provide comprehensive network scanning capabilities.

## What Changed

### 1. **New nmap-scanner Service**
- **Location**: `/services/nmap-scanner/`
- **Full nmap capabilities**: OS detection, service version detection, NSE scripts, all 65535 ports
- **Scan profiles**: quick, standard, aggressive, stealth, full
- **Subnet discovery**: Automatically discovers live hosts in IPsec tunnel networks (10.121.x.x)
- **XML parsing**: Complete extraction of all nmap data including:
  - OS fingerprinting with accuracy scores
  - Service versions (product, version, CPE)
  - NSE script results (vulnerability scans, exploits, etc.)
  - MAC address vendor lookup
  - Multiple hostnames per device
  - Uptime information

### 2. **Database Schema Updates**
Added columns to `ip_inventory` table:
- `all_hostnames` - Array of all discovered hostnames
- `os_name` - Operating system name from nmap
- `os_accuracy` - OS detection accuracy percentage
- `os_detection` - Full OS detection data (JSONB)
- `uptime_seconds` - Device uptime
- `host_scripts` - NSE host script results (JSONB)
- `nmap_scan_time` - Timestamp of last nmap scan

### 3. **Enhanced UI**
Updated `InventoryGrid.tsx` to display:
- **OS Detection Panel**: Shows detected OS, accuracy, uptime, scan timestamp
- **NSE Script Results**: Collapsible sections for each script with formatted output
- **Port-Specific Scripts**: Script results for individual ports
- **Service Versions**: Full version info including product, version, CPE identifiers

### 4. **Configuration Options** (`.env`)
```bash
# Scan interval (default: 1 hour)
NMAP_SCAN_INTERVAL_SECONDS=3600

# Scan profile: quick, standard, aggressive, stealth, full
NMAP_SCAN_PROFILE=standard

# Timing template (0-5, default: 4)
NMAP_TIMING=4

# NSE scripts to run
NSE_SCRIPTS=default,vulners,vulscan

# Tunnel networks to discover
TUNNEL_NETWORKS=10.121.0.0/16

# Enable subnet discovery
ENABLE_SUBNET_DISCOVERY=true

# Custom nmap arguments (optional)
CUSTOM_NMAP_ARGS=
```

## Scan Profiles

| Profile | Description | Flags |
|---------|-------------|-------|
| **quick** | Fast scan of common ports | `-F -sV --version-intensity 2` |
| **standard** | All ports + OS + version + scripts | `-p- -sV -O --osscan-guess --script default,vulners,vulscan` |
| **aggressive** | Full scan with all features | `-A -p- -T5 --script default,vulners,vulscan` |
| **stealth** | SYN stealth scan | `-sS -p- -sV -O --osscan-guess` |
| **full** | Maximum detail scan | `-A -p- -sC -sV -O --osscan-guess --version-all` |

## Deployment Steps

### 1. Stop Old Scanner
```bash
docker stop llm-topology-port-scanner-1
docker rm llm-topology-port-scanner-1
```

### 2. Run Database Migration
```bash
docker compose exec postgres psql -U topo -d topology -c "
ALTER TABLE ip_inventory 
ADD COLUMN IF NOT EXISTS all_hostnames TEXT[],
ADD COLUMN IF NOT EXISTS os_name VARCHAR(255),
ADD COLUMN IF NOT EXISTS os_accuracy VARCHAR(10),
ADD COLUMN IF NOT EXISTS os_detection JSONB,
ADD COLUMN IF NOT EXISTS uptime_seconds VARCHAR(50),
ADD COLUMN IF NOT EXISTS host_scripts JSONB,
ADD COLUMN IF NOT EXISTS nmap_scan_time TIMESTAMP WITH TIME ZONE;
"
```

### 3. Build and Start
```bash
docker compose build nmap-scanner
docker compose up -d nmap-scanner
```

### 4. Verify
```bash
# Check health
curl http://localhost:9200/health

# Watch logs
docker compose logs -f nmap-scanner
```

## Features

### Tunnel Network Discovery
The scanner automatically discovers live hosts in IPsec tunnel networks:
1. Pings subnet (e.g., `10.121.0.0/16`) to find live hosts
2. Adds discovered hosts to scan targets
3. Performs full nmap scan on all discovered devices

### NSE Scripts
Default scripts include:
- **vulners**: CVE vulnerability detection
- **vulscan**: Extended vulnerability database
- **default**: Standard nmap scripts (auth, broadcast, discovery, etc.)

### Service Detection
Captures full service information:
- Service name (http, ssh, telnet, etc.)
- Product (Apache, OpenSSH, etc.)
- Version (2.4.41, 8.2p1, etc.)
- Extra info (OS, device type, etc.)
- CPE identifiers for vulnerability tracking

## Performance

| Scan Type | ~50 Devices | Notes |
|-----------|-------------|-------|
| **quick** | ~10 min | Common ports only |
| **standard** | ~45 min | All ports + OS + version |
| **full** | ~90 min | Maximum detail |

## Security

- Runs with `NET_ADMIN` and `NET_RAW` capabilities for raw socket access
- Uses `network_mode: host` for direct network access
- Requires privileged mode for OS fingerprinting
- SYN scans leave minimal footprint in target logs

## Troubleshooting

### No hosts discovered
- Check `TUNNEL_NETWORKS` environment variable
- Verify routes to tunnel networks exist
- Check firewall rules allow ICMP/scanning

### Scan too slow
- Reduce `NMAP_TIMING` (T3 or T2)
- Use `quick` profile for faster scans
- Limit `NSE_SCRIPTS` to fewer scripts

### Port already allocated
- Old port-scanner still running: `docker stop llm-topology-port-scanner-1`

## Migration Benefits

✅ **Full port coverage**: Scans all 65535 ports vs 12 hardcoded ports  
✅ **OS detection**: Identifies operating systems with accuracy scores  
✅ **Service versioning**: Captures exact software versions  
✅ **Vulnerability scanning**: NSE scripts detect known CVEs  
✅ **Tunnel discovery**: Automatically finds devices in IPsec networks  
✅ **Industry standard**: Uses proven nmap instead of custom code  
✅ **Extensibility**: 600+ NSE scripts available  
✅ **Better fingerprinting**: Advanced TCP/IP stack analysis  

## Files Changed

- ✅ Created `/services/nmap-scanner/` - New nmap service
- ✅ Updated `/services/state-server/app/models.py` - Database schema
- ✅ Updated `/ui/src/InventoryGrid.tsx` - UI enhancements
- ✅ Updated `/docker-compose.yml` - Service replacement
- ✅ Updated `/.env` - Configuration options
- ✅ Deleted `/services/port-scanner/` - Old scanner removed
