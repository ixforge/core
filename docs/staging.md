# Staging: de desarrollo a produccion

El commit es la unidad de promocion. Dev y prod no son dos copias que se editan
por separado: son dos entornos que corren el mismo commit de git, verificable por
hash. El codigo vive en tres repos (`core`, `agent`, `collector`); los servidores
no tienen `.git`, se les manda una copia de un commit puntual.

**Regla base:** commit primero, deploy despues. Nunca desplegar desde cambios sin
commitear. Los `deploy.sh` de cada repo abortan si el working tree esta sucio.

## Entornos

| | dev | prod |
|--|--|--|
| IXP | REDACTED_IXP DEV | REDACTED_IXP |
| Core (Docker) | REDACTED_IP | REDACTED_IP |
| Route servers | REDACTED_IP / .136 | REDACTED_IP / .36 |
| Red | aislada, datos de prueba | peering real |

En la VM Core corren, por Docker Compose: el stack del core (api + worker + portal
+ postgres 17, en `/opt/ixforge/core/docker`) y el collector + VictoriaMetrics (en
`/opt/ixforge/collector`). En cada route server corre BIRD 2.x y el agent (systemd
`ixforge-agent`).

El acceso es por SSH. Desde WSL se usa `ssh.exe` (la VPN corre en Windows); los
`deploy.sh` lo detectan solos. Si un host no responde directo por la VPN pero si
desde la red, se puede saltar por otro host con `ssh -J`.

## El pipeline

1. **Rama.** Cada cambio sale de `main` en su propia rama
2. **Gate local.** `ruff`, `mypy`, `pytest` (TDD: el test primero). Si falla, no avanza
3. **Push y PR.** CI corre el mismo gate sobre la rama. Verde o no se mergea
4. **Deploy a dev.** `./deploy.sh dev`, y se prueba de verdad ahi
5. **Merge a `main`.** Con CI verde y dev validado
6. **Deploy a prod.** `./deploy.sh prod`, el mismo commit que se probo en dev

## Los deploy.sh

Cada repo tiene su `./deploy.sh <dev|prod>`. Todos despliegan el commit de HEAD
(con `git archive`, no el working tree), abortan si hay cambios sin commitear,
piden confirmacion para prod (saltable con `--yes`) y verifican al final.

```bash
./deploy.sh dev            # despliega a dev
./deploy.sh prod           # despliega a prod (pide escribir "prod" para confirmar)
./deploy.sh prod --yes     # sin confirmacion interactiva
```

Que hace cada uno:

- **core.** Backup de la base, sube el commit a `/opt/ixforge/core`, restaura el
  `.env` maestro, `docker compose up -d --build`, aplica migraciones
  (`ixforge upgrade`), y verifica health + worker sin errores + hash del codigo
  igual al commit.
- **collector.** Sube el commit a `/opt/ixforge/collector` preservando el `.env`
  y la config real del servidor, `docker compose up -d --build`, y verifica health
  + hash. Sin migraciones (el collector no tiene BD).
- **agent.** Compila el binario release en Docker (`rust:1-bookworm`), lo instala
  en los dos route servers del entorno via systemd, y verifica que ambos queden
  con el binario identico y reporten `bird running` + `core_connected`. BIRD no se
  toca.

## El ritual de deploy a prod

Lo automatiza `./deploy.sh prod`, pero conviene entender que hace, en orden:

1. **Chequeos.** Working tree limpio, acceso al host, confirmacion interactiva.
   Si el arbol esta sucio o el host no responde, aborta antes de tocar nada.
2. **Backup** (core). Un `pg_dump` comprimido de la base antes de tocar nada, en
   `/opt/ixforge/backups`. Es el punto de retorno.
3. **Subir el commit.** `git archive HEAD` (solo lo commiteado, nada de working
   tree ni untracked) sobre el directorio del servidor.
4. **Reconstruir.** `docker compose up -d --build` y, en core, las migraciones.
   Se reinician core/worker/portal; BIRD y los agents en los route servers no se
   tocan, asi que el peering no se cae.
5. **Verificar.** Health OK, worker sin errores, y el hash del codigo en el
   servidor igual al del commit. Si no coincide, aborta. Para el agent: mismo
   binario en los dos RS + health.

Ademas conviene capturar el estado antes (sesiones BGP en `up`, miembros, config
actual) para comparar despues y confirmar que nada se movio.

## Deploy manual (respaldo)

Si `deploy.sh` no puede correr (por ejemplo un route server que no responde por la
VPN pero si por jump host), esto es lo que automatiza, a mano:

```bash
# core (desde el repo, working tree limpio)
git archive --format=tar HEAD | gzip | ssh root@REDACTED_IP '
  rm -rf /opt/ixforge/core/src && tar xzf - -C /opt/ixforge/core \
  && cp /opt/ixforge/.env.core /opt/ixforge/core/docker/.env \
  && cd /opt/ixforge/core/docker && docker compose up -d --build \
  && docker compose run --rm core upgrade'

# agent a un RS via jump host (cuando el RS no responde directo)
docker run --rm -v "$PWD":/src -v ixforge-cargo-cache:/usr/local/cargo/registry \
  -w /src rust:1-bookworm cargo build --release
cat target/release/ixforge-agent | ssh -J root@REDACTED_IP root@REDACTED_IP \
  'systemctl stop ixforge-agent && cat > /usr/local/bin/ixforge-agent.new \
   && chmod 755 /usr/local/bin/ixforge-agent.new \
   && mv /usr/local/bin/ixforge-agent.new /usr/local/bin/ixforge-agent \
   && systemctl start ixforge-agent'
```

## Verificar la version desplegada

Los servidores no tienen `.git`, asi que "que commit corre" se verifica hasheando
el arbol de fuentes y comparando con el commit local:

```bash
H='find src -type f -name "*.py" -print0 | LC_ALL=C sort -z | xargs -0 sha256sum | sha256sum'
eval "$H"                                   # local (con el working tree limpio)
ssh root@REDACTED_IP "cd /opt/ixforge/core && $H"   # prod
```

**Ojo: usar `LC_ALL=C`.** Sin eso, la collation de WSL y la de las VMs difieren y
el hash agregado da distinto aunque los archivos sean identicos. El agent se
verifica por el sha del binario (`sha256sum /usr/local/bin/ixforge-agent`).

## Rollback

Como prod es un commit, volver atras es desplegar otro commit:

```bash
git checkout <commit-anterior>
./deploy.sh prod
```

Si hubo cambios de datos (migraciones que transformaron la base), ademas restaurar
el backup del paso 2 (`/opt/ixforge/backups/ixforge_backup_*.sql.gz`).

## Reglas

- **Commit antes de deploy.** Prod siempre corresponde a un commit. Nunca desde un
  working tree con cambios sin commitear
- **Etiqueta los releases de prod** (`v0.2`, `v0.3`...) para saber que version esta
  arriba de un vistazo
- **CI es el gate.** Un commit con CI en rojo no se deploya
- **Orden entre repos.** `core` define contratos (`api/v1/agent.py`,
  `api/v1/monitoring.py`) que `agent` y `collector` consumen. Si tocas esos
  endpoints, despliega `core` primero y revisa el e2e
- **Docs y scripts no necesitan deploy.** Cambios que solo tocan `docs/` o los
  `deploy.sh` viven en el repo; no cambian el runtime, no hace falta desplegarlos

## Como encaja Claude

La idea de meterle Claude a dev y pasar los cambios limpios a prod funciona porque
la disciplina la pone el flujo, no el modelo. Claude trabaja en una rama, corre el
gate local (ruff, mypy, pytest en TDD) y commitea. Tu revisas el PR y el CI, lo
despliegas a dev y lo verificas. Cuando esta ok, se promueve ese mismo commit a
prod con el ritual de arriba. Claude puede escribir el codigo y hasta correr el
deploy, pero el gate verde y la verificacion en prod son los que hacen que sea
limpio, sin importar quien escribio el cambio.
