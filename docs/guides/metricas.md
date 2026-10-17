# Métricas y gráficos

Los datos de los gráficos (tráfico por puerto, latencia y pérdida hacia los miembros,
prefijos anunciados) **no están en la base del Core**: viven en **VictoriaMetrics**.
El collector escribe ahí las métricas SNMP e ICMP, y VictoriaMetrics además scrapea el
`/metrics` del Core para guardar la historia del conteo de prefijos por sesión BGP.

VictoriaMetrics escucha solo en localhost (el Core la consulta en
`IXFORGE_VICTORIAMETRICS_URL`, por defecto `http://localhost:8428`), así que la vía para
cualquier consumidor externo es la API del Core, `/api/v1/metrics/*`. La consulta
directa con PromQL queda para quien opera desde el mismo host.

El collector solo monitorea las conexiones en estado `active` (SNMP) y las IPs de los
miembros `active` con trunk `active` (ICMP).

## Por la API del Core

```bash
CORE=http://localhost:8000
# TOKEN=... (ver autenticacion.md)
```

Los endpoints aceptan cualquier usuario autenticado por JWT, o una API key con el
scope `metrics:read`. Si VictoriaMetrics no responde, no devuelven error: responden
con los datos vacíos y `"disponible": false`.

El parámetro `range` acepta solo `1h` (un punto cada 60 s), `6h` (300 s), `24h`
(900 s) y `7d` (3600 s); cualquier otro valor responde 422.

| Endpoint | Parámetros | Devuelve |
|----------|------------|----------|
| `GET /api/v1/metrics/interfaces` | `connection_id`, `member_id` (opcionales) | `items`: valores actuales por conexión |
| `GET /api/v1/metrics/interfaces/series` | `connection_id`, `member_id`, `range` (default `1h`), `metric` | `series`: una por conexión |
| `GET /api/v1/metrics/icmp/series` | `member_id`, `range` (default `1h`), `metric` | `series`: una por IP de miembro |
| `GET /api/v1/metrics/aggregate/series` | `range` (default `1h`) | `entrada` y `salida`: tráfico total del IXP |
| `GET /api/v1/metrics/aggregate/peak` | `range` (default `24h`) | `entrada` y `salida`: pico de tráfico total en la ventana (bps, o `null`) |
| `GET /api/v1/metrics/prefixes/series` | `member_id` (obligatorio), `range` (default `24h`) | `series`: una por familia (`af`) |

Valores de `metric`:

- En `interfaces/series`: `ixforge_interface_traffic_in_bps` (default),
  `ixforge_interface_traffic_out_bps`, `ixforge_interface_packets_in_pps`,
  `ixforge_interface_packets_out_pps`.
- En `icmp/series`: `rtt` (default), `rtt_min`, `rtt_max`, `packet_loss`.

Cada ítem de `interfaces` trae `connection_id`, `member_id`, `ifname`, `switch_name`,
`oper_status` (`up` si el valor IF-MIB es 1, `down` para cualquier otro, `unknown` si
no hay dato) y los valores `traffic_in_bps`,
`traffic_out_bps`, `packets_in_pps`, `packets_out_pps`, `errors_in` y `errors_out`.
Las series traen sus etiquetas (`connection_id`, `member_id`, `ifname`; o `ip` e
`ip_version` en ICMP) y una lista `points` de `{"timestamp", "value"}`, con el
timestamp en segundos Unix.

```bash
# Estado actual de las conexiones de un miembro
curl -s "$CORE/api/v1/metrics/interfaces?member_id=$MEMBER_ID" -H "Authorization: Bearer $TOKEN"

# Tráfico saliente de un miembro, últimas 6 horas
curl -s "$CORE/api/v1/metrics/interfaces/series?member_id=$MEMBER_ID&range=6h&metric=ixforge_interface_traffic_out_bps" \
  -H "Authorization: Bearer $TOKEN"

# Pérdida de paquetes hacia un miembro, último día
curl -s "$CORE/api/v1/metrics/icmp/series?member_id=$MEMBER_ID&range=24h&metric=packet_loss" \
  -H "Authorization: Bearer $TOKEN"

# Tráfico total del IXP y pico de la última semana
curl -s "$CORE/api/v1/metrics/aggregate/series?range=24h" -H "Authorization: Bearer $TOKEN"
curl -s "$CORE/api/v1/metrics/aggregate/peak?range=7d" -H "Authorization: Bearer $TOKEN"

# Prefijos que anuncia un miembro, por familia
curl -s "$CORE/api/v1/metrics/prefixes/series?member_id=$MEMBER_ID" -H "Authorization: Bearer $TOKEN"
```

Respuesta de una serie:

```json
{
  "series": [
    {"connection_id": "…", "member_id": "…", "ifname": "Ethernet1/1",
     "points": [{"timestamp": 1760659200, "value": 1250000000.0}]}
  ],
  "disponible": true
}
```

Los agregados suman solo las interfaces asociadas a una conexión de miembro: el
switch reporta además el Eth-Trunk que agrupa los puertos físicos, y sumar todo
contaría dos veces a cada miembro. Los prefijos de un miembro son el máximo entre
route servers, no la suma, porque todos reciben los mismos prefijos del mismo peer.

## Directo en VictoriaMetrics

Desde el host donde se ejecuta VictoriaMetrics, se consulta con la API compatible con
Prometheus:

```bash
VM=http://localhost:8428   # VictoriaMetrics
```

> VictoriaMetrics no lleva autenticación por defecto; por eso escucha solo en localhost.
> Si se configuró BasicAuth, agregar `-u usuario:clave` a los `curl`.

- **Valor actual** (instant query): `GET /api/v1/query?query=<PromQL>`
- **Serie en el tiempo** (para graficar): `GET /api/v1/query_range?query=<PromQL>&start=&end=&step=`

```bash
# Valor actual
curl -s "$VM/api/v1/query" --data-urlencode 'query=ixforge_interface_traffic_in_bps'

# Última hora, un punto cada 60 s (rango por tiempo relativo)
curl -s "$VM/api/v1/query_range" \
  --data-urlencode 'query=ixforge_interface_traffic_in_bps{member_id="'$MEMBER_ID'"}' \
  --data-urlencode 'start=-1h' --data-urlencode 'end=now' --data-urlencode 'step=60s'
```

La respuesta es el formato estándar de Prometheus (`{"data":{"result":[...]}}`),
directo para alimentar Grafana u otro dashboard con VictoriaMetrics como datasource.

## Catálogo de métricas

### Tráfico e interfaces (SNMP, collector)

Labels: `switch_id`, `switch_name`, `ifname`, `port_id` (el `id` de la conexión),
`member_id`, `asn`. Las interfaces que no corresponden a una conexión de miembro (como
el Eth-Trunk) llevan `port_id` y `member_id` vacíos.

| Métrica | Qué es |
|---------|--------|
| `ixforge_interface_traffic_in_bps` | Tráfico entrante (bits/s) |
| `ixforge_interface_traffic_out_bps` | Tráfico saliente (bits/s) |
| `ixforge_interface_packets_in_pps` | Paquetes entrantes (pps) |
| `ixforge_interface_packets_out_pps` | Paquetes salientes (pps) |
| `ixforge_interface_errors_in` | Errores de entrada (por segundo) |
| `ixforge_interface_errors_out` | Errores de salida (por segundo) |
| `ixforge_interface_discards_out` | Descartes de salida (por segundo) |
| `ixforge_interface_oper_status` | Estado operativo del puerto |

Tráfico, paquetes, errores y descartes son tasas calculadas entre polls (por
segundo), no contadores absolutos; `oper_status` es el valor de `ifOperStatus` de
IF-MIB (1 up, 2 down, 3 testing, 4 unknown, 5 dormant, 6 notPresent, 7 lowerLayerDown). Los
descartes solo se consultan directo en VictoriaMetrics: la API del Core no los
expone. El label `asn` hoy siempre vale `0` (no viene en el target del puerto);
filtrar por `member_id` o `port_id`, no por `asn`.

### Latencia y pérdida (ICMP, collector)

Labels: `ip`, `ip_version`, `asn`, `member_id`, `member_name`.

| Métrica | Qué es |
|---------|--------|
| `ixforge_icmp_rtt_seconds` | RTT promedio |
| `ixforge_icmp_rtt_min_seconds` | RTT mínimo |
| `ixforge_icmp_rtt_max_seconds` | RTT máximo |
| `ixforge_icmp_packet_loss_ratio` | Pérdida (0 a 1) |
| `ixforge_icmp_packets_sent` | Paquetes enviados |
| `ixforge_icmp_packets_received` | Paquetes recibidos |

Las métricas de RTT solo se emiten cuando hubo al menos una respuesta. Igual que en
SNMP, el label `asn` de ICMP hoy siempre vale `0` (el ASN no viene en el target del
Core); filtrar por `member_id` o `ip`, no por `asn`.

### Sesiones BGP (scrape del `/metrics` del Core)

El `/metrics` del Core (fuera de `/api/v1`, sin autenticación) expone métricas
internas de la app (`ixforge_http_requests_total`,
`ixforge_http_request_duration_seconds`) y los valores que reportan los agents:

| Métrica | Labels | Qué es |
|---------|--------|--------|
| `ixforge_bgp_session_prefixes_imported` | `route_server_id`, `peer_asn`, `af` | Prefijos recibidos del peer en la sesión |
| `ixforge_bgp_session_prefixes_exported` | `route_server_id`, `peer_asn`, `af` | Prefijos anunciados al peer en la sesión |
| `ixforge_bgp_sessions_active` | `route_server_id` | Sesiones en estado `up` |

Una sesión sin conteo borra su serie en vez de publicar cero, así que el gráfico
muestra un hueco cuando la sesión está caída.

## Ejemplos de PromQL

```bash
# Tráfico in/out de un miembro (bps)
curl -s "$VM/api/v1/query" --data-urlencode \
  'query=ixforge_interface_traffic_in_bps{member_id="'$MEMBER_ID'"}'

# Tráfico total del IX entrante (solo interfaces de miembros, sin contar dos veces el Eth-Trunk)
curl -s "$VM/api/v1/query" --data-urlencode \
  'query=sum(ixforge_interface_traffic_in_bps{member_id!=""})'

# RTT a un miembro, serie de las últimas 6 h para graficar
curl -s "$VM/api/v1/query_range" \
  --data-urlencode 'query=ixforge_icmp_rtt_seconds{member_id="'$MEMBER_ID'"}' \
  --data-urlencode 'start=-6h' --data-urlencode 'end=now' --data-urlencode 'step=300s'

# Miembros con pérdida de paquetes ahora mismo
curl -s "$VM/api/v1/query" --data-urlencode \
  'query=ixforge_icmp_packet_loss_ratio > 0'
```
