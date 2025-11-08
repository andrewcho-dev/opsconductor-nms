#!/usr/bin/env python3
import os
import sys
import asyncio
import logging
import ipaddress
import subprocess
import time
from datetime import datetime
from typing import Dict, List, Optional, Tuple
import psycopg2
from psycopg2.extras import Json
import socket

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

DB_HOST = os.getenv('DB_HOST', 'localhost')
DB_NAME = os.getenv('DB_NAME', 'opsconductor')
DB_USER = os.getenv('DB_USER', 'oc')
DB_PASS = os.getenv('DB_PASS', 'oc')
SCAN_INTERVAL = int(os.getenv('SCAN_INTERVAL', '300'))

class NetworkScanner:
    def __init__(self, db_conn):
        self.conn = db_conn
        self.snmp_credentials = []
        self.load_credentials()
    
    def load_credentials(self):
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                SELECT type, snmp_community, snmp_username, snmp_auth_protocol, snmp_auth_password,
                       snmp_priv_protocol, snmp_priv_password
                FROM credentials
                WHERE enabled = TRUE
                ORDER BY priority ASC
            """)
            rows = cursor.fetchall()
            cursor.close()
            
            for row in rows:
                cred_type, community, username, auth_proto, auth_pass, priv_proto, priv_pass = row
                if community:
                    self.snmp_credentials.append({
                        'type': 'v2c',
                        'community': community
                    })
                if username:
                    self.snmp_credentials.append({
                        'type': 'v3',
                        'username': username,
                        'auth_proto': auth_proto,
                        'auth_pass': auth_pass,
                        'priv_proto': priv_proto,
                        'priv_pass': priv_pass
                    })
            
            if self.snmp_credentials:
                logger.info(f"Loaded {len(self.snmp_credentials)} SNMP credential(s)")
            else:
                logger.warning("No SNMP credentials found in database, using defaults")
                self.snmp_credentials = [
                    {'type': 'v2c', 'community': 'public'},
                    {'type': 'v3', 'username': 'public'},
                    {'type': 'v3', 'username': 'snmpuser'},
                    {'type': 'v3', 'username': 'monitor'}
                ]
        except Exception as e:
            logger.error(f"Error loading credentials: {e}")
            self.snmp_credentials = [
                {'type': 'v2c', 'community': 'public'},
                {'type': 'v3', 'username': 'public'},
                {'type': 'v3', 'username': 'snmpuser'},
                {'type': 'v3', 'username': 'monitor'}
            ]
        
    def ping_host(self, ip: str, timeout: int = 2) -> Tuple[bool, Optional[float]]:
        try:
            start = time.time()
            result = subprocess.run(
                ['ping', '-c', '1', '-W', str(timeout), str(ip)],
                capture_output=True,
                text=True,
                timeout=timeout + 1
            )
            rtt = (time.time() - start) * 1000
            return result.returncode == 0, rtt if result.returncode == 0 else None
        except (subprocess.TimeoutExpired, Exception) as e:
            logger.debug(f"Ping failed for {ip}: {e}")
            return False, None
    
    def check_tcp_port(self, ip: str, port: int, timeout: int = 2) -> Tuple[bool, Optional[str]]:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            result = sock.connect_ex((str(ip), port))
            
            if result == 0:
                try:
                    banner = sock.recv(1024).decode('utf-8', errors='ignore').strip()
                except:
                    banner = None
                sock.close()
                return True, banner
            
            sock.close()
            return False, None
        except Exception as e:
            logger.debug(f"TCP port check failed for {ip}:{port}: {e}")
            return False, None
    
    def check_ssh(self, ip: str, port: int = 22) -> Tuple[bool, Optional[str]]:
        reachable, banner = self.check_tcp_port(ip, port, timeout=3)
        return reachable, banner
    
    def check_https(self, ip: str, port: int = 443) -> bool:
        reachable, _ = self.check_tcp_port(ip, port, timeout=2)
        return reachable
    
    def check_snmp_v2c(self, ip: str, community: str = 'public') -> Tuple[bool, Optional[str], Optional[str]]:
        try:
            result = subprocess.run(
                ['snmpget', '-v2c', '-c', community, '-t', '2', '-r', '1',
                 str(ip), '.1.3.6.1.2.1.1.1.0', '.1.3.6.1.2.1.1.2.0'],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result.returncode == 0:
                output = result.stdout
                sys_descr = None
                sys_oid = None
                
                lines = output.split('\n')
                if len(lines) >= 1 and 'STRING:' in lines[0]:
                    sys_descr = lines[0].split('STRING:')[-1].strip()
                if len(lines) >= 2 and 'OID:' in lines[1]:
                    sys_oid = lines[1].split('OID:')[-1].strip()
                
                return True, sys_descr, sys_oid
            
            return False, None, None
        except (subprocess.TimeoutExpired, Exception) as e:
            logger.debug(f"SNMPv2c check failed for {ip}: {e}")
            return False, None, None
    
    def check_snmp_v3(self, ip: str, username: str = 'public', auth_proto: str = None, 
                      auth_pass: str = None, priv_proto: str = None, priv_pass: str = None) -> Tuple[bool, Optional[str], Optional[str]]:
        try:
            cmd = ['snmpget', '-v3', '-l']
            
            if auth_proto and auth_pass and priv_proto and priv_pass:
                cmd.extend(['authPriv', '-u', username, '-a', auth_proto, '-A', auth_pass, 
                           '-x', priv_proto, '-X', priv_pass])
            elif auth_proto and auth_pass:
                cmd.extend(['authNoPriv', '-u', username, '-a', auth_proto, '-A', auth_pass])
            else:
                cmd.extend(['noAuthNoPriv', '-u', username])
            
            cmd.extend(['-t', '2', '-r', '1', str(ip), '.1.3.6.1.2.1.1.1.0', '.1.3.6.1.2.1.1.2.0'])
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
            
            if result.returncode == 0:
                output = result.stdout
                sys_descr = None
                sys_oid = None
                
                lines = output.split('\n')
                if len(lines) >= 1 and 'STRING:' in lines[0]:
                    sys_descr = lines[0].split('STRING:')[-1].strip()
                if len(lines) >= 2 and 'OID:' in lines[1]:
                    sys_oid = lines[1].split('OID:')[-1].strip()
                
                return True, sys_descr, sys_oid
            
            return False, None, None
        except (subprocess.TimeoutExpired, Exception) as e:
            logger.debug(f"SNMPv3 check failed for {ip} with user {username}: {e}")
            return False, None, None
    
    def check_snmp(self, ip: str, community: str = None) -> Tuple[bool, Optional[str], Optional[str], Optional[str]]:
        for cred in self.snmp_credentials:
            if cred['type'] == 'v2c':
                snmp_ok, sys_descr, sys_oid = self.check_snmp_v2c(str(ip), cred['community'])
                if snmp_ok:
                    logger.debug(f"{ip} - SNMPv2c successful with community: {cred['community']}")
                    return True, sys_descr, sys_oid, 'v2c'
            elif cred['type'] == 'v3':
                snmp_ok, sys_descr, sys_oid = self.check_snmp_v3(
                    str(ip), 
                    cred['username'],
                    cred.get('auth_proto'),
                    cred.get('auth_pass'),
                    cred.get('priv_proto'),
                    cred.get('priv_pass')
                )
                if snmp_ok:
                    logger.debug(f"{ip} - SNMPv3 successful with username: {cred['username']}")
                    return True, sys_descr, sys_oid, 'v3'
        
        return False, None, None, None
    
    def probe_device(self, ip: str, credential_ids: List[int] = None) -> Dict:
        logger.info(f"Probing {ip}...")
        
        result = {
            'ip': str(ip),
            'ping_reachable': False,
            'ping_rtt_ms': None,
            'ssh_reachable': False,
            'ssh_port': 22,
            'ssh_banner': None,
            'snmp_reachable': False,
            'snmp_version': None,
            'snmp_sys_descr': None,
            'snmp_sys_object_id': None,
            'https_reachable': False,
            'https_port': 443,
            'discovery_status': 'unreachable',
            'last_probed': datetime.now()
        }
        
        ping_ok, rtt = self.ping_host(str(ip))
        result['ping_reachable'] = ping_ok
        result['ping_rtt_ms'] = rtt
        
        if not ping_ok:
            logger.debug(f"{ip} - Not reachable via ping")
            return result
        
        ssh_ok, ssh_banner = self.check_ssh(str(ip))
        result['ssh_reachable'] = ssh_ok
        result['ssh_banner'] = ssh_banner
        
        https_ok = self.check_https(str(ip))
        result['https_reachable'] = https_ok
        
        snmp_ok, sys_descr, sys_oid, snmp_version = self.check_snmp(str(ip))
        result['snmp_reachable'] = snmp_ok
        if snmp_ok:
            result['snmp_version'] = snmp_version
            result['snmp_sys_descr'] = sys_descr
            result['snmp_sys_object_id'] = sys_oid
            
            if sys_descr:
                sys_descr_lower = sys_descr.lower()
                if 'cisco' in sys_descr_lower:
                    result['vendor'] = 'Cisco'
                elif 'juniper' in sys_descr_lower:
                    result['vendor'] = 'Juniper'
                elif 'arista' in sys_descr_lower:
                    result['vendor'] = 'Arista'
                elif 'axis' in sys_descr_lower:
                    result['vendor'] = 'Axis'
                elif 'linux' in sys_descr_lower:
                    result['vendor'] = 'Linux'
        
        
        if ssh_ok or snmp_ok or https_ok:
            result['discovery_status'] = 'reachable'
        elif ping_ok:
            result['discovery_status'] = 'online'
        else:
            result['discovery_status'] = 'unreachable'
        
        logger.info(f"{ip} - Status: {result['discovery_status']} (Ping:{ping_ok}, SSH:{ssh_ok}, SNMP:{snmp_ok}, HTTPS:{https_ok})")
        return result
    
    def scan_network(self, network_cidr: str, scan_id: int):
        logger.info(f"Starting network scan for {network_cidr} (scan_id={scan_id})")
        
        try:
            network = ipaddress.ip_network(network_cidr, strict=False)
        except ValueError as e:
            logger.error(f"Invalid network CIDR {network_cidr}: {e}")
            return
        
        cursor = self.conn.cursor()
        cursor.execute(
            "UPDATE discovery_scans SET status = 'running', started_at = NOW() WHERE id = %s",
            (scan_id,)
        )
        self.conn.commit()
        
        devices_found = 0
        devices_reachable = 0
        
        for ip in network.hosts():
            try:
                device_info = self.probe_device(ip)
                
                cursor.execute("""
                    INSERT INTO discovered_devices (
                        ip, vendor, ping_reachable, ping_rtt_ms, ping_last_checked,
                        ssh_reachable, ssh_port, ssh_banner, ssh_last_checked,
                        snmp_reachable, snmp_version, snmp_sys_descr, snmp_sys_object_id, snmp_last_checked,
                        https_reachable, https_port, https_last_checked,
                        discovery_status, discovery_scan_id, last_probed, discovered_at
                    ) VALUES (
                        %s, %s, %s, %s, NOW(),
                        %s, %s, %s, NOW(),
                        %s, %s, %s, %s, NOW(),
                        %s, %s, NOW(),
                        %s, %s, NOW(), NOW()
                    )
                    ON CONFLICT (ip) DO UPDATE SET
                        vendor = EXCLUDED.vendor,
                        ping_reachable = EXCLUDED.ping_reachable,
                        ping_rtt_ms = EXCLUDED.ping_rtt_ms,
                        ping_last_checked = NOW(),
                        ssh_reachable = EXCLUDED.ssh_reachable,
                        ssh_banner = EXCLUDED.ssh_banner,
                        ssh_last_checked = NOW(),
                        snmp_reachable = EXCLUDED.snmp_reachable,
                        snmp_version = EXCLUDED.snmp_version,
                        snmp_sys_descr = EXCLUDED.snmp_sys_descr,
                        snmp_sys_object_id = EXCLUDED.snmp_sys_object_id,
                        snmp_last_checked = NOW(),
                        https_reachable = EXCLUDED.https_reachable,
                        https_last_checked = NOW(),
                        discovery_status = EXCLUDED.discovery_status,
                        last_probed = NOW()
                """, (
                    device_info['ip'],
                    device_info.get('vendor'),
                    device_info['ping_reachable'],
                    device_info['ping_rtt_ms'],
                    device_info['ssh_reachable'],
                    device_info['ssh_port'],
                    device_info['ssh_banner'],
                    device_info['snmp_reachable'],
                    device_info['snmp_version'],
                    device_info['snmp_sys_descr'],
                    device_info['snmp_sys_object_id'],
                    device_info['https_reachable'],
                    device_info['https_port'],
                    device_info['discovery_status'],
                    scan_id
                ))
                
                
                if device_info['discovery_status'] in ['online', 'reachable']:
                    devices_found += 1
                if device_info['discovery_status'] == 'reachable':
                    devices_reachable += 1
                
                self.conn.commit()
                
            except Exception as e:
                logger.error(f"Error probing {ip}: {e}")
                self.conn.rollback()
                continue
        
        cursor.execute("""
            UPDATE discovery_scans 
            SET status = 'completed', 
                completed_at = NOW(), 
                devices_found = %s,
                devices_reachable = %s
            WHERE id = %s
        """, (devices_found, devices_reachable, scan_id))
        self.conn.commit()
        cursor.close()
        
        logger.info(f"Scan {scan_id} completed: {devices_found} found, {devices_reachable} reachable")


    def process_rescan_requests(self):
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT ip FROM discovered_devices 
            WHERE rescan_requested = TRUE 
            LIMIT 10
        """)
        
        rescan_ips = cursor.fetchall()
        cursor.close()
        
        if not rescan_ips:
            return 0
        
        logger.info(f"Processing {len(rescan_ips)} rescan requests")
        rescanned_count = 0
        
        for (ip,) in rescan_ips:
            try:
                import ipaddress
                device_info = self.probe_device(ipaddress.ip_address(ip))
                
                cursor = self.conn.cursor()
                cursor.execute("""
                    UPDATE discovered_devices SET
                        vendor = %s,
                        ping_reachable = %s,
                        ping_rtt_ms = %s,
                        ping_last_checked = NOW(),
                        ssh_reachable = %s,
                        ssh_banner = %s,
                        ssh_last_checked = NOW(),
                        snmp_reachable = %s,
                        snmp_version = %s,
                        snmp_sys_descr = %s,
                        snmp_sys_object_id = %s,
                        snmp_last_checked = NOW(),
                        https_reachable = %s,
                        https_last_checked = NOW(),
                        discovery_status = %s,
                        last_probed = NOW(),
                        rescan_requested = FALSE
                    WHERE ip = %s
                """, (
                    device_info.get('vendor'),
                    device_info['ping_reachable'],
                    device_info['ping_rtt_ms'],
                    device_info['ssh_reachable'],
                    device_info['ssh_banner'],
                    device_info['snmp_reachable'],
                    device_info['snmp_version'],
                    device_info['snmp_sys_descr'],
                    device_info['snmp_sys_object_id'],
                    device_info['https_reachable'],
                    device_info['discovery_status'],
                    str(ip)
                ))
                
                self.conn.commit()
                cursor.close()
                rescanned_count += 1
                logger.info(f"Rescanned {ip}: {device_info['discovery_status']}")
                
            except Exception as e:
                logger.error(f"Error rescanning {ip}: {e}")
                cursor = self.conn.cursor()
                cursor.execute("UPDATE discovered_devices SET rescan_requested = FALSE WHERE ip = %s", (str(ip),))
                self.conn.commit()
                cursor.close()
                continue
        
        return rescanned_count

def get_db():
    return psycopg2.connect(
        host=DB_HOST,
        database=DB_NAME,
        user=DB_USER,
        password=DB_PASS
    )

def main():
    logger.info("Discovery scanner service starting...")
    
    while True:
        try:
            conn = get_db()
            scanner = NetworkScanner(conn)
            
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, network_cidr 
                FROM discovery_scans 
                WHERE status = 'pending' 
                ORDER BY created_at ASC 
                LIMIT 1
            """)
            
            scan = cursor.fetchone()
            cursor.close()
            
            # Check for rescan requests first
            rescan_count = scanner.process_rescan_requests()
            if rescan_count > 0:
                logger.info(f"Processed {rescan_count} rescan requests")
            
            if scan:
                scan_id, network_cidr = scan
                logger.info(f"Found pending scan: {scan_id} for {network_cidr}")
                scanner.scan_network(network_cidr, scan_id)
            else:
                logger.debug("No pending scans, sleeping...")
                time.sleep(SCAN_INTERVAL)
            
            conn.close()
            
        except Exception as e:
            logger.error(f"Error in main loop: {e}", exc_info=True)
            time.sleep(10)

if __name__ == '__main__':
    main()
