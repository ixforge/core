# Paridad euro-ix y RPKI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Que un IXP creado con `run_setup` genere, sin tocar templates, un config BIRD 2.x con el patron euro-ix completo (tabla y pipe por peer, `rs client`, communities de filtrado, filtrado por origen y prefijos) y RPKI activable por route server.

**Architecture:** El generador pasa de dos renders concatenados a un unico render de `bird.conf.j2` con ambas familias. Tres tablas nuevas alimentan lo que los templates necesitan y el modelo no tenia: filtros de prefijos por miembro, sesiones que no cuelgan de un miembro, y servidores RTR. Los filtros dejan de rechazar en el import: marcan con large communities y el pipe hacia master descarta lo marcado.

**Tech Stack:** Python 3.12, SQLAlchemy 2 async, Alembic, FastAPI, Jinja2 sandboxed, PostgreSQL 17, pytest, ruff, mypy, BIRD 2.x

**Spec:** `docs/superpowers/specs/2026-09-10-euroix-parity-design.md`

## Global Constraints

- Nunca poner punto al final de un comentario
- Absolutamente no emojis
- Nunca poner comentarios changelog
- TDD: el test se escribe y se ve fallar antes de la implementacion
- Defensive programming: esto maneja infraestructura critica
- `uv run ruff check src/ tests/` y `uv run mypy src/` en cero antes de cada commit
- Postgres de test: `docker compose -f docker/docker-compose.testing.yml up -d` (puerto 5433)
- Los tests crean las tablas con `Base.metadata.create_all`, no con Alembic: un modelo es testeable sin haber escrito la migracion
- Toda la concurrencia con asyncio, logging con structlog
- Errores de API con el formato `{"error": {"code", "message", "details"}}`, nunca el default de FastAPI
- Slug de simbolos BIRD: **55 caracteres**, no 64
- El repo `agent` no se toca: el contrato no cambia

## Estructura de archivos

**Modelo y enums**
- `src/ixforge/enums.py` (modificar): 4 enums nuevos
- `src/ixforge/models/member_prefix_filter.py` (crear)
- `src/ixforge/models/route_server_peer.py` (crear)
- `src/ixforge/models/rpki_server.py` (crear)
- `src/ixforge/models/route_server.py` (modificar): 3 campos
- `src/ixforge/models/__init__.py` (modificar): registrar los modelos nuevos
- `alembic/versions/<rev>_euroix_parity.py` (crear)

**Generador**
- `src/ixforge/services/config_generation.py` (modificar): contextos, un solo render, slug 55
- `src/ixforge/services/communities.py` (crear): mapeo `MemberType` a numero de community
- `src/ixforge/services/default_templates.py` (modificar): el set nuevo

**API**
- `src/ixforge/schemas/route_server_peer.py`, `member_prefix_filter.py`, `rpki_server.py` (crear)
- `src/ixforge/services/route_server_peers.py`, `member_prefix_filters.py`, `rpki_servers.py` (crear)
- `src/ixforge/api/v1/route_server_peers.py`, `member_prefix_filters.py`, `rpki_servers.py` (crear)
- `src/ixforge/api/v1/__init__.py` (modificar): registrar routers

**Tests**
- `tests/test_euroix_communities.py`, `test_route_server_peers.py`, `test_member_prefix_filters.py`, `test_rpki_servers.py` (crear)
- `tests/test_config_generation.py` (reescribir contra el set nuevo)
- `tests/golden/` (crear): configs esperados versionados
- `tests/factories.py` (modificar): factories de los modelos nuevos

**Docs**
- `docs/templates.md`, `docs/api.md`, `README.md`, `docs/guides/` (modificar)
- `docs/migracion-euroix.md` (crear): el procedimiento para IXPs ya desplegados

---

### Task 1: Enums y modelos nuevos

Los cuatro enums, las tres tablas y los tres campos de `route_servers`, en un solo
bloque porque un reviewer los evalua junto: son la forma del modelo de datos.

**Files:**
- Modify: `src/ixforge/enums.py`
- Create: `src/ixforge/models/member_prefix_filter.py`
- Create: `src/ixforge/models/route_server_peer.py`
- Create: `src/ixforge/models/rpki_server.py`
- Modify: `src/ixforge/models/route_server.py`
- Modify: `src/ixforge/models/__init__.py`
- Test: `tests/test_model_fields.py`, `tests/test_enums.py`, `tests/test_new_models_import.py`

**Interfaces:**
- Produces: `RouteServerPeerType`, `PrefixFilterSource`, `RPKIPolicy`, `RPKITransport` en `ixforge.enums`; modelos `MemberPrefixFilter`, `RouteServerPeer`, `RPKIServer`; campos `RouteServer.passive_sessions`, `.rpki_enabled`, `.rpki_policy`

- [ ] **Step 1: Escribir los tests que fallan**

En `tests/test_enums.py`, agregar:

```python
def test_route_server_peer_type_values():
    from ixforge.enums import RouteServerPeerType

    assert {e.value for e in RouteServerPeerType} == {"upstream", "collector", "special"}


def test_rpki_policy_values():
    from ixforge.enums import RPKIPolicy

    assert {e.value for e in RPKIPolicy} == {"info_only", "reject_invalid"}


def test_prefix_filter_source_values():
    from ixforge.enums import PrefixFilterSource

    assert {e.value for e in PrefixFilterSource} == {"manual", "irr"}


def test_rpki_transport_values():
    from ixforge.enums import RPKITransport

    assert {e.value for e in RPKITransport} == {"tcp", "ssh"}
```

En `tests/test_model_fields.py`, agregar:

```python
async def test_member_prefix_filter_roundtrip(db_session, ixp):
    from ixforge.enums import MemberState, PeeringPolicy, PrefixFilterSource
    from ixforge.models.member import Member
    from ixforge.models.member_prefix_filter import MemberPrefixFilter

    member = Member(
        ixp_id=ixp.id,
        name="Apoapsis",
        short_name="APO",
        asn=273973,
        state=MemberState.active,
        peering_policy=PeeringPolicy.open,
    )
    db_session.add(member)
    await db_session.flush()

    pf = MemberPrefixFilter(
        ixp_id=ixp.id,
        member_id=member.id,
        af=4,
        origin_asns=[273973, 64512],
        prefixes=["45.170.100.0/24", "45.238.179.0/24"],
        as_set="AS-APOAPSIS",
        source=PrefixFilterSource.manual,
    )
    db_session.add(pf)
    await db_session.flush()

    assert pf.origin_asns == [273973, 64512]
    assert pf.prefixes == ["45.170.100.0/24", "45.238.179.0/24"]
    assert pf.source is PrefixFilterSource.manual


async def test_member_prefix_filter_nullable_lists(db_session, ixp):
    """origin_asns y prefixes en NULL son el caso normal, no un error"""
    from ixforge.enums import MemberState, PeeringPolicy
    from ixforge.models.member import Member
    from ixforge.models.member_prefix_filter import MemberPrefixFilter

    member = Member(
        ixp_id=ixp.id, name="LACTLD", short_name="LACTLD", asn=61455,
        state=MemberState.active, peering_policy=PeeringPolicy.open,
    )
    db_session.add(member)
    await db_session.flush()

    pf = MemberPrefixFilter(ixp_id=ixp.id, member_id=member.id, af=6)
    db_session.add(pf)
    await db_session.flush()

    assert pf.origin_asns is None
    assert pf.prefixes is None


async def test_route_server_peer_roundtrip(db_session, ixp):
    from ixforge.enums import BGPAdminState, RouteServerPeerType
    from ixforge.models.route_server import RouteServer
    from ixforge.models.route_server_peer import RouteServerPeer

    rs = RouteServer(ixp_id=ixp.id, name="rs1", ip_v4="192.0.2.1", is_active=True)
    db_session.add(rs)
    await db_session.flush()

    peer = RouteServerPeer(
        ixp_id=ixp.id,
        route_server_id=rs.id,
        name="PIT Chile upstream",
        peer_ip="192.0.2.5",
        peer_asn=64166,
        local_asn=64166,
        passive=True,
        peer_type=RouteServerPeerType.upstream,
        mark_community="64166:9999",
    )
    db_session.add(peer)
    await db_session.flush()

    assert peer.peer_type is RouteServerPeerType.upstream
    assert peer.admin_state is BGPAdminState.up


async def test_rpki_server_defaults(db_session, ixp):
    from ixforge.enums import RPKITransport
    from ixforge.models.rpki_server import RPKIServer

    srv = RPKIServer(ixp_id=ixp.id, name="routinator", host="10.20.30.65")
    db_session.add(srv)
    await db_session.flush()

    assert srv.port == 3323
    assert srv.transport is RPKITransport.tcp
    assert srv.route_server_id is None


async def test_route_server_new_defaults(db_session, ixp):
    from ixforge.enums import RPKIPolicy
    from ixforge.models.route_server import RouteServer

    rs = RouteServer(ixp_id=ixp.id, name="rs1", ip_v4="192.0.2.1", is_active=True)
    db_session.add(rs)
    await db_session.flush()

    assert rs.passive_sessions is True
    assert rs.rpki_enabled is False
    assert rs.rpki_policy is RPKIPolicy.info_only
```

- [ ] **Step 2: Correr los tests y verificar que fallan**

Run: `uv run pytest tests/test_enums.py tests/test_model_fields.py -v -k "peer_type or rpki or prefix_filter or new_defaults"`
Expected: FAIL con `ModuleNotFoundError` / `ImportError` para los modelos y enums nuevos

- [ ] **Step 3: Agregar los enums**

En `src/ixforge/enums.py`, agregar al `__all__` y al final del archivo:

```python
# -- Route server peers --


class RouteServerPeerType(StrEnum):
    upstream = "upstream"
    collector = "collector"
    special = "special"


# -- Filtrado de prefijos --


class PrefixFilterSource(StrEnum):
    manual = "manual"
    irr = "irr"


# -- RPKI --


class RPKIPolicy(StrEnum):
    info_only = "info_only"
    reject_invalid = "reject_invalid"


class RPKITransport(StrEnum):
    tcp = "tcp"
    ssh = "ssh"
```

- [ ] **Step 4: Crear `src/ixforge/models/member_prefix_filter.py`**

```python
"""Filtros de prefijos y ASN de origen por miembro y familia."""

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, Enum, ForeignKey, String, Uuid
from sqlalchemy.dialects.postgresql import ARRAY, CIDR
from sqlalchemy.orm import Mapped, mapped_column

from ixforge.enums import PrefixFilterSource
from ixforge.models.base import Base, TenantMixin, TimestampMixin, UUIDPrimaryKey


class MemberPrefixFilter(UUIDPrimaryKey, TenantMixin, TimestampMixin, Base):
    """Origen permitido para las rutas de un miembro en una familia

    Un miembro sin fila se comporta como origin_asns = [su propio ASN] y sin
    filtro de prefijos, que es el default seguro
    """

    __tablename__ = "member_prefix_filters"
    __table_args__ = (
        CheckConstraint("af IN (4, 6)", name="ck_member_prefix_filters_af_valid"),
    )

    member_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("members.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    af: Mapped[int] = mapped_column(nullable=False, comment="Address family: 4 o 6")
    origin_asns: Mapped[list[int] | None] = mapped_column(
        ARRAY(BigInteger),
        nullable=True,
        comment="NULL o vacio significa solo el ASN del miembro",
    )
    prefixes: Mapped[list[str] | None] = mapped_column(
        ARRAY(CIDR),
        nullable=True,
        comment="NULL significa no filtrar por prefijo",
    )
    as_set: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source: Mapped[PrefixFilterSource] = mapped_column(
        Enum(PrefixFilterSource, name="prefix_filter_source"),
        nullable=False,
        default=PrefixFilterSource.manual,
    )
    last_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
```

Agregar en `__table_args__` la unicidad, importando `UniqueConstraint`:

```python
        UniqueConstraint("member_id", "af", name="uq_member_prefix_filters_member_af"),
```

- [ ] **Step 5: Crear `src/ixforge/models/route_server_peer.py`**

```python
"""Sesiones BGP de un route server que no pertenecen a un miembro."""

import uuid

from sqlalchemy import Enum, ForeignKey, Integer, String, Text, UniqueConstraint, Uuid
from sqlalchemy.dialects.postgresql import INET
from sqlalchemy.orm import Mapped, mapped_column

from ixforge.enums import BGPAdminState, BGPOperState, RouteServerPeerType
from ixforge.models.base import Base, TenantMixin, TimestampMixin, UUIDPrimaryKey


class RouteServerPeer(UUIDPrimaryKey, TenantMixin, TimestampMixin, Base):
    """Upstream, colector o peer especial

    No lleva columna af: se deriva de peer_ip. Guardarla seria una segunda
    fuente de verdad que puede discrepar de la primera
    """

    __tablename__ = "route_server_peers"
    __table_args__ = (
        UniqueConstraint("route_server_id", "peer_ip", name="uq_route_server_peers_rs_ip"),
    )

    route_server_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("route_servers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    peer_ip: Mapped[str] = mapped_column(INET, nullable=False)
    peer_asn: Mapped[int] = mapped_column(Integer, nullable=False)
    local_asn: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="NULL usa el ASN del IXP"
    )
    passive: Mapped[bool] = mapped_column(nullable=False, default=True)
    peer_type: Mapped[RouteServerPeerType] = mapped_column(
        Enum(RouteServerPeerType, name="route_server_peer_type"), nullable=False
    )
    mark_community: Mapped[str | None] = mapped_column(
        String(32), nullable=True, comment="Forma asn:value"
    )
    max_prefixes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    admin_state: Mapped[BGPAdminState] = mapped_column(
        Enum(BGPAdminState, name="bgp_admin_state"),
        nullable=False,
        default=BGPAdminState.up,
    )
    oper_state: Mapped[BGPOperState] = mapped_column(
        Enum(BGPOperState, name="bgp_oper_state"),
        nullable=False,
        default=BGPOperState.unknown,
    )
```

- [ ] **Step 6: Crear `src/ixforge/models/rpki_server.py`**

```python
"""Servidores RTR para validacion RPKI."""

import uuid

from sqlalchemy import Enum, ForeignKey, Integer, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from ixforge.enums import RPKITransport
from ixforge.models.base import Base, TenantMixin, TimestampMixin, UUIDPrimaryKey


class RPKIServer(UUIDPrimaryKey, TenantMixin, TimestampMixin, Base):
    __tablename__ = "rpki_servers"
    __table_args__ = (
        UniqueConstraint("ixp_id", "name", name="uq_rpki_servers_ixp_name"),
    )

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    host: Mapped[str] = mapped_column(String(255), nullable=False)
    port: Mapped[int] = mapped_column(Integer, nullable=False, default=3323)
    route_server_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("route_servers.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
        comment="NULL aplica a todos los route servers del IXP",
    )
    transport: Mapped[RPKITransport] = mapped_column(
        Enum(RPKITransport, name="rpki_transport"),
        nullable=False,
        default=RPKITransport.tcp,
    )
    refresh_time: Mapped[int | None] = mapped_column(Integer, nullable=True)
    retry_time: Mapped[int | None] = mapped_column(Integer, nullable=True)
    expire_time: Mapped[int | None] = mapped_column(Integer, nullable=True)
```

- [ ] **Step 7: Agregar los campos a `RouteServer`**

En `src/ixforge/models/route_server.py`, importar `RPKIPolicy` de `ixforge.enums` y `Enum` de sqlalchemy, y agregar despues de `software`:

```python
    passive_sessions: Mapped[bool] = mapped_column(
        nullable=False,
        default=True,
        server_default="true",
        comment="El route server nunca inicia la conexion BGP",
    )
    rpki_enabled: Mapped[bool] = mapped_column(
        nullable=False, default=False, server_default="false"
    )
    rpki_policy: Mapped[RPKIPolicy] = mapped_column(
        Enum(RPKIPolicy, name="rpki_policy"),
        nullable=False,
        default=RPKIPolicy.info_only,
        server_default=RPKIPolicy.info_only.value,
    )
```

- [ ] **Step 8: Registrar los modelos**

En `src/ixforge/models/__init__.py`, agregar los imports de `MemberPrefixFilter`, `RouteServerPeer` y `RPKIServer` siguiendo el patron de los que ya estan, para que `Base.metadata` los conozca.

- [ ] **Step 9: Correr los tests y verificar que pasan**

Run: `uv run pytest tests/test_enums.py tests/test_model_fields.py tests/test_new_models_import.py -v`
Expected: PASS

- [ ] **Step 10: Lint, tipos y commit**

```bash
uv run ruff check src/ tests/ && uv run mypy src/
git add src/ixforge/enums.py src/ixforge/models/ tests/test_enums.py tests/test_model_fields.py
git commit -m "feat: modelo para filtros de prefijos, peers no-miembro y servidores RPKI"
```

---

### Task 2: Migracion Alembic del modelo

**Files:**
- Create: `alembic/versions/<rev>_euroix_parity.py`

**Interfaces:**
- Consumes: los modelos de la Task 1
- Produces: revision aplicable sobre `b8c1d2e3f4a5`

- [ ] **Step 1: Levantar el Postgres de test y generar la migracion**

```bash
docker compose -f docker/docker-compose.testing.yml up -d
uv run alembic revision --autogenerate -m "euroix parity"
```

- [ ] **Step 2: Revisar la migracion generada a mano**

El autogenerate de Alembic no maneja bien tres cosas de esta migracion, hay que
corregirlas en el archivo:

1. Los tipos `ARRAY(BigInteger)` y `ARRAY(CIDR)` necesitan el import
   `from sqlalchemy.dialects import postgresql` y escribirse como
   `postgresql.ARRAY(sa.BigInteger())` y `postgresql.ARRAY(postgresql.CIDR())`
2. Los enums nuevos (`route_server_peer_type`, `prefix_filter_source`,
   `rpki_policy`, `rpki_transport`) se crean con `sa.Enum(..., name=...)`, pero
   `bgp_admin_state` y `bgp_oper_state` **ya existen** en la base: hay que pasarles
   `create_type=False` para que no intente crearlos de nuevo
3. Las tres columnas de `route_servers` son `nullable=False` sobre una tabla con
   filas: tienen que llevar `server_default`, ya declarado en el modelo

- [ ] **Step 3: Verificar que sube y baja**

```bash
uv run alembic upgrade head
uv run alembic downgrade -1
uv run alembic upgrade head
```
Expected: los tres comandos sin error, y `\d route_server_peers` en psql muestra la tabla

- [ ] **Step 4: Commit**

```bash
git add alembic/versions/
git commit -m "feat: migracion de las tablas de paridad euro-ix"
```

---

### Task 3: Mapeo de MemberType a community informativa

**Files:**
- Create: `src/ixforge/services/communities.py`
- Test: `tests/test_euroix_communities.py`

**Interfaces:**
- Produces: `member_type_community(member_type: MemberType | None) -> int | None`

- [ ] **Step 1: Escribir el test que falla**

`tests/test_euroix_communities.py`:

```python
"""Tests del mapeo de tipo de miembro a community informativa euro-ix."""

import pytest

from ixforge.enums import MemberType
from ixforge.services.communities import member_type_community


@pytest.mark.parametrize(
    ("member_type", "expected"),
    [
        (MemberType.ixp, 210),
        (MemberType.isp, 220),
        (MemberType.academico, 230),
        (MemberType.gobierno, 240),
        (MemberType.cdn, 250),
        (MemberType.corporativo, 260),
        (MemberType.infraestructura_critica, 270),
        (MemberType.otro, None),
        (None, None),
    ],
)
def test_member_type_community(member_type, expected):
    assert member_type_community(member_type) == expected


def test_every_member_type_is_mapped():
    """Un MemberType nuevo sin entrada en el mapeo tiene que romper este test"""
    from ixforge.services.communities import MEMBER_TYPE_COMMUNITIES

    assert set(MEMBER_TYPE_COMMUNITIES) == set(MemberType)
```

- [ ] **Step 2: Correr el test y verificar que falla**

Run: `uv run pytest tests/test_euroix_communities.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'ixforge.services.communities'`

- [ ] **Step 3: Implementar**

`src/ixforge/services/communities.py`:

```python
"""Mapeo de conceptos del dominio a communities BGP del esquema euro-ix.

Los numeros son los del esquema euro-ix de tipo de miembro y no son
configurables: cambiarlos rompe la interoperabilidad con los looking glass
y con lo que los miembros ya tienen documentado
"""

from ixforge.enums import MemberType

MEMBER_TYPE_COMMUNITIES: dict[MemberType, int | None] = {
    MemberType.ixp: 210,
    MemberType.isp: 220,
    MemberType.academico: 230,
    MemberType.gobierno: 240,
    MemberType.cdn: 250,
    MemberType.corporativo: 260,
    MemberType.infraestructura_critica: 270,
    MemberType.otro: None,
}


def member_type_community(member_type: MemberType | None) -> int | None:
    """Devuelve el valor de la community informativa de tipo de miembro

    None significa que no se agrega ninguna community
    """
    if member_type is None:
        return None
    return MEMBER_TYPE_COMMUNITIES.get(member_type)
```

- [ ] **Step 4: Correr el test y verificar que pasa**

Run: `uv run pytest tests/test_euroix_communities.py -v`
Expected: PASS, 10 tests

- [ ] **Step 5: Commit**

```bash
uv run ruff check src/ tests/ && uv run mypy src/
git add src/ixforge/services/communities.py tests/test_euroix_communities.py
git commit -m "feat: mapeo de tipo de miembro a community euro-ix"
```

---

### Task 4: Presupuesto de nombres a 55 caracteres

BIRD limita los simbolos a 64. El patron euro-ix deriva cinco simbolos del mismo
slug y el prefijo mas largo es `f_import_`, de 9 caracteres. El codigo actual
trunca a 64 y con el set nuevo generaria simbolos de 73 que BIRD rechaza.

**Files:**
- Modify: `src/ixforge/services/config_generation.py:60-70`
- Test: `tests/test_config_generation.py`

**Interfaces:**
- Produces: `PEER_SLUG_MAX_LEN = 55` y `_build_peer_slug(short_name: str, peer_ip: str, af: int) -> str` en `ixforge.services.config_generation`, reemplazando a `_sanitize_protocol_name`

- [ ] **Step 1: Escribir los tests que fallan**

En `tests/test_config_generation.py`, agregar:

```python
def test_peer_slug_truncates_to_55():
    from ixforge.services.config_generation import PEER_SLUG_MAX_LEN, _build_peer_slug

    slug = _build_peer_slug("A" * 200, "192.0.2.1", 4)

    assert len(slug) == PEER_SLUG_MAX_LEN == 55


def test_derived_symbols_fit_in_bird_limit():
    """f_import_ es el prefijo mas largo del patron euro-ix: 9 caracteres"""
    from ixforge.services.config_generation import _build_peer_slug

    slug = _build_peer_slug("A" * 200, "192.0.2.1", 4)

    for prefix in ("t_", "pb_", "pp_", "f_import_", "f_export_"):
        assert len(prefix + slug) <= 64


def test_peer_slug_sanitizes_and_keeps_af():
    from ixforge.services.config_generation import _build_peer_slug

    slug_v4 = _build_peer_slug("Rio Negro S.A.", "192.0.2.1", 4)
    slug_v6 = _build_peer_slug("Rio Negro S.A.", "2001:db8::1", 6)

    assert slug_v4 == "Rio_Negro_S_A__192_0_2_1_v4"
    assert slug_v6 != slug_v4
    assert all(c.isalnum() or c == "_" for c in slug_v4)
```

- [ ] **Step 2: Correr los tests y verificar que fallan**

Run: `uv run pytest tests/test_config_generation.py -v -k "slug or derived_symbols"`
Expected: FAIL con `ImportError: cannot import name '_build_peer_slug'`

- [ ] **Step 3: Reemplazar `_sanitize_protocol_name`**

En `src/ixforge/services/config_generation.py`, borrar `_sanitize_protocol_name` y poner:

```python
# BIRD limita los simbolos a 64 caracteres. El patron euro-ix deriva cinco
# simbolos del mismo slug (t_, pb_, pp_, f_import_, f_export_) y el prefijo
# mas largo mide 9, asi que el slug no puede pasar de 55
PEER_SLUG_MAX_LEN = 55


def _build_peer_slug(short_name: str, peer_ip: str, af: int) -> str:
    """Base alfanumerica de la que salen todos los simbolos BIRD de un peer

    Incluye la familia porque un mismo peer tiene sesiones v4 y v6 en el mismo
    daemon y sus tablas no pueden colisionar
    """
    raw = f"{short_name}_{peer_ip}_v{af}"
    sanitized = re.sub(r"[^a-zA-Z0-9_]", "_", raw)
    return sanitized[:PEER_SLUG_MAX_LEN]
```

- [ ] **Step 4: Actualizar el desambiguador de colisiones en `build_peers`**

El bloque que agrega sufijo numerico en colision usa el limite viejo. Cambiarlo a:

```python
        slug = _build_peer_slug(member.short_name, peer_ip_str, af)
        base = slug
        counter = 2
        while slug in seen_slugs:
            suffix = f"_{counter}"
            slug = base[: PEER_SLUG_MAX_LEN - len(suffix)] + suffix
            counter += 1
        seen_slugs.add(slug)
```

- [ ] **Step 5: Correr los tests y verificar que pasan**

Run: `uv run pytest tests/test_config_generation.py -v -k "slug or derived_symbols"`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
uv run ruff check src/ tests/ && uv run mypy src/
git add src/ixforge/services/config_generation.py tests/test_config_generation.py
git commit -m "fix: bajar el presupuesto de nombres BIRD a 55 para los simbolos derivados"
```

---

### Task 5: Contexto extendido de los peers de miembros

`PeerContext` hoy no tiene con que alimentar el chequeo de next hop (`allips`), el
filtrado por origen (`allas`), el filtrado por prefijos (`allnet`) ni la community
de tipo de miembro.

**Files:**
- Modify: `src/ixforge/services/config_generation.py`
- Test: `tests/test_config_generation.py`

**Interfaces:**
- Consumes: `_build_peer_slug` (Task 4), `member_type_community` (Task 3), `MemberPrefixFilter` (Task 1)
- Produces: `PeerContext` con los campos `slug`, `member_short_name`, `member_type_community`, `all_peer_ips`, `origin_asns`, `prefixes`, `af`; `build_peers` devuelve esa forma

- [ ] **Step 1: Escribir los tests que fallan**

En `tests/test_config_generation.py`, agregar. `_setup_route_server` ya existe en
ese archivo; `_setup_member_peer` y `_add_second_connection` se escriben en el Step 2:

```python
async def test_peer_context_defaults_origin_to_member_asn(db_session, ixp):
    """Un miembro sin fila en member_prefix_filters filtra por su propio ASN"""
    from ixforge.services.config_generation import build_peers

    rs = await _setup_route_server(db_session, ixp)
    await _setup_member_peer(db_session, ixp, rs, asn=61455, ipv4="192.0.2.16")

    peers = await build_peers(db_session, rs.id, af=4)

    assert len(peers) == 1
    assert peers[0].origin_asns == [61455]
    assert peers[0].prefixes is None


async def test_peer_context_uses_prefix_filter(db_session, ixp):
    from ixforge.models.member_prefix_filter import MemberPrefixFilter
    from ixforge.services.config_generation import build_peers

    rs = await _setup_route_server(db_session, ixp)
    member = await _setup_member_peer(db_session, ixp, rs, asn=273973, ipv4="192.0.2.11")
    db_session.add(
        MemberPrefixFilter(
            ixp_id=ixp.id,
            member_id=member.id,
            af=4,
            origin_asns=[273973, 64512],
            prefixes=["45.170.100.0/24", "45.238.179.0/24"],
        )
    )
    await db_session.flush()

    peers = await build_peers(db_session, rs.id, af=4)

    assert peers[0].origin_asns == [273973, 64512]
    assert peers[0].prefixes == ["45.170.100.0/24", "45.238.179.0/24"]


async def test_peer_context_prefix_filter_is_per_af(db_session, ixp):
    """El filtro v6 no se le puede aplicar a la sesion v4"""
    from ixforge.models.member_prefix_filter import MemberPrefixFilter
    from ixforge.services.config_generation import build_peers

    rs = await _setup_route_server(db_session, ixp)
    member = await _setup_member_peer(
        db_session, ixp, rs, asn=273973, ipv4="192.0.2.11", ipv6="2001:db8::11"
    )
    db_session.add(
        MemberPrefixFilter(
            ixp_id=ixp.id, member_id=member.id, af=6, prefixes=["2001:db8:aa::/48"]
        )
    )
    await db_session.flush()

    peers_v4 = await build_peers(db_session, rs.id, af=4)
    peers_v6 = await build_peers(db_session, rs.id, af=6)

    assert peers_v4[0].prefixes is None
    assert peers_v6[0].prefixes == ["2001:db8:aa::/48"]


async def test_all_peer_ips_covers_every_connection_of_the_member(db_session, ixp):
    """allips tiene que traer todas las IPs del miembro en la VLAN, no solo la de
    la sesion, o el chequeo de next hop marca como hijack su propio segundo puerto
    """
    from ixforge.services.config_generation import build_peers

    rs = await _setup_route_server(db_session, ixp)
    member = await _setup_member_peer(db_session, ixp, rs, asn=273973, ipv4="192.0.2.11")
    await _add_second_connection(db_session, ixp, rs, member, ipv4="192.0.2.12")

    peers = await build_peers(db_session, rs.id, af=4)

    for peer in peers:
        assert set(peer.all_peer_ips) == {"192.0.2.11", "192.0.2.12"}


async def test_peer_context_carries_member_type_community(db_session, ixp):
    from ixforge.enums import MemberType
    from ixforge.services.config_generation import build_peers

    rs = await _setup_route_server(db_session, ixp)
    await _setup_member_peer(
        db_session, ixp, rs, asn=25152, ipv4="192.0.2.10",
        member_type=MemberType.infraestructura_critica,
    )

    peers = await build_peers(db_session, rs.id, af=4)

    assert peers[0].member_type_community == 270
```

- [ ] **Step 2: Escribir los helpers de LAN de peering compartida**

El helper `_setup_active_peer` que ya existe crea **una VLAN por miembro**. Sirve
para los tests viejos, pero no reproduce el caso que importa aca: varios miembros
en la misma VLAN, que es de donde sale el conjunto `allips`. Los tests nuevos usan
helpers propios y no tocan el viejo, para no romper lo que ya pasa.

En la seccion de helpers de `tests/test_config_generation.py`:

```python
PEERING_VLAN_VID = 64


async def _get_or_create_peering_lan(db: AsyncSession, ixp: IXP) -> tuple[VLAN, IPPool, IPPool]:
    """Una unica LAN de peering compartida por todos los miembros del IXP

    Idempotente: el primer miembro la crea y los siguientes la reusan, asi cada
    test la pide sin coordinarse con los demas
    """
    existing = (
        await db.execute(
            select(VLAN).where(VLAN.ixp_id == ixp.id, VLAN.vid == PEERING_VLAN_VID)
        )
    ).scalar_one_or_none()

    if existing is None:
        existing = VLAN(
            ixp_id=ixp.id,
            name="Peering LAN",
            vid=PEERING_VLAN_VID,
            type=VLANType.production,
        )
        db.add(existing)
        await db.flush()
        db.add_all([
            IPPool(ixp_id=ixp.id, vlan_id=existing.id, network="192.0.2.0/24", af=4),
            IPPool(ixp_id=ixp.id, vlan_id=existing.id, network="2001:db8::/64", af=6),
        ])
        await db.flush()

    pools = (
        await db.execute(select(IPPool).where(IPPool.vlan_id == existing.id).order_by(IPPool.af))
    ).scalars().all()
    return existing, pools[0], pools[1]


async def _setup_member_peer(
    db: AsyncSession,
    ixp: IXP,
    rs: RouteServer,
    *,
    asn: int,
    ipv4: str | None = None,
    ipv6: str | None = None,
    short_name: str | None = None,
    member_type: MemberType | None = None,
    max_prefixes: int | None = None,
) -> Member:
    """Miembro activo con trunk, conexion, IPs y sesiones BGP en la LAN compartida

    Devuelve el Member para que el test le pueda colgar un MemberPrefixFilter
    """
    vlan, pool_v4, pool_v6 = await _get_or_create_peering_lan(db, ixp)

    member = Member(
        ixp_id=ixp.id,
        name=f"Miembro AS{asn}",
        short_name=short_name or f"AS{asn}",
        asn=asn,
        state=MemberState.active,
        peering_policy=PeeringPolicy.open,
        member_type=member_type,
    )
    db.add(member)
    await db.flush()

    await _attach_trunk(
        db, ixp, rs, member, vlan, pool_v4, pool_v6,
        trunk_name=f"ae-{asn}", ipv4=ipv4, ipv6=ipv6, max_prefixes=max_prefixes,
    )
    return member


async def _attach_trunk(
    db: AsyncSession,
    ixp: IXP,
    rs: RouteServer,
    member: Member,
    vlan: VLAN,
    pool_v4: IPPool,
    pool_v6: IPPool,
    *,
    trunk_name: str,
    ipv4: str | None,
    ipv6: str | None,
    max_prefixes: int | None = None,
) -> TrunkVLAN:
    """Trunk activo con su conexion, IPs y sesiones BGP en la VLAN dada"""
    location = Location(ixp_id=ixp.id, name=f"DC-{trunk_name}", city="Test", country="US")
    db.add(location)
    await db.flush()

    switch = Switch(ixp_id=ixp.id, name=f"sw-{trunk_name}", location_id=location.id)
    db.add(switch)
    await db.flush()

    trunk = Trunk(ixp_id=ixp.id, member_id=member.id, name=trunk_name, state=TrunkState.active)
    db.add(trunk)
    await db.flush()

    db.add(
        Connection(
            ixp_id=ixp.id,
            trunk_id=trunk.id,
            switch_id=switch.id,
            name=f"eth-{trunk_name}",
            type=ConnectionType.physical,
            state=ConnectionState.active,
            speed=10000,
        )
    )

    trunk_vlan = TrunkVLAN(ixp_id=ixp.id, trunk_id=trunk.id, vlan_id=vlan.id)
    db.add(trunk_vlan)
    await db.flush()

    for address, pool, af in ((ipv4, pool_v4, 4), (ipv6, pool_v6, 6)):
        if address is None:
            continue
        db.add(
            IPAssignment(
                ixp_id=ixp.id, pool_id=pool.id, trunk_vlan_id=trunk_vlan.id, address=address
            )
        )
        db.add(
            BGPSession(
                ixp_id=ixp.id,
                route_server_id=rs.id,
                trunk_vlan_id=trunk_vlan.id,
                af=af,
                admin_state=BGPAdminState.up,
                max_prefixes=max_prefixes,
            )
        )
    await db.flush()
    return trunk_vlan


async def _add_second_connection(
    db: AsyncSession, ixp: IXP, rs: RouteServer, member: Member, *, ipv4: str
) -> None:
    """Segundo trunk del mismo miembro en la misma VLAN, con su propia IP

    Reproduce a un miembro con dos puertos: las dos IPs son legitimas y las dos
    tienen que entrar en allips, o el chequeo de next hop marca como hijack su
    propio segundo puerto
    """
    vlan, pool_v4, pool_v6 = await _get_or_create_peering_lan(db, ixp)
    await _attach_trunk(
        db, ixp, rs, member, vlan, pool_v4, pool_v6,
        trunk_name=f"ae-{member.asn}-2", ipv4=ipv4, ipv6=None,
    )
```

Agregar al bloque de imports del archivo lo que falte: `select` de sqlalchemy,
`MemberType` de `ixforge.enums`, y `MemberPrefixFilter`, `RouteServerPeer` y
`RPKIServer` de sus modulos.

- [ ] **Step 3: Correr los tests y verificar que fallan**

Run: `uv run pytest tests/test_config_generation.py -v -k "peer_context or all_peer_ips"`
Expected: FAIL con `AttributeError: 'PeerContext' object has no attribute 'origin_asns'`

- [ ] **Step 4: Extender `PeerContext`**

En `src/ixforge/services/config_generation.py`:

```python
@dataclass(frozen=True)
class PeerContext:
    """Template context for a single BGP peer."""

    slug: str
    member_name: str
    member_short_name: str
    member_type_community: int | None
    peer_ip: str
    all_peer_ips: tuple[str, ...]
    peer_asn: int
    origin_asns: tuple[int, ...]
    prefixes: tuple[str, ...] | None
    max_prefixes: int | None
    af: int
```

`all_peer_ips`, `origin_asns` y `prefixes` van como tuplas porque el dataclass es
`frozen` y una lista mutable adentro de un contexto congelado invita a que alguien
la modifique durante el render.

- [ ] **Step 5: Escribir los dos helpers de consulta**

```python
async def _member_vlan_ips(
    session: AsyncSession, route_server_id: uuid.UUID, af: int
) -> dict[tuple[uuid.UUID, uuid.UUID], list[str]]:
    """Todas las IPs de cada miembro en cada VLAN, para el chequeo de next hop

    Clave: (member_id, vlan_id). El chequeo euro-ix necesita el conjunto completo
    del miembro y no solo la IP de la sesion que se esta renderizando
    """
    stmt = (
        select(Trunk.member_id, TrunkVLAN.vlan_id, IPAssignment.address)
        .join(TrunkVLAN, IPAssignment.trunk_vlan_id == TrunkVLAN.id)
        .join(Trunk, TrunkVLAN.trunk_id == Trunk.id)
        .join(IPPool, IPAssignment.pool_id == IPPool.id)
        .where(IPPool.af == af, Trunk.state == TrunkState.active)
        .order_by(IPAssignment.address)
    )
    result = await session.execute(stmt)
    out: dict[tuple[uuid.UUID, uuid.UUID], list[str]] = {}
    for member_id, vlan_id, address in result.all():
        out.setdefault((member_id, vlan_id), []).append(str(address))
    return out


async def _prefix_filters(
    session: AsyncSession, member_ids: set[uuid.UUID], af: int
) -> dict[uuid.UUID, MemberPrefixFilter]:
    """Filtros de prefijos de esos miembros para esa familia, en una sola consulta"""
    if not member_ids:
        return {}
    stmt = select(MemberPrefixFilter).where(
        MemberPrefixFilter.member_id.in_(member_ids),
        MemberPrefixFilter.af == af,
    )
    result = await session.execute(stmt)
    return {pf.member_id: pf for pf in result.scalars()}
```

- [ ] **Step 6: Reescribir el armado del contexto en `build_peers`**

`build_peers` tiene que traer tambien `TrunkVLAN.vlan_id` y `Trunk.member_id` en el
`select`, y despues del loop de filas:

```python
    member_ids = {member.id for _s, member, _ip in rows}
    ips_by_member_vlan = await _member_vlan_ips(session, route_server_id, af)
    filters_by_member = await _prefix_filters(session, member_ids, af)

    for bgp_session, member, peer_ip, vlan_id in rows:
        peer_ip_str = str(peer_ip)
        slug = _build_peer_slug(member.short_name, peer_ip_str, af)
        base = slug
        counter = 2
        while slug in seen_slugs:
            suffix = f"_{counter}"
            slug = base[: PEER_SLUG_MAX_LEN - len(suffix)] + suffix
            counter += 1
        seen_slugs.add(slug)

        pf = filters_by_member.get(member.id)
        origin_asns = tuple(pf.origin_asns) if pf and pf.origin_asns else (member.asn,)
        prefixes = tuple(pf.prefixes) if pf and pf.prefixes else None
        all_ips = ips_by_member_vlan.get((member.id, vlan_id), [str(peer_ip)])

        peers.append(
            PeerContext(
                slug=slug,
                member_name=member.name,
                member_short_name=member.short_name,
                member_type_community=member_type_community(member.member_type),
                peer_ip=str(peer_ip),
                all_peer_ips=tuple(all_ips),
                peer_asn=member.asn,
                origin_asns=origin_asns,
                prefixes=prefixes,
                max_prefixes=bgp_session.max_prefixes,
                af=af,
            )
        )
```

Nota defensiva: `origin_asns` cae al ASN del miembro tanto si no hay fila como si
la fila tiene la lista vacia. Una lista vacia rendereada como `int set allas = [];`
haria que BIRD marque **todas** las rutas del miembro como filtradas por origen.

- [ ] **Step 7: Correr todos los tests del generador**

Run: `uv run pytest tests/test_config_generation.py -v`
Expected: los tests nuevos PASS. Los viejos que asertan sobre `protocol_name` fallan y se arreglan en la Task 10, cuando se reescriben contra el set nuevo

- [ ] **Step 8: Commit**

```bash
uv run ruff check src/ tests/ && uv run mypy src/
git add src/ixforge/services/config_generation.py tests/test_config_generation.py
git commit -m "feat: contexto de peer con allips, origen permitido y filtro de prefijos"
```

---

### Task 6: Contexto de peers no-miembro y de RPKI

**Files:**
- Modify: `src/ixforge/services/config_generation.py`
- Test: `tests/test_config_generation.py`

**Interfaces:**
- Consumes: `RouteServerPeer`, `RPKIServer`, `RPKIPolicy` (Task 1)
- Produces: `RSPeerContext`, `build_rs_peers(session, route_server_id, af) -> list[RSPeerContext]`, `RouteServerContext` con `passive_sessions`, `rpki_enabled`, `rpki_policy`, `rpki_servers`

- [ ] **Step 1: Escribir los tests que fallan**

```python
async def test_build_rs_peers_splits_by_family(db_session, ixp):
    """El af sale de la IP, no de una columna"""
    from ixforge.enums import RouteServerPeerType
    from ixforge.models.route_server_peer import RouteServerPeer
    from ixforge.services.config_generation import build_rs_peers

    rs = await _setup_route_server(db_session, ixp)
    db_session.add_all([
        RouteServerPeer(
            ixp_id=ixp.id, route_server_id=rs.id, name="PIT v4",
            peer_ip="192.0.2.5", peer_asn=64166,
            peer_type=RouteServerPeerType.upstream, mark_community="64166:9999",
        ),
        RouteServerPeer(
            ixp_id=ixp.id, route_server_id=rs.id, name="PIT v6",
            peer_ip="2001:db8::5", peer_asn=64166,
            peer_type=RouteServerPeerType.upstream, mark_community="64166:9999",
        ),
    ])
    await db_session.flush()

    v4 = await build_rs_peers(db_session, rs.id, af=4)
    v6 = await build_rs_peers(db_session, rs.id, af=6)

    assert [p.peer_ip for p in v4] == ["192.0.2.5"]
    assert [p.peer_ip for p in v6] == ["2001:db8::5"]
    assert v4[0].mark_community == "64166:9999"


async def test_rs_peer_local_asn_defaults_to_ixp_asn(db_session, ixp):
    from ixforge.enums import RouteServerPeerType
    from ixforge.models.route_server_peer import RouteServerPeer
    from ixforge.services.config_generation import build_rs_peers

    rs = await _setup_route_server(db_session, ixp)
    db_session.add(
        RouteServerPeer(
            ixp_id=ixp.id, route_server_id=rs.id, name="colector",
            peer_ip="192.0.2.17", peer_asn=212232,
            peer_type=RouteServerPeerType.collector,
        )
    )
    await db_session.flush()

    peers = await build_rs_peers(db_session, rs.id, af=4)

    assert peers[0].local_asn == ixp.asn


async def test_rs_peer_admin_state_down_is_excluded(db_session, ixp):
    from ixforge.enums import BGPAdminState, RouteServerPeerType
    from ixforge.models.route_server_peer import RouteServerPeer
    from ixforge.services.config_generation import build_rs_peers

    rs = await _setup_route_server(db_session, ixp)
    db_session.add(
        RouteServerPeer(
            ixp_id=ixp.id, route_server_id=rs.id, name="apagado",
            peer_ip="192.0.2.99", peer_asn=65000,
            peer_type=RouteServerPeerType.special,
            admin_state=BGPAdminState.down,
        )
    )
    await db_session.flush()

    assert await build_rs_peers(db_session, rs.id, af=4) == []


async def test_rs_context_collects_applicable_rpki_servers(db_session, ixp):
    """Un servidor con route_server_id NULL aplica a todos los RS del IXP"""
    from ixforge.models.rpki_server import RPKIServer
    from ixforge.services.config_generation import build_rs_context

    rs = await _setup_route_server(db_session, ixp)
    other = await _setup_route_server(db_session, ixp, name="rs2", ip_v4="192.0.2.251")
    db_session.add_all([
        RPKIServer(ixp_id=ixp.id, name="global", host="10.0.0.1"),
        RPKIServer(ixp_id=ixp.id, name="solo-rs2", host="10.0.0.2", route_server_id=other.id),
    ])
    await db_session.flush()

    ctx = await build_rs_context(db_session, rs, ixp.asn)

    assert [s.name for s in ctx.rpki_servers] == ["global"]
```

- [ ] **Step 2: Correr los tests y verificar que fallan**

Run: `uv run pytest tests/test_config_generation.py -v -k "rs_peer or rpki"`
Expected: FAIL con `ImportError: cannot import name 'build_rs_peers'`

- [ ] **Step 3: Implementar `RSPeerContext` y `build_rs_peers`**

```python
@dataclass(frozen=True)
class RSPeerContext:
    """Template context para una sesion que no pertenece a un miembro."""

    slug: str
    name: str
    description: str | None
    peer_ip: str
    peer_asn: int
    local_asn: int
    passive: bool
    peer_type: str
    mark_community: str | None
    max_prefixes: int | None
    af: int


async def build_rs_peers(
    session: AsyncSession, route_server_id: uuid.UUID, af: int
) -> list[RSPeerContext]:
    """Peers de upstream, colectores y especiales de un route server

    La familia se deriva de peer_ip: el modelo no guarda af para no tener dos
    fuentes de verdad
    """
    stmt = (
        select(RouteServerPeer)
        .where(
            RouteServerPeer.route_server_id == route_server_id,
            RouteServerPeer.admin_state == BGPAdminState.up,
        )
        .order_by(RouteServerPeer.peer_asn, RouteServerPeer.peer_ip)
    )
    result = await session.execute(stmt)

    ixp_asn_stmt = (
        select(IXP.asn)
        .join(RouteServer, RouteServer.ixp_id == IXP.id)
        .where(RouteServer.id == route_server_id)
    )
    ixp_asn = (await session.execute(ixp_asn_stmt)).scalar_one()

    peers: list[RSPeerContext] = []
    seen_slugs: set[str] = set()
    for peer in result.scalars():
        peer_ip = str(peer.peer_ip)
        if ipaddress.ip_address(peer_ip).version != af:
            continue

        slug = _build_peer_slug(peer.name, peer_ip, af)
        base = slug
        counter = 2
        while slug in seen_slugs:
            suffix = f"_{counter}"
            slug = base[: PEER_SLUG_MAX_LEN - len(suffix)] + suffix
            counter += 1
        seen_slugs.add(slug)

        peers.append(
            RSPeerContext(
                slug=slug,
                name=peer.name,
                description=peer.description,
                peer_ip=peer_ip,
                peer_asn=peer.peer_asn,
                local_asn=peer.local_asn if peer.local_asn is not None else ixp_asn,
                passive=peer.passive,
                peer_type=peer.peer_type.value,
                mark_community=peer.mark_community,
                max_prefixes=peer.max_prefixes,
                af=af,
            )
        )
    return peers
```

Mover el `import ipaddress` que hoy esta adentro de `build_rs_context` al tope del
modulo, porque ahora lo usan dos funciones, y agregar `or_` al import de sqlalchemy
y los modelos `RouteServerPeer`, `RPKIServer` y `MemberPrefixFilter` a los imports
del modulo.

- [ ] **Step 4: Extender `RouteServerContext`**

Agregar al dataclass:

```python
    passive_sessions: bool
    rpki_enabled: bool
    rpki_policy: str
    rpki_servers: tuple["RPKIServerContext", ...]
```

y el contexto del servidor RTR:

```python
@dataclass(frozen=True)
class RPKIServerContext:
    """Template context para un servidor RTR."""

    slug: str
    name: str
    host: str
    port: int
    transport: str
    refresh_time: int | None
    retry_time: int | None
    expire_time: int | None
```

Al final de `build_rs_context`, antes del `return`:

```python
    rpki_stmt = (
        select(RPKIServer)
        .where(
            RPKIServer.ixp_id == rs.ixp_id,
            or_(
                RPKIServer.route_server_id.is_(None),
                RPKIServer.route_server_id == rs.id,
            ),
        )
        .order_by(RPKIServer.name)
    )
    rpki_result = await session.execute(rpki_stmt)
    rpki_servers = tuple(
        RPKIServerContext(
            slug=re.sub(r"[^a-zA-Z0-9_]", "_", srv.name)[:PEER_SLUG_MAX_LEN],
            name=srv.name,
            host=srv.host,
            port=srv.port,
            transport=srv.transport.value,
            refresh_time=srv.refresh_time,
            retry_time=srv.retry_time,
            expire_time=srv.expire_time,
        )
        for srv in rpki_result.scalars()
    )
```

y pasarlos al `RouteServerContext` junto con `passive_sessions=rs.passive_sessions`,
`rpki_enabled=rs.rpki_enabled` y `rpki_policy=rs.rpki_policy.value`.

- [ ] **Step 5: Correr los tests y verificar que pasan**

Run: `uv run pytest tests/test_config_generation.py -v -k "rs_peer or rpki"`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
uv run ruff check src/ tests/ && uv run mypy src/
git add src/ixforge/services/config_generation.py tests/test_config_generation.py
git commit -m "feat: contexto de peers no-miembro y de servidores RPKI"
```

---

### Task 7: Template raiz, render unico y funciones base

Deliverable: un IXP sin peers genera un config que `bird -p` acepta.

**Files:**
- Create: `docker/bird-validator/Dockerfile`
- Create: `tests/bird_validator.py`
- Modify: `pyproject.toml` (marker de pytest)
- Modify: `src/ixforge/services/default_templates.py`
- Modify: `src/ixforge/services/config_generation.py`
- Modify: `src/ixforge/services/template_filters.py`
- Test: `tests/test_config_generation.py`, `tests/test_template_filters.py`

**Interfaces:**
- Consumes: los contextos de las Tasks 5 y 6
- Produces: template `bird.conf.j2` como unico punto de entrada; `generate_config` con un solo render; filtro Jinja `bird_community`; helper `tests.bird_validator.assert_bird_parses(config)`

- [ ] **Step 1: Crear la imagen de validacion**

`docker/bird-validator/Dockerfile`:

```dockerfile
FROM debian:bookworm-slim
RUN apt-get update \
    && apt-get install -y --no-install-recommends bird2 \
    && rm -rf /var/lib/apt/lists/*
ENTRYPOINT ["bird"]
```

Construirla una vez:

```bash
docker build -t ixforge-bird-validator:2 docker/bird-validator/
docker run --rm ixforge-bird-validator:2 --version
```
Expected: imprime `BIRD version 2.x`

- [ ] **Step 2: Escribir el helper de validacion**

`tests/bird_validator.py`:

```python
"""Validacion de configs BIRD con bird -p en docker.

Los tests que lo usan se saltean si docker o la imagen no estan disponibles,
para que la suite siga corriendo en una maquina sin docker
"""

import shutil
import subprocess
import tempfile
from pathlib import Path

BIRD_IMAGE = "ixforge-bird-validator:2"


def bird_available() -> bool:
    """True si docker existe y la imagen del validador esta construida"""
    if shutil.which("docker") is None:
        return False
    result = subprocess.run(
        ["docker", "image", "inspect", BIRD_IMAGE],
        capture_output=True,
        check=False,
    )
    return result.returncode == 0


def assert_bird_parses(config: str) -> None:
    """Corre bird -p sobre el config y falla con la salida real si lo rechaza"""
    with tempfile.TemporaryDirectory() as tmpdir:
        conf_path = Path(tmpdir) / "bird.conf"
        conf_path.write_text(config, encoding="utf-8")
        result = subprocess.run(
            [
                "docker", "run", "--rm",
                "-v", f"{tmpdir}:/conf:ro",
                BIRD_IMAGE, "-p", "-c", "/conf/bird.conf",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
    if result.returncode != 0:
        numbered = "\n".join(
            f"{i:4d}  {line}" for i, line in enumerate(config.splitlines(), start=1)
        )
        raise AssertionError(
            f"bird -p rechazo el config:\n{result.stdout}{result.stderr}\n\n{numbered}"
        )
```

En `pyproject.toml`, bajo `[tool.pytest.ini_options]`:

```toml
markers = ["bird: requiere la imagen ixforge-bird-validator:2"]
```

- [ ] **Step 3: Escribir el test que falla**

En `tests/test_config_generation.py`:

```python
import pytest

from tests.bird_validator import assert_bird_parses, bird_available

requires_bird = pytest.mark.skipif(
    not bird_available(), reason="falta la imagen ixforge-bird-validator:2"
)


async def test_config_has_single_globals_section(db_session, ixp):
    """Un solo daemon: los globals no pueden aparecer dos veces"""
    from ixforge.services.config_generation import generate_config

    rs = await _setup_route_server(db_session, ixp)
    cv = await generate_config(db_session, rs.id, ixp.id)

    assert cv.content.count("protocol device") == 1
    assert cv.content.count("define routeserverasn") == 1
    assert cv.content.count("router id") == 1


async def test_config_defines_euroix_communities(db_session, ixp):
    from ixforge.services.config_generation import generate_config

    rs = await _setup_route_server(db_session, ixp)
    cv = await generate_config(db_session, rs.id, ixp.id)

    assert "define IXP_LC_FILTERED_BOGON " in cv.content
    assert "define IXP_LC_FILTERED_NEXT_HOP_NOT_PEER_IP " in cv.content
    assert "define IXP_LC_INFO_RPKI_NOT_CHECKED " in cv.content
    assert "filter f_export_to_master" in cv.content
    assert "function ixp_community_filter" in cv.content


async def test_config_defines_source_address_per_family(db_session, ixp):
    """Sin source address, un RS con mas de una IP en la LAN elige origen por
    lookup de ruta, que es ambiguo
    """
    from ixforge.services.config_generation import generate_config

    rs = await _setup_route_server(db_session, ixp)
    cv = await generate_config(db_session, rs.id, ixp.id)

    assert "define routeserveraddress4 = 192.0.2.250;" in cv.content
    assert "define routeserveraddress6 = 2001:db8::250;" in cv.content
    assert "source address routeserveraddress4;" in cv.content
    assert "source address routeserveraddress6;" in cv.content


@requires_bird
async def test_empty_config_parses(db_session, ixp):
    from ixforge.services.config_generation import generate_config

    rs = await _setup_route_server(db_session, ixp)
    cv = await generate_config(db_session, rs.id, ixp.id)

    assert_bird_parses(cv.content)


@requires_bird
async def test_v4_only_config_parses(db_session, ixp):
    from ixforge.services.config_generation import generate_config

    rs = await _setup_route_server(db_session, ixp, name="rs-v4", ip_v6=None)
    cv = await generate_config(db_session, rs.id, ixp.id)

    assert "routeserveraddress6" not in cv.content
    assert_bird_parses(cv.content)
```

En `tests/test_template_filters.py`:

```python
def test_bird_community_splits_pair():
    from ixforge.services.template_filters import bird_community

    assert bird_community("64166:9999") == "64166, 9999"


def test_bird_community_rejects_garbage():
    import pytest

    from ixforge.services.template_filters import bird_community

    for bad in ("64166", "a:b", "64166:9999:1", "", "-1:5"):
        with pytest.raises(ValueError):
            bird_community(bad)
```

- [ ] **Step 4: Correr los tests y verificar que fallan**

Run: `uv run pytest tests/test_config_generation.py tests/test_template_filters.py -v -k "globals or euroix_communities or source_address or parses or bird_community"`
Expected: FAIL, `TemplateNotFound: bird.conf.j2` y `ImportError` para `bird_community`

- [ ] **Step 5: Agregar el filtro `bird_community`**

En `src/ixforge/services/template_filters.py`:

```python
def bird_community(value: str) -> str:
    """Convierte "64166:9999" en "64166, 9999" para usar dentro de parentesis

    Valida agresivamente porque el resultado se inyecta en un config que maneja
    infraestructura critica
    """
    parts = value.split(":")
    if len(parts) != 2:
        raise ValueError(f"community invalida, se esperaba asn:value: {value!r}")
    try:
        asn, val = int(parts[0]), int(parts[1])
    except ValueError as exc:
        raise ValueError(f"community con partes no numericas: {value!r}") from exc
    if not (0 <= asn <= 4294967295) or not (0 <= val <= 65535):
        raise ValueError(f"community fuera de rango: {value!r}")
    return f"{asn}, {val}"
```

Registrarlo en `src/ixforge/services/template_env.py` junto a los otros:
`env.filters["bird_community"] = bird_community`

- [ ] **Step 6: Reescribir el set de templates base**

En `src/ixforge/services/default_templates.py`, `DEFAULT_TEMPLATES` pasa a tener
estas entradas (las de peers y RPKI llegan en las Tasks 8 y 9).

`bird.conf.j2`, `is_protected: True`:

```jinja
# BIRD 2.x configuration for {{ route_server.name }}
# Generated by IXForge Core at {{ generated_at }}
# Config hash: {{ config_hash }}
# DO NOT EDIT MANUALLY - this file is managed by IXForge

timeformat base     iso long;
timeformat log      iso long;
timeformat protocol iso long;
timeformat route    iso long;

log syslog all;
log stderr { error, fatal };

define routeserverasn = {{ route_server.asn }};
{% if route_server.ip_v4 %}
define routeserveraddress4 = {{ route_server.ip_v4 }};
{% endif %}
{% if route_server.ip_v6 %}
define routeserveraddress6 = {{ route_server.ip_v6 }};
{% endif %}

router id {{ route_server.router_id }};

# ignore interface up/down events
protocol device { }

{% include "functions/communities.j2" %}
{% include "filters/bogons.j2" %}
{% include "functions/common.j2" %}
{% include "functions/transit.j2" %}
{% include "functions/announce_control.j2" %}
{% include "filters/to_master.j2" %}
{% if route_server.rpki_enabled %}
{% include "protocols/rpki.j2" %}
{% endif %}
{% if route_server.ip_v4 %}
{% with af = 4 %}
{% include "protocols/rs_client.j2" %}
{% for peer in peers_v4 %}
{% include "protocols/bgp_peer.j2" %}
{% endfor %}
{% for peer in rs_peers_v4 %}
{% include "protocols/rs_peer.j2" %}
{% endfor %}
{% endwith %}
{% endif %}
{% if route_server.ip_v6 %}
{% with af = 6 %}
{% include "protocols/rs_client.j2" %}
{% for peer in peers_v6 %}
{% include "protocols/bgp_peer.j2" %}
{% endfor %}
{% for peer in rs_peers_v6 %}
{% include "protocols/rs_peer.j2" %}
{% endfor %}
{% endwith %}
{% endif %}
```

No lleva `protocol kernel`: un route server no instala rutas en el kernel y el
config que corre hoy en produccion tampoco lo tiene.

`functions/communities.j2`, `is_protected: False`:

```jinja
# Communities del esquema euro-ix
# https://github.com/euro-ix/rs-workshop-july-2017/wiki/Route-Server-BGP-Community-usage

# Filtradas: el pipe hacia master descarta todo lo que lleve (routeserverasn, 1101, *)
define IXP_LC_FILTERED_PREFIX_LEN_TOO_LONG      = ( routeserverasn, 1101, 1  );
define IXP_LC_FILTERED_PREFIX_LEN_TOO_SHORT     = ( routeserverasn, 1101, 2  );
define IXP_LC_FILTERED_BOGON                    = ( routeserverasn, 1101, 3  );
define IXP_LC_FILTERED_BOGON_ASN                = ( routeserverasn, 1101, 4  );
define IXP_LC_FILTERED_AS_PATH_TOO_LONG         = ( routeserverasn, 1101, 5  );
define IXP_LC_FILTERED_AS_PATH_TOO_SHORT        = ( routeserverasn, 1101, 6  );
define IXP_LC_FILTERED_FIRST_AS_NOT_PEER_AS     = ( routeserverasn, 1101, 7  );
define IXP_LC_FILTERED_NEXT_HOP_NOT_PEER_IP     = ( routeserverasn, 1101, 8  );
define IXP_LC_FILTERED_IRRDB_PREFIX_FILTERED    = ( routeserverasn, 1101, 9  );
define IXP_LC_FILTERED_IRRDB_ORIGIN_AS_FILTERED = ( routeserverasn, 1101, 10 );
define IXP_LC_FILTERED_PREFIX_NOT_IN_ORIGIN_AS  = ( routeserverasn, 1101, 11 );
define IXP_LC_FILTERED_RPKI_UNKNOWN             = ( routeserverasn, 1101, 12 );
define IXP_LC_FILTERED_RPKI_INVALID             = ( routeserverasn, 1101, 13 );
define IXP_LC_FILTERED_TRANSIT_FREE_ASN         = ( routeserverasn, 1101, 14 );
define IXP_LC_FILTERED_TOO_MANY_COMMUNITIES     = ( routeserverasn, 1101, 15 );

# Informativas
define IXP_LC_INFO_RPKI_VALID       = ( routeserverasn, 1000, 1  );
define IXP_LC_INFO_RPKI_UNKNOWN     = ( routeserverasn, 1000, 2  );
define IXP_LC_INFO_RPKI_NOT_CHECKED = ( routeserverasn, 1000, 3  );
define IXP_LC_INFO_RPKI_INVALID     = ( routeserverasn, 1000, 4  );

define IXP_LC_INFO_IRRDB_VALID         = ( routeserverasn, 1001, 1  );
define IXP_LC_INFO_IRRDB_NOT_CHECKED   = ( routeserverasn, 1001, 2  );
define IXP_LC_INFO_IRRDB_MORE_SPECIFIC = ( routeserverasn, 1001, 3  );

define IXP_LC_INFO_IRRDB_FILTERED_LOOSE  = ( routeserverasn, 1001, 1000 );
define IXP_LC_INFO_IRRDB_FILTERED_STRICT = ( routeserverasn, 1001, 1001 );
define IXP_LC_INFO_IRRDB_PREFIX_EMPTY    = ( routeserverasn, 1001, 1002 );

define IXP_LC_INFO_SAME_AS_NEXT_HOP = ( routeserverasn, 1001, 1200 );
```

`IXP_LC_INFO_RPKI_INVALID` es un agregado nuestro al esquema: sin el, el modo
`info_only` no tiene con que marcar una ruta invalida.

`filters/bogons.j2`, `is_protected: False`: reemplaza el contenido actual por las
listas del config en produccion, que son mas completas que las que hay hoy:

```jinja
# Martians, listas del patron euro-ix

define MARTIANS_V4 = [
    0.0.0.0/32-,            # rfc5735 Special Use IPv4 Addresses
    0.0.0.0/0{0,7},         # rfc1122 3.2.1.3
    10.0.0.0/8+,            # rfc1918
    100.64.0.0/10+,         # rfc6598 Shared Address Space
    127.0.0.0/8+,           # rfc1122 loopback
    169.254.0.0/16+,        # rfc3927 link-local
    172.16.0.0/12+,         # rfc1918
    192.0.0.0/24+,          # rfc6890
    192.0.2.0/24+,          # rfc5737 TEST-NET-1
    192.168.0.0/16+,        # rfc1918
    198.18.0.0/15+,         # rfc2544 benchmarking
    198.51.100.0/24+,       # rfc5737 TEST-NET-2
    203.0.113.0/24+,        # rfc5737 TEST-NET-3
    224.0.0.0/4+,           # rfc1112 multicast
    240.0.0.0/4+            # rfc6890 reservado
];

define MARTIANS_V6 = [
    ::/0,                   # default
    ::/96,                  # IPv4-compatible, deprecado por rfc4291
    ::/128,                 # unspecified
    ::1/128,                # loopback
    ::ffff:0.0.0.0/96+,     # IPv4-mapped
    ::224.0.0.0/100+,
    ::127.0.0.0/104+,
    ::0.0.0.0/104+,
    ::255.0.0.0/104+,
    0000::/8+,
    0200::/7+,              # OSI NSAP-mapped, deprecado por rfc4048
    3ffe::/16+,             # 6bone
    2001:db8::/32+,         # rfc3849 documentacion
    2002:e000::/20+,        # 6to4 invalido (multicast)
    2002:7f00::/24+,        # 6to4 invalido (loopback)
    2002:0000::/24+,        # 6to4 invalido (default)
    2002:ff00::/24+,
    2002:0a00::/24+,        # 6to4 invalido (10/8)
    2002:ac10::/28+,        # 6to4 invalido (172.16/12)
    2002:c0a8::/32+,        # 6to4 invalido (192.168/16)
    fc00::/7+,              # rfc4193 ULA
    fe80::/10+,             # link-local
    fec0::/10+,             # site-local, deprecado por rfc3879
    ff00::/8+               # multicast
];
```

`functions/common.j2`, `is_protected: False`:

```jinja
# Funciones comunes

function avoid_martians4() {
    if net ~ MARTIANS_V4 then return false;
    return true;
}

function avoid_martians6() {
    if net ~ MARTIANS_V6 then return false;
    return true;
}

function honor_graceful_shutdown() {
    if (65535, 0) ~ bgp_community then {
        bgp_local_pref = 0;
    }
}
```

`functions/transit.j2`, `is_protected: False`:

```jinja
# ASNs transit-free, inspirado en http://bgpfilterguide.nlnog.net/guides/no_transit_leaks/
# Esta lista envejece: es editable a proposito para poder actualizarla sin un release

define TRANSIT_ASNS = [ 174, 701, 1299, 2914, 3257, 3320, 3356, 3491, 4134, 5511, 6453, 6461, 6762, 6830, 7018 ];

function filter_has_transit_path()
int set transit_asns;
{
    transit_asns = TRANSIT_ASNS;
    if (bgp_path ~ transit_asns) then {
        bgp_large_community.add( IXP_LC_FILTERED_TRANSIT_FREE_ASN );
        return true;
    }

    return false;
}
```

`functions/announce_control.j2`, `is_protected: False`:

```jinja
# Control de anuncio selectivo por communities
# Se evalua en el pipe master -> tabla del peer, o sea decide a quien se le
# anuncia cada ruta segun lo que el miembro que la origino haya pedido

function ixp_community_filter(int peerasn)
{
    # las rutas que no vienen de BGP no se propagan
    if !(source = RTS_BGP) then
        return false;

    # 1. no anunciar a un peer especifico, maxima prioridad
    if (peerasn <= 65535) && (0, peerasn) ~ bgp_community then
        return false;
    if (routeserverasn, 0, peerasn) ~ bgp_large_community then
        return false;

    # 2. no anunciar a nadie, con excepciones
    bool deny_all_std = (0, routeserverasn) ~ bgp_community;
    bool deny_all_lrg = (routeserverasn, 0, 0) ~ bgp_large_community;

    if deny_all_std || deny_all_lrg then {
        # excepcion: anunciar a todos
        if (routeserverasn, routeserverasn) ~ bgp_community then
            return true;
        if (routeserverasn, 1, 0) ~ bgp_large_community then
            return true;

        # excepcion: anunciar a este peer
        if (peerasn <= 65535) && (routeserverasn, peerasn) ~ bgp_community then
            return true;
        if (routeserverasn, 1, peerasn) ~ bgp_large_community then
            return true;

        return false;
    }

    # 3. por defecto se anuncia
    return true;
}
```

`filters/to_master.j2`, `is_protected: False`:

```jinja
# El unico lugar donde se descarta: todo lo marcado como filtrado muere aca
filter f_export_to_master
{
    if bgp_large_community ~ [( routeserverasn, 1101, * )] then reject;
    accept;
}
```

Borrar del set `bird_v4.conf.j2`, `bird_v6.conf.j2`, `protocols/bgp_peer.j2`
(se reescribe en la Task 8), `protocols/static.j2` y `filters/communities.j2`.

- [ ] **Step 7: Pasar `generate_config` a un solo render**

En `src/ixforge/services/config_generation.py`, reemplazar el bloque de dos renders
y la llamada a `_combine_configs` por:

```python
    v4_peers = await build_peers(session, route_server_id, af=4)
    v6_peers = await build_peers(session, route_server_id, af=6)
    v4_rs_peers = await build_rs_peers(session, route_server_id, af=4)
    v6_rs_peers = await build_rs_peers(session, route_server_id, af=6)

    template = env.get_template("bird.conf.j2")
    combined = template.render(
        route_server=rs_context,
        peers_v4=v4_peers,
        peers_v6=v6_peers,
        rs_peers_v4=v4_rs_peers,
        rs_peers_v6=v6_rs_peers,
        generated_at=generated_at_str,
        config_hash="",
    )
```

Borrar `_combine_configs`, que queda sin uso.

- [ ] **Step 8: Correr los tests**

Run: `uv run pytest tests/test_config_generation.py tests/test_template_filters.py -v -k "globals or euroix_communities or source_address or parses or bird_community"`
Expected: PASS

Si `bird -p` rechaza `net ~ MARTIANS_V6` conviviendo con `MARTIANS_V4` en el mismo
daemon por chequeo de tipos, la salida del helper dice exactamente en que linea.
El arreglo en ese caso es un unico `define MARTIANS` con las dos familias adentro y
una sola `avoid_martians()`: BIRD 2 acepta sets mixtos porque `net` es un tipo
union. Ajustar `common.j2` y `bgp_peer.j2` en consecuencia.

- [ ] **Step 9: Commit**

```bash
uv run ruff check src/ tests/ && uv run mypy src/
git add docker/bird-validator/ tests/bird_validator.py pyproject.toml src/ tests/
git commit -m "feat: template raiz euro-ix y render unico de ambas familias"
```

---

### Task 8: Templates de peers de miembros

Deliverable: un IXP con miembros genera el bloque completo de tabla, filtros,
protocolo y pipe por peer, y `bird -p` lo acepta.

**Files:**
- Modify: `src/ixforge/services/default_templates.py`
- Test: `tests/test_config_generation.py`

**Interfaces:**
- Consumes: `PeerContext` (Task 5), `bird.conf.j2` (Task 7)
- Produces: templates `protocols/rs_client.j2` y `protocols/bgp_peer.j2`

- [ ] **Step 1: Escribir los tests que fallan**

```python
async def test_peer_block_has_all_five_symbols(db_session, ixp):
    from ixforge.services.config_generation import generate_config

    rs = await _setup_route_server(db_session, ixp)
    await _setup_member_peer(db_session, ixp, rs, asn=61455, ipv4="192.0.2.16")
    cv = await generate_config(db_session, rs.id, ixp.id)

    peers = await build_peers(db_session, rs.id, af=4)
    slug = peers[0].slug
    for symbol in (
        f"ipv4 table t_{slug};",
        f"filter f_import_{slug}",
        f"filter f_export_{slug}",
        f"protocol bgp pb_{slug} from tb_rsclient_v4",
        f"protocol pipe pp_{slug}",
    ):
        assert symbol in cv.content


async def test_peer_import_filter_marks_instead_of_rejecting(db_session, ixp):
    """El patron euro-ix nunca rechaza en el import: marca y acepta"""
    from ixforge.services.config_generation import generate_config

    rs = await _setup_route_server(db_session, ixp)
    await _setup_member_peer(db_session, ixp, rs, asn=61455, ipv4="192.0.2.16")
    cv = await generate_config(db_session, rs.id, ixp.id)

    import_block = cv.content.split("filter f_import_")[1].split("filter f_export_")[0]
    assert "reject" not in import_block
    assert "IXP_LC_FILTERED_BOGON" in import_block
    assert "IXP_LC_FILTERED_FIRST_AS_NOT_PEER_AS" in import_block
    assert "IXP_LC_FILTERED_NEXT_HOP_NOT_PEER_IP" in import_block


async def test_peer_allips_lists_every_member_ip(db_session, ixp):
    from ixforge.services.config_generation import generate_config

    rs = await _setup_route_server(db_session, ixp)
    member = await _setup_member_peer(db_session, ixp, rs, asn=273973, ipv4="192.0.2.11")
    await _add_second_connection(db_session, ixp, rs, member, ipv4="192.0.2.12")
    cv = await generate_config(db_session, rs.id, ixp.id)

    assert "allips = [ 192.0.2.11, 192.0.2.12 ];" in cv.content


async def test_peer_without_prefix_filter_omits_allnet(db_session, ixp):
    """Sin filtro de prefijos no se declara allnet, para no dejar un set vacio
    que marcaria todas las rutas del miembro como filtradas
    """
    from ixforge.services.config_generation import generate_config

    rs = await _setup_route_server(db_session, ixp)
    await _setup_member_peer(db_session, ixp, rs, asn=61455, ipv4="192.0.2.16")
    cv = await generate_config(db_session, rs.id, ixp.id)

    assert "prefix set allnet;" not in cv.content
    assert "IXP_LC_INFO_IRRDB_NOT_CHECKED" in cv.content


async def test_peer_with_prefix_filter_renders_allnet(db_session, ixp):
    from ixforge.models.member_prefix_filter import MemberPrefixFilter
    from ixforge.services.config_generation import generate_config

    rs = await _setup_route_server(db_session, ixp)
    member = await _setup_member_peer(db_session, ixp, rs, asn=273973, ipv4="192.0.2.11")
    db_session.add(
        MemberPrefixFilter(
            ixp_id=ixp.id, member_id=member.id, af=4,
            prefixes=["45.170.100.0/24", "45.238.179.0/24"],
        )
    )
    await db_session.flush()
    cv = await generate_config(db_session, rs.id, ixp.id)

    assert "prefix set allnet;" in cv.content
    assert "allnet = [ 45.170.100.0/24, 45.238.179.0/24 ];" in cv.content
    assert "IXP_LC_FILTERED_IRRDB_PREFIX_FILTERED" in cv.content


async def test_rs_client_template_has_rs_client_and_passive(db_session, ixp):
    """Sin rs client BIRD mete su ASN en el AS path: no es un route server"""
    from ixforge.services.config_generation import generate_config

    rs = await _setup_route_server(db_session, ixp)
    cv = await generate_config(db_session, rs.id, ixp.id)

    assert "rs client;" in cv.content
    assert "passive yes;" in cv.content
    assert "interpret communities off;" in cv.content
    assert "connect delay time 30;" in cv.content


async def test_passive_sessions_false_omits_passive(db_session, ixp):
    from ixforge.services.config_generation import generate_config

    rs = await _setup_route_server(db_session, ixp, name="rs-activo")
    rs.passive_sessions = False
    await db_session.flush()
    cv = await generate_config(db_session, rs.id, ixp.id)

    assert "passive yes;" not in cv.content


@requires_bird
async def test_config_with_peers_parses(db_session, ixp):
    from ixforge.models.member_prefix_filter import MemberPrefixFilter
    from ixforge.services.config_generation import generate_config

    rs = await _setup_route_server(db_session, ixp)
    member = await _setup_member_peer(
        db_session, ixp, rs, asn=273973, ipv4="192.0.2.11", ipv6="2001:db8::11"
    )
    db_session.add(
        MemberPrefixFilter(
            ixp_id=ixp.id, member_id=member.id, af=4, prefixes=["45.170.100.0/24"]
        )
    )
    await db_session.flush()
    cv = await generate_config(db_session, rs.id, ixp.id)

    assert_bird_parses(cv.content)
```

- [ ] **Step 2: Correr los tests y verificar que fallan**

Run: `uv run pytest tests/test_config_generation.py -v -k "peer_block or import_filter_marks or allips or allnet or rs_client or passive or with_peers_parses"`
Expected: FAIL, `TemplateNotFound: protocols/rs_client.j2`

- [ ] **Step 3: Agregar `protocols/rs_client.j2`**

```jinja
template bgp tb_rsclient_v{{ af }} {
    local as routeserverasn;
{% if af == 4 %}
    source address routeserveraddress4;
{% else %}
    source address routeserveraddress6;
{% endif %}
{% if route_server.passive_sessions %}
    passive yes;
{% endif %}

    # le da tiempo al RTR a poblarse antes de que levanten las sesiones
    connect delay time 30;

    # pass through de communities well-known de rfc1997
    interpret communities off;

{% if af == 4 %}
    ipv4 {
        export all;
    };
{% else %}
    ipv6 {
        export all;
    };
{% endif %}

    rs client;
}
```

- [ ] **Step 4: Agregar `protocols/bgp_peer.j2`**

```jinja
# {{ peer.member_name | bird_str }} (AS{{ peer.peer_asn }}) en {{ peer.peer_ip }}
{% if af == 4 %}
ipv4 table t_{{ peer.slug }};
{% else %}
ipv6 table t_{{ peer.slug }};
{% endif %}

filter f_import_{{ peer.slug }}
{% if peer.prefixes %}
prefix set allnet;
{% endif %}
ip set allips;
int set allas;
{
{% if af == 4 %}
    if ( net ~ [ 0.0.0.0/0{25,32} ] ) then {
{% else %}
    if ( net ~ [ ::/0{49,128} ] ) then {
{% endif %}
        bgp_large_community.add( IXP_LC_FILTERED_PREFIX_LEN_TOO_LONG );
        accept;
    }

{% if af == 4 %}
    if !(avoid_martians4()) then {
{% else %}
    if !(avoid_martians6()) then {
{% endif %}
        bgp_large_community.add( IXP_LC_FILTERED_BOGON );
        accept;
    }

    if( bgp_path.len < 1 ) then {
        bgp_large_community.add( IXP_LC_FILTERED_AS_PATH_TOO_SHORT );
        accept;
    }

    if (bgp_path.first != {{ peer.peer_asn }} ) then {
        bgp_large_community.add( IXP_LC_FILTERED_FIRST_AS_NOT_PEER_AS );
        accept;
    }

    allips = [ {{ peer.all_peer_ips | join(', ') }} ];

    if !( from = bgp_next_hop ) then {
        if( bgp_next_hop ~ allips ) then {
            bgp_large_community.add( IXP_LC_INFO_SAME_AS_NEXT_HOP );
        } else {
            bgp_large_community.add( IXP_LC_FILTERED_NEXT_HOP_NOT_PEER_IP );
            accept;
        }
    }

    if filter_has_transit_path() then accept;

    if( bgp_path.len > 64 ) then {
        bgp_large_community.add( IXP_LC_FILTERED_AS_PATH_TOO_LONG );
        accept;
    }

    allas = [ {{ peer.origin_asns | join(', ') }} ];

    if !(bgp_path.last_nonaggregated ~ allas) then {
        bgp_large_community.add( IXP_LC_FILTERED_IRRDB_ORIGIN_AS_FILTERED );
        accept;
    }

{% if route_server.rpki_enabled %}
    if ( roa_check(roa_v{{ af }}, net, bgp_path.last) = ROA_VALID ) then {
        bgp_large_community.add( IXP_LC_INFO_RPKI_VALID );
    } else {
        if ( roa_check(roa_v{{ af }}, net, bgp_path.last) = ROA_INVALID ) then {
            bgp_large_community.add( IXP_LC_INFO_RPKI_INVALID );
{% if route_server.rpki_policy == 'reject_invalid' %}
            bgp_large_community.add( IXP_LC_FILTERED_RPKI_INVALID );
{% endif %}
        } else {
            bgp_large_community.add( IXP_LC_INFO_RPKI_UNKNOWN );
        }
    }
{% else %}
    bgp_large_community.add( IXP_LC_INFO_RPKI_NOT_CHECKED );
{% endif %}

{% if peer.prefixes %}
    allnet = [ {{ peer.prefixes | join(', ') }} ];

    if ! (net ~ allnet) then {
        bgp_large_community.add( IXP_LC_FILTERED_IRRDB_PREFIX_FILTERED );
        bgp_large_community.add( IXP_LC_INFO_IRRDB_FILTERED_STRICT );
        accept;
    } else {
        bgp_large_community.add( IXP_LC_INFO_IRRDB_VALID );
    }
{% else %}
    bgp_large_community.add( IXP_LC_INFO_IRRDB_NOT_CHECKED );
{% endif %}

    honor_graceful_shutdown();

{% if peer.member_type_community %}
    bgp_community.add( (routeserverasn, {{ peer.member_type_community }}) );
{% endif %}

    accept;
}

# el export strippea nuestras propias communities de filtrado y looking glass
filter f_export_{{ peer.slug }}
{
    bgp_large_community.delete( [( routeserverasn, *, * )] );
    accept;
}

protocol bgp pb_{{ peer.slug }} from tb_rsclient_v{{ af }} {
    description "{{ peer.member_name | bird_str }}";
    neighbor {{ peer.peer_ip }} as {{ peer.peer_asn }};

{% if af == 4 %}
    ipv4 {
{% else %}
    ipv6 {
{% endif %}
{% if peer.max_prefixes %}
        import limit {{ peer.max_prefixes }} action restart;
{% endif %}
        import filter f_import_{{ peer.slug }};
        table t_{{ peer.slug }};
        export filter f_export_{{ peer.slug }};
    };
}

protocol pipe pp_{{ peer.slug }} {
    description "Pipe for {{ peer.member_name | bird_str }}";
{% if af == 4 %}
    table master4;
{% else %}
    table master6;
{% endif %}
    peer table t_{{ peer.slug }};
    import filter f_export_to_master;
    export where ixp_community_filter({{ peer.peer_asn }});
}
```

- [ ] **Step 5: Correr los tests y verificar que pasan**

Run: `uv run pytest tests/test_config_generation.py -v -k "peer_block or import_filter_marks or allips or allnet or rs_client or passive or with_peers_parses"`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
uv run ruff check src/ tests/ && uv run mypy src/
git add src/ixforge/services/default_templates.py tests/test_config_generation.py
git commit -m "feat: templates de peer euro-ix con tabla, pipe y filtros por cliente"
```

---

### Task 9: Templates de RPKI y de peers no-miembro

**Files:**
- Modify: `src/ixforge/services/default_templates.py`
- Modify: `src/ixforge/services/rpki_servers.py` (creado en la Task 12, si esta task va antes se crea la validacion ahi)
- Test: `tests/test_config_generation.py`

**Interfaces:**
- Consumes: `RSPeerContext` y `RPKIServerContext` (Task 6)
- Produces: templates `protocols/rpki.j2` y `protocols/rs_peer.j2`

- [ ] **Step 1: Escribir los tests que fallan**

```python
async def test_rpki_disabled_marks_not_checked(db_session, ixp):
    from ixforge.services.config_generation import generate_config

    rs = await _setup_route_server(db_session, ixp)
    await _setup_member_peer(db_session, ixp, rs, asn=61455, ipv4="192.0.2.16")
    cv = await generate_config(db_session, rs.id, ixp.id)

    assert "protocol rpki" not in cv.content
    assert "roa_check" not in cv.content
    assert "IXP_LC_INFO_RPKI_NOT_CHECKED" in cv.content


async def test_rpki_info_only_checks_without_filtering(db_session, ixp):
    from ixforge.models.rpki_server import RPKIServer
    from ixforge.services.config_generation import generate_config

    rs = await _setup_route_server(db_session, ixp)
    rs.rpki_enabled = True
    db_session.add(RPKIServer(ixp_id=ixp.id, name="routinator", host="10.0.0.1"))
    await _setup_member_peer(db_session, ixp, rs, asn=61455, ipv4="192.0.2.16")
    await db_session.flush()
    cv = await generate_config(db_session, rs.id, ixp.id)

    assert "roa4 table roa_v4;" in cv.content
    assert 'remote "10.0.0.1" port 3323;' in cv.content
    assert "roa_check(roa_v4, net, bgp_path.last)" in cv.content
    assert "IXP_LC_INFO_RPKI_INVALID" in cv.content
    assert "IXP_LC_FILTERED_RPKI_INVALID" not in cv.content


async def test_rpki_reject_invalid_adds_filter_community(db_session, ixp):
    from ixforge.enums import RPKIPolicy
    from ixforge.models.rpki_server import RPKIServer
    from ixforge.services.config_generation import generate_config

    rs = await _setup_route_server(db_session, ixp)
    rs.rpki_enabled = True
    rs.rpki_policy = RPKIPolicy.reject_invalid
    db_session.add(RPKIServer(ixp_id=ixp.id, name="routinator", host="10.0.0.1"))
    await _setup_member_peer(db_session, ixp, rs, asn=61455, ipv4="192.0.2.16")
    await db_session.flush()
    cv = await generate_config(db_session, rs.id, ixp.id)

    assert "IXP_LC_FILTERED_RPKI_INVALID" in cv.content


async def test_rs_peer_upstream_block(db_session, ixp):
    from ixforge.enums import RouteServerPeerType
    from ixforge.models.route_server_peer import RouteServerPeer
    from ixforge.services.config_generation import build_rs_peers, generate_config

    rs = await _setup_route_server(db_session, ixp)
    db_session.add(
        RouteServerPeer(
            ixp_id=ixp.id, route_server_id=rs.id, name="PIT Chile",
            peer_ip="192.0.2.5", peer_asn=64166, local_asn=64166,
            peer_type=RouteServerPeerType.upstream, mark_community="64166:9999",
        )
    )
    await db_session.flush()
    cv = await generate_config(db_session, rs.id, ixp.id)

    slug = (await build_rs_peers(db_session, rs.id, af=4))[0].slug
    assert f"protocol bgp pb_{slug} {{" in cv.content
    assert "local as 64166;" in cv.content
    assert "neighbor 192.0.2.5 as 64166;" in cv.content
    assert "bgp_community.add( (64166, 9999) );" in cv.content
    assert "export where !(bgp_community ~ [(64166, 9999)]);" in cv.content
    # un peer no-miembro no es cliente del route server
    assert f"pb_{slug} from tb_rsclient" not in cv.content


@requires_bird
async def test_full_config_with_rpki_and_upstream_parses(db_session, ixp):
    from ixforge.enums import RPKIPolicy, RouteServerPeerType
    from ixforge.models.route_server_peer import RouteServerPeer
    from ixforge.models.rpki_server import RPKIServer
    from ixforge.services.config_generation import generate_config

    rs = await _setup_route_server(db_session, ixp)
    rs.rpki_enabled = True
    rs.rpki_policy = RPKIPolicy.reject_invalid
    db_session.add_all([
        RPKIServer(ixp_id=ixp.id, name="routinator", host="10.0.0.1"),
        RouteServerPeer(
            ixp_id=ixp.id, route_server_id=rs.id, name="PIT Chile v4",
            peer_ip="192.0.2.5", peer_asn=64166, local_asn=64166,
            peer_type=RouteServerPeerType.upstream, mark_community="64166:9999",
        ),
    ])
    await _setup_member_peer(
        db_session, ixp, rs, asn=273973, ipv4="192.0.2.11", ipv6="2001:db8::11"
    )
    await db_session.flush()
    cv = await generate_config(db_session, rs.id, ixp.id)

    assert_bird_parses(cv.content)
```

- [ ] **Step 2: Correr los tests y verificar que fallan**

Run: `uv run pytest tests/test_config_generation.py -v -k "rpki or rs_peer or full_config"`
Expected: FAIL, `TemplateNotFound: protocols/rpki.j2`

- [ ] **Step 3: Agregar `protocols/rpki.j2`**

```jinja
# Validacion RPKI via RTR
roa4 table roa_v4;
roa6 table roa_v6;

{% for server in route_server.rpki_servers %}
protocol rpki rpki_{{ server.slug }} {
    roa4 { table roa_v4; };
    roa6 { table roa_v6; };
    remote "{{ server.host }}" port {{ server.port }};
{% if server.refresh_time %}
    refresh keep {{ server.refresh_time }};
{% endif %}
{% if server.retry_time %}
    retry keep {{ server.retry_time }};
{% endif %}
{% if server.expire_time %}
    expire keep {{ server.expire_time }};
{% endif %}
}

{% endfor %}
```

El generador solo emite transporte TCP. `RPKITransport.ssh` existe en el modelo
pero necesita rutas de llaves que todavia no estan modeladas, asi que el servicio
de la Task 12 tiene que **rechazar** `ssh` en vez de dejar que se configure y
rendere un config silenciosamente incorrecto.

- [ ] **Step 4: Agregar `protocols/rs_peer.j2`**

```jinja
# {{ peer.name | bird_str }} (AS{{ peer.peer_asn }}, {{ peer.peer_type }})
{% if af == 4 %}
ipv4 table t_{{ peer.slug }};
{% else %}
ipv6 table t_{{ peer.slug }};
{% endif %}

protocol bgp pb_{{ peer.slug }} {
    description "{{ peer.name | bird_str }}";
    local as {{ peer.local_asn }};
    neighbor {{ peer.peer_ip }} as {{ peer.peer_asn }};
{% if peer.passive %}
    passive yes;
{% endif %}

{% if af == 4 %}
    ipv4 {
{% else %}
    ipv6 {
{% endif %}
{% if peer.max_prefixes %}
        import limit {{ peer.max_prefixes }} action restart;
{% endif %}
        import filter {
{% if peer.mark_community %}
            bgp_community.add( ({{ peer.mark_community | bird_community }}) );
{% endif %}
            accept;
        };
        export all;
        table t_{{ peer.slug }};
    };
}

protocol pipe pp_{{ peer.slug }} {
    description "Pipe for {{ peer.name | bird_str }}";
{% if af == 4 %}
    table master4;
{% else %}
    table master6;
{% endif %}
    peer table t_{{ peer.slug }};
    import all;
{% if peer.mark_community %}
    export where !(bgp_community ~ [({{ peer.mark_community | bird_community }})]);
{% else %}
    export all;
{% endif %}
}
```

- [ ] **Step 5: Correr los tests y verificar que pasan**

Run: `uv run pytest tests/test_config_generation.py -v -k "rpki or rs_peer or full_config"`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
uv run ruff check src/ tests/ && uv run mypy src/
git add src/ixforge/services/default_templates.py tests/test_config_generation.py
git commit -m "feat: templates de RPKI y de peers que no son miembros"
```

---

### Task 10: Reescribir los tests viejos y agregar golden files

Los tests de `test_config_generation.py` que asertan sobre el formato viejo
(`protocol_name`, `bird_v4.conf.j2`, `include_globals`, `_combine_configs`) fallan
desde la Task 7. Se reescriben contra el set nuevo, no se adaptan a medias.

**Files:**
- Modify: `tests/test_config_generation.py`
- Create: `tests/golden/rs_dual_full.conf`
- Create: `tests/golden/__init__.py`
- Modify: `tests/factories.py`

**Interfaces:**
- Produces: fixture `golden_ixp` que arma un IXP determinista, y el archivo esperado versionado

- [ ] **Step 1: Borrar o reescribir los tests obsoletos**

Buscar y tratar uno por uno:

```bash
uv run pytest tests/test_config_generation.py -v 2>&1 | grep -E "FAILED|ERROR"
grep -n "include_globals\|_combine_configs\|_sanitize_protocol_name\|bird_v4.conf.j2\|protocol_name" tests/test_config_generation.py
```

Los que verifican que los globals no se dupliquen ya estan cubiertos por
`test_config_has_single_globals_section`: se borran. Los que verifican naming de
protocolo se reescriben usando `slug`.

- [ ] **Step 2: Escribir el test golden que falla**

```python
GOLDEN_PATH = Path(__file__).parent / "golden" / "rs_dual_full.conf"


async def _build_golden_ixp(db_session, ixp) -> RouteServer:
    """IXP determinista: mismos UUIDs, mismos datos, mismo orden

    Cualquier cambio de template tiene que aparecer en el diff del PR, no
    descubrirse en produccion
    """
    rs = await _setup_route_server(
        db_session,
        ixp,
        id=uuid.UUID("00000000-0000-0000-0000-0000000000a1"),
        name="rs-golden",
        ip_v4="192.0.2.250",
        ip_v6="2001:db8::250",
    )
    rs.rpki_enabled = True
    rs.rpki_policy = RPKIPolicy.reject_invalid
    db_session.add(
        RPKIServer(
            id=uuid.UUID("00000000-0000-0000-0000-0000000000b1"),
            ixp_id=ixp.id,
            name="routinator",
            host="10.0.0.1",
        )
    )

    # ISP con filtro de prefijos en las dos familias
    isp = await _setup_member_peer(
        db_session, ixp, rs, asn=273973, short_name="APO",
        ipv4="192.0.2.11", ipv6="2001:db8::11", member_type=MemberType.isp,
    )
    db_session.add_all([
        MemberPrefixFilter(
            ixp_id=ixp.id, member_id=isp.id, af=4,
            origin_asns=[273973], prefixes=["45.170.100.0/24", "45.238.179.0/24"],
        ),
        MemberPrefixFilter(
            ixp_id=ixp.id, member_id=isp.id, af=6,
            origin_asns=[273973], prefixes=["2001:db8:aa::/48"],
        ),
    ])

    # infraestructura critica sin filtro: cae al ASN propio
    root = await _setup_member_peer(
        db_session, ixp, rs, asn=25152, short_name="KROOT",
        ipv4="192.0.2.10", ipv6="2001:db8::10",
        member_type=MemberType.infraestructura_critica,
    )

    # CDN con dos conexiones: allips tiene que traer las dos IPs
    cdn = await _setup_member_peer(
        db_session, ixp, rs, asn=61455, short_name="CDN",
        ipv4="192.0.2.16", member_type=MemberType.cdn,
    )
    await _add_second_connection(db_session, ixp, rs, cdn, ipv4="192.0.2.18")

    # upstream que no es miembro
    db_session.add(
        RouteServerPeer(
            id=uuid.UUID("00000000-0000-0000-0000-0000000000c1"),
            ixp_id=ixp.id,
            route_server_id=rs.id,
            name="PIT Chile v4",
            peer_ip="192.0.2.5",
            peer_asn=64166,
            local_asn=64166,
            peer_type=RouteServerPeerType.upstream,
            mark_community="64166:9999",
        )
    )

    await db_session.flush()
    return rs


async def test_golden_config_matches(db_session, ixp):
    from ixforge.services.config_generation import generate_config

    rs = await _build_golden_ixp(db_session, ixp)
    cv = await generate_config(db_session, rs.id, ixp.id)

    # las dos lineas volatiles se normalizan
    got = re.sub(r"^# Generated by IXForge Core at .*$", "# Generated at <fixed>", cv.content, flags=re.M)
    got = re.sub(r"^# Config hash: .*$", "# Config hash: <fixed>", got, flags=re.M)

    if not GOLDEN_PATH.exists():
        GOLDEN_PATH.write_text(got, encoding="utf-8")
        pytest.fail("golden file creado, revisalo a mano y volve a correr")

    assert got == GOLDEN_PATH.read_text(encoding="utf-8")
```

`_build_golden_ixp` arma: route server dual stack con RPKI en `reject_invalid` y un
servidor RTR, tres miembros (uno `isp` con filtro de prefijos v4 y v6, uno
`infraestructura_critica` sin filtro, uno `cdn` con dos conexiones), y un peer de
upstream con `mark_community`. Los UUIDs se pasan explicitos para que el orden de
salida sea estable entre corridas.

- [ ] **Step 3: Correr, revisar el golden generado a mano, commitear**

Run: `uv run pytest tests/test_config_generation.py::test_golden_config_matches -v`
Expected: primera corrida FAIL creando el archivo. Leer `tests/golden/rs_dual_full.conf`
entero y verificar que sea el config que uno querria en un route server real:
cada peer con sus cinco simbolos, `rs client` presente, `f_export_to_master` una
sola vez, RPKI con las dos tablas. Segunda corrida PASS.

- [ ] **Step 4: Validar el golden con bird -p**

```python
@requires_bird
def test_golden_config_parses():
    assert_bird_parses(GOLDEN_PATH.read_text(encoding="utf-8"))
```

Run: `uv run pytest tests/test_config_generation.py -v`
Expected: toda la suite del archivo en verde

- [ ] **Step 5: Correr la suite completa**

Run: `uv run pytest`
Expected: PASS. Los tests de `tests/ui/` y `test_agent.py` que mencionan configs no
deberian tocarse, pero si alguno asertaba sobre el formato viejo, arreglarlo aca

- [ ] **Step 6: Commit**

```bash
uv run ruff check src/ tests/ && uv run mypy src/
git add tests/
git commit -m "test: golden files del config euro-ix y limpieza de los tests viejos"
```

---

### Task 11: API de peers no-miembro

**Files:**
- Create: `src/ixforge/schemas/route_server_peer.py`
- Create: `src/ixforge/services/route_server_peers.py`
- Create: `src/ixforge/api/v1/route_server_peers.py`
- Modify: `src/ixforge/api/v1/__init__.py`
- Test: `tests/test_route_server_peers.py`

**Interfaces:**
- Produces: `GET|POST /route-servers/{id}/peers`, `GET|PATCH|DELETE /route-servers/{id}/peers/{peer_id}`

- [ ] **Step 1: Escribir los tests que fallan**

```python
"""Tests de la API de peers que no pertenecen a un miembro."""


async def test_create_peer_returns_201(client, auth_headers, route_server):
    resp = await client.post(
        f"/api/v1/route-servers/{route_server.id}/peers",
        headers=auth_headers,
        json={
            "name": "PIT Chile v4",
            "peer_ip": "192.0.2.5",
            "peer_asn": 64166,
            "peer_type": "upstream",
            "mark_community": "64166:9999",
        },
    )

    assert resp.status_code == 201
    assert resp.json()["peer_type"] == "upstream"
    assert resp.json()["passive"] is True


async def test_create_peer_rejects_duplicate_ip(client, auth_headers, route_server):
    body = {"name": "a", "peer_ip": "192.0.2.5", "peer_asn": 64166, "peer_type": "upstream"}
    await client.post(f"/api/v1/route-servers/{route_server.id}/peers", headers=auth_headers, json=body)

    resp = await client.post(
        f"/api/v1/route-servers/{route_server.id}/peers",
        headers=auth_headers,
        json={**body, "name": "b"},
    )

    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "CONFLICT"


async def test_create_peer_rejects_bad_community(client, auth_headers, route_server):
    resp = await client.post(
        f"/api/v1/route-servers/{route_server.id}/peers",
        headers=auth_headers,
        json={
            "name": "malo", "peer_ip": "192.0.2.5", "peer_asn": 64166,
            "peer_type": "upstream", "mark_community": "no-es-una-community",
        },
    )

    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


async def test_create_peer_rejects_invalid_ip(client, auth_headers, route_server):
    resp = await client.post(
        f"/api/v1/route-servers/{route_server.id}/peers",
        headers=auth_headers,
        json={"name": "malo", "peer_ip": "no.es.una.ip", "peer_asn": 64166, "peer_type": "upstream"},
    )

    assert resp.status_code == 422


async def test_member_user_cannot_create_peer(client, member_auth_headers, route_server):
    resp = await client.post(
        f"/api/v1/route-servers/{route_server.id}/peers",
        headers=member_auth_headers,
        json={"name": "x", "peer_ip": "192.0.2.5", "peer_asn": 64166, "peer_type": "upstream"},
    )

    assert resp.status_code == 403


async def test_create_peer_triggers_regeneration(client, auth_headers, route_server, monkeypatch):
    """Sin el defer, la plataforma parece funcionar y el RS nunca recibe la config"""
    calls = []

    async def _fake_defer(rs_id, triggered_by):
        calls.append((rs_id, triggered_by))

    monkeypatch.setattr("ixforge.tasks.config.defer_rs_config_regeneration", _fake_defer)

    await client.post(
        f"/api/v1/route-servers/{route_server.id}/peers",
        headers=auth_headers,
        json={"name": "x", "peer_ip": "192.0.2.5", "peer_asn": 64166, "peer_type": "upstream"},
    )

    assert calls == [(route_server.id, "route_server_peer.created")]


async def test_delete_peer_triggers_regeneration(client, auth_headers, route_server, monkeypatch):
    calls = []

    async def _fake_defer(rs_id, triggered_by):
        calls.append((rs_id, triggered_by))

    created = await client.post(
        f"/api/v1/route-servers/{route_server.id}/peers",
        headers=auth_headers,
        json={"name": "x", "peer_ip": "192.0.2.5", "peer_asn": 64166, "peer_type": "upstream"},
    )
    monkeypatch.setattr("ixforge.tasks.config.defer_rs_config_regeneration", _fake_defer)

    resp = await client.delete(
        f"/api/v1/route-servers/{route_server.id}/peers/{created.json()['id']}",
        headers=auth_headers,
    )

    assert resp.status_code == 204
    assert calls == [(route_server.id, "route_server_peer.deleted")]
```

Agregar la fixture `route_server` a `tests/conftest.py` si no existe, siguiendo el
patron de la fixture `ixp`.

- [ ] **Step 2: Correr los tests y verificar que fallan**

Run: `uv run pytest tests/test_route_server_peers.py -v`
Expected: FAIL con 404 en todos los endpoints

- [ ] **Step 3: Escribir los schemas**

`src/ixforge/schemas/route_server_peer.py`, siguiendo el patron de
`schemas/bgp_session.py`. La validacion de `mark_community` reusa el filtro:

```python
    @field_validator("mark_community")
    @classmethod
    def _validate_community(cls, v: str | None) -> str | None:
        if v is None:
            return v
        bird_community(v)  # levanta ValueError si no es asn:value valido
        return v
```

y `peer_ip` se valida con `ipaddress.ip_address()` en otro `field_validator`, no
solo por tipo `str`.

- [ ] **Step 4: Escribir el servicio y el router**

`services/route_server_peers.py` con `list_peers`, `create`, `get`, `update` y
`delete`, cada uno verificando que el `route_server_id` pertenezca al `ixp_id` del
request antes de tocar nada. `create`, `update` y `delete` llaman a
`defer_rs_config_regeneration` con `route_server_peer.created`, `.updated` y
`.deleted`. El router copia la forma de `api/v1/route_servers.py` y se registra en
`api/v1/__init__.py`.

- [ ] **Step 5: Correr los tests y verificar que pasan**

Run: `uv run pytest tests/test_route_server_peers.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
uv run ruff check src/ tests/ && uv run mypy src/
git add src/ixforge/schemas/ src/ixforge/services/ src/ixforge/api/ tests/
git commit -m "feat: API de peers de route server que no son miembros"
```

---

### Task 12: API de filtros de prefijos, RPKI y campos del route server

**Files:**
- Create: `src/ixforge/schemas/member_prefix_filter.py`, `rpki_server.py`
- Create: `src/ixforge/services/member_prefix_filters.py`, `rpki_servers.py`
- Create: `src/ixforge/api/v1/member_prefix_filters.py`, `rpki_servers.py`
- Modify: `src/ixforge/api/v1/__init__.py`, `src/ixforge/schemas/route_server.py`
- Test: `tests/test_member_prefix_filters.py`, `tests/test_rpki_servers.py`, `tests/test_route_servers.py`

**Interfaces:**
- Produces: `GET|PUT|DELETE /members/{id}/prefix-filters/{af}`, CRUD de `/rpki-servers`, campos nuevos en el schema de route server

- [ ] **Step 1: Escribir los tests que fallan**

```python
async def test_put_prefix_filter_is_idempotent(client, auth_headers, member):
    body = {"origin_asns": [273973], "prefixes": ["45.170.100.0/24"], "as_set": "AS-APOAPSIS"}

    first = await client.put(f"/api/v1/members/{member.id}/prefix-filters/4", headers=auth_headers, json=body)
    second = await client.put(f"/api/v1/members/{member.id}/prefix-filters/4", headers=auth_headers, json=body)

    assert first.status_code in (200, 201)
    assert second.status_code == 200
    assert second.json()["origin_asns"] == [273973]


async def test_prefix_filter_rejects_wrong_family(client, auth_headers, member):
    """Un prefijo v6 en el filtro v4 es un error del operador, no algo a ignorar"""
    resp = await client.put(
        f"/api/v1/members/{member.id}/prefix-filters/4",
        headers=auth_headers,
        json={"prefixes": ["2001:db8::/32"]},
    )

    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


async def test_prefix_filter_rejects_invalid_af(client, auth_headers, member):
    resp = await client.put(
        f"/api/v1/members/{member.id}/prefix-filters/5", headers=auth_headers, json={}
    )

    assert resp.status_code == 422


async def test_prefix_filter_rejects_bad_asn(client, auth_headers, member):
    resp = await client.put(
        f"/api/v1/members/{member.id}/prefix-filters/4",
        headers=auth_headers,
        json={"origin_asns": [0, -1]},
    )

    assert resp.status_code == 422


async def test_prefix_filter_triggers_regeneration_of_every_rs(client, auth_headers, member, monkeypatch):
    """El filtro es del miembro, asi que afecta a todos los route servers donde peerea"""
    calls = []

    async def _fake_defer(rs_id, triggered_by):
        calls.append(rs_id)

    monkeypatch.setattr("ixforge.tasks.config.defer_rs_config_regeneration", _fake_defer)

    await client.put(
        f"/api/v1/members/{member.id}/prefix-filters/4",
        headers=auth_headers,
        json={"origin_asns": [273973]},
    )

    assert len(calls) == len(set(calls))
    assert len(calls) >= 1


async def test_rpki_server_rejects_ssh_transport(client, auth_headers):
    """El generador solo emite TCP: configurar ssh renderearia un config incorrecto
    en silencio
    """
    resp = await client.post(
        "/api/v1/rpki-servers",
        headers=auth_headers,
        json={"name": "x", "host": "10.0.0.1", "transport": "ssh"},
    )

    assert resp.status_code == 422
    assert "ssh" in resp.json()["error"]["message"].lower()


async def test_route_server_read_exposes_rpki_fields(client, auth_headers, route_server):
    resp = await client.get(f"/api/v1/route-servers/{route_server.id}", headers=auth_headers)

    body = resp.json()
    assert body["passive_sessions"] is True
    assert body["rpki_enabled"] is False
    assert body["rpki_policy"] == "info_only"


async def test_enabling_rpki_triggers_regeneration(client, auth_headers, route_server, monkeypatch):
    calls = []

    async def _fake_defer(rs_id, triggered_by):
        calls.append((rs_id, triggered_by))

    monkeypatch.setattr("ixforge.tasks.config.defer_rs_config_regeneration", _fake_defer)

    resp = await client.patch(
        f"/api/v1/route-servers/{route_server.id}",
        headers=auth_headers,
        json={"rpki_enabled": True, "rpki_policy": "reject_invalid"},
    )

    assert resp.status_code == 200
    assert calls == [(route_server.id, "route_server.updated")]
```

- [ ] **Step 2: Correr los tests y verificar que fallan**

Run: `uv run pytest tests/test_member_prefix_filters.py tests/test_rpki_servers.py tests/test_route_servers.py -v`
Expected: FAIL con 404 en los endpoints nuevos y `KeyError: 'rpki_policy'`

- [ ] **Step 3: Implementar los schemas con validacion de familia**

En `schemas/member_prefix_filter.py`, el validador que rechaza mezclar familias:

```python
    @model_validator(mode="after")
    def _prefixes_match_af(self) -> "MemberPrefixFilterWrite":
        if self.prefixes is None:
            return self
        for prefix in self.prefixes:
            try:
                network = ipaddress.ip_network(prefix, strict=False)
            except ValueError as exc:
                raise ValueError(f"prefijo invalido: {prefix!r}") from exc
            if network.version != self.af:
                raise ValueError(
                    f"el prefijo {prefix} es IPv{network.version} y el filtro es IPv{self.af}"
                )
        return self
```

y para los ASNs, `Field(ge=1, le=4294967295)` sobre los items de la lista.

- [ ] **Step 4: Implementar servicios y routers**

`services/member_prefix_filters.py` con `upsert(db, ixp_id, member_id, af, data)`,
que hace insert o update sobre la unica fila `(member_id, af)`, y despues encola la
regeneracion de **cada route server distinto** donde ese miembro tenga una sesion
BGP: consulta `BGPSession.route_server_id` por `trunk_vlan -> trunk -> member`, la
deduplica y llama al defer una vez por route server.

`services/rpki_servers.py` con el CRUD y la validacion que rechaza
`RPKITransport.ssh` con `ValidationError("el transporte ssh todavia no esta soportado
por el generador")`. Al crear, actualizar o borrar, encola la regeneracion de los
route servers afectados: el que tenga `route_server_id`, o todos los del IXP si es
NULL.

En `schemas/route_server.py`, agregar `passive_sessions`, `rpki_enabled` y
`rpki_policy` a `RouteServerRead`, `RouteServerCreate` (con defaults) y
`RouteServerUpdate` (opcionales). Verificar que `update` en
`services/route_servers.py` ya encole la regeneracion; si no lo hace, agregarlo.

- [ ] **Step 5: Correr los tests y verificar que pasan**

Run: `uv run pytest tests/test_member_prefix_filters.py tests/test_rpki_servers.py tests/test_route_servers.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
uv run ruff check src/ tests/ && uv run mypy src/
git add src/ tests/
git commit -m "feat: API de filtros de prefijos, servidores RPKI y politica del route server"
```

---

### Task 13: Migracion de los IXPs existentes y documentacion

**Files:**
- Create: `alembic/versions/<rev>_euroix_templates.py`
- Create: `docs/migracion-euroix.md`
- Modify: `docs/templates.md`, `docs/api.md`, `README.md`
- Test: manual, sobre una copia de la base de dev

**Interfaces:**
- Consumes: el set de templates de las Tasks 7, 8 y 9

- [ ] **Step 1: Escribir la migracion de datos**

Siguiendo el patron que ya usa `a3b4c5d6e7f8`, la migracion lleva un **snapshot
literal** de los templates, copiado de `default_templates.py` al momento de
escribirla, y no importa codigo de la aplicacion: un template que cambie en el
futuro no debe cambiar lo que hizo esta migracion.

```python
def upgrade() -> None:
    conn = op.get_bind()
    ixp_ids = [row[0] for row in conn.execute(sa.text("SELECT id FROM ixps"))]
    for ixp_id in ixp_ids:
        conn.execute(
            sa.text("DELETE FROM route_server_templates WHERE ixp_id = :ixp_id"),
            {"ixp_id": ixp_id},
        )
        for tmpl in EUROIX_TEMPLATE_SNAPSHOT:
            conn.execute(
                sa.text(
                    "INSERT INTO route_server_templates "
                    "(ixp_id, filename, content, description, is_protected) "
                    "VALUES (:ixp_id, :filename, :content, :description, :is_protected)"
                ),
                {"ixp_id": ixp_id, **tmpl},
            )
```

`downgrade` levanta `NotImplementedError` con un mensaje que apunte a restaurar
desde el export del paso 1 del procedimiento: reconstruir los templates viejos a
ciegas seria peor que no bajar.

- [ ] **Step 2: Probar la migracion sobre una copia de dev**

```bash
pg_dump -h <dev> -U ixforge ixforge > /tmp/dev-antes.sql
createdb ixforge_migtest && psql ixforge_migtest < /tmp/dev-antes.sql
DATABASE_URL=postgresql+asyncpg://.../ixforge_migtest uv run alembic upgrade head
psql ixforge_migtest -c "SELECT ixp_id, filename FROM route_server_templates ORDER BY 1,2"
```
Expected: cada IXP con exactamente el set nuevo, ningun `bird_v4.conf.j2` ni
`protocols/static.j2` sobreviviente

- [ ] **Step 3: Escribir `docs/migracion-euroix.md`**

Procedimiento para cada IXP ya desplegado, con estos seis pasos y su verificacion:

1. Exportar los templates actuales via `GET /route-servers/templates` a un archivo fuera de la base
2. Sacar la foto previa: `birdc show protocols` y conteo de prefijos por peer en cada route server
3. Aplicar la migracion
4. Cargar los datos nuevos que apliquen: `member_type` de cada miembro, filtros de prefijos, peers no-miembro
5. Regenerar y revisar el diff en el portal, despues validar con `bird -p` antes de aplicar
6. Aplicar y comparar sesiones y conteos contra la foto del paso 2

Con la advertencia en primer plano, no al final: **para un IXP que venia con los
templates viejos esto es un cambio de comportamiento, no de formato**. Gana
`rs client`, o sea el route server deja de meter su ASN en el AS path y deja de
reescribir el next hop. Es una correccion, pero cambia lo que ven los peers y hay
que verificarlo con ellos. Ademas gana `interpret communities off` y pierde el
`protocol kernel`, y desaparecen los dos templates de blackhole que nunca estuvieron
conectados.

- [ ] **Step 4: Actualizar la documentacion existente**

- `docs/templates.md`: reescribir entero. Ya no hay `include_globals` ni par
  v4/v6: hay un `bird.conf.j2` y sus includes. Documentar la inversion de logica
  (marcar en vez de rechazar) porque es lo que mas va a confundir a quien edite un
  template por primera vez, y la tabla de simbolos derivados con el limite de 55
- `docs/api.md`: los endpoints de las Tasks 11 y 12
- `README.md`: mencionar paridad euro-ix y RPKI en la lista de features
- `docs/guides/aprovisionamiento.md`: agregar el paso de cargar el filtro de
  prefijos al dar de alta un miembro

- [ ] **Step 5: Correr la suite completa y los linters**

```bash
uv run pytest
uv run ruff check src/ tests/
uv run mypy src/
```
Expected: todo en verde

- [ ] **Step 6: Commit**

```bash
git add alembic/versions/ docs/ README.md
git commit -m "feat: migracion de IXPs existentes al set euro-ix y documentacion"
```

---

## Notas para quien ejecute

- **El orden importa hasta la Task 10.** Las Tasks 11 a 13 se pueden hacer en
  cualquier orden entre ellas
- **`bird -p` es el arbitro.** Los templates de este plan estan escritos contra
  BIRD 2.14 y 2.18 leyendo un config real en produccion, pero no fueron ejecutados.
  Si BIRD rechaza algo, la salida del helper trae archivo, linea y columna, y el
  config numerado. Ajustar el template y seguir, no adivinar
- **No agregar features de paso.** Blackholing (RFC 7999), resolver IRR y looking
  glass estan explicitamente fuera de alcance y tienen su razon escrita en el spec
- **Al terminar**, el corte de PatagoniaIX depende de esto: el spec de deployment
  se escribe despues, con este trabajo ya mergeado
