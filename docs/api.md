# Referencia de la API

- Base URL: `/api/v1`
- Documentación interactiva: `/api/v1/docs` (Swagger) y `/api/v1/redoc` (ReDoc);
  esquema en `/api/v1/openapi.json`. Los cuerpos de request y response completos
  están ahí; esta página documenta paths, permisos y reglas
- Métricas Prometheus: `/metrics`, en la raíz de la app, fuera de `/api/v1`

Recetas con `curl` en [guides/README.md](guides/README.md); conceptos en
[architecture.md](architecture.md).

## Autenticación

| Método | Header | Descripción |
|--------|--------|-------------|
| JWT | `Authorization: Bearer <token>` | Se obtiene con `POST /auth/login`. Vence a los 30 minutos y no hay refresh |
| API key | `X-API-Key: <raw_key>` | Empieza con `ixf_`. El valor completo se devuelve una sola vez, al crearla |

Si llegan los dos headers, se usa el JWT. Sin credenciales, `401`.

Hay dos roles: `admin` y `member`. Varios endpoints distinguen entre un admin, que
ve todo, y un usuario `member`, que ve solo lo de su miembro (`member_id` del
usuario).

### API keys

Una API key pertenece **o** a un usuario (`POST /users/{id}/api-keys`) **o** a un
route server (`POST /route-servers/{id}/api-keys`), nunca a los dos. Hay dos
scopes de servicio:

| Scope | Lo usa | Habilita |
|-------|--------|----------|
| `agent:route_server` | El agent del route server | `/route-servers/{id}/agent/*` del route server al que está vinculada la key. Es el único scope de las keys de route server |
| `monitoring:read` | El collector | `GET /monitoring/targets` |

Y scopes de gestión de la forma `<recurso>:read` / `<recurso>:write`, donde
`read` cubre GET, HEAD y OPTIONS, y `write` todo lo demás. Recursos válidos:
`members`, `trunks`, `connections`, `bgp-sessions`, `ip-pools`,
`ip-assignments`, `vlans`, `switches`, `route-servers`, `locations`, `users`,
`ixp`, `events`, `contacts`, `custom-fields`, `rs-templates`, `metrics`.

El scope requerido se deriva del primer segmento del path después de `/api/v1`
y del método: `GET /api/v1/members/{id}/prefixes` pide `members:read`, y
`POST /api/v1/route-servers/{id}/config/generate` pide `route-servers:write`. Una
key sin ese scope recibe `403`. Consecuencias:

- `GET /auth/me` y `/rpki-servers` no tienen scope válido (`auth`, `rpki-servers`),
  así que una API key siempre recibe `403` ahí: solo aceptan JWT
- Una key de route server en un endpoint de gestión recibe `401`
- La key autentica como su usuario, así que no pasa de sus scopes **ni** del rol
  del usuario (doble candado): una key con `members:write` de un usuario
  `member` no puede crear miembros

Más detalle y ejemplos en [guides/autenticacion.md](guides/autenticacion.md).

## Paginación

Los listados principales usan paginación por cursor:

```
GET /members?limit=50&cursor=<cursor_opaco>
```

```json
{
  "items": [...],
  "next_cursor": "abc123...",
  "has_more": true
}
```

`limit` va de 1 a 200 (50 por defecto). El orden es por fecha de creación
ascendente, salvo `/route-servers/{id}/config/history`, que devuelve primero la
versión más nueva. Un cursor malformado da `422`.

| Forma | Endpoints |
|-------|-----------|
| Paginado con cursor | `/users`, `/users/{id}/api-keys`, `/members`, `/members/{id}/contacts`, `/locations`, `/switches`, `/vlans`, `/vlans/{id}/members`, `/ip-pools`, `/ip-pools/{id}/assignments`, `/trunks`, `/connections`, `/route-servers`, `/route-servers/{id}/peers`, `/route-servers/{id}/vlans`, `/route-servers/{id}/config/history`, `/rpki-servers`, `/bgp-sessions`, `/events`, `/custom-fields` |
| Array plano | `/trunks/{id}/vlans`, `/trunks/{id}/vlans/{tv_id}/ips`, `/trunks/{id}/connections`, `/route-servers/{id}/ips`, `/route-servers/{id}/api-keys`, `/rs-templates`, `/ip-pools/available` |
| `{"items": [...]}` sin cursor | `/members/{id}/prefixes`, `/members/{id}/prefix-events` (`limit` de 1 a 1000, 100 por defecto) |

## Formato de errores

Todo error de la aplicación usa este formato. `details` suele ser un objeto; en
los errores de validación de Pydantic es la lista de errores por campo.

```json
{
  "error": {
    "code": "NOT_FOUND",
    "message": "Member with id ... not found",
    "details": {}
  }
}
```

| Código | Status | Cuándo |
|--------|--------|--------|
| `UNAUTHORIZED` | 401 | Sin credenciales, token vencido o inválido, key inexistente o usuario inactivo |
| `FORBIDDEN` | 403 | Rol insuficiente, recurso de otro miembro o API key sin el scope |
| `NOT_FOUND` | 404 | El recurso no existe en el IXP, o todavía no hay IXP configurado |
| `CONFLICT` | 409 | Duplicados y borrados bloqueados por dependencias |
| `VALIDATION_ERROR` | 422 | Body o query inválido (Pydantic) y reglas de negocio: transiciones de estado, precondiciones |
| `INTERNAL_ERROR` | 500 | Error no manejado, o el commit falló después de procesar el request |

Dos respuestas no usan este formato: una ruta o método inexistente devuelve el
`{"detail": "Not Found"}` / `{"detail": "Method Not Allowed"}` de Starlette, y el
`429` de rate limiting devuelve `{"error": "Rate limit exceeded: ..."}`, con
`error` como string.

## Rate limiting

Por IP de la conexión. El límite general es `IXFORGE_RATE_LIMIT_PER_MINUTE` por
minuto (60 por defecto). `POST /auth/login` tiene 10 por minuto y `/metrics`, 60
por minuto.

Detrás de un proxy, uvicorn toma la IP real de `X-Forwarded-For` solo si el
proxy está en `FORWARDED_ALLOW_IPS` (por defecto `127.0.0.1`). Sin eso, todos los
clientes comparten la IP del proxy y el mismo límite.

## Convenciones

- Columna **Acceso** de las tablas:
  - **Público**: sin autenticación
  - **Auth**: cualquier usuario activo (JWT, o API key con el scope del recurso)
  - **Admin**: rol `admin`
  - **Propio**: un admin accede a todo; un usuario `member`, solo a lo de su miembro
- Las creaciones devuelven `201` con el recurso creado y los borrados `204` sin
  cuerpo. Las demás respuestas son `200` salvo que se indique otra cosa
- Los IDs son UUID

---

## Endpoints

### Sistema

| Método | Path | Acceso | Descripción |
|--------|------|--------|-------------|
| GET | `/health` | Público | Health check: `status` (`healthy` / `degraded`), `version` y `checks`. Devuelve `503` si la base no responde. `checks.task_queue` siempre informa `ok`: no se verifica |
| GET | `/setup/status` | Público | `{"configured": bool}`: si ya existe un IXP |
| POST | `/setup` | Público | Crea el IXP, el admin inicial e instala los templates BIRD por defecto. `201` con `{"message": "Setup completed"}`; `409` si ya hay un IXP |

### Auth

| Método | Path | Acceso | Descripción |
|--------|------|--------|-------------|
| POST | `/auth/login` | Público | `{"email", "password"}` -> `{"access_token", "token_type": "bearer"}`. `401` con el mismo mensaje para email inexistente, contraseña incorrecta o usuario inactivo. Requiere un IXP configurado |
| GET | `/auth/me` | Auth (solo JWT) | Usuario actual |

### IXP

| Método | Path | Acceso | Descripción |
|--------|------|--------|-------------|
| GET | `/ixp` | Auth | Datos del IXP |
| PATCH | `/ixp` | Admin | Modificar `name`, `website`, `country`, `city`, `peeringdb_id` |

### Usuarios y API keys de usuario

| Método | Path | Acceso | Descripción |
|--------|------|--------|-------------|
| GET | `/users` | Admin | Listar usuarios |
| POST | `/users` | Admin | Crear usuario (`role` por defecto `member`, contraseña de 8 caracteres o más). `409` si el email existe |
| GET | `/users/me` | Auth | Usuario actual |
| GET | `/users/{id}` | Admin | Obtener usuario |
| PATCH | `/users/{id}` | Admin | Modificar usuario. `409` si el admin intenta desactivarse o quitarse el rol `admin` a sí mismo, o si se desactiva o degrada al último admin activo |
| DELETE | `/users/{id}` | Admin | Borrar usuario. `409` si está activo o es el propio usuario |
| POST | `/users/{id}/api-keys` | Admin | Crear API key (`{"name", "scopes": [...]}`). Devuelve `raw_key` una sola vez. `422` si un scope no es válido |
| GET | `/users/{id}/api-keys` | Admin | Listar keys del usuario (sin el valor) |
| DELETE | `/users/{id}/api-keys/{key_id}` | Admin | Revocar la key (se borra) |

La API no expone `member_id` al crear ni al modificar usuarios: la asociación de
un usuario `member` con su miembro no se puede hacer por API.

### Miembros

| Método | Path | Acceso | Descripción |
|--------|------|--------|-------------|
| GET | `/members` | Propio | Listar. Un usuario `member` recibe solo su miembro, o una lista vacía |
| POST | `/members` | Admin | Crear miembro en estado `prospect`. `409` si el ASN ya existe en el IXP |
| GET | `/members/asn-lookup?asn=` | Auth | Nombre de un ASN (miembro local -> cache de 7 días -> PeeringDB). `name` puede ser `null` |
| GET | `/members/{id}` | Propio | Obtener miembro. `403` si es de otro |
| GET | `/members/{id}/asn-name` | Propio | Nombre del ASN del miembro |
| PATCH | `/members/{id}` | Admin | Modificar miembro. El estado no se cambia aquí, sino con `/transition` |
| POST | `/members/{id}/transition` | Admin | Cambiar estado (`{"state": "active"}`) |
| DELETE | `/members/{id}` | Admin | Borrar miembro. `409` si no está `terminated` |

Estados: `prospect` -> `provisioning`; `provisioning` -> `active` o `terminated`;
`active` -> `suspended` o `terminated`; `suspended` -> `active` o `terminated`.
Para activar hace falta al menos un trunk `active`; para pasar a `terminated`,
todos los trunks `decommissioned`. Una transición inválida da `422`.

### Logo del miembro

| Método | Path | Acceso | Descripción |
|--------|------|--------|-------------|
| GET | `/members/{id}/logo` | Auth | El logo como PNG. `404` si el miembro no tiene |
| POST | `/members/{id}/logo` | Admin | Subir logo (multipart, campo `file`): JPEG, PNG o WebP de hasta 2 MB, se guarda como PNG. `204` |
| DELETE | `/members/{id}/logo` | Admin | Borrar logo |

### Contactos

| Método | Path | Acceso | Descripción |
|--------|------|--------|-------------|
| GET | `/members/{id}/contacts` | Propio | Listar contactos del miembro |
| POST | `/members/{id}/contacts` | Propio | Crear contacto |
| PATCH | `/contacts/{id}` | Propio | Modificar contacto |
| DELETE | `/contacts/{id}` | Propio | Borrar contacto |

### Filtros de prefijos del miembro

| Método | Path | Acceso | Descripción |
|--------|------|--------|-------------|
| GET | `/members/{id}/prefix-filters/{af}` | Admin | Filtro del miembro para una familia. `404` si no hay fila |
| PUT | `/members/{id}/prefix-filters/{af}` | Admin | Crear o reemplazar el filtro: `origin_asns`, `prefixes`, `as_set`, `source` (`manual` / `irr`) |
| DELETE | `/members/{id}/prefix-filters/{af}` | Admin | Borrar el filtro |

`af` es `4` o `6`; otro valor da `422`, igual que un prefijo de la otra familia.
Un miembro **sin fila** se comporta como "solo su propio ASN, sin filtro de
prefijos", que es el default seguro. `origin_asns` vacío o en `null` también cae
al ASN del miembro.

`prefixes` en `null` desactiva el filtro de prefijos. La lista **vacía** es
distinta y se acepta: significa "no autorizar ningún prefijo". Es el caso de un
colector de rutas, que recibe y no anuncia: lista blanca vacía, no ausente.

`as_set` y `source` se guardan como referencia; el generador solo usa
`origin_asns` y `prefixes`. Crear, reemplazar o borrar un filtro encola la
regeneración de todos los route servers donde el miembro tiene sesiones.

### Prefijos anunciados

Lo que cada miembro anuncia ahora y lo que cambió. Lo escribe el agent, una fila
por prefijo y por sesión BGP; aquí se lee por miembro.

| Método | Path | Acceso | Descripción |
|--------|------|--------|-------------|
| GET | `/members/{id}/prefixes` | Auth | Prefijos que el miembro anuncia ahora, deduplicados entre route servers. Filtros: `prefix` (empieza con), `limit` |
| GET | `/members/{id}/prefix-events` | Auth | Eventos `announced`, `withdrawn` y `updated` (cambio de AS path o communities), del más nuevo al más viejo. Cada evento indica de qué route server vino, así que un mismo hecho aparece una vez por route server. Filtros: `prefix`, `limit` |

Un miembro inexistente da `404`, no una lista vacía.

Los prefijos cuelgan de la sesión BGP de un miembro o de un peer del route
server, nunca de los dos: el upstream no tiene sesión de miembro, pero sus
prefijos se listan igual, bajo el miembro cuya IP usa ese peer.

El agent lista hasta 500.000 prefijos por sesión. El tope existe para que una
sesión que se comporta mal no produzca un reporte sin límite, no para excluir el
tránsito.

Los eventos de prefijos se guardan 30 días (`cleanup_old_prefix_events`, todos
los días a las 03:30).

### Locations

| Método | Path | Acceso | Descripción |
|--------|------|--------|-------------|
| GET | `/locations` | Admin | Listar locations |
| POST | `/locations` | Admin | Crear location (`name`, `city`, `country` ISO de 2 letras). `409` si el nombre existe |
| GET | `/locations/{id}` | Admin | Obtener location |
| PATCH | `/locations/{id}` | Admin | Modificar location |
| DELETE | `/locations/{id}` | Admin | Borrar location. `409` si tiene switches |

### Switches

| Método | Path | Acceso | Descripción |
|--------|------|--------|-------------|
| GET | `/switches` | Admin | Listar switches |
| POST | `/switches` | Admin | Crear switch (`location_id` obligatorio). `409` si el nombre existe |
| GET | `/switches/{id}` | Admin | Obtener switch |
| PATCH | `/switches/{id}` | Admin | Modificar switch |
| DELETE | `/switches/{id}` | Admin | Borrar switch. `409` si tiene conexiones |

`snmp_community` se guarda cifrada y no se devuelve en las lecturas; solo
`/monitoring/targets` la entrega en claro.

### VLANs

| Método | Path | Acceso | Descripción |
|--------|------|--------|-------------|
| GET | `/vlans` | Admin | Listar VLANs |
| POST | `/vlans` | Admin | Crear VLAN (`vid` de 1 a 4094, `type`: `production`, `quarantine`, `management`, `private`, `other`). `409` si el VID existe |
| GET | `/vlans/{id}` | Admin | Obtener VLAN |
| PATCH | `/vlans/{id}` | Admin | Modificar VLAN |
| DELETE | `/vlans/{id}` | Admin | Borrar VLAN. `409` si tiene pools, trunks o route servers asociados |
| GET | `/vlans/{id}/members` | Admin | Miembros autorizados en la VLAN privada |
| POST | `/vlans/{id}/members` | Admin | Autorizar un miembro (`{"member_id"}`). `422` si la VLAN no es `private` |
| DELETE | `/vlans/{id}/members/{member_id}` | Admin | Quitar la autorización |

Asignar una VLAN `private` a un trunk exige que el miembro esté autorizado en ella.

### IP pools

| Método | Path | Acceso | Descripción |
|--------|------|--------|-------------|
| GET | `/ip-pools?vlan_id=` | Admin | Pools de una VLAN (`vlan_id` obligatorio) |
| POST | `/ip-pools` | Admin | Crear pool (`{"vlan_id", "network", "af"}`). `422` si el CIDR no es válido o no coincide con `af`; `409` si se solapa con otro pool del IXP |
| GET | `/ip-pools/available?vlan_id=` | Admin | Pools de la VLAN con disponibilidad (próxima IP libre, uso) |
| GET | `/ip-pools/{id}` | Admin | Obtener pool |
| DELETE | `/ip-pools/{id}` | Admin | Borrar pool. `409` si tiene asignaciones de miembros o de route servers |
| GET | `/ip-pools/{id}/assignments` | Admin | Asignaciones del pool |
| POST | `/ip-pools/{id}/assign` | Admin | Asignar una IP a un trunk VLAN (`{"trunk_vlan_id"}`; con `"address"` es manual, sin ella secuencial). `409` si la IP ya está asignada o el pool está lleno |
| DELETE | `/ip-assignments/{id}` | Admin | Liberar la asignación. A diferencia de `DELETE /trunks/{id}/vlans/{tv_id}/ips/{assignment_id}`, no verifica si una sesión BGP usa la IP |

### Trunks

| Método | Path | Acceso | Descripción |
|--------|------|--------|-------------|
| GET | `/trunks?member_id=` | Propio | Listar trunks. Un admin puede filtrar por `member_id`; un `member` ve los suyos (`403` si el usuario no tiene miembro) |
| POST | `/trunks` | Admin | Crear trunk en `draft` (`{"member_id", "name"}`). `422` si el miembro está `terminated` |
| GET | `/trunks/{id}` | Propio | Obtener trunk. `404` si es de otro miembro |
| PATCH | `/trunks/{id}` | Admin | Modificar trunk. `422` si está `decommissioned` |
| DELETE | `/trunks/{id}` | Admin | Borrar trunk. `422` si no está `decommissioned` |
| POST | `/trunks/{id}/transition` | Admin | Cambiar estado (`{"state": "active"}`) |
| GET | `/trunks/{id}/vlans` | Propio | VLANs asignadas al trunk |
| POST | `/trunks/{id}/vlans` | Admin | Asignar VLAN (`{"vlan_id"}`). `422` si el trunk está `disabled` o `decommissioned`; `409` si ya estaba |
| DELETE | `/trunks/{id}/vlans/{tv_id}` | Admin | Quitar VLAN. `409` si quedan IPs o sesiones BGP |
| GET | `/trunks/{id}/vlans/{tv_id}/ips` | Propio | IPs del trunk VLAN |
| POST | `/trunks/{id}/vlans/{tv_id}/ips` | Admin | Asignar IP (`{"pool_id", "address"}`; sin `address`, secuencial) |
| DELETE | `/trunks/{id}/vlans/{tv_id}/ips/{assignment_id}` | Admin | Liberar IP. `409` si una sesión BGP la usa |
| GET | `/trunks/{id}/connections` | Propio | Conexiones del trunk |
| POST | `/trunks/{id}/connections` | Admin | Agregar conexión en `draft` (`switch_id`, `name`, `type`, `speed`). `422` si el trunk está `disabled` o `decommissioned`, o si el `type` difiere del de las otras conexiones del trunk |

Estados: `draft` -> `provisioning`; `provisioning` -> `active` o `decommissioned`;
`active` -> `disabled`; `disabled` -> `active` o `decommissioned`. Para activar
hace falta al menos una conexión, al menos una VLAN y, por cada VLAN
`production`, al menos una IP. Para `decommissioned` no puede quedar ninguna
sesión BGP, IP ni VLAN, y todas las conexiones tienen que estar
`decommissioned`.

### Conexiones

Las conexiones se crean bajo su trunk con `POST /trunks/{id}/connections`; estos
endpoints operan sobre conexiones existentes.

| Método | Path | Acceso | Descripción |
|--------|------|--------|-------------|
| GET | `/connections?switch_id=` | Propio | Listar conexiones, con filtro opcional por switch. Un `member` ve las de sus trunks |
| GET | `/connections/{id}` | Propio | Obtener conexión. `404` si es de otro miembro |
| PATCH | `/connections/{id}` | Admin | Modificar conexión |
| DELETE | `/connections/{id}` | Admin | Borrar conexión. `422` si no está `decommissioned` |
| POST | `/connections/{id}/transition` | Admin | Cambiar estado (`{"state": "active"}`) |

Estados: los mismos que un trunk, sin precondiciones. Pasar a `active` o salir
de `active` encola la regeneración de los route servers con sesiones en ese trunk.

### Route servers

| Método | Path | Acceso | Descripción |
|--------|------|--------|-------------|
| GET | `/route-servers` | Admin | Listar route servers |
| POST | `/route-servers` | Admin | Crear route server |
| GET | `/route-servers/{id}` | Admin | Obtener route server (incluye `last_heartbeat_at` y `agent_version`) |
| PATCH | `/route-servers/{id}` | Admin | Modificar route server. Encola la regeneración del config |
| DELETE | `/route-servers/{id}` | Admin | Borrar route server. `409` si tiene sesiones BGP o IPs asignadas |
| GET | `/route-servers/{id}/vlans` | Admin | VLANs asociadas |
| POST | `/route-servers/{id}/vlans` | Admin | Asociar VLAN (`{"vlan_id"}`). `409` si ya estaba |
| DELETE | `/route-servers/{id}/vlans/{vlan_id}` | Admin | Quitar la asociación |
| GET | `/route-servers/{id}/ips` | Admin | IPs del route server |
| POST | `/route-servers/{id}/ips` | Admin | Asignar IP de un pool (`{"pool_id", "address"}`; sin `address`, secuencial). Una por familia (`409` si ya tiene); actualiza `ip_v4` o `ip_v6` |
| DELETE | `/route-servers/{id}/ips/{assignment_id}` | Admin | Liberar la IP y limpiar `ip_v4` o `ip_v6` |
| GET | `/route-servers/{id}/api-keys` | Admin | Keys de agent del route server (sin el valor) |
| POST | `/route-servers/{id}/api-keys` | Admin | Crear key de agent (`{"name"}`), con scope fijo `agent:route_server`. Devuelve `raw_key` una sola vez |
| DELETE | `/route-servers/{id}/api-keys/{key_id}` | Admin | Revocar la key (se borra) |
| GET | `/route-servers/{id}/peers` | Admin | Peers que no son miembros |
| POST | `/route-servers/{id}/peers` | Admin | Crear peer `upstream`, `collector` o `special`. `409` si la IP ya existe en el route server |
| GET | `/route-servers/{id}/peers/{peer_id}` | Admin | Obtener peer |
| PATCH | `/route-servers/{id}/peers/{peer_id}` | Admin | Modificar peer (incluye `admin_state`; `peer_ip` no se cambia) |
| DELETE | `/route-servers/{id}/peers/{peer_id}` | Admin | Borrar peer |

`passive_sessions` (por defecto `true`) y `rpki_enabled` (por defecto `false`)
son campos del route server: se leen y se escriben con el CRUD de arriba, y
cambiarlos regenera el config. Con `rpki_enabled` encendido, una ruta RPKI
inválida se descarta siempre.

Los peers de `/peers` son sesiones que **no pertenecen a un miembro**: upstream,
colectores, looking glass. La familia se deriva de `peer_ip`, no se envía. Sin
`local_asn`, el config usa el ASN del IXP. `mark_community` va en forma
`asn:value` y se valida con la misma regla que el generador: cada componente
admite hasta 65535, porque una community estándar son 32 bits partidos 16:16.
Crear, modificar o borrar un peer encola la regeneración del config.

### Servidores RPKI

| Método | Path | Acceso | Descripción |
|--------|------|--------|-------------|
| GET | `/rpki-servers` | Admin (solo JWT) | Listar servidores RTR |
| POST | `/rpki-servers` | Admin (solo JWT) | Crear servidor RTR (`name`, `host`, `port` 3323 por defecto, `route_server_id`, `transport`, tiempos de refresh, retry y expire). `409` si el nombre existe |
| GET | `/rpki-servers/{id}` | Admin (solo JWT) | Obtener servidor RTR |
| PATCH | `/rpki-servers/{id}` | Admin (solo JWT) | Modificar servidor RTR |
| DELETE | `/rpki-servers/{id}` | Admin (solo JWT) | Borrar servidor RTR |

`route_server_id` en `null` aplica el servidor a todos los route servers del IXP.
El transporte `ssh` se rechaza con `422`: está en el modelo, pero el generador
solo emite TCP. Cada cambio encola la regeneración del route server afectado, o
de todos los activos si el servidor aplica a todos.

### Generación de config

| Método | Path | Acceso | Descripción |
|--------|------|--------|-------------|
| POST | `/route-servers/{id}/config/generate` | Admin | Generar el config BIRD ahora, en el mismo request. `201` con la versión creada |
| GET | `/route-servers/{id}/config/history` | Admin | Versiones, de la más nueva a la más vieja |
| GET | `/route-servers/{id}/config/current` | Admin | Última versión. `404` si nunca se generó |
| GET | `/route-servers/{id}/config/diff?to=&from=` | Admin | Diff unificado (`{"current_hash", "new_hash", "diff"}`) |
| GET | `/route-servers/{id}/config/{version_id}` | Admin | Una versión, con el contenido generado completo |

Cada versión incluye `content`, `config_hash`, `template_snapshot`,
`generated_at`, `applied_at`, `apply_error` y `apply_error_at`. En el diff, `to`
es obligatorio; sin `from` se compara contra la versión anterior a `to` (o
contra vacío si no hay, con `current_hash` en `null`).

### Templates de route server

Los templates BIRD se guardan por IXP en la base y los usa la generación de
config. El set por defecto se instala en el setup del IXP. Detalle en
[templates.md](templates.md).

| Método | Path | Acceso | Descripción |
|--------|------|--------|-------------|
| GET | `/rs-templates` | Admin | Listar templates, ordenados por `filename` |
| POST | `/rs-templates` | Admin | Crear template (`filename`, `content`, `description`). `409` si el `filename` existe |
| POST | `/rs-templates/validate` | Admin | Validar la sintaxis Jinja2 sin guardar ni renderizar (`{"valid", "errors"}`) |
| GET | `/rs-templates/{id}` | Admin | Obtener template |
| PATCH | `/rs-templates/{id}` | Admin | Modificar `content` y/o `description`; `filename` no se cambia |
| DELETE | `/rs-templates/{id}` | Admin | Borrar template. `409` si está protegido o lo referencia otro template con `include` o `import` |
| POST | `/rs-templates/{id}/preview` | Admin | Renderiza el config completo de un route server (`{"route_server_id"}`) con los templates actuales, sin guardar una versión. Un error de template vuelve en `errors` con `200` |

Solo `bird.conf.j2` está protegido. Editar un template no regenera los configs:
hay que generarlos con `POST /route-servers/{id}/config/generate` o desde el
portal.

### Sesiones BGP

| Método | Path | Acceso | Descripción |
|--------|------|--------|-------------|
| GET | `/bgp-sessions?route_server_id=` | Propio | Sesiones de un route server (`route_server_id` obligatorio). Un `member` ve las suyas |
| POST | `/bgp-sessions` | Admin | Crear sesión (`{"route_server_id", "trunk_vlan_id", "af", "max_prefixes"}`, `max_prefixes` opcional). Nace con `admin_state` `up` y `oper_state` `unknown` |
| GET | `/bgp-sessions/{id}` | Propio | Obtener sesión. `403` si es de otro miembro |
| PATCH | `/bgp-sessions/{id}` | Admin | Cambiar `admin_state` (`{"admin_state": "up"}` o `"down"`) |
| DELETE | `/bgp-sessions/{id}` | Admin | Borrar sesión |

Crear exige un trunk `active` y una IP de la familia `af` en el trunk VLAN
(`422` si no); repetir route server, trunk VLAN y familia da `409`. `peer_ip` y
`peer_asn` no se guardan en la sesión: salen de la IP asignada y del ASN del
miembro. `prefixes_imported` y `prefixes_exported` son los del último reporte
del agent. Crear, modificar o borrar una sesión encola la regeneración del
config del route server.

### Agent (API key con `agent:route_server`)

La key tiene que estar vinculada al route server del path; si no, `403`.

| Método | Path | Descripción |
|--------|------|-------------|
| GET | `/route-servers/{id}/agent/config` | Última versión: `{"config_hash", "content", "generated_at"}`. `404` si nunca se generó |
| POST | `/route-servers/{id}/agent/config/applied` | Confirmar que la versión `{"config_hash"}` quedó aplicada. `204`; `404` si el hash no es de una versión del route server |
| POST | `/route-servers/{id}/agent/config/failed` | Informar que una versión no se pudo aplicar (`{"config_hash", "error"}`). `204` |
| POST | `/route-servers/{id}/agent/status` | Estado operativo y conteo de prefijos por sesión (`peer_ip`, `af`, `oper_state`, `prefixes_imported`, `prefixes_exported`; los conteos son opcionales y ausente no es cero). Una IP que no es sesión de miembro se busca entre los peers del route server (upstream, collectors), que también reciben estado y conteo. Responde `{"updated", "unchanged", "not_found"}` |
| POST | `/route-servers/{id}/agent/prefixes` | Prefijos que anuncia cada peer (prefijo, AS path y communities). Se guarda como espejo del último reporte; lo que desaparece queda como evento `withdrawn`. Hasta 1000 sesiones por reporte y 600.000 prefijos por sesión |
| POST | `/route-servers/{id}/agent/heartbeat` | `{"version", "uptime_seconds", "current_config_hash", "bird_instances"}`. Responde `{"acknowledged", "config_hash_match"}` y agrega `X-IXForge-Agent-Upgrade` si la versión es menor a la mínima o no se puede interpretar |

### Monitoring (API key con `monitoring:read`)

| Método | Path | Descripción |
|--------|------|-------------|
| GET | `/monitoring/targets` | `switches` activos (con `snmp_community` en claro), `ports` (conexiones `active`) y `member_ips` (IPs de miembros `active` en trunks `active`) |

### Métricas (VictoriaMetrics)

VictoriaMetrics escucha solo en localhost del Core, así que este router es la
única vía para un consumidor externo, incluido el sitio público. Toda respuesta
trae `disponible`: `false` significa que VictoriaMetrics no respondió, que no es
lo mismo que no tener datos. Acceso: **Auth** (con API key, `metrics:read`).

| Método | Path | Descripción |
|--------|------|-------------|
| GET | `/metrics/interfaces` | Valores actuales por conexión: tráfico, paquetes, errores, estado operativo. Filtros: `connection_id`, `member_id` |
| GET | `/metrics/interfaces/series` | Serie temporal de una métrica de interfaz. `range`, `metric`, `connection_id`, `member_id` |
| GET | `/metrics/icmp/series` | Latencia y pérdida de paquetes por IP de miembro. `range`, `metric` (`rtt`, `rtt_min`, `rtt_max`, `packet_loss`), `member_id` |
| GET | `/metrics/aggregate/series` | Tráfico total del IXP, entrada y salida, en el tiempo. `range` |
| GET | `/metrics/aggregate/peak` | Pico de tráfico del IXP en la ventana. `range` (24h por defecto) |
| GET | `/metrics/prefixes/series` | Prefijos que el miembro anuncia, por familia, en el tiempo. `member_id` (obligatorio, `404` si no existe), `range` (24h por defecto) |

`range` es uno de `1h`, `6h`, `24h`, `7d` (1h por defecto salvo donde se indica);
el paso se deriva de él. Los nombres de métrica son enumeraciones cerradas y no
texto libre, porque el valor termina dentro de una consulta PromQL. En
`/metrics/interfaces/series`, `metric` es `ixforge_interface_traffic_in_bps`
(por defecto), `ixforge_interface_traffic_out_bps`,
`ixforge_interface_packets_in_pps` o `ixforge_interface_packets_out_pps`.

`/metrics/prefixes/series` toma el máximo entre route servers, no la suma: los
dos reciben los mismos prefijos del mismo peer. Consulta el gauge
`ixforge_bgp_session_prefixes_imported` que el Core publica en `/metrics`, así
que solo devuelve datos si VictoriaMetrics hace scrape de `/metrics` del Core.

### Eventos

| Método | Path | Acceso | Descripción |
|--------|------|--------|-------------|
| GET | `/events` | Propio | Log de auditoría. Un admin filtra con `resource_type` y `resource_id`; un `member` solo ve los eventos de su miembro (`403` si el usuario no tiene miembro) |

Los eventos se guardan 90 días (`cleanup_old_events`, todos los días a las 03:00).

### Custom fields

| Método | Path | Acceso | Descripción |
|--------|------|--------|-------------|
| GET | `/custom-fields` | Auth | Listar definiciones. Filtro: `entity_type` (`member`, `connection`, `trunk`, `switch`, `vlan`) |
| POST | `/custom-fields` | Admin | Crear definición |
| PATCH | `/custom-fields/{id}` | Admin | Modificar definición |
| DELETE | `/custom-fields/{id}` | Admin | Borrar definición |

### IX-F

| Método | Path | Acceso | Descripción |
|--------|------|--------|-------------|
| GET | `/ixf/member-export` | Público | IX-F Member Export JSON, versión `1.0`. Con rate limit y cache en memoria de 5 minutos. Incluye los miembros `active` que no tienen `skip_ixf_export` |

### Prometheus

| Método | Path | Acceso | Descripción |
|--------|------|--------|-------------|
| GET | `/metrics` | Público | Métricas Prometheus. Se sirve en la raíz de la app (`/metrics`), fuera de `/api/v1`, no figura en OpenAPI y tiene un límite de 60 por minuto |
