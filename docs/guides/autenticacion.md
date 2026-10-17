# Autenticación

La API acepta dos métodos: **JWT** (para usuarios, humanos o scripts) y **API
keys** (para servicios como el agent y el collector, o integraciones con scopes
acotados).

```bash
CORE=http://localhost:8000
```

## Login con usuario (JWT)

`POST /api/v1/auth/login` con email y password devuelve un token Bearer que
expira a los 30 minutos. El endpoint admite 10 intentos por minuto por IP.

```bash
curl -s -X POST $CORE/api/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email": "admin@example.com", "password": "changeme123"}'
```

Respuesta:

```json
{"access_token": "eyJhbGci...", "token_type": "bearer"}
```

Guardar el token y usarlo en el header `Authorization` del resto de las llamadas:

```bash
TOKEN=$(curl -s -X POST $CORE/api/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"admin@example.com","password":"changeme123"}' | jq -r .access_token)

curl -s $CORE/api/v1/auth/me -H "Authorization: Bearer $TOKEN"
```

`GET /api/v1/auth/me` (o `/users/me`) devuelve el usuario actual; sirve para
validar que el token está vigente.

## API keys

Las API keys son para servicios, no para personas. Se envían en el header
`X-API-Key` y cada una sirve **solo** para lo que habilitan sus scopes.

Hay dos scopes de servicio (internos):

| Scope | Lo usa | Sirve para |
|-------|--------|------------|
| `monitoring:read` | El collector | `GET /monitoring/targets` |
| `agent:route_server` | Los agents de route server | Los endpoints `/route-servers/{id}/agent/*` del RS al que está vinculada |

Además hay scopes **granulares por recurso** para la API de gestión, con la forma
`<recurso>:read` y `<recurso>:write`. `read` habilita los GET del recurso y `write`
los POST/PUT/PATCH/DELETE. El recurso es el primer segmento del path después de
`/api/v1/`: `members`, `trunks`, `connections`, `bgp-sessions`, `ip-pools`,
`ip-assignments`, `vlans`, `switches`, `route-servers`, `locations`, `users`, `ixp`,
`events`, `contacts`, `custom-fields`, `rs-templates`, `metrics`. Salvo los endpoints
de servicio de la tabla anterior, los paths que no están en esa lista (por ejemplo
`/rpki-servers` o `/auth/me`) no admiten API key: requieren JWT.

Ejemplo: una key con `members:read` puede hacer `GET /members` y `GET /members/{id}`,
pero **no** `POST /members` (necesita `members:write`) ni consultar `/trunks` (necesita
`trunks:read`). Una key sin el scope del endpoint recibe **403**.

**Doble candado:** la key nunca puede superar sus scopes **ni** los permisos
del usuario dueño. Si pertenece a un usuario `member` (no admin), además queda
limitada por el rol. Para leer todos los miembros, la key tiene que estar en un
usuario admin y tener `members:read`.

Una key está vinculada **a un usuario o a un route server, nunca a ambos**. El
valor completo (`raw_key`) se devuelve **una sola vez** al crearla; hay que
guardarlo, porque no se puede recuperar después.

### Usar una key de la API de gestión

```bash
curl -s "$CORE/api/v1/members?limit=2" -H "X-API-Key: ixf_...tu_key"
```

En el portal, al crear la key en el detalle del usuario, se marca `read`/`write` por
cada recurso que necesite.

### Key de usuario (ej. para el collector)

`POST /api/v1/users/{user_id}/api-keys` (requiere admin):

```bash
curl -s -X POST $CORE/api/v1/users/$USER_ID/api-keys \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"name": "collector-prod", "scopes": ["monitoring:read"]}'
```

Respuesta (incluye `raw_key` solo aquí):

```json
{
  "id": "…", "prefix": "ixf_ab12cd34", "name": "collector-prod",
  "scopes": ["monitoring:read"], "is_active": true,
  "last_used_at": null, "created_at": "…",
  "raw_key": "ixf_ab12cd34…elrestodelakey"
}
```

Uso:

```bash
curl -s $CORE/api/v1/monitoring/targets -H "X-API-Key: ixf_ab12cd34…elrestodelakey"
```

### Key de agente (vinculada a un route server)

`POST /api/v1/route-servers/{rs_id}/api-keys`. El scope queda fijo en
`agent:route_server`; solo se envía el nombre:

```bash
curl -s -X POST $CORE/api/v1/route-servers/$RS_ID/api-keys \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"name": "rs1-agent"}'
```

Esa key solo sirve para los endpoints de agente de **ese** route server.

### Listar y revocar

```bash
# Keys de un usuario (paginado: items, next_cursor, has_more)
curl -s $CORE/api/v1/users/$USER_ID/api-keys -H "Authorization: Bearer $TOKEN"

# Keys de agente de un RS (lista simple)
curl -s $CORE/api/v1/route-servers/$RS_ID/api-keys -H "Authorization: Bearer $TOKEN"

# Revocar una key de usuario
curl -s -X DELETE $CORE/api/v1/users/$USER_ID/api-keys/$KEY_ID \
  -H "Authorization: Bearer $TOKEN"

# Revocar una key de agente
curl -s -X DELETE $CORE/api/v1/route-servers/$RS_ID/api-keys/$KEY_ID \
  -H "Authorization: Bearer $TOKEN"
```

Revocar es inmediato y definitivo (la key se borra): deja de autenticar en la
siguiente llamada, y cualquier servicio que la use empieza a recibir 401. En el
portal, cada key tiene un botón "Revocar" en el detalle del usuario.

El listado nunca devuelve el `raw_key`, solo el `prefix` (los primeros 12
caracteres) para identificarla.
