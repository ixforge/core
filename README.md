# IXForge Core

API REST central de [IXForge](https://github.com/ixforge), plataforma open-source para gestionar Internet Exchange Points. El Core maneja miembros, conexiones, switches, IPAM, generacion de configuracion BIRD, sesiones BGP, y expone toda la funcionalidad via REST para los demas componentes.

## Componentes del ecosistema

- **Core** (este repo) — API REST, logica de negocio, base de datos
- [Agent](https://github.com/ixforge/agent) — Daemon Rust que aplica configs BIRD en route servers
- [Collector](https://github.com/ixforge/collector) — Daemon Python que recolecta metricas SNMP/ICMP
- [E2E](https://github.com/ixforge/e2e) — Tests end-to-end del pipeline completo

## Requisitos

- Python 3.12+
- PostgreSQL 17
- [uv](https://docs.astral.sh/uv/)

## Quick start

```bash
cd core
uv sync

# PostgreSQL de desarrollo (puerto 5432)
docker compose -f docker/docker-compose.dev.yml up -d postgres

# Migraciones
uv run ixforge upgrade

# Iniciar servidor (hot reload)
IXFORGE_DEBUG=true uv run ixforge run
```

API y Swagger UI en `http://localhost:8000/api/v1/docs`. En una BD nueva, crea el
IXP y el usuario admin con el setup inicial (`POST /api/v1/setup`, o el portal en
`http://localhost:8001/setup`) — ver [Quickstart](docs/quickstart.md).

## Deploy

`./deploy.sh <dev|prod>` despliega el commit actual de HEAD al entorno elegido.
Aborta si hay cambios sin commitear, hace backup, sube el codigo con `git archive`,
reconstruye, aplica migraciones y verifica que el hash del codigo en el servidor
coincida con el commit. Para prod pide confirmacion (saltable con `--yes`). El
flujo completo dev -> prod esta en [docs/staging.md](docs/staging.md).

## Documentacion

- [Quickstart](docs/quickstart.md) — Setup inicial, configuracion, CLI, tests, Docker
- [Staging dev -> prod](docs/staging.md) — Flujo de trabajo, ritual de deploy, reglas
- [Guias de API](docs/guides/README.md) — Recetas: login, crear miembros, aprovisionar, consultar metricas
- [API](docs/api.md) — Endpoints, autenticacion, paginacion
- [Templates BIRD](docs/templates.md) — Como se genera la config, `include_globals`, editar templates
- [Arquitectura](docs/architecture.md) — Capas, patrones, convenciones

## Licencia

Apache 2.0
