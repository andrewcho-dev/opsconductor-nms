# OpsConductor NMS Router Topology Crawler - Development Plan

## Project Overview

This document outlines the development plan for the **Router Topology Crawler** - a replacement for the legacy automated discovery services. The system intelligently maps network topologies by recursively crawling routers starting from a user-provided gateway IP, using SNMP to extract routing tables and detect router connectivity.

**Key Principle**: User initiates discovery via UI; system never crawls automatically. Manual control with real-time visibility into every discovery step.

---

## Architecture Summary

### Core Components

1. **Database Schema**: PostgreSQL INET-based storage for routers, routes, networks, and protocol-specific peer tables
2. **IP Normalization**: Utility to ensure consistent IP address formatting throughout the system
3. **Discovery Service**: Backend service implementing queue-based recursive router crawler
4. **WebSocket Layer**: Real-time event streaming from discovery service to frontend
5. **REST API**: Control endpoints for start/pause/resume/cancel and status queries
6. **React Frontend**: Real-time UI with discovery controls, progress tracking, and topology visualization

### Key Design Decisions

- **INET as Primary Key**: PostgreSQL INET type for automatic validation/normalization; routers identified by `primary_ip`
- **JSONB for Protocol Metrics**: Flexible storage of protocol-specific data (BGP ≠ OSPF ≠ EIGRP metrics)
- **Queue-Based State Tracking**: Prevents infinite loops, enables pause/resume, tracks retry attempts
- **WebSocket for Real-Time**: Instant UI updates without polling; user sees every discovery step
- **Manual Control**: User explicitly initiates discovery from UI

---

## Development Sprints

### Sprint 1: Database Schema & Infrastructure Setup

**Duration**: 1-2 days  
**Dependency**: None

#### Overview
Create PostgreSQL schema for storing router topology, routing tables, and protocol-specific data. Set up database migrations and initial seed data structures.

#### Tasks

1. **Create Database Migration Files**
   - **File**: `services/state-server/migrations/001_create_topology_schema.sql`
   - **Content**: 
     - `routers` table (primary_ip INET, secondary_ips INET[], vendor, model, snmp_credentials)
     - `routes` table (router_ip INET, destination_network CIDR, next_hop_ip INET, protocol, metrics JSONB)
     - `networks` table (router_ip INET, network CIDR, is_local BOOLEAN)
     - `topology_edges` table (from_router_ip INET, to_router_ip INET, protocol_layer TEXT)
     - `discovery_queue` table (router_ip INET, status TEXT, attempt_count INT, error_message TEXT)
     - `router_protocols` table (router_ip INET, protocol TEXT)
     - `bgp_peers` table (router_ip INET, peer_ip INET, peer_asn INT, state TEXT)
     - `ospf_neighbors` table (router_ip INET, neighbor_ip INET, area_id TEXT, state TEXT)
     - `eigrp_neighbors` table (router_ip INET, neighbor_ip INET, metric INT)

2. **Define PostgreSQL Indexes**
   - Primary key indexes on all tables (especially INET types for fast lookups)
   - Index on `discovery_queue.status` for queue filtering
   - Index on `routes.router_ip, destination_network` for route lookups
   - Index on `networks.router_ip` for network-per-router queries

3. **Create Alembic Migration Wrapper** (if using SQLAlchemy)
   - **File**: `services/state-server/alembic/versions/001_topology_schema.py`
   - Wrap the SQL migration for Python-based applications

#### Acceptance Criteria

- [ ] All 8 tables created with correct INET/CIDR column types
- [ ] All indexes created for optimal query performance
- [ ] Migration can be applied fresh to empty database
- [ ] Migration can be rolled back cleanly
- [ ] INET type constraints validated (IP normalization automatic)

#### Files to Create/Modify

- Create: `services/state-server/migrations/001_create_topology_schema.sql`
- Create: `services/state-server/alembic/versions/001_topology_schema.py` (if applicable)
- Modify: `docker-compose.yml` (ensure PostgreSQL volume persists)

---

### Sprint 2: IP Address Normalization Utility

**Duration**: 1 day  
**Dependency**: Sprint 1 (schema exists)

#### Overview
Create a shared utility library for consistent IP address handling across all services. Leverages PostgreSQL INET type for automatic normalization.

#### Tasks

1. **Create IP Normalization Module**
   - **File**: `shared/ip_utils.py`
   - **Functions**:
     - `normalize_ip(ip: str) -> str`: Converts to standard dotted decimal (e.g., "192.168.1.1")
     - `validate_ip(ip: str) -> bool`: Returns True if valid IPv4 format
     - `is_subnet(network: str) -> bool`: Validates CIDR notation
     - `ip_in_subnet(ip: str, network: str) -> bool`: Checks if IP belongs to network
     - `extract_gateway_from_cidr(network: str) -> str`: Gets network gateway IP
     - `get_network_from_ip(ip: str, netmask: str) -> str`: Computes network address in CIDR

2. **Create IP Utilities Test Suite**
   - **File**: `shared/tests/test_ip_utils.py`
   - Test cases for each normalization function
   - Edge cases: invalid IPs, CIDR boundary conditions

3. **Database Helper Layer**
   - **File**: `shared/db_ip_helpers.py`
   - `ip_to_inet(ip: str)`: Prepares IP for PostgreSQL INET insertion
   - `inet_from_db(inet_val)`: Parses INET from database to normalized string
   - `validate_before_insert(ip: str)`: Pre-validates before DB insert

#### Acceptance Criteria

- [ ] All IP normalization functions implemented and tested
- [ ] Functions handle edge cases (invalid IPs, CIDR boundaries, multi-interface IPs)
- [ ] Test suite passes with 100% code coverage
- [ ] Database helper layer correctly interfaces with INET type
- [ ] Utility is reusable across all backend services

#### Files to Create/Modify

- Create: `shared/ip_utils.py`
- Create: `shared/tests/test_ip_utils.py`
- Create: `shared/db_ip_helpers.py`

---

### Sprint 3: Discovery Service - Router Topology Crawler

**Duration**: 3-4 days  
**Dependency**: Sprint 1 (schema), Sprint 2 (IP utils)

#### Overview
Implement the core discovery service that recursively crawls routers, querying SNMP routing tables and identifying router-to-router connections. Includes queue-based state management for pause/resume capability.

#### Tasks

1. **Create Discovery Service Main Module**
   - **File**: `services/discovery-engine/app/main.py`
   - Initialize Flask app, database connection, logging
   - Create HTTP health check endpoint
   - Service should NOT auto-start discovery; wait for API trigger

2. **Implement Router SNMP Querying**
   - **File**: `services/discovery-engine/app/snmp_client.py`
   - Create SNMPv2c client wrapper (using `pysnmp` library)
   - Function: `get_routing_table(router_ip, snmp_community, snmp_version)` → returns list of routes
   - Function: `get_sysinfo(router_ip, community)` → returns vendor, model, description
   - Function: `get_ip_forwarding_status(router_ip, community)` → returns is_router BOOLEAN
   - Function: `get_interfaces_and_ips(router_ip, community)` → returns all IPs on router
   - Error handling for SNMP timeouts, unreachable hosts, invalid credentials

3. **Implement Routing Table Parser**
   - **File**: `services/discovery-engine/app/route_parser.py`
   - `parse_route_entry(snmp_table_row, router_ip)` → extracts:
     - `destination_network` (CIDR)
     - `next_hop_ip` (INET)
     - `routing_protocol` (static, BGP, OSPF, EIGRP, RIP, ISIS)
     - `administrative_distance` (INT)
     - `metric` (INT or protocol-specific JSONB)
   - Distinguish between local routes and remote routes
   - Handle protocol-specific metric formats (BGP AS path, OSPF cost, EIGRP composite metric)

4. **Implement Queue-Based Discovery Crawler**
   - **File**: `services/discovery-engine/app/crawler.py`
   - `DiscoveryCrawler` class with state machine:
     - States: IDLE, INITIALIZING, RUNNING, PAUSED, COMPLETED, CANCELLED, ERROR
     - Methods:
       - `start(gateway_ip, snmp_community, snmp_version)`: Initialize discovery
       - `pause()`: Pause current crawl
       - `resume()`: Resume paused crawl
       - `cancel()`: Stop and cleanup
       - `get_state()` → returns current state + metrics
   - Queue management:
     - `_enqueue_router(ip)`: Add to discovery queue with status PENDING
     - `_dequeue_router()`: Get next PENDING router from queue
     - `_mark_as_completed(ip)`: Move router to COMPLETED status
     - `_mark_as_failed(ip, error)`: Move to FAILED status, track error
   - Crawl loop logic:
     - Fetch router from queue (status PENDING)
     - Query SNMP: routing table, sysinfo, interfaces
     - Parse routes: identify next-hop IPs
     - For each next-hop: determine if it's a router (IP forwarding enabled)
     - If router: add to queue if not already crawled
     - Store routes, networks, topology edges in database
     - Update router status to COMPLETED
     - Continue until queue empty
   - Prevent infinite loops: track already-crawled router IPs, skip duplicates
   - Track retry attempts per router (max 3 retries on timeout)

5. **Implement Discovery State Manager**
   - **File**: `services/discovery-engine/app/discovery_state.py`
   - `DiscoveryStateManager` class
   - Persistent state tracking (stored in database table `discovery_state`)
   - Methods:
     - `save_state(state_object)`: Serialize current crawl state
     - `load_state()`: Restore previous crawl state (for pause/resume)
     - `reset_state()`: Clear discovery state
   - Enable pause/resume without data loss or duplicate processing

6. **Database Access Layer**
   - **File**: `services/discovery-engine/app/db_access.py`
   - Functions:
     - `insert_router(ip, primary_ip, secondary_ips, vendor, model)`: Add to `routers` table
     - `insert_route(router_ip, dest_network, next_hop, protocol, metric)`: Add to `routes` table
     - `insert_network(router_ip, network, is_local)`: Add to `networks` table
     - `insert_topology_edge(from_ip, to_ip, protocol_layer)`: Add to `topology_edges` table
     - `get_discovery_queue_status()`: Query queue table
     - `update_queue_status(ip, status, error)`: Update queue entry
     - `router_already_discovered(ip)` → BOOLEAN
     - Use IP normalization utility for all IP inputs

7. **Protocol-Specific Handlers** (extensible for future protocols)
   - **File**: `services/discovery-engine/app/protocol_handlers.py`
   - Base `ProtocolHandler` class with abstract methods
   - Implementations:
     - `StaticRouteHandler`: Parse static routes
     - `BGPHandler`: Extract BGP routes, AS paths, local preference
     - `OSPFHandler`: Extract OSPF routes, areas, costs
     - `EIGRPHandler`: Extract EIGRP routes, composite metrics
   - Each handler responsible for metric parsing into JSONB format

8. **Error Handling & Logging**
   - **File**: `services/discovery-engine/app/logger_config.py`
   - Structured logging (JSON format) for:
     - Router connection attempts
     - SNMP query success/failure
     - Routes discovered
     - Topology edges created
     - Errors with traceback
   - Log levels: DEBUG, INFO, WARNING, ERROR
   - Write to both file and stdout

#### Acceptance Criteria

- [ ] SNMP client successfully queries test router (vendor/model/interfaces/routing table)
- [ ] Route parser correctly extracts all route components and identifies protocol
- [ ] Crawler starts from gateway IP, identifies next-hop routers, adds to queue
- [ ] Crawler recursively discovers all reachable routers (no infinite loops)
- [ ] Pause/resume functionality preserves state and prevents duplicate work
- [ ] All discovered routers, routes, networks stored in database correctly
- [ ] IP normalization applied consistently across all database inserts
- [ ] Error handling graceful (timeouts, unreachable hosts, invalid credentials don't crash service)
- [ ] Discovery can be cancelled mid-crawl with clean shutdown
- [ ] Service exposes current state (routers_discovered, routes_discovered, queue_status)

#### Files to Create/Modify

- Create: `services/discovery-engine/app/main.py`
- Create: `services/discovery-engine/app/snmp_client.py`
- Create: `services/discovery-engine/app/route_parser.py`
- Create: `services/discovery-engine/app/crawler.py`
- Create: `services/discovery-engine/app/discovery_state.py`
- Create: `services/discovery-engine/app/db_access.py`
- Create: `services/discovery-engine/app/protocol_handlers.py`
- Create: `services/discovery-engine/app/logger_config.py`
- Create: `services/discovery-engine/requirements.txt` (pysnmp, Flask, psycopg2)
- Create: `services/discovery-engine/Dockerfile`
- Modify: `docker-compose.yml` (add discovery-engine service)

---

### Sprint 4: WebSocket Event Streaming System

**Duration**: 2-3 days  
**Dependency**: Sprint 3 (crawler service)

#### Overview
Implement bidirectional WebSocket communication from discovery service to frontend, streaming real-time events during topology crawl.

#### Tasks

1. **Create WebSocket Server in Discovery Service**
   - **File**: `services/discovery-engine/app/websocket_server.py`
   - Use `python-socketio` or `websockets` library
   - Namespace: `/discovery`
   - Connected clients tracked in memory
   - Broadcast events to all connected clients

2. **Define Event Types & Schema**
   - **File**: `services/discovery-engine/app/event_types.py`
   - Event classes (Pydantic models):
     - `DiscoveryStartedEvent`: gateway_ip, snmp_version, timestamp
     - `RouterDiscoveredEvent`: ip, vendor, model, num_interfaces, timestamp
     - `CrawlStartedEvent`: router_ip, timestamp
     - `RoutingTableFetchedEvent`: router_ip, route_count, timestamp
     - `RouteProcessedEvent`: router_ip, destination_network, next_hop_ip, protocol, timestamp
     - `NetworkDiscoveredEvent`: router_ip, network, is_local, timestamp
     - `TopologyEdgeCreatedEvent`: from_router_ip, to_router_ip, protocol_layer, timestamp
     - `CrawlCompletedEvent`: router_ip, timestamp
     - `DiscoveryPausedEvent`: timestamp
     - `DiscoveryResumedEvent`: timestamp
     - `DiscoveryCompletedEvent`: total_routers, total_routes, total_networks, elapsed_time, timestamp
     - `DiscoveryCancelledEvent`: reason, timestamp
     - `DiscoveryErrorEvent`: error_message, router_ip (optional), timestamp
     - `ProgressUpdateEvent`: routers_crawled, routers_queued, routes_discovered, networks_discovered, current_router, elapsed_time, estimated_remaining_time

3. **Integrate WebSocket Broadcasting into Crawler**
   - **File**: Modify `services/discovery-engine/app/crawler.py`
   - Add `websocket_broadcaster` dependency to crawler
   - Emit event after each significant action:
     - Router discovered
     - Routes fetched
     - Route processed
     - Network discovered
     - Topology edge created
     - Crawl step completed
     - Crawler paused/resumed/completed/cancelled
   - Include timestamps and full context in every event

4. **Create Event Queue for Buffering**
   - **File**: `services/discovery-engine/app/event_queue.py`
   - `EventQueue` class (thread-safe or async)
   - Prevents blocking crawler if WebSocket clients slow
   - Methods:
     - `enqueue(event)`: Add event to queue
     - `dequeue_batch(max_events)`: Retrieve next batch for broadcast
   - Optional persistence to Redis for multi-instance deployments

5. **Client-Side WebSocket Handler** (Reference implementation)
   - **File**: `frontend/src/utils/discoveryWebSocket.ts`
   - Establish WebSocket connection on component mount
   - Auto-reconnect on disconnection with exponential backoff
   - Dispatch events to Redux/Context store
   - Handle event parsing and validation

#### Acceptance Criteria

- [ ] WebSocket server starts with discovery service
- [ ] Events properly serialized and sent to all connected clients
- [ ] Client receives events in real-time (< 100ms latency typical)
- [ ] WebSocket reconnection works if connection drops
- [ ] Event schema validated (no incomplete events sent)
- [ ] Multiple concurrent connections supported
- [ ] Discovery service continues functioning if no WebSocket clients connected

#### Files to Create/Modify

- Create: `services/discovery-engine/app/websocket_server.py`
- Create: `services/discovery-engine/app/event_types.py`
- Create: `services/discovery-engine/app/event_queue.py`
- Create: `frontend/src/utils/discoveryWebSocket.ts`
- Modify: `services/discovery-engine/app/crawler.py` (add event broadcasting)
- Modify: `services/discovery-engine/requirements.txt` (add socketio/websockets)

---

### Sprint 5: REST API Endpoints for Discovery Control

**Duration**: 2 days  
**Dependency**: Sprint 3 (crawler), Sprint 4 (websocket)

#### Overview
Implement REST API endpoints to control discovery lifecycle and query topology data.

#### Tasks

1. **Create Discovery Control Endpoints**
   - **File**: `services/discovery-engine/app/routes.py` or `services/state-server/app/routes/discovery.py`
   - **POST /api/discovery/start**
     - Body: `{ "gateway_ip": "192.168.1.1", "snmp_community": "public", "snmp_version": "2c" }`
     - Response: `{ "status": "INITIALIZING", "discovery_id": "uuid" }`
     - Validation: Valid IP, non-empty community string
     - Error: 400 if already running, 422 if invalid input

   - **GET /api/discovery/state**
     - Response: `{ "status": "RUNNING"|"PAUSED"|"IDLE"|..., "routers_crawled": 5, "routers_queued": 12, "routes_discovered": 156, "networks_discovered": 23, "current_router": "192.168.1.254", "elapsed_time": 234, "estimated_remaining": 400 }`
     - Always returns current state (no auth required for demo)

   - **POST /api/discovery/pause**
     - Response: `{ "status": "PAUSED" }`
     - Error: 400 if not running

   - **POST /api/discovery/resume**
     - Response: `{ "status": "RUNNING" }`
     - Error: 400 if not paused

   - **POST /api/discovery/cancel**
     - Response: `{ "status": "CANCELLED", "reason": "user_requested" }`
     - Cleans up queue and state

   - **GET /api/discovery/queue**
     - Response: `{ "queue": [ { "ip": "192.168.1.254", "status": "PENDING", "attempts": 1, "error": null }, ... ], "total": 12 }`
     - Paginated if queue is large (limit=50 default)

2. **Create Data Query Endpoints**
   - **File**: `services/discovery-engine/app/routes.py`
   - **GET /api/discovery/routers**
     - Response: `{ "routers": [ { "primary_ip": "192.168.1.1", "secondary_ips": ["192.168.1.2"], "vendor": "Cisco", "model": "ISR-4431", "interfaces": 4, "discovered_at": "2025-01-15T10:30:00Z" }, ... ] }`
     - Paginated (limit=100 default)
     - Optional query: `?vendor=Cisco&sort=ip`

   - **GET /api/discovery/routers/<ip>/routes**
     - Response: `{ "router_ip": "192.168.1.1", "routes": [ { "destination_network": "10.0.0.0/8", "next_hop_ip": "192.168.2.1", "protocol": "BGP", "metric": {"as_path": "65000 65001", "local_preference": 100}, "admin_distance": 20 }, ... ] }`
     - Sorted by destination network

   - **GET /api/discovery/routers/<ip>/networks**
     - Response: `{ "router_ip": "192.168.1.1", "networks": [ { "network": "192.168.1.0/24", "is_local": true }, ... ] }`

   - **GET /api/discovery/topology**
     - Response: `{ "nodes": [ {"id": "192.168.1.1", "label": "Gateway", "vendor": "Cisco"}, ... ], "edges": [ {"from": "192.168.1.1", "to": "192.168.1.254", "protocol_layer": "BGP"}, ... ] }`
     - Graph format suitable for D3.js or similar visualization

   - **GET /api/discovery/statistics**
     - Response: `{ "total_routers": 42, "total_routes": 5234, "total_networks": 156, "protocols_used": ["BGP", "OSPF", "static"], "avg_routes_per_router": 124.6, "largest_router": "192.168.1.254" (by route count) }`

3. **Error Handling & Validation**
   - **File**: `services/discovery-engine/app/errors.py` or `services/state-server/app/errors.py`
   - Custom exception classes:
     - `DiscoveryAlreadyRunning`: 409 Conflict
     - `DiscoveryNotRunning`: 400 Bad Request
     - `InvalidIPAddress`: 422 Unprocessable Entity
     - `SNMPError`: 503 Service Unavailable
   - Consistent error response format: `{ "error": "error_name", "message": "user-friendly message", "timestamp": "ISO-8601" }`

4. **Request Validation**
   - **File**: `services/discovery-engine/app/validators.py`
   - Pydantic models for request bodies
   - IP address validation using shared `ip_utils`
   - SNMP version validation (2c, 3)

#### Acceptance Criteria

- [ ] All 7 endpoints implemented and tested with curl/Postman
- [ ] Start endpoint successfully initiates discovery crawl
- [ ] Pause/resume/cancel endpoints modify discovery state correctly
- [ ] State endpoint returns accurate real-time metrics
- [ ] Queue endpoint shows correct status for each router
- [ ] Data query endpoints return correct data from database
- [ ] Topology endpoint returns properly formatted graph structure
- [ ] All error cases handled with appropriate HTTP status codes
- [ ] Request validation prevents invalid data

#### Files to Create/Modify

- Create: `services/discovery-engine/app/routes.py` (or modify state-server)
- Create: `services/discovery-engine/app/errors.py`
- Create: `services/discovery-engine/app/validators.py`
- Modify: `services/discovery-engine/app/main.py` (register routes)

---

### Sprint 6: Frontend UI Components - Real-Time Discovery Interface

**Duration**: 3-4 days  
**Dependency**: Sprint 5 (API endpoints), Sprint 4 (WebSocket)

#### Overview
Build React UI for discovery control, real-time progress tracking, and topology visualization.

#### Tasks

1. **Create Discovery Control Panel Component**
   - **File**: `frontend/src/components/DiscoveryControl.tsx`
   - Sub-components:
     - **GatewayIPInput**: Text input with IP validation
     - **SNMPConfigForm**: SNMP version (2c/3) selector, community string input
     - **ControlButtons**: [Start Discovery], [Pause], [Resume], [Cancel] buttons
       - Buttons disabled based on current state
       - Loading spinner on active button
       - Tooltip help text
   - Form validation before submission
   - Success/error toast notifications

2. **Create Real-Time Metrics Dashboard**
   - **File**: `frontend/src/components/MetricsDashboard.tsx`
   - Sub-components:
     - **MetricCard**: Displays single metric with icon
       - routers_crawled, routers_queued
       - routes_discovered
       - networks_discovered
       - elapsed_time, estimated_remaining_time
     - **CurrentRouterCard**: Shows currently being crawled router with spinning loader
     - **ProgressBars**: Visual progress for routers/routes/networks discovered
     - Update in real-time from WebSocket events

3. **Create Event Log Component**
   - **File**: `frontend/src/components/EventLog.tsx`
   - Scrollable log of last 50 events
   - Each log entry shows:
     - Event type (colored badge)
     - Timestamp
     - Event details (router IP, network discovered, etc.)
     - Auto-scroll to newest events
     - Optional filtering by event type

4. **Create Queue Status Panel**
   - **File**: `frontend/src/components/QueueStatus.tsx`
   - Paginated table of discovery queue
   - Columns: Router IP, Status (PENDING/IN_PROGRESS/COMPLETED/FAILED), Attempts, Error (if any)
   - Color-coded status badges
   - Sort/filter by status
   - Manual refresh button

5. **Create Topology Visualization**
   - **File**: `frontend/src/components/TopologyVisualization.tsx`
   - Use D3.js or Vis.js for interactive graph
   - Nodes: Routers (labeled with IP, vendor/model tooltip)
   - Edges: Router connections (labeled with protocol layer)
   - Features:
     - Zoom/pan interaction
     - Click node to see routes
     - Hover edge to see protocol type
     - Legend for node types, protocol colors
     - Export topology as image/JSON
   - Updates incrementally as new edges discovered via WebSocket

6. **Create Discovery Main Container**
   - **File**: `frontend/src/pages/DiscoveryPage.tsx`
   - Layout combining all components:
     - Left column: Control panel (40% width)
     - Right column: Metrics + Event log (60% width)
     - Bottom: Queue status panel
     - Full-width: Topology visualization (can be toggled/maximized)
   - Responsive layout
   - State management (Redux/Context):
     - Current discovery state
     - Event history
     - Metrics
     - Topology data

7. **Create Redux/Context Store (State Management)**
   - **File**: `frontend/src/store/discoverySlice.ts` (Redux) or `frontend/src/context/DiscoveryContext.tsx` (Context)
   - Actions:
     - `setDiscoveryState(state)`: Update current state (RUNNING, PAUSED, etc.)
     - `addEvent(event)`: Append event to history
     - `updateMetrics(metrics)`: Update dashboard counters
     - `setTopologyData(nodes, edges)`: Update graph
     - `setQueueStatus(queue)`: Update queue panel
   - State shape:
     ```
     {
       discoveryState: "IDLE" | "RUNNING" | "PAUSED" | "COMPLETED" | etc.,
       gateway_ip: string,
       events: Event[],
       metrics: { routers_crawled, routers_queued, ... },
       topology: { nodes: [], edges: [] },
       queue: QueueEntry[],
       error: string | null,
       loading: boolean
     }
     ```

8. **Create WebSocket Connection Management**
   - **File**: `frontend/src/hooks/useDiscoveryWebSocket.ts`
   - Custom hook for connecting to discovery WebSocket
   - Handles:
     - Connection establishment
     - Auto-reconnect with backoff
     - Event parsing and dispatch to Redux/Context
     - Disconnection cleanup
   - Usage: `useDiscoveryWebSocket(gateway_ip, onError)`

9. **Create API Integration Hooks**
   - **File**: `frontend/src/hooks/useDiscoveryAPI.ts`
   - Custom hooks for each API call:
     - `useStartDiscovery(gateway_ip, snmp_config)`: POST /api/discovery/start
     - `usePauseDiscovery()`: POST /api/discovery/pause
     - `useResumeDiscovery()`: POST /api/discovery/resume
     - `useCancelDiscovery()`: POST /api/discovery/cancel
     - `useDiscoveryState()`: GET /api/discovery/state (poll every 2s if not WebSocket)
     - `useRouters()`: GET /api/discovery/routers
     - `useTopologyData()`: GET /api/discovery/topology
   - Error handling with retry logic

10. **Create Styling & Theming**
    - **File**: `frontend/src/styles/discovery.css` or `discovery.module.css`
    - Color scheme for status badges:
      - PENDING: Gray
      - IN_PROGRESS: Blue with spinner
      - COMPLETED: Green
      - FAILED: Red
      - PAUSED: Yellow
    - Responsive breakpoints for mobile/tablet/desktop
    - Dark mode support (optional)

#### Acceptance Criteria

- [ ] Control panel successfully starts discovery with valid gateway IP + SNMP config
- [ ] Metrics dashboard updates in real-time via WebSocket
- [ ] Event log receives and displays all discovery events
- [ ] Queue panel shows current crawl queue with statuses
- [ ] Topology visualization renders nodes/edges, updates incrementally
- [ ] Pause/resume/cancel buttons work correctly
- [ ] UI remains responsive during long crawls (no freezing)
- [ ] WebSocket reconnection works if connection drops
- [ ] All data correctly formatted and displayed
- [ ] No console errors or warnings

#### Files to Create/Modify

- Create: `frontend/src/components/DiscoveryControl.tsx`
- Create: `frontend/src/components/MetricsDashboard.tsx`
- Create: `frontend/src/components/EventLog.tsx`
- Create: `frontend/src/components/QueueStatus.tsx`
- Create: `frontend/src/components/TopologyVisualization.tsx`
- Create: `frontend/src/pages/DiscoveryPage.tsx`
- Create: `frontend/src/store/discoverySlice.ts` (or Context)
- Create: `frontend/src/hooks/useDiscoveryWebSocket.ts`
- Create: `frontend/src/hooks/useDiscoveryAPI.ts`
- Create: `frontend/src/styles/discovery.css`
- Modify: `frontend/src/App.tsx` (add Discovery route)
- Modify: `frontend/package.json` (add D3.js or Vis.js dependency)

---

### Sprint 7: Testing & Integration

**Duration**: 2-3 days  
**Dependency**: Sprints 1-6 (all components)

#### Overview
Write comprehensive tests for discovery service, API endpoints, frontend components, and perform end-to-end integration testing.

#### Tasks

1. **Backend Unit Tests**
   - **File**: `services/discovery-engine/tests/test_snmp_client.py`
     - Mock SNMP queries with fake router data
     - Test successful queries and error handling
     - Test vendor detection, IP extraction

   - **File**: `services/discovery-engine/tests/test_route_parser.py`
     - Test parsing routes for all protocol types (static, BGP, OSPF, EIGRP)
     - Test metric extraction and protocol detection
     - Test CIDR/IP parsing

   - **File**: `services/discovery-engine/tests/test_crawler.py`
     - Mock SNMP client
     - Test crawler state transitions
     - Test queue management (enqueue, dequeue, mark complete)
     - Test pause/resume functionality
     - Test cycle detection (prevents infinite loops)
     - Test with multi-router topology

   - **File**: `services/discovery-engine/tests/test_db_access.py`
     - Mock database (use pytest fixtures)
     - Test all insert/query operations
     - Test INET type normalization
     - Test transaction rollback on error

2. **Backend Integration Tests**
   - **File**: `services/discovery-engine/tests/test_integration.py`
     - Real database (use Docker PostgreSQL in test)
     - Real SNMP client (mock external SNMP servers)
     - Full crawl cycle: start → discover routers → fetch routes → pause → resume → complete
     - Verify database consistency after crawl
     - Verify event sequence correctness

3. **API Endpoint Tests**
   - **File**: `services/discovery-engine/tests/test_api.py`
     - Use pytest-flask or similar
     - Test each endpoint with valid/invalid inputs
     - Test state transitions (start → pause → resume → cancel)
     - Verify response formats match schema
     - Test error cases (invalid IP, already running, etc.)

4. **Frontend Unit Tests**
   - **File**: `frontend/src/components/__tests__/DiscoveryControl.test.tsx`
     - Use React Testing Library
     - Test form submission with valid/invalid inputs
     - Test button state (enabled/disabled)
     - Test API call triggers

   - **File**: `frontend/src/components/__tests__/MetricsDashboard.test.tsx`
     - Test metric updates from Redux/Context
     - Test component rendering with various metric values

   - **File**: `frontend/src/components/__tests__/TopologyVisualization.test.tsx`
     - Test graph rendering with sample nodes/edges
     - Test click/hover interactions

5. **Frontend Integration Tests**
   - **File**: `frontend/src/__tests__/discovery.integration.test.tsx`
     - Mock API and WebSocket
     - Test full discovery workflow: start → receive events → UI updates
     - Test pause/resume/cancel flows

6. **End-to-End Testing**
   - **File**: `e2e-tests/discovery.spec.ts` (using Cypress or Playwright)
   - Launch full stack (backend + frontend)
   - Mock external SNMP servers with test data
     - Create fake router with routing table
     - Create test network with multiple routers
   - User initiates discovery → system crawls topology → verify results displayed in UI
   - Test pause/resume during crawl
   - Test cancel and cleanup

#### Acceptance Criteria

- [ ] All unit tests pass (backend and frontend)
- [ ] Integration tests pass with real database
- [ ] API endpoint tests cover all happy paths and error cases
- [ ] E2E test covers full discovery workflow
- [ ] Code coverage > 80% for critical paths
- [ ] No failing tests in CI/CD pipeline

#### Files to Create/Modify

- Create: `services/discovery-engine/tests/test_snmp_client.py`
- Create: `services/discovery-engine/tests/test_route_parser.py`
- Create: `services/discovery-engine/tests/test_crawler.py`
- Create: `services/discovery-engine/tests/test_db_access.py`
- Create: `services/discovery-engine/tests/test_integration.py`
- Create: `services/discovery-engine/tests/test_api.py`
- Create: `frontend/src/components/__tests__/DiscoveryControl.test.tsx`
- Create: `frontend/src/components/__tests__/MetricsDashboard.test.tsx`
- Create: `frontend/src/components/__tests__/TopologyVisualization.test.tsx`
- Create: `frontend/src/__tests__/discovery.integration.test.tsx`
- Create: `e2e-tests/discovery.spec.ts`
- Create: `services/discovery-engine/tests/conftest.py` (pytest fixtures)
- Create: `frontend/src/__tests__/setup.ts` (test setup)

---

### Sprint 8: Deployment, Documentation & Cleanup

**Duration**: 1-2 days  
**Dependency**: Sprint 7 (all tests passing)

#### Overview
Update deployment configuration, create operational documentation, clean up disabled services, and prepare for production.

#### Tasks

1. **Update Docker Compose Configuration**
   - **File**: Modify `docker-compose.yml`
   - Add `discovery-engine` service
   - Configure resource limits (CPU, memory)
   - Add health checks
   - Configure logging drivers
   - Ensure PostgreSQL has persistent volume
   - Set environment variables for discovery service:
     - `DB_CONNECTION_STRING`
     - `SNMP_TIMEOUT`
     - `DISCOVERY_MAX_RETRIES`
     - `LOG_LEVEL`

2. **Environment Configuration**
   - **File**: Create `.env.example` (if not exists)
   - Document all required environment variables for discovery service:
     ```
     DISCOVERY_MAX_RETRIES=3
     DISCOVERY_QUEUE_TIMEOUT=300
     SNMP_TIMEOUT=5
     SNMP_MAX_RETRIES=2
     WEBSOCKET_HEARTBEAT=30
     DISCOVERY_LOG_LEVEL=INFO
     ```

3. **Operational Documentation**
   - **File**: Create `docs/DISCOVERY_OPERATION.md`
   - Usage guide: How to initiate discovery from UI
   - Troubleshooting section:
     - Common SNMP errors and solutions
     - Database connection issues
     - WebSocket connection problems
   - Performance tuning: Adjusting timeouts, retry counts
   - Monitoring: What metrics to track, log patterns to watch for

4. **API Documentation**
   - **File**: Create `docs/DISCOVERY_API.md` or add to OpenAPI spec
   - Document all REST endpoints
   - Include request/response examples
   - Error codes and meanings
   - WebSocket event schemas

5. **Architecture Documentation**
   - **File**: Create `docs/DISCOVERY_ARCHITECTURE.md`
   - System overview diagram
   - Data flow diagrams
   - Queue state machine diagram
   - Database schema diagram
   - Component interaction diagram

6. **Clean Up Disabled Services** (Optional but Recommended)
   - **File**: Modify `docker-compose.yml`
   - Option A: Completely remove disabled services (packet-collector, nmap-scanner, snmp-discovery, network-discovery, mac-enricher, mib-assigner, mib-walker)
   - Option B: Move to separate `docker-compose.legacy.yml` for archival
   - Option C: Keep commented with clear explanation of deprecation
   - Update any references in documentation

7. **Migration Guide**
   - **File**: Create `docs/LEGACY_TO_DISCOVERY_MIGRATION.md`
   - Explain what changed (automatic discovery → manual router crawler)
   - Steps to export old discovery data (if applicable)
   - Verify new system discovers same topology
   - Rollback procedures if needed

8. **Performance Optimization (Optional)**
   - Profile crawler on test topology with 50+ routers
   - Optimize SNMP queries (batch operations if possible)
   - Optimize database inserts (bulk operations)
   - Consider caching frequently accessed routes

#### Acceptance Criteria

- [ ] Discovery service starts successfully via docker-compose
- [ ] Service is reachable and responsive
- [ ] All documentation is clear and complete
- [ ] Environment variables documented and validated
- [ ] Disabled services removed or archived properly
- [ ] No orphaned references to old discovery services
- [ ] Deployment can be replicated on clean environment

#### Files to Create/Modify

- Modify: `docker-compose.yml` (add discovery-engine, cleanup old services)
- Modify: `.env.example` (add discovery env vars)
- Create: `docs/DISCOVERY_OPERATION.md`
- Create: `docs/DISCOVERY_API.md`
- Create: `docs/DISCOVERY_ARCHITECTURE.md`
- Create: `docs/LEGACY_TO_DISCOVERY_MIGRATION.md` (optional)
- Create: `docs/DISCOVERY_TROUBLESHOOTING.md`
- Modify: `README.md` (add link to discovery documentation)

---

## Cross-Sprint Considerations

### Dependencies & Ordering

```
Sprint 1 (Schema) 
  ↓
Sprint 2 (IP Utils) ←─ Sprint 1
  ↓
Sprint 3 (Crawler) ←─ Sprint 1, 2
  ├─→ Sprint 4 (WebSocket)
  └─→ Sprint 5 (API)
       ↓
Sprint 6 (Frontend) ←─ Sprint 4, 5
  ↓
Sprint 7 (Testing) ←─ All previous
  ↓
Sprint 8 (Deploy) ←─ Sprint 7
```

### Parallel Work Opportunities

- **Sprint 3 & 4**: While crawler implementation in Sprint 3, WebSocket integration can begin once event types defined
- **Sprint 4 & 5**: API endpoints can be implemented in parallel with WebSocket
- **Sprint 5 & 6**: Frontend development can begin while API is being tested
- **Concurrent**: Frontend and backend can be developed independently with mock data/APIs

### Testing Strategy

- **Unit Tests**: Write during implementation (each sprint)
- **Integration Tests**: After individual service complete (after each service sprint)
- **End-to-End Tests**: After full stack integration (Sprint 7)
- **Performance Tests**: After Sprint 3 (crawler optimization)

### Code Quality Gates

- Lint: `npm run lint` / `pylint` before each commit
- Type Check: `npm run typecheck` / `mypy` before each commit
- Test Coverage: Minimum 80% for critical paths
- Code Review: All PRs require review before merge

---

## Technology Stack

### Backend

- **Language**: Python 3.9+
- **Web Framework**: Flask or FastAPI
- **SNMP**: pysnmp or PySNMP
- **Database**: PostgreSQL with INET/CIDR support
- **ORM**: SQLAlchemy (optional)
- **WebSocket**: python-socketio or websockets
- **Logging**: Python logging with JSON formatter
- **Testing**: pytest, pytest-fixtures, pytest-flask

### Frontend

- **Language**: TypeScript
- **Framework**: React 18+
- **State Management**: Redux Toolkit or Context API
- **HTTP Client**: axios or fetch
- **WebSocket**: Socket.IO client or native WebSocket
- **UI Components**: Material-UI or similar
- **Graph Visualization**: D3.js or Vis.js
- **Testing**: React Testing Library, Jest, Cypress

### Infrastructure

- **Containerization**: Docker
- **Orchestration**: docker-compose (local dev), Kubernetes (prod ready)
- **Database**: PostgreSQL 13+
- **Version Control**: Git with semantic versioning

---

## Definition of Done

A sprint is considered complete when:

1. **Code**: All tasks implemented, reviewed, and merged
2. **Tests**: Unit tests pass, integration tests pass, code coverage > 80%
3. **Documentation**: Inline code comments (minimal), README/docs updated
4. **Performance**: No obvious bottlenecks, reasonable response times
5. **Security**: No hardcoded secrets, SNMP credentials stored securely
6. **Integration**: Component integrates cleanly with previous sprints

---

## Risk Mitigation

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|-----------|
| SNMP timeout on large networks | Medium | High | Configurable timeout, async processing, retry logic |
| Database connection pooling issues | Low | High | Use connection pooling, health checks, reconnect logic |
| WebSocket connection drops | Medium | Medium | Auto-reconnect with exponential backoff, fallback polling |
| Memory overflow during large crawl | Low | High | Pagination, streaming results, queue-based processing |
| IP normalization inconsistency | Low | Medium | Use PostgreSQL INET type exclusively, unit test thoroughly |
| Frontend performance with large topology | Medium | Medium | Virtualization, lazy loading, progressive rendering |

---

## Success Metrics

After deployment:

1. **Functionality**: Discovery successfully maps network topology from user-provided gateway
2. **Performance**: Discovery of 50-router network completes in < 5 minutes
3. **Reliability**: 99% successful SNMP queries, < 1% timeout rate
4. **UX**: Real-time UI updates within 100ms of event generation
5. **Maintainability**: All code reviewed, tested, and documented

---

## Next Steps for Implementation

1. **Assign team members** to each sprint
2. **Set sprint duration** (recommend 1-2 weeks per sprint)
3. **Create GitHub issues** for each task
4. **Set up CI/CD pipeline** for automated testing
5. **Reserve staging environment** for end-to-end testing
6. **Create test network topology** (3-5 routers with routing) for development/testing

---

*Document Version: 1.0*  
*Last Updated: 2025-01-15*  
*Status: Ready for Implementation*
