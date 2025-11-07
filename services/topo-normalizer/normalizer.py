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
    def __init__(self, pg_dsn: str, suzieq_url: str = "http://suzieq:8000"):
        self.pg_dsn = pg_dsn
        self.suzieq_url = suzieq_url
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
            response = requests.get(f"{self.suzieq_url}/api/v1/{endpoint}", timeout=10)
            if response.status_code == 200:
                return response.json()
            else:
                logger.warning(f"SuzieQ API returned {response.status_code} for {endpoint}")
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
        
        values = []
        for record in data:
            values.append((
                record.get('hostname'),
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
                device as a_dev,
                ifname as a_if,
                peer_device as b_dev,
                peer_ifname as b_if,
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
            ON CONFLICT (edge_id) DO NOTHING
        """)
        
        rows_inserted = cursor.rowcount
        self.conn.commit()
        logger.info(f"Created {rows_inserted} LLDP edges")
        
        cursor.close()
    
    def update_devices(self):
        logger.info("Updating devices...")
        data = self.fetch_suzieq_data("device")
        
        if not data:
            logger.info("No device data available")
            return
        
        cursor = self.conn.cursor()
        
        values = []
        for record in data:
            values.append((
                record.get('hostname'),
                record.get('ipAddress'),
                record.get('vendor'),
                record.get('model'),
                record.get('version'),
                record.get('namespace'),
                record.get('namespace')
            ))
        
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
        
        values = []
        for record in data:
            values.append((
                record.get('hostname'),
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
    
    def run_cycle(self):
        try:
            self.update_devices()
            self.update_interfaces()
            self.process_lldp_facts()
            self.compute_edges_from_lldp()
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
