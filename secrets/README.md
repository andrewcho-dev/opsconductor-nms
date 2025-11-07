# Secrets Directory

This directory contains sensitive credentials used by the OpsConductor NMS services.

## Required Files

Create the following files with appropriate credentials:

- `db_password.txt` - PostgreSQL password
- `db_user.txt` - PostgreSQL username
- `netbox_api_token.txt` - NetBox API token (optional)
- `netbox_url.txt` - NetBox URL (optional)

## Example

```bash
echo "oc" > secrets/db_user.txt
echo "secure_password_here" > secrets/db_password.txt
echo "your_netbox_token" > secrets/netbox_api_token.txt
echo "https://netbox.example.com" > secrets/netbox_url.txt
```

## Security

- Never commit actual secret files to version control
- Set appropriate file permissions: `chmod 600 secrets/*.txt`
- Use strong, unique passwords in production
