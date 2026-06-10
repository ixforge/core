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
docker compose -f docker/docker-compose.dev.yml up -d

# Migraciones y usuario admin
uv run ixforge upgrade
uv run ixforge createsuperuser

# Iniciar servidor (hot reload)
IXFORGE_DEBUG=true uv run ixforge run
```

API disponible en `http://localhost:8000/api/v1/docs`.

## Tests

```bash
# PostgreSQL de testing (puerto 5433, tmpfs)
docker compose -f docker/docker-compose.testing.yml up -d

uv run pytest -v
uv run ruff check src/ tests/
uv run mypy src/
```

## CLI

```
ixforge run              Iniciar servidor API
ixforge ui               Iniciar portal admin (puerto 8001)
ixforge worker           Iniciar workers de tareas en background
ixforge upgrade          Ejecutar migraciones de base de datos
ixforge createsuperuser  Crear usuario administrador
ixforge backup           Backup comprimido de la base de datos
ixforge restore <file>   Restaurar desde archivo de backup
```

## Documentacion

- [Quickstart](docs/quickstart.md) — Instalacion, configuracion, Docker
- [API](docs/api.md) — Endpoints, autenticacion, paginacion
- [Arquitectura](docs/architecture.md) — Capas, patrones, convenciones

## Licencia

Apache 2.0
