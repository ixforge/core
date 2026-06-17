# Métricas y gráficos

Los datos de los gráficos (tráfico por puerto, latencia/pérdida a los miembros)
**no están en el Core**: el collector los empuja a **VictoriaMetrics**, que se
consulta con la API compatible con Prometheus. El `/metrics` del Core expone métricas
internas de la app (requests, etc.), no datos de gráficos.

```bash
VM=http://localhost:8428   # VictoriaMetrics
```

> VictoriaMetrics no lleva auth por defecto (suele exponerse solo en localhost).
> Si configuraste BasicAuth, agrega `-u usuario:clave` a los `curl`.

## Cómo consultar

- **Valor actual** (instant query): `GET /api/v1/query?query=<PromQL>`
- **Serie en el tiempo** (para graficar): `GET /api/v1/query_range?query=<PromQL>&start=&end=&step=`

```bash
# Valor actual
curl -s "$VM/api/v1/query" --data-urlencode 'query=ixforge_interface_traffic_in_bps'

# Última hora, punto cada 60s (rango por tiempo relativo)
curl -s "$VM/api/v1/query_range" \
  --data-urlencode 'query=ixforge_interface_traffic_in_bps{member_id="'$MEMBER_ID'"}' \
  --data-urlencode 'start=-1h' --data-urlencode 'end=now' --data-urlencode 'step=60s'
```

## Catálogo de métricas

### Tráfico e interfaces (SNMP)

Labels: `switch_id`, `switch_name`, `ifname`, `port_id`, `member_id`, `asn`.

| Métrica | Qué es |
|---------|--------|
| `ixforge_interface_traffic_in_bps` | Tráfico entrante (bits/s) |
| `ixforge_interface_traffic_out_bps` | Tráfico saliente (bits/s) |
| `ixforge_interface_packets_in_pps` | Paquetes entrantes (pps) |
| `ixforge_interface_packets_out_pps` | Paquetes salientes (pps) |
| `ixforge_interface_errors_in` | Errores de entrada |
| `ixforge_interface_errors_out` | Errores de salida |
| `ixforge_interface_discards_out` | Descartes de salida |
| `ixforge_interface_oper_status` | Estado operativo del puerto |

### Latencia y pérdida (ICMP)

Labels: `ip`, `ip_version`, `asn`, `member_id`, `member_name`.

| Métrica | Qué es |
|---------|--------|
| `ixforge_icmp_rtt_seconds` | RTT promedio |
| `ixforge_icmp_rtt_min_seconds` | RTT mínimo |
| `ixforge_icmp_rtt_max_seconds` | RTT máximo |
| `ixforge_icmp_packet_loss_ratio` | Pérdida (0 a 1) |
| `ixforge_icmp_packets_sent` | Paquetes enviados |
| `ixforge_icmp_packets_received` | Paquetes recibidos |

Las métricas de RTT solo se emiten cuando hubo al menos una respuesta. Hoy el
label `asn` de ICMP siempre vale `0` (el ASN no viene en el target del Core);
filtra por `member_id` o `ip`, no por `asn`.

## Ejemplos útiles

```bash
# Tráfico in/out de un miembro (bps)
curl -s "$VM/api/v1/query" --data-urlencode \
  'query=ixforge_interface_traffic_in_bps{member_id="'$MEMBER_ID'"}'

# Tráfico total del IX entrante (suma de todos los puertos)
curl -s "$VM/api/v1/query" --data-urlencode \
  'query=sum(ixforge_interface_traffic_in_bps)'

# RTT a un miembro, serie de las últimas 6h para graficar
curl -s "$VM/api/v1/query_range" \
  --data-urlencode 'query=ixforge_icmp_rtt_seconds{member_id="'$MEMBER_ID'"}' \
  --data-urlencode 'start=-6h' --data-urlencode 'end=now' --data-urlencode 'step=300s'

# Miembros con pérdida de paquetes ahora mismo
curl -s "$VM/api/v1/query" --data-urlencode \
  'query=ixforge_icmp_packet_loss_ratio > 0'
```

La respuesta es el formato estándar de Prometheus (`{"data":{"result":[...]}}`),
directo para alimentar Grafana u otro dashboard apuntando a VictoriaMetrics como
datasource.
