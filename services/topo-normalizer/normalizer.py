import os
import time
import logging
import json
from datetime import datetime
from typing import Dict, List, Optional
import psycopg2
from psycopg2.extras import execute_values, Json
import requests

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class TopologyNormalizer:
    def __init__(self, pg_dsn: str, suzieq_url: str = "http://localhost:8000", suzieq_api_key: str = "opsconductor-dev-key-12345"):
        self.pg_dsn = pg_dsn
        self.suzieq_url = suzieq_url
        self.suzieq_api_key = suzieq_api_key
        self.conn = None
        
    def connect_db(self):
        max_retries = 30
        for attempt in range(max_retries):
            try:
                self.conn = psycopg2.connect(self.pg_dsn)
                logger.info("Connected to database")
                return True
            except psycopg2.OperationalError as e:
                logger.info(f"Waiting for database... (attempt {attempt + 1}/{max_retries})")
                time.sleep(2)
        
        logger.error("Could not connect to database")
        return False
    
    def fetch_suzieq_data(self, endpoint: str) -> Optional[List[Dict]]:
        try:
            url = f"{self.suzieq_url}/api/v2/{endpoint}/show?access_token={self.suzieq_api_key}"
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                return response.json()
            else:
                logger.warning(f"SuzieQ API returned {response.status_code} for {endpoint}: {response.text}")
                return None
        except requests.exceptions.RequestException as e:
            logger.warning(f"Failed to fetch {endpoint} from SuzieQ: {e}")
            return None
    
    def process_lldp_facts(self):
        logger.info("Processing LLDP facts...")
        data = self.fetch_suzieq_data("lldp")
        
        if not data:
            logger.info("No LLDP data available")
            return
        
        cursor = self.conn.cursor()
        
        cursor.execute("SELECT hostname, ip_address FROM hostname_mappings")
        hostname_map = {row[0]: row[1] for row in cursor.fetchall()}
        
        values = []
        for record in data:
            hostname = record.get('hostname')
            device_name = hostname_map.get(hostname, hostname)
            values.append((
                device_name,
                record.get('ifname'),
                record.get('peerHostname'),
                record.get('peerIfname'),
                Json(record)
            ))
        
        if values:
            execute_values(
                cursor,
                """INSERT INTO facts_lldp (device, ifname, peer_device, peer_ifname, protocol_payload)
                   VALUES %s""",
                values
            )
            self.conn.commit()
            logger.info(f"Inserted {len(values)} LLDP facts")
        
        cursor.close()
    
    def ensure_lldp_peer_nodes(self):
        logger.info("Creating nodes for LLDP peer devices...")
        cursor = self.conn.cursor()
        
        cursor.execute("""
            INSERT INTO devices (name, vendor, model, os_version, role, site)
            SELECT DISTINCT peer_device, 'N/A', 'N/A', 'N/A', 'default', 'default'
            FROM facts_lldp
            WHERE peer_device NOT IN (SELECT name FROM devices)
            ON CONFLICT (name) DO NOTHING
        """)
        
        rows_inserted = cursor.rowcount
        self.conn.commit()
        logger.info(f"Created {rows_inserted} peer device nodes")
        
        cursor.close()
    
    def compute_edges_from_lldp(self):
        logger.info("Computing edges from LLDP...")
        cursor = self.conn.cursor()
        
        cursor.execute("""
            WITH latest_lldp AS (
                SELECT DISTINCT ON (device, ifname, peer_device, peer_ifname)
                    device, ifname, peer_device, peer_ifname, collected_at, protocol_payload
                FROM facts_lldp
                WHERE collected_at > NOW() - INTERVAL '1 hour'
                ORDER BY device, ifname, peer_device, peer_ifname, collected_at DESC
            )
            INSERT INTO edges (a_dev, a_if, b_dev, b_if, method, confidence, evidence, first_seen, last_seen)
            SELECT
                COALESCE(hm1.ip_address, ll.device) as a_dev,
                ll.ifname as a_if,
                COALESCE(hm2.ip_address, ll.peer_device) as b_dev,
                ll.peer_ifname as b_if,
                'lldp' as method,
                1.0 as confidence,
                jsonb_build_object(
                    'source', 'lldp',
                    'collected_at', ll.collected_at,
                    'payload', ll.protocol_payload
                ) as evidence,
                ll.collected_at as first_seen,
                ll.collected_at as last_seen
            FROM latest_lldp ll
            LEFT JOIN hostname_mappings hm1 ON ll.device = hm1.hostname
            LEFT JOIN hostname_mappings hm2 ON ll.peer_device = hm2.hostname
            ON CONFLICT (a_dev, a_if, b_dev, b_if) DO UPDATE SET last_seen = EXCLUDED.last_seen, confidence = EXCLUDED.confidence, evidence = EXCLUDED.evidence
        """)
        
        rows_inserted = cursor.rowcount
        self.conn.commit()
        logger.info(f"Created {rows_inserted} LLDP edges")
        
        cursor.close()
    
    
    def compute_edges_from_mac_correlation(self):
        """Map IP addresses to switch ports using ARP+MAC tables."""
        logger.info("Computing edges from MAC correlation...")
        cursor = self.conn.cursor()
        
        cursor.execute("""
            WITH switch_ports AS (
                SELECT DISTINCT
                    host(d.mgmt_ip) as switch_ip,
                    host(a.ip_addr) as device_ip,
                    a.mac_addr,
                    m.ifname as switch_port
                FROM facts_arp a
                JOIN facts_mac m ON a.mac_addr = m.mac_addr AND a.device = m.device
                JOIN devices d ON d.name = a.device
                WHERE a.collected_at > NOW() - INTERVAL '1 hour'
                  AND m.collected_at > NOW() - INTERVAL '1 hour'
                  AND NOT (a.ip_addr <<= '169.254.0.0/16'::inet)
                  AND d.mgmt_ip IS NOT NULL
            )
            INSERT INTO edges (a_dev, a_if, b_dev, b_if, method, confidence, evidence, first_seen, last_seen)
            SELECT DISTINCT
                sp.device_ip as a_dev,
                'arp-inferred' as a_if,
                sp.switch_ip as b_dev,
                sp.switch_port as b_if,
                'mac_arp' as method,
                0.9 as confidence,
                jsonb_build_object(
                    'source', 'switch_arp_mac',
                    'device_ip', sp.device_ip,
                    'device_mac', sp.mac_addr::text,
                    'switch_ip', sp.switch_ip,
                    'switch_port', sp.switch_port
                ) as evidence,
                NOW() as first_seen,
                NOW() as last_seen
            FROM switch_ports sp
            WHERE sp.device_ip != sp.switch_ip
            ON CONFLICT (a_dev, a_if, b_dev, b_if) DO UPDATE SET
                last_seen = EXCLUDED.last_seen,
                confidence = GREATEST(edges.confidence, EXCLUDED.confidence),
                evidence = EXCLUDED.evidence
        """)

        rows_inserted = cursor.rowcount
        self.conn.commit()
        logger.info(f"Created/updated {rows_inserted} edges from MAC correlation")
        cursor.close()
    
    def compute_edges_from_arp_correlation(self):
        """
        Infer edges by matching ARP entries to known devices.
        Devices appearing in 2+ ARP tables are treated as infrastructure.
        """
        logger.info("Computing edges from ARP correlation...")
        cursor = self.conn.cursor()
        
        cursor.execute("""
            WITH device_ips AS (
                SELECT DISTINCT ON (ip) device, ip
                FROM (
                    SELECT DISTINCT i.device, host(i.l3_addr)::inet as ip
                    FROM interfaces i
                    WHERE i.l3_addr IS NOT NULL
                    UNION
                    SELECT DISTINCT d.name as device, d.mgmt_ip as ip
                    FROM devices d
                    WHERE d.mgmt_ip IS NOT NULL
                ) sub
                ORDER BY ip, 
                    CASE WHEN device ~ '^[0-9]+\\.[0-9]+\\.[0-9]+\\.[0-9]+$' THEN 1 ELSE 0 END,
                    device
            ),
            infra_devices AS (
                SELECT DISTINCT device FROM facts_mac
                UNION
                SELECT DISTINCT device FROM facts_lldp
            )
            INSERT INTO edges (a_dev, a_if, b_dev, b_if, method, confidence, evidence, first_seen, last_seen)
            SELECT DISTINCT
                a.device as a_dev,
                COALESCE(a.ifname, 'arp-inferred') as a_if,
                d.device as b_dev,
                'arp-inferred' as b_if,
                'mac_arp' as method,
                0.6 as confidence,
                jsonb_build_object(
                    'source', 'arp_to_device',
                    'matched_ip', a.ip_addr::text,
                    'matched_mac', a.mac_addr::text
                ) as evidence,
                NOW() as first_seen,
                NOW() as last_seen
            FROM facts_arp a
            JOIN device_ips d ON a.ip_addr = d.ip
            WHERE a.device != d.device
                AND d.device IN (SELECT device FROM infra_devices)
                AND a.collected_at > NOW() - INTERVAL '1 hour'
            ON CONFLICT (a_dev, a_if, b_dev, b_if) DO UPDATE SET
                last_seen = EXCLUDED.last_seen,
                confidence = GREATEST(edges.confidence, EXCLUDED.confidence),
                evidence = EXCLUDED.evidence
        """)
        
        rows_inserted = cursor.rowcount
        self.conn.commit()
        logger.info(f"Created/updated {rows_inserted} edges from ARP correlation")
        cursor.close()

    def update_devices(self):
        logger.info("Updating devices...")
        data = self.fetch_suzieq_data("device")
        
        if not data:
            logger.info("No device data available")
            return
        
        cursor = self.conn.cursor()
        
        hostname_to_ip = {}
        values = []
        for record in data:
            ip_addr = record.get('address')
            hostname = record.get('hostname')
            if ip_addr:
                hostname_to_ip[hostname] = ip_addr
                values.append((
                    ip_addr,
                    record.get('vendor'),
                    record.get('model'),
                    record.get('version'),
                    record.get('namespace'),
                    record.get('namespace')
                ))
        
        if values:
            execute_values(
                cursor,
                """INSERT INTO devices (name, vendor, model, os_version, role, site)
                   VALUES %s
                   ON CONFLICT (name) DO UPDATE SET
                       vendor = EXCLUDED.vendor,
                       model = EXCLUDED.model,
                       os_version = EXCLUDED.os_version,
                       last_seen = NOW()""",
                values
            )
            
            for hostname, ip in hostname_to_ip.items():
                cursor.execute("""
                    INSERT INTO hostname_mappings (hostname, ip_address)
                    VALUES (%s, %s)
                    ON CONFLICT (hostname) DO UPDATE SET ip_address = EXCLUDED.ip_address
                """, (hostname, ip))
            self.conn.commit()
            logger.info(f"Updated {len(values)} devices")
        
        cursor.close()
    
    def update_interfaces(self):
        logger.info("Updating interfaces...")
        data = self.fetch_suzieq_data("interface")
        
        if not data:
            logger.info("No interface data available")
            return
        
        cursor = self.conn.cursor()
        
        cursor.execute("SELECT hostname, ip_address FROM hostname_mappings")
        hostname_map = {row[0]: row[1] for row in cursor.fetchall()}
        
        values = []
        for record in data:
            hostname = record.get('hostname')
            device_name = hostname_map.get(hostname, hostname)
            values.append((
                device_name,
                record.get('ifname'),
                record.get('adminState') == 'up',
                record.get('state') == 'up',
                record.get('speed'),
                record.get('vlan'),
                record.get('ipAddressList', [None])[0] if record.get('ipAddressList') else None,
                record.get('macaddr')
            ))
        
        if values:
            execute_values(
                cursor,
                """INSERT INTO interfaces (device, ifname, admin_up, oper_up, speed_mbps, vlan, l3_addr, l2_mac)
                   VALUES %s
                   ON CONFLICT (device, ifname) DO UPDATE SET
                       admin_up = EXCLUDED.admin_up,
                       oper_up = EXCLUDED.oper_up,
                       speed_mbps = EXCLUDED.speed_mbps,
                       vlan = EXCLUDED.vlan,
                       l3_addr = EXCLUDED.l3_addr,
                       l2_mac = EXCLUDED.l2_mac,
                       last_seen = NOW()""",
                values
            )
            self.conn.commit()
            logger.info(f"Updated {len(values)} interfaces")
        
        cursor.close()
    
    def ensure_ip_device_nodes(self):
        """Create device nodes for IP addresses referenced in mac_arp edges."""
        logger.info("Creating nodes for IP devices from edges...")
        cursor = self.conn.cursor()
        
        cursor.execute("""
            INSERT INTO devices (name, vendor, model, os_version, role, site)
            SELECT DISTINCT a_dev, 'Unknown', 'Unknown', 'Unknown', 'endpoint', 'default'
            FROM edges
            WHERE method = 'mac_arp' 
              AND a_dev NOT IN (SELECT name FROM devices)
            ON CONFLICT (name) DO NOTHING
        """)
        
        cursor.execute("""
            INSERT INTO devices (name, vendor, model, os_version, role, site, mgmt_ip)
            SELECT DISTINCT b_dev, 'Unknown', 'Switch', 'Unknown', 'switch', 'default', b_dev::inet
            FROM edges
            WHERE method = 'mac_arp' 
              AND b_dev NOT IN (SELECT name FROM devices)
            ON CONFLICT (name) DO NOTHING
        """)
        
        rows_inserted = cursor.rowcount
        self.conn.commit()
        logger.info(f"Created {rows_inserted} IP device nodes")
        cursor.close()
    
    def run_cycle(self):
        try:
            self.update_devices()
            self.update_interfaces()
            self.process_lldp_facts()
            self.ensure_lldp_peer_nodes()
            self.compute_edges_from_lldp()
            self.compute_edges_from_mac_correlation()
            self.ensure_ip_device_nodes()
#            self.compute_edges_from_arp_correlation()
            logger.info("Normalization cycle completed")
        except Exception as e:
            logger.error(f"Error during normalization cycle: {e}", exc_info=True)
            if self.conn:
                self.conn.rollback()
    
    def run(self, interval: int = 300):
        logger.info(f"Starting topology normalizer (interval: {interval}s)")
        
        if not self.connect_db():
            return
        
        while True:
            self.run_cycle()
            logger.info(f"Sleeping for {interval} seconds...")
            time.sleep(interval)

def main():
    pg_dsn = os.getenv("PG_DSN", "postgresql://oc:oc@db/opsconductor")
    suzieq_url = os.getenv("SUZIEQ_URL", "http://suzieq:8000")
    interval = int(os.getenv("POLL_INTERVAL", "300"))
    
    normalizer = TopologyNormalizer(pg_dsn, suzieq_url)
    normalizer.run(interval)

if __name__ == "__main__":
    main()
