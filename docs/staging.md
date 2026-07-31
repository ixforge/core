# Staging: de desarrollo a produccion

El commit es la unidad de promocion. Dev y prod no son dos copias que se editan
por separado: son dos entornos que corren el mismo commit de git, verificable por
hash. El codigo vive en tres repos (`core`, `agent`, `collector`); los servidores
no tienen `.git`, se les manda una copia de un commit puntual.

**Regla base:** commit primero, deploy despues. Nunca desplegar desde cambios sin
commitear. Los `deploy.sh` de cada repo abortan si el working tree esta sucio.

## El pipeline

1. **Rama** — cada cambio sale de `main` en su propia rama
2. **Gate local** — `ruff`, `mypy`, `pytest` (TDD: el test primero). Si falla, no avanza
3. **Push y PR** — CI corre el mismo gate sobre la rama. Verde o no se mergea
4. **Deploy a dev** — `./deploy.sh dev`, y se prueba de verdad ahi
5. **Merge a `main`** — con CI verde y dev validado
6. **Deploy a prod** — `./deploy.sh prod`, el mismo commit que se probo en dev

## El ritual de deploy a prod

Lo automatiza `./deploy.sh prod`, pero conviene entender que hace:

1. **Chequeos** — working tree limpio, acceso al host, confirmacion interactiva
2. **Backup** de la base antes de tocar nada
3. **Subir el commit** con `git archive HEAD` (solo lo commiteado)
4. **Reconstruir** los contenedores y aplicar migraciones
5. **Verificar** — health OK, worker sin errores, y el hash del codigo en el
   servidor igual al del commit. Si no coincide, aborta

Rollback: como prod es un commit, volver atras es `git checkout <commit-anterior>`
y `./deploy.sh prod` de nuevo; si hubo cambios de datos, restaurar el backup.

## Reglas

- **Commit antes de deploy.** Prod siempre corresponde a un commit
- **Etiqueta los releases de prod** (`v0.2`, `v0.3`...) para saber que version esta arriba
- **CI es el gate.** Un commit en rojo no se deploya
- **Orden entre repos.** `core` define contratos (`api/v1/agent.py`,
  `api/v1/monitoring.py`) que `agent` y `collector` consumen. Si tocas esos
  endpoints, despliega `core` primero y revisa el e2e

## Entornos

| | dev | prod |
|--|--|--|
| IXP | REDACTED_IXP DEV | REDACTED_IXP |
| Core | REDACTED_IP | REDACTED_IP |
| Route servers | REDACTED_IP / .136 | REDACTED_IP / .36 |
| Red | aislada, datos de prueba | peering real |
