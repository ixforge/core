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
docker compose -f docker/docker-compose.dev.yml up -d postgres

# Run migrations
uv run ixforge upgrade

# Start API server (with hot reload)
IXFORGE_DEBUG=true uv run ixforge run
```

The API is available at `http://localhost:8000/api/v1/docs` (Swagger UI).

On an empty database, create the IXP and the admin user via the setup endpoint
(or the portal at `/setup`); `createsuperuser` alone does not create an IXP:

```bash
curl -X POST http://localhost:8000/api/v1/setup \
  -H 'Content-Type: application/json' \
  -d '{
    "ixp": {"name":"Example IX","short_name":"EXIX","asn":65000,"country":"CL","city":"Santiago"},
    "admin": {"full_name":"Admin","email":"admin@example.com","password":"changeme123"}
  }'
```

Notes:

- Background config regeneration (e.g. when a member is activated) runs on a
  worker; start one with `uv run ixforge worker` or the route servers never get
  new configs.
- The dev compose can also run the full stack (`core` on 8000, `portal` on 8001,
  `postgres`) with `docker compose -f docker/docker-compose.dev.yml up -d`. In
  that mode run migrations with `docker compose exec core uv run ixforge upgrade`
  and skip the local `ixforge run`.

## Configuration

All settings use the `IXFORGE_` prefix. Core variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `IXFORGE_DATABASE_URL` | `postgresql+asyncpg://ixforge:ixforge@localhost:5432/ixforge` | Database connection |
| `IXFORGE_SECRET_KEY` | `change-me-...` | JWT signing & SNMP encryption key |
| `IXFORGE_DEBUG` | `false` | Enables reload and verbose logging |
| `IXFORGE_CORS_ORIGINS` | `[]` (debug: localhost:3000/8001) | Allowed CORS origins |
| `IXFORGE_RATE_LIMIT_PER_MINUTE` | `60` | Rate limit for public endpoints |
| `IXFORGE_UI_SECURE_COOKIES` | `true` | Session cookies require HTTPS; set `false` when serving the portal over plain HTTP on a trusted internal network |
| `IXFORGE_UI_PORT` | `8001` | Port for the `ixforge ui` portal |
| `IXFORGE_CORE_URL` | `http://localhost:8000` | Core API URL the portal calls |
| `IXFORGE_MEDIA_ROOT` | `./media` | Directory for uploaded files (member logos) |
| `IXFORGE_MEDIA_URL` | `/media` | URL prefix for uploaded files |

Feature modules are toggled with `IXFORGE_MODULE_*` (booleans). Defaults: only
`ixf_export` is on; `ui`, `switching`, `rpki`, `peeringdb_sync` are off.

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
ixforge createsuperuser  Create an additional admin (the IXP and first admin are created via /setup)
ixforge backup           Create compressed database backup (.sql.gz)
ixforge restore <file>   Restore from backup archive
```

## Web Portal

`ixforge ui` (the `portal` service in the production compose) serves two
server-rendered UIs on port 8001:

- **Admin portal** at `/admin` — full management of members, trunks,
  connections, switches, VLANs, IPAM, route servers, BIRD templates (with live
  preview), BGP sessions, users, API keys and the audit log
- **Member portal** at `/portal` — read-only view for `member`-role users of
  their own trunks, BGP sessions, profile and contacts

First-run setup is at `/setup`. The portal consumes the REST API over
`IXFORGE_CORE_URL`.

## Backups

`ixforge backup` shells out to `pg_dump` and writes a gzipped SQL dump; it needs
the Postgres client tools available (they ship in the `core` image). `restore`
reads such an archive back. For scheduled backups run it from cron on the host
against the postgres container, e.g.:

```bash
docker compose exec -T postgres pg_dump -U ixforge -d ixforge --no-owner | gzip > backup.sql.gz
```

Keep copies off the database host.

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
