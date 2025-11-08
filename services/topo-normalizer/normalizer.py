import os
import time
import logging
import json
import ipaddress
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
            WITH peer_hostname_to_ip AS (
                SELECT DISTINCT
                    fl.peer_device as hostname,
                    COALESCE(hm.ip_address, host(fa.ip_addr)) as ip_address
                FROM facts_lldp fl
                LEFT JOIN hostname_mappings hm ON fl.peer_device = hm.hostname
                LEFT JOIN facts_arp fa ON 
                    LOWER(TRIM('\"' FROM (fl.protocol_payload->>'chassis_id'))) = LOWER(REPLACE(fa.mac_addr::text, ':', '-'))
                    AND NOT (fa.ip_addr <<= '169.254.0.0/16'::inet)
                WHERE fl.peer_device NOT IN (SELECT name FROM devices)
            ),
            mapped_peers AS (
                SELECT DISTINCT
                    COALESCE(ip_address, hostname) as device_name,
                    ip_address
                FROM peer_hostname_to_ip
                WHERE ip_address IS NOT NULL
            )
            INSERT INTO devices (name, mgmt_ip, vendor, model, os_version, role, site)
            SELECT device_name, ip_address::inet, 'N/A', 'N/A', 'N/A', 'endpoint', 'default'
            FROM mapped_peers
            WHERE device_name NOT IN (SELECT name FROM devices)
            ON CONFLICT (name) DO NOTHING
        """)
        
        cursor.execute("""
            INSERT INTO hostname_mappings (hostname, ip_address)
            SELECT DISTINCT
                fl.peer_device,
                host(fa.ip_addr)
            FROM facts_lldp fl
            JOIN facts_arp fa ON 
                LOWER(TRIM('\"' FROM (fl.protocol_payload->>'chassis_id'))) = LOWER(REPLACE(fa.mac_addr::text, ':', '-'))
                AND NOT (fa.ip_addr <<= '169.254.0.0/16'::inet)
                AND fa.ip_addr IS NOT NULL
            ON CONFLICT (hostname) DO UPDATE SET ip_address = EXCLUDED.ip_address
        """)
        
        rows_inserted = cursor.rowcount
        self.conn.commit()
        logger.info(f"Created hostname mappings for {rows_inserted} LLDP peers")
        
        cursor.close()
    
    def compute_edges_from_lldp(self):
        logger.info("Computing edges from LLDP...")
        cursor = self.conn.cursor()
        
        cursor.execute("""
            WITH resolved_lldp AS (
                SELECT
                    COALESCE(hm1.ip_address, ll.device) as a_dev,
                    ll.ifname as a_if,
                    COALESCE(hm2.ip_address, ll.peer_device) as b_dev,
                    ll.peer_ifname as b_if,
                    ll.collected_at,
                    ll.protocol_payload
                FROM facts_lldp ll
                LEFT JOIN hostname_mappings hm1 ON ll.device = hm1.hostname
                LEFT JOIN hostname_mappings hm2 ON ll.peer_device = hm2.hostname
                WHERE ll.collected_at > NOW() - INTERVAL '1 hour'
            ),
            latest_lldp AS (
                SELECT DISTINCT ON (a_dev, a_if, b_dev, b_if)
                    a_dev, a_if, b_dev, b_if, collected_at, protocol_payload
                FROM resolved_lldp
                ORDER BY a_dev, a_if, b_dev, b_if, collected_at DESC
            )
            INSERT INTO edges (a_dev, a_if, b_dev, b_if, method, confidence, evidence, first_seen, last_seen)
            SELECT
                a_dev,
                a_if,
                b_dev,
                b_if,
                'lldp' as method,
                1.0 as confidence,
                jsonb_build_object(
                    'source', 'lldp',
                    'collected_at', collected_at,
                    'payload', protocol_payload
                ) as evidence,
                collected_at as first_seen,
                collected_at as last_seen
            FROM latest_lldp
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
        
        cursor.execute("""
            WITH all_learned_macs AS (
                SELECT DISTINCT
                    host(d.mgmt_ip) as switch_ip,
                    m.ifname as switch_port,
                    m.mac_addr,
                    m.device as switch_device
                FROM facts_mac m
                JOIN devices d ON d.name = m.device
                WHERE m.collected_at > NOW() - INTERVAL '1 hour'
                  AND d.mgmt_ip IS NOT NULL
            ),
            arp_mappings AS (
                SELECT DISTINCT
                    a.mac_addr,
                    host(a.ip_addr) as ip_addr
                FROM facts_arp a
                WHERE a.collected_at > NOW() - INTERVAL '1 hour'
                  AND NOT (a.ip_addr <<= '169.254.0.0/16'::inet)
            )
            INSERT INTO edges (a_dev, a_if, b_dev, b_if, method, confidence, evidence, first_seen, last_seen)
            SELECT DISTINCT
                am.ip_addr as a_dev,
                'mac-learned' as a_if,
                lm.switch_ip as b_dev,
                lm.switch_port as b_if,
                'mac_arp' as method,
                0.75 as confidence,
                jsonb_build_object(
                    'source', 'switch_learned_mac',
                    'device_mac', lm.mac_addr::text,
                    'switch_ip', lm.switch_ip,
                    'switch_port', lm.switch_port
                ) as evidence,
                NOW() as first_seen,
                NOW() as last_seen
            FROM all_learned_macs lm
            JOIN arp_mappings am ON lm.mac_addr = am.mac_addr
            WHERE am.ip_addr != lm.switch_ip
            ON CONFLICT (a_dev, a_if, b_dev, b_if) DO UPDATE SET
                last_seen = EXCLUDED.last_seen,
                confidence = GREATEST(edges.confidence, EXCLUDED.confidence),
                evidence = EXCLUDED.evidence
        """)
        
        rows_inserted2 = cursor.rowcount
        self.conn.commit()
        logger.info(f"Created/updated {rows_inserted2} edges from learned MAC addresses on switches")
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
                UNION
                SELECT DISTINCT device FROM facts_arp
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
                try:
                    ipaddress.ip_address(ip_addr)
                    hostname_to_ip[hostname] = ip_addr
                    values.append((
                        ip_addr,
                        ip_addr,
                        record.get('vendor'),
                        record.get('model'),
                        record.get('version'),
                        record.get('namespace'),
                        record.get('namespace')
                    ))
                except ValueError:
                    logger.debug(f"Skipping device {hostname} with invalid IP: {ip_addr}")
        
        if values:
            execute_values(
                cursor,
                """INSERT INTO devices (name, mgmt_ip, vendor, model, os_version, role, site)
                   VALUES %s
                   ON CONFLICT (name) DO UPDATE SET
                       mgmt_ip = EXCLUDED.mgmt_ip,
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
        
        cursor.execute("SELECT name FROM devices")
        existing_devices = {row[0] for row in cursor.fetchall()}
        
        values = []
        for record in data:
            hostname = record.get('hostname')
            device_name = hostname_map.get(hostname, hostname)
            
            if device_name not in existing_devices:
                logger.debug(f"Skipping interface for non-existent device: {device_name}")
                continue
            
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
            INSERT INTO devices (name, mgmt_ip, vendor, model, os_version, role, site)
            SELECT DISTINCT a_dev, a_dev::inet, 'Unknown', 'Unknown', 'Unknown', 'endpoint', 'default'
            FROM edges
            WHERE method = 'mac_arp' 
              AND a_dev NOT IN (SELECT name FROM devices)
              AND a_dev ~ '^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$'
            ON CONFLICT (name) DO NOTHING
        """)
        
        cursor.execute("""
            INSERT INTO devices (name, vendor, model, os_version, role, site, mgmt_ip)
            SELECT DISTINCT b_dev, 'Unknown', 'Switch', 'Unknown', 'switch', 'default', b_dev::inet
            FROM edges
            WHERE method = 'mac_arp' 
              AND b_dev NOT IN (SELECT name FROM devices)
              AND b_dev ~ '^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$'
            ON CONFLICT (name) DO NOTHING
        """)
        
        rows_inserted = cursor.rowcount
        self.conn.commit()
        logger.info(f"Created {rows_inserted} IP device nodes")
        cursor.close()
    
    def compute_edges_from_poller_lldp(self):
        """Process LLDP facts collected directly by the poller."""
        logger.info("Computing edges from poller LLDP facts...")
        cursor = self.conn.cursor()
        
        cursor.execute("""
            WITH resolved_lldp AS (
                SELECT
                    fl.device as a_dev,
                    fl.ifname as a_if,
                    fl.peer_device as b_dev,
                    fl.peer_ifname as b_if,
                    fl.collected_at,
                    fl.protocol_payload,
                    1.0 as confidence
                FROM facts_lldp fl
                WHERE fl.collected_at > NOW() - INTERVAL '1 hour'
                  AND fl.peer_device IS NOT NULL
                  AND fl.peer_device IN (SELECT name FROM devices)
            ),
            latest_lldp AS (
                SELECT DISTINCT ON (a_dev, a_if, b_dev, b_if)
                    a_dev, a_if, b_dev, b_if, collected_at, protocol_payload, confidence
                FROM resolved_lldp
                ORDER BY a_dev, a_if, b_dev, b_if, collected_at DESC
            )
            INSERT INTO edges (a_dev, a_if, b_dev, b_if, method, confidence, evidence, first_seen, last_seen)
            SELECT
                a_dev,
                a_if,
                b_dev,
                b_if,
                'lldp' as method,
                confidence,
                jsonb_build_object(
                    'source', 'poller_lldp',
                    'collected_at', collected_at,
                    'payload', protocol_payload
                ) as evidence,
                collected_at as first_seen,
                collected_at as last_seen
            FROM latest_lldp
            ON CONFLICT (a_dev, a_if, b_dev, b_if) DO UPDATE SET 
                last_seen = EXCLUDED.last_seen, 
                confidence = EXCLUDED.confidence, 
                evidence = EXCLUDED.evidence
        """)
        
        rows_inserted = cursor.rowcount
        self.conn.commit()
        logger.info(f"Created/updated {rows_inserted} edges from poller LLDP facts")
        cursor.close()
    
    def run_cycle(self):
        try:
            self.update_devices()
            self.update_interfaces()
            self.process_lldp_facts()
            self.ensure_lldp_peer_nodes()
            self.compute_edges_from_poller_lldp()
            self.compute_edges_from_lldp()
            self.compute_edges_from_mac_correlation()
            self.compute_edges_from_arp_correlation()
            self.ensure_ip_device_nodes()
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
