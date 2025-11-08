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
POLL_NETWORKS_ENV = os.getenv('POLL_NETWORKS', '')
SKIP_NETWORKS_ENV = os.getenv('SKIP_NETWORKS', '')

import ipaddress

def parse_network_list(network_str):
    networks = []
    if network_str:
        for net in network_str.split(','):
            net = net.strip()
            if net:
                try:
                    networks.append(ipaddress.ip_network(net, strict=False))
                except ValueError:
                    print(f"Warning: Invalid network {net}", flush=True)
    return networks

def get_db():
    return psycopg2.connect(host=DB_HOST, database=DB_NAME, user=DB_USER, password=DB_PASS)

def get_polling_config_from_db():
    try:
        conn = get_db()
        with conn.cursor() as cur:
            cur.execute("""
                SELECT key, value FROM polling_config 
                WHERE key IN ('poll_networks', 'skip_networks')
            """)
            config = {}
            for row in cur.fetchall():
                config[row[0]] = row[1]
            conn.close()
            return config
    except Exception as e:
        print(f"Warning: Failed to get polling config from database: {e}", flush=True)
        return {}

def get_networks_for_polling():
    config = get_polling_config_from_db()
    poll_networks = config.get('poll_networks', POLL_NETWORKS_ENV)
    skip_networks = config.get('skip_networks', SKIP_NETWORKS_ENV)
    
    return parse_network_list(poll_networks), parse_network_list(skip_networks)

POLL_NETWORKS_LIST = []
SKIP_NETWORKS_LIST = []

def should_poll_device(ip_str, poll_networks_list=None, skip_networks_list=None):
    try:
        ip = ipaddress.ip_address(ip_str)
        if skip_networks_list is None:
            skip_networks_list = SKIP_NETWORKS_LIST
        if poll_networks_list is None:
            poll_networks_list = POLL_NETWORKS_LIST
        
        if skip_networks_list:
            for net in skip_networks_list:
                if ip in net:
                    return False
        if poll_networks_list:
            for net in poll_networks_list:
                if ip in net:
                    return True
            return False
        return True
    except ValueError:
        return False

def get_devices_from_db():
    try:
        conn = get_db()
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            cur.execute("""
                SELECT 
                    d.name,
                    d.mgmt_ip,
                    d.vendor,
                    c1.snmp_community,
                    c2.ssh_username,
                    c2.ssh_password
                FROM devices d
                LEFT JOIN credentials c1 ON d.snmp_credential_id = c1.id AND c1.type = 'snmp_v2c'
                LEFT JOIN credentials c2 ON d.ssh_credential_id = c2.id AND c2.type = 'ssh'
                WHERE d.polling_enabled = TRUE 
                  AND d.snmp_polling_enabled = TRUE
                  AND d.mgmt_ip IS NOT NULL
            """)
            devices = []
            for row in cur.fetchall():
                ip_str = str(row['mgmt_ip'])
                if not should_poll_device(ip_str):
                    continue
                
                device = {
                    'hostname': row['name'],
                    'ip': ip_str,
                    'community': row['snmp_community'] or 'public',
                    'vendor': row['vendor'] or 'Unknown',
                }
                
                if row['ssh_username']:
                    device['ssh_user'] = row['ssh_username']
                if row['ssh_password']:
                    device['ssh_pass'] = row['ssh_password']
                
                devices.append(device)
            
            conn.close()
            return devices
    except Exception as e:
        print(f"ERROR: Failed to get devices from database: {e}", flush=True)
        return []

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

def snmp_lldp_neighbors(ip, community, port_map):
    try:
        lldp_local_ports_out = snmpwalk(ip, community, '1.3.6.1.2.1.99.1.1.1.1')
        
        if not lldp_local_ports_out or not lldp_local_ports_out.strip():
            return None
        
        lldp_local_ports = {}
        for line in lldp_local_ports_out.split('\n'):
            match = re.search(r'1\.3\.6\.1\.2\.1\.99\.1\.1\.1\.1\.(\d+)\s*=\s*(?:STRING|Hex-STRING):\s*"?([^"]*)"?', line)
            if match:
                index = match.group(1)
                port = match.group(2).strip()
                if port:
                    lldp_local_ports[index] = port
        
        if not lldp_local_ports:
            return None
        
        remote_chassis_out = snmpwalk(ip, community, '1.3.6.1.2.1.99.1.2.1.4')
        remote_ports_out = snmpwalk(ip, community, '1.3.6.1.2.1.99.1.2.1.7')
        remote_systems_out = snmpwalk(ip, community, '1.3.6.1.2.1.99.1.2.1.3')
        
        if not remote_chassis_out or not remote_ports_out:
            return None
        
        chassis_map = {}
        for line in remote_chassis_out.split('\n'):
            match = re.search(r'1\.3\.6\.1\.2\.1\.99\.1\.2\.1\.4\.(\d+)\s*=\s*(?:STRING|Hex-STRING):\s*"?([^"]*)"?', line)
            if match:
                index = match.group(1)
                chassis = match.group(2).strip()
                if chassis:
                    chassis_map[index] = chassis
        
        port_map_remote = {}
        for line in remote_ports_out.split('\n'):
            match = re.search(r'1\.3\.6\.1\.2\.1\.99\.1\.2\.1\.7\.(\d+)\s*=\s*(?:STRING|Hex-STRING):\s*"?([^"]*)"?', line)
            if match:
                index = match.group(1)
                port = match.group(2).strip()
                if port:
                    port_map_remote[index] = port
        
        system_map = {}
        for line in remote_systems_out.split('\n'):
            match = re.search(r'1\.3\.6\.1\.2\.1\.99\.1\.2\.1\.3\.(\d+)\s*=\s*(?:STRING|Hex-STRING):\s*"?([^"]*)"?', line)
            if match:
                index = match.group(1)
                system = match.group(2).strip()
                if system:
                    system_map[index] = system
        
        neighbors = []
        for index in lldp_local_ports:
            if index in chassis_map and index in port_map_remote:
                neighbors.append({
                    'local_if': lldp_local_ports[index],
                    'chassis_id': chassis_map[index],
                    'port_id': port_map_remote[index],
                    'system_name': system_map.get(index, ''),
                    'port_desc': port_map_remote.get(index, ''),
                    'system_desc': '',
                    'mgmt_addr': '',
                    'source': 'snmp_lldp'
                })
        
        return neighbors if neighbors else None
    except Exception as e:
        print(f"  SNMP LLDP Error: {e}", flush=True)
        return None

def ssh_lldp_neighbors(ip, username, password, timeout=15):
    try:
        ssh_cmd = f'ssh -o StrictHostKeyChecking=no -o HostKeyAlgorithms=+ssh-rsa -o PubkeyAcceptedKeyTypes=+ssh-rsa -o ConnectTimeout=5 {username}@{ip}'
        child = pexpect.spawn(ssh_cmd, timeout=timeout)
        
        try:
            i = child.expect(['Press any key', 'Username:', 'password:', '# ', pexpect.TIMEOUT, pexpect.EOF], timeout=5)
            
            if i == 0:
                child.sendline('')
                i = child.expect(['Username:', 'password:', '# ', pexpect.TIMEOUT, pexpect.EOF], timeout=3)
            
            if i in [0, 1]:
                child.sendline(username)
                i = child.expect(['password:', '# ', pexpect.TIMEOUT, pexpect.EOF], timeout=3)
            
            if i in [0, 1, 2]:
                child.sendline(password)
                i = child.expect(['# ', pexpect.TIMEOUT, pexpect.EOF], timeout=3)
            
            if i != 0:
                child.close()
                return None
            
            child.sendline('terminal length 0')
            child.expect('# ', timeout=5)
            
            child.sendline('show lldp neighbors')
            child.expect('# ', timeout=10)
            output = child.before.decode('utf-8', errors='ignore')
            
            child.sendline('exit')
            child.close()
            
            return output
        except Exception as ex:
            print(f"  SSH interaction error: {ex}", flush=True)
            try:
                child.close()
            except:
                pass
            return None
    except Exception as e:
        print(f"  SSH Error: {e}", flush=True)
        return None

def parse_lldp_table_format(output, local_device, source='ssh_lldp'):
    neighbors = []
    lines = output.split('\n')
    
    header_found = False
    for line in lines:
        line = line.strip()
        if not line:
            continue
        
        if 'Port' in line and 'Device ID' in line and '|' in line:
            header_found = True
            continue
        
        if not header_found or line.startswith('---') or line.startswith('MCL-'):
            continue
        
        if '|' in line:
            parts = [p.strip() for p in line.split('|')]
            if len(parts) >= 3:
                local_if = parts[0]
                chassis_id = parts[1]
                port_id = parts[2]
                system_name = parts[3]
                
                if local_if and chassis_id:
                    neighbors.append({
                        'local_device': local_device,
                        'local_if': local_if,
                        'chassis_id': chassis_id,
                        'port_id': port_id,
                        'system_name': system_name,
                        'port_desc': '',
                        'system_desc': '',
                        'mgmt_addr': '',
                        'source': source
                    })
    
    return neighbors

def parse_lldp_neighbors(output, local_device, source='ssh_lldp'):
    neighbors = []
    
    if not output:
        return neighbors
    
    if '|' in output and 'Device ID' in output:
        return parse_lldp_table_format(output, local_device, source)
    
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
                'mgmt_addr': '',
                'source': source
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
        
        print(f"  Attempting LLDP collection (priority: SNMP -> SSH)...", flush=True)
        
        lldp_neighbors = snmp_lldp_neighbors(device['ip'], device['community'], port_map)
        if lldp_neighbors:
            print(f"  Found {len(lldp_neighbors)} LLDP neighbors via SNMP", flush=True)
        else:
            print(f"  No LLDP data via SNMP, trying SSH...", flush=True)
            if 'ssh_user' in device and 'ssh_pass' in device:
                lldp_output = ssh_lldp_neighbors(device['ip'], device['ssh_user'], device['ssh_pass'])
                if lldp_output:
                    lldp_neighbors = parse_lldp_neighbors(lldp_output, device['hostname'], source='ssh_lldp')
                    print(f"  Found {len(lldp_neighbors)} LLDP neighbors via SSH", flush=True)
            else:
                print(f"  SSH credentials not available for LLDP collection", flush=True)
        
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
                            'source': neighbor.get('source', 'ssh_lldp')
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
    print(f"Reading polling configuration from database", flush=True)
    
    while True:
        global POLL_NETWORKS_LIST, SKIP_NETWORKS_LIST
        
        POLL_NETWORKS_LIST, SKIP_NETWORKS_LIST = get_networks_for_polling()
        
        if POLL_NETWORKS_LIST:
            poll_networks_str = ','.join(str(net) for net in POLL_NETWORKS_LIST)
            print(f"[{datetime.now()}] POLL_NETWORKS: {poll_networks_str}", flush=True)
        if SKIP_NETWORKS_LIST:
            skip_networks_str = ','.join(str(net) for net in SKIP_NETWORKS_LIST)
            print(f"[{datetime.now()}] SKIP_NETWORKS: {skip_networks_str}", flush=True)
        
        devices = get_devices_from_db()
        print(f"[{datetime.now()}] Found {len(devices)} devices to poll", flush=True)
        
        for device in devices:
            poll_device(device)
        
        print(f"[{datetime.now()}] Sleeping {POLL_INTERVAL}s...", flush=True)
        time.sleep(POLL_INTERVAL)

if __name__ == '__main__':
    main()
