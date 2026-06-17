# Remove Port Model - Implementation Plan

> **Estado: IMPLEMENTADO (documento historico).** El modelo `Port` fue eliminado y
> sus campos movidos a `Connection` (migracion `c5a1e8f34d02`). Ojo: un refactor
> posterior movio la `Connection` bajo un `Trunk` (`trunk_id`), por lo que las
> partes de este plan que mencionan `member_id`/`mac_address` en `Connection` ya
> no reflejan el modelo actual. Ver `docs/architecture.md` para el estado vigente.

**Goal:** Eliminar la tabla `ports` y mover la info de puerto (nombre, switch, velocidad) directamente al modelo `Connection`, como hace PatagoniaIX.

**Architecture:** El modelo `Port` desaparece. `Connection` gana tres campos: `name` (string, nombre del puerto), `switch_id` (FK a switches), y `speed` se vuelve NOT NULL. La unicidad se garantiza con `UNIQUE(switch_id, name)`. El monitoring pipeline y IXF export se adaptan para leer de Connection en vez de Port.

**Tech Stack:** Python 3.12, SQLAlchemy 2.0 async, FastAPI, Alembic, Pydantic v2, Jinja2, pytest

---

## Notas importantes

- No hay DB de test, los tests con `db_session` van a fallar con error de conexion. Solo correr tests que no requieren DB o verificar con `ruff check`
- Los tests de collector se corren con `cd /home/kr105/repos/ixforge/collector && uv run pytest`
- `uv run ruff check <file>` para lint
- Este es entorno dev, perder datos es OK
- No tocar route_server hostname (es otro modelo, se mantiene)
- No agregar comentarios, docstrings o type annotations a codigo que no se cambio
- Hablar en español casual

---

## Task 1: Migración Alembic - agregar campos a Connection y migrar datos

**Files:**
- Create: `alembic/versions/<rev>_move_port_fields_to_connection.py`

**Step 1: Crear la migración**

La migración debe:
1. Agregar `name` (String(100), nullable temporalmente) a `connections`
2. Agregar `switch_id` (UUID, FK a switches.id con ondelete RESTRICT, nullable temporalmente) a `connections`
3. Migrar datos: `UPDATE connections SET name = p.name, switch_id = p.switch_id, speed = p.speed FROM ports p WHERE connections.port_id = p.id`
4. Para connections sin port_id: `UPDATE connections SET name = 'unassigned', speed = 1000 WHERE name IS NULL` (fallback para dev)
5. `ALTER connections.name SET NOT NULL`
6. `ALTER connections.speed SET NOT NULL`
7. `ALTER connections.switch_id SET NOT NULL`
8. Agregar `UNIQUE(switch_id, name)` constraint: `uq_connections_switch_name`
9. Agregar CHECK: `speed > 0`, name: `ck_connections_speed_positive`
10. Drop FK `connections.port_id`
11. Drop column `connections.port_id`
12. Drop table `ports`
13. Drop enum type `port_type` de PostgreSQL

La revision debe encadenarse despues de `b79735bb9c91` (la ultima migracion).

El downgrade NO necesita ser perfecto (dev environment), pero al menos debe recrear la tabla ports y restaurar port_id en connections.

**Step 2: Correr la migración**

```bash
IXFORGE_SECRET_KEY=dev-secret-key-at-least-32-characters-long \
IXFORGE_DATABASE_URL=postgresql+asyncpg://ixforge:ixforge@localhost:5433/ixforge \
uv run python -m ixforge.cli upgrade
```

Expected: migración aplicada sin errores.

**Step 3: Commit**

```bash
git add alembic/versions/*move_port*
git commit -m "migration: move port fields to connection, drop ports table"
```

---

## Task 2: Modelo Connection - reemplazar port_id con name/switch_id/speed

**Files:**
- Modify: `src/ixforge/models/connection.py`
- Modify: `src/ixforge/models/__init__.py`
- Modify: `src/ixforge/enums.py`

**Step 1: Editar `connection.py`**

Cambios:
- Remover `port_id` mapped_column y su FK/index
- Remover relationship `port`
- Agregar `name: Mapped[str]` (String(100), not null)
- Agregar `switch_id: Mapped[uuid.UUID]` (FK a switches.id, ondelete RESTRICT, not null, indexed)
- Cambiar `speed` de `Mapped[int | None]` a `Mapped[int]` (not null, check > 0)
- Agregar `__table_args__` con `UniqueConstraint("switch_id", "name")` y `CheckConstraint("speed > 0")`
- Mantener relationship `member` tal cual

Resultado:

```python
class Connection(UUIDPrimaryKey, TenantMixin, TimestampMixin, ExtraDataMixin, Base):
    __tablename__ = "connections"
    __table_args__ = (
        UniqueConstraint("switch_id", "name", name="uq_connections_switch_name"),
        CheckConstraint("speed > 0", name="ck_connections_speed_positive"),
    )

    member_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("members.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    switch_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("switches.id", ondelete="RESTRICT"), nullable=False, index=True,
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    type: Mapped[ConnectionType] = mapped_column(
        Enum(ConnectionType, name="connection_type"), nullable=False,
    )
    state: Mapped[ConnectionState] = mapped_column(
        Enum(ConnectionState, name="connection_state"), nullable=False, default=ConnectionState.draft,
    )
    mac_address: Mapped[str | None] = mapped_column(MACADDR, nullable=True)
    speed: Mapped[int] = mapped_column(Integer, nullable=False, comment="Speed in Mbps")

    member: Mapped["Member"] = relationship(lazy="raise")
```

Agregar imports necesarios: `String`, `CheckConstraint`, `UniqueConstraint` en los imports de sqlalchemy.

**Step 2: Editar `__init__.py`**

Remover `from ixforge.models.port import Port` y `Port` de `__all__`.

**Step 3: Editar `enums.py`**

- Remover clase `PortType` completa (lineas 72-78)
- Remover `"PortType"` de `__all__`
- Remover `port = "port"` de `CustomFieldEntityType` (linea 108)

**Step 4: Verificar lint**

```bash
uv run ruff check src/ixforge/models/connection.py src/ixforge/models/__init__.py src/ixforge/enums.py
```

**Step 5: Commit**

```bash
git add src/ixforge/models/connection.py src/ixforge/models/__init__.py src/ixforge/enums.py
git commit -m "model: replace port_id with name/switch_id on Connection, remove Port model"
```

---

## Task 3: Schemas Connection - reemplazar port_id/port_name

**Files:**
- Modify: `src/ixforge/schemas/connection.py`
- Delete: `src/ixforge/schemas/port.py`

**Step 1: Editar `connection.py`**

`ConnectionCreate`:
- Remover `port_id: uuid.UUID | None = None`
- Agregar `switch_id: uuid.UUID`
- Agregar `name: str = Field(min_length=1, max_length=100)`
- Cambiar `speed: int | None = Field(default=None, gt=0)` a `speed: int = Field(gt=0)`

`ConnectionUpdate`:
- Remover `port_id: uuid.UUID | None = None`
- Agregar `switch_id: uuid.UUID | None = None`
- Agregar `name: str | None = Field(default=None, min_length=1, max_length=100)`
- Cambiar `speed` a `speed: int | None = Field(default=None, gt=0)` (se mantiene opcional en update)

`ConnectionRead`:
- Remover `port_id: uuid.UUID | None`
- Remover `port_name: str | None = None`
- Agregar `switch_id: uuid.UUID`
- Agregar `name: str`
- Cambiar `speed: int | None` a `speed: int`
- Simplificar `_populate_names`: remover el bloque try/except de port, dejar solo member_name

**Step 2: Eliminar `schemas/port.py`**

```bash
rm src/ixforge/schemas/port.py
```

**Step 3: Verificar lint**

```bash
uv run ruff check src/ixforge/schemas/connection.py
```

**Step 4: Commit**

```bash
git add -A src/ixforge/schemas/
git commit -m "schema: update Connection schemas, delete Port schemas"
```

---

## Task 4: Servicio connections - quitar lógica de Port

**Files:**
- Modify: `src/ixforge/services/connections.py`
- Delete: `src/ixforge/services/ports.py`

**Step 1: Editar `connections.py`**

En `create()`:
- Remover bloque de validación de `port_id` (lineas 51-56, el import lazy de Port)
- Agregar validación de `switch_id`: verificar que el switch existe y pertenece al IXP (import lazy de Switch)
- Construir Connection con `name=data.name`, `switch_id=data.switch_id`, `speed=data.speed` en vez de `port_id=data.port_id`

En `get()`:
- Remover `joinedload(Connection.port)` de la query
- Solo dejar `joinedload(Connection.member)`

En `list_connections()`:
- Remover `joinedload(Connection.port)`

En `update()`:
- Remover bloque de validación de `port_id` (lineas 149-154, el import lazy de Port)
- Agregar validación de `switch_id` si se incluye en update_fields

En `_has_complete_setup()`:
- Remover check `if connection.port_id is None: return False`
- El check de "completitud" ahora solo requiere VLAN + IP (name y switch_id siempre están)

En `transition()`:
- Cambiar mensaje de error: "port, VLAN, and IP must be assigned" -> "VLAN and IP must be assigned"

**Step 2: Eliminar `services/ports.py`**

```bash
rm src/ixforge/services/ports.py
```

**Step 3: Verificar lint**

```bash
uv run ruff check src/ixforge/services/connections.py
```

**Step 4: Commit**

```bash
git add -A src/ixforge/services/
git commit -m "service: update connections to use name/switch_id, delete ports service"
```

---

## Task 5: Servicios dependientes - monitoring, ixf_export, switches, members

**Files:**
- Modify: `src/ixforge/services/monitoring.py`
- Modify: `src/ixforge/services/ixf_export.py`
- Modify: `src/ixforge/services/switches.py`
- Modify: `src/ixforge/services/members.py`
- Modify: `src/ixforge/schemas/monitoring.py`

**Step 1: Editar `monitoring.py`**

Remover `from ixforge.models.port import Port`. El bloque "Active ports on active switches" (lineas 53-67) ahora debe leer de Connection:

```python
# Active connections on active switches (replaces port-based query)
port_targets: list[MonitoringPortTarget] = []
if switch_ids:
    conn_stmt = (
        select(Connection)
        .where(
            Connection.switch_id.in_(switch_ids),
            Connection.state == ConnectionState.active,
        )
    )
    conn_result = await session.execute(conn_stmt)
    for conn in conn_result.scalars().all():
        port_targets.append(
            MonitoringPortTarget(
                id=conn.id,
                switch_id=conn.switch_id,
                name=conn.name,
                speed=conn.speed,
                member_id=conn.member_id,
            )
        )
```

**Step 2: Editar `schemas/monitoring.py`**

`MonitoringPortTarget` se mantiene estructuralmente igual (id, switch_id, name, speed, member_id) pero ahora se puebla desde Connection. Semánticamente el `id` ahora es `connection.id` no `port.id`. No necesita cambios de código en el schema.

**Step 3: Editar `ixf_export.py`**

- Remover `from ixforge.models.port import Port`
- Remover `_BulkData.ports` y toda la lógica de carga de ports (lineas 190-194)
- En `_build_connection_entry()`: reemplazar `ports.get(conn.port_id)` con acceso directo a `conn.speed` y `conn.switch_id`
- `if_speed` ahora viene de `conn.speed * 1_000_000` (ya es Mbps en el modelo)
- `switch_id` viene de `conn.switch_id`

Buscar la funcion `_build_connection_entry` y todas las referencias a `port` dentro de ixf_export.py para ajustar.

**Step 4: Editar `switches.py`**

En `delete()`: cambiar el check de "has ports" por "has connections":

```python
has_connection = await session.scalar(
    select(Connection.id).where(Connection.switch_id == switch_id).limit(1)
)
if has_connection is not None:
    raise ConflictError("Cannot delete switch: connections are assigned to it")
```

Reemplazar `from ixforge.models.port import Port` por `from ixforge.models.connection import Connection`.

**Step 5: Editar `members.py`**

En `_has_complete_connection()`: remover el check de `Connection.port_id.is_not(None)`. Ahora `switch_id` y `name` siempre existen, así que solo checar VLAN + IP:

```python
async def _has_complete_connection(session: AsyncSession, member_id: uuid.UUID) -> bool:
    stmt = (
        select(Connection.id)
        .where(Connection.member_id == member_id)
    )
    result = await session.execute(stmt)
    connection_ids = [row[0] for row in result.all()]

    for conn_id in connection_ids:
        has_vlan = await session.scalar(
            select(ConnectionVLAN.id).where(ConnectionVLAN.connection_id == conn_id).limit(1)
        )
        if has_vlan is None:
            continue
        has_ip = await session.scalar(
            select(IPAssignment.id).where(IPAssignment.connection_id == conn_id).limit(1)
        )
        if has_ip is not None:
            return True

    return False
```

Ya no necesita `Connection.port_id.is_not(None)` en el WHERE.

**Step 6: Verificar lint**

```bash
uv run ruff check src/ixforge/services/monitoring.py src/ixforge/services/ixf_export.py src/ixforge/services/switches.py src/ixforge/services/members.py src/ixforge/schemas/monitoring.py
```

**Step 7: Commit**

```bash
git add src/ixforge/services/monitoring.py src/ixforge/services/ixf_export.py src/ixforge/services/switches.py src/ixforge/services/members.py src/ixforge/schemas/monitoring.py
git commit -m "service: adapt monitoring, ixf_export, switches, members to portless connections"
```

---

## Task 6: API routes - eliminar ports router

**Files:**
- Delete: `src/ixforge/api/v1/ports.py`
- Modify: `src/ixforge/api/v1/router.py`

**Step 1: Eliminar `api/v1/ports.py`**

```bash
rm src/ixforge/api/v1/ports.py
```

**Step 2: Editar `router.py`**

Remover la linea que importa `ports_router` y la linea que lo incluye con `router.include_router(...)`.

**Step 3: Verificar lint**

```bash
uv run ruff check src/ixforge/api/v1/router.py
```

**Step 4: Commit**

```bash
git add -A src/ixforge/api/v1/
git commit -m "api: remove ports router"
```

---

## Task 7: UI - eliminar ports, actualizar connections

**Files:**
- Delete: `src/ixforge/ui/routes/ports.py`
- Delete: `src/ixforge/ui/templates/ports/` (directorio entero)
- Modify: `src/ixforge/ui/app.py`
- Modify: `src/ixforge/ui/routes/connections.py`
- Modify: `src/ixforge/ui/templates/connections/form.html`
- Modify: `src/ixforge/ui/templates/connections/list.html` (si tiene header "Puerto")
- Modify: `src/ixforge/ui/templates/connections/list_rows.html` (si referencia port_name)
- Modify: `src/ixforge/ui/templates/connections/detail.html`
- Modify: `src/ixforge/ui/templates/members/detail.html`
- Modify: `src/ixforge/ui/templates/components/sidebar.html` (quitar link a Puertos)

**Step 1: Eliminar archivos de ports**

```bash
rm src/ixforge/ui/routes/ports.py
rm -rf src/ixforge/ui/templates/ports/
```

**Step 2: Editar `app.py`**

- Remover import de `ports` module
- Remover todas las rutas `/admin/ports/...`

**Step 3: Editar `sidebar.html`**

Remover el link a "Puertos" (`/admin/ports`) del sidebar de Infraestructura.

**Step 4: Editar `connections/form.html`**

Reemplazar el bloque de switch selector + HTMX port selector por campos simples:

- `switch_id`: select con las ubicaciones/switches disponibles (se pasan como contexto)
- `name`: text input libre, placeholder "Ej: Ethernet1/1"
- `speed`: number input en Mbps, required

Remover todo el bloque HTMX de carga dinamica de ports.

**Step 5: Editar `ui/routes/connections.py`**

En `connection_new()`:
- Cargar switches para el formulario: `switches = await api.get("/api/v1/switches", token, params={"limit": 200})`
- Pasar `switches` al template
- En POST: leer `switch_id`, `name`, `speed` del form en vez de `port_id`

En `connection_edit()`:
- Cargar switches
- En POST: leer `switch_id`, `name`, `speed` del form

**Step 6: Editar templates de conexiones**

`list.html` / `list_rows.html`: cambiar `port_name` por `name`
`detail.html`: cambiar `port_name or port_id` por `name`

**Step 7: Editar `members/detail.html`**

Cambiar `c.port_name or c.port_id or "-"` por `c.name or "-"`.

**Step 8: Verificar lint**

```bash
uv run ruff check src/ixforge/ui/app.py src/ixforge/ui/routes/connections.py
```

**Step 9: Commit**

```bash
git add -A src/ixforge/ui/
git commit -m "ui: remove ports UI, update connection forms with free-text port name"
```

---

## Task 8: CLI seed data

**Files:**
- Modify: `src/ixforge/cli.py`

**Step 1: Editar seed data**

Remover la creación de `Port` objects (buscar el bloque "Ports" en `_seed_data`).
Actualizar la creación de `Connection` objects para usar `name`, `switch_id`, `speed` directamente en vez de `port_id`.

Ejemplo:
```python
connection = Connection(
    ixp_id=ixp.id,
    member_id=member.id,
    switch_id=switches[0].id,
    name=f"Ethernet{i + 1}",
    type=ConnectionType.physical,
    speed=10000,
    state=ConnectionState.draft,
)
```

Remover imports de `Port` y `PortType`.

**Step 2: Verificar lint**

```bash
uv run ruff check src/ixforge/cli.py
```

**Step 3: Commit**

```bash
git add src/ixforge/cli.py
git commit -m "cli: update seed data to create connections without ports"
```

---

## Task 9: Tests core - eliminar test_ports, actualizar fixtures y tests

**Files:**
- Delete: `tests/test_ports.py`
- Delete: `tests/ui/test_ports.py`
- Modify: `tests/factories.py` (eliminar PortFactory)
- Modify: `tests/conftest.py` (eliminar fixtures de port si existen)
- Modify: `tests/test_connections.py`
- Modify: `tests/test_switches.py` (si referencia ports en delete test)
- Modify: `tests/test_members.py` (si referencia port_id en _has_complete_connection tests)
- Modify: `tests/test_ixf_export.py`
- Modify: `tests/test_bgp_sessions.py` (si crea ports como fixtures)
- Modify: `tests/test_locations.py` (si crea ports)
- Modify: `tests/test_member_access.py`
- Modify: `tests/test_ipam.py`
- Modify: `tests/ui/test_connections.py`
- Modify: `tests/e2e_runner.py`

**Step 1: Eliminar tests de ports**

```bash
rm tests/test_ports.py tests/ui/test_ports.py
```

**Step 2: Editar factories.py**

Remover `PortFactory` class y sus imports de `PortType`.

**Step 3: Actualizar todos los tests**

Para cada test file que crea ports como fixtures:
- Remover la creación de Port objects
- Cuando un test crea una Connection, agregar `name`, `switch_id`, `speed` directamente
- Remover `port_id=port.id` de las creaciones de Connection
- Cambiar assertions que referencien `port_id` o `port_name`

Usar un agente subagent para hacer estos cambios mecánicos en batch.

**Step 4: Verificar lint**

```bash
uv run ruff check tests/
```

**Step 5: Commit**

```bash
git add -A tests/
git commit -m "test: remove port tests, update all fixtures to portless connections"
```

---

## Task 10: Collector - actualizar modelos y SNMP

**Files:**
- Modify: `/home/kr105/repos/ixforge/collector/src/ixforge_collector/core_client/models.py`
- Modify: `/home/kr105/repos/ixforge/collector/src/ixforge_collector/core_client/client.py`
- Modify: Tests del collector que referencien port_id

**Step 1: Verificar `PortTarget` en collector**

El `PortTarget` en el collector ya tiene los campos correctos (id, switch_id, name, speed, member_id). Solo cambia que `id` ahora es `connection.id` en vez de `port.id`. Si el collector usa `port_id` como label en métricas, considerar renombrar a `connection_id` o dejarlo como `port_id` por compatibilidad con dashboards.

Verificar todos los archivos del collector que referencien `port_id` y decidir si renombrar.

**Step 2: Actualizar tests del collector si es necesario**

**Step 3: Verificar**

```bash
cd /home/kr105/repos/ixforge/collector && uv run pytest -v
```

**Step 4: Commit**

```bash
git add -A /home/kr105/repos/ixforge/collector/
git commit -m "collector: adapt to connection-based port targets"
```

---

## Task 11: E2E seed data

**Files:**
- Modify: `/home/kr105/repos/ixforge/e2e/seed_e2e.py`

**Step 1: Actualizar seed**

Remover creación de ports. Crear connections directamente con `name`, `switch_id`, `speed`.

**Step 2: Commit**

```bash
git add /home/kr105/repos/ixforge/e2e/seed_e2e.py
git commit -m "e2e: update seed data for portless connections"
```

---

## Task 12: Verificación final

**Step 1: Verificar que no queden referencias a Port**

```bash
grep -r "from ixforge.models.port" src/
grep -r "port_id" src/ixforge/
grep -r "PortType" src/ixforge/
grep -r "port_name" src/ixforge/
```

Todos deben retornar vacío (excepto port en el sentido de "portal" o "export").

**Step 2: Verificar lint completo**

```bash
uv run ruff check src/ tests/
```

**Step 3: Correr la UI y verificar manualmente**

```bash
IXFORGE_SECRET_KEY=dev-secret-key-at-least-32-characters-long \
IXFORGE_DATABASE_URL=postgresql+asyncpg://ixforge:ixforge@localhost:5433/ixforge \
uv run python -m ixforge.cli ui
```

Navegar a `http://localhost:8001/admin/connections` y verificar que funciona.

**Step 4: Commit final si hay ajustes**

```bash
git add -A
git commit -m "cleanup: final adjustments after port removal"
```
