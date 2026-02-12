# Architecture

## Stack

- **Runtime**: Python 3.12, FastAPI (ASGI), uvicorn
- **Database**: PostgreSQL 17, SQLAlchemy 2.0 (async via asyncpg)
- **Migrations**: Alembic (async)
- **Validation**: Pydantic v2
- **Auth**: JWT (python-jose HS256) + API Keys (SHA-256 hashed)
- **Background tasks**: Procrastinate (PostgreSQL-based queue)
- **Config generation**: Jinja2 templates for BIRD 2.x
- **Metrics**: prometheus-client
- **Logging**: structlog (JSON in production, console in debug)

## Layer Architecture

```
HTTP Request
    |
    v
+-----------------------+
|   API Layer           |  api/v1/*.py - FastAPI routers
|   (validation, auth)  |  api/deps.py - dependency injection
+-----------------------+
    |
    v
+-----------------------+
|   Service Layer       |  services/*.py - business logic
|   (business rules)    |  services/config_generation.py
+-----------------------+
    |
    v
+-----------------------+
|   Model Layer         |  models/*.py - SQLAlchemy ORM
|   (persistence)       |  schemas/*.py - Pydantic schemas
+-----------------------+
    |
    v
+-----------------------+
|   PostgreSQL 17       |  Native types: UUID, JSONB, ARRAY
+-----------------------+
```

## Project Layout

```
src/ixforge/
  main.py              Application factory, middleware, exception handlers
  config.py            Pydantic Settings (IXFORGE_* env vars)
  cli.py               CLI entrypoint (run, worker, upgrade, seed, backup, restore)
  exceptions.py        Exception hierarchy -> HTTP status codes
  metrics.py           Prometheus counters, histograms, gauges
  models/
    base.py            UUIDPrimaryKey, TimestampMixin, TenantMixin, ExtraDataMixin
    ixp.py             IXP (top-level tenant)
    member.py          Member (state machine)
    connection.py      Connection + ConnectionVLAN (state machine)
    switch.py          Switch (encrypted SNMP)
    port.py            Port (assignable to member)
    vlan.py            VLAN
    ip.py              IPPool + IPAssignment
    route_server.py    RouteServer
    bgp_session.py     BGPSession
    config.py          ConfigVersion (BIRD config snapshots)
    event.py           Event (audit log)
    contact.py         Contact
    user.py            User (admin/member roles)
    api_key.py         APIKey (scoped, hashed)
    custom_field.py    CustomFieldDefinition
  schemas/             Pydantic request/response models (1:1 with models)
  services/
    auth.py            Password hashing, JWT, API key generation
    base.py            Cursor-based keyset pagination
    members.py         Member CRUD + state machine
    connections.py     Connection CRUD + state machine + VLAN/IP ops
    switches.py        Switch CRUD + Fernet SNMP encryption
    ports.py           Port CRUD + assign/release
    vlans.py           VLAN CRUD
    ipam.py            IP pool management, sequential/manual allocation
    route_servers.py   Route server CRUD
    bgp_sessions.py    BGP session read/update
    config_generation.py  BIRD config rendering + diff
    ixf_export.py      IX-F Member Export JSON v1.0
    events.py          Audit event create/list
    custom_fields.py   Custom field definitions + validation
    monitoring.py      Build monitoring targets for collector agent
    templates/bird/    Jinja2 templates (bird_v4.conf.j2, bird_v6.conf.j2, ...)
  api/
    deps.py            FastAPI dependencies (DB session, auth, tenant resolution)
    v1/router.py       Router aggregator (18 routers)
    v1/*.py            Endpoint modules
  tasks/
    setup.py           Procrastinate app configuration
    config.py          Config generation tasks (queue: config)
    maintenance.py     Cleanup tasks (queue: maintenance)
  database.py          Async engine + session factory
tests/
  conftest.py          Fixtures (db, client, auth, IXP seed)
  factories.py         Factory Boy factories (17 models)
  test_auth.py         Auth + RBAC tests
  test_members.py      Member CRUD + state machine tests
  test_ipam.py         IP pool + allocation tests
```

## Key Patterns

### Multi-Tenant Prep

All domain models include `ixp_id` via `TenantMixin`. The current MVP operates in single-tenant mode (resolves the first IXP in the database). Multi-tenant routing can be added later without schema changes.

### State Machines

**Member**: `prospect` -> `provisioning` -> `active` <-> `suspended` -> `terminated`
**Connection**: `draft` -> `provisioning` -> `active` <-> `disabled` -> `decommissioned`

Transitions are validated in the service layer. The `provisioning -> active` transition requires a complete setup (port + VLAN + IP assigned). All state changes emit audit events.

### IPAM

IP pools are CIDR-scoped and attached to VLANs. Allocation supports:
- **Sequential**: next available host address, skipping network/broadcast/gateway
- **Manual**: specific address with validation

All addresses are globally unique across pools.

### BIRD Config Generation

Jinja2 templates render separate IPv4 and IPv6 BIRD 2.x configs per route server. Each generated config includes:
- SHA-256 content hash (for change detection by agents)
- Template snapshot (for reproducibility)
- Unified diffs between versions

Only active BGP sessions on active connections for active members are included.

### Agent Communication

Route server agents authenticate with scoped API keys (`agent:route_server`). The polling flow:

1. **Config poll** (`GET .../agent/config`): agent compares hash, downloads if changed
2. **Status report** (`POST .../agent/status`): agent pushes BGP session operational states
3. **Heartbeat** (`POST .../agent/heartbeat`): agent reports health, server checks config sync and version

### Background Tasks

Procrastinate uses PostgreSQL as the task queue (no Redis needed). Two queues:
- **config**: triggered on state changes, regenerates BIRD configs for affected route servers
- **maintenance**: periodic cleanup of old events and config versions

### Custom Fields

Entities with `ExtraDataMixin` store arbitrary data in a JSONB `extra_data` column. `CustomFieldDefinition` records define the expected schema per entity type, enforced at the service layer with type validation (string, integer, boolean, URL, email).
