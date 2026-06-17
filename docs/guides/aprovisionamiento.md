# Aprovisionamiento de un miembro

Alta completa de un miembro hasta dejarlo con sesiones BGP, paso a paso por API.
La jerarquía es: **Miembro → Trunk → (Conexión + VLAN con IP) → Sesiones BGP**.

```bash
CORE=http://localhost:8000
# TOKEN=... (JWT de admin, ver autenticacion.md)
```

## Prerequisitos (infraestructura)

Esto se crea una vez por IXP, no por miembro. Si ya existen, solo recupera sus IDs:

```bash
SWITCH_ID=$(curl -s $CORE/api/v1/switches -H "Authorization: Bearer $TOKEN" | jq -r '.items[0].id')
VLAN_ID=$(curl -s $CORE/api/v1/vlans   -H "Authorization: Bearer $TOKEN" | jq -r '.items[0].id')
RS_ID=$(curl -s $CORE/api/v1/route-servers -H "Authorization: Bearer $TOKEN" | jq -r '.items[0].id')
POOL_ID=$(curl -s "$CORE/api/v1/ip-pools?vlan_id=$VLAN_ID" -H "Authorization: Bearer $TOKEN" | jq -r '.items[0].id')
```

Para crearlos desde cero (resumen):

```bash
# VLAN de producción (vid 1-4094, type: production|quarantine|management|private|other)
curl -s -X POST $CORE/api/v1/vlans -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"name": "Peering", "vid": 35, "type": "production"}'

# Pool de IPs sobre la VLAN (af 4 o 6, network debe coincidir con af)
curl -s -X POST $CORE/api/v1/ip-pools -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"vlan_id": "'$VLAN_ID'", "network": "REDACTED_NET.0/24", "af": 4}'
```

(Switch y route server tienen sus propios campos; ver [../api.md](../api.md).)

## 1. Crear el miembro

Ver [miembros.md](miembros.md). Guarda el `MEMBER_ID`.

## 2. Crear el trunk

`POST /api/v1/trunks`. Obligatorio: `member_id`, `name`. `mac_address` opcional
(formato `XX:XX:XX:XX:XX:XX`).

```bash
TRUNK_ID=$(curl -s -X POST $CORE/api/v1/trunks \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"member_id": "'$MEMBER_ID'", "name": "ae0"}' | jq -r .id)
```

El trunk nace en estado `draft`.

## 3. Agregar una conexión al trunk

`POST /api/v1/trunks/{trunk_id}/connections`. Obligatorio: `switch_id`, `name`,
`type` (`physical`|`virtual`), `speed` (en **Mbps**).

```bash
CONN_ID=$(curl -s -X POST $CORE/api/v1/trunks/$TRUNK_ID/connections \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"switch_id": "'$SWITCH_ID'", "name": "Ethernet1/1", "type": "physical", "speed": 100000}' | jq -r .id)
```

(`speed: 100000` = 100G.)

## 4. Asignar la VLAN al trunk

`POST /api/v1/trunks/{trunk_id}/vlans`. Devuelve el **trunk-VLAN**, cuyo `id` es
el que usan la asignación de IP y las sesiones BGP.

```bash
TRUNK_VLAN_ID=$(curl -s -X POST $CORE/api/v1/trunks/$TRUNK_ID/vlans \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"vlan_id": "'$VLAN_ID'"}' | jq -r .id)
```

## 5. Asignar una IP

`POST /api/v1/ip-pools/{pool_id}/assign` con el `trunk_vlan_id`. Si pasas
`address` es asignación manual; si la omites, toma la siguiente IP libre del pool.

```bash
# Manual
curl -s -X POST $CORE/api/v1/ip-pools/$POOL_ID/assign \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"trunk_vlan_id": "'$TRUNK_VLAN_ID'", "address": "REDACTED_NET.11"}'

# Secuencial (siguiente libre)
curl -s -X POST $CORE/api/v1/ip-pools/$POOL_ID/assign \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"trunk_vlan_id": "'$TRUNK_VLAN_ID'"}'
```

Repite para el pool IPv6 si el miembro tiene v6.

## 6. Activar la conexión

Las conexiones tienen su propia máquina de estados (`draft → provisioning →
active`). Dos transiciones:

```bash
for s in provisioning active; do
  curl -s -X POST $CORE/api/v1/connections/$CONN_ID/transition \
    -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
    -d '{"state": "'$s'"}'
done
```

## 7. Activar el trunk

`draft → provisioning → active`. Para llegar a `active`, el trunk exige:

- al menos **una conexión**
- al menos **una VLAN** asignada
- **una IP** por cada VLAN de tipo `production`

Si falta algo, la API responde 422 con el detalle.

```bash
for s in provisioning active; do
  curl -s -X POST $CORE/api/v1/trunks/$TRUNK_ID/transition \
    -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
    -d '{"state": "'$s'"}'
done
```

## 8. Crear las sesiones BGP

`POST /api/v1/bgp-sessions`. Obligatorio: `route_server_id`, `trunk_vlan_id`,
`af` (4 o 6). `max_prefixes` opcional. El `peer_ip` y el `peer_asn` se calculan
solos (de la IP asignada y el ASN del miembro), no se mandan.

```bash
# Una sesión por familia, contra cada route server
for af in 4 6; do
  curl -s -X POST $CORE/api/v1/bgp-sessions \
    -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
    -d '{"route_server_id": "'$RS_ID'", "trunk_vlan_id": "'$TRUNK_VLAN_ID'", "af": '$af'}'
done
```

Las sesiones nacen con `admin_state: up` y `oper_state: unknown`. Para
deshabilitar/habilitar una sesión sin borrarla:

```bash
curl -s -X PATCH $CORE/api/v1/bgp-sessions/$SESSION_ID \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"admin_state": "down"}'
```

## 9. Activar el miembro

Finalmente, el miembro `provisioning → active` (requiere el trunk activo del paso 7):

```bash
for s in provisioning active; do
  curl -s -X POST $CORE/api/v1/members/$MEMBER_ID/transition \
    -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
    -d '{"state": "'$s'"}'
done
```

## Qué pasa después

Activar al miembro / trunk dispara la regeneración de la config BIRD de los route
servers afectados (vía el worker; ver [../quickstart.md](../quickstart.md)). Los
agents la recogen, validan y aplican, y reportan el estado operativo de las
sesiones de vuelta al Core. Hasta que el miembro conecte su router, las sesiones
quedarán `oper_state: down` — es lo esperado.
