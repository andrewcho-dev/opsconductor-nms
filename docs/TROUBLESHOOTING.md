# OpsConductor NMS Troubleshooting Guide

This guide provides step-by-step instructions for common network troubleshooting scenarios using OpsConductor NMS.

## Table of Contents

1. [Finding a Path Between Devices](#finding-a-path-between-devices)
2. [Who is Connected to Port X?](#who-is-connected-to-port-x)
3. [What's Impacted if Device/Port Fails?](#whats-impacted-if-deviceport-fails)
4. [Verifying LLDP/CDP Discovery](#verifying-lldpcdp-discovery)
5. [Checking Interface Status](#checking-interface-status)
6. [Investigating Missing Devices](#investigating-missing-devices)
7. [NetBox Integration Issues](#netbox-integration-issues)
8. [Database Connection Issues](#database-connection-issues)

---

## Finding a Path Between Devices

### Use Case
You need to understand the network path between two devices (e.g., from a router to a server).

### Using the UI

1. Navigate to **Path Query** tab in the web interface
2. Select **Source Device** from the dropdown
3. Select **Target Device** from the dropdown
4. Click **Find Path**
5. Review the hop-by-hop path with confidence scores

### Using the API

```bash
curl "http://localhost:8080/topology/path?src_dev=device1&dst_dev=device2"
```

**Response:**
```json
{
  "path": [
    {
      "device": "device1",
      "interface": "GigabitEthernet0/0",
      "method": "lldp",
      "confidence": 1.0
    },
    {
      "device": "device2",
      "interface": "GigabitEthernet1/0",
      "method": "lldp",
      "confidence": 1.0
    }
  ],
  "total_hops": 2
}
```

### Using SQL

```sql
WITH RECURSIVE path_search AS (
    SELECT 
        a_dev as device,
        a_if as interface,
        b_dev as next_device,
        method,
        confidence,
        ARRAY[a_dev] as visited,
        1 as hop_count
    FROM vw_links_canonical
    WHERE a_dev = 'device1'
    
    UNION ALL
    
    SELECT 
        e.a_dev,
        e.a_if,
        e.b_dev,
        e.method,
        e.confidence,
        ps.visited || e.a_dev,
        ps.hop_count + 1
    FROM path_search ps
    JOIN vw_links_canonical e ON ps.next_device = e.a_dev
    WHERE NOT (e.a_dev = ANY(ps.visited))
      AND ps.hop_count < 20
)
SELECT device, interface, method, confidence
FROM path_search
WHERE next_device = 'device2'
ORDER BY hop_count
LIMIT 1;
```

---

## Who is Connected to Port X?

### Use Case
You need to identify what device is connected to a specific port on a switch.

### Using the UI

1. Open the **Topology** view
2. Click on the edge (link) connected to the port of interest
3. The **Port Details** panel will show:
   - Source and target devices
   - Source and target interfaces
   - Discovery method (LLDP/CDP)
   - Interface status (admin/oper up/down)
   - Speed, VLAN, IP, MAC

### Using the API

```bash
curl "http://localhost:8080/topology/edges" | jq '.[] | select(.a_dev=="switch1" and .a_if=="GigabitEthernet1/0/1")'
```

### Using SQL

```sql
SELECT 
    a_dev, a_if, b_dev, b_if, method, confidence, evidence
FROM vw_edges_current
WHERE (a_dev = 'switch1' AND a_if = 'GigabitEthernet1/0/1')
   OR (b_dev = 'switch1' AND b_if = 'GigabitEthernet1/0/1')
ORDER BY last_seen DESC;
```

**Example to find all devices connected to a switch:**

```sql
SELECT DISTINCT b_dev as connected_device, b_if as remote_port
FROM vw_edges_current
WHERE a_dev = 'switch1'
ORDER BY connected_device;
```

---

## What's Impacted if Device/Port Fails?

### Use Case
You need to determine the blast radius if a device or port fails (e.g., for maintenance planning).

### Using the UI

1. Navigate to the **Topology** view
2. Click on the device node
3. The **Impact Analysis** panel will show:
   - List of all downstream devices
   - Total count of affected devices

### Using the API

```bash
# Impact of entire device failing
curl "http://localhost:8080/topology/impact?node=switch1"

# Impact of specific port failing
curl "http://localhost:8080/topology/impact?node=switch1&port=GigabitEthernet1/0/1"
```

**Response:**
```json
{
  "affected_devices": ["server1", "server2", "switch2"],
  "affected_count": 3
}
```

### Using SQL

```sql
WITH RECURSIVE downstream AS (
    SELECT DISTINCT b_dev as device
    FROM vw_links_canonical
    WHERE a_dev = 'switch1'
    
    UNION
    
    SELECT DISTINCT e.b_dev
    FROM downstream d
    JOIN vw_links_canonical e ON d.device = e.a_dev
    WHERE e.b_dev != 'switch1'
)
SELECT device FROM downstream ORDER BY device;
```

---

## Verifying LLDP/CDP Discovery

### Use Case
Troubleshoot why a device isn't appearing in the topology or why links are missing.

### Check if Device is Being Polled

```bash
# Via SuzieQ API
curl "http://localhost:8000/api/v2/device/show?access_token=opsconductor-dev-key-12345"
```

### Check LLDP Status on Device

```bash
# Via SuzieQ API
curl "http://localhost:8000/api/v2/lldp/show?hostname=device1&access_token=opsconductor-dev-key-12345"
```

### Check Database for LLDP Facts

```sql
SELECT * FROM facts_lldp 
WHERE device = 'device1' 
ORDER BY collected_at DESC 
LIMIT 10;
```

### Common Issues

1. **LLDP not enabled on device**
   - Solution: Enable LLDP on the device (see device configuration guides)

2. **Device not in inventory**
   - Solution: Add device to `inventory/devices.yaml`

3. **Authentication failure**
   - Solution: Verify credentials in `inventory/devices.yaml`

4. **Device marked as "neverpoll"**
   - Check SuzieQ status: `docker exec -it <suzieq-container> sq-cli device show`

---

## Checking Interface Status

### Use Case
Verify if an interface is administratively up and operationally up.

### Using the API

```bash
curl "http://localhost:8080/topology/interface?device=router1&ifname=GigabitEthernet0/0"
```

**Response:**
```json
{
  "device": "router1",
  "ifname": "GigabitEthernet0/0",
  "admin_up": true,
  "oper_up": true,
  "speed_mbps": 1000,
  "vlan": null,
  "l3_addr": "10.120.0.1",
  "l2_mac": "00:50:56:a1:b2:c3",
  "last_seen": "2025-11-07T00:00:00Z"
}
```

### Using SQL

```sql
SELECT * FROM interfaces 
WHERE device = 'router1' AND ifname = 'GigabitEthernet0/0';
```

### Check All Down Interfaces

```sql
SELECT device, ifname, admin_up, oper_up, last_seen
FROM interfaces
WHERE oper_up = false
ORDER BY device, ifname;
```

---

## Investigating Missing Devices

### Symptom
A device is in the inventory but not showing in the topology.

### Diagnostic Steps

1. **Check if device is reachable**
   ```bash
   ping <device-ip>
   ssh <device-ip>
   ```

2. **Check SuzieQ poller logs**
   ```bash
   docker logs <suzieq-container-name>
   ```

3. **Check if device is in database**
   ```sql
   SELECT * FROM devices WHERE name = 'missing-device';
   ```

4. **Check normalizer logs**
   ```bash
   docker logs topo-normalizer
   ```

5. **Verify device in inventory**
   ```bash
   cat inventory/devices.yaml
   ```

6. **Force a poll**
   ```bash
   docker exec <suzieq-container> sq-cli device poll <device-name>
   ```

### Common Causes

- **Wrong IP address**: Verify management IP in inventory
- **Wrong credentials**: Check username/password in `devices.yaml`
- **Firewall blocking**: Ensure SSH (port 22) is allowed
- **Unsupported device type**: Check SuzieQ supported platforms
- **Device unreachable**: Network connectivity issue

---

## NetBox Integration Issues

### Syncing Devices to NetBox

```bash
# Sync all devices
curl -X POST "http://localhost:8080/netbox/sync/devices"

# Sync devices from specific site
curl -X POST "http://localhost:8080/netbox/sync/devices?site=datacenter1"
```

### Syncing Cables to NetBox

```bash
# Sync cables with minimum 80% confidence
curl -X POST "http://localhost:8080/netbox/sync/cables?min_confidence=0.8"
```

### Sync Everything

```bash
curl -X POST "http://localhost:8080/netbox/sync/all?site=datacenter1&min_confidence=0.8"
```

### Common Issues

1. **NetBox not configured**
   - Error: `NetBox integration not configured`
   - Solution: Set environment variables:
     ```bash
     export NETBOX_URL="https://netbox.example.com"
     export NETBOX_API_TOKEN="your-token-here"
     ```

2. **Authentication failure**
   - Check that API token is valid
   - Verify token has write permissions

3. **Missing objects in NetBox**
   - The integration auto-creates sites, manufacturers, device types
   - If failing, check NetBox logs for permission issues

---

## Database Connection Issues

### Symptom
API returns 503 errors or "Database not connected"

### Diagnostic Steps

1. **Check database container status**
   ```bash
   docker ps | grep db
   docker logs db
   ```

2. **Verify database credentials**
   ```bash
   cat secrets/db_user.txt
   cat secrets/db_password.txt
   ```

3. **Test database connection**
   ```bash
   docker exec -it db psql -U oc -d opsconductor -c "SELECT 1"
   ```

4. **Check API database connection**
   ```bash
   curl http://localhost:8080/healthz
   ```

5. **Check connection pool status**
   - Review API logs for pool exhaustion errors
   - Consider increasing `DB_POOL_MAX_SIZE` environment variable

### Environment Variables for Tuning

```bash
# In docker-compose.yml or .env
DB_POOL_MIN_SIZE=5        # Minimum connections
DB_POOL_MAX_SIZE=20       # Maximum connections
DB_COMMAND_TIMEOUT=30     # Query timeout in seconds
PG_DSN=postgresql://oc:oc@localhost/opsconductor
```

---

## Quick Reference Commands

### Service Status
```bash
make ps                    # List all containers
docker compose logs -f     # Follow all logs
docker logs <container>    # View specific container logs
```

### API Health
```bash
curl http://localhost:8080/healthz
curl http://localhost:8080/docs
```

### Database Access
```bash
docker exec -it db psql -U oc -d opsconductor
```

### Restart Services
```bash
make down && make up       # Restart all services
docker restart <container> # Restart specific container
```

### View Topology Data
```bash
curl http://localhost:8080/topology/nodes | jq
curl http://localhost:8080/topology/edges | jq
curl http://localhost:8080/topology/edges/enriched | jq
```

---

## Performance Tuning

### Increase Polling Frequency

Edit `inventory/sq.yaml`:
```yaml
poller:
  period: 300  # Reduce from 300s (5min) to 60s (1min)
```

### Optimize Database Queries

Check slow queries:
```sql
SELECT query, mean_exec_time, calls
FROM pg_stat_statements
ORDER BY mean_exec_time DESC
LIMIT 10;
```

### Increase API Rate Limits

Edit `services/api/main.py`:
```python
limiter = Limiter(key_func=get_remote_address, default_limits=["200/minute"])
```

---

## Support

For additional help:
- Check logs: `docker compose logs -f`
- API documentation: http://localhost:8080/docs
- Project issues: GitHub issues page
- Architecture docs: `docs/ARCHITECTURE.md`
- Implementation plan: `docs/IMPLEMENTATION_PLAN.md`
