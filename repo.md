# OpsConductor NMS Repository

## Repository Overview

This repository contains the OpsConductor Network Management System (NMS), a simplified network discovery and monitoring solution.

## Current State

The repository has been streamlined to focus on core network discovery functionality:

### Active Components
- **Network Discovery Service** (`services/network-discovery-simplified/`)
  - Python FastAPI-based service
  - SNMP network discovery
  - RESTful API endpoints
  - PostgreSQL integration

- **Web UI** (`ui/`)
  - React + TypeScript interface
  - Network inventory display
  - Basic topology information
  - No visualization components

- **Database** (`services/init-db/`)
  - PostgreSQL schema initialization
  - Network topology data storage

### Removed Components
The following have been removed to simplify the codebase:
- All visualization libraries (Cytoscape, D3, vis-network)
- Complex topology orchestration services
- Multiple discovery engines (LLM-based, packet collection, etc.)
- Advanced routing analysis components
- Documentation and schema files that don't reflect current state

## Project Structure

```
opsconductor-nms/
├── services/
│   ├── init-db/                     # Database initialization scripts
│   └── network-discovery-simplified/  # Main discovery service
├── ui/                              # React web interface
├── docker-compose.yml               # Service orchestration
├── docker-compose.override.yml      # Development overrides
├── .env.example                      # Environment configuration template
└── README.md                         # Main documentation
```

## Technology Stack

### Backend
- **Python 3.11+** with FastAPI
- **PostgreSQL** for data persistence
- **SNMP** for network device discovery
- **Docker** for containerization

### Frontend
- **React 18** with TypeScript
- **Vite** for build tooling
- **Basic HTML/CSS** (no visualization libraries)

### Infrastructure
- **Docker Compose** for orchestration
- **PostgreSQL** database
- **RESTful API** architecture

## API Documentation

The service provides a comprehensive REST API:

### Core Endpoints
- `GET /api/v1/routers` - List discovered routers
- `POST /api/v1/discover` - Trigger network discovery
- `GET /api/v1/network-links` - Get network topology data
- `GET /health` - Health check endpoint
- `GET /docs` - Interactive API documentation

### Data Models
- **Router**: Network device information (IP, hostname, vendor, etc.)
- **NetworkLink**: Connections between routers
- **Interface**: Network interface details

## Development Workflow

### Setup
1. Clone repository
2. Copy `.env.example` to `.env` and configure
3. Run `docker compose up -d`
4. Access services at localhost ports

### Local Development
- Backend: `cd services/network-discovery-simplified && python -m app.main`
- Frontend: `cd ui && npm run dev`
- Database: Available at localhost:5433

### Testing
- API tests via `/docs` endpoint
- Frontend tests via browser
- Integration tests via Docker Compose

## Configuration

### Environment Variables
Key configuration options:
- `DATABASE_URL` - PostgreSQL connection string
- `DISCOVERY_NETWORKS` - Networks to scan
- `SNMP_COMMUNITY` - SNMP community string
- `LOG_LEVEL` - Logging verbosity

### Docker Configuration
- `docker-compose.yml` - Production configuration
- `docker-compose.override.yml` - Development overrides
- Environment-specific settings via `.env` files

## Deployment

### Development
```bash
docker compose up -d
```

### Production
- Use external PostgreSQL
- Configure environment variables
- Set up reverse proxy
- Enable monitoring

## Current Limitations

The simplified version focuses on core functionality:
- No network topology visualization
- Basic SNMP discovery only
- Simple web interface
- No advanced analytics or reporting

## Future Enhancements

Potential areas for expansion:
- Add back visualization capabilities
- Enhanced discovery methods
- Real-time monitoring
- Alerting and notifications
- Advanced reporting

## Support

For current functionality:
- Check README.md for setup instructions
- Review API docs at http://localhost:8000/docs
- Examine service logs for troubleshooting
- Create issues for bugs or feature requests
