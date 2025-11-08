#!/usr/bin/env python3
import subprocess
import psycopg2
import re
import time
import os
from datetime import datetime

DB_HOST = os.getenv('DB_HOST', 'localhost')
DB_NAME = os.getenv('DB_NAME', 'opsconductor')
DB_USER = os.getenv('DB_USER', 'oc')
DB_PASS = os.getenv('DB_PASS', 'oc')
POLL_INTERVAL = int(os.getenv('POLL_INTERVAL', '60'))

DEVICES = [
    {'hostname': 'axis-switch', 'ip': '10.121.19.21', 'community': 'public', 'vendor': 'Axis'},
]

def snmpwalk(ip, community, oid):
    cmd = ['snmpwalk', '-v2c', '-c', community, '-OXn', ip, oid]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    return result.stdout

def parse_arp_table(output):
    arps = []
    for line in output.split('\n'):
        match = re.search(r'1\.3\.6\.1\.2\.1\.4\.35\.1\.4\.\d+\.1\.4\.(\d+\.\d+\.\d+\.\d+)\s*=.*Hex-STRING:\s*([0-9A-F ]+)', line, re.IGNORECASE)
        if match:
            ip = match.group(1)
            mac_hex = match.group(2).replace(' ', '')
            mac = ':'.join([mac_hex[i:i+2] for i in range(0, len(mac_hex), 2)])
            arps.append({'ip': ip, 'mac': mac.lower()})
    return arps

def parse_mac_table(output, port_map):
    macs = []
    for line in output.split('\n'):
        match = re.search(r'1\.3\.6\.1\.2\.1\.17\.4\.3\.1\.2\.(\d+)\.(\d+)\.(\d+)\.(\d+)\.(\d+)\.(\d+)\s*=.*INTEGER:\s*(\d+)', line)
        if match:
            mac_parts = [match.group(i) for i in range(1, 7)]
            mac = ':'.join([f'{int(p):02x}' for p in mac_parts])
            port_num = int(match.group(7))
            interface = port_map.get(port_num, f'Port{port_num}')
            macs.append({'mac': mac, 'interface': interface, 'port': port_num})
    return macs

def get_interface_map(ip, community):
    ifname_output = snmpwalk(ip, community, '1.3.6.1.2.1.31.1.1.1.1')
    bridge_output = snmpwalk(ip, community, '1.3.6.1.2.1.17.1.4.1.2')
    
    ifindex_to_name = {}
    for line in ifname_output.split('\n'):
        match = re.search(r'1\.3\.6\.1\.2\.1\.31\.1\.1\.1\.1\.(\d+)\s*=\s*STRING:\s*(.+)', line)
        if match:
            ifindex = int(match.group(1))
            name = match.group(2).strip().strip('"')
            ifindex_to_name[ifindex] = name
    
    bridge_to_if = {}
    for line in bridge_output.split('\n'):
        match = re.search(r'1\.3\.6\.1\.2\.1\.17\.1\.4\.1\.2\.(\d+)\s*=\s*INTEGER:\s*(\d+)', line)
        if match:
            bridge_port = int(match.group(1))
            ifindex = int(match.group(2))
            bridge_to_if[bridge_port] = ifindex
    
    port_map = {}
    for bridge_port, ifindex in bridge_to_if.items():
        if ifindex in ifindex_to_name:
            port_map[bridge_port] = ifindex_to_name[ifindex]
    
    return port_map, list(ifindex_to_name.values())

def get_db():
    return psycopg2.connect(host=DB_HOST, database=DB_NAME, user=DB_USER, password=DB_PASS)

def poll_device(device):
    print(f"[{datetime.now()}] Polling {device['hostname']} ({device['ip']})...", flush=True)
    
    try:
        port_map, interfaces = get_interface_map(device['ip'], device['community'])
        print(f"  Found {len(interfaces)} interfaces", flush=True)
        
        arp_output = snmpwalk(device['ip'], device['community'], '1.3.6.1.2.1.4.35.1.4')
        arp_entries = parse_arp_table(arp_output)
        print(f"  Found {len(arp_entries)} ARP entries", flush=True)
        
        mac_output = snmpwalk(device['ip'], device['community'], '1.3.6.1.2.1.17.4.3.1.2')
        mac_entries = parse_mac_table(mac_output, port_map)
        print(f"  Found {len(mac_entries)} MAC entries", flush=True)
        
        conn = get_db()
        try:
            with conn.cursor() as cur:
                device_name = device['hostname']
                
                cur.execute("""
                    INSERT INTO devices (name, mgmt_ip, vendor, last_seen)
                    VALUES (%s, %s, %s, NOW())
                    ON CONFLICT (name) DO UPDATE SET mgmt_ip = EXCLUDED.mgmt_ip, last_seen = NOW()
                """, (device_name, device['ip'], device['vendor']))
                
                for iface in interfaces:
                    cur.execute("""
                        INSERT INTO interfaces (device, ifname, admin_up, oper_up, last_seen)
                        VALUES (%s, %s, true, true, NOW())
                        ON CONFLICT (device, ifname) DO UPDATE SET last_seen = NOW()
                    """, (device_name, iface))
                
                cur.execute("DELETE FROM facts_arp WHERE device = %s", (device_name,))
                for entry in arp_entries:
                    cur.execute("""
                        INSERT INTO facts_arp (device, ip_addr, mac_addr, vlan)
                        VALUES (%s, %s, %s, '1')
                    """, (device_name, entry['ip'], entry['mac']))
                
                cur.execute("DELETE FROM facts_mac WHERE device = %s", (device_name,))
                for entry in mac_entries:
                    cur.execute("""
                        INSERT INTO facts_mac (device, ifname, mac_addr, vlan)
                        VALUES (%s, %s, %s, '1')
                    """, (device_name, entry['interface'], entry['mac']))
                
                conn.commit()
                print(f"  Successfully updated database", flush=True)
        finally:
            conn.close()
            
    except Exception as e:
        print(f"  ERROR: {e}", flush=True)
        import traceback
        traceback.print_exc()

def main():
    print(f"SNMP Poller starting - polling every {POLL_INTERVAL} seconds", flush=True)
    while True:
        for device in DEVICES:
            poll_device(device)
        print(f"[{datetime.now()}] Sleeping {POLL_INTERVAL}s...", flush=True)
        time.sleep(POLL_INTERVAL)

if __name__ == '__main__':
    main()
