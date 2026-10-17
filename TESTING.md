# Testing

Guía para ejecutar y escribir tests en IXForge Core.

## Requisitos

- Python 3.12+
- [uv](https://docs.astral.sh/uv/)
- Docker (PostgreSQL de testing y validador BIRD)

## Entorno de desarrollo

```bash
# Levantar PostgreSQL, Core (hot reload) y portal
docker compose -f docker/docker-compose.dev.yml up -d

# Limpiar todo y empezar de cero
docker compose -f docker/docker-compose.dev.yml down -v
docker compose -f docker/docker-compose.dev.yml up -d
```

API disponible en `http://localhost:8000/api/v1/docs` y portal en `http://localhost:8001`.
El entrypoint del contenedor aplica las migraciones al arrancar. En una base nueva, crear
el IXP y el primer admin con el setup inicial (`http://localhost:8001/setup` o
`POST /api/v1/setup`); `ixforge createsuperuser` solo agrega admins cuando ya existe un IXP:

```bash
docker compose -f docker/docker-compose.dev.yml exec core uv run ixforge createsuperuser
```

Solo `src/` se monta como volumen, así que los cambios de código se reflejan sin
rebuild; una migración nueva en `alembic/` requiere reconstruir la imagen
(`up -d --build`). Este compose no incluye el worker: las regeneraciones de
configuración quedan encoladas hasta ejecutar
`docker compose -f docker/docker-compose.dev.yml exec core uv run ixforge worker`.

## Preparación para tests

```bash
# Instalar dependencias (incluye dev)
uv sync

# Levantar PostgreSQL de testing (puerto 5433, tmpfs para velocidad)
docker compose -f docker/docker-compose.testing.yml up -d
```

El contenedor de testing usa `tmpfs` en vez de un volumen persistente: la base vive en memoria y los tests son más rápidos. La base se llama `ixforge_test` y escucha en el puerto **5433**.

## Ejecutar tests

```bash
# Todos los tests
uv run pytest -v

# Un archivo específico
uv run pytest tests/test_members.py -v

# Un test específico (los tests agrupados en clases incluyen la clase en la ruta)
uv run pytest tests/test_members.py::TestMemberCRUD::test_create_member -v

# Tests de un directorio (ej: tests de UI)
uv run pytest tests/ui/ -v

# Con coverage
uv run pytest --cov=ixforge --cov-report=term-missing
```

Los tests de configuración que invocan BIRD necesitan su imagen local:

```bash
docker build -t ixforge-bird-validator:2 docker/bird-validator/
IXFORGE_REQUIRE_BIRD=1 uv run pytest
```

CI construye esa imagen y exige `IXFORGE_REQUIRE_BIRD=1`: si Docker o la imagen
faltan, la suite falla durante la colección en vez de omitir la validación.
Sin esa variable, una máquina de desarrollo sin Docker puede seguir ejecutando
el resto de los tests. La versión de BIRD de la imagen debe coincidir con la
del despliegue; ver `docker/bird-validator/Dockerfile`.

`test_golden_config_matches` compara la configuración generada para un IXP fijo
contra `tests/golden/rs_dual_full.conf`, así que cualquier cambio de template
aparece en el diff. Si el cambio es intencional, borrar el archivo y ejecutar el
test: lo regenera y falla a propósito para que el diff se revise a mano antes de
volver a ejecutarlo.

## Pipeline Core -> Agent -> BIRD

El job `Core + Agent + BIRD` de `.github/workflows/e2e.yml` arranca los tres
componentes reales sobre un PostgreSQL desechable. Comprueba que el Agent instala
la configuración generada, que BIRD muestra el router ID esperado y que el Core recibe
la confirmación y el heartbeat. Luego genera una configuración con sintaxis BIRD
inválida: debe reportarse el rechazo y conservarse tanto el archivo como la
configuración activa. Una tercera versión válida debe aplicarse y confirmarse.

El job compila `ixforge/agent` desde `main`. La variable de repositorio
`IXFORGE_AGENT_REF` permite fijar un tag o SHA para verificar una combinación
específica. Los logs de Core, Agent y BIRD quedan como artefactos del job.

Para ejecutarlo localmente, iniciar el Core sobre una **base migrada desechable sin
setup**, construir la imagen anterior y compilar el Agent. El runner rechaza
un Core que ya tenga un IXP configurado y crea sus propios datos de prueba.
Por ejemplo, con el PostgreSQL de testing y el repositorio del Agent clonado junto a `core`:

```bash
# Base desechable, migrada y sin setup
docker compose -f docker/docker-compose.testing.yml exec -T postgres createdb -U ixforge ixforge_pipeline
export IXFORGE_DATABASE_URL=postgresql+asyncpg://ixforge:ixforge@localhost:5433/ixforge_pipeline
export IXFORGE_SECRET_KEY=pipeline-local-secret-key-at-least-32-chars
uv run ixforge upgrade
uv run uvicorn ixforge.main:app --host 127.0.0.1 --port 8000 &

# Agent
(cd ../agent && cargo build --locked)
```

```bash
IXFORGE_AGENT_BINARY=../agent/target/debug/ixforge-agent \
  E2E_BASE_URL=http://127.0.0.1:8000/api/v1 \
  IXFORGE_REQUIRE_BIRD=1 uv run pytest tests/pipeline_runner.py -v -s
```

`tests/pipeline_runner.py` no sigue el patrón `test_*.py`, así que `uv run pytest`
no lo recolecta: solo se ejecuta nombrándolo. BIRD se ejecuta en un contenedor sin red,
con el UID/GID local y archivos temporales; el Agent usa ese mismo BIRD para validar.
La prueba verifica el ciclo de configuración y recuperación, no establece sesiones
BGP con routers externos.

## Linting, formato y type checking

```bash
# Linting con ruff
uv run ruff check src/ tests/

# Formato con ruff (CI falla si hay archivos sin formatear)
uv run ruff format --check src/ tests/

# Type checking con mypy (strict mode)
uv run mypy src/
```

CI (`.github/workflows/ci.yml`) ejecuta esos tres comandos y la suite completa en
Python 3.12, con PostgreSQL 17 en el puerto 5433 y `IXFORGE_REQUIRE_BIRD=1`.

## Estructura de tests

```
tests/
  conftest.py          # Fixtures globales (DB, client, usuarios)
  factories.py         # Factories de Factory Boy para los modelos principales
  bird_validator.py    # Validación de configs con bird -p en Docker
  golden/              # Configuración de referencia para test_golden_config_matches
  pipeline_runner.py   # Pipeline Core -> Agent -> BIRD (se ejecuta aparte)
  test_*.py            # Tests de API y servicios
  ui/
    conftest.py        # Fixtures de UI (bypass del middleware de setup)
    test_*.py          # Tests del portal de administración
```

## Arquitectura de testing

### Base de datos

Los tests usan una base PostgreSQL real (no mocks). Cada test se ejecuta dentro de una transacción con savepoint que se revierte (rollback) al final, así:

- Los tests quedan **aislados** entre sí
- No quedan datos residuales entre tests
- Las tablas se crean una vez por sesión (scope `session`) y se eliminan al final

La URL de la base se configura con la variable de entorno `TEST_DATABASE_URL`. Valor por defecto:

```
postgresql+asyncpg://ixforge:ixforge@localhost:5433/ixforge_test
```

### Cliente HTTP

El fixture `client` provee un `httpx.AsyncClient` conectado a la app FastAPI, con la sesión de test inyectada por dependency override. No levanta un servidor real: usa `ASGITransport`.

### Fixtures principales

| Fixture | Scope | Descripción |
|---------|-------|-------------|
| `test_engine` | session | Engine SQLAlchemy conectado a la base de test |
| `db_session` | function | Sesión transaccional con rollback automático |
| `client` | function | `AsyncClient` conectado a la app |
| `ixp` | function | IXP de ejemplo |
| `admin_user` | function | Usuario admin con password `adminpass123` |
| `member_user` | function | Usuario member con password `memberpass123` |
| `auth_headers` | function | Headers `Authorization: Bearer <jwt>` del admin |
| `member_auth_headers` | function | Headers `Authorization: Bearer <jwt>` del member |

### Factories

Se usa [Factory Boy](https://factoryboy.readthedocs.io/) con `BUILD_STRATEGY` (no persiste en la base automáticamente). Para usar una factory:

```python
from tests.factories import MemberFactory

async def test_something(db_session, ixp):
    member = MemberFactory(ixp_id=ixp.id)
    db_session.add(member)
    await db_session.flush()
```

Factories disponibles: `IXPFactory`, `MemberFactory`, `ContactFactory`, `SwitchFactory`, `VLANFactory`, `TrunkFactory`, `TrunkVLANFactory`, `IPPoolFactory`, `IPAssignmentFactory`, `ConnectionFactory`, `RouteServerFactory`, `BGPSessionFactory`, `ConfigVersionFactory`, `EventFactory`, `UserFactory`, `APIKeyFactory`, `CustomFieldDefinitionFactory`.

## Escribir un test nuevo

```python
from httpx import AsyncClient

from tests.factories import MemberFactory


async def test_list_members(client: AsyncClient, db_session, ixp, auth_headers):
    """GET /api/v1/members debe listar miembros del IXP."""
    member = MemberFactory(ixp_id=ixp.id)
    db_session.add(member)
    await db_session.flush()

    response = await client.get(
        "/api/v1/members",
        headers=auth_headers,
    )

    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) == 1
    assert data["items"][0]["asn"] == member.asn
```

Notas:
- No hace falta marcar los tests con `@pytest.mark.asyncio`: `asyncio_mode = "auto"` está configurado en `pyproject.toml`
- Los tests de UI (`tests/ui/`) tienen un fixture `autouse` que omite el middleware de setup
- Las factories completan los campos obligatorios con valores válidos; preferirlas a construir los modelos campo por campo

## Resetear la base de testing

```bash
# Eliminar el contenedor y recrearlo (tmpfs, no se pierde nada persistente)
docker compose -f docker/docker-compose.testing.yml down
docker compose -f docker/docker-compose.testing.yml up -d
```

No es necesario ejecutar migraciones para testing: las tablas se crean automáticamente desde los modelos SQLAlchemy al inicio de la sesión de tests.

Eso mismo abre una brecha: el schema de los tests sale de los modelos y el de
producción, de las migraciones, así que una migración incompleta pasa toda la
suite y falla al desplegar. `tests/test_paridad_migraciones.py` la cierra:
crea una base aparte, le aplica las migraciones desde cero y compara el
resultado contra los modelos. Si se agrega una migración a mano, ese test es el
que indica si le faltó algo.
