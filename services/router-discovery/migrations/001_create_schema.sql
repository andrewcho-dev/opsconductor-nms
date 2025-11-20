-- Create discovery_runs table
CREATE TABLE discovery_runs (
    id BIGSERIAL PRIMARY KEY,
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at TIMESTAMPTZ,
    status TEXT NOT NULL DEFAULT 'PENDING' CHECK (status IN ('PENDING', 'RUNNING', 'COMPLETED', 'FAILED', 'CANCELLED')),
    root_ip INET NOT NULL,
    snmp_community TEXT NOT NULL,
    snmp_version TEXT NOT NULL CHECK (snmp_version IN ('2c', '3')),
    error_message TEXT
);

CREATE INDEX idx_discovery_runs_status ON discovery_runs(status);
CREATE INDEX idx_discovery_runs_started_at ON discovery_runs(started_at);

-- Create routers table
CREATE TABLE routers (
    id BIGSERIAL PRIMARY KEY,
    run_id BIGINT NOT NULL REFERENCES discovery_runs(id) ON DELETE CASCADE,
    primary_ip INET NOT NULL,
    hostname TEXT,
    sys_descr TEXT,
    sys_object_id TEXT,
    vendor TEXT,
    model TEXT,
    is_router BOOLEAN NOT NULL,
    router_score INTEGER NOT NULL,
    classification_reason TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(run_id, primary_ip)
);

CREATE INDEX idx_routers_run_id ON routers(run_id);
CREATE INDEX idx_routers_run_id_is_router ON routers(run_id, is_router);

-- Create router_networks table
CREATE TABLE router_networks (
    id BIGSERIAL PRIMARY KEY,
    run_id BIGINT NOT NULL REFERENCES discovery_runs(id) ON DELETE CASCADE,
    router_id BIGINT NOT NULL REFERENCES routers(id) ON DELETE CASCADE,
    network CIDR NOT NULL,
    is_local BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE INDEX idx_router_networks_run_id_router_id ON router_networks(run_id, router_id);
CREATE INDEX idx_router_networks_run_id_network ON router_networks(run_id, network);

-- Create router_routes table
CREATE TABLE router_routes (
    id BIGSERIAL PRIMARY KEY,
    run_id BIGINT NOT NULL REFERENCES discovery_runs(id) ON DELETE CASCADE,
    router_id BIGINT NOT NULL REFERENCES routers(id) ON DELETE CASCADE,
    destination CIDR NOT NULL,
    next_hop INET,
    protocol TEXT,
    admin_distance INTEGER,
    metric INTEGER
);

CREATE INDEX idx_router_routes_run_id_router_id ON router_routes(run_id, router_id);
CREATE INDEX idx_router_routes_run_id_destination ON router_routes(run_id, destination);

-- Create topology_edges table
CREATE TABLE topology_edges (
    id BIGSERIAL PRIMARY KEY,
    run_id BIGINT NOT NULL REFERENCES discovery_runs(id) ON DELETE CASCADE,
    from_router_id BIGINT NOT NULL REFERENCES routers(id) ON DELETE CASCADE,
    to_router_id BIGINT NOT NULL REFERENCES routers(id) ON DELETE CASCADE,
    reason TEXT NOT NULL,
    UNIQUE(run_id, from_router_id, to_router_id)
);

CREATE INDEX idx_topology_edges_run_id ON topology_edges(run_id);
