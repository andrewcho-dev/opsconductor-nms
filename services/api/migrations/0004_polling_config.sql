-- Polling configuration
-- Migration 0004

CREATE TABLE IF NOT EXISTS polling_config (
    id SERIAL PRIMARY KEY,
    key TEXT NOT NULL UNIQUE,
    value TEXT NOT NULL,
    data_type TEXT DEFAULT 'string',
    description TEXT,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_polling_config_key ON polling_config(key);

INSERT INTO polling_config (key, value, data_type, description) 
VALUES 
    ('poll_networks', '', 'string', 'Comma-separated CIDR networks to poll (e.g., 10.121.40.0/24,10.121.50.0/24)'),
    ('skip_networks', '', 'string', 'Comma-separated CIDR networks to skip (e.g., 10.121.19.0/24)'),
    ('poll_enabled', 'true', 'boolean', 'Enable/disable all polling')
ON CONFLICT (key) DO NOTHING;

COMMENT ON TABLE polling_config IS 'Global polling configuration settings';
