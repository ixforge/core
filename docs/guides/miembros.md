# Miembros

CRUD de miembros vía API. Requiere JWT de admin (ver [autenticacion.md](autenticacion.md)).

```bash
CORE=http://localhost:8000
# TOKEN=... (ver guía de autenticación)
```

## Crear un miembro

`POST /api/v1/members`. Campos obligatorios: `name`, `short_name`, `asn`. El
resto es opcional.

```bash
curl -s -X POST $CORE/api/v1/members \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{
    "name": "Ejemplo Networks SpA",
    "short_name": "EJEMPLO",
    "asn": 64500,
    "peering_policy": "open",
    "member_type": "isp",
    "contract_type": "standard",
    "country": "CL",
    "city": "Santiago",
    "website": "https://ejemplo.example"
  }'
```

Valores de los enums:

- `peering_policy`: `open` (default), `selective`, `restrictive`, `no`
- `member_type`: `isp`, `cdn`, `ixp`, `academico`, `gobierno`, `corporativo`, `infraestructura_critica`, `otro`
- `contract_type`: `free`, `standard`
- `country`: código ISO de 2 letras (mayúsculas)

El miembro nace en estado `prospect`. La respuesta incluye su `id`:

```bash
MEMBER_ID=$(curl -s -X POST $CORE/api/v1/members \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"name":"Ejemplo Networks SpA","short_name":"EJEMPLO","asn":64500}' | jq -r .id)
```

## Listar (con paginación)

`GET /api/v1/members?limit=&cursor=`. Paginación por cursor: la respuesta trae
`items`, `next_cursor` y `has_more`.

```bash
curl -s "$CORE/api/v1/members?limit=50" -H "Authorization: Bearer $TOKEN"
```

```json
{"items": [ ... ], "next_cursor": "eyJ...", "has_more": true}
```

Recorrer todas las páginas:

```bash
cursor=""
while :; do
  page=$(curl -s "$CORE/api/v1/members?limit=100&cursor=$cursor" -H "Authorization: Bearer $TOKEN")
  echo "$page" | jq -r '.items[] | "\(.asn)\t\(.name)\t\(.state)"'
  [ "$(echo "$page" | jq -r .has_more)" = "true" ] || break
  cursor=$(echo "$page" | jq -r .next_cursor)
done
```

`limit` va de 1 a 200 (default 50).

## Consultar uno

```bash
curl -s $CORE/api/v1/members/$MEMBER_ID -H "Authorization: Bearer $TOKEN"
```

## Modificar

`PATCH /api/v1/members/{id}`. Solo manda los campos que quieras cambiar.

```bash
curl -s -X PATCH $CORE/api/v1/members/$MEMBER_ID \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"peering_policy": "selective", "notes": "migrado a peering selectivo"}'
```

Dos detalles importantes:

- El **ASN no se puede cambiar** después de crear el miembro (no es un campo de update). Si está mal, hay que borrar y recrear.
- El **estado no se cambia por PATCH**, se usa el endpoint de transición (abajo).

## Cambiar de estado

`POST /api/v1/members/{id}/transition` con `{"state": "..."}`. Transiciones
permitidas:

```
prospect -> provisioning
provisioning -> active | terminated
active -> suspended | terminated
suspended -> active | terminated
```

```bash
curl -s -X POST $CORE/api/v1/members/$MEMBER_ID/transition \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"state": "provisioning"}'
```

Para pasar de `provisioning` a `active` el miembro necesita **al menos un trunk
activo**; si no, la API responde 422. Ver [aprovisionamiento.md](aprovisionamiento.md)
para el flujo completo.

## Borrar

Solo se puede borrar un miembro en estado `terminated` (si no, la API responde
409). Para llegar ahí desde `prospect` hay que recorrer las transiciones:
`prospect -> provisioning -> terminated`. Lo mismo aplica al comentario de arriba
sobre el ASN: para "borrar y recrear" hay que terminar el miembro primero.

```bash
curl -s -X POST $CORE/api/v1/members/$MEMBER_ID/transition \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"state": "terminated"}'

curl -s -X DELETE $CORE/api/v1/members/$MEMBER_ID -H "Authorization: Bearer $TOKEN"
```

## Lookup de ASN

Resolver el nombre de un ASN antes de crear el miembro (busca en los miembros
locales, luego en la cache con TTL de 7 días, y por último en PeeringDB):

```bash
curl -s "$CORE/api/v1/members/asn-lookup?asn=64500" -H "Authorization: Bearer $TOKEN"
# {"asn": 64500, "name": "EJEMPLO"}
```

Para el nombre cacheado de un miembro ya creado: `GET /api/v1/members/{id}/asn-name`.
