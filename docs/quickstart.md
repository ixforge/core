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
| `IXFORGE_CORS_ORIGINS` | `[]` (debug: `["*"]`) | Allowed CORS origins |
| `IXFORGE_RATE_LIMIT_PER_MINUTE` | `60` | Rate limit for public endpoints |
| `IXFORGE_UI_SECURE_COOKIES` | `true` | Session cookies require HTTPS; set `false` when serving the portal over plain HTTP on a trusted internal network |

## Docker (Production)

```bash
cd docker

# Create the environment file (compose reads it as env_file and for interpolation)
cat > .env <<'EOF'
POSTGRES_USER=ixforge
POSTGRES_PASSWORD=change-me
POSTGRES_DB=ixforge
IXFORGE_DATABASE_URL=postgresql+asyncpg://ixforge:change-me@postgres:5432/ixforge
IXFORGE_SECRET_KEY=change-me-to-a-random-string-at-least-32-chars
IXFORGE_DEBUG=false
# Portal served over plain HTTP on a trusted internal network? uncomment:
# IXFORGE_UI_SECURE_COOKIES=false
EOF
vi .env  # set real secrets; keep POSTGRES_PASSWORD and IXFORGE_DATABASE_URL in sync

# Start the stack
docker compose up -d

# Run migrations (also applies the procrastinate schema)
docker compose exec core uv run ixforge upgrade
```

Then open `http://<host>:8001/setup` (or `POST /api/v1/setup`) to create the
IXP and the admin user. The setup also installs the default BIRD templates —
`createsuperuser` alone does not create an IXP.

Services:

| Service | Description | Port |
|---------|-------------|------|
| `core` | FastAPI server | 8000 |
| `portal` | Admin + member web UI | 8001 |
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
ixforge ui               Start admin portal (port 8001)
ixforge worker           Start background task workers
ixforge upgrade          Run database migrations (alembic upgrade head)
ixforge createsuperuser  Create an admin user
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
