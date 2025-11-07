# Contributing to OpsConductor NMS

## Development Setup

### Prerequisites

- Docker & Docker Compose
- Git
- Node.js 20+ (for local UI development)
- Python 3.11+ (for local API development)

### Quick Start

```bash
# Clone the repository
git clone https://github.com/andrewcho-dev/opsconductor-nms.git
cd opsconductor-nms

# Start all services
docker compose up -d

# View logs
docker compose logs -f
```

## Project Structure

```
opsconductor-nms/
├── docs/                   # Architecture and planning docs
├── inventory/              # SuzieQ device inventory
├── services/
│   ├── api/               # FastAPI backend
│   │   ├── migrations/    # Database migrations
│   │   └── routers/       # API route handlers
│   ├── topo-normalizer/   # Topology computation service
│   └── ui/                # React frontend
├── docker-compose.yml     # Service orchestration
└── Makefile              # Common commands
```

## Development Workflow

### Backend (API)

```bash
# Local development
cd services/api
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Set environment
export PG_DSN=postgresql://oc:oc@localhost:5432/opsconductor

# Run migrations
python migrate.py

# Start API
uvicorn main:app --reload --port 8088
```

### Frontend (UI)

```bash
# Local development
cd services/ui
npm install
npm run dev

# Build for production
npm run build
```

### Database Changes

1. Create new migration file: `services/api/migrations/XXXX_description.sql`
2. Follow naming convention: `0001_`, `0002_`, etc.
3. Make migrations idempotent using `IF NOT EXISTS`
4. Test migration: `docker compose restart api`

### Adding New Endpoints

1. Create route in `services/api/routers/`
2. Add router to `main.py`
3. Update OpenAPI docs
4. Test with `/docs` endpoint

## Code Standards

### Python

- Follow PEP 8
- Use type hints
- Add docstrings for public functions
- Use async/await for I/O operations

### JavaScript/React

- Use functional components with hooks
- Keep components small and focused
- Use CSS modules or styled-components
- Follow existing naming conventions

### SQL

- Use lowercase for keywords
- Indent for readability
- Add comments for complex queries
- Always include indexes for foreign keys

## Testing

### Manual Testing

```bash
# Test API endpoints
curl http://localhost:8088/healthz
curl http://localhost:8088/topology/nodes
curl http://localhost:8088/topology/edges

# Test UI
open http://localhost:8089
```

### Adding Tests (TODO)

```bash
# Backend tests
pytest services/api/tests/

# Frontend tests
cd services/ui
npm test
```

## Common Tasks

### Adding a New Fact Type

1. Add table in migration: `facts_<protocol>`
2. Add processing in normalizer: `process_<protocol>_facts()`
3. Add edge computation: `compute_edges_from_<protocol>()`
4. Update confidence scoring if needed

### Adding a New API Endpoint

1. Define Pydantic models in router file
2. Create endpoint function with type hints
3. Query database using `db_pool`
4. Return response model
5. Test with `/docs`

### Updating the UI

1. Create component in `services/ui/src/components/`
2. Import and use in `App.jsx`
3. Add styles in component CSS file
4. Test with `npm run dev`

## Docker Commands

```bash
# Rebuild specific service
docker compose build api

# Restart service
docker compose restart api

# View service logs
docker compose logs -f api

# Execute command in container
docker compose exec api python migrate.py

# Clean everything
docker compose down -v
```

## Debugging

### API Issues

```bash
# Check API logs
docker compose logs api

# Connect to database
docker compose exec db psql -U oc opsconductor

# Check migrations
docker compose exec db psql -U oc opsconductor -c "SELECT * FROM schema_migrations"
```

### Normalizer Issues

```bash
# Check normalizer logs
docker compose logs topo-normalizer

# Test SuzieQ connectivity
docker compose exec topo-normalizer curl http://suzieq:8000/api/v1/device
```

### UI Issues

```bash
# Check build errors
docker compose logs ui

# Rebuild UI
docker compose build ui
docker compose up -d ui
```

## Performance Tips

- Use connection pooling (already configured)
- Add indexes for frequently queried columns
- Use materialized views for expensive queries
- Limit polling frequency in normalizer
- Use React.memo for expensive components

## Security Considerations

Before deploying to production:

1. Enable authentication (add middleware)
2. Use Docker secrets for credentials
3. Enable HTTPS/TLS
4. Add rate limiting
5. Sanitize all inputs
6. Enable CORS restrictions
7. Add audit logging

## Getting Help

- Review `docs/ARCHITECTURE.md`
- Check `docs/IMPLEMENTATION_PLAN.md`
- Read `STATUS.md` for current progress
- Check existing issues on GitHub

## Submitting Changes

1. Create a feature branch
2. Make your changes
3. Test locally
4. Update documentation
5. Submit pull request
6. Address review comments
