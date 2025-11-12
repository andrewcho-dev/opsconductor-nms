# OpsConductor NMS: LLM-Powered Network Topology Discovery

An experimental network management system that uses Large Language Models to autonomously discover and map network topology from passive packet observation. The system combines real-time packet capture, LLM reasoning, and interactive visualization to build a living map of your network.

[![Status](https://img.shields.io/badge/status-experimental-orange)]()
[![License](https://img.shields.io/badge/license-MIT-blue)]()

---

## Overview

**OpsConductor NMS** replaces traditional network discovery heuristics with AI-powered reasoning. Instead of hardcoded rules, a fine-tuned language model observes ARP frames and network flows, forms hypotheses about network relationships, and iteratively refines a topology graph.

### Key Features

- **AI-Driven Discovery**: LLM (Phi-3) analyzes packet evidence to infer network topology
- **Real-Time Updates**: 250ms evidence windows with live WebSocket streaming
- **Confidence Scoring**: Every edge has a confidence score (0-1) with evidence citations
- **Interactive Visualization**: React-based UI with vis-network for graph exploration
- **JSON Patch Architecture**: Incremental, auditable graph updates
- **PostgreSQL Backend**: Persistent graph state with full patch history

---

## Architecture

```
  Network Interface
         │
         ▼
  ┌──────────────┐
  │   Packet     │  ✓ Implemented
  │  Collector   │    Scapy + asyncio
  │  (250ms)     │    Host network mode
  └──────┬───────┘
         │ 250ms batches
         │ (ARP + Flows)
         ▼
  ┌──────────────┐
  │     LLM      │  ✓ Implemented
  │   Analyst    │    FastAPI + httpx
  │  (Phi-3)     │    Structured output
  └──────┬───────┘
         │ JSON Patch
         ▼
  ┌──────────────┐
  │    State     │  ✓ Implemented
  │   Server     │    PostgreSQL
  │  (Graph DB)  │    WebSocket pub/sub
  └──────┬───────┘
         │ WebSocket
         ▼
  ┌──────────────┐
  │   UI (React) │  ✓ Implemented
  │  vis-network │    Real-time graph
  └──────────────┘
```

### Components

| Service | Purpose | Tech Stack | Status |
|---------|---------|-----------|--------|
| **vLLM** | LLM inference engine | vLLM + Phi-3-mini-4k | ✅ Running |
| **Analyst** | Evidence → Patch reasoning | FastAPI + httpx | ✅ Running |
| **State Server** | Graph storage & streaming | FastAPI + PostgreSQL | ✅ Running |
| **UI** | Interactive visualization | React + vis-network | ✅ Running |
| **Packet Collector** | pcap → evidence batches | Python + Scapy | ✅ **Implemented** |

> **✅ COMPLETE**: All core services implemented. System is now functional for live network topology discovery.

---

## Prerequisites

### Hardware Requirements

- **GPU**: NVIDIA GPU with 8GB+ VRAM (for vLLM)
- **RAM**: 16GB minimum, 32GB recommended
- **Storage**: 20GB for models + Docker volumes

### Software Requirements

- **Docker** 24.0+ with Docker Compose v2
- **NVIDIA Container Toolkit** (for GPU support)
- **Linux** (tested on Ubuntu 22.04)

### Network Requirements

- Promiscuous mode access to a network interface
- Ability to capture raw packets (root/CAP_NET_RAW)

---

## Installation

### 1. Clone Repository

```bash
git clone https://github.com/yourusername/opsconductor-nms.git
cd opsconductor-nms
```

### 2. Configure Environment

```bash
# Copy and edit environment file
cp .env.example .env
nano .env
```

**Environment Variables**:

```bash
# LLM Configuration
MODEL_NAME=microsoft/Phi-3-mini-4k-instruct
VLLM_MAX_CONTEXT_LEN=4096
HF_TOKEN=                           # Optional: HuggingFace token for private models

# Network Seeds (Optional)
GATEWAY_IP=192.168.1.1              # Known gateway IP
FIREWALL_IP=                        # Known firewall IP

# UI Configuration
UI_WS_ORIGIN=*                      # CORS origin for WebSocket
```

### 3. Download Model (Optional)

Pre-download the model to avoid startup delays:

```bash
mkdir -p models
docker run --rm -v $(pwd)/models:/models \
  vllm/vllm-openai:latest \
  huggingface-cli download microsoft/Phi-3-mini-4k-instruct \
  --local-dir /models/Phi-3-mini-4k-instruct
```

### 4. Start Services

```bash
# Start all services
docker compose up -d

# View logs
docker compose logs -f

# Check service health
docker compose ps
```

### 5. Access UI

Open your browser to:

```
http://localhost:3000
```

---

## Configuration

### Service Ports

| Service | Internal Port | External Port | Purpose |
|---------|--------------|---------------|---------|
| vLLM | 8000 | 8000 | OpenAI-compatible API |
| State Server | 8080 | 8080 | REST API + WebSocket |
| UI | 3000 | 3000 | Web interface |
| Analyst | 8100 | (internal) | Evidence processing |
| PostgreSQL | 5432 | (internal) | Database |

### LLM Configuration

Edit `docker-compose.yml` to adjust vLLM settings:

```yaml
services:
  vllm:
    command: >
      --host 0.0.0.0
      --port 8000
      --model ${MODEL_NAME}
      --dtype auto
      --max-model-len ${VLLM_MAX_CONTEXT_LEN:-8192}
      --gpu-memory-utilization 0.9     # Adjust GPU memory usage
      --trust-remote-code
```

### Analyst Configuration

Environment variables for `analyst` service:

```yaml
environment:
  - LLM_BASE_URL=http://vllm:8000/v1
  - LLM_MODEL=${MODEL_NAME}
  - RESPONSE_FORMAT=json_schema          # or json_object
  - BATCH_MS=250                         # Evidence window size (ms)
  - MAX_EVIDENCE_ITEMS=512               # Max ARP+flow items per batch
  - SEED_GATEWAY_IP=${GATEWAY_IP:-}     # Optional seed
  - SEED_FIREWALL_IP=${FIREWALL_IP:-}   # Optional seed
```

### Custom Prompts & Schemas

- **System Prompt**: `prompts/system_topologist.txt`
- **JSON Schema**: `schemas/topology_patch.schema.json`

Both are mounted as read-only volumes and can be edited without rebuilding containers.

---

## API Documentation

### State Server API

**Base URL**: `http://localhost:8080`

#### `GET /health`

Health check endpoint.

**Response**:
```json
{"status": "ok"}
```

#### `GET /graph`

Retrieve current topology graph.

**Response**:
```json
{
  "graph": {
    "nodes": {
      "192.168.10.1": {
        "ip": "192.168.10.1",
        "kind": "gateway",
        "role": "core",
        "labels": ["seed"]
      }
    },
    "edges": [
      {
        "src": "192.168.10.1",
        "dst": "192.168.10.50",
        "type": "inferred_l3",
        "confidence": 0.85,
        "evidence": ["t0+250ms#flows[3]"],
        "notes": null
      }
    ]
  },
  "updated_at": "2025-11-11T18:17:49.346782Z"
}
```

#### `POST /patch`

Apply a JSON Patch to the graph.

**Request Body**:
```json
{
  "version": "1.0",
  "patch": [
    {
      "op": "add",
      "path": "/nodes/192.168.10.100",
      "value": {
        "ip": "192.168.10.100",
        "kind": "host",
        "role": "workstation"
      }
    }
  ],
  "rationale": "New host discovered via ARP request",
  "warnings": []
}
```

**Response**: Same as `GET /graph`

#### `GET /patches?limit=50`

Retrieve patch history.

**Query Parameters**:
- `limit` (int, 1-500): Number of patches to retrieve

**Response**:
```json
[
  {
    "id": 42,
    "patch": [...],
    "rationale": "Added new edge based on flow data",
    "warnings": [],
    "created_at": "2025-11-11T18:20:00.123Z"
  }
]
```

#### `WS /ws`

WebSocket endpoint for real-time graph updates.

**Initial Message** (snapshot):
```json
{
  "graph": {...},
  "updated_at": "2025-11-11T18:17:49.346782Z",
  "patch": [],
  "rationale": "initial",
  "warnings": []
}
```

**Update Messages**:
```json
{
  "graph": {...},
  "updated_at": "2025-11-11T18:17:49.596Z",
  "patch": [{...}],
  "rationale": "Added edge 192.168.10.1 -> 8.8.8.8 (NAT hypothesis)",
  "warnings": ["Low confidence due to limited visibility"]
}
```

---

### Analyst API (Internal)

**Base URL**: `http://analyst:8100` (internal network only)

#### `POST /tick`

Process evidence window and generate topology patch.

**Request Body**:
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
    "edge_count": 1
  },
  "seed_facts": {
    "gateway_ip": "192.168.10.1"
  },
  "previous_rationales": []
}
```

**Response**:
```json
{
  "request_id": "t0+250ms",
  "patch": {
    "version": "1.0",
    "patch": [{...}],
    "rationale": "...",
    "warnings": []
  },
  "applied_graph": {...},
  "applied_at": "2025-11-11T18:00:00.500Z"
}
```

---

## Usage

### Manual Patch Testing

```bash
# Add a new node
curl -X POST http://localhost:8080/patch \
  -H "Content-Type: application/json" \
  -d '{
    "version": "1.0",
    "patch": [
      {
        "op": "add",
        "path": "/nodes/192.168.10.100",
        "value": {
          "ip": "192.168.10.100",
          "kind": "host",
          "role": "server"
        }
      }
    ],
    "rationale": "Manual test",
    "warnings": []
  }'
```

### Testing WebSocket Connection

```bash
# Use websocat or similar
websocat ws://localhost:8080/ws
```

### Viewing Logs

```bash
# All services
docker compose logs -f

# Specific service
docker compose logs -f analyst
docker compose logs -f state-server
```

### Stopping Services

```bash
# Stop all services
docker compose down

# Stop and remove volumes (wipes database)
docker compose down -v
```

---

## Development

### Project Structure

```
opsconductor-nms/
├── docker-compose.yml          # Service orchestration
├── .env                        # Environment configuration
├── schemas/
│   └── topology_patch.schema.json  # JSON Schema for patches
├── prompts/
│   └── system_topologist.txt       # LLM system prompt
├── services/
│   ├── llm-analyst/
│   │   ├── Dockerfile
│   │   ├── requirements.txt
│   │   └── app/
│   │       ├── main.py         # FastAPI app
│   │       ├── service.py      # Business logic
│   │       ├── schemas.py      # Pydantic models
│   │       └── config.py       # Settings
│   └── state-server/
│       ├── Dockerfile
│       ├── requirements.txt
│       └── app/
│           ├── main.py         # FastAPI app
│           ├── service.py      # Graph operations
│           ├── database.py     # SQLAlchemy setup
│           ├── models.py       # DB models
│           ├── schemas.py      # Pydantic models
│           └── config.py       # Settings
└── ui/
    ├── Dockerfile
    ├── package.json
    ├── vite.config.ts
    ├── index.html
    └── src/
        ├── main.tsx
        ├── App.tsx             # Main component
        └── index.css
```

### Technology Stack

**Backend**:
- **Framework**: FastAPI 0.115+
- **ORM**: SQLAlchemy 2.0 (async)
- **Database**: PostgreSQL 16
- **LLM Inference**: vLLM
- **Validation**: Pydantic 2.9
- **Patches**: jsonpatch 1.33

**Frontend**:
- **Framework**: React 18
- **Build Tool**: Vite 5.4
- **Visualization**: vis-network 9.1
- **Language**: TypeScript 5.6

**Infrastructure**:
- **Container Runtime**: Docker + Docker Compose
- **GPU Acceleration**: NVIDIA Container Toolkit

### Local Development

#### Backend Services

```bash
# Install dependencies
cd services/llm-analyst
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Run locally (requires PostgreSQL + vLLM running)
export LLM_BASE_URL=http://localhost:8000/v1
export LLM_MODEL=microsoft/Phi-3-mini-4k-instruct
export STATE_SERVER_URL=http://localhost:8080
export JSON_SCHEMA_PATH=../../schemas/topology_patch.schema.json
export SYSTEM_PROMPT_PATH=../../prompts/system_topologist.txt
uvicorn app.main:app --reload --port 8100
```

#### Frontend

```bash
cd ui
npm install
npm run dev
```

Access dev server at `http://localhost:5173`

### Adding a Node Type

1. Update JSON Schema (`schemas/topology_patch.schema.json`):
```json
{
  "kind": {
    "type": "string",
    "enum": ["host", "gateway", "firewall", "router", "server", "switch", "load_balancer", "unknown"]
  }
}
```

2. Update UI visualization (`ui/src/App.tsx`):
```typescript
const kind = typeof details.kind === "string" ? details.kind : "unknown";
// vis-network will automatically color by group
```

3. Update system prompt if needed (`prompts/system_topologist.txt`)

### Modifying LLM Behavior

Edit `prompts/system_topologist.txt` to adjust reasoning behavior. Changes take effect on container restart.

Example modifications:
- Adjust confidence thresholds
- Add new inference rules
- Change output format guidelines

---

## Troubleshooting

### Analyst Service Won't Start

**Symptom**: `JSONDecodeError: Invalid \escape` in logs

**Cause**: JSON schema has invalid escape sequences

**Solution**: Validate schema syntax:
```bash
python3 -c "import json; json.load(open('schemas/topology_patch.schema.json'))"
```

### vLLM Out of Memory

**Symptom**: `CUDA out of memory` errors

**Solutions**:
```bash
# Reduce context length
VLLM_MAX_CONTEXT_LEN=2048

# Reduce GPU memory utilization in docker-compose.yml
--gpu-memory-utilization 0.8

# Use a smaller model
MODEL_NAME=microsoft/Phi-3-mini-128k-instruct
```

### UI Shows "error" Status

**Check**:
1. State server is running: `curl http://localhost:8080/health`
2. CORS configuration in `docker-compose.yml`
3. Network connectivity between containers

### WebSocket Connection Fails

**Check**:
1. WebSocket URL in UI environment variables
2. CORS origin matches client origin
3. Firewall rules allow WebSocket connections

### Packet Collector Not Capturing

**Check**:
1. Correct network interface: `ip addr` or `ifconfig`
2. Update `PCAP_IFACE` in `.env`
3. Container has NET_RAW capability
4. BPF filter is not too restrictive

**Logs**:
```bash
docker compose logs -f packet-collector
```

**Health check**:
```bash
curl http://localhost:9100/health
```

---

## Performance Tuning

### LLM Inference

- **Batch size**: Adjust `BATCH_MS` (default: 250ms)
- **Context length**: Lower `VLLM_MAX_CONTEXT_LEN` for faster inference
- **Temperature**: Modify in `services/llm-analyst/app/service.py`

### Database

```sql
-- Add indexes for faster queries
CREATE INDEX idx_patch_events_created ON patch_events(created_at DESC);
```

### WebSocket Broadcasting

Adjust queue size in `services/state-server/app/service.py`:
```python
queue: asyncio.Queue = asyncio.Queue(maxsize=16)  # Increase for slower clients
```

---

## Security Considerations

### Current State (Development)

⚠️ **Not production-ready**:
- No authentication on APIs
- No TLS/SSL encryption
- CORS set to `*` (allow all origins)
- Database credentials in plaintext

### Production Recommendations

1. **Add API authentication** (JWT, API keys)
2. **Enable TLS** on all endpoints
3. **Restrict CORS** to specific origins
4. **Use secrets management** (HashiCorp Vault, K8s secrets)
5. **Network segmentation** (internal network for services)
6. **Audit logging** for all graph modifications
7. **Rate limiting** on public endpoints

---

## Roadmap

### Immediate (Required for MVP)
- [ ] Implement packet collector service
- [ ] Add system initialization script
- [ ] Create synthetic test data generator
- [ ] Add health checks to all services

### Short-term
- [ ] Implement error recovery & retries
- [ ] Add Prometheus metrics
- [ ] Create API documentation (OpenAPI)
- [ ] Add unit tests
- [ ] Support PCAP replay for testing

### Long-term
- [ ] Multi-network support
- [ ] Graph history & time-travel
- [ ] Advanced filtering in UI
- [ ] Export to Graphviz/GraphML
- [ ] Authentication & RBAC
- [ ] Anomaly detection
- [ ] Integration with SIEM systems

---

## Contributing

Contributions welcome! Please see [CONTRIBUTING.md](./CONTRIBUTING.md) for guidelines.

### Development Workflow

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make your changes
4. Run tests (when available)
5. Commit your changes (`git commit -m 'Add amazing feature'`)
6. Push to the branch (`git push origin feature/amazing-feature`)
7. Open a Pull Request

---

## Recent Updates (2025-11-12)

### ✅ Fixed Issues
- **UI Edge Duplication Errors**: Implemented deduplication logic to merge duplicate edges by combining evidence
- **LLM Token Limits**: Increased max_tokens to 1400 and reduced evidence window to 80 items to prevent JSON truncation
- **Missing Node Auto-Creation**: State server now automatically creates nodes when edges reference non-existent IPs
- **Graph Rendering**: Fixed vis-network CSS to properly display topology (min-height: 400px)
- **Deterministic Output**: Set LLM temperature to 0.0 for more consistent JSON generation

### 🎯 Current Status
- **7 nodes discovered** on 192.168.10.0/24 network (12% of 40+ devices)
- **87 edges** (deduplicated from 90%+ duplication rate)
- **System fully operational** - All services running with WebSocket streaming
- **LLM analysis working** - No more JSON parsing errors

### Known Limitations

1. **Limited Network Visibility** - Passive packet capture on switched networks only observes ~12% of devices (see [GAP_ANALYSIS.md](./GAP_ANALYSIS.md))
2. **No Active Discovery** - System relies purely on passive observation (no ARP/ping sweeps)
3. **Backend Edge Duplication** - State server accumulates duplicate edges (90%+ duplication) - deduplication needed
4. **No Authentication** - All endpoints are publicly accessible
5. **No Error Recovery** - Failed LLM calls are not retried
6. **Limited Testing** - No automated test suite

See [GAP_ANALYSIS.md](./GAP_ANALYSIS.md) for comprehensive analysis and improvement roadmap.

---

## License

MIT License - See [LICENSE](./LICENSE) for details.

---

## Acknowledgments

- **vLLM Team** - Fast LLM inference engine
- **Microsoft** - Phi-3 model family
- **vis.js** - Network visualization library
- **FastAPI** - Modern Python web framework

---

## Contact

- **Issues**: [GitHub Issues](https://github.com/yourusername/opsconductor-nms/issues)
- **Discussions**: [GitHub Discussions](https://github.com/yourusername/opsconductor-nms/discussions)

---

## Citation

If you use this project in your research, please cite:

```bibtex
@software{opsconductor_nms,
  title={OpsConductor NMS: LLM-Powered Network Topology Discovery},
  author={Your Name},
  year={2025},
  url={https://github.com/yourusername/opsconductor-nms}
}
```
