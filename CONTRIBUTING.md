# Contributing to OpsConductor NMS

Thank you for your interest in contributing! This document provides guidelines for contributing to the project.

## Code of Conduct

Be respectful, inclusive, and professional in all interactions.

## How to Contribute

### Reporting Bugs

1. Check if the bug has already been reported in [Issues](https://github.com/yourusername/opsconductor-nms/issues)
2. If not, create a new issue with:
   - Clear, descriptive title
   - Steps to reproduce
   - Expected vs actual behavior
   - Environment details (OS, Docker version, GPU model)
   - Relevant logs

### Suggesting Features

1. Search existing [Issues](https://github.com/yourusername/opsconductor-nms/issues) for similar suggestions
2. Create a new issue with:
   - Clear use case description
   - Proposed solution (if any)
   - Alternative approaches considered
   - Impact on existing functionality

### Pull Requests

1. **Fork** the repository
2. **Create a branch** from `main`:
   ```bash
   git checkout -b feature/your-feature-name
   ```
3. **Make your changes**:
   - Follow existing code style
   - Add comments for complex logic
   - Update documentation if needed
4. **Test your changes**:
   - Ensure all services start correctly
   - Test functionality manually
   - Add tests if applicable
5. **Commit** with clear messages:
   ```bash
   git commit -m "Add feature: description of what you did"
   ```
6. **Push** to your fork:
   ```bash
   git push origin feature/your-feature-name
   ```
7. **Open a Pull Request** with:
   - Description of changes
   - Related issue numbers
   - Testing performed
   - Screenshots/logs if relevant

## Development Guidelines

### Code Style

**Python**:
- Follow PEP 8
- Use type hints
- Keep functions focused and small
- Use async/await for I/O operations

**TypeScript/React**:
- Use functional components with hooks
- Prefer TypeScript strict mode
- Use meaningful variable names
- Keep components small and focused

### Commit Messages

Use conventional commits format:

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
- `test`: Adding or updating tests
- `chore`: Maintenance tasks

**Examples**:
```
feat(analyst): add retry logic for failed LLM calls
fix(ui): correct WebSocket reconnection behavior
docs(readme): update installation instructions
```

### Project Structure

Respect the existing directory structure:

```
services/
  llm-analyst/     # LLM evidence processing
  state-server/    # Graph database & API
  packet-collector/ # (to be implemented)
ui/                # React frontend
schemas/           # JSON schemas
prompts/           # LLM prompts
```

### Adding New Services

1. Create service directory under `services/`
2. Include:
   - `Dockerfile`
   - `requirements.txt` or `package.json`
   - `app/` directory with main logic
   - README in service directory
3. Update `docker-compose.yml`
4. Update main README.md

### Modifying Schemas

1. Update `schemas/topology_patch.schema.json`
2. Test with: `python -c "import json; json.load(open('schemas/topology_patch.schema.json'))"`
3. Update Pydantic models in affected services
4. Update documentation
5. Test end-to-end data flow

### Testing

**Manual Testing Checklist**:
- [ ] Services start without errors
- [ ] Health endpoints respond
- [ ] API endpoints return expected data
- [ ] WebSocket connections work
- [ ] UI renders correctly
- [ ] Logs show no unexpected errors

**Future**: Add automated tests (unit, integration, e2e)

## Priority Areas for Contribution

### Critical (P0)
- **Packet Collector Service**: The missing piece that makes the system functional
- **Test Data Generator**: Synthetic packet data for testing
- **System Initialization**: Bootstrap script for graph seeding

### High Priority (P1)
- Error recovery & retry logic
- Health checks for all services
- Basic test suite
- API documentation (OpenAPI/Swagger)

### Medium Priority (P2)
- Authentication & authorization
- Prometheus metrics
- Graph history & time-travel
- UI enhancements (filtering, search)

### Low Priority (P3)
- Additional LLM model support
- Export formats (GraphML, GEXF)
- Advanced visualization options
- Performance optimizations

## Questions?

- Open a [Discussion](https://github.com/yourusername/opsconductor-nms/discussions)
- Check existing [Issues](https://github.com/yourusername/opsconductor-nms/issues)

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
