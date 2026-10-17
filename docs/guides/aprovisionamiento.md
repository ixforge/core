# Aprovisionamiento de un miembro

Alta completa de un miembro hasta dejarlo con sesiones BGP, paso a paso por API.
La jerarquía es: **Miembro -> Trunk -> (Conexión + VLAN con IP) -> Sesiones BGP**.

```bash
CORE=http://localhost:8000
# TOKEN=... (JWT de admin, ver autenticacion.md)
```

## Prerrequisitos (infraestructura)

Esto se crea una vez por IXP, no por miembro. Si ya existe, solo hay que recuperar los IDs:

```bash
SWITCH_ID=$(curl -s $CORE/api/v1/switches -H "Authorization: Bearer $TOKEN" | jq -r '.items[0].id')
VLAN_ID=$(curl -s $CORE/api/v1/vlans   -H "Authorization: Bearer $TOKEN" | jq -r '.items[0].id')
RS_ID=$(curl -s $CORE/api/v1/route-servers -H "Authorization: Bearer $TOKEN" | jq -r '.items[0].id')
POOL_ID=$(curl -s "$CORE/api/v1/ip-pools?vlan_id=$VLAN_ID" -H "Authorization: Bearer $TOKEN" \
  | jq -r '.items[] | select(.af == 4) | .id')
```

Para crearla desde cero (resumen):

```bash
# Ubicación y switch (el switch exige location_id; management_ip y snmp_community
# son los datos que usa el collector)
LOCATION_ID=$(curl -s -X POST $CORE/api/v1/locations -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"name": "DC1", "city": "Santiago", "country": "CL"}' | jq -r .id)
curl -s -X POST $CORE/api/v1/switches -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"name": "sw1", "location_id": "'$LOCATION_ID'"}'

# VLAN de producción (vid 1-4094, type: production|quarantine|management|private|other)
curl -s -X POST $CORE/api/v1/vlans -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"name": "Peering", "vid": 35, "type": "production"}'

# Pool de IPs sobre la VLAN (af 4 o 6, network debe coincidir con af)
curl -s -X POST $CORE/api/v1/ip-pools -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"vlan_id": "'$VLAN_ID'", "network": "192.0.2.0/24", "af": 4}'
```

(El route server tiene sus propios campos, IPs y VLANs; ver [../api.md](../api.md).)
Reservar sus IPs en el pool con `POST /api/v1/route-servers/{rs_id}/ips`
(`{"pool_id": ..., "address": ...}`): la asignación secuencial del paso 5 salta las
IPs reservadas así, pero no conoce los campos `ip_v4`/`ip_v6` del route server: sin
la reserva, puede asignar esa misma IP a un miembro.

## 1. Crear el miembro

Ver [miembros.md](miembros.md). Guardar el `MEMBER_ID`.

## 2. Crear el trunk

`POST /api/v1/trunks`. Obligatorio: `member_id`, `name`. `mac_address` es opcional
(formato `XX:XX:XX:XX:XX:XX`).

```bash
TRUNK_ID=$(curl -s -X POST $CORE/api/v1/trunks \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"member_id": "'$MEMBER_ID'", "name": "ae0"}' | jq -r .id)
```

El trunk nace en estado `draft`. No se puede crear un trunk para un miembro `terminated`.

## 3. Agregar una conexión al trunk

`POST /api/v1/trunks/{trunk_id}/connections`. Obligatorio: `switch_id`, `name`,
`type` (`physical`|`virtual`), `speed` (en **Mbps**). Todas las conexiones de un
trunk tienen que ser del mismo `type`.

```bash
CONN_ID=$(curl -s -X POST $CORE/api/v1/trunks/$TRUNK_ID/connections \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"switch_id": "'$SWITCH_ID'", "name": "Ethernet1/1", "type": "physical", "speed": 100000}' | jq -r .id)
```

(`speed: 100000` = 100G.) La conexión nace en estado `draft`.

## 4. Asignar la VLAN al trunk

`POST /api/v1/trunks/{trunk_id}/vlans`. Devuelve el **trunk-VLAN**, cuyo `id` es
el que usan la asignación de IP y las sesiones BGP. Una VLAN `private` solo se
puede asignar si el miembro está autorizado en ella.

```bash
TRUNK_VLAN_ID=$(curl -s -X POST $CORE/api/v1/trunks/$TRUNK_ID/vlans \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"vlan_id": "'$VLAN_ID'"}' | jq -r .id)
```

## 5. Asignar una IP

`POST /api/v1/ip-pools/{pool_id}/assign` con el `trunk_vlan_id`. Si se envía
`address`, la asignación es manual; si se omite, toma la siguiente IP libre del pool.
Usar una de las dos variantes: ejecutar ambas deja dos IPs en el trunk-VLAN.
`GET /api/v1/ip-pools/available?vlan_id=...` muestra la próxima IP libre de cada pool.

```bash
# Manual
curl -s -X POST $CORE/api/v1/ip-pools/$POOL_ID/assign \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"trunk_vlan_id": "'$TRUNK_VLAN_ID'", "address": "192.0.2.11"}'

# Secuencial (siguiente libre)
curl -s -X POST $CORE/api/v1/ip-pools/$POOL_ID/assign \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"trunk_vlan_id": "'$TRUNK_VLAN_ID'"}'
```

Repetir con el pool IPv6 si el miembro tiene v6.

## 6. Activar la conexión

Las conexiones tienen su propia máquina de estados (`draft -> provisioning ->
active`). Son dos transiciones:

```bash
for s in provisioning active; do
  curl -s -X POST $CORE/api/v1/connections/$CONN_ID/transition \
    -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
    -d '{"state": "'$s'"}'
done
```

Activar la conexión no es requisito para activar el trunk (basta con que exista),
pero refleja el estado real del puerto: el collector solo monitorea por SNMP las
conexiones `active`. Además, entrar a `active` o salir de él encola la regeneración
de la configuración de los route servers con sesiones en ese trunk.

## 7. Activar el trunk

`draft -> provisioning -> active`. Para llegar a `active`, el trunk exige:

- al menos **una conexión**
- al menos **una VLAN** asignada
- al menos **una IP** en cada VLAN de tipo `production`

Si falta algo, la API responde 422 con el motivo.

```bash
for s in provisioning active; do
  curl -s -X POST $CORE/api/v1/trunks/$TRUNK_ID/transition \
    -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
    -d '{"state": "'$s'"}'
done
```

## 8. Crear las sesiones BGP

`POST /api/v1/bgp-sessions`. Obligatorio: `route_server_id`, `trunk_vlan_id`,
`af` (4 o 6). `max_prefixes` es opcional. El `peer_ip` y el `peer_asn` se calculan
solos (de la IP asignada y el ASN del miembro), no se envían. El trunk tiene que
estar `active` y el trunk-VLAN tiene que tener una IP de esa familia; si no, la API
responde 422.

```bash
# Una sesión por familia, contra cada route server
for af in 4 6; do
  curl -s -X POST $CORE/api/v1/bgp-sessions \
    -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
    -d '{"route_server_id": "'$RS_ID'", "trunk_vlan_id": "'$TRUNK_VLAN_ID'", "af": '$af'}'
done
```

Las sesiones nacen con `admin_state: up` y `oper_state: unknown`. Para
deshabilitar o habilitar una sesión sin borrarla (`SESSION_ID` es el `id` que
devuelve la creación):

```bash
curl -s -X PATCH $CORE/api/v1/bgp-sessions/$SESSION_ID \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"admin_state": "down"}'
```

Una sesión con `admin_state: down` sale de la configuración generada.

## 9. Cargar el filtro de prefijos (opcional, pero recomendado)

Un miembro sin filtro se comporta como "solo su propio ASN como origen, sin filtro de
prefijos". Sirve para empezar, pero si el miembro anuncia prefijos legítimos de
terceros (clientes, un AS-SET) hay que declararlos, y lo mismo si se quiere filtrar
por prefijo además de por origen:

```bash
curl -s -X PUT $CORE/api/v1/members/$MEMBER_ID/prefix-filters/4 \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{
        "origin_asns": [64500, 64501],
        "prefixes": ["203.0.113.0/24"],
        "as_set": "AS-EJEMPLO"
      }'
```

El filtro es por familia: el v6 se carga aparte en `/prefix-filters/6`, y cada
prefijo tiene que ser de la familia del filtro. `origin_asns` reemplaza al ASN del
miembro, así que hay que incluirlo; si se omite o va vacío, se usa solo el ASN del
miembro. Para `prefixes`, `null` desactiva el filtrado por prefijo y deja solo el de
origen, mientras que la lista vacía significa "no autorizar ningún prefijo" (útil,
por ejemplo, para un colector de rutas que recibe y no anuncia).
`DELETE /api/v1/members/{id}/prefix-filters/{af}` borra el filtro de esa familia.

Hoy estas listas se cargan a mano. El campo `as_set` es informativo hasta que
exista el resolver de IRR. Cada cambio del filtro encola la regeneración de los
route servers donde el miembro tiene sesiones.

## 10. Activar el miembro

Por último, el miembro pasa `prospect -> provisioning -> active` (requiere el trunk
activo del paso 7):

```bash
for s in provisioning active; do
  curl -s -X POST $CORE/api/v1/members/$MEMBER_ID/transition \
    -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
    -d '{"state": "'$s'"}'
done
```

## Qué pasa después

La configuración de un route server solo incluye las sesiones con `admin_state: up`
cuyo trunk está `active` y cuyo miembro está `active`. Por eso activar al miembro
dispara la regeneración de la configuración BIRD de los route servers afectados, igual
que activar o desactivar conexiones, crear, modificar o borrar sesiones BGP y cambiar
el filtro de prefijos. La transición del trunk no encola nada por sí misma. La
regeneración la ejecuta el worker (ver [../quickstart.md](../quickstart.md)); sin
worker, los trabajos quedan en la cola.

Los agents recogen la configuración nueva, la validan, la aplican y reportan de
vuelta al Core el estado operativo de las sesiones. Hasta que el miembro conecte su
router, las sesiones quedarán en `oper_state: down`: es lo esperado.
