# Autenticación

La API acepta dos métodos: **JWT** (para usuarios, humanos o scripts) y **API
keys** (para servicios: agent y collector).

```bash
CORE=http://localhost:8000
```

## Login con usuario (JWT)

`POST /api/v1/auth/login` con email y password devuelve un token Bearer que
expira a los 30 minutos.

```bash
curl -s -X POST $CORE/api/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email": "admin@example.com", "password": "changeme123"}'
```

Respuesta:

```json
{"access_token": "eyJhbGci...", "token_type": "bearer"}
```

Guarda el token y úsalo en el header `Authorization` del resto de llamadas:

```bash
TOKEN=$(curl -s -X POST $CORE/api/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"admin@example.com","password":"changeme123"}' | jq -r .access_token)

curl -s $CORE/api/v1/auth/me -H "Authorization: Bearer $TOKEN"
```

`GET /api/v1/auth/me` (o `/users/me`) devuelve el usuario actual; sirve para
validar que el token está vigente.

## API keys

Las API keys son para servicios, no para personas. Se mandan en el header
`X-API-Key` y cada una sirve **solo** para los endpoints de su scope, nada más.
Scopes válidos:

| Scope | Lo usa | Sirve para |
|-------|--------|---------|
| `monitoring:read` | El collector | `GET /monitoring/targets` |
| `agent:route_server` | Los agents de route server | Los endpoints `/route-servers/{id}/agent/*` del RS al que está vinculada |

Una API key **no** autentica el resto del API (miembros, usuarios, trunks, etc.):
esos endpoints piden un JWT de admin. O sea una key de scope `monitoring:read`
sirve para leer los targets de monitoreo y para nada más, aunque cuelgue de un
usuario admin. Para operar el API se usa el JWT, no la key.

Una key está vinculada **a un usuario o a un route server, nunca a ambos**. El
valor crudo (`raw_key`) se devuelve **una sola vez** al crearla; guárdalo, no se
puede recuperar después.

### Key de usuario (ej. para el collector)

`POST /api/v1/users/{user_id}/api-keys`:

```bash
curl -s -X POST $CORE/api/v1/users/$USER_ID/api-keys \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"name": "collector-prod", "scopes": ["monitoring:read"]}'
```

Respuesta (incluye `raw_key` solo aquí):

```json
{
  "id": "…", "prefix": "ixf_ab12", "name": "collector-prod",
  "scopes": ["monitoring:read"], "is_active": true,
  "last_used_at": null, "created_at": "…",
  "raw_key": "ixf_ab12…elrestodelakey"
}
```

Uso:

```bash
curl -s $CORE/api/v1/monitoring/targets -H "X-API-Key: ixf_ab12…elrestodelakey"
```

### Key de agente (vinculada a un route server)

`POST /api/v1/route-servers/{rs_id}/api-keys`. El scope queda fijo en
`agent:route_server`, solo se pasa el nombre:

```bash
curl -s -X POST $CORE/api/v1/route-servers/$RS_ID/api-keys \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"name": "rs1-agent"}'
```

Esa key solo sirve para los endpoints de agente de **ese** route server.

### Listar y revocar

```bash
# Keys de un usuario
curl -s $CORE/api/v1/users/$USER_ID/api-keys -H "Authorization: Bearer $TOKEN"

# Keys de agente de un RS
curl -s $CORE/api/v1/route-servers/$RS_ID/api-keys -H "Authorization: Bearer $TOKEN"

# Revocar una key de usuario
curl -s -X DELETE $CORE/api/v1/users/$USER_ID/api-keys/$KEY_ID \
  -H "Authorization: Bearer $TOKEN"

# Revocar una key de agente
curl -s -X DELETE $CORE/api/v1/route-servers/$RS_ID/api-keys/$KEY_ID \
  -H "Authorization: Bearer $TOKEN"
```

Revocar es inmediato y definitivo: la key deja de autenticar en la siguiente
llamada, y cualquier servicio que la use empieza a recibir 401. En el portal
admin, cada key tiene un boton "Revocar" en el detalle del usuario.

El listado nunca devuelve el `raw_key`, solo el `prefix` para identificarla.
