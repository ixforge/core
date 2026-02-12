# Quickstart

## Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) package manager
- PostgreSQL 17 (or Docker)

## Local Development

```bash
# Clone and install
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

## Configuration

All settings use the `IXFORGE_` prefix. Core variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `IXFORGE_DATABASE_URL` | `postgresql+asyncpg://ixforge:ixforge@localhost:5432/ixforge` | Database connection |
| `IXFORGE_SECRET_KEY` | `change-me-...` | JWT signing & SNMP encryption key |
| `IXFORGE_DEBUG` | `false` | Enables reload and verbose logging |
| `IXFORGE_CORS_ORIGINS` | `["*"]` | Allowed CORS origins |
| `IXFORGE_RATE_LIMIT_PER_MINUTE` | `60` | Rate limit for public endpoints |

## Docker (Production)

```bash
cd docker

# Edit environment
cp .env .env.local
vi .env.local  # Set IXFORGE_SECRET_KEY and POSTGRES_PASSWORD

# Start the stack
docker compose --env-file .env.local up -d

# Run migrations
docker compose exec core uv run ixforge upgrade

# Create admin user
docker compose exec -e IXFORGE_ADMIN_EMAIL=admin@example.com \
  -e IXFORGE_ADMIN_PASSWORD=changeme \
  core uv run ixforge createsuperuser
```

Services:

| Service | Description | Port |
|---------|-------------|------|
| `core` | FastAPI server | 8000 |
| `worker` | Procrastinate background tasks | - |
| `postgres` | PostgreSQL 17 | internal |

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
ixforge upgrade          Run database migrations (alembic upgrade head)
ixforge createsuperuser  Create an admin user
ixforge seed             Seed demo data (idempotent)
ixforge backup           Create compressed database backup (.sql.gz)
ixforge restore <file>   Restore from backup archive
```

## Authentication

Two methods are supported:

```bash
# 1. JWT Bearer token
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@example.com","password":"changeme"}' | jq -r .access_token)

curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/v1/members

# 2. API Key (created via admin endpoint)
curl -H "X-API-Key: ixf_abc123..." http://localhost:8000/api/v1/members
```
