# Contributing to OpsConductor NMS

Thank you for your interest in contributing! This document provides guidelines for contributing to the project.

---

## Code of Conduct

Be respectful, inclusive, and professional in all interactions. We're building this together.

---

## How to Contribute

### Reporting Bugs

1. **Check existing issues**: Search [Issues](https://github.com/yourusername/opsconductor-nms/issues) to avoid duplicates
2. **Create a new issue** with:
   - **Clear title**: Describe the bug briefly
   - **Steps to reproduce**: Exact steps that trigger the bug
   - **Expected vs actual behavior**: What should happen vs what happens
   - **Environment details**: 
     - OS and version
     - Docker version
     - GPU model (if relevant)
     - Network configuration
   - **Relevant logs**: From `docker compose logs <service>`
   - **Screenshots** (if applicable)

**Example**:
```
Title: Port scanner fails on devices with filtered ports

Environment:
- Ubuntu 22.04
- Docker 24.0.7
- No GPU

Steps to reproduce:
1. Start all services
2. Wait for port-scanner to scan devices
3. Check logs: docker compose logs port-scanner

Expected: Scanner handles filtered ports gracefully
Actual: Scanner crashes with timeout error

Logs:
[paste relevant logs]
```

### Suggesting Features

1. **Search existing issues** for similar suggestions
2. **Create a new issue** with:
   - **Clear use case**: What problem does this solve?
   - **Proposed solution**: How would it work?
   - **Alternative approaches**: Other ways to solve it?
   - **Impact**: Who benefits? Breaking changes?

### Pull Requests

1. **Fork** the repository
2. **Create a branch** from `main`:
   ```bash
   git checkout -b feature/add-ipv6-support
   # or
   git checkout -b fix/port-scanner-timeout
   ```

3. **Make your changes**:
   - Follow existing code style (see below)
   - Add comments for complex logic
   - Update documentation if needed
   - Test your changes thoroughly

4. **Test your changes**:
   ```bash
   # Start all services
   docker compose up -d
   
   # Check logs for errors
   docker compose logs -f <your-service>
   
   # Verify functionality manually
   curl http://localhost:8080/health
   curl http://localhost:8080/api/inventory
   
   # Test edge cases
   ```

5. **Commit** with clear messages (see Commit Guidelines below)

6. **Push** to your fork:
   ```bash
   git push origin feature/add-ipv6-support
   ```

7. **Open a Pull Request** with:
   - **Description of changes**: What did you change and why?
   - **Related issue numbers**: Fixes #123
   - **Testing performed**: How did you verify it works?
   - **Screenshots/logs** (if relevant)
   - **Breaking changes** (if any)

---

## Development Guidelines

### Code Style

#### Python

- **Follow PEP 8** with minor exceptions
- **Use type hints** everywhere:
  ```python
  async def scan_port(ip: str, port: int, timeout: float = 2.0) -> tuple[bool, str | None]:
      pass
  ```
- **Keep functions focused**: One function = one responsibility
- **Use async/await** for I/O operations
- **Error handling**: Use try/except with specific exceptions
- **Logging**: Use Python logging module, not print()
  ```python
  import logging
  logger = logging.getLogger(__name__)
  logger.info(f"Scanning {ip}:{port}")
  ```

#### TypeScript/React

- **Use functional components** with hooks (no class components)
- **Prefer TypeScript strict mode**
- **Use meaningful variable names**: `deviceList` not `dl`
- **Keep components small**: <200 lines ideally
- **Extract reusable logic**: Custom hooks for shared state
- **Type everything**: Avoid `any` types

#### General

- **Comments**: Explain WHY, not WHAT
  ```python
  # Good
  # Use asyncio.gather to scan ports in parallel, reducing total scan time
  results = await asyncio.gather(*tasks)
  
  # Bad
  # Gather tasks
  results = await asyncio.gather(*tasks)
  ```
- **Naming**:
  - Functions: `verb_noun` (e.g., `scan_port`, `update_inventory`)
  - Classes: `PascalCase` (e.g., `PortScanner`, `IpInventory`)
  - Constants: `UPPER_CASE` (e.g., `DEFAULT_TIMEOUT`, `MAX_RETRIES`)
  - Variables: `snake_case` (e.g., `device_list`, `scan_results`)

### Commit Messages

Use **conventional commits** format:

```
<type>(<scope>): <description>

[optional body]

[optional footer]
```

**Types**:
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation changes
- `style`: Code style changes (formatting, no logic change)
- `refactor`: Code refactoring
- `perf`: Performance improvements
- `test`: Adding or updating tests
- `chore`: Maintenance tasks (dependencies, build, etc.)

**Examples**:

```bash
feat(port-scanner): add UDP scanning support

Implemented UDP scanning using asyncio DatagramProtocol.
Supports SNMP discovery on port 161/udp.

Fixes #45
```

```bash
fix(snmp-discovery): handle timeout gracefully

Previously crashed on timeout, now logs warning and continues.
Added retry logic with exponential backoff.

Fixes #67
```

```bash
docs(readme): update installation instructions

Added note about network interface configuration.
Clarified GPU requirements.
```

### Project Structure

Respect the existing directory structure:

```
services/
  <service-name>/
    app/
      main.py          # Entry point (FastAPI app or async main())
      config.py        # Configuration (optional)
      schemas.py       # Pydantic models (if using FastAPI)
    Dockerfile
    requirements.txt
    .dockerignore

ui/
  src/
    components/        # Reusable components
    App.tsx            # Main component
    main.tsx           # Entry point
```

### Adding New Services

If you're adding a new microservice:

1. **Create service directory** under `services/`
   ```bash
   mkdir -p services/my-new-service/app
   ```

2. **Create required files**:
   ```
   services/my-new-service/
   ├── app/
   │   └── main.py
   ├── Dockerfile
   ├── requirements.txt
   └── .dockerignore
   ```

3. **Implement health check endpoint**:
   ```python
   from aiohttp import web
   
   async def health(request):
       return web.json_response({"status": "ok"})
   
   app = web.Application()
   app.router.add_get('/health', health)
   ```

4. **Update `docker-compose.yml`**:
   ```yaml
   my-new-service:
     build:
       context: ./services/my-new-service
       dockerfile: Dockerfile
     environment:
       - STATE_SERVER_URL=http://state-server:8080
       - HEALTH_PORT=9700
     ports:
       - "9700:9700"
     depends_on:
       state-server:
         condition: service_started
     restart: unless-stopped
   ```

5. **Update documentation**:
   - Add to README.md (user-facing)
   - Add to repo.md (technical details)
   - Update this file if needed

6. **Test thoroughly**:
   ```bash
   docker compose build my-new-service
   docker compose up -d my-new-service
   docker compose logs -f my-new-service
   curl http://localhost:9700/health
   ```

### Testing

**Current State**: No automated tests (contributions welcome!)

**Manual Testing Checklist**:

- [ ] Services start without errors
- [ ] Health endpoints respond (`:9100-9600/health`)
- [ ] API endpoints return expected data
- [ ] WebSocket connections work
- [ ] UI renders correctly
- [ ] Logs show no unexpected errors
- [ ] Memory usage is reasonable
- [ ] No resource leaks (run for 30+ minutes)

**Future**: We need contributors to help add:
- Unit tests (pytest for Python)
- Integration tests (test service interactions)
- E2E tests (test full discovery pipeline)
- UI tests (React Testing Library)

---

## Priority Areas for Contribution

### Critical (P0)

**High-impact improvements needed now**:

1. **Authentication System**
   - Add JWT-based authentication
   - Protect all API endpoints
   - User management (create/delete users)
   - File: `services/state-server/app/auth.py` (new)

2. **Automated Testing**
   - Unit tests for each service
   - Integration tests for API
   - CI/CD pipeline (GitHub Actions)
   - File: `tests/` (new directory)

3. **Export Functionality**
   - Export inventory to CSV
   - Export inventory to JSON
   - Export MIB assignments
   - File: `services/state-server/app/export.py` (new)

### High Priority (P1)

**Important features for production use**:

4. **Error Recovery**
   - Retry logic for failed API calls
   - Exponential backoff for SNMP failures
   - Dead letter queue for failed patches

5. **Monitoring & Metrics**
   - Prometheus metrics endpoints
   - Grafana dashboards
   - Service health indicators
   - Resource usage tracking

6. **Advanced Filtering in UI**
   - Search by IP range
   - Filter by multiple criteria
   - Save filter presets
   - Export filtered results

7. **Device Grouping**
   - Group devices by subnet
   - Group by device type
   - Group by vendor
   - Custom tags

### Medium Priority (P2)

**Nice-to-have enhancements**:

8. **IPv6 Support**
   - Full IPv6 discovery
   - IPv6 SNMP queries
   - Dual-stack handling

9. **Multi-Network Support**
   - Scan multiple subnets
   - Cross-network topology
   - VLAN awareness

10. **Historical Tracking**
    - Track device status changes
    - Port changes over time
    - SNMP data history
    - Topology evolution

11. **Alerting System**
    - Alert on new devices
    - Alert on device down
    - Alert on configuration changes
    - Email/Slack notifications

12. **Configuration Backup**
    - Backup device configs via SNMP
    - Track config changes
    - Restore previous configs

### Low Priority (P3)

**Future enhancements**:

13. **Advanced Visualization**
    - Topology graph visualization
    - Network map with geographic layout
    - Interactive dashboards

14. **Additional LLM Models**
    - Support for Llama, Claude, GPT-4
    - Model comparison
    - Fine-tuned models

15. **Performance Optimizations**
    - Batch SNMP queries
    - Parallel scanning optimizations
    - Database query optimization

---

## Specific Contribution Opportunities

### Good First Issues

**Easy tasks for new contributors**:

- [ ] Add more SNMP community strings support
- [ ] Improve error messages in UI
- [ ] Add tooltips to UI components
- [ ] Document additional MIB sources
- [ ] Add more port service mappings
- [ ] Improve logging messages
- [ ] Add configuration validation

### Help Wanted

**Harder tasks that need expertise**:

- [ ] Implement JWT authentication
- [ ] Add Prometheus metrics
- [ ] Create Grafana dashboards
- [ ] Implement CSV/JSON export
- [ ] Add automated tests
- [ ] Optimize database queries
- [ ] Add TLS/SSL support

---

## Development Workflow

### Local Development

#### Backend Service

```bash
# Example: Developing port-scanner locally

cd services/port-scanner

# Create virtual environment
python -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run locally (requires state-server running)
export STATE_SERVER_URL=http://localhost:8080
export HEALTH_PORT=9200
python app/main.py

# Test changes
curl http://localhost:9200/health
```

#### Frontend

```bash
cd ui

# Install dependencies
npm install

# Run dev server
npm run dev

# Access at http://localhost:5173
```

### Docker Development

```bash
# Build single service
docker compose build port-scanner

# Start with logs
docker compose up port-scanner

# Rebuild and restart
docker compose up -d --build port-scanner

# View logs
docker compose logs -f port-scanner
```

---

## Code Review Process

When reviewing PRs, we check:

1. **Functionality**: Does it work as intended?
2. **Code quality**: Is it readable and maintainable?
3. **Testing**: Has it been tested manually?
4. **Documentation**: Are docs updated?
5. **Security**: Are there security implications?
6. **Performance**: Does it impact performance?
7. **Breaking changes**: Does it break existing functionality?

**Review timeline**: We aim to review within 3-5 days.

---

## Questions?

- **Open a Discussion**: [GitHub Discussions](https://github.com/yourusername/opsconductor-nms/discussions)
- **Ask in an issue**: Tag with `question` label
- **Check existing issues**: Someone may have asked already

---

## Recognition

Contributors will be:
- Listed in CONTRIBUTORS.md (coming soon)
- Mentioned in release notes
- Credited in commit messages

---

## License

By contributing, you agree that your contributions will be licensed under the MIT License.

---

**Thank you for contributing to OpsConductor NMS!** 🎉
