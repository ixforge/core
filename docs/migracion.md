# Actualizar un IXP ya desplegado

Cada sección cubre un salto de versión. Ejecutarla **una vez por IXP**, con una
persona mirando cada paso. Una versión de IXForge son los tres componentes juntos:
`core`, `agent` y `collector` en los commits que indica cada sección.

## Qué versión corre hoy

Hasta v0.2, los tres componentes reportan la versión `0.1.0`. La versión real
sale de la revisión de Alembic del core:

```bash
cd <directorio del core>/docker
docker compose exec core uv run alembic current
```

| Revisión | Versión | Qué seguir |
|---|---|---|
| `b7d3f2a9c615 (head)` | v0.3 | Nada, ya está al día |
| `f3c81a4d267e` | v0.2 | [De v0.2 a v0.3](#de-v02-a-v03) |
| Cualquier otra | Anterior a v0.2 | [Desde los templates anteriores a v0.2](#desde-los-templates-anteriores-a-v02) y después [De v0.2 a v0.3](#de-v02-a-v03), en un solo despliegue: el core aplica todas las migraciones pendientes de una vez |

Desde v0.3, la versión real aparece en `GET /api/v1/health` del core, en
`GET /health` del agent y en el `agent_version` de cada route server.

## De v0.2 a v0.3

v0.3 son estos commits de `main`:

| Repositorio | Commit |
|---|---|
| `core` | `530b2044e6d48cdc509f428ba3405419a7e93c6c` |
| `agent` | `f3caf8c2f6fe3f6c4102f79304fe12c522ba7160` |
| `collector` | `770c0820ffbbb53ed266ee49fcf8557d13bb11c9` |

### Qué cambia

**Core**

- **Migración `8c2e5d1a9f47`: los ASN pasan a `BIGINT`.** Hasta v0.2, un ASN
  mayor que 2147483647 no se podía guardar y la API respondía 500. Ahora se
  acepta todo el rango de 32 bits sin signo, hasta 4294967295. El cambio de tipo
  reescribe cada tabla con ASN y la bloquea mientras dura. La más grande suele ser
  `bgp_session_prefixes`, sobre todo si un route server recibe la tabla completa
  de un upstream
- **Migración `b7d3f2a9c615`: RPKI con ASN de 4 bytes.** Con RPKI encendido y un
  ASN de IXP mayor que 65535, el config no compilaba, porque una community
  estándar lleva solo 16 bits. Ahora esos IXPs marcan solo las rutas inválidas.
  **Con un ASN de 2 bytes el config generado no cambia.** Solo se actualizan los
  templates que siguen iguales a los de v0.2; los editados quedan como están y se
  avisa (ver [Actualizar el core](#3-actualizar-el-core))
- **El rate limit usa la IP de la conexión**, no la que declara el cliente en
  `X-Forwarded-For`, que cualquiera podía falsificar para saltarse el límite.
  **Requiere acción si hay un proxy inverso delante del core** (ver
  [Proxy inverso y rate limit](#2-proxy-inverso-y-rate-limit))
- **`ixforge upgrade` ya no intenta reaplicar el schema de procrastinate** si ya
  existe. En v0.2, cada arranque sobre una base instalada imprimía
  `Warning: could not apply procrastinate schema: Database error`, que no
  significaba nada pero tapaba los errores reales
- **Las limpiezas periódicas corren por primera vez.** En v0.2 fallaban siempre,
  porque no aceptaban el `timestamp` que procrastinate les pasa a las tareas
  periódicas. Desde v0.3 se ejecutan, en hora UTC: todos los días a las 03:00
  borran los eventos de auditoría de más de 90 días, a las 03:30 los eventos de
  prefijos de más de 30 días, y los domingos a las 04:00 las versiones de config
  que nunca se aplicaron, conservando las últimas 100 de cada route server. La
  primera corrida se lleva todo lo acumulado desde la instalación. Si hace falta
  conservar algo de eso, exportarlo antes de actualizar
- Correcciones que cambian respuestas de la API (ver
  [Cambios en la API](#cambios-en-la-api)). Activar o desactivar un trunk ahora
  regenera el config de sus route servers, como ya pasaba con las conexiones

- **Dependencias al día.** Con los commits de v0.3, al 24 de octubre de 2026, ni
  `pip-audit` ni `cargo audit` reportan vulnerabilidades conocidas en los tres
  componentes. En el core los
  saltos grandes son starlette 1.9, FastAPI 0.162, SQLAlchemy 2.1 y uvicorn 0.54, y
  PyJWT reemplaza a python-jose, que tiene un advisory sin corrección. El formato
  del token no cambia, así que las sesiones abiertas siguen valiendo. La imagen fija
  uv en 0.13.5 en vez de `latest`

**Agent**

- Si BIRD aplica el config pero falla la confirmación al core, el agent la
  reintenta en cada ciclo sin volver a aplicar. En v0.2 la confirmación se perdía
  y la versión quedaba como pendiente para siempre
- La métrica de errores de poll se expone como `ixforge_agent_poll_errors_total`.
  En v0.2 salía como `ixforge_agent_poll_errors_total_total`: hay que actualizar
  cualquier dashboard o alerta que la use
- `config.toml` y la unit de systemd no cambian
- Dependencias al día. El cliente HTTP sigue en reqwest 0.12: no cambia cómo se
  valida el certificado del core

**Collector**

- El health refleja los fallos y las recuperaciones reales de cada componente.
  Puede mostrar `degraded` en casos que en v0.2 figuraban como `ok`. Sigue
  respondiendo 503 solo con `error`
- Se retira `polling.icmp.max_concurrency`, que no tenía efecto. Un config que
  lo tenga sigue cargando
- Dependencias al día. VictoriaMetrics sigue en v1.106.1: actualizarlo cambia el
  formato del índice y va en una versión aparte

**Compatibilidad entre componentes.** El contrato entre agent y core no cambia:
un agent v0.2 funciona con un core v0.3 y al revés. Por eso se actualiza primero
el core y después cada route server por separado, sin una ventana conjunta.

**Corte.** Mientras el core migra, la API y el portal no responden. BIRD sigue
enrutando con el config que tiene, y los agents reintentan hasta que el core
vuelve. **El peering no se corta en ningún paso.** En un ensayo con 200 mil filas
en `bgp_session_prefixes` (151 MB), la migración y el arranque tomaron unos 20
segundos.

### 1. Antes de empezar

**Confirmar la versión.** `docker compose exec core uv run alembic current` tiene
que mostrar `f3c81a4d267e (head)`. Si muestra otra cosa, volver a
[Qué versión corre hoy](#qué-versión-corre-hoy).

**Respaldar la base y sacarla del servidor.** Es la única vuelta atrás
garantizada (ver [Volver a v0.2](#volver-a-v02)):

```bash
cd <directorio del core>/docker
docker compose exec -T postgres pg_dump -U ixforge -Fc ixforge \
  > ixforge-v0.2-$(date +%F).dump
```

`-U` y el nombre de la base son los de `POSTGRES_USER` y `POSTGRES_DB` en
`docker/.env` (`ixforge` por defecto). Con `deploy.sh`, el paso de backup de
`/opt/ixforge/backup.sh` también sirve, siempre que el archivo se pueda restaurar
con `pg_restore`.

**Medir las tablas que se reescriben:**

```bash
docker compose exec -T postgres psql -U ixforge -d ixforge -c "
  SELECT relname, n_live_tup, pg_size_pretty(pg_total_relation_size(relid))
  FROM pg_stat_user_tables
  WHERE relname IN ('bgp_session_prefixes', 'bgp_prefix_events')
  ORDER BY pg_total_relation_size(relid) DESC"
```

Postgres escribe la copia nueva de cada tabla antes de borrar la vieja, así que
hace falta espacio libre en disco al menos igual a la tabla más grande
(`df -h` sobre el disco donde vive el volumen de Docker). Con millones de filas,
la migración puede superar el minuto que `deploy.sh` espera al health check: en
ese caso el script falla en la verificación, pero la migración sigue. Esperar a
que termine (`docker compose logs -f core worker`) antes de concluir nada.

**Revisar dos problemas de IPAM conocidos.** Existen en v0.2 y en v0.3, y su
corrección viene en una versión siguiente. No bloquean la actualización, pero
conviene saber si el IXP los tiene:

```bash
docker compose exec -T postgres psql -U ixforge -d ixforge <<'EOF'
-- IPs de route servers sin reserva en el pool, o que también tiene un miembro
SELECT rs.name AS route_server, ip.address,
       r.id IS NOT NULL AS reservada,
       m.name AS miembro_con_la_misma_ip
FROM route_servers rs
CROSS JOIN LATERAL (VALUES (rs.ip_v4), (rs.ip_v6)) AS ip(address)
LEFT JOIN rs_ip_assignments r ON r.route_server_id = rs.id AND r.address = ip.address
LEFT JOIN ip_assignments a ON a.address = ip.address
LEFT JOIN trunk_vlans tv ON tv.id = a.trunk_vlan_id
LEFT JOIN trunks t ON t.id = tv.trunk_id
LEFT JOIN members m ON m.id = t.member_id
WHERE ip.address IS NOT NULL AND (r.id IS NULL OR a.id IS NOT NULL);

-- Trunks con más de una IP de la misma familia en la misma VLAN
SELECT m.name AS miembro, t.name AS trunk, p.af,
       array_agg(a.address ORDER BY a.address) AS ips
FROM ip_assignments a
JOIN ip_pools p ON p.id = a.pool_id
JOIN trunk_vlans tv ON tv.id = a.trunk_vlan_id
JOIN trunks t ON t.id = tv.trunk_id
JOIN members m ON m.id = t.member_id
GROUP BY m.name, t.name, a.trunk_vlan_id, p.af
HAVING count(*) > 1;
EOF
```

- **Una IP de route server sin reservar** (`reservada` en `f`): el IPAM se la
  puede dar a un miembro, porque solo `POST /route-servers/{id}/ips` la reserva.
  Reservarla con ese endpoint, con el pool de la LAN de peering y la misma IP
  (`{"pool_id": ..., "address": "<la misma IP>"}`). La IP del route server no
  cambia, así que no hace falta regenerar. Si responde `422` porque la IP no está
  en ese pool, y ningún otro pool de la familia la contiene, no hay riesgo: el
  IPAM solo asigna IPs de los pools
- **Un miembro con la IP del route server** (`miembro_con_la_misma_ip` con un
  nombre): esa sesión no puede levantar nunca, y si el miembro configura esa IP
  hay un conflicto ARP con el route server. Coordinar con el miembro: borrar sus
  sesiones BGP de esa familia, liberar la IP, asignarle otra y volver a crear las
  sesiones. Recién después reservar la IP del route server, como en el punto
  anterior
- **Dos IPs de la misma familia en un trunk:** el config usa la menor, pero la
  lista de sesiones de la API y del portal puede mostrar la otra, y agregar una IP
  no regenera el config. Confirmar con el miembro cuál usa (`neighbor` en
  `/etc/bird/bird.conf` del route server), borrar la sesión de esa familia,
  liberar la otra IP y volver a crear la sesión

**Respaldar el binario del agent en cada route server:**

```bash
sudo cp /usr/local/bin/ixforge-agent /usr/local/bin/ixforge-agent.v0.2
```

**Tomar una foto de cada route server**, para comparar al final:

```bash
birdc show protocols > protocolos-antes.txt
birdc show route count
```

Anotar las sesiones que **ya estaban caídas**, para que nadie se las atribuya a la
actualización.

### 2. Proxy inverso y rate limit

El rate limit es por IP de la conexión y **por path**: cada ruta tiene su propio
contador de `IXFORGE_RATE_LIMIT_PER_MINUTE` (60 por defecto), y `POST /auth/login`
tiene 10 por minuto.

**Si hay un proxy inverso delante del core** (nginx, Caddy, HAProxy, Traefik) que
agrega `X-Forwarded-For`, en v0.2 cada cliente tenía su propio contador. En v0.3,
uvicorn solo toma la IP de ese header si la conexión viene de una dirección que
figura en `FORWARDED_ALLOW_IPS` (por defecto `127.0.0.1`). Un proxy en el mismo
host llega al contenedor desde el gateway de la red de Docker, no desde
`127.0.0.1`. Sin configurarlo, todos los clientes comparten el contador del proxy:
el login queda en 10 intentos por minuto para todo el mundo, y cualquier ruta
común, como `/ixf/member-export`, se reparte entre todos. Los agents no se ven
afectados, porque cada uno usa rutas propias con el id de su route server.

Para corregirlo, agregar en `docker/.env` la IP con la que el proxy llega al core.
Con `deploy.sh`, agregarla en `/opt/ixforge/.env.core`, porque el script
sobrescribe `docker/.env` con ese archivo en cada despliegue:

```bash
# un proxy en el mismo host llega desde el gateway de la red del compose
docker network ls | grep ixforge
docker network inspect <red> -f '{{range .IPAM.Config}}{{.Gateway}} {{end}}'

# en el archivo de entorno
FORWARDED_ALLOW_IPS=<gateway o IP del proxy>
```

No usar `*` salvo que el puerto 8000 sea alcanzable **solo** desde el proxy:
cualquier otro cliente podría volver a elegir su IP. **Si los agents, el
collector y los usuarios llegan directo al puerto 8000, sin proxy, no hay nada
que hacer.**

**Aparte del proxy, revisar si ya hay rechazos.** El agent reporta los prefijos
con una request por sesión BGP, todas seguidas, cada 10 ciclos. Un route server
con más sesiones que el límite por minuto recibe 429 en las últimas, siempre las
mismas. Esto también ocurre en v0.2:

```bash
journalctl -u ixforge-agent --since "-1 day" | grep -c "429"
```

Si da más que cero, subir `IXFORGE_RATE_LIMIT_PER_MINUTE` en el mismo archivo de
entorno a por lo menos la cantidad de sesiones del route server más grande más
20.

### 3. Actualizar el core

**Con git en el servidor:**

```bash
cd <directorio del core>
git fetch origin
git checkout 530b2044e6d48cdc509f428ba3405419a7e93c6c
cd docker
docker compose build
docker compose up -d
docker compose logs -f core worker
```

**Con `deploy.sh`** desde un checkout de ese commit (`git checkout` del commit
de `core` y `./deploy.sh prod`): hace el backup, sube el commit, reconstruye, migra y
verifica el hash. Requiere la estructura de servidor que describe
[staging.md](staging.md).

En el log de `core` o de `worker` tiene que aparecer lo siguiente. Migra el primero
que toma el lock, y el otro no encuentra nada que aplicar. Las líneas pueden salir
en otro orden, porque Alembic escribe en stderr y el resto en stdout:

```
entrypoint: aplicando migraciones (IXFORGE_AUTO_MIGRATE=true)
INFO  [alembic.runtime.migration] Running upgrade f3c81a4d267e -> 8c2e5d1a9f47, ASN columns hold the full unsigned 32-bit range
INFO  [alembic.runtime.migration] Running upgrade 8c2e5d1a9f47 -> b7d3f2a9c615, RPKI tags only where the IXP ASN fits a standard community
Procrastinate schema already present.
```

**Si además aparece una línea `aviso:`**, por ejemplo
`aviso: 1 de 1 plantillas protocols/bgp_peer.j2 estaban editadas y quedaron como estaban`,
alguien había editado ese template y la migración no lo tocó. Con un ASN de IXP
de 2 bytes no tiene ningún efecto. Con un ASN de 4 bytes y RPKI encendido, hay
que portar a mano el cambio en `protocols/bgp_peer.j2` y `protocols/rs_peer.j2`:
la condición `{% if route_server.rpki_enabled %}` del bloque que etiqueta con
`rpki_communities` pasa a ser
`{% if route_server.rpki_enabled and route_server.asn <= 65535 %}`, y se agrega
una rama
`{% elif route_server.rpki_enabled %}` que solo agrega
`IXP_LC_FILTERED_RPKI_INVALID` cuando `roa_check(...) = ROA_INVALID`. El texto
exacto está en `services/default_templates.py`.

**Verificar:**

```bash
curl -s http://localhost:8000/api/v1/health
# {"status":"healthy","version":"0.3.0",...}

docker compose exec core uv run alembic current
# b7d3f2a9c615 (head)
```

Después, entrar al portal y abrir un route server. Para confirmar que la
generación funciona igual, generar una versión y revisar el diff contra la
anterior ("Ver Diff" en el portal, o `GET /route-servers/{id}/config/diff`). Con
un ASN de 2 bytes, solo cambian las dos líneas de la cabecera (`Generated by` y
`Config hash`). El agent la aplica en su próximo poll, y como el contenido es el
mismo, BIRD no reinicia ninguna sesión.

### 4. Actualizar los agents, de a un route server

Compilar el binario de v0.3 en una máquina con Docker:

```bash
cd <checkout del repo agent>
git fetch origin
git checkout f3caf8c2f6fe3f6c4102f79304fe12c522ba7160
docker run --rm -v "$PWD":/src -w /src rust:1-bookworm cargo build --release --locked
sha256sum target/release/ixforge-agent
```

Copiarlo al **primer** route server y reemplazarlo:

```bash
scp target/release/ixforge-agent <rs1>:/tmp/ixforge-agent-v0.3

# en el route server
sudo systemctl stop ixforge-agent
sudo install -m 755 /tmp/ixforge-agent-v0.3 /usr/local/bin/ixforge-agent
sudo systemctl start ixforge-agent
```

Detener el agent no toca BIRD, que sigue con el config cargado. Al arrancar, el
agent vuelve a pedir el config y lo aplica aunque sea el mismo; con el contenido
igual, BIRD no reinicia sesiones.

Verificar en ese route server antes de seguir con el otro:

```bash
curl -s http://127.0.0.1:9100/health
# "version":"0.3.0" y "core_connected":true

journalctl -u ixforge-agent -n 30 --no-pager
birdc show protocols | diff protocolos-antes.txt -
```

En el portal, el route server muestra `agent_version` `0.3.0` después del
siguiente heartbeat (30 s con el `poll_interval_secs` del ejemplo). Recién
entonces repetir con el segundo route server.

`deploy.sh` instala en los dos route servers del entorno en la misma corrida. Como
no toca BIRD, el riesgo es bajo, pero el procedimiento manual permite parar
después del primero si algo no cuadra.

### 5. Actualizar el collector

```bash
cd <directorio del collector>
git fetch origin
git checkout 770c0820ffbbb53ed266ee49fcf8557d13bb11c9
docker compose up -d --build
curl -s http://127.0.0.1:9200/health
```

Con `deploy.sh`: `git checkout` del commit de `collector` y `./deploy.sh prod`
desde un checkout del repo collector. Si `configs/ixforge-collector.yaml` tiene
`polling.icmp.max_concurrency`, se puede borrar; si queda, se ignora.

### 6. Verificación final

- [ ] `GET /api/v1/health` del core responde `healthy` con `version` `0.3.0`
- [ ] `alembic current` muestra `b7d3f2a9c615 (head)`
- [ ] Las líneas `aviso:` del log, si las hubo, están revisadas
- [ ] El portal abre y el login funciona
- [ ] Los dos route servers muestran `agent_version` `0.3.0` y un heartbeat reciente
- [ ] `birdc show protocols` coincide con la foto previa en los dos route servers
- [ ] El health del collector muestra `ok` o un `degraded` explicado
- [ ] Dashboards y alertas usan `ixforge_agent_poll_errors_total`
- [ ] Con proxy inverso: `FORWARDED_ALLOW_IPS` configurado

### Volver a v0.2

**No basta con volver al código de v0.2.** Contra una base ya migrada, el core
v0.2 entra en un loop de reinicios con
`Can't locate revision identified by 'b7d3f2a9c615'`. Además, el downgrade de
`8c2e5d1a9f47` falla si ya se guardó algún ASN mayor que 2147483647. La vuelta
atrás es restaurar el respaldo del paso 1:

```bash
cd <directorio del core>/docker
docker compose stop core worker portal
docker compose exec -T postgres pg_restore -U ixforge -d ixforge --clean --if-exists \
  < ixforge-v0.2-<fecha>.dump

cd ..
git checkout v0.2
cd docker
docker compose build
docker compose up -d
docker compose exec core uv run alembic current
# f3c81a4d267e (head)
```

Se pierde todo lo que se cargó en la base después del respaldo. Los agents y el
collector de v0.3 funcionan con un core v0.2, así que no hace falta bajarlos. Si
se quiere igual, en cada route server:

```bash
sudo systemctl stop ixforge-agent
sudo install -m 755 /usr/local/bin/ixforge-agent.v0.2 /usr/local/bin/ixforge-agent
sudo systemctl start ixforge-agent
```

### Cambios en la API

Para quien integra contra la API:

| Antes (v0.2) | Ahora (v0.3) |
|---|---|
| Un ASN mayor que 2147483647 en miembros, peers o AS paths reportados daba `500` | Se acepta hasta 4294967295 |
| Un usuario `member` sin miembro asignado que pedía `GET /connections` recibía las conexiones de todos | `403 FORBIDDEN` |
| `POST /trunks/{id}/connections` guardaba `extra_data` sin validar | Lo valida contra los custom fields de `connection` y responde `422 VALIDATION_ERROR` si no cumple |
| `DELETE /ip-assignments/{id}` liberaba una IP aunque tuviera una sesión BGP de su familia | `409 CONFLICT` hasta borrar la sesión |
| La segunda página de un listado ordenado por fecha o por número, como `/members` o `/custom-fields`, podía responder `500` | Pagina bien |
| Un cursor manipulado podía responder `500` | `422 VALIDATION_ERROR` con `Invalid pagination cursor` |
| El preview de templates no renderizaba `bird.conf.j2` como la generación | Lo renderiza igual que la generación |
| Activar o desactivar un trunk no regeneraba configs | Regenera el config de los route servers de sus sesiones |
| Un `429` respondía `{"error": "Rate limit exceeded: ..."}`, con `error` como string | Usa el formato de error de la API, con el código `RATE_LIMITED` |

## Desde los templates anteriores a v0.2

Procedimiento para IXPs que venían con los templates anteriores (el par
`bird_v4.conf.j2` / `bird_v6.conf.j2`). Ejecutarlo **una vez por IXP**, con una
persona mirando cada paso.

### Qué cambia, y por qué no es opcional

El generador solo soporta `bird.conf.j2`. Un IXP que quede con el set anterior
falla con `TemplateNotFound: bird.conf.j2` al generar config. **La migración de
templates tiene que ir en el mismo despliegue que el código**, no después.

La hace la cadena de migraciones de Alembic. `9f2c7a1b4d3e` borra todas las filas
de `route_server_templates` de cada IXP e instala el set de route server. Las
siguientes (`c7a41f2e8b05`, `d8b52a3f9c16`, `e4c9d17a5b38`, `f1d3a86b40c2`)
actualizan cada template solo si sigue igual a como lo dejó la anterior: si
alguien lo editó, lo dejan como está e imprimen
`aviso: N de M plantillas <archivo> estaban editadas y quedaron como estaban`.
Partiendo del set viejo, al final de la cadena quedan exactamente los once
templates de `services/default_templates.py`.

Para un IXP que venía con los templates viejos esto es un cambio de
**comportamiento**, no de formato:

- **Gana `rs client`.** El route server deja de meter su ASN en el AS path y de
  reescribir el next hop. Es una corrección, era un bug, pero cambia lo que ven
  los peers y hay que verificarlo con ellos
- **Las sesiones pasan a pasivas.** La migración `3786dfba4315` crea
  `passive_sessions` en `true` para todos los route servers, y con eso el
  template de clientes emite `passive yes;`: el route server deja de iniciar las
  sesiones y espera que las abra el miembro
- **Gana `interpret communities off`**, el pass-through de communities well-known
  de RFC 1997
- **Gana el patrón completo de route server**: tabla y pipe por peer, chequeo de
  first AS, protección de next hop, ASNs transit-free, filtrado por ASN de origen
  y por prefijos
- **Pierde `protocol kernel`.** Un route server no instala rutas en el kernel
- **Pierde los timers y el graceful restart del bloque viejo** (`hold time 90`,
  `keepalive time 30`, `graceful restart on`): quedan los valores por defecto de
  BIRD
- **Las communities siguen el esquema de PIT Chile.** Tipo de miembro en
  `65110..65170`, tipo de peer en `65180`/`65190`, RPKI en `65012`/`65023`. Si el
  IXP venía emitiendo valores bajos (`2xx`) para el tipo de miembro, hay una
  colisión explotable con el control de anuncio que se corrige aquí. Ver
  [templates.md](templates.md). **Si un looking glass interpreta esas communities
  por su valor, hay que actualizarlo**
- **El export borra las communities estándar del IXP salvo el bloque público**
  `65000..65199` (RPKI y tipos) y las marcas configuradas en los peers que no son
  miembros. El import de cada miembro borra ese mismo bloque, para que no se
  pueda falsificar
- **RPKI ya no tiene modos.** La migración `f1d3a86b40c2` elimina `rpki_policy`:
  con `rpki_enabled` encendido, una ruta inválida siempre se descarta
- **Desaparecen `protocols/static.j2` y `filters/communities.j2`.** Eran templates
  huérfanos: se instalaban en la base pero no los incluía nadie, así que la
  community de blackhole `(65535, 666)` no tenía ningún efecto. El borrado es
  intencional, no un descuido. El blackholing RFC 7999 queda fuera de alcance

### Procedimiento

Con Docker, el entrypoint de los contenedores aplica las migraciones al arrancar
(salvo con `IXFORGE_AUTO_MIGRATE=false`). Desplegar el commit nuevo **es**
migrar, así que los pasos 1 a 3 van antes del despliegue.

#### 1. Exportar los templates actuales

```bash
curl -sH "Authorization: Bearer $TOKEN" \
  https://<core>/api/v1/rs-templates \
  > templates-antes-$(date +%F).json
```

Guardarlo **fuera de la base**. Es lo único que permite volver atrás: el
`downgrade` de `9f2c7a1b4d3e` levanta `NotImplementedError` a propósito, porque
reconstruir los templates anteriores a ciegas sería peor que no bajar.

Red de seguridad adicional: `ConfigVersion.template_snapshot` guarda una copia de
los templates con los que se generó cada config, así que el estado anterior queda
recuperable aunque alguien se saltee este paso. La limpieza semanal de versiones
conserva siempre las aplicadas.

#### 2. Foto previa de cada route server

```bash
birdc show protocols
birdc show route count
for p in $(birdc show protocols | awk '/BGP/ {print $1}'); do
  echo "$p: $(birdc show route protocol $p count)"
done
```

Sin esta foto no hay con qué comparar después, y sin comparación no se sabe si el
corte salió bien. Anotar también cualquier sesión que **ya estuviera caída**, para
que nadie se la atribuya a la migración.

#### 3. Confirmar contra qué base se va a ejecutar

```bash
# en el servidor: deploy.sh copia este archivo a docker/.env
grep IXFORGE_DATABASE_URL /opt/ixforge/.env.core

# desde un checkout, si se migra con uv
uv run python -c "from ixforge.config import get_settings; print(get_settings().database_url)"
```

La variable es `IXFORGE_DATABASE_URL`, no `DATABASE_URL`: `Settings` usa
`env_prefix="IXFORGE_"` y cualquier otra cosa se ignora en silencio. Esta
migración **borra todas las filas de `route_server_templates`**; apuntada a la
base equivocada borra los templates de otro IXP.

Si el comando imprime cualquier cosa que no sea la base esperada, **parar**.

#### 4. Aplicar la migración

Con Docker, la aplica el despliegue del commit nuevo (`./deploy.sh <dev|prod>`,
ver [staging.md](staging.md)). Fuera de Docker:

```bash
uv run ixforge upgrade
```

`ixforge upgrade` aplica el schema de procrastinate y después
`alembic upgrade head`. Las líneas `aviso:` salen en esa salida; con Docker
quedan en el log del contenedor que aplicó la migración
(`docker compose logs core worker | grep aviso`).

#### 5. Cargar los datos nuevos

Nada de esto es obligatorio para generar, pero sin ello el config puede no
comportarse como se quiere: sale más permisivo en los filtros, o con sesiones
pasivas que los peers no inician:

- `passive_sessions` de cada route server: si los peers no inician la sesión,
  apagarlo con `PATCH /route-servers/{id}` antes de regenerar
- `member_type` de cada miembro (`PATCH /members/{id}`), para la community
  informativa
- Filtros de prefijos: `PUT /members/{id}/prefix-filters/{af}`. Un miembro sin
  filtro se comporta como "solo su propio ASN, sin filtro de prefijos"
- Peers que no son miembros: `POST /route-servers/{id}/peers` para upstream y
  colectores
- RPKI, si se va a usar: `POST /rpki-servers` y después `PATCH` del route server
  con `rpki_enabled`. Encenderlo primero en un route server, medir el impacto y
  solo después encenderlo en el otro

#### 6. Regenerar y revisar el diff antes de aplicar

La config generada pasa a ser la vigente en el acto: el agent la toma en su
próximo poll (`poll_interval_secs`, 30 s en `config.toml.example`), la valida con
`bird -p` y la aplica. Si `bird -p` la rechaza, no la aplica y reporta el error al
Core.

Para revisarla antes de que llegue a los route servers, detener el agent en
ambos (`systemctl stop ixforge-agent`; BIRD sigue con la config anterior) antes
del paso 4: después de migrar, cualquier regeneración en segundo plano ya produce
una config con los templates nuevos. Con los agents detenidos, generar y revisar:

```bash
# generar una versión nueva (la respuesta trae su id)
curl -sX POST -H "Authorization: Bearer $TOKEN" \
  https://<core>/api/v1/route-servers/<rs_id>/config/generate

# diff contra la versión anterior (también en el portal, "Ver Diff")
curl -sH "Authorization: Bearer $TOKEN" \
  "https://<core>/api/v1/route-servers/<rs_id>/config/diff?to=<version_id>"

# config completa, para validarla con bird -p -c en el route server
curl -sH "Authorization: Bearer $TOKEN" \
  https://<core>/api/v1/route-servers/<rs_id>/config/current | jq -r .content
```

#### 7. Aplicar y comparar

Arrancar el agent (`systemctl start ixforge-agent`) en un route server a la vez,
esperar a que las sesiones vuelvan a Established y comparar los conteos de
prefijos contra la foto del paso 2. `show route count` cuenta las tablas master, o sea lo
que el route server redistribuye; `show route protocol <p> count` cuenta la tabla
del peer, que incluye también las rutas marcadas como filtradas.

Una diferencia grande hacia abajo casi siempre significa un filtro nuevo
descartando más de lo esperado: revisar qué communities `1101` aparecen en las rutas
filtradas. `show route filtered` no sirve aquí, porque los filtros de import no
rechazan y lo que descarta el pipe no queda guardado; hay que mirar la tabla del
peer:

```bash
birdc "show route table t_<slug> where bgp_large_community ~ [(routeserverasn, 1101, *)] count"
birdc "show route table t_<slug> where bgp_large_community ~ [(routeserverasn, 1101, *)] all"
```

Los motivos de cada valor están en [templates.md](templates.md).
