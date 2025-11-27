# OpsConductor Network Management System

A simplified network discovery and management system for monitoring network infrastructure.

## Overview

OpsConductor NMS provides basic network discovery capabilities including:
- Router discovery via SNMP
- Network topology mapping
- Basic inventory management
- RESTful API for network data

## Architecture

The system consists of three main components:

### 1. Network Discovery Service
- **Port**: 8000
- **Technology**: Python with FastAPI
- **Database**: PostgreSQL
- **Functionality**: SNMP-based router discovery, topology mapping

### 2. PostgreSQL Database
- **Port**: 5433 (mapped from host)
- **Purpose**: Persistent storage for network topology data
- **Schema**: Routers, interfaces, network links

### 3. Web UI
- **Port**: 3000
- **Technology**: React + TypeScript
- **Functionality**: Network inventory display, basic topology information

## Quick Start

### Prerequisites
- Docker and Docker Compose
- Network access to target devices (SNMP)

### Installation

1. Clone the repository:
```bash
git clone <repository-url>
cd opsconductor-nms
```

2. Start the services:
```bash
docker compose up -d
```

3. Access the applications:
- Web UI: http://localhost:3000
- API: http://localhost:8000
- API Documentation: http://localhost:8000/docs

### Initial Configuration

1. **Database Setup**: The database initializes automatically on first start
2. **Network Discovery**: Configure target networks in the UI or via API
3. **SNMP Settings**: Ensure SNMP is accessible on target devices

## API Endpoints

### Network Discovery
- `GET /api/v1/routers` - List discovered routers
- `POST /api/v1/discover` - Trigger network discovery
- `GET /api/v1/network-links` - Get network topology links

### Health Checks
- `GET /health` - Service health status
- `GET /api/v1/status` - Discovery service status

## Configuration

### Environment Variables

Create a `.env` file based on `.env.example`:

```bash
# Database Configuration
DATABASE_URL=postgresql://opsconductor:opsconductor@postgres:5432/opsconductor

# Network Discovery
DISCOVERY_NETWORKS=10.120.0.0/24,192.168.1.0/24
SNMP_COMMUNITY=public
SNMP_TIMEOUT=5

# API Configuration
API_HOST=0.0.0.0
API_PORT=8000
LOG_LEVEL=INFO
```

### Docker Compose Override

Use `docker-compose.override.yml` for local development overrides:

```yaml
services:
  network-discovery:
    volumes:
      - ./services/network-discovery-simplified:/app
    environment:
      - LOG_LEVEL=DEBUG
```

## Development

### Project Structure
```
opsconductor-nms/
├── services/
│   ├── init-db/                 # Database initialization
│   └── network-discovery-simplified/  # Discovery API service
├── ui/                          # React web interface
├── docker-compose.yml           # Service orchestration
└── README.md                    # This file
```

### Local Development

1. **Backend Development**:
```bash
cd services/network-discovery-simplified
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
python -m app.main
```

2. **Frontend Development**:
```bash
cd ui
npm install
npm run dev
```

### Database Management

- **Connect**: `psql -h localhost -p 5433 -U opsconductor -d opsconductor`
- **Password**: `opsconductor`
- **Schema**: Auto-created on service start

## Troubleshooting

### Common Issues

1. **Services Won't Start**:
   - Check port conflicts (3000, 8000, 5433)
   - Verify Docker is running
   - Check logs: `docker compose logs`

2. **Network Discovery Fails**:
   - Verify SNMP access to target devices
   - Check network connectivity
   - Review SNMP community strings

3. **Database Connection Issues**:
   - Wait for PostgreSQL to fully start
   - Check database logs: `docker compose logs postgres`
   - Verify environment variables

### Logs

View service logs:
```bash
# All services
docker compose logs

# Specific service
docker compose logs network-discovery
docker compose logs ui
docker compose logs postgres
```

## Production Deployment

### Security Considerations
- Change default passwords
- Use SNMPv3 instead of SNMPv2c
- Configure firewall rules
- Enable HTTPS for API

### Scaling
- Use external PostgreSQL for production
- Configure load balancer for UI
- Set up monitoring and alerting

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make changes
4. Test thoroughly
5. Submit a pull request

## License

[License information]

## Support

For support and questions:
- Create an issue in the repository
- Check the API documentation at http://localhost:8000/docs
- Review service logs for debugging information
