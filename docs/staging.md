# Staging: de desarrollo a producción

Lo que pasa de dev a prod es un commit, siempre el mismo, no un cambio suelto. Dev
y prod no son dos copias que se editan por separado: son dos entornos que ejecutan
el mismo commit de git, verificable por hash. El código que se despliega vive en
tres repos (`core`, `agent`, `collector`); los servidores no tienen `.git`, reciben
una copia de un commit puntual.

**Regla base:** commit primero, despliegue después. Nunca desplegar desde cambios
sin hacer commit. Los `deploy.sh` de cada repo abortan si hay cambios sin hacer commit
en archivos versionados.

## Entornos

Hay dos entornos, dev y prod, cada uno con su VM Core y sus route servers. En los
ejemplos se usan placeholders (`<core-host>`, `<rs1>`, `<rs2>`); reemplazarlos por
los valores de cada entorno.

| | dev | prod |
|--|--|--|
| Core (Docker) | `<core-host>` | `<core-host>` |
| Route servers | `<rs1>` / `<rs2>` | `<rs1>` / `<rs2>` |
| Red | aislada, datos de prueba | peering real |

En la VM Core se ejecutan, con Docker Compose, el stack del core (`core`,
`worker`, `portal` y `postgres` 17, en `/opt/ixforge/core/docker`) y el collector
con VictoriaMetrics (en `/opt/ixforge/collector`). En cada route server se
ejecutan BIRD 2.x y el agent (unidad systemd `ixforge-agent`, binario
`/usr/local/bin/ixforge-agent`, health check en el puerto 9100).

El acceso es por SSH como `root`. Desde WSL se usa `ssh.exe` (la VPN se ejecuta
en Windows); los `deploy.sh` lo detectan solos, y la variable `SSH` permite
forzar otro binario. Si un host no responde directo por la VPN pero sí desde la red, se
puede saltar por otro host con `ssh -J` (ver Despliegue manual).

## El pipeline

1. **Rama.** Cada cambio sale de `main` en su propia rama
2. **Gate local.** Si falla, no avanza (TDD: el test primero):
   ```bash
   uv run ruff check src/ tests/
   uv run ruff format --check src/ tests/
   uv run mypy src/
   uv run pytest
   ```
3. **Push y PR.** CI ejecuta el mismo gate sobre la rama, con el validador BIRD
   obligatorio (`IXFORGE_REQUIRE_BIRD=1`), y además el E2E de Core + agent + BIRD.
   Verde o no se mergea
4. **Despliegue a dev.** `./deploy.sh dev`, y se prueba de verdad ahí
5. **Merge a `main`.** Con CI verde y dev validado
6. **Despliegue a prod.** `./deploy.sh prod`, el mismo código que se probó en dev

## Los deploy.sh

Cada repo tiene su `./deploy.sh <dev|prod>`. Los hosts de cada entorno se leen de
un `deploy.env` local (gitignored, no va al repo): copiar `deploy.env.example` a
`deploy.env` y completar las IPs (`DEV_HOST` / `PROD_HOST` en core y collector,
`DEV_ROUTE_SERVERS` / `PROD_ROUTE_SERVERS` en agent). Todos abortan si hay cambios
sin hacer commit, verifican el acceso por SSH, piden confirmación para prod
(escribir `prod`; se salta con `--yes` o `-y`) y verifican al final.

```bash
./deploy.sh dev            # despliega a dev
./deploy.sh prod           # despliega a prod (pide escribir "prod" para confirmar)
./deploy.sh prod --yes     # sin confirmación interactiva
```

Qué hace cada uno:

- **core.** Ejecuta `/opt/ixforge/backup.sh` en el servidor, sube `git archive HEAD`
  a `/opt/ixforge/core`, copia el `.env` maestro (`/opt/ixforge/.env.core`) a
  `docker/.env`, ejecuta `docker compose up -d --build` y
  `docker compose run --rm core upgrade`, y verifica el health check, los errores
  del worker y el hash del código.
- **collector.** Sube `git archive HEAD` a `/opt/ixforge/collector`, ejecuta
  `docker compose up -d --build` y verifica el health check
  (`localhost:9200/health`) y el hash. Solo borra `src/` antes de extraer, así que
  el `.env` y la config real del servidor se conservan. Sin migraciones (el
  collector no tiene base).
- **agent.** Compila el binario release en Docker (`rust:1-bookworm`) a partir del
  checkout local, lo instala en cada route server del entorno (detiene
  `ixforge-agent`, reemplaza el binario y lo vuelve a arrancar), verifica que el
  sha256 del binario instalado sea el del compilado y que el health check del
  agent responda, y muestra lo que reporta: si BIRD está en ejecución y
  `core_connected`. BIRD no se toca.

## El ritual de despliegue a prod

Lo automatiza `./deploy.sh prod` de core, pero conviene entender qué hace, en
orden:

1. **Chequeos.** Árbol de trabajo limpio, acceso al host, confirmación
   interactiva. Si hay cambios sin hacer commit o el host no responde, aborta antes
   de tocar nada.
2. **Backup.** Ejecuta `/opt/ixforge/backup.sh` en el servidor, que deja un
   `pg_dump` comprimido de la base en `/opt/ixforge/backups`. Es el punto de
   retorno. Si falla, el despliegue aborta. El script vive en el servidor, no en
   el repo.
3. **Subir el commit.** `git archive HEAD` (solo lo que está en el commit, nada del árbol de
   trabajo ni archivos sin versionar) sobre `/opt/ixforge/core`. Solo se borra
   `src/` antes de extraer: un archivo que se eliminó del repo fuera de `src/`
   sigue en el servidor.
4. **Reconstruir.** `docker compose up -d --build`. Se recrean `core`, `worker` y
   `portal`, y el entrypoint aplica las migraciones al arrancar; BIRD y los agents
   en los route servers no se tocan, así que el peering no se cae.
5. **Migraciones.** `docker compose run --rm core upgrade`. Con las migraciones
   automáticas activas, el entrypoint ya migró en el paso anterior y este no
   encuentra nada que aplicar.
6. **Verificar.** El health check (`/api/v1/health`) tiene que responder (hasta
   20 intentos, cada 3 s) y el hash del código en el servidor tiene que ser igual
   al del commit; si no, aborta. Las líneas de error del worker en el último
   minuto solo generan un aviso.

Además conviene capturar el estado antes (sesiones BGP en `up`, miembros, config
actual) para comparar después y confirmar que nada se movió.

## Despliegue manual (respaldo)

Si `deploy.sh` no puede ejecutarse (por ejemplo, un route server que no responde
por la VPN pero sí a través de un jump host), esto es lo que automatiza, a mano:

```bash
# core (desde el repo, árbol de trabajo limpio)
ssh root@<core-host> /opt/ixforge/backup.sh
git archive --format=tar HEAD | gzip | ssh root@<core-host> '
  rm -rf /opt/ixforge/core/src && tar xzf - -C /opt/ixforge/core \
  && cp /opt/ixforge/.env.core /opt/ixforge/core/docker/.env \
  && cd /opt/ixforge/core/docker && docker compose up -d --build \
  && docker compose run --rm core upgrade'

# agent a un route server vía jump host (cuando no responde directo)
docker run --rm -v "$PWD":/src -v ixforge-cargo-cache:/usr/local/cargo/registry \
  -w /src rust:1-bookworm cargo build --release
cat target/release/ixforge-agent | ssh -J root@<core-host> root@<rs1> \
  'systemctl stop ixforge-agent && cat > /usr/local/bin/ixforge-agent.new \
   && chmod 755 /usr/local/bin/ixforge-agent.new \
   && mv /usr/local/bin/ixforge-agent.new /usr/local/bin/ixforge-agent \
   && systemctl start ixforge-agent'
```

## Verificar la versión desplegada

Los servidores no tienen `.git`, así que "qué commit está desplegado" se verifica
hasheando el árbol de fuentes y comparando con el commit local. Es el mismo
cálculo que hace `deploy.sh`, y cubre solo los `.py` de `src/`:

```bash
H='find src -type f -name "*.py" -print0 | LC_ALL=C sort -z | xargs -0 sha256sum | sha256sum'
eval "$H"                                     # local (con el árbol de trabajo limpio)
ssh root@<core-host> "cd /opt/ixforge/core && $H"   # servidor
```

**Atención: usar `LC_ALL=C`.** Sin eso, la collation de WSL y la de las VMs
difieren y el hash agregado da distinto aunque los archivos sean idénticos. El
agent se verifica por el sha del binario (`sha256sum /usr/local/bin/ixforge-agent`).

## Rollback

Como prod es un commit, volver atrás es desplegar otro commit:

```bash
git checkout <commit-anterior>
./deploy.sh prod
```

Si el commit que se revierte trae migraciones, el código anterior no reconoce la
revisión de la base: `ixforge upgrade` falla con `Can't locate revision` y, como el
entrypoint migra al arrancar y aborta ante un error, los contenedores no levantan.
En ese caso hay que devolver la base a la revisión anterior antes de desplegar:
con `alembic downgrade` desde el código nuevo, todavía desplegado (no todas las
migraciones lo soportan; `9f2c7a1b4d3e`, por ejemplo, no), o restaurando el
backup del paso 2 (`/opt/ixforge/backups/ixforge_backup_*.sql.gz`).

```bash
# en el servidor, antes de desplegar el commit anterior
cd /opt/ixforge/core/docker
docker compose exec core uv run alembic downgrade <revision-del-commit-anterior>
```

## Reglas

- **Commit antes de desplegar.** Prod siempre corresponde a un commit. Nunca
  desde un árbol de trabajo con cambios sin hacer commit
- **Etiquetar los releases de prod** (`v0.2`, `v0.3`...) para saber qué versión
  está arriba de un vistazo
- **CI es el gate.** Un commit con CI en rojo no se despliega
- **Orden entre repos.** `core` define contratos (`api/v1/agent.py`,
  `api/v1/monitoring.py`) que `agent` y `collector` consumen. Si se tocan esos
  endpoints, desplegar `core` primero y revisar los tests e2e
- **Docs y scripts no necesitan despliegue.** Los cambios que solo tocan `docs/` o
  los `deploy.sh` viven en el repo; no cambian el runtime, no hace falta
  desplegarlos

## Cómo encaja Claude

La idea de meter a Claude en dev y pasar los cambios limpios a prod funciona
porque la disciplina la pone el flujo, no el modelo. Claude trabaja en una rama,
ejecuta el gate local (ruff, mypy, pytest en TDD) y hace commit. Una persona
revisa el PR y el CI, lo despliega a dev y lo verifica. Cuando está bien, se
promueve ese mismo commit a prod con el ritual de arriba. Claude puede escribir el
código y hasta ejecutar el despliegue, pero el gate verde y la verificación en
prod son los que hacen que sea limpio, sin importar quién escribió el cambio.
