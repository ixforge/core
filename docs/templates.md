# Templates BIRD y `include_globals`

Los route servers corren BIRD 2.x. IXForge genera la config de cada route server
a partir de templates Jinja2 que viven en la base de datos por IXP (tabla
`route_server_templates`), editables desde el portal admin (Route Servers ->
Templates) con validacion de sintaxis y vista previa. El set por defecto esta en
`services/default_templates.py` y se instala al crear el IXP. Los templates
`bird_v4.conf.j2` y `bird_v6.conf.j2` estan protegidos (no se pueden borrar).

## Como se arma la config

BIRD 2.x es un daemon **dual-stack**: la misma instancia maneja IPv4 e IPv6. Por
eso IXForge no genera dos archivos, genera **un solo `bird.conf`** que junta la
parte v4 y la v6, y ese archivo lo valida un unico `bird -p`:

```
bird.conf  =  render(bird_v4.conf.j2)  +  render(bird_v6.conf.j2)
```

Cada regeneracion lee los templates **frescos de la base** (no hay cache): el
proceso arma un entorno Jinja nuevo con lo que este guardado en ese momento. Lo
que se edita y guarda en el portal se usa en la proxima regeneracion.

## Que es `include_globals` y por que existe

Hay directivas de BIRD que solo pueden aparecer **una vez** en todo el archivo. Si
aparecen dos veces, `bird -p` rechaza la config. Son:

- `router id`
- `protocol device`
- `protocol direct`
- el `log`
- las funciones comunes (`functions/common.j2`)

Como el archivo se arma juntando el template v4 **y** el v6, si los dos emitieran
esas directivas quedarian duplicadas y `bird -p` falla (por ejemplo "Kernel device
protocol already defined").

Para evitarlo, cada render recibe la variable booleana `include_globals`, y en el
template esas directivas van envueltas en un guard:

```jinja
{% if include_globals | default(true) %}
log syslog all;
router id {{ route_server.router_id }};
protocol device { scan time 10; }
protocol direct { disabled; }
{% include "functions/common.j2" %}
{% endif %}
```

IXForge pone `include_globals = True` en **un solo** render y `False` en el otro,
asi los globals salen una sola vez en el archivo combinado.

## Quien emite los globals

La regla, tal cual esta en `config_generation.py`:

- El render de **v4** siempre va con `include_globals = True`.
- El render de **v6** va con `include_globals = not (el RS tiene IPv4)`.

| Route server | v4 render | v6 render | Globals los emite |
|--------------|-----------|-----------|-------------------|
| Dual-stack (v4 + v6) | `True` | **`False`** | v4 |
| Solo v4 | `True` | (sin v6) | v4 |
| Solo v6 | (sin v4) | **`True`** | v6 |

**Consecuencia clave:** en un route server dual-stack (el caso normal), el
`bird_v6.conf.j2` se renderiza con `include_globals = False`, asi que **todo lo que
este dentro del `{% if include_globals %}` en el template v6 se descarta**. Solo
sobrevive lo que este fuera del guard (por ejemplo `protocol kernel`, los bogons y
los peers BGP, que estan despues del `{% endif %}`).

## Regla de oro al editar templates

El bloque `{% if include_globals %}` es **solo** para lo que debe salir una vez en
todo el daemon. Nada mas.

Cualquier cosa **por familia** va **fuera** del guard, porque no se duplica: v4 y
v6 tienen bloques con nombres distintos que no chocan entre si.

## Ejemplo: RPKI

RPKI es por familia. Las tablas ROA y los protocolos RPKI de v4 y v6 tienen nombres
distintos, no chocan, asi que cada uno va en su template, **fuera** del guard.

En `bird_v6.conf.j2`, despues del `{% endif %}` y antes del `protocol kernel`:

```jinja
{% if include_globals | default(true) %}
log syslog all;
...
{% include "functions/common.j2" %}
{% endif %}

roa6 table rpki6;
protocol rpki rpkiv6 {
    roa6 { table rpki6; };
    remote "REDACTED_IP" port 3323;
    refresh 600;
    retry 600;
    expire 7200;
}

protocol kernel {
    ipv6 { ... }
}
```

Lo mismo para v4 en `bird_v4.conf.j2` (`roa4 table rpki4;` + `protocol rpki
rpkiv4`, fuera del guard). Para que el RPKI filtre de verdad, agregar
`roa_check()` en el filtro de import de los peers.

Error tipico: poner el bloque RPKI v6 **dentro** del `{% if include_globals %}`. En
un RS dual-stack se descarta y el RPKI v6 nunca aparece, aunque el sistema diga que
la config se genero y aplico bien (la config es valida, solo le falta ese bloque).

## Como debuggear un template

- **Ver config generada** (detalle del route server, o el historial): muestra el
  `bird.conf` exacto que va al RS, con numeros de linea. Si un bloque que editaste
  no aparece ahi, casi siempre es que quedo dentro de un `{% if %}` que no se
  renderizo (tipicamente el `include_globals` del v6 en dual-stack).
- **Aviso de config pendiente** (detalle del RS): si el agente rechazo la config en
  la validacion de BIRD, muestra el error de `bird -p` con la linea. La vista de
  config generada resalta esa linea.
- El archivo temporal del RS (`/etc/bird/bird.conf.tmp`) se borra cuando `bird -p`
  falla, por eso no queda para mirar en el route server; el contenido siempre esta
  en el Core (vista de config generada).
