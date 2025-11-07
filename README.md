# OpsConductor NMS

Network Management System with topology discovery, visualization, and troubleshooting capabilities.

## Architecture

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for detailed architecture documentation.

## Quick Start

```bash
docker compose up -d
```

Services will be available at:
- API: http://localhost:8088
- UI: http://localhost:8089
- API Docs: http://localhost:8088/docs

## Services

- **suzieq**: Network data collector (SSH/API/SNMP)
- **topo-normalizer**: Processes facts and computes topology edges
- **api**: REST API for topology queries
- **ui**: React-based web interface
- **db**: PostgreSQL database
- **sflow**: Optional sFlow collector

## Development

See [docs/IMPLEMENTATION_PLAN.md](docs/IMPLEMENTATION_PLAN.md) for the implementation roadmap.

## Documentation

- [Architecture](docs/ARCHITECTURE.md)
- [Implementation Plan](docs/IMPLEMENTATION_PLAN.md)
