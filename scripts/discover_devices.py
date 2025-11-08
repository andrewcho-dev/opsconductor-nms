#!/usr/bin/env python3
import paramiko
import socket
import ipaddress
import yaml
import sys
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

INVENTORY_FILE = Path(__file__).parent.parent / 'inventory' / 'devices.yaml'
TIMEOUT = 15
MAX_WORKERS = 10

CREDENTIALS = [
    ('admin', 'admin'),
    ('admin', 'Metrolink222'),
    ('root', 'Metrolink222'),
    ('admin', 'Metrolink96$'),
    ('admin', 'Metrolink202'),
    ('root', 'Metrolink202'),
    ('root', 'pass'),
]

def detect_device_type(ssh_client):
    """Try to detect device OS type"""
    try:
        stdin, stdout, stderr = ssh_client.exec_command('uname -s', timeout=3)
        uname = stdout.read().decode().strip().lower()
        if 'linux' in uname:
            return 'linux'
    except:
        pass
    
    try:
        stdin, stdout, stderr = ssh_client.exec_command('show version', timeout=3)
        output = stdout.read().decode().lower()
        if 'cisco' in output and 'ios xe' in output:
            return 'iosxe'
        elif 'cisco' in output and 'nx-os' in output:
            return 'nxos'
        elif 'arista' in output:
            return 'eos'
    except:
        pass
    
    return 'linux'

def try_ssh_connection(ip, username, password):
    """Try to connect via SSH with given credentials"""
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    
    try:
        client.connect(
            str(ip),
            username=username,
            password=password,
            timeout=TIMEOUT,
            banner_timeout=30,
            auth_timeout=TIMEOUT,
            look_for_keys=False,
            allow_agent=False
        )
        
        devtype = detect_device_type(client)
        client.close()
        
        return {
            'ip': str(ip),
            'username': username,
            'password': password,
            'devtype': devtype,
            'success': True
        }
    except Exception as e:
        return {'ip': str(ip), 'success': False, 'error': str(e)}

def scan_ip(ip):
    """Try all credentials for a single IP"""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(1)
    result = sock.connect_ex((str(ip), 22))
    sock.close()
    
    if result != 0:
        return None
    
    for username, password in CREDENTIALS:
        result = try_ssh_connection(ip, username, password)
        if result['success']:
            print(f"✓ {ip} - {username} - {result['devtype']}")
            return result
    
    print(f"✗ {ip} - SSH open but no valid credentials")
    return None

def main():
    if len(sys.argv) < 2:
        print("Usage: ./discover_devices.py <network_cidr>")
        print("Example: ./discover_devices.py 10.121.19.0/24")
        sys.exit(1)
    
    network = ipaddress.ip_network(sys.argv[1], strict=False)
    print(f"Scanning {network} ({network.num_addresses} addresses)...")
    print(f"Trying {len(CREDENTIALS)} credential pairs...")
    print()
    
    discovered = []
    
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(scan_ip, ip): ip for ip in network.hosts()}
        
        for future in as_completed(futures):
            result = future.result()
            if result:
                discovered.append(result)
    
    print()
    print(f"Found {len(discovered)} accessible devices")
    
    if not discovered:
        print("No devices found. Exiting.")
        return
    
    with open(INVENTORY_FILE, 'r') as f:
        inventory = yaml.safe_load(f)
    
    existing_ips = set()
    for host in inventory['sources'][0]['hosts']:
        if '@' in host['url']:
            ip = host['url'].split('@')[1].split()[0]
            existing_ips.add(ip)
    
    new_hosts = []
    for device in discovered:
        if device['ip'] not in existing_ips:
            url = f"ssh://{device['username']}:{device['password']}@{device['ip']}"
            if device['devtype'] != 'linux':
                url += f" devtype={device['devtype']}"
            new_hosts.append({'url': url})
    
    if new_hosts:
        inventory['sources'][0]['hosts'].extend(new_hosts)
        
        with open(INVENTORY_FILE, 'w') as f:
            yaml.dump(inventory, f, default_flow_style=False, sort_keys=False)
        
        print(f"\n✓ Added {len(new_hosts)} new devices to {INVENTORY_FILE}")
        print("Restart SuzieQ poller to start collecting data:")
        print("  docker-compose restart suzieq-poller")
    else:
        print("\nAll discovered devices already in inventory")

if __name__ == '__main__':
    main()
