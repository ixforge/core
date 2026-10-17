# IXForge Core

API REST central de [IXForge](https://github.com/ixforge), plataforma open source para gestionar Internet Exchange Points. El Core gestiona miembros, conexiones, switches, IPAM, sesiones BGP y la generación de la configuración BIRD de los route servers. Expone toda la funcionalidad por REST para los demás componentes e incluye el portal web de administración.

## Componentes del ecosistema

- **Core** (este repositorio): API REST, lógica de negocio, base de datos y portal web.
- [Agent](https://github.com/ixforge/agent): daemon en Rust que aplica la configuración BIRD en los route servers y reporta el estado de las sesiones BGP y los prefijos que anuncia cada peer.
- [Collector](https://github.com/ixforge/collector): daemon en Python que recolecta métricas SNMP e ICMP y las escribe en VictoriaMetrics.
- [E2E](https://github.com/ixforge/e2e): tests end-to-end del ecosistema completo.

## Requisitos

- Python 3.12+
- PostgreSQL 17
- [uv](https://docs.astral.sh/uv/)
- Docker, para el PostgreSQL de desarrollo y el validador BIRD de los tests

## Inicio rápido

```bash
cd core
uv sync

# PostgreSQL de desarrollo (puerto 5432)
docker compose -f docker/docker-compose.dev.yml up -d postgres

# Migraciones
uv run ixforge upgrade

# Servidor de la API (hot reload)
IXFORGE_DEBUG=true uv run ixforge run
```

API y Swagger UI en `http://localhost:8000/api/v1/docs`. El portal se inicia aparte con
`IXFORGE_DEBUG=true uv run ixforge ui` (puerto 8001) y la regeneración de configuraciones
BIRD necesita el worker: `IXFORGE_DEBUG=true uv run ixforge worker`.

En una base nueva, crear el IXP y el usuario admin con el setup inicial
(`POST /api/v1/setup`, o el portal en `http://localhost:8001/setup`). Ver
[Quickstart](docs/quickstart.md).

## Despliegue

`./deploy.sh <dev|prod>` despliega el commit actual de HEAD al entorno elegido; los
hosts se definen en `deploy.env` (ver `deploy.env.example`). Aborta si hay cambios sin
commit, hace backup de la base, sube el código con `git archive`, reconstruye los
contenedores, aplica las migraciones, comprueba el health check y verifica que el hash
del código en el servidor coincida con el commit. Para prod pide confirmación (se omite
con `--yes`). El flujo completo dev -> prod está en [docs/staging.md](docs/staging.md).

## Documentación

- [Quickstart](docs/quickstart.md): instalación, configuración, CLI, tests y Docker
- [Staging dev -> prod](docs/staging.md): flujo de trabajo, ritual de despliegue y reglas
- [Guías de API](docs/guides/README.md): recetas de login, miembros, aprovisionamiento y métricas
- [API](docs/api.md): endpoints, autenticación y paginación
- [Templates BIRD](docs/templates.md): cómo se genera la configuración, el patrón de route server y la edición de templates
- [Migración](docs/migracion.md): procedimiento para actualizar un IXP ya desplegado
- [Arquitectura](docs/architecture.md): capas, patrones y convenciones
- [Testing](TESTING.md): suite, validación BIRD obligatoria en CI y pipeline Core -> Agent -> BIRD

## Licencia

Apache 2.0
