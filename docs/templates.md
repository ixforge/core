# Templates BIRD

Los route servers ejecutan BIRD 2.x. IXForge genera la configuración de cada
route server a partir de templates Jinja2 que viven en la base de datos, por IXP
(tabla `route_server_templates`). Se editan desde el portal admin (Route Servers
-> Administrar Templates, en `/admin/route-servers/templates`) o por la API
(`/api/v1/rs-templates`). El set por defecto está en
`services/default_templates.py` y lo instala el setup inicial (`run_setup`, vía
`POST /api/v1/setup`). Un IXP que ya existía llega al mismo set con las
migraciones: ver [migracion.md](migracion.md).

Guardar un template no valida su sintaxis Jinja. Se puede verificar aparte con
`POST /api/v1/rs-templates/validate`; si no, el error solo aparece al generar la
configuración.

Cada regeneración lee los templates **frescos de la base** (no hay caché): el
proceso arma un entorno Jinja nuevo con lo que esté guardado en ese momento. Lo
que se edita y guarda se usa en la próxima regeneración, y cada `ConfigVersion`
guarda en `template_snapshot` una copia de los templates con los que se generó.

## La inversión de lógica, lo primero que hay que entender

Es la parte contraintuitiva y la que más confunde a quien edita un filtro por
primera vez.

**Los filtros de import NUNCA rechazan.** Cuando una ruta falla un chequeo, el
filtro le agrega una large community de la forma `(routeserverasn, 1101, N)` y la
**acepta**:

```
    if !(avoid_martians4()) then {
        bgp_large_community.add( IXP_LC_FILTERED_BOGON );
        accept;
    }
```

La ruta entra igual a la tabla del peer, marcada con la razón. Quien la descarta
es el pipe hacia master, con un único filtro:

```
filter f_export_to_master
{
    if bgp_large_community ~ [( routeserverasn, 1101, * )] then reject;
    accept;
}
```

El motivo es operativo: así un looking glass puede mostrar "esta ruta la recibí y
la filtré por esta razón". Si se rechazara en el import, la ruta no existiría y no
habría nada que explicar.

**Para agregar un chequeo nuevo: marcar y aceptar, nunca `reject`.** El único
`reject` del config vive en `f_export_to_master`, y hay un test que verifica que
siga siendo el único.

### Los motivos que marca hoy el filtro de un miembro

`f_import_<peer>` (en `protocols/bgp_peer.j2`) evalúa en este orden. Casi todos
los chequeos marcan y aceptan en el acto, así que una ruta lleva el primer motivo
que falló:

| Chequeo | Large community |
|---|---|
| prefijo demasiado específico (IPv4 /25 a /32, IPv6 /49 a /128) | `(rsasn, 1101, 1)` |
| martian (`MARTIANS_V4` / `MARTIANS_V6`) | `(rsasn, 1101, 3)` |
| AS path vacío | `(rsasn, 1101, 6)` |
| el primer AS no es el del peer | `(rsasn, 1101, 7)` |
| next hop que no es ninguna IP del miembro en esa VLAN | `(rsasn, 1101, 8)` |
| un ASN transit-free en el AS path | `(rsasn, 1101, 14)` |
| AS path de más de 64 saltos | `(rsasn, 1101, 5)` |
| ASN de origen fuera de `origin_asns` | `(rsasn, 1101, 10)` |
| RPKI inválido, solo con RPKI encendido | `(rsasn, 1101, 13)` |
| prefijo fuera de la lista del miembro | `(rsasn, 1101, 9)` |

RPKI inválido es la excepción: marca pero no acepta en el acto, así que la ruta
sigue hasta el filtro de prefijos. `functions/communities.j2` define además los
motivos 2, 4, 11, 12 y 15, que hoy ningún template usa.

## Cómo se arma la config

BIRD 2.x es un daemon dual-stack: la misma instancia maneja IPv4 e IPv6. IXForge
hace **un solo render** de `bird.conf.j2`, con las dos familias adentro, y el
resultado es un único archivo:

```
bird.conf = render(bird.conf.j2, route_server, peers_v4, peers_v6,
                   rs_peers_v4, rs_peers_v6, rpki_communities)
```

`bird.conf.j2` emite una sola vez los globals (`timeformat`, `log`, los `define`
del route server, `router id` y `protocol device`), incluye los templates de
funciones y filtros, `protocols/rpki.j2` si `rpki_enabled` está encendido, y
después, por cada familia para la que el route server tiene IP, el template BGP de
clientes y los bloques de cada peer.

Como todo sale de un solo render, los bloques globales como `protocol device`
aparecen una sola vez sin que ningún template tenga que coordinarse con otro.

El hash SHA-256 de la versión se calcula sobre el render con la línea
`# Config hash:` vacía, y después se escribe en esa línea de la cabecera.

## Los once templates

| Archivo | Contenido |
|---|---|
| `bird.conf.j2` | esqueleto: globals, includes, loops de peers de ambas familias. **Protegido** |
| `functions/communities.j2` | defines de large communities: `1101` filtradas, `1001` informativas, `1002` tipo de miembro en forma large |
| `filters/bogons.j2` | sets `MARTIANS_V4` y `MARTIANS_V6` |
| `functions/common.j2` | `avoid_martians4`, `avoid_martians6`, `honor_graceful_shutdown` |
| `functions/transit.j2` | `TRANSIT_ASNS` y `filter_has_transit_path` |
| `functions/announce_control.j2` | `ixp_community_filter`, el anuncio selectivo |
| `filters/to_master.j2` | `f_export_to_master`, el único lugar que descarta |
| `protocols/rpki.j2` | tablas ROA y protocolos RPKI |
| `protocols/rs_client.j2` | `template bgp tb_rsclient_v4` / `_v6` |
| `protocols/bgp_peer.j2` | por peer miembro: tabla, filtros, protocolo y pipe |
| `protocols/rs_peer.j2` | por peer que no es miembro: upstream, colector, especial |

Protegido significa que no se puede borrar; sí se puede editar. Los otros diez
tampoco se pueden borrar mientras otro template los incluya. Que todos sean
editables es a propósito: un operador tiene que poder ajustar filtros o
actualizar la lista de ASNs transit-free sin esperar un release.

## Símbolos derivados y el límite de 64

BIRD limita los símbolos a 64 caracteres. El patrón de route server deriva
**cinco** símbolos del mismo slug por peer y familia:

| Símbolo | Prefijo | Largo |
|---|---|---|
| tabla | `t_` | 2 |
| protocolo bgp | `pb_` | 3 |
| pipe | `pp_` | 3 |
| filtro import | `f_import_` | 9 |
| filtro export | `f_export_` | 9 |

El prefijo más largo mide 9, así que el slug se trunca a **55**, no a 64.

Y lo que se recorta es el **nombre**: la IP y la familia van al final y no se
truncan nunca, porque son lo único que distingue dos sesiones del mismo miembro.
Truncar el string completo, que es lo obvio, hace que dos peers con nombre largo
colapsen en el mismo símbolo y BIRD rechace el config con `Symbol already
defined`. La unicidad se verifica además sobre **todo el config**, no por familia,
porque BIRD tiene un único namespace de símbolos por daemon: si dos slugs
coinciden, el segundo recibe un sufijo `_2`, `_3`, etc.

## StrictUndefined

El entorno Jinja es un `SandboxedEnvironment` con `StrictUndefined`. Un atributo
que no existe en el contexto **revienta al renderizar** en vez de resolverse a
string vacío.

Esto no es una preferencia de estilo. Sin `StrictUndefined`, un `{{ peer.tipo }}`
mal escrito produce `protocol bgp  {`, que BIRD rechaza, pero el config se guarda
igual como `ConfigVersion` y se le manda al agent: el error se descubre en el
route server y no en el origen.

Consecuencia al editar templates: para una variable que puede no estar, usar
`| default(...)` o `is defined`. Un `{% if %}` sobre algo inexistente no da falso,
revienta.

## Variables del contexto

`route_server`: `name`, `ip_v4`, `ip_v6`, `asn` (el ASN del IXP), `router_id`,
`passive_sessions`, `rpki_enabled`, `rpki_servers`, `communities_conservadas`.

`route_server.rpki_servers`, cada uno con: `slug`, `name`, `host`, `port`,
`transport`, `refresh_time`, `retry_time`, `expire_time`.

`peers_v4` / `peers_v6`, cada uno con: `slug`, `member_name`, `member_short_name`,
`member_type_community`, `peer_ip`, `all_peer_ips`, `peer_asn`, `origin_asns`,
`prefixes`, `max_prefixes`, `af`.

`rs_peers_v4` / `rs_peers_v6`, cada uno con: `slug`, `name`, `description`,
`peer_ip`, `peer_asn`, `local_asn`, `passive`, `peer_type`, `peer_type_community`,
`mark_community`, `max_prefixes`, `af`.

Además: `rpki_communities` (`valid` y `unknown`), `generated_at`, `config_hash`
(vacío durante el render) y `af`, que `bird.conf.j2` fija con `{% with af = 4 %}`
y `{% with af = 6 %}`.

Sobre `origin_asns`: sin filtro cargado, o con la lista vacía, cae al ASN del
miembro, que es el lado restrictivo.

Sobre `prefixes`: **`none` y la lista vacía no son lo mismo**. `none` desactiva el
filtro de prefijos; la lista vacía se renderiza como `allnet = [  ];` y, como
`net ~ []` nunca coincide, marca todo como filtrado. Por eso los templates usan
`{% if peer.prefixes is not none %}` y no `{% if peer.prefixes %}`.

## Filtros Jinja propios

- `bird_str`: sanitiza un string para meterlo en el config (deja letras, dígitos,
  `_`, espacio, tab, `-` y `.`, y corta a 255 caracteres)
- `bird_community`: convierte `"64166:9999"` en `"64166, 9999"`. Rechaza cualquier
  componente mayor a 65535, porque una community estándar son 32 bits partidos
  16:16 y BIRD rechaza el config entero con `value out of bounds in pair
  constructor`
- `rangos_a_borrar`: el complemento de `communities_conservadas` como set de
  `(routeserverasn, a..b)`, para el borrado del export
- `intervalos_como_set`: `communities_conservadas` como set, para el borrado del
  import
- `ipaddr`, `prefixlist`

## El esquema de communities es el de PIT Chile

Una community lleva el ASN adelante, así que `61522:65120` y `64166:65120` son
distintas por construcción y nunca hubo colisión que evitar entre dos IXPs. Usar
los mismos valores hace que un miembro conectado a varios use un solo número por
concepto, y que un IXP nuevo adopte el esquema tal cual en vez de inventar el
suyo. Los valores están en `services/communities.py`.

| Origen | Community |
|---|---|
| RPKI válido | `(rsasn, 65012)` |
| RPKI desconocido | `(rsasn, 65023)` |
| miembro `ixp` | `(rsasn, 65110)` |
| miembro `isp` | `(rsasn, 65120)` |
| miembro `academico` | `(rsasn, 65130)` |
| miembro `gobierno` | `(rsasn, 65140)` |
| miembro `cdn` | `(rsasn, 65150)` |
| miembro `corporativo` | `(rsasn, 65160)` |
| miembro `infraestructura_critica` | `(rsasn, 65170)` |
| peer `upstream` | `(rsasn, 65180)` |
| peer `collector` | `(rsasn, 65190)` |
| miembro `otro` o sin tipo, peer `special` | ninguna |

Las de `upstream` y `collector` son extensión: PIT no modela peers que no son
miembros.

Todo el bloque, `65000..65199`, es **público**: el export lo conserva para que el
miembro pueda distinguir tránsito de peering y una ruta validada de una que no.

### Por qué el rango 65xxx: la colisión con el control de anuncio

El bloque cae dentro de los ASN privados (64512-65534). No es estético: el control
de anuncio usa `(routeserverasn, peer-as)` para "anunciar a este peer", así que si
el tipo de miembro usara valores bajos, esos números serían ASN de 16 bits reales
y los dos espacios de nombres colisionarían.

La colisión es explotable y va en la dirección peligrosa. El route server agrega
la community de tipo en el import, y después `ixp_community_filter` la lee como
una excepción de anuncio:

| | |
|---|---|
| Un miembro CDN pide "no anunciar a nadie" | `(0, rsasn)` |
| El route server le agrega su tipo | `(rsasn, 250)` con un esquema de valores bajos |
| Al decidir si anunciar a AS250 | encuentra `(rsasn, 250)` y lo lee como "anunciar a AS250" |
| Resultado | la ruta se anuncia contra la voluntad del miembro |

En el rango privado no hay peers reales en un IXP, así que los namespaces quedan
separados por construcción. Hay un test que verifica que todos los valores caigan
ahí.

## RPKI también en los peers que no son miembros

`protocols/rs_peer.j2` valida igual que el bloque de un miembro: etiqueta las
rutas válidas con `(rsasn, 65012)`, las desconocidas con `(rsasn, 65023)` y marca
las inválidas con `IXP_LC_FILTERED_RPKI_INVALID`. Para que esa marca sirva, el
pipe del peer importa con `f_export_to_master` en vez de `import all`, o sea que
descarta en el mismo único lugar que los miembros. El bloque agrega además la
community de tipo del peer y su `mark_community`, si tiene una.

Esto importa más de lo que parece. En un IXP con un upstream, la enorme mayoría
de las rutas que el route server redistribuye entran por ahí, no por los
miembros: validar solo a los miembros deja sin mirar casi todo lo que se reparte.
En PatagoniaIX eran 123.341 rutas del upstream contra 8 de los cinco miembros.

Lo que el bloque del peer NO hace es el resto de los chequeos de route server: ni
bogons, ni first-AS, ni next hop, ni filtro de prefijos, ni el borrado de las
communities del bloque público. Un upstream anuncia legítimamente rutas de
terceros con AS paths largos, así que esos chequeos no aplican. Para acotarlo se
usa `max_prefixes`.

## El control de anuncio tiene dos niveles

`ixp_community_filter` se evalúa en el export del pipe de cada miembro (master ->
tabla del peer) y decide, para cada par (ruta, peer), si la ruta se le anuncia.
Las rutas que no vienen de BGP no se propagan. Los peers que no son miembros no
pasan por este filtro: su pipe exporta con `export all`.

El modelo son dos niveles, no una lista plana de banderas:

1. **Prohibiciones**, que valen solas y tienen prioridad: `(0, peer-as)` y su
   forma large `(rsasn, 0, peer-as)` sacan a ese peer; `(0, rsasn)` y
   `(rsasn, 0, 0)` activan el modo selectivo, o sea nadie salvo excepciones
2. **Excepciones**, que solo se evalúan si el modo selectivo está activo:
   `(rsasn, peer-as)` y `(rsasn, 1, peer-as)` habilitan a ese peer;
   `(rsasn, rsasn)` y `(rsasn, 1, 0)` habilitan a todos

Fuera del modo selectivo el default es anunciar, así que **una community de
habilitar sin una de prohibir no cambia nada**. Eso importa al documentar: si se
listan como si fueran acciones sueltas, un miembro pone la de habilitar sola y
espera un efecto que no ocurre.

Las formas large existen para peers con ASN de 4 bytes, que no entran en una
community estándar de 16:16.

El cuarteto clásico incluye `(rsasn, rsasn)`, "anunciar a todos". El filtro la
entiende, pero con el default de anunciar no puede cambiar ningún resultado:
ponerla junto a `(0, rsasn)` equivale a no poner ninguna de las dos. Solo sería
necesaria en un route server cuyo default fuera denegar. Se mantiene implementada
por compatibilidad con miembros que vengan de otros IXPs, y se omite de la
documentación de cara al miembro por la misma razón del párrafo anterior.

## RPKI no tiene modos: si está encendido, descarta

`rpki_enabled` es el único switch. Una ruta inválida se marca con
`IXP_LC_FILTERED_RPKI_INVALID` y muere en el pipe hacia master, como cualquier
otra ruta filtrada.

De ahí sale que **solo se etiquetan dos estados**, válido y desconocido: son los
únicos que un miembro puede llegar a ver. Una inválida se descarta, así que no
hay a quién informarle, y "no verificado" solo existiría con RPKI apagado, que es
cuando tampoco se emite nada.

Con RPKI encendido, el template de clientes activa `import table on`: sin eso,
cuando cambian o expiran las ROAs, BIRD no puede reevaluar el filtro de import
sobre las rutas ya recibidas sin pedirle un route refresh al peer. Un servidor RTR
sin `route_server_id` aplica a todos los route servers del IXP.

Para estrenar RPKI sin riesgo se enciende primero en un route server y después en
el otro, midiendo el impacto en el primero. Usa la redundancia que ya existe en
vez de una opción de configuración.

## El export conserva el bloque público y borra el resto

`f_export_<peer>` borra las large `(rsasn, *, *)` y, de las estándar, todo
`(rsasn, *)` **menos** el bloque público y las `mark_community` del ASN del IXP
configuradas en los peers que no son miembros. Lo que se sigue borrando es el
control de anuncio, que es interno.

El borrado se expresa como el **complemento en rangos** de lo que se conserva.
Sin marcas configuradas queda así:

```
    bgp_community.delete( [( routeserverasn, 0..64999 ), ( routeserverasn, 65200..65535 )] );
```

Es una sola sentencia declarativa en vez de un borrado seguido de un re-add
condicional. El re-add necesita saber qué estaba presente *después* de haber
borrado todo, lo que sin variables locales obliga a anidar una rama por
combinación. El complemento crece lineal y no depende de sintaxis que varíe entre
menores de BIRD 2.x.

## El import borra exactamente lo que el export conserva

Simétrico y por la misma razón: lo que el route server tiene derecho a poner es
justo lo que no puede aceptar de un peer. Sin esto un miembro manda
`(rsasn, 65180)` en sus propias rutas y se hace pasar por el upstream ante los
demás, o se autoetiqueta como RPKI válido. Sin marcas configuradas queda así:

```
    bgp_community.delete( [( routeserverasn, 65000..65199 )] );
```

Va como primera sentencia del filtro de import de cada miembro, antes de
cualquier chequeo. Si hay marcas, entran en el mismo set.

## El pipe no lleva filtro anti-bucle

BIRD no reinyecta por un pipe lo que entró por ese mismo pipe. Verificado contra
2.18 con dos tablas, dos protocolos y `export all` sin ningún filtro: la tabla
de cada uno termina con su propia ruta una sola vez.

Eso importa porque invita a un error: pintar la ruta con una community en el
import para reconocerla después en el pipe. No hace falta, no escala (con dos
upstreams se necesita una marca por peer) y tiene un costo real: esa marca
interna se le escapa al miembro y termina siendo su interfaz de facto. En
PatagoniaIX pasó exactamente eso, y 123.410 rutas dependían de un número que
nunca fue parte de ningún contrato.

## Prefijos de documentación y filtros de prefijos

`MARTIANS_V6` incluye `2001:db8::/32` (RFC 3849) y `3fff::/20` (RFC 9637), que son
los dos rangos de documentación IPv6. Eso tiene una consecuencia al escribir
tests o fixtures: **el chequeo de martians va ANTES del filtro de prefijos**, así
que una lista de prefijos con uno de documentación nunca se evalúa, porque la ruta
ya murió. Un test que use `2001:db8:aa::/48` en `allnet` parece probar el
filtrado por prefijo y no prueba nada.

Hay un test que verifica que ningún prefijo autorizado coincida con un martian,
respetando la semántica de prefix set de BIRD: sin sufijo es coincidencia exacta,
`+` es el prefijo y sus más específicos, `-` el prefijo y sus menos específicos.

## Compatibilidad entre versiones de BIRD 2.x

El validador de los tests y el BIRD de producción pueden divergir **en las dos
direcciones**. Medido: BIRD 2.18 acepta `function f() -> bool` y además infiere
el tipo si no se declara; BIRD 2.0.12 **rechaza** esa sintaxis. Por eso los
templates no declaran tipo de retorno, aunque 2.18 emita un mensaje informativo.

La imagen de `docker/bird-validator/` instala el paquete `bird2` de Debian
bookworm, que es 2.0.12. Tiene que coincidir con la versión que se ejecuta en los
route servers: un config que pasa con una versión no garantiza nada sobre otra.

## IXPs con ASN de 4 bytes

Un IXP con ASN mayor a 65535 no puede expresar communities estándar propias. Los
templates condicionan esas formas a `route_server.asn <= 65535`:

- Del control de anuncio quedan las formas large y `(0, peer-as)`, que no lleva el
  ASN del IXP
- La community de tipo de miembro va en forma large, `(rsasn, 1002, valor)`
- La community de tipo de los peers que no son miembros no se emite
- Con RPKI encendido no se emiten las etiquetas de válido `(rsasn, 65012)` ni de
  desconocido `(rsasn, 65023)`; la ruta inválida se sigue marcando con
  `IXP_LC_FILTERED_RPKI_INVALID` y se descarta igual
- El export borra todas las large `(rsasn, *, *)`, así que el miembro no recibe
  la de tipo: en estos IXPs no hay bloque público

Hay que documentárselo a los miembros.

## Validar cambios

Hay un golden file en `tests/golden/rs_dual_full.conf` con el config completo de
un IXP de referencia. Cualquier cambio de template aparece en su diff, que es el
punto: que se vea en el PR y no en producción.

```bash
# base de tests en el puerto 5433
docker compose -f docker/docker-compose.testing.yml up -d
# validador BIRD; sin la imagen, los tests que lo usan se saltan
docker build -t ixforge-bird-validator:2 docker/bird-validator/
uv run pytest tests/test_config_generation.py
```

Con `IXFORGE_REQUIRE_BIRD=1`, como en CI, la falta del validador hace fallar la
suite en vez de saltar esos tests.

Para actualizar el golden después de un cambio intencional: borrar el archivo y
ejecutar el test. Lo recrea y falla a propósito; revisar el diff en git y volver a
ejecutarlo.
