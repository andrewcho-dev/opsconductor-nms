#!/usr/bin/env python3
import subprocess
import psycopg2
import psycopg2.extras
import re
import time
import os
from datetime import datetime
import pexpect

DB_HOST = os.getenv('DB_HOST', 'localhost')
DB_NAME = os.getenv('DB_NAME', 'opsconductor')
DB_USER = os.getenv('DB_USER', 'oc')
DB_PASS = os.getenv('DB_PASS', 'oc')
POLL_INTERVAL = int(os.getenv('POLL_INTERVAL', '60'))

DEVICES = [
    {
        'hostname': 'axis-switch', 
        'ip': '10.121.19.21', 
        'community': 'public', 
        'vendor': 'Axis',
        'ssh_user': 'root',
        'ssh_pass': 'Metrolink222'
    },
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

def ssh_lldp_neighbors(ip, username, password, timeout=30):
    try:
        ssh_cmd = f'ssh -o StrictHostKeyChecking=no -o HostKeyAlgorithms=+ssh-rsa -o PubkeyAcceptedKeyTypes=+ssh-rsa {username}@{ip}'
        child = pexpect.spawn(ssh_cmd, timeout=timeout)
        
        i = child.expect(['password:', '# ', pexpect.TIMEOUT, pexpect.EOF])
        
        if i == 0:
            child.sendline(password)
            child.expect('# ')
        elif i != 1:
            return None
        
        child.sendline('terminal length 0')
        child.expect('# ')
        
        child.sendline('show lldp neighbors')
        child.expect('# ')
        output = child.before.decode('utf-8', errors='ignore')
        
        child.sendline('exit')
        child.close()
        
        return output
    except Exception as e:
        print(f"  SSH Error: {e}", flush=True)
        return None

def parse_lldp_neighbors(output, local_device):
    neighbors = []
    
    if not output:
        return neighbors
    
    lines = output.split('\n')
    i = 0
    
    while i < len(lines):
        line = lines[i].strip()
        
        if line.startswith('Local Interface'):
            local_if_match = re.search(r'Local Interface\s*:\s*(.+)', line)
            if not local_if_match:
                i += 1
                continue
            
            local_if = local_if_match.group(1).strip()
            
            neighbor = {
                'local_device': local_device,
                'local_if': local_if,
                'chassis_id': '',
                'port_id': '',
                'system_name': '',
                'port_desc': '',
                'system_desc': '',
                'mgmt_addr': ''
            }
            
            i += 1
            while i < len(lines) and not lines[i].strip().startswith('Local Interface'):
                line = lines[i].strip()
                
                if line.startswith('Chassis ID'):
                    match = re.search(r'Chassis ID\s*:\s*(.+)', line)
                    if match:
                        neighbor['chassis_id'] = match.group(1).strip()
                
                elif line.startswith('Port ID'):
                    match = re.search(r'Port ID\s*:\s*(.+)', line)
                    if match:
                        neighbor['port_id'] = match.group(1).strip()
                
                elif line.startswith('System Name'):
                    match = re.search(r'System Name\s*:\s*(.+)', line)
                    if match:
                        neighbor['system_name'] = match.group(1).strip()
                
                elif line.startswith('Port Description'):
                    match = re.search(r'Port Description\s*:\s*(.+)', line)
                    if match:
                        neighbor['port_desc'] = match.group(1).strip()
                
                elif line.startswith('System Description'):
                    match = re.search(r'System Description\s*:\s*(.+)', line)
                    if match:
                        neighbor['system_desc'] = match.group(1).strip()
                
                elif line.startswith('Management Address'):
                    match = re.search(r'Management Address\s*:\s*([0-9\.]+)', line)
                    if match:
                        neighbor['mgmt_addr'] = match.group(1).strip()
                
                i += 1
                
                if line.startswith('Power Over Ethernet'):
                    break
            
            if neighbor['system_name'] or neighbor['chassis_id']:
                neighbors.append(neighbor)
        else:
            i += 1
    
    return neighbors

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
        
        lldp_neighbors = []
        if 'ssh_user' in device and 'ssh_pass' in device:
            print(f"  Collecting LLDP via SSH...", flush=True)
            lldp_output = ssh_lldp_neighbors(device['ip'], device['ssh_user'], device['ssh_pass'])
            if lldp_output:
                lldp_neighbors = parse_lldp_neighbors(lldp_output, device['hostname'])
                print(f"  Found {len(lldp_neighbors)} LLDP neighbors", flush=True)
        
        conn = get_db()
        try:
            with conn.cursor() as cur:
                device_name = device['ip']
                hostname = device.get('hostname')
                
                cur.execute("""
                    INSERT INTO devices (name, mgmt_ip, vendor, last_seen)
                    VALUES (%s, %s, %s, NOW())
                    ON CONFLICT (name) DO UPDATE SET mgmt_ip = EXCLUDED.mgmt_ip, last_seen = NOW()
                """, (device_name, device['ip'], device['vendor']))
                
                if hostname:
                    cur.execute("""
                        INSERT INTO hostname_mappings (hostname, ip_address)
                        VALUES (%s, %s)
                        ON CONFLICT (hostname) DO UPDATE SET ip_address = EXCLUDED.ip_address
                    """, (hostname, device['ip']))
                
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
                
                if lldp_neighbors:
                    cur.execute("DELETE FROM facts_lldp WHERE device = %s", (device_name,))
                    for neighbor in lldp_neighbors:
                        peer_device = neighbor['system_name'] or neighbor['mgmt_addr'] or neighbor['chassis_id']
                        peer_ifname = neighbor['port_desc'] or neighbor['port_id'] or 'unknown'
                        
                        protocol_payload = {
                            'chassis_id': neighbor['chassis_id'],
                            'port_id': neighbor['port_id'],
                            'system_name': neighbor['system_name'],
                            'port_description': neighbor['port_desc'],
                            'system_description': neighbor['system_desc'],
                            'management_address': neighbor['mgmt_addr'],
                            'source': 'ssh_lldp'
                        }
                        
                        cur.execute("""
                            INSERT INTO facts_lldp (device, ifname, peer_device, peer_ifname, protocol_payload)
                            VALUES (%s, %s, %s, %s, %s::jsonb)
                        """, (device_name, neighbor['local_if'], peer_device, peer_ifname, psycopg2.extras.Json(protocol_payload)))
                
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
