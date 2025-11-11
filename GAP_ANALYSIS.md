# Gap Analysis: LLM-Powered Network Topology Discovery System

**Date**: 2025-11-11  
**Status**: Partially Implemented - Non-Functional

---

## Executive Summary

The system architecture is 80% complete with all core services implemented and containerized. However, the system is **non-functional** due to a missing critical component: the packet capture and evidence aggregation service that drives the topology discovery loop.

---

## System Architecture Overview

### Designed Components

```
┌─────────────────┐
│  Packet Source  │ ❌ MISSING
│  (pcap/netflow) │
└────────┬────────┘
         │
         v
┌─────────────────┐
│  Evidence       │ ❌ MISSING
│  Aggregator     │
│  (250ms batch)  │
└────────┬────────┘
         │
         v
┌─────────────────┐
│  LLM Analyst    │ ✅ IMPLEMENTED
│  (Phi-3 model)  │
└────────┬────────┘
         │
         v
┌─────────────────┐
│  State Server   │ ✅ IMPLEMENTED
│  (PostgreSQL)   │
└────────┬────────┘
         │
         v
┌─────────────────┐
│  UI (React)     │ ✅ IMPLEMENTED
│  (vis-network)  │
└─────────────────┘
```

---

## Implementation Status

### ✅ Completed Components

#### 1. **vLLM Service**
- **Status**: Running (healthy)
- **Model**: microsoft/Phi-3-mini-4k-instruct
- **Context**: 4096 tokens
- **Port**: 8000
- **API**: OpenAI-compatible `/v1/chat/completions`

#### 2. **State Server**
- **Status**: Running
- **Stack**: FastAPI + PostgreSQL + AsyncIO
- **Port**: 8080
- **Features**:
  - REST API (`/graph`, `/patch`, `/patches`)
  - WebSocket streaming (`/ws`)
  - JSON Patch-based graph updates
  - CORS configured for UI
- **Location**: `services/state-server/app/`

#### 3. **LLM Analyst Service**
- **Status**: Running (recovered from startup error)
- **Stack**: FastAPI + httpx + jsonschema
- **Port**: Not exposed (internal only)
- **Features**:
  - `/tick` endpoint accepting evidence batches
  - JSON Schema validation (`topology_patch.schema.json`)
  - System prompt loaded from `prompts/system_topologist.txt`
  - Structured output with confidence scores
  - Auto-applies patches to state-server
- **Location**: `services/llm-analyst/app/`

#### 4. **UI Service**
- **Status**: Running
- **Stack**: React 18 + TypeScript + Vite + vis-network
- **Port**: 3000
- **Features**:
  - Real-time graph visualization
  - WebSocket connection to state-server
  - Network topology rendering
- **Location**: `ui/`

#### 5. **PostgreSQL**
- **Status**: Running (healthy)
- **Database**: topology
- **Credentials**: topo/topo

#### 6. **Configuration & Schemas**
- **Topology Patch Schema**: `schemas/topology_patch.schema.json` (125 lines, complete)
- **System Prompt**: `prompts/system_topologist.txt` (28 lines, comprehensive)
- **Environment Config**: `.env` (model selection, context length)
- **Docker Compose**: `docker-compose.yml` (97 lines, all services defined)

---

## ❌ Critical Gaps

### 1. **Missing: Evidence Capture Service** (BLOCKING)

**Impact**: System cannot function

**Description**: No service exists to capture, parse, and batch network traffic evidence.

**Required Capabilities**:
- Capture packets from network interface (libpcap/tcpdump)
- Parse ARP frames
- Parse flow data (NetFlow/sFlow/IPFIX or synthesize from packets)
- Batch evidence into 250ms windows
- Format data according to `InferenceInput` schema
- HTTP POST to analyst service `/tick` endpoint every 250ms
- Handle analyst responses

**Expected Input Format to `/tick`**:
```json
{
  "evidence_window": {
    "window_id": "t0+250ms",
    "arp": [
      {
        "timestamp": "2025-11-11T18:00:00.123Z",
        "src_ip": "192.168.10.50",
        "src_mac": "aa:bb:cc:dd:ee:ff",
        "dst_ip": "192.168.10.1",
        "operation": "request"
      }
    ],
    "flows": [
      {
        "timestamp": "2025-11-11T18:00:00.150Z",
        "src_ip": "192.168.10.50",
        "dst_ip": "8.8.8.8",
        "src_port": 54321,
        "dst_port": 443,
        "protocol": "tcp",
        "packets": 5,
        "bytes": 1500
      }
    ]
  },
  "hypothesis_digest": {
    "node_count": 2,
    "edge_count": 1,
    "top_edges": ["192.168.10.1->192.168.10.50"]
  },
  "seed_facts": {
    "gateway_ip": "192.168.10.1"
  },
  "previous_rationales": []
}
```

**Suggested Implementation**:
- Language: Python (consistent with other services)
- Libraries: `scapy` or `pyshark` for packet capture
- Configuration: network interface, capture filter, batch interval
- Deployment: Docker service with `network_mode: host` and `CAP_NET_RAW`

**Location**: Should be `services/packet-collector/` (does not exist)

---

### 2. **Missing: System Initialization** (HIGH PRIORITY)

**Description**: No bootstrap process to seed initial graph state

**Current State**: 
- Graph has 2 manually-inserted nodes
- No automated seeding from `.env` variables

**Expected Behavior**:
- On startup, seed gateway IP (from `GATEWAY_IP` env var)
- On startup, seed firewall IP (from `FIREWALL_IP` env var)
- Create initial nodes in graph via state-server API

**Suggested Implementation**:
- Init container in docker-compose with `depends_on` state-server
- Simple Python/bash script to POST initial nodes
- Run once on stack startup

---

### 3. **Missing: Error Recovery & Monitoring** (MEDIUM PRIORITY)

**Gaps**:
- No health checks on analyst service
- No retry logic for failed `/tick` calls
- No dead-letter queue for problematic evidence batches
- No metrics/observability (Prometheus, Grafana)
- No structured logging aggregation

**Impact**: System will fail silently on errors

---

### 4. **Missing: Testing & Validation** (MEDIUM PRIORITY)

**Gaps**:
- No unit tests
- No integration tests
- No synthetic data generator for testing
- No PCAP replay capability
- No performance benchmarks

**Impact**: Unknown behavior under load or edge cases

---

### 5. **Documentation Gaps** (LOW PRIORITY)

**Missing**:
- README.md (setup, architecture, usage)
- API documentation (OpenAPI/Swagger)
- Deployment guide
- Network requirements documentation
- Troubleshooting guide

---

## Configuration Issues

### Resolved
- ❌ **Analyst Service Startup Crash** (resolved during analysis)
  - **Error**: `JSONDecodeError: Invalid \escape: line 28 column 58`
  - **Root Cause**: JSON parser strict on regex escapes in schema
  - **Status**: Service now running after container restart

### Existing
- **UI WebSocket URLs hardcoded to `192.168.10.50`**
  - May not work on different networks
  - Should use relative URLs or environment-based configuration

---

## Data Flow Analysis

### Expected Flow (Designed)
```
1. Packet Collector → captures raw packets (250ms window)
2. Packet Collector → formats evidence → POST /tick → Analyst
3. Analyst → LLM inference → generates patch JSON
4. Analyst → validates patch → POST /patch → State Server
5. State Server → applies patch → broadcasts via WebSocket
6. UI → receives update → renders graph changes
```

### Current Flow (Actual)
```
1. ❌ Nothing generates evidence
2. ⏸️  Analyst sits idle waiting for /tick calls
3. ✅ State Server serves static graph data
4. ✅ UI connects and displays initial seed data
```

---

## Environment Variables

### Configured
```bash
MODEL_NAME=microsoft/Phi-3-mini-4k-instruct
VLLM_MAX_CONTEXT_LEN=4096
HF_TOKEN=
```

### Used but Not Set
```bash
GATEWAY_IP=          # Used by analyst service
FIREWALL_IP=         # Used by analyst service
BATCH_MS=250         # Hardcoded in docker-compose
MAX_EVIDENCE_ITEMS=512  # Hardcoded in docker-compose
```

---

## Network Topology Test Data

### Current Graph State
```json
{
  "nodes": {
    "192.168.10.1": {
      "ip": "192.168.10.1",
      "kind": "gateway",
      "role": "core",
      "labels": ["seed"]
    },
    "192.168.10.50": {
      "ip": "192.168.10.50",
      "kind": "host",
      "role": "workstation"
    }
  },
  "edges": [
    {
      "src": "192.168.10.1",
      "dst": "192.168.10.50",
      "type": "inferred_l3",
      "confidence": 0.8,
      "evidence": ["manual"],
      "notes": null
    }
  ]
}
```

---

## Recommendations

### Immediate Actions (P0)
1. **Implement packet collector service**
   - Start with basic pcap → ARP/flow parser
   - Call analyst `/tick` endpoint with batched evidence
   - Handle errors gracefully

2. **Add system initialization**
   - Seed graph on startup
   - Validate all services are reachable

3. **Create test harness**
   - PCAP replay tool
   - Synthetic traffic generator
   - Validate end-to-end flow

### Short-term (P1)
1. Add health checks to all services
2. Implement structured logging
3. Add basic metrics (request counts, latency)
4. Create README with quickstart guide

### Long-term (P2)
1. Add authentication/authorization
2. Implement graph history/time-travel
3. Add filtering/search in UI
4. Support multiple network interfaces
5. Add export capabilities (GraphML, JSON, etc.)

---

## Estimated Effort

| Component | Complexity | Estimated Effort |
|-----------|-----------|------------------|
| Packet Collector Service | Medium | 2-3 days |
| System Initialization | Low | 2-4 hours |
| Test Harness | Medium | 1-2 days |
| Documentation | Low | 1 day |
| Monitoring/Observability | Medium | 2-3 days |
| **Total** | | **7-10 days** |

---

## Conclusion

The system demonstrates solid architectural design and has successfully implemented the most complex components (LLM integration, graph storage, real-time visualization). However, it is currently **non-operational** due to the missing packet collector service, which is the critical driver of the entire system.

The gap is well-defined and solvable. With focused effort on the packet collector implementation, the system could be fully operational within 2-3 days.

---

## Files to Review

- `docker-compose.yml` - Service orchestration
- `services/llm-analyst/app/service.py` - Evidence processing logic
- `services/state-server/app/main.py` - Graph API endpoints
- `schemas/topology_patch.schema.json` - Data contract
- `prompts/system_topologist.txt` - LLM instructions
