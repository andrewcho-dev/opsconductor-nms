# Inventory Configuration

This directory contains the SuzieQ collector configuration and device inventory.

## Files

- **sq.yaml**: SuzieQ main configuration
- **devices.yaml**: Device inventory (YAML format)

## Quick Start

1. Edit `devices.yaml` and add your network devices:

```yaml
---
- name: my-router
  transport: ssh
  address: 192.168.1.1
  username: admin
  password: changeme  # or use keyfile
  devtype: eos
```

2. Start the services:

```bash
docker compose up -d
```

3. Check SuzieQ logs:

```bash
docker compose logs suzieq
```

## Security Best Practices

### Using Docker Secrets

Instead of storing passwords in `devices.yaml`, use Docker secrets:

1. Create a secret file:
```bash
echo "my_password" > /path/to/secret.txt
```

2. Add to docker-compose.yml:
```yaml
services:
  suzieq:
    secrets:
      - ssh_password
      
secrets:
  ssh_password:
    file: /path/to/secret.txt
```

3. Reference in devices.yaml:
```yaml
- name: my-device
  password_file: /run/secrets/ssh_password
```

### SSH Key Authentication

Recommended for production:

```yaml
- name: my-device
  transport: ssh
  address: 192.168.1.1
  username: admin
  keyfile: /secrets/id_rsa
  devtype: eos
```

## Supported Device Types

| Device Type | Vendor | Notes |
|------------|--------|-------|
| eos | Arista | EOS devices |
| nxos | Cisco | Nexus switches |
| iosxe | Cisco | IOS XE routers/switches |
| junos | Juniper | JunOS devices |
| cumulus | Cumulus | Cumulus Linux |
| sonic | Microsoft | SONiC switches |

## Testing Connectivity

Test a single device before adding to inventory:

```bash
docker compose exec suzieq suzieq-cli device show --hostname=my-router
```

## Troubleshooting

### Device not showing up

1. Check logs: `docker compose logs suzieq`
2. Verify SSH connectivity from the suzieq container
3. Ensure credentials are correct
4. Check device type is supported

### Authentication failures

- Verify username/password
- Check SSH key permissions (0600)
- Ensure device allows SSH from container IP
