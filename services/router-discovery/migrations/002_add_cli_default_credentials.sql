BEGIN;

ALTER TABLE discovery_runs
    ADD COLUMN cli_default_credentials JSONB NOT NULL DEFAULT '[]'::jsonb;

COMMIT;
