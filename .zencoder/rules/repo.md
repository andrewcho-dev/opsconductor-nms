---
description: Repository Information Overview
alwaysApply: true
---

# OpsConductor NMS Repository Information

## Repository Summary
AI-powered network management system that automatically discovers, classifies, and monitors network devices using passive packet observation, active scanning, and LLM-based analysis. Built with microservices architecture using Python FastAPI services, React UI, and vLLM for AI inference.

## Repository Structure
```
opsconductor-nms/
├── services/         # Python microservices (8 services)
├── ui/              # React/TypeScript frontend
├── schemas/         # JSON schemas for LLM output
├── prompts/         # LLM system prompts
├── models/          # ML model storage
└── docker-compose.yml
```

### Main Repository Components
- **State Server**: Core API, PostgreSQL database, WebSocket streaming for real-time updates
- **Packet Collector**: Network packet capture using Scapy (ARP, flows)
- **Port Scanner**: TCP/UDP port scanning for device identification
- **SNMP Discovery**: Device information gathering via SNMP queries
- **MAC Enricher**: IEEE OUI database lookups for vendor identification
- **MIB Assigner**: Automatic MIB assignment based on device types
- **MIB Walker**: SNMP tree walking with OID text label resolution
- **LLM Analyst**: AI-powered device classification using Phi-3 model
- **UI**: Real-time inventory grid with filtering and device management
- **vLLM**: GPU-accelerated LLM inference engine

## Projects

### UI (React/TypeScript)
**Configuration File**: `ui/package.json`

#### Language & Runtime
**Language**: TypeScript
**Version**: TypeScript 5.6.3, React 18.3.1, Node.js 20
**Build System**: Vite 5.4.8
**Package Manager**: npm

#### Dependencies
**Main Dependencies**:
- `react@18.3.1`, `react-dom@18.3.1`
- `vis-network@9.1.9`, `vis-data@7.1.9` (topology visualization)

**Development Dependencies**:
- `@vitejs/plugin-react@4.3.2`
- `@types/react@18.3.3`, `@types/react-dom@18.3.2`

#### Build & Installation
```bash
cd ui
npm install
npm run dev       # Development server
npm run build     # Production build
npm run preview   # Preview production build
```

#### Docker
**Dockerfile**: `ui/Dockerfile`
**Base Image**: `node:20-alpine`
**Port**: 3000

### State Server (Python)
**Configuration File**: `services/state-server/requirements.txt`

#### Language & Runtime
**Language**: Python 3.11
**Framework**: FastAPI 0.115.2, Uvicorn 0.30.6
**Database**: PostgreSQL 16 with asyncpg

#### Dependencies
**Main Dependencies**:
- `fastapi@0.115.2`, `uvicorn[standard]@0.30.6`
- `sqlalchemy[asyncio]@2.0.36`, `asyncpg@0.29.0`
- `pydantic@2.9.2`, `pydantic-settings@2.4.0`
- `jsonpatch@1.33`, `httpx@0.27.0`
- `python-json-logger@2.0.7`

#### Build & Installation
```bash
cd services/state-server
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8080
```

#### Docker
**Dockerfile**: `services/state-server/Dockerfile`
**Base Image**: `python:3.11-slim`
**Port**: 8080

### LLM Analyst (Python)
**Configuration File**: `services/llm-analyst/requirements.txt`

#### Language & Runtime
**Language**: Python 3.11
**Framework**: FastAPI 0.115.2

#### Dependencies
**Main Dependencies**:
- `fastapi@0.115.2`, `uvicorn[standard]@0.30.6`
- `httpx@0.27.2`, `pydantic@2.9.2`
- `jsonschema@4.23.0`
- `python-json-logger@2.0.7`

#### Docker
**Dockerfile**: `services/llm-analyst/Dockerfile`
**Base Image**: `python:3.11-slim`
**Port**: 8100

### Packet Collector (Python)
**Configuration File**: `services/packet-collector/requirements.txt`

#### Language & Runtime
**Language**: Python 3.11
**Network Library**: Scapy 2.5.0

#### Dependencies
**Main Dependencies**:
- `scapy@2.5.0` (packet capture/manipulation)
- `httpx@0.27.2`, `aiohttp@3.10.5`
- `pydantic@2.9.2`, `uvloop@0.20.0` (Linux only)

#### Docker
**Network Mode**: `host` (requires NET_ADMIN, NET_RAW capabilities)
**Port**: 9100 (health check)

### Port Scanner (Python)
**Configuration File**: `services/port-scanner/requirements.txt`

#### Dependencies
**Main Dependencies**:
- `httpx@0.27.2`, `aiohttp@3.10.5`

#### Docker
**Port**: 9200 (health check)

### SNMP Discovery (Python)
**Configuration File**: `services/snmp-discovery/requirements.txt`

#### Dependencies
**Main Dependencies**:
- `httpx@0.27.2`, `aiohttp@3.10.5`
- `pysnmp@6.2.6`

#### Docker
**Port**: 9300 (health check)

### MIB Walker (Python)
**Configuration File**: `services/mib-walker/requirements.txt`

#### Dependencies
**Main Dependencies**:
- `httpx`, `aiohttp`
- `pysnmp`, `pysmi` (SNMP MIB parsing)

#### Docker
**Port**: 9600 (health check)

### MAC Enricher (Python)
**Configuration File**: `services/mac-enricher/requirements.txt`

#### Docker
**Port**: 9400 (health check)

### MIB Assigner (Python)
**Configuration File**: `services/mib-assigner/requirements.txt`

#### Docker
**Port**: 9500 (health check)

## Docker Orchestration

### Docker Compose
**File**: `docker-compose.yml`
**Services**: 10 containers (vLLM, PostgreSQL, 8 microservices)

**Key Configuration**:
- **vLLM**: Requires NVIDIA GPU, ports 8000
- **PostgreSQL**: Volume-backed data persistence
- **Network Mode**: Host networking for packet-collector (requires promiscuous mode)
- **Health Checks**: All services have health check endpoints

### Usage
```bash
docker compose up -d              # Start all services
docker compose logs -f            # View logs
docker compose ps                 # Check status
docker compose down               # Stop services
docker compose down -v            # Stop and remove volumes
```

### Environment Configuration
**File**: `.env.example` (copy to `.env`)
**Key Variables**:
- `PCAP_IFACE`: Network interface for packet capture
- `MODEL_NAME`: LLM model (default: microsoft/Phi-3-mini-4k-instruct)
- `VLLM_MAX_CONTEXT_LEN`: LLM context length (default: 8192)
- `SCAN_PORTS`: Comma-separated port list for scanning
- `SNMP_COMMUNITY`: SNMP community string (default: public)
- `GATEWAY_IP`, `FIREWALL_IP`: Network seed IPs

## Main Files

### Application Entry Points
- **State Server**: `services/state-server/app/main.py`
- **LLM Analyst**: `services/llm-analyst/app/main.py`
- **UI**: `ui/src/main.tsx`

### Configuration Files
- **LLM Prompts**: `prompts/system_topologist.txt`
- **JSON Schema**: `schemas/topology_patch.schema.json`
- **Database Scripts**: `services/state-server/populate_mibs.py`, `services/state-server/migrate_mib_ids.py`

## Prerequisites

### Hardware Requirements
- Modern multi-core CPU
- NVIDIA GPU with 8GB+ VRAM (for AI features)
- 16GB RAM minimum (32GB recommended)
- Network interface with promiscuous mode support

### Software Requirements
- Docker 24.0+ with Compose v2
- NVIDIA Container Toolkit (for GPU support)
- Linux (tested on Ubuntu 22.04)

## Validation

**Health Checks**:
```bash
curl http://localhost:8080/health          # State server
curl http://localhost:8080/api/inventory   # API verification
curl http://localhost:3000                 # UI access
```

**Database Operations**:
```bash
# Backup
docker compose exec postgres pg_dump -U topo topology > backup.sql

# Restore
cat backup.sql | docker compose exec -T postgres psql -U topo topology
```
