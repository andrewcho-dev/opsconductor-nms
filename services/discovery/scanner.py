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
    
    def check_snmp(self, ip: str, community: str = 'public') -> Tuple[bool, Optional[str], Optional[str]]:
        try:
            result = subprocess.run(
                ['snmpget', '-v2c', '-c', community, '-t', '2', '-r', '1',
                 str(ip), 'SNMPv2-MIB::sysDescr.0', 'SNMPv2-MIB::sysObjectID.0'],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result.returncode == 0:
                output = result.stdout
                sys_descr = None
                sys_oid = None
                
                for line in output.split('\n'):
                    if 'sysDescr' in line:
                        sys_descr = line.split('STRING:')[-1].strip() if 'STRING:' in line else None
                    elif 'sysObjectID' in line:
                        sys_oid = line.split('OID:')[-1].strip() if 'OID:' in line else None
                
                return True, sys_descr, sys_oid
            
            return False, None, None
        except (subprocess.TimeoutExpired, Exception) as e:
            logger.debug(f"SNMP check failed for {ip}: {e}")
            return False, None, None
    
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
        
        snmp_ok, sys_descr, sys_oid = self.check_snmp(str(ip))
        result['snmp_reachable'] = snmp_ok
        if snmp_ok:
            result['snmp_version'] = 'v2c'
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
        else:
            result['discovery_status'] = 'unreachable'
        
        logger.info(f"{ip} - Status: {result['discovery_status']} (SSH:{ssh_ok}, SNMP:{snmp_ok}, HTTPS:{https_ok})")
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
