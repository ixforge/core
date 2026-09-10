# Paridad euro-ix y RPKI en la generacion de configs BIRD

> **Estado: DISEÑO APROBADO, sin implementar.** Origen: migracion de PatagoniaIX
> desde configs generados por IXP Manager hacia IXForge. El deployment y el corte
> de PatagoniaIX son un spec aparte que depende de este.

## Contexto

Los templates BIRD que IXForge instala hoy por defecto generan un `protocol bgp`
plano por peer contra la tabla master, con filtros que rechazan bogons y prefijos
de largo invalido. Eso no alcanza para operar un IXP real y tiene un problema de
fondo: **no emiten `rs client`**, asi que BIRD agrega el ASN del route server al
AS path y reescribe el next hop, que es exactamente lo que un route server no debe
hacer.

PatagoniaIX corre hoy un config generado por IXP Manager (y despues editado a
mano) que implementa el patron euro-ix completo: tabla y pipe por peer, `rs client`,
large communities de filtrado, control de anuncio selectivo, chequeo de first AS,
proteccion de next hop, filtrado por ASN de origen y por lista de prefijos, e
hincapie de RPKI. Migrar PatagoniaIX a IXForge con los templates actuales seria
degradar el IXP.

Este spec lleva a IXForge a paridad con ese patron, como funcionalidad del
producto y no como customizacion de un IXP.

## Objetivo

Que un IXP creado con `run_setup` genere, sin tocar templates, un config BIRD 2.x
equivalente en comportamiento al que corre hoy en PatagoniaIX, con soporte de RPKI
activable por route server.

## Alcance

Dentro:

- Modelo de datos para filtrado por origen y prefijos, sesiones que no son de
  miembros, y servidores RPKI
- Generador: un solo render con ambas familias, contexto extendido
- Set de templates default euro-ix, reemplazando el actual
- API para los recursos nuevos
- Migracion de los IXPs existentes al set nuevo, con procedimiento documentado

Fuera:

- **Resolver automatico de IRR.** La tabla `member_prefix_filters` queda con su
  forma definitiva y con el campo `as_set` listo, pero la llena el operador. Un
  updater que corra `bgpq4` contra el AS-SET es un sub-proyecto propio, con su
  job, su cache y su manejo de fallas de IRR
- **Comparador semantico contra un `bird.conf` externo.** Es herramienta de
  validacion de la migracion de PatagoniaIX y vive en el spec de deployment.
  Parsear `bird.conf` arbitrario para hacerlo generico es un problema mas grande
  que el que resuelve hoy
- Looking glass
- **Blackholing RFC 7999.** Ver la seccion de templates huerfanos

## La inversion de logica de los filtros

Es el cambio conceptual central y hay que entenderlo antes de leer el resto.

Los templates actuales rechazan en el import:

```
import filter {
    if is_bogon_v4() then reject;
    ...
}
```

El patron euro-ix **nunca rechaza en el import**. Marca y acepta:

```
if !(avoid_martians()) then {
    bgp_large_community.add( IXP_LC_FILTERED_BOGON );
    accept;
}
```

La ruta entra igual a la tabla del peer, marcada con la razon. Quien la mata es el
pipe hacia master, con un filtro unico:

```
filter f_export_to_master {
    if bgp_large_community ~ [( routeserverasn, 1101, * )] then reject;
    accept;
}
```

El motivo es operativo: asi un looking glass puede mostrar "esta ruta la recibi y
la filtre por esta razon". Si se rechaza en el import, la ruta no existe y no hay
nada que explicar. Portar esto significa dar vuelta la logica completa de los
filtros default, no agregarles casos.

## Modelo de datos

### Tabla nueva: `route_server_peers`

Sesiones BGP que no cuelgan de un miembro. Hoy un `BGPSession` cuelga de
`trunk_vlan` -> `trunk` -> `member`, asi que una sesion de upstream o un colector
obligaria a inventar un miembro falso con trunk y conexion falsos, que despues
ensucia el IX-F export, las metricas y el portal.

| Campo | Tipo | Notas |
|---|---|---|
| `id` | UUID | PK |
| `ixp_id` | UUID | TenantMixin |
| `route_server_id` | UUID | FK, ON DELETE CASCADE |
| `name` | String(100) | usado para derivar el nombre de protocolo |
| `description` | Text | nullable |
| `peer_ip` | INET | |
| `peer_asn` | Integer | |
| `local_asn` | Integer | nullable, default el ASN del IXP |
| `passive` | Boolean | default true |
| `peer_type` | Enum | `upstream` / `collector` / `special` |
| `mark_community` | String(32) | nullable, forma `asn:value` |
| `max_prefixes` | Integer | nullable |
| `admin_state` | Enum | `BGPAdminState`, default `up` |
| `oper_state` | Enum | `BGPOperState`, default `unknown` |

`UniqueConstraint(route_server_id, peer_ip)`.

No lleva columna `af`: se deriva de `peer_ip`. `BGPSession` si la necesita porque
cuelga de un `trunk_vlan` y no de una IP, pero aca guardarla seria una segunda
fuente de verdad que puede discrepar de la primera.

`mark_community` cubre el caso real del upstream: las rutas que entran se marcan
con esa community, y el pipe hacia el peer excluye lo que la lleve, para no
devolverle al upstream sus propias rutas.

### Tabla nueva: `member_prefix_filters`

El `allas` / `allnet` del patron euro-ix. Por miembro y por familia, porque las
listas de v4 y v6 son distintas.

| Campo | Tipo | Notas |
|---|---|---|
| `id` | UUID | PK |
| `ixp_id` | UUID | TenantMixin |
| `member_id` | UUID | FK, ON DELETE CASCADE |
| `af` | Integer | 4 o 6, CHECK |
| `origin_asns` | ARRAY(BigInteger) | nullable |
| `prefixes` | ARRAY(CIDR) | nullable |
| `as_set` | String(255) | nullable, informativo hasta que exista el updater IRR |
| `source` | Enum | `manual` / `irr`, default `manual` |
| `last_updated_at` | timestamptz | nullable |

`UniqueConstraint(member_id, af)`.

Semantica, elegida para reproducir exacto lo que corre hoy:

- `origin_asns` NULL o vacio: se usa solo el ASN del miembro
- `prefixes` NULL: no se filtra por prefijo, solo por ASN de origen
- `prefixes` presente: la ruta que no matchee se marca
  `IXP_LC_FILTERED_IRRDB_PREFIX_FILTERED`

Un miembro sin fila en esta tabla se comporta como `origin_asns` = su propio ASN y
sin filtro de prefijos, que es el default seguro y lo que hacen 4 de los 5
miembros de PatagoniaIX.

### Tabla nueva: `rpki_servers`

| Campo | Tipo | Notas |
|---|---|---|
| `id` | UUID | PK |
| `ixp_id` | UUID | TenantMixin |
| `name` | String(100) | |
| `host` | String(255) | IP o hostname del RTR |
| `port` | Integer | default 3323 |
| `route_server_id` | UUID | nullable, NULL significa todos los RS del IXP |
| `transport` | Enum | `tcp` / `ssh`, default `tcp` |
| `refresh_time` | Integer | nullable |
| `retry_time` | Integer | nullable |
| `expire_time` | Integer | nullable |

`UniqueConstraint(ixp_id, name)`.

### Campos nuevos en `route_servers`

| Campo | Tipo | Default | Notas |
|---|---|---|---|
| `passive_sessions` | Boolean | true | politica del RS, no del peer |
| `rpki_enabled` | Boolean | false | |
| `rpki_policy` | Enum | `info_only` | `info_only` / `reject_invalid` |

`info_only` agrega solo la community de estado RPKI. `reject_invalid` ademas
agrega la community de filtrado `1101:13`, que es lo que hace que el pipe la
descarte. El paso de un modo al otro es un campo y una regeneracion, sin cambio de
template y sin downtime.

### Enums nuevos

`RouteServerPeerType`, `PrefixFilterSource`, `RPKIPolicy`, `RPKITransport`, todos
en `enums.py`.

### Mapeo de `MemberType` a community informativa

Los numeros ya estan definidos en el esquema euro-ix y documentados dentro del
config actual de PatagoniaIX:

| `MemberType` | Community |
|---|---|
| `ixp` | `(rsasn, 210)` |
| `isp` | `(rsasn, 220)` |
| `academico` | `(rsasn, 230)` |
| `gobierno` | `(rsasn, 240)` |
| `cdn` | `(rsasn, 250)` |
| `corporativo` | `(rsasn, 260)` |
| `infraestructura_critica` | `(rsasn, 270)` |
| `otro` | ninguna |
| NULL | ninguna |

Va como constante en codigo, no como configuracion.

## Generador

### Un solo render

`generate_config` deja de renderizar `bird_v4.conf.j2` y `bird_v6.conf.j2` por
separado para despues concatenar. Pasa a un unico render de `bird.conf.j2` con las
dos familias adentro y sin `include_globals`.

El motivo no es estetico. Con el patron euro-ix hay tres niveles de alcance
distintos: cosas globales de verdad (defines de communities, funciones), cosas
globales por familia (las tablas ROA, el `template bgp tb_rsclient` que lleva
adentro su bloque `ipv4 {}` o `ipv6 {}`), y las tablas por peer que ahora necesitan
sufijo de familia para no colisionar entre v4 y v6, cosa que antes no pasaba porque
eran daemons separados. Coordinar eso con una variable booleana que los templates
tienen que respetar por convencion es la misma clase de bug que ya produjo el
`protocol device` duplicado en produccion.

**No se mantiene el camino viejo.** El generador solo soporta `bird.conf.j2`. Los
IXPs existentes se migran (ver mas abajo).

### Presupuesto de nombres

BIRD limita los simbolos a 64 caracteres. El patron euro-ix deriva cinco simbolos
del mismo slug por peer y familia:

| Simbolo | Prefijo | Largo |
|---|---|---|
| tabla | `t_` | 2 |
| protocolo bgp | `pb_` | 3 |
| pipe | `pp_` | 3 |
| filtro import | `f_import_` | 9 |
| filtro export | `f_export_` | 9 |

El prefijo mas largo es 9, asi que **el slug se trunca a 55 caracteres**, no a 64.
`_sanitize_protocol_name` hoy trunca a 64 y con el set nuevo generaria simbolos de
hasta 73 que BIRD rechaza. Es un bug latente que este spec corrige, con test.

### Contexto extendido

`PeerContext` suma:

- `slug`: la base de 55 chars de la que salen los cinco simbolos
- `member_short_name`
- `member_type_community`: int o None
- `all_peer_ips`: todas las IPs de ese miembro en esa VLAN y familia, para el
  `allips` del chequeo de next hop. Hoy `build_peers` devuelve una IP por
  `trunk_vlan`; el chequeo necesita el conjunto completo del miembro
- `origin_asns`: resuelto ya sea de `member_prefix_filters` o del ASN del miembro
- `prefixes`: lista o None
- `af`

`RSPeerContext` nuevo para `route_server_peers`.

`RouteServerContext` suma `passive_sessions`, `rpki_enabled`, `rpki_policy` y la
lista de `rpki_servers` aplicables.

`build_peers` cambia de forma: una consulta por familia que ya traiga el filtro de
prefijos y el conjunto de IPs del miembro, sin N+1.

## Set de templates

Reemplaza a los 6 archivos actuales como default del producto.

| Archivo | Contenido |
|---|---|
| `bird.conf.j2` | esqueleto: globals, tablas, RPKI, loops de peers, ambas familias |
| `functions/communities.j2` | defines de large communities euro-ix: `1101` filtrado, `1000`/`1001` informativas |
| `functions/common.j2` | `avoid_martians` (consume los sets de `bogons.j2`), `honor_graceful_shutdown`, largo de prefijo |
| `functions/transit.j2` | `filter_has_transit_path` y la lista de ASNs transit-free |
| `functions/announce_control.j2` | `ixp_community_filter`: anuncio selectivo por `(0, peer-as)` y su forma large |
| `filters/to_master.j2` | `f_export_to_master` |
| `protocols/rpki.j2` | `protocol rpki` y tablas `roa4` / `roa6` |
| `protocols/rs_client.j2` | `template bgp tb_rsclient`: `rs client`, `source address`, `passive`, `interpret communities off`, `connect delay time 30` |
| `protocols/bgp_peer.j2` | por peer: tabla, filtro import, filtro export, protocolo, pipe |
| `protocols/rs_peer.j2` | los `route_server_peers` |
| `filters/bogons.j2` | se conserva: define los sets `BOGONS_V4` / `BOGONS_V6` |

Detalles que hay que portar y que no son obvios:

- `source address`: hoy los templates no lo emiten. Sin el, un route server con mas
  de una IP en la LAN de peering elige origen por lookup de ruta, que es ambiguo
- `interpret communities off`: habilita el pass-through de communities well-known
  de RFC 1997
- `connect delay time 30`: le da tiempo al RTR a poblarse antes de que levanten las
  sesiones
- `passive`: sale de `route_server.passive_sessions`
- `avoid_martians()` reemplaza a `is_bogon_v4()` / `is_bogon_v6()` y devuelve el
  valor **invertido**: true significa que la ruta esta limpia. Es el nombre y la
  convencion del patron euro-ix. Tener las dos formas conviviendo seria una fuente
  garantizada de errores de signo, asi que las viejas se eliminan

## Templates huerfanos y blackholing

El set default actual tiene 8 templates, no 6. Dos de ellos se instalan en la base
de cada IXP y **no los incluye nadie**:

- `protocols/static.j2`, que define `protocol static blackhole_v4` / `_v6` a partir
  de una variable `blackhole_routes_v4` que el generador nunca pasa
- `filters/communities.j2`, que define `BLACKHOLE_COMMUNITY` y la funcion
  `is_blackhole_request()`, que nadie llama

`bird_v4.conf.j2` solo hace include de `functions/common.j2`, `filters/bogons.j2` y
`protocols/bgp_peer.j2`. El resultado es que IXForge aparenta soportar RFC 7999 y
no lo soporta: la community `(65535, 666)` no tiene ningun efecto en el config
generado.

**Decision: los dos templates se borran y el blackholing queda fuera de alcance.**
El razonamiento es que implementarlo de verdad no es agregar un `if`: hay que
relajar los limites de largo de prefijo para aceptar /32 y /128 solo cuando la
ruta viene marcada, reescribir el next hop hacia una direccion de descarte,
decidir si se propaga la community a los demas miembros y verificar que ningun
filtro previo mate la ruta antes de llegar ahi. Estrenar ese camino en un route
server de produccion el mismo dia que cambia de plataforma acumula riesgo sin
necesidad, y PatagoniaIX no tiene blackholing hoy, asi que no es una regresion.

Queda como spec propio. El borrado es intencional y hay que decirlo en las notas
de la migracion, para que nadie lea la desaparicion de los archivos como un
descuido.

## API

- `POST` / `GET` / `PATCH` / `DELETE` `/route-servers/{id}/peers`
- `GET` / `PUT` / `DELETE` `/members/{id}/prefix-filters/{af}`
- `POST` / `GET` / `PATCH` / `DELETE` `/rpki-servers`
- `RouteServer` suma `passive_sessions`, `rpki_enabled` y `rpki_policy` en su
  schema de lectura y escritura

El contrato con el agent no cambia: sigue pidiendo un config y aplicandolo, sin
enterarse de que adentro hay tablas y pipes por peer. No hace falta tocar el repo
`agent` para este spec.

Todos los recursos nuevos disparan `defer_rs_config_regeneration` en create,
update y delete, igual que las sesiones BGP. Sin eso pasa lo mismo que paso antes:
la plataforma parece funcionar y los route servers nunca reciben la config nueva.

## Migracion de IXPs existentes

La migracion Alembic crea las tablas y campos nuevos, y **reemplaza el set de
templates de todos los IXPs existentes** por el nuevo, borrando los archivos
viejos. No hay modo de compatibilidad.

Procedimiento documentado, a correr por cada IXP ya desplegado (hoy: MetroportIX
prod y dev):

1. Exportar los templates actuales via `GET /route-servers/templates` y guardarlos
   fuera de la base
2. Aplicar la migracion
3. Cargar los datos nuevos que apliquen: tipo de miembro, filtros de prefijos,
   peers que no son miembros
4. Regenerar el config y revisar el diff contra la version anterior en el portal
5. Validar con `bird -p` antes de aplicar
6. Aplicar y verificar que las sesiones vuelvan a Established y que los conteos de
   prefijos coincidan con la foto previa

**Advertencia obligatoria en el procedimiento:** para un IXP que venia con los
templates viejos esto no es solo un cambio de formato, es un cambio de
comportamiento. Gana `rs client`, o sea el route server deja de meter su ASN en el
AS path y deja de reescribir el next hop. Es una correccion, pero cambia lo que ven
los peers y hay que verificarlo con ellos, no darlo por sentado.

La red de seguridad es que `ConfigVersion.template_snapshot` guarda una copia de
los templates con los que se genero cada config, asi que el estado anterior queda
recuperable aunque alguien se saltee el paso 1.

## Testing

TDD, como el resto del repo.

- Unitarios del generador: contexto, resolucion de `origin_asns` con y sin fila en
  `member_prefix_filters`, `all_peer_ips` con un miembro de dos conexiones,
  truncado del slug a 55 y unicidad tras el truncado
- Golden files: renderizar el config de un IXP fixture y comparar contra un archivo
  esperado versionado, para que cualquier cambio de template sea visible en el diff
  del PR
- Validacion real con `bird -p` en docker, como test de integracion marcado, para
  al menos: IXP sin peers, IXP solo v4, IXP solo v6, IXP dual con RPKI apagado, IXP
  dual con RPKI en cada uno de los dos modos, y un peer con filtro de prefijos
- Los tests de `test_config_generation` existentes se reescriben contra el set
  nuevo, no se adaptan a medias

## Riesgos y decisiones abiertas

1. **Un solo validador RPKI.** euro-ix recomienda dos. En el deployment de
   PatagoniaIX va a haber uno solo, en el Core, lo que convierte al Core en
   dependencia del filtrado de los route servers. En `info_only` es irrelevante. En
   `reject_invalid`, si el validador muere BIRD mantiene la ultima tabla ROA hasta
   que expire y despues deja de filtrar por RPKI, que es el comportamiento seguro.
   El modelo ya soporta varias filas en `rpki_servers` para cuando haya un segundo
2. **`interpret communities off`** cambia como BIRD trata las communities
   well-known. Es lo correcto para un route server y es lo que corre hoy en
   PatagoniaIX, pero para MetroportIX es un cambio de comportamiento
3. **Los ASNs transit-free** son una lista que envejece. Va como template editable,
   no como constante de codigo, para que un operador la pueda actualizar sin
   esperar un release
4. **Sin resolver IRR**, `member_prefix_filters` depende de que alguien la
   mantenga. Para un IXP chico es correcto. Para uno que crezca es deuda conocida,
   y el campo `as_set` esta puesto para pagarla despues sin migrar datos
