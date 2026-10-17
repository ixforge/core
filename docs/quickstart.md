# Inicio rápido

## Requisitos

- Python 3.12+
- [uv](https://docs.astral.sh/uv/)
- PostgreSQL 17 (o Docker)
- Node.js, solo para compilar los assets del portal fuera de Docker

## Desarrollo local

```bash
# instalar dependencias (incluye las de desarrollo)
cd core
uv sync

# configuración de desarrollo: IXFORGE_DEBUG=true y la base local
cp .env.example .env

# PostgreSQL de desarrollo en el puerto 5432
docker compose -f docker/docker-compose.dev.yml up -d postgres

# migraciones y schema de procrastinate
uv run ixforge upgrade

# API con hot reload
IXFORGE_DEBUG=true uv run ixforge run
```

`Settings` lee las variables del entorno y de un `.env` en el directorio actual.
Sin `IXFORGE_DEBUG=true`, la aplicación no arranca con el `IXFORGE_SECRET_KEY` por
defecto: por eso el `.env` de desarrollo.

La API queda en `http://localhost:8000/api/v1/docs` (Swagger UI).

Con la base vacía, crear el IXP y el usuario admin con el endpoint de setup (o
desde el portal en `/setup`). `createsuperuser` por sí solo no crea un IXP:

```bash
curl -X POST http://localhost:8000/api/v1/setup \
  -H 'Content-Type: application/json' \
  -d '{
    "ixp": {"name":"Example IX","short_name":"EXIX","asn":65000,"country":"CL","city":"Santiago"},
    "admin": {"full_name":"Admin","email":"admin@example.com","password":"changeme123"}
  }'
```

El setup también instala los templates BIRD por defecto. Solo funciona una vez:
con un IXP ya creado responde 409.

Notas:

- La regeneración de configs en segundo plano (por ejemplo, al activar un
  miembro) la ejecuta un worker. Sin uno, los route servers nunca reciben
  configs nuevas: levantarlo con `uv run ixforge worker`
- El portal necesita los assets compilados (CSS de Tailwind, Alpine, htmx), que
  no están en el repo: `npm ci && npm run build`, y después `uv run ixforge ui`
  (puerto 8001)
- El compose de desarrollo también puede levantar el stack completo (`core` en
  8000, `portal` en 8001, `postgres` en 5432) con
  `docker compose -f docker/docker-compose.dev.yml up -d`. En ese modo no hacen
  falta el `ixforge run` local ni las migraciones a mano: el entrypoint migra al
  arrancar. Ese compose no
  trae worker; para tener uno, ejecutar
  `docker compose -f docker/docker-compose.dev.yml exec core uv run ixforge worker`.
  Como monta el `src/` del host sobre la imagen, el portal también necesita el
  `npm run build` local

## Configuración

Todas las variables usan el prefijo `IXFORGE_`:

| Variable | Default | Descripción |
|----------|---------|-------------|
| `IXFORGE_DATABASE_URL` | `postgresql+asyncpg://ixforge:ixforge@localhost:5432/ixforge` | Conexión a la base |
| `IXFORGE_SECRET_KEY` | `change-me-...` | Firma de JWT, hash HMAC de las API keys, cookies de sesión del portal y cifrado de las communities SNMP de los switches. Cambiarla invalida las API keys existentes |
| `IXFORGE_DEBUG` | `false` | Activa reload, logs legibles en consola en vez de JSON y CORS de desarrollo; desactiva las cookies `Secure` y permite el `IXFORGE_SECRET_KEY` por defecto |
| `IXFORGE_CORS_ORIGINS` | `[]` (en debug: localhost y 127.0.0.1 en 3000 y 8001) | Orígenes CORS permitidos |
| `IXFORGE_RATE_LIMIT_PER_MINUTE` | `60` | Límite por IP y por minuto de la API (login tiene su propio límite de 10) |
| `IXFORGE_UI_SECURE_COOKIES` | `true` | Las cookies de sesión exigen HTTPS. Poner `false` si el portal se sirve por HTTP en una red interna de confianza |
| `IXFORGE_UI_PORT` | `8001` | Puerto de `ixforge ui` |
| `IXFORGE_CORE_URL` | `http://localhost:8000` | URL de la API que consume el portal |
| `IXFORGE_MEDIA_ROOT` | `./media` | Directorio de archivos subidos (logos de miembros) |
| `IXFORGE_MEDIA_URL` | `/media` | Prefijo de URL de los archivos subidos |
| `IXFORGE_VICTORIAMETRICS_URL` | `http://localhost:8428` | VictoriaMetrics que consulta el Core para las métricas (la misma donde escribe el collector) |
| `IXFORGE_VICTORIAMETRICS_TIMEOUT` | `10` | Timeout en segundos de las consultas a VictoriaMetrics |

Con `IXFORGE_DEBUG=false`, la aplicación no arranca si `IXFORGE_SECRET_KEY` queda
con el valor por defecto o tiene menos de 32 caracteres.

Fuera de `Settings`:

- `IXFORGE_AUTO_MIGRATE` (`true`): lo lee el entrypoint del contenedor, ver
  Migraciones automáticas más abajo
- `IXFORGE_PORT` (`8000`): puerto del host donde el compose de producción publica
  `core`
- `IXFORGE_ADMIN_EMAIL`, `IXFORGE_ADMIN_PASSWORD`, `IXFORGE_ADMIN_FULL_NAME`:
  credenciales para `createsuperuser` sin prompts

`config.py` define además flags `IXFORGE_MODULE_*` (`ui`, `switching`, `rpki`,
`peeringdb_sync`, `ixf_export`), pero hoy ningún componente las lee: todos los
routers de la API se registran siempre y el portal funciona sin
`IXFORGE_MODULE_UI`.

## Docker (producción)

```bash
cd docker

# crear el archivo de entorno (compose lo usa como env_file y para interpolar)
cat > .env <<'EOF'
POSTGRES_USER=ixforge
POSTGRES_PASSWORD=change-me
POSTGRES_DB=ixforge
IXFORGE_DATABASE_URL=postgresql+asyncpg://ixforge:change-me@postgres:5432/ixforge
IXFORGE_SECRET_KEY=change-me-to-a-random-string-at-least-32-chars
IXFORGE_DEBUG=false
# ¿portal servido por HTTP en una red interna de confianza? descomentar:
# IXFORGE_UI_SECURE_COOKIES=false
EOF
vi .env  # poner secretos reales; POSTGRES_PASSWORD e IXFORGE_DATABASE_URL tienen que coincidir

# levantar el stack (el entrypoint aplica las migraciones al arrancar)
docker compose up -d

# solo con IXFORGE_AUTO_MIGRATE=false: migraciones y schema de procrastinate
docker compose exec core uv run ixforge upgrade
```

El `IXFORGE_SECRET_KEY` del ejemplo es el valor por defecto, y con
`IXFORGE_DEBUG=false` la aplicación no arranca con él: generar uno real, por
ejemplo con `openssl rand -hex 32`.

Después, abrir `http://<host>:8001/setup` (o usar `POST /api/v1/setup`) para crear
el IXP y el usuario admin. El setup también instala los templates BIRD por
defecto; `createsuperuser` por sí solo no crea un IXP.

Servicios:

| Servicio | Descripción | Puerto |
|----------|-------------|--------|
| `core` | API FastAPI | 8000 (`IXFORGE_PORT`) |
| `portal` | UI web de admin y de miembros | 8001 |
| `worker` | Tareas en segundo plano de procrastinate | - |
| `postgres` | PostgreSQL 17 | interno |

El portal no recibe el `.env` completo: solo `IXFORGE_CORE_URL`,
`IXFORGE_SECRET_KEY`, `IXFORGE_DEBUG=false` e `IXFORGE_UI_SECURE_COOKIES`. No tiene
credenciales de base.

### Mirrors de Debian en el build

`deb.debian.org` y `security.debian.org` se degradan cada tanto: medido, 1 de
cada 3 descargas terminaba en timeout, desde dos redes distintas, y eso hace
fallar el build entero. Dos build args permiten apuntar a un mirror propio, con
los oficiales por defecto:

```bash
docker compose build \
  --build-arg DEBIAN_MIRROR=mi-mirror.example.net \
  --build-arg DEBIAN_SECURITY_MIRROR=mi-mirror.example.net
```

El compose también los toma de `DEBIAN_MIRROR` y `DEBIAN_SECURITY_MIRROR` en el
`.env`. Son dos porque el archivo principal y el de seguridad se sincronizan por
separado y un mirror local puede tener uno sin el otro.

Los assets (CSS de Tailwind, bundles de JS) se construyen en un stage con la
imagen oficial de node, no con `npm` de Debian: ese arrastra `node-gyp` ->
`libnode-dev` -> `libssl-dev`, que exige un `libssl3t64` más viejo que el de
`python:3.12-slim`, y apt rechaza el downgrade.

### Migraciones automáticas

El entrypoint aplica las migraciones al arrancar (`ixforge upgrade`), así que un
despliegue nuevo no necesita un paso manual. `core` y `worker` arrancan a la vez
y los dos pasan por el entrypoint; el lock de alembic hace que migre uno y el
otro espere. El portal no migra. `IXFORGE_AUTO_MIGRATE=false` lo desactiva para
quien prefiera controlar cuándo se migra.

Si la migración falla, el contenedor no arranca. Y con las migraciones
automáticas desactivadas, atención al health check: verifica que la conexión a la
base abra, **no** que el esquema exista. Con la base vacía reporta `healthy`
mientras la API responde 500 en cada request.

## Ejecutar los tests

```bash
# base de tests (puerto 5433, tmpfs efímero)
docker compose -f docker/docker-compose.testing.yml up -d

# validador BIRD; sin la imagen, los tests que lo usan se saltan
docker build -t ixforge-bird-validator:2 docker/bird-validator/

# tests
uv run pytest -v

# con cobertura
uv run pytest --cov=ixforge --cov-report=term-missing
```

Si el 5433 está ocupado, apuntar a otra base con `TEST_DATABASE_URL`. Con
`IXFORGE_REQUIRE_BIRD=1`, como en CI, la falta del validador hace fallar la suite.

## Comandos de la CLI

| Comando | Qué hace |
|---------|----------|
| `ixforge run` | Arranca la API (puerto 8000) |
| `ixforge ui` | Arranca el portal (`IXFORGE_UI_PORT`, 8001) |
| `ixforge worker [--queues <cola> ...]` | Arranca el worker; sin `--queues` atiende todas las colas (`config`, `maintenance`) |
| `ixforge upgrade` | Aplica el schema de procrastinate y `alembic upgrade head` |
| `ixforge createsuperuser` | Crea un admin adicional; exige que el IXP ya exista (el IXP y el primer admin se crean con `/setup`) |
| `ixforge backup` | Crea un backup comprimido de la base (`.sql.gz`) |
| `ixforge restore <archivo>` | Restaura un backup |

## Portal web

`ixforge ui` (el servicio `portal` en el compose de producción) sirve dos UIs
renderizadas en el servidor, en el puerto 8001:

- **Portal admin** en `/admin`: gestión de miembros y contactos, trunks,
  conexiones, switches, ubicaciones, VLANs, IPAM, route servers y sus templates
  BIRD, sesiones BGP, usuarios y API keys, campos personalizados, export IX-F,
  configuración del IXP y el log de auditoría
- **Portal de miembros** en `/portal`: vista de solo lectura, para usuarios con
  rol `member`, de sus propios trunks, sesiones BGP, perfil y contactos

El setup inicial está en `/setup`. El portal consume la API REST en
`IXFORGE_CORE_URL`.

## Backups

`ixforge backup` ejecuta `pg_dump` y escribe un dump SQL comprimido,
`ixforge_backup_<timestamp>.sql.gz`, en el directorio actual. Necesita las
herramientas cliente de Postgres, que vienen en la imagen de `core`; adentro del
contenedor el archivo queda en `/app`, que no es un volumen, así que hay que
sacarlo con `docker compose cp`. `restore` lo vuelca con `psql` sobre la base
configurada sin borrar nada antes: usarlo contra una base vacía.

Para backups programados, ejecutarlo desde cron en el host contra el contenedor
de postgres, por ejemplo:

```bash
docker compose exec -T postgres pg_dump -U ixforge -d ixforge --no-owner | gzip > backup.sql.gz
```

Guardar copias fuera del host de la base.

## Autenticación

Hay dos métodos (detalle en [guides/autenticacion.md](guides/autenticacion.md)):

```bash
# 1. token JWT Bearer
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@example.com","password":"changeme123"}' | jq -r .access_token)

curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/v1/members

# 2. API key de usuario (POST /api/v1/users/{id}/api-keys, con el scope members:read)
curl -H "X-API-Key: ixf_abc123..." http://localhost:8000/api/v1/members
```

Una API key de usuario solo pasa si tiene el scope del recurso
(`<recurso>:read` o `<recurso>:write`) y nunca supera el rol de su usuario. Las
keys de agente (`POST /api/v1/route-servers/{id}/api-keys`) solo sirven para los
endpoints de agente de ese route server.
