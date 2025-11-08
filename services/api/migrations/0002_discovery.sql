-- Discovery and Device Management Schema
-- Migration 0002

-- Credentials table for storing authentication methods
CREATE TABLE IF NOT EXISTS credentials (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    type TEXT NOT NULL CHECK (type IN ('ssh', 'snmp_v2c', 'snmp_v3', 'api', 'http_basic')),
    
    -- SSH credentials
    ssh_username TEXT,
    ssh_password TEXT,
    ssh_private_key TEXT,
    ssh_port INTEGER DEFAULT 22,
    
    -- SNMP v2c credentials
    snmp_community TEXT,
    
    -- SNMP v3 credentials
    snmp_username TEXT,
    snmp_auth_protocol TEXT,
    snmp_auth_password TEXT,
    snmp_priv_protocol TEXT,
    snmp_priv_password TEXT,
    
    -- API credentials
    api_key TEXT,
    api_secret TEXT,
    api_endpoint TEXT,
    
    -- HTTP Basic Auth
    http_username TEXT,
    http_password TEXT,
    
    priority INTEGER DEFAULT 100,
    enabled BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_credentials_type ON credentials(type);
CREATE INDEX IF NOT EXISTS idx_credentials_enabled ON credentials(enabled);

-- Discovery scans table
CREATE TABLE IF NOT EXISTS discovery_scans (
    id SERIAL PRIMARY KEY,
    network_cidr CIDR NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'running', 'completed', 'failed', 'cancelled')),
    
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    
    devices_found INTEGER DEFAULT 0,
    devices_reachable INTEGER DEFAULT 0,
    
    -- Scan options
    scan_ping BOOLEAN DEFAULT TRUE,
    scan_ssh BOOLEAN DEFAULT TRUE,
    scan_snmp BOOLEAN DEFAULT TRUE,
    scan_lldp BOOLEAN DEFAULT FALSE,
    scan_https BOOLEAN DEFAULT TRUE,
    
    credential_ids INTEGER[],
    
    error_message TEXT,
    scan_metadata JSONB,
    
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_discovery_scans_status ON discovery_scans(status);
CREATE INDEX IF NOT EXISTS idx_discovery_scans_created ON discovery_scans(created_at DESC);

-- Discovered devices table
CREATE TABLE IF NOT EXISTS discovered_devices (
    ip INET PRIMARY KEY,
    hostname TEXT,
    vendor TEXT,
    model TEXT,
    os_version TEXT,
    serial_number TEXT,
    role TEXT,
    site TEXT,
    
    -- Reachability status for different protocols
    ping_reachable BOOLEAN DEFAULT FALSE,
    ping_rtt_ms NUMERIC,
    ping_last_checked TIMESTAMPTZ,
    
    ssh_reachable BOOLEAN DEFAULT FALSE,
    ssh_port INTEGER DEFAULT 22,
    ssh_banner TEXT,
    ssh_last_checked TIMESTAMPTZ,
    ssh_credential_id INTEGER REFERENCES credentials(id),
    
    snmp_reachable BOOLEAN DEFAULT FALSE,
    snmp_version TEXT,
    snmp_sys_descr TEXT,
    snmp_sys_object_id TEXT,
    snmp_last_checked TIMESTAMPTZ,
    snmp_credential_id INTEGER REFERENCES credentials(id),
    
    lldp_supported BOOLEAN DEFAULT FALSE,
    lldp_system_name TEXT,
    lldp_neighbors JSONB,
    lldp_last_checked TIMESTAMPTZ,
    
    https_reachable BOOLEAN DEFAULT FALSE,
    https_port INTEGER DEFAULT 443,
    https_last_checked TIMESTAMPTZ,
    
    api_reachable BOOLEAN DEFAULT FALSE,
    api_type TEXT,
    api_endpoint TEXT,
    api_last_checked TIMESTAMPTZ,
    api_credential_id INTEGER REFERENCES credentials(id),
    
    -- Discovery metadata
    discovered_at TIMESTAMPTZ DEFAULT NOW(),
    last_probed TIMESTAMPTZ,
    discovery_status TEXT DEFAULT 'discovered' CHECK (discovery_status IN ('discovered', 'probing', 'reachable', 'unreachable', 'imported', 'ignored')),
    discovery_method TEXT,
    discovery_scan_id INTEGER REFERENCES discovery_scans(id),
    
    -- Import tracking
    imported_to_devices BOOLEAN DEFAULT FALSE,
    imported_at TIMESTAMPTZ,
    device_name TEXT,
    
    -- Additional metadata
    metadata JSONB,
    notes TEXT
);

CREATE INDEX IF NOT EXISTS idx_discovered_devices_hostname ON discovered_devices(hostname);
CREATE INDEX IF NOT EXISTS idx_discovered_devices_vendor ON discovered_devices(vendor);
CREATE INDEX IF NOT EXISTS idx_discovered_devices_status ON discovered_devices(discovery_status);
CREATE INDEX IF NOT EXISTS idx_discovered_devices_discovered_at ON discovered_devices(discovered_at DESC);
CREATE INDEX IF NOT EXISTS idx_discovered_devices_scan_id ON discovered_devices(discovery_scan_id);
CREATE INDEX IF NOT EXISTS idx_discovered_devices_imported ON discovered_devices(imported_to_devices);

-- Hostname mappings table (if not exists from previous migrations)
CREATE TABLE IF NOT EXISTS hostname_mappings (
    hostname TEXT PRIMARY KEY,
    ip_address TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_hostname_mappings_ip ON hostname_mappings(ip_address);

-- Add unique constraint to edges table if not exists
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint 
        WHERE conname = 'edges_unique_link'
    ) THEN
        ALTER TABLE edges 
        ADD CONSTRAINT edges_unique_link 
        UNIQUE (a_dev, a_if, b_dev, b_if);
    END IF;
END $$;

-- View: Summary of discovered devices by status
CREATE OR REPLACE VIEW vw_discovery_summary AS
SELECT 
    discovery_status,
    COUNT(*) as device_count,
    COUNT(*) FILTER (WHERE ping_reachable) as ping_reachable_count,
    COUNT(*) FILTER (WHERE ssh_reachable) as ssh_reachable_count,
    COUNT(*) FILTER (WHERE snmp_reachable) as snmp_reachable_count,
    COUNT(*) FILTER (WHERE imported_to_devices) as imported_count
FROM discovered_devices
GROUP BY discovery_status;

-- View: Reachable devices ready for import
CREATE OR REPLACE VIEW vw_discovery_ready_to_import AS
SELECT 
    ip,
    hostname,
    vendor,
    model,
    os_version,
    CASE 
        WHEN ssh_reachable THEN 'ssh'
        WHEN snmp_reachable THEN 'snmp'
        WHEN api_reachable THEN 'api'
        ELSE 'ping_only'
    END as best_method,
    ssh_credential_id,
    snmp_credential_id,
    api_credential_id,
    discovered_at,
    last_probed
FROM discovered_devices
WHERE discovery_status = 'reachable'
  AND imported_to_devices = FALSE
  AND (ssh_reachable OR snmp_reachable OR api_reachable);

-- Comments
COMMENT ON TABLE credentials IS 'Authentication credentials for device access';
COMMENT ON TABLE discovery_scans IS 'Network discovery scan jobs';
COMMENT ON TABLE discovered_devices IS 'Devices found through network discovery';
COMMENT ON VIEW vw_discovery_summary IS 'Summary statistics of discovered devices';
COMMENT ON VIEW vw_discovery_ready_to_import IS 'Devices ready to be imported into active monitoring';
