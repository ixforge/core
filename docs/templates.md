# Templates BIRD

Los route servers corren BIRD 2.x. IXForge genera la config de cada route server
a partir de templates Jinja2 que viven en la base de datos por IXP (tabla
`route_server_templates`), editables desde el portal admin (Route Servers ->
Templates) con validacion de sintaxis y vista previa. El set por defecto esta en
`services/default_templates.py` y se instala al crear el IXP.

Cada regeneracion lee los templates **frescos de la base** (no hay cache): el
proceso arma un entorno Jinja nuevo con lo que este guardado en ese momento. Lo
que se edita y guarda en el portal se usa en la proxima regeneracion.

## La inversion de logica, lo primero que hay que entender

Es la parte contraintuitiva y la que mas confunde a quien edita un filtro por
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

La ruta entra igual a la tabla del peer, marcada con la razon. Quien la mata es el
pipe hacia master, con un unico filtro:

```
filter f_export_to_master
{
    if bgp_large_community ~ [( routeserverasn, 1101, * )] then reject;
    accept;
}
```

El motivo es operativo: asi un looking glass puede mostrar "esta ruta la recibi y
la filtre por esta razon". Si se rechazara en el import, la ruta no existiria y no
habria nada que explicar.

**Si vas a agregar un chequeo nuevo, marca y acepta. No pongas `reject`.** El
unico `reject` del config vive en `f_export_to_master`, y hay un test que verifica
que siga siendo el unico.

## Como se arma la config

BIRD 2.x es un daemon dual-stack: la misma instancia maneja IPv4 e IPv6. IXForge
hace **un solo render** de `bird.conf.j2`, con las dos familias adentro:

```
bird.conf = render(bird.conf.j2, peers_v4, peers_v6, rs_peers_v4, rs_peers_v6)
```

No existe `include_globals`. Antes se renderizaban `bird_v4.conf.j2` y
`bird_v6.conf.j2` por separado y se concatenaban, coordinando con una variable
booleana que los templates tenian que respetar por convencion. De ahi salio el
`protocol device` duplicado que llego a produccion. Con un solo render el problema
no se puede plantear.

## Los once templates

| Archivo | Contenido |
|---|---|
| `bird.conf.j2` | esqueleto: globals, includes, loops de peers de ambas familias. **Protegido** |
| `functions/communities.j2` | defines de large communities euro-ix: `1101` filtrado, `1000`/`1001` informativas |
| `filters/bogons.j2` | sets `MARTIANS_V4` y `MARTIANS_V6` |
| `functions/common.j2` | `avoid_martians4`, `avoid_martians6`, `honor_graceful_shutdown` |
| `functions/transit.j2` | `TRANSIT_ASNS` y `filter_has_transit_path` |
| `functions/announce_control.j2` | `ixp_community_filter`, el anuncio selectivo |
| `filters/to_master.j2` | `f_export_to_master`, el unico lugar que descarta |
| `protocols/rpki.j2` | tablas ROA y protocolos RPKI |
| `protocols/rs_client.j2` | `template bgp tb_rsclient_v4` / `_v6` |
| `protocols/bgp_peer.j2` | por peer miembro: tabla, filtros, protocolo y pipe |
| `protocols/rs_peer.j2` | por peer que no es miembro: upstream, colector, especial |

Solo `bird.conf.j2` esta protegido. Los otros diez son editables a proposito: un
operador tiene que poder ajustar filtros o actualizar la lista de ASNs
transit-free sin esperar un release.

## Simbolos derivados y el limite de 64

BIRD limita los simbolos a 64 caracteres. El patron euro-ix deriva **cinco**
simbolos del mismo slug por peer y familia:

| Simbolo | Prefijo | Largo |
|---|---|---|
| tabla | `t_` | 2 |
| protocolo bgp | `pb_` | 3 |
| pipe | `pp_` | 3 |
| filtro import | `f_import_` | 9 |
| filtro export | `f_export_` | 9 |

El prefijo mas largo mide 9, asi que el slug se trunca a **55**, no a 64.

Y lo que se recorta es el **nombre**: la IP y la familia van al final y no se
truncan nunca, porque son lo unico que distingue dos sesiones del mismo miembro.
Truncar el string completo, que es lo obvio, hace que dos peers con nombre largo
colapsen en el mismo simbolo y BIRD rechace el config con `Symbol already
defined`. La unicidad se verifica ademas sobre **todo el config**, no por familia:
BIRD tiene un unico namespace de simbolos por daemon.

## StrictUndefined

El entorno Jinja usa `StrictUndefined`. Un atributo que no existe en el contexto
**revienta al renderear** en vez de resolverse a string vacio.

Esto no es una preferencia de estilo. Sin `StrictUndefined`, un `{{ peer.tipo }}`
mal escrito produce `protocol bgp  {`, que BIRD rechaza, pero el config se guarda
igual como `ConfigVersion` y se le manda al agent: el error se descubre en el
route server y no en el origen.

Consecuencia al editar templates: para una variable que puede no estar, usa
`| default(...)` o `is defined`, no confies en que un `{% if %}` sobre algo
inexistente sea falso.

## Variables del contexto

`route_server`: `name`, `ip_v4`, `ip_v6`, `asn`, `router_id`, `passive_sessions`,
`rpki_enabled`, `rpki_policy`, `rpki_servers`.

`peers_v4` / `peers_v6`, cada uno con: `slug`, `member_name`, `member_short_name`,
`member_type_community`, `peer_ip`, `all_peer_ips`, `peer_asn`, `origin_asns`,
`prefixes`, `max_prefixes`, `af`.

`rs_peers_v4` / `rs_peers_v6`, cada uno con: `slug`, `name`, `description`,
`peer_ip`, `peer_asn`, `local_asn`, `passive`, `peer_type`, `mark_community`,
`max_prefixes`, `af`.

Sobre `prefixes`: **`none` y lista vacia no son lo mismo**. `none` desactiva el
filtro de prefijos; la lista vacia se renderea como `allnet = [ ];` y, como
`net ~ []` nunca matchea, marca todo como filtrado. Por eso los templates usan
`{% if peer.prefixes is not none %}` y no `{% if peer.prefixes %}`.

## Filtros Jinja propios

- `bird_str`: sanitiza un string para meterlo en el config
- `bird_community`: convierte `"64166:9999"` en `"64166, 9999"`. Rechaza ASNs de
  4 bytes, porque una community estandar son 32 bits partidos 16:16 y BIRD
  rechaza el config entero con `value out of bounds in pair constructor`
- `ipaddr`, `prefixlist`

## Communities informativas y colision de namespace

La community de tipo de miembro usa valores en el rango **65xxx**, dentro de los
ASN privados (64512-65534). No es estetico: el control de anuncio usa
`(routeserverasn, peer-as)` para "anunciar a este peer", asi que si el tipo de
miembro usara valores bajos, esos numeros serian ASN de 16 bits reales y los dos
espacios de nombres colisionarian.

La colision es explotable y va en la direccion peligrosa. El route server agrega
la community de tipo en el import, y despues `ixp_community_filter` la lee como
una excepcion de anuncio:

| | |
|---|---|
| Un miembro CDN pide "no anunciar a nadie" | `(0, rsasn)` |
| El route server le agrega su tipo | `(rsasn, 250)` con el esquema viejo |
| Al decidir si anunciar a AS250 | encuentra `(rsasn, 250)` y lo lee como "anunciar a AS250" |
| Resultado | la ruta se anuncia contra la voluntad del miembro |

En el rango privado no hay peers reales en un IXP, asi que los namespaces quedan
separados por construccion. Hay un test que verifica que todos los valores caigan
ahi.

| `MemberType` | Community |
|---|---|
| `ixp` | `(rsasn, 65210)` |
| `isp` | `(rsasn, 65220)` |
| `academico` | `(rsasn, 65230)` |
| `gobierno` | `(rsasn, 65240)` |
| `cdn` | `(rsasn, 65250)` |
| `corporativo` | `(rsasn, 65260)` |
| `infraestructura_critica` | `(rsasn, 65270)` |
| `otro`, NULL | ninguna |

Esa community es de uso interno y del looking glass: el filtro de export la borra
antes de mandarle la ruta al miembro.

## RPKI tambien en los peers que no son miembros

`protocols/rs_peer.j2` valida igual que el bloque de un miembro: etiqueta
`IXP_LC_INFO_RPKI_VALID` / `_INVALID` / `_UNKNOWN`, y con `rpki_policy =
reject_invalid` agrega ademas `IXP_LC_FILTERED_RPKI_INVALID`. Para que esa marca
sirva, el pipe del peer importa con `f_export_to_master` en vez de `import all`,
o sea que descarta en el mismo unico lugar que los miembros.

Esto importa mas de lo que parece. En un IXP con un upstream, la enorme mayoria
de las rutas que el route server redistribuye entran por ahi, no por los
miembros: validar solo a los miembros deja sin mirar casi todo lo que se
reparte. En PatagoniaIX eran 123.341 rutas del upstream contra 8 de los cinco
miembros.

Lo que el bloque del peer NO hace es el resto de los chequeos euro-ix: ni
bogons, ni first-AS, ni next hop, ni filtro de prefijos. Un upstream anuncia
legitimamente rutas de terceros con AS paths largos, asi que esos chequeos no
aplican. Si necesitas acotarlo, es con `max_prefixes`.

## El filtro de export borra las dos formas de community, salvo las marcas

`f_export_<peer>` borra las large `(rsasn, *, *)` **y** las estandar
`(rsasn, *)`. Dejar pasar las estandar filtra menos de lo que parece: las de
control de anuncio llegarian al miembro.

La excepcion son las `mark_community` configuradas en los peers que no son
miembros. Esa marca existe para que el miembro la vea y arme politica con ella,
asi que borrarla rompe al miembro. Pasa de verdad: en PatagoniaIX, Apoapsis usa
la marca del upstream para no reenviarle el transito a su cache de Microsoft, y
123.441 rutas dependian de eso.

El borrado se expresa entonces como el **complemento en rangos** de las marcas:

```
bgp_community.delete( [( routeserverasn, 0..9998 ), ( routeserverasn, 10000..65535 )] );
```

Es una sola sentencia declarativa en vez de un borrado seguido de un re-add
condicional. El re-add necesita saber cual marca estaba presente *despues* de
haberlas borrado todas, lo que sin variables locales obliga a anidar una rama
por combinacion de marcas. El complemento crece lineal y no depende de sintaxis
que varie entre menores de BIRD 2.x.

Solo se exceptuan las marcas cuyo primer componente es el ASN del IXP: una marca
de otro ASN no cae dentro de `(rsasn, *)` y no hay nada que exceptuar.

Las estandar solo se emiten si el ASN del IXP entra en 16 bits, por la misma
razon que el resto.

## Prefijos de documentacion y filtros de prefijos

`MARTIANS_V6` incluye `2001:db8::/32` (RFC 3849) y `3fff::/20` (RFC 9637), que son
los dos rangos de documentacion IPv6. Eso tiene una consecuencia al escribir
tests o fixtures: **el chequeo de martians corre ANTES del filtro de prefijos**,
asi que una whitelist con un prefijo de documentacion nunca se evalua, porque la
ruta ya murio. Un test que use `2001:db8:aa::/48` en `allnet` parece probar el
filtrado por prefijo y no prueba nada.

Hay un test que verifica que ningun prefijo de whitelist matchee un martian,
respetando la semantica de prefix set de BIRD: sin sufijo es coincidencia exacta,
`+` es el y mas especificos, `-` al reves.

## Compatibilidad entre versiones de BIRD 2.x

El validador de los tests y el BIRD de produccion pueden divergir **en las dos
direcciones**. Medido: BIRD 2.18 acepta `function f() -> bool` y ademas infiere
el tipo si no se declara; BIRD 2.0.12 **rechaza** esa sintaxis. Por eso los
templates no declaran tipo de retorno, aunque 2.18 emita un mensaje informativo.

Construir la imagen del validador con la version que corre en los route servers
no es opcional.

## IXPs con ASN de 4 bytes

Un IXP con ASN mayor a 65535 no puede expresar communities estandar. Los templates
condicionan esas formas al tamano del ASN y dejan solo las large, que cubren el
mismo caso. Para esos IXPs el control de anuncio y la community de tipo de miembro
funcionan exclusivamente por large communities, y hay que documentarselo a los
miembros.

## Validar cambios

Hay un golden file en `tests/golden/rs_dual_full.conf` con el config completo de
un IXP de referencia. Cualquier cambio de template aparece en su diff, que es el
punto: que se vea en el PR y no en produccion.

```bash
docker build -t ixforge-bird-validator:2 docker/bird-validator/
uv run pytest tests/test_config_generation.py
```

La imagen del validador tiene que construirse con **la misma version de BIRD que
corre en los route servers**: la sintaxis cambia entre menores de 2.x y un config
que pasa con una version no garantiza nada sobre otra.
