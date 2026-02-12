# IXForge Core

Modular IXP management platform.

## Quick Start

```bash
# Install dependencies
cd core
uv sync

# Start PostgreSQL (dev instance on port 5432)
docker compose -f docker/docker-compose.dev.yml up -d

# Run migrations
uv run ixforge upgrade

# Create admin user
uv run ixforge createsuperuser

# Seed demo data (optional)
uv run ixforge seed

# Start API server (with hot reload)
IXFORGE_DEBUG=true uv run ixforge run
```

The API is available at `http://localhost:8000/api/v1/docs` (Swagger UI).

## Documentation

- [Quickstart Guide](docs/quickstart.md) - Installation, configuration, Docker
- [API Reference](docs/api.md) - Endpoints, auth, pagination
- [Architecture](docs/architecture.md) - Layers, patterns, conventions

## Running Tests

```bash
# Start test database (port 5433, ephemeral tmpfs)
docker compose -f docker/docker-compose.testing.yml up -d

# Run tests
uv run pytest -v

# With coverage
uv run pytest --cov=ixforge --cov-report=term-missing
```

## CLI Commands

```
ixforge run              Start API server
ixforge worker           Start background task workers
ixforge upgrade          Run database migrations
ixforge createsuperuser  Create an admin user
ixforge seed             Seed demo data (idempotent)
ixforge backup           Create compressed database backup
ixforge restore <file>   Restore from backup archive
```

## License

Apache 2.0
