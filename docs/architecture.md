# Arquitectura

El Core es la API REST central de IXForge: guarda el modelo del IXP (miembros,
trunks, conexiones, VLANs, IPAM, route servers, sesiones BGP), genera la
configuración BIRD de cada route server y la expone a los demás componentes. Los
endpoints están en [api.md](api.md); los templates BIRD, en
[templates.md](templates.md).

## Stack

- **Runtime**: Python 3.12, FastAPI (ASGI), uvicorn
- **Base de datos**: PostgreSQL 17, SQLAlchemy 2.0 async (asyncpg)
- **Migraciones**: Alembic (async)
- **Validación**: Pydantic v2
- **Autenticación**: JWT HS256 (python-jose) y API keys guardadas como
  HMAC-SHA256 con `IXFORGE_SECRET_KEY`; contraseñas con bcrypt
- **Tareas en segundo plano**: Procrastinate 3.x (cola sobre PostgreSQL, sin Redis)
- **Generación de config**: templates Jinja2 para BIRD 2.x, guardados por IXP en la base
- **Portal admin y de miembros**: Starlette + Jinja2 + Tailwind + HTMX, renderizado
  en servidor, consume la API REST
- **Métricas**: prometheus-client en `/metrics`; tráfico e ICMP se leen de VictoriaMetrics
- **Rate limiting**: slowapi, por IP de la conexión (ver [api.md](api.md#rate-limiting))
- **Logging**: structlog (JSON en producción, consola con `IXFORGE_DEBUG=true`)

## Ecosistema y contratos

IXForge es multi-repo:

| Repo | Lenguaje | Rol |
|------|----------|-----|
| `core` (este) | Python | API REST, lógica de negocio, base de datos, portal |
| `agent` | Rust | Se ejecuta en cada route server: descarga el config BIRD, lo aplica y reporta sesiones y prefijos |
| `collector` | Python | Recolecta SNMP e ICMP de los targets que publica el Core y escribe en VictoriaMetrics |
| `e2e` | Python | Tests end-to-end del ecosistema completo |

Los contratos con los otros repos viven en `api/v1/agent.py` (agent) y
`api/v1/monitoring.py` (collector): cambiar un path, un campo o un código de
respuesta ahí rompe a esos componentes.

Dentro de este repo, el job `Core + Agent + BIRD` de
`.github/workflows/e2e.yml` inicia Core, agent y BIRD reales y ejecuta
`tests/pipeline_runner.py`. Detalle en [../TESTING.md](../TESTING.md).

## Capas

```
Petición HTTP
    |
    v
+-------------------------+
| Middlewares ASGI        |  main.py: CommitBeforeResponse, headers de seguridad,
|                         |  métricas, request ID, rate limit
+-------------------------+
    |
    v
+-------------------------+
| Capa API                |  api/v1/*.py: routers FastAPI
| (validación, auth)      |  api/deps.py: sesión de base, auth, scopes, IXP
+-------------------------+
    |
    v
+-------------------------+
| Capa de servicios       |  services/*.py: lógica de negocio y reglas
| (reglas de negocio)     |  services/config_generation.py: config BIRD
+-------------------------+
    |
    v
+-------------------------+
| Capa de modelos         |  models/*.py: ORM SQLAlchemy
| (persistencia)          |  schemas/*.py: schemas Pydantic
+-------------------------+
    |
    v
+-------------------------+
| PostgreSQL 17           |  Tipos nativos: UUID, JSONB, ARRAY, INET, CIDR
+-------------------------+
```

## Estructura del proyecto

```
src/ixforge/
  main.py              Factory de la app, middlewares, handlers de error, lifespan
                       (abre la app de Procrastinate para que los endpoints encolen)
  config.py            Settings de Pydantic (variables IXFORGE_*)
  cli.py               CLI: run, ui, worker, upgrade, createsuperuser, backup, restore
  database.py          Engine async, factory de sesiones y tenant_context
  enums.py             Enumeraciones del dominio (estados, tipos, políticas)
  exceptions.py        Jerarquía IXForgeError -> código HTTP
  logging.py           Configuración de structlog
  metrics.py           Contadores, histogramas y gauges de Prometheus
  rate_limit.py        Limiter de slowapi
  models/
    base.py            UUIDPrimaryKey, TimestampMixin, TenantMixin, ExtraDataMixin
                       y el filtro automático por tenant
    ixp.py             IXP (tenant de nivel superior)
    member.py          Member (máquina de estados)
    trunk.py           Trunk y TrunkVLAN (máquina de estados, agrupa conexiones y VLANs)
    connection.py      Connection (puerto físico o virtual de un trunk, máquina de estados)
    switch.py          Switch (community SNMP cifrada)
    location.py        Location (sitio o datacenter)
    vlan.py            VLAN
    vlan_member.py     Miembros autorizados en una VLAN privada
    ip.py              IPPool e IPAssignment
    route_server.py    RouteServer
    route_server_vlan.py   Asociación route server <-> VLAN
    route_server_peer.py   Peers del route server que no son miembros
                           (upstream, collector, special)
    rs_ip_assignment.py    IPs del route server (IPAM)
    rs_template.py     RouteServerTemplate (templates BIRD por IXP)
    rpki_server.py     Servidores RTR para validación RPKI
    bgp_session.py     BGPSession
    bgp_prefix.py      Prefijos que anuncia cada peer (espejo) y su historial
    member_prefix_filter.py  Filtro de prefijos y ASNs de origen por miembro y familia
    config.py          ConfigVersion (cada config BIRD generado)
    event.py           Event (log de auditoría)
    contact.py         Contact
    user.py            User (roles admin y member)
    api_key.py         APIKey (con scopes; de usuario XOR de route server)
    asn_cache.py       Cache global de nombres de ASN
    custom_field.py    CustomFieldDefinition
    types.py           Tipos de columna propios (INET, CIDR, MACADDR)
  schemas/             Schemas Pydantic de request y response, por recurso, más
                       los transversales (setup, monitoring, agent, common)
  services/            Lógica de negocio por recurso (members, trunks, connections,
                       switches, vlans, ipam, route_servers, bgp_sessions, ...)
    config_generation.py   Contexto de render, render de bird.conf.j2, hash y diff
    default_templates.py   Set canónico de templates BIRD, instalado en el setup
    rs_templates.py        CRUD de templates, chequeo de referencias, sintaxis, preview
    template_env.py        Entorno Jinja2 sandboxed con los templates de la base
    template_filters.py    Filtros propios (ipaddr, bird_str, prefixlist, bird_community, ...)
    communities.py         Communities informativas por tipo de miembro, de peer y RPKI
    setup.py               Alta del IXP y el admin inicial (instala los templates)
    asn_lookup.py          Nombre de un ASN (miembro local -> cache de 7 días -> PeeringDB)
    monitoring.py          Targets de monitoreo para el collector
    metricas.py            Consultas a VictoriaMetrics
    prefijos_bgp.py        Prefijos y eventos de prefijos por miembro
    ixf_export.py          IX-F Member Export
  api/
    deps.py            Dependencias FastAPI (sesión de base, auth, scopes, IXP)
    v1/router.py       Agregador de routers
    v1/*.py            Endpoints (agent.py para el agent, monitoring.py para el
                       collector, rs_api_keys.py para las keys de agent)
  ui/
    app.py             App Starlette (portal admin y portal de miembros)
    api_client.py      Cliente HTTP contra la API REST
    routes/            Vistas renderizadas en servidor (/admin/*, /portal/*, /login, /setup)
    templates/         Templates Jinja2 (Tailwind, HTMX)
  tasks/
    setup.py           App de Procrastinate
    config.py          Regeneración del config y helper para encolarla (cola config)
    maintenance.py     Limpiezas periódicas (cola maintenance)
alembic/               Migraciones; env.py toma el lock que las serializa
docker/                Dockerfile, archivos de docker compose, entrypoint e
                       imagen del validador BIRD
tests/                 Un módulo por recurso o feature (pytest, asyncio_mode auto);
                       conftest.py da fixtures de base, cliente y auth sobre el
                       postgres de testing (puerto 5433); bird_validator.py valida
                       configs con bird -p; pipeline_runner.py es el pipeline
                       Core -> Agent -> BIRD
```

## Patrones clave

### Preparado para multi-tenant

Los modelos de dominio llevan `ixp_id` vía `TenantMixin`. Quedan fuera, a
propósito, `ixps`, `users`, `api_keys`, `config_versions` (cuelga de su route
server) y `asn_cache` (global).

Hoy el Core opera en modo single-tenant: `get_ixp_id` (`api/deps.py`) resuelve
el primer IXP de la base. Esa dependencia, las del agent y del collector y las
tareas en segundo plano fijan `tenant_context`, y un listener `do_orm_execute`
de `models/base.py` agrega `ixp_id = <tenant>` a toda consulta sobre un modelo
con `TenantMixin` (defensa en profundidad, además de los `WHERE` explícitos de
los servicios). `RequestIDMiddleware` resetea el contexto en cada request.

### Máquinas de estado

Las transiciones se validan en la capa de servicios: cada estado tiene un
conjunto explícito de destinos permitidos, y una transición inválida devuelve
`422` con `current_state` y `target_state` en `details`. Todo cambio de estado
emite un evento de auditoría (`member.state_changed`, `trunk.state_changed`,
`connection.state_changed`).

| Entidad | Transiciones |
|---------|--------------|
| Member | `prospect` -> `provisioning`; `provisioning` -> `active` o `terminated`; `active` -> `suspended` o `terminated`; `suspended` -> `active` o `terminated` |
| Trunk | `draft` -> `provisioning`; `provisioning` -> `active` o `decommissioned`; `active` -> `disabled`; `disabled` -> `active` o `decommissioned` |
| Connection | Las mismas que Trunk |

El orden importa:

- Un trunk no se crea para un miembro `terminated`
- Para activar un trunk hace falta al menos una conexión, al menos una VLAN
  asignada y, por cada VLAN de tipo `production`, al menos una IP
- Una sesión BGP solo se crea sobre un trunk `active` que tenga IP de esa familia
  en el trunk VLAN
- Un miembro pasa de `provisioning` a `active` solo con al menos un trunk `active`
- Para dar de baja un trunk (`decommissioned`) no puede quedar ninguna sesión BGP,
  IP ni VLAN, y todas sus conexiones tienen que estar `decommissioned`
- Un miembro pasa a `terminated` solo con todos sus trunks `decommissioned`

### IPAM

Los pools son CIDR de una familia asociados a una VLAN, y dos pools del mismo
IXP no pueden solaparse. La asignación es:

- **Secuencial**: la siguiente dirección libre del pool
- **Manual**: una dirección concreta, validada contra el pool

En ambos casos se excluyen las direcciones reservadas: en IPv4, red y broadcast
para prefijos más cortos que /31; en IPv6, la dirección de red (anycast de
subnet-router) para prefijos más cortos que /127. `ip_assignments.address` y
`rs_ip_assignments.address` son únicas en la base, y el servicio además impide
que la misma IP quede asignada a un miembro y a un route server.

### Generación de config BIRD

Los templates son documentos Jinja2 guardados por IXP en la tabla
`route_server_templates`, editables desde el portal admin. Guardar no valida la
sintaxis: eso lo hace aparte `POST /rs-templates/validate`. La fuente canónica es `services/default_templates.py`, que `run_setup`
instala al crear el IXP. Solo `bird.conf.j2` está protegido contra borrado, y un
template referenciado por otro con `include` o `import` tampoco se puede borrar.

El config generado es **un solo archivo** IPv4 + IPv6 para un único daemon BIRD
2.x, salido de **un solo render** de `bird.conf.j2` con `peers_v4`, `peers_v6`,
`rs_peers_v4` y `rs_peers_v6` en el contexto. El entorno es un
`SandboxedEnvironment` con `StrictUndefined`: un atributo inexistente rompe el
render en vez de producir un config inválido.

Entra al config:

- Cada sesión BGP con `admin_state` `up`, de un trunk `active` de un miembro
  `active`, cuyo trunk VLAN tiene IP de la familia de la sesión
- Cada peer del route server que no es miembro (`route_server_peers`) con
  `admin_state` `up`
- El filtro de prefijos y ASNs de origen del miembro (`member_prefix_filters`);
  sin fila, solo el ASN del miembro y sin filtro de prefijos

Cada generación guarda una fila en `config_versions` con el contenido, el hash
SHA-256 (que el agent usa para detectar cambios), un snapshot de todos los
templates del IXP y quién la generó. El hash se calcula sobre el render con la
línea `# Config hash:` vacía y después se rellena. Los diffs no se guardan: se
calculan al pedirlos.

Los filtros de import del route server nunca rechazan: marcan con una large
community y aceptan; el único `reject` vive en `f_export_to_master`. Los símbolos
BIRD se truncan a 55 caracteres recortando el nombre, nunca la IP ni la familia.
El mecanismo completo y cómo editar templates están en
[templates.md](templates.md).

### Comunicación con el agent

Cada agent se autentica con una API key vinculada a su route server (scope
`agent:route_server`, creada con `POST /route-servers/{id}/api-keys`). Una key
de otro route server recibe `403`. El flujo:

1. **Config** (`GET .../agent/config`): el agent compara el hash con su copia
   local y descarga el contenido si cambió. `404` si nunca se generó una versión
2. **Aplicada** (`POST .../agent/config/applied`): confirma que la versión con
   ese hash está en servicio; marca `applied_at` y limpia el error anterior
3. **Fallida** (`POST .../agent/config/failed`): informa que la versión no se
   pudo aplicar (por ejemplo, `bird -p` falló). El error queda en
   `apply_error`, y el portal lo muestra
4. **Estado** (`POST .../agent/status`): el agent reporta todos los protocolos
   BIRD sin distinguir. Cada entrada se cruza por `(peer_ip, af)` con las
   sesiones de miembro y, si no hay coincidencia, por `peer_ip` con los peers
   del route server (upstream, collectors). Se guarda el estado operativo y,
   por sesión, cuántos prefijos importó y exportó. Los dos conteos son
   opcionales: una sesión que no está establecida no tiene conteo, y ausente no
   es cero. El conteo se guarda en cada reporte, aunque el estado no cambie.
   Las sesiones de miembro emiten `bgp_session.up` y `bgp_session.down`

   Los conteos también se publican en `/metrics` como
   `ixforge_bgp_session_prefixes_imported` y `..._exported`, con etiquetas
   `route_server_id`, `peer_asn` y `af`. A una sesión sin conteo se le borra la
   serie en vez de ponerla en cero, así el gráfico muestra un hueco y no un valor
   viejo. La columna solo guarda el último valor: para tener historia hay que
   configurar el scrape de `/metrics`
5. **Prefijos** (`POST .../agent/prefixes`): cada 10 ciclos, el agent lista los
   prefijos que anuncia cada peer, con AS path y communities. El Core guarda un
   espejo del último reporte en `bgp_session_prefixes` y convierte la diferencia
   con el anterior en eventos `announced`, `withdrawn` y `updated` en
   `bgp_prefix_events`. El agent lista hasta 500.000 prefijos por sesión; el
   Core acepta hasta 600.000
6. **Heartbeat** (`POST .../agent/heartbeat`): actualiza `last_heartbeat_at` y
   `agent_version`, responde si el hash del agent coincide con la última versión
   y agrega el header `X-IXForge-Agent-Upgrade` si la versión es menor a la
   mínima o no se puede interpretar

### Tareas en segundo plano

Procrastinate usa PostgreSQL como cola. `ixforge worker` escucha todas las colas;
`ixforge worker --queues config maintenance` limita a las indicadas.

- **config**: `generate_route_server_config` regenera el config de un route
  server; `regenerate_configs_for_member` y `regenerate_configs_for_trunk`
  encolan una regeneración por cada route server con sesiones de ese miembro o
  trunk
- **maintenance** (periódicas): `cleanup_old_events` todos los días a las 03:00
  (retención de 90 días), `cleanup_old_prefix_events` todos los días a las 03:30
  (30 días) y `cleanup_config_versions` los domingos a las 04:00 (conserva las
  últimas 100 por route server y nunca borra una versión aplicada)

Encolan regeneración: el cambio de estado de un miembro, de un trunk o de una
conexión desde o hacia `active`; crear, borrar o cambiar `admin_state` de una
sesión BGP; editar un route server; crear, editar o borrar un peer de route
server, un servidor RPKI o un filtro de prefijos. No encolan: la edición de
templates ni la asignación de IPs al route server. En esos
casos, o si la cola no está disponible (queda un warning
`config_regeneration.defer_failed` en el log), se regenera a mano con
`POST /route-servers/{id}/config/generate` o desde el portal.

La app de Procrastinate tiene que abrirse (`open_async`) en todo proceso que use
la cola: el worker, la aplicación del schema en `ixforge upgrade` y el lifespan
de la API, para que los endpoints puedan hacer `defer_async`. Sin eso el encolado
falla y solo queda el warning.

### Commit antes de responder

El commit de la sesión no vive en el código posterior al `yield` de la
dependencia: FastAPI ejecuta eso **después de entregar la respuesta al
cliente**. Lo hace `CommitBeforeResponse` (`main.py`), un middleware ASGI puro
que intercepta el envío y hace el commit antes de reenviar el
`http.response.start`. Es el middleware más externo, y solo hace commit si el
status es menor a 400.

Hacer el commit después del `yield` tiene dos consecuencias, medidas contra un
despliegue real:

1. La API confirma antes de saber. Devuelve `201` y solo después intenta
   guardar; si el commit falla, el cliente ya tiene confirmación de algo que no
   existe, sin forma de enterarse
2. Crear y usar acto seguido falla. Crear un route server y pedirle su API key
   da `404` en **4 de cada 6** intentos, porque la fila todavía no es visible
   para la petición siguiente

Si el commit falla, el middleware hace rollback, descarta la respuesta original
y manda un `500` con el formato de error del proyecto.

**Punto ciego de los tests:** la suite usa una sesión transaccional con
rollback, donde el commit nunca ocurre de verdad. Todo lo que dependa de
*cuándo* se hace el commit es invisible ahí. Los tests de
`test_commit_antes_de_responder.py` verifican el orden con una sesión falsa, no
intentan ganarle a la carrera.

### Middlewares

Los middlewares propios son ASGI puro, porque `BaseHTTPMiddleware` no es seguro
con asyncpg. Del más externo al más interno:

- `CommitBeforeResponse`: commit antes del primer byte (ver arriba)
- `SecurityHeadersMiddleware`: `X-Content-Type-Options: nosniff`,
  `X-Frame-Options: DENY`, `Referrer-Policy: strict-origin-when-cross-origin`
- `MetricsMiddleware`: `ixforge_http_requests_total` e
  `ixforge_http_request_duration_seconds`, etiquetados por el template de la ruta
  para no disparar la cardinalidad
- `RequestIDMiddleware`: toma `X-Request-ID` o genera uno, lo agrega al contexto
  de structlog y a la respuesta
- `SlowAPIMiddleware` (slowapi): es el único `BaseHTTPMiddleware`; los tests lo
  desactivan con `create_app(enable_rate_limit=False)`
- `CORSMiddleware`: solo si `IXFORGE_CORS_ORIGINS` tiene valores (en debug, sin
  valor explícito, toma `localhost` y `127.0.0.1` en los puertos 3000 y 8001)

### Migraciones al arrancar

El entrypoint del contenedor (`docker/entrypoint.sh`) ejecuta `ixforge upgrade`
antes del comando pedido: primero intenta aplicar el schema de Procrastinate
(si falla, deja un aviso y sigue) y después `alembic upgrade head`.
`IXFORGE_AUTO_MIGRATE=false` lo desactiva.

El portal (`ui`) **no** migra: es una UI que habla con la API por HTTP y no
tiene, ni debe tener, credenciales de base de datos.

Los servicios que sí migran (`run` y `worker`) arrancan a la vez desde la misma
imagen, así que `alembic/env.py` toma un `pg_advisory_lock` **antes** de
`run_sync`. La ubicación importa: alembic lee `alembic_version` y planifica qué
aplicar dentro de `do_run_migrations`, así que tomarlo más tarde serializa la
ejecución pero no la planificación, y el segundo reaplica todo sobre una base ya
migrada. Es lock de sesión y no de transacción porque tiene que sobrevivir a las
transacciones que alembic abre por cada migración.

### Custom fields

Member, Trunk, Connection, Switch y VLAN tienen una columna JSONB `extra_data`
(`ExtraDataMixin`). Las definiciones (`CustomFieldDefinition`) fijan por tipo de
entidad qué claves se esperan y de qué tipo (`string`, `integer`, `boolean`,
`url`, `email`), y los servicios validan `extra_data` contra ellas al crear y al
actualizar.

### Secretos derivados de `IXFORGE_SECRET_KEY`

La misma clave firma los JWT, es la clave del HMAC de las API keys y, vía
SHA-256, la clave Fernet con la que se cifra la community SNMP de cada switch.
Cambiarla invalida los tokens emitidos y todas las API keys, y deja ilegibles
las communities guardadas. Fuera de debug, la app no arranca si la clave es la
de ejemplo o tiene menos de 32 caracteres.

### Portal

`ixforge ui` inicia una app Starlette aparte (`ui/app.py`, puerto
`IXFORGE_UI_PORT`, 8001 por defecto) que solo habla con el Core por HTTP
(`IXFORGE_CORE_URL`), con el JWT guardado en una cookie de sesión firmada. Sirve
el portal admin (`/admin/*`), el portal de miembros (`/portal/*`), `/login`,
`/setup` y los logos de `/media`. Mientras no haya un IXP configurado,
`SetupRedirectMiddleware` redirige todo a `/setup`.
