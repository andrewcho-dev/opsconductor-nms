-- OpsConductor NMS Topology Schema
-- Initial migration

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Devices table
CREATE TABLE IF NOT EXISTS devices (
  name TEXT PRIMARY KEY,
  mgmt_ip INET,
  vendor TEXT,
  model TEXT,
  os_version TEXT,
  role TEXT,
  site TEXT,
  last_seen TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_devices_site ON devices(site);
CREATE INDEX IF NOT EXISTS idx_devices_role ON devices(role);
CREATE INDEX IF NOT EXISTS idx_devices_last_seen ON devices(last_seen);

-- Interfaces table
CREATE TABLE IF NOT EXISTS interfaces (
  device TEXT NOT NULL REFERENCES devices(name) ON DELETE CASCADE,
  ifname TEXT NOT NULL,
  admin_up BOOLEAN DEFAULT FALSE,
  oper_up BOOLEAN DEFAULT FALSE,
  speed_mbps INTEGER,
  vlan TEXT,
  l3_addr INET,
  l2_mac MACADDR,
  last_seen TIMESTAMPTZ DEFAULT NOW(),
  PRIMARY KEY (device, ifname)
);

CREATE INDEX IF NOT EXISTS idx_interfaces_device ON interfaces(device);
CREATE INDEX IF NOT EXISTS idx_interfaces_vlan ON interfaces(vlan);
CREATE INDEX IF NOT EXISTS idx_interfaces_l2_mac ON interfaces(l2_mac);

-- Raw facts tables (append-only)

CREATE TABLE IF NOT EXISTS facts_lldp (
  fact_id BIGSERIAL PRIMARY KEY,
  collected_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  device TEXT NOT NULL,
  ifname TEXT NOT NULL,
  peer_device TEXT,
  peer_ifname TEXT,
  protocol_payload JSONB
);

CREATE INDEX IF NOT EXISTS idx_facts_lldp_collected ON facts_lldp(collected_at DESC);
CREATE INDEX IF NOT EXISTS idx_facts_lldp_device ON facts_lldp(device, ifname);

CREATE TABLE IF NOT EXISTS facts_cdp (
  fact_id BIGSERIAL PRIMARY KEY,
  collected_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  device TEXT NOT NULL,
  ifname TEXT NOT NULL,
  peer_device TEXT,
  peer_ifname TEXT,
  protocol_payload JSONB
);

CREATE INDEX IF NOT EXISTS idx_facts_cdp_collected ON facts_cdp(collected_at DESC);
CREATE INDEX IF NOT EXISTS idx_facts_cdp_device ON facts_cdp(device, ifname);

CREATE TABLE IF NOT EXISTS facts_mac (
  fact_id BIGSERIAL PRIMARY KEY,
  collected_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  device TEXT NOT NULL,
  ifname TEXT,
  mac_addr MACADDR NOT NULL,
  vlan TEXT,
  protocol_payload JSONB
);

CREATE INDEX IF NOT EXISTS idx_facts_mac_collected ON facts_mac(collected_at DESC);
CREATE INDEX IF NOT EXISTS idx_facts_mac_device ON facts_mac(device);
CREATE INDEX IF NOT EXISTS idx_facts_mac_addr ON facts_mac(mac_addr);

CREATE TABLE IF NOT EXISTS facts_arp (
  fact_id BIGSERIAL PRIMARY KEY,
  collected_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  device TEXT NOT NULL,
  ifname TEXT,
  ip_addr INET NOT NULL,
  mac_addr MACADDR NOT NULL,
  vlan TEXT,
  protocol_payload JSONB
);

CREATE INDEX IF NOT EXISTS idx_facts_arp_collected ON facts_arp(collected_at DESC);
CREATE INDEX IF NOT EXISTS idx_facts_arp_device ON facts_arp(device);
CREATE INDEX IF NOT EXISTS idx_facts_arp_ip ON facts_arp(ip_addr);

CREATE TABLE IF NOT EXISTS facts_routing (
  fact_id BIGSERIAL PRIMARY KEY,
  collected_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  device TEXT NOT NULL,
  ifname TEXT,
  peer_device TEXT,
  peer_ifname TEXT,
  protocol TEXT,
  vrf TEXT,
  protocol_payload JSONB
);

CREATE INDEX IF NOT EXISTS idx_facts_routing_collected ON facts_routing(collected_at DESC);
CREATE INDEX IF NOT EXISTS idx_facts_routing_device ON facts_routing(device);
CREATE INDEX IF NOT EXISTS idx_facts_routing_protocol ON facts_routing(protocol);

-- Edges table (computed connections)
CREATE TABLE IF NOT EXISTS edges (
  edge_id BIGSERIAL PRIMARY KEY,
  a_dev TEXT NOT NULL,
  a_if TEXT NOT NULL,
  b_dev TEXT NOT NULL,
  b_if TEXT NOT NULL,
  method TEXT NOT NULL,
  confidence NUMERIC NOT NULL CHECK (confidence >= 0.0 AND confidence <= 1.0),
  first_seen TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  last_seen TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  evidence JSONB NOT NULL,
  CONSTRAINT valid_method CHECK (method IN ('lldp', 'cdp', 'mac_arp', 'ospf', 'bgp', 'inferred_flow'))
);

CREATE INDEX IF NOT EXISTS idx_edges_a ON edges(a_dev, a_if);
CREATE INDEX IF NOT EXISTS idx_edges_b ON edges(b_dev, b_if);
CREATE INDEX IF NOT EXISTS idx_edges_method ON edges(method);
CREATE INDEX IF NOT EXISTS idx_edges_confidence ON edges(confidence);
CREATE INDEX IF NOT EXISTS idx_edges_last_seen ON edges(last_seen DESC);

-- Name mapping table for device aliases
CREATE TABLE IF NOT EXISTS name_map (
  canonical_name TEXT NOT NULL,
  alias TEXT NOT NULL,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  PRIMARY KEY (canonical_name, alias)
);

CREATE INDEX IF NOT EXISTS idx_name_map_alias ON name_map(alias);

-- View: Latest edge per (a_dev, a_if, b_dev, b_if, method)
CREATE OR REPLACE VIEW vw_edges_current AS
SELECT DISTINCT ON (a_dev, a_if, b_dev, b_if, method)
  edge_id,
  a_dev,
  a_if,
  b_dev,
  b_if,
  method,
  confidence,
  first_seen,
  last_seen,
  evidence
FROM edges
ORDER BY a_dev, a_if, b_dev, b_if, method, last_seen DESC;

-- View: Canonical links (one edge per physical link, highest score)
CREATE OR REPLACE VIEW vw_links_canonical AS
WITH scored_edges AS (
  SELECT
    *,
    ROW_NUMBER() OVER (
      PARTITION BY 
        LEAST(a_dev, b_dev),
        CASE WHEN a_dev < b_dev THEN a_if ELSE b_if END,
        CASE WHEN a_dev < b_dev THEN b_if ELSE a_if END
      ORDER BY 
        confidence DESC,
        CASE method
          WHEN 'lldp' THEN 1
          WHEN 'cdp' THEN 2
          WHEN 'mac_arp' THEN 3
          WHEN 'ospf' THEN 4
          WHEN 'bgp' THEN 5
          WHEN 'inferred_flow' THEN 6
        END,
        last_seen DESC
    ) AS rn
  FROM vw_edges_current
)
SELECT
  edge_id,
  a_dev,
  a_if,
  b_dev,
  b_if,
  method,
  confidence,
  first_seen,
  last_seen,
  evidence
FROM scored_edges
WHERE rn = 1;

-- Comment the tables
COMMENT ON TABLE devices IS 'Network devices discovered in the topology';
COMMENT ON TABLE interfaces IS 'Network interfaces on devices';
COMMENT ON TABLE edges IS 'Computed topology connections between devices';
COMMENT ON TABLE facts_lldp IS 'Raw LLDP neighbor facts from collectors';
COMMENT ON TABLE facts_cdp IS 'Raw CDP neighbor facts from collectors';
COMMENT ON TABLE facts_mac IS 'Raw MAC address table facts from collectors';
COMMENT ON TABLE facts_arp IS 'Raw ARP table facts from collectors';
COMMENT ON TABLE facts_routing IS 'Raw routing protocol adjacency facts from collectors';
COMMENT ON VIEW vw_edges_current IS 'Latest edge per connection and method';
COMMENT ON VIEW vw_links_canonical IS 'Single best edge per physical link';
