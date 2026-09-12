# Architecture

## Stack

- **Runtime**: Python 3.12, FastAPI (ASGI), uvicorn
- **Database**: PostgreSQL 17, SQLAlchemy 2.0 (async via asyncpg)
- **Migrations**: Alembic (async)
- **Validation**: Pydantic v2
- **Auth**: JWT (python-jose HS256) + API Keys (SHA-256 hashed)
- **Background tasks**: Procrastinate (PostgreSQL-based queue)
- **Config generation**: Jinja2 templates for BIRD 2.x (stored per-IXP in the database)
- **Admin/member UI**: Starlette + Jinja2 + Tailwind, server-side rendered, consumes the REST API
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
  main.py              Application factory, middleware, exception handlers, lifespan
                       (opens the procrastinate app so endpoints can defer tasks)
  config.py            Pydantic Settings (IXFORGE_* env vars)
  cli.py               CLI entrypoint (run, ui, worker, upgrade, createsuperuser, backup, restore)
  enums.py             Shared enumerations (states, types, policies)
  exceptions.py        Exception hierarchy -> HTTP status codes
  logging.py           structlog configuration
  metrics.py           Prometheus counters, histograms, gauges
  rate_limit.py        Rate limiting (slowapi)
  models/
    base.py            UUIDPrimaryKey, TimestampMixin, TenantMixin, ExtraDataMixin
    ixp.py             IXP (top-level tenant)
    member.py          Member (state machine)
    trunk.py           Trunk + TrunkVLAN (state machine, owns connections and VLANs)
    connection.py      Connection (physical/virtual switch port belonging to a Trunk, state machine)
    switch.py          Switch (encrypted SNMP)
    location.py        Location (site/datacenter)
    vlan.py            VLAN
    vlan_member.py     VLAN <-> Member assignment
    ip.py              IPPool + IPAssignment
    route_server.py    RouteServer
    route_server_vlan.py  RS <-> VLAN assignment
    rs_ip_assignment.py   RS IP assignments (IPAM)
    rs_template.py     RouteServerTemplate (BIRD templates per IXP, DB-stored)
    bgp_session.py     BGPSession
    config.py          ConfigVersion (BIRD config snapshots)
    event.py           Event (audit log)
    contact.py         Contact
    user.py            User (admin/member roles)
    api_key.py         APIKey (scoped, hashed; user-bound XOR route-server-bound)
    asn_cache.py       Cached ASN name lookups
    custom_field.py    CustomFieldDefinition
    types.py           Custom SQLAlchemy column types
  schemas/             Pydantic request/response schemas (mostly per resource, plus
                       cross-cutting ones: setup, monitoring, agent, common)
  services/            Business logic per resource (members, trunks, connections,
                       switches, vlans, ipam, route_servers, bgp_sessions, ...)
    config_generation.py  BIRD config rendering + combining + diff
    default_templates.py  Canonical default BIRD template set, installed at setup
    rs_templates.py    Template CRUD, reference checks, syntax validation, preview
    template_env.py    Sandboxed Jinja2 environment with DB-loaded templates
    template_filters.py   Custom filters (ipaddr, bird_str, prefixlist)
    setup.py           Initial IXP + admin creation (installs default templates)
    asn_lookup.py      ASN name resolution (local -> cache -> PeeringDB)
    monitoring.py      Build monitoring targets for the collector
  api/
    deps.py            FastAPI dependencies (DB session, auth, tenant resolution)
    v1/router.py       Router aggregator
    v1/*.py            Endpoint modules (incl. agent.py for RS agents,
                       rs_api_keys.py for agent key management)
  ui/
    app.py             Starlette app factory (admin portal + member portal)
    api_client.py      HTTP client against the REST API
    routes/            Server-rendered views (/admin/*, /portal/*, /login, /setup)
    templates/         Jinja2 templates (Tailwind)
  tasks/
    setup.py           Procrastinate app configuration
    config.py          Config regeneration tasks + defer helpers (queue: config)
    maintenance.py     Cleanup tasks (queue: maintenance)
  database.py          Async engine + session factory
tests/                 One test module per resource/feature (pytest, asyncio_mode auto),
                       conftest.py provides db/client/auth fixtures over the testing
                       postgres (port 5433, see docker/docker-compose.testing.yml)
```

## Key Patterns

### Multi-Tenant Prep

All domain models include `ixp_id` via `TenantMixin`. The current MVP operates in single-tenant mode (resolves the first IXP in the database). Multi-tenant routing can be added later without schema changes.

### State Machines

**Member**: `prospect` -> `provisioning` -> `active` <-> `suspended`; any of
`provisioning`, `active`, `suspended` can go to `terminated` (terminal).
**Trunk**: `draft` -> `provisioning` -> `active` <-> `disabled` -> `decommissioned`
**Connection**: `draft` -> `provisioning` -> `active` <-> `disabled` -> `decommissioned`

Transitions are validated in the service layer (each state maps to an explicit
set of allowed targets) and the order matters: a member cannot become `active`
without at least one active trunk, and a trunk needs its connection plus, for
each **production** VLAN it carries, at least one IP assignment before
activating. All state changes emit audit events.

### IPAM

IP pools are CIDR-scoped and attached to VLANs. Allocation supports:
- **Sequential**: next available host address, skipping network/broadcast
- **Manual**: specific address with validation

All addresses are globally unique across pools.

### BIRD Config Generation

Templates are Jinja2 documents stored per-IXP in the database
(`route_server_templates`), editable from the admin portal with syntax
validation and live preview. The default set lives in
`services/default_templates.py` and is installed when the IXP is created via
setup. Protected templates (`bird_v4.conf.j2`, `bird_v6.conf.j2`) cannot be
deleted.

The IPv4 and IPv6 sections are rendered separately and combined into a single
file for one dual-stack BIRD 2.x daemon: global directives (log, router id,
`protocol device`/`direct`, common functions) appear exactly once, controlled
by the `include_globals` template variable (see [templates.md](templates.md) for
the full mechanism and how to edit templates). Each generated config includes:
- SHA-256 content hash (for change detection by agents)
- Template snapshot (for reproducibility)
- Unified diffs between versions

Only admin-up BGP sessions on active trunks for active members are included.

### Agent Communication

Route server agents authenticate with API keys bound to their route server
(scope `agent:route_server`, created via `POST /route-servers/{id}/api-keys`).
The polling flow:

1. **Config poll** (`GET .../agent/config`): agent compares hash, downloads if changed
2. **Apply confirmation** (`POST .../agent/config/applied`): agent confirms the version is live
3. **Status report** (`POST .../agent/status`): agent pushes BGP session operational
   states and, per session, how many prefixes it imported and exported. Both counts are
   optional: a session that is not established has no count, and absent is not zero.
   The count is stored on every report, including reports where the state did not change

   The counts are also published on `/metrics` as `ixforge_bgp_session_prefixes_imported`
   and `..._exported`, labelled by route server, peer ASN and address family. A session
   that reports no count has its series removed rather than set to zero, so the graph
   shows a gap instead of a stale value. Scrape `/metrics` to keep history: the column
   only holds the latest value
4. **Heartbeat** (`POST .../agent/heartbeat`): agent reports health, server checks config sync and version

### Commit antes de responder

El commit de la sesion NO vive en el codigo posterior al `yield` de la
dependencia: FastAPI ejecuta eso **despues de entregar la respuesta al cliente**.
Lo hace `CommitBeforeResponse` (`main.py`), un middleware ASGI puro que
intercepta el envio y commitea antes de reenviar el `http.response.start`.

Las dos consecuencias de hacerlo al reves, medidas contra un deployment real:

1. La API confirmaba antes de saber. Devolvia `201` y recien despues intentaba
   guardar; si el commit fallaba, el cliente ya tenia confirmacion de algo que no
   existia, sin forma de enterarse
2. Crear y usar acto seguido fallaba. Crear un route server y pedirle su API key
   daba `404` en **4 de cada 6** intentos, porque la fila no estaba visible para
   la peticion siguiente

Si el commit falla, el middleware descarta la respuesta original y manda un 500
con el formato de error del proyecto.

Es ASGI puro y no `BaseHTTPMiddleware`, como el resto de los middlewares del
proyecto: ese no es seguro con asyncpg.

**Punto ciego de los tests:** la suite usa una sesion transaccional con rollback,
donde el commit nunca ocurre de verdad. Todo lo que dependa de *cuando* commitea
es invisible ahi. Los tests de `test_commit_antes_de_responder.py` verifican el
orden con una sesion falsa, no intentan ganarle a la carrera.

### Migraciones al arrancar

El entrypoint del contenedor aplica migraciones antes de arrancar el comando.
`IXFORGE_AUTO_MIGRATE=false` lo desactiva.

El portal **no** migra: es una UI que habla con la API por HTTP y no tiene, ni
debe tener, credenciales de base de datos.

Los servicios que si migran (`run` y `worker`) arrancan a la vez desde la misma
imagen, asi que `alembic/env.py` toma un `pg_advisory_lock` **antes** de
`run_sync`. La ubicacion importa: alembic lee `alembic_version` y planifica que
aplicar dentro de `do_run_migrations`, asi que tomarlo mas tarde serializa la
ejecucion pero no la planificacion, y el segundo reaplica todo sobre una base ya
migrada. Es lock de sesion y no de transaccion porque tiene que sobrevivir a las
transacciones que alembic abre por cada migracion.

### Background Tasks

Procrastinate uses PostgreSQL as the task queue (no Redis needed). Two queues:
- **config**: triggered on member/trunk state changes and BGP session mutations,
  regenerates BIRD configs for affected route servers
- **maintenance**: periodic cleanup of old events and config versions

The procrastinate app must be opened (`open_async`) in every process that
touches the queue: the worker, the schema setup during `ixforge upgrade`, and
the API lifespan (so endpoints can `defer_async`).

### Custom Fields

Entities with `ExtraDataMixin` store arbitrary data in a JSONB `extra_data` column. `CustomFieldDefinition` records define the expected schema per entity type, enforced at the service layer with type validation (string, integer, boolean, URL, email).
