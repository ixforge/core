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
