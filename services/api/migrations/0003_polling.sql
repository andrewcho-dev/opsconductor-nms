-- Add polling configuration columns to devices table
-- Migration 0003

ALTER TABLE devices 
ADD COLUMN IF NOT EXISTS polling_enabled BOOLEAN DEFAULT FALSE,
ADD COLUMN IF NOT EXISTS snmp_polling_enabled BOOLEAN DEFAULT FALSE,
ADD COLUMN IF NOT EXISTS snmp_credential_id INTEGER REFERENCES credentials(id),
ADD COLUMN IF NOT EXISTS ssh_credential_id INTEGER REFERENCES credentials(id);

COMMENT ON COLUMN devices.polling_enabled IS 'Enable general polling for this device';
COMMENT ON COLUMN devices.snmp_polling_enabled IS 'Enable SNMP-based polling for this device';
COMMENT ON COLUMN devices.snmp_credential_id IS 'SNMP credentials for polling';
COMMENT ON COLUMN devices.ssh_credential_id IS 'SSH credentials for polling';
