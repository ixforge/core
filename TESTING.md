# Testing

Guia para correr y escribir tests en IXForge Core.

## Requisitos

- Python 3.12+
- [uv](https://docs.astral.sh/uv/)
- Docker (para PostgreSQL de testing)

## Entorno de desarrollo

```bash
# Levantar PostgreSQL + Core con hot reload
docker compose -f docker/docker-compose.dev.yml up -d

# Correr migraciones y crear admin
docker compose -f docker/docker-compose.dev.yml exec core uv run ixforge upgrade
docker compose -f docker/docker-compose.dev.yml exec core uv run ixforge createsuperuser

# Limpiar todo y empezar de cero
docker compose -f docker/docker-compose.dev.yml down -v
docker compose -f docker/docker-compose.dev.yml up -d
```

API disponible en `http://localhost:8000/api/v1/docs`. El source se monta como volumen (`src/`), asi los cambios se reflejan sin rebuild.

## Setup para tests

```bash
# Instalar dependencias (incluye dev)
uv sync

# Levantar PostgreSQL de testing (puerto 5433, tmpfs para velocidad)
docker compose -f docker/docker-compose.testing.yml up -d
```

El container de testing usa `tmpfs` en vez de un volumen persistente, asi la BD vive en memoria y los tests corren mas rapido. La BD se llama `ixforge_test`, puerto **5433**.

## Correr tests

```bash
# Todos los tests
uv run pytest -v

# Un archivo especifico
uv run pytest tests/test_members.py -v

# Un test especifico
uv run pytest tests/test_members.py::test_create_member -v

# Tests de un directorio (ej: UI tests)
uv run pytest tests/ui/ -v

# Con coverage
uv run pytest --cov=ixforge --cov-report=term-missing
```

Los tests de configuracion que invocan BIRD necesitan su imagen local:

```bash
docker build -t ixforge-bird-validator:2 docker/bird-validator/
IXFORGE_REQUIRE_BIRD=1 uv run pytest
```

CI construye esa imagen y exige `IXFORGE_REQUIRE_BIRD=1`: si Docker o la imagen
faltan, la suite falla durante la coleccion en vez de omitir la validacion.
Sin esa variable, una maquina de desarrollo sin Docker puede seguir ejecutando
el resto de los tests. La version de BIRD de la imagen debe coincidir con la
del deployment; ver `docker/bird-validator/Dockerfile`.

## Pipeline Core -> Agent -> BIRD

El job `Core + Agent + BIRD` de `.github/workflows/e2e.yml` arranca los tres
componentes reales sobre PostgreSQL desechable. Comprueba que el Agent instala
la configuracion generada, BIRD muestra el router ID esperado y el Core recibe
la confirmacion y el heartbeat. Luego genera una configuracion con sintaxis BIRD
invalida: debe reportarse el rechazo y conservarse tanto el archivo como la
configuracion activa. Una tercera version valida debe aplicarse y confirmarse.

El job compila `ixforge/agent` desde `main`. La variable de repositorio
`IXFORGE_AGENT_REF` permite fijar un tag o SHA para verificar una combinacion
especifica. Los logs de Core, Agent y BIRD quedan como artefactos del job.

Para correrlo localmente, iniciar Core sobre una **base migrada desechable sin
setup**, construir la imagen anterior y compilar el Agent. El runner rechaza
un Core que ya tenga un IXP configurado y crea sus propios datos de prueba:

```bash
IXFORGE_AGENT_BINARY=../agent/target/debug/ixforge-agent \
  E2E_BASE_URL=http://127.0.0.1:8000/api/v1 \
  IXFORGE_REQUIRE_BIRD=1 uv run pytest tests/pipeline_runner.py -v -s
```

BIRD corre en un contenedor sin red, con el UID/GID local y archivos temporales;
el Agent usa ese mismo BIRD para validar. La prueba verifica el ciclo de
configuracion y recuperacion, no establece sesiones BGP con routers externos.

## Linting y type checking

```bash
# Linting con ruff
uv run ruff check src/ tests/

# Type checking con mypy (strict mode)
uv run mypy src/
```

## Estructura de tests

```
tests/
  conftest.py          # Fixtures globales (DB, client, usuarios)
  factories.py         # Factory Boy factories para todos los modelos
  test_*.py            # Tests de API y servicios
  ui/
    conftest.py        # Fixtures de UI (bypass setup middleware)
    test_*.py          # Tests del admin UI
```

## Arquitectura de testing

### Base de datos

Los tests usan una BD PostgreSQL real (no mocks). Cada test corre dentro de una transaccion con savepoint que se hace rollback al final, asi:

- Los tests son **aislados** entre si
- No queda data residual entre tests
- Las tablas se crean una vez por sesion (`session` scope) y se dropean al final

La URL de la BD se configura con la variable de entorno `TEST_DATABASE_URL`. Default:

```
postgresql+asyncpg://ixforge:ixforge@localhost:5433/ixforge_test
```

### Client HTTP

El fixture `client` provee un `httpx.AsyncClient` conectado a la app FastAPI con la sesion de test inyectada via dependency override. No levanta un servidor real, usa `ASGITransport`.

### Fixtures principales

| Fixture | Scope | Descripcion |
|---------|-------|-------------|
| `test_engine` | session | Engine SQLAlchemy conectado a la BD de test |
| `db_session` | function | Sesion transaccional con rollback automatico |
| `client` | function | `AsyncClient` conectado a la app |
| `ixp` | function | IXP de ejemplo |
| `admin_user` | function | Usuario admin con password `adminpass123` |
| `member_user` | function | Usuario member con password `memberpass123` |
| `auth_headers` | function | Headers `Authorization: Bearer <jwt>` del admin |
| `member_auth_headers` | function | Headers `Authorization: Bearer <jwt>` del member |

### Factories

Se usa [Factory Boy](https://factoryboy.readthedocs.io/) con `BUILD_STRATEGY` (no persiste a DB automaticamente). Para usar una factory:

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
import pytest
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
- No hace falta marcar tests con `@pytest.mark.asyncio`, `asyncio_mode = "auto"` esta configurado
- Los tests de UI (`tests/ui/`) tienen un fixture `autouse` que bypasea el middleware de setup
- Siempre usar las factories en vez de construir objetos manualmente para consistencia

## Resetear la BD de testing

```bash
# Tirar el container y recrearlo (tmpfs, no pierde nada persistente)
docker compose -f docker/docker-compose.testing.yml down
docker compose -f docker/docker-compose.testing.yml up -d
```

No es necesario correr migraciones para testing: las tablas se crean automaticamente desde los modelos SQLAlchemy al inicio de la sesion de tests.

Eso mismo abre una brecha: el schema de los tests sale de los modelos y el de
produccion de las migraciones, asi que una migracion incompleta pasa toda la
suite y revienta al desplegar. `tests/test_paridad_migraciones.py` la cierra:
levanta una base aparte, le aplica las migraciones de cero y compara el
resultado contra los modelos. Si agregas una migracion a mano, ese test es el
que te dice si le falto algo.
