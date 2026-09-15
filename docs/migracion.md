# Migrar un IXP ya desplegado

Procedimiento para IXPs que venian con los templates anteriores. Correrlo **una
vez por IXP**, con una persona mirando cada paso.

## Que cambia, y por que no es opcional

El generador solo soporta `bird.conf.j2`. Un IXP que quede con el set anterior
falla con `TemplateNotFound: bird.conf.j2` al generar config. **La migracion de
templates tiene que ir en el mismo deploy que el codigo**, no despues.

Y para un IXP que venia con los templates viejos esto es un cambio de
**comportamiento**, no de formato:

- **Gana `rs client`.** El route server deja de meter su ASN en el AS path y de
  reescribir el next hop. Es una correccion, era un bug, pero cambia lo que ven
  los peers y hay que verificarlo con ellos
- **Gana `interpret communities off`**, el pass-through de communities well-known
  de RFC 1997
- **Gana el patron completo de route server**: tabla y pipe por peer, chequeo de
  first AS, proteccion de next hop, ASNs transit-free, filtrado por ASN de origen
- **Pierde `protocol kernel`.** Un route server no instala rutas en el kernel
- **Las communities de tipo de miembro pasan al rango 65xxx.** Si el IXP venia
  emitiendo valores bajos (`2xx`), hay una colision explotable con el control de
  anuncio que se corrige aca. Ver `docs/templates.md`. **Si un looking glass
  interpreta esas communities por su valor, hay que actualizarlo**
- **El filtro de export pasa a borrar tambien las communities estandar del IXP.**
  Los miembros dejan de recibir la de tipo de miembro, que es de uso interno
- **Desaparecen `protocols/static.j2` y `filters/communities.j2`.** Eran templates
  huerfanos: se instalaban en la base pero no los incluia nadie, asi que la
  community de blackhole `(65535, 666)` no tenia ningun efecto. El borrado es
  intencional, no un descuido. El blackholing RFC 7999 queda fuera de alcance y
  tiene su propio spec pendiente

## Procedimiento

### 1. Exportar los templates actuales

```bash
curl -sH "Authorization: Bearer $TOKEN" \
  https://<core>/api/v1/route-servers/templates \
  > templates-antes-$(date +%F).json
```

Guardarlo **fuera de la base**. Es lo unico que permite volver atras: el
`downgrade` de la migracion levanta `NotImplementedError` a proposito, porque
reconstruir los templates anteriores a ciegas seria peor que no bajar.

Red de seguridad adicional: `ConfigVersion.template_snapshot` guarda una copia de
los templates con los que se genero cada config, asi que el estado anterior queda
recuperable aunque alguien se saltee este paso.

### 2. Foto previa de cada route server

```bash
birdc show protocols
birdc show route count
for p in $(birdc show protocols | awk '/BGP/ {print $1}'); do
  echo "$p: $(birdc show route protocol $p count)"
done
```

Sin esta foto no hay con que comparar despues, y sin comparacion no se sabe si el
corte salio bien. Anotar tambien cualquier sesion que **ya estuviera caida**, para
que nadie se la achaque a la migracion.

### 3. Confirmar contra que base se va a correr

```bash
uv run python -c "from ixforge.config import get_settings; print(get_settings().database_url)"
```

La variable es `IXFORGE_DATABASE_URL`, no `DATABASE_URL`: `Settings` usa
`env_prefix="IXFORGE_"` y cualquier otra cosa se ignora en silencio. Esta
migracion **borra todas las filas de `route_server_templates`**; apuntada a la
base equivocada se lleva puestos los templates de otro IXP.

Si el comando imprime cualquier cosa que no sea la base esperada, **parar**.

### 4. Aplicar la migracion

```bash
uv run alembic upgrade head
```

### 5. Cargar los datos nuevos

Nada de esto es obligatorio para generar, pero sin ello el config sale mas
permisivo de lo que probablemente se quiera:

- `member_type` de cada miembro, para la community informativa
- Filtros de prefijos: `PUT /members/{id}/prefix-filters/{af}`. Un miembro sin
  filtro se comporta como "solo su propio ASN, sin filtro de prefijos"
- Peers que no son miembros: `POST /route-servers/{id}/peers` para upstream y
  colectores
- RPKI, si se va a usar: `POST /rpki-servers` y despues `PATCH` del route server
  con `rpki_enabled`. **Empezar en `info_only`**, que marca sin filtrar. Pasar a
  `reject_invalid` recien cuando este estable: es un campo y una regeneracion

### 6. Regenerar y revisar el diff antes de aplicar

Generar la config nueva y mirar el diff contra la anterior en el portal. Despues,
validar con `bird -p` **antes** de que el agent la aplique.

### 7. Aplicar y comparar

Aplicar, esperar a que las sesiones vuelvan a Established, y comparar los conteos
de prefijos contra la foto del paso 2. Una diferencia grande hacia abajo casi
siempre significa un filtro nuevo mordiendo mas de lo esperado: revisar que
communities `1101` aparecen en las rutas filtradas.

```bash
birdc show route filtered count
```
