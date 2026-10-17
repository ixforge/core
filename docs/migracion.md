# Migrar un IXP ya desplegado

Procedimiento para IXPs que venían con los templates anteriores (el par
`bird_v4.conf.j2` / `bird_v6.conf.j2`). Ejecutarlo **una vez por IXP**, con una
persona mirando cada paso.

## Qué cambia, y por qué no es opcional

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

## Procedimiento

Con Docker, el entrypoint de los contenedores aplica las migraciones al arrancar
(salvo con `IXFORGE_AUTO_MIGRATE=false`). Desplegar el commit nuevo **es**
migrar, así que los pasos 1 a 3 van antes del despliegue.

### 1. Exportar los templates actuales

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

### 2. Foto previa de cada route server

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

### 3. Confirmar contra qué base se va a ejecutar

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

### 4. Aplicar la migración

Con Docker, la aplica el despliegue del commit nuevo (`./deploy.sh <dev|prod>`,
ver [staging.md](staging.md)). Fuera de Docker:

```bash
uv run ixforge upgrade
```

`ixforge upgrade` aplica el schema de procrastinate y después
`alembic upgrade head`. Las líneas `aviso:` salen en esa salida; con Docker
quedan en el log del contenedor que aplicó la migración
(`docker compose logs core worker | grep aviso`).

### 5. Cargar los datos nuevos

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

### 6. Regenerar y revisar el diff antes de aplicar

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

### 7. Aplicar y comparar

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
