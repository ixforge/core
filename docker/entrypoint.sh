#!/bin/sh
# Entrypoint de los contenedores de IXForge.
#
# Aplica las migraciones antes de arrancar el comando pedido. Sin esto, un
# deployment nuevo levanta con la base vacia: el healthcheck da "healthy"
# porque solo chequea que la conexion abra, y el Core responde 500 en cada
# request con relation "ixps" does not exist.
#
# Los tres servicios (core, worker, ui) arrancan a la vez y todos pasan por
# aca. La concurrencia la resuelve el pg_advisory_xact_lock de alembic/env.py:
# el primero migra y los otros esperan y no encuentran nada que aplicar.
#
# IXFORGE_AUTO_MIGRATE=false lo desactiva, para quien prefiera controlar
# cuando se migra.
set -e

if [ "${IXFORGE_AUTO_MIGRATE:-true}" = "true" ]; then
    echo "entrypoint: aplicando migraciones (IXFORGE_AUTO_MIGRATE=true)"
    uv run ixforge upgrade
else
    echo "entrypoint: migraciones salteadas (IXFORGE_AUTO_MIGRATE=false)"
fi

exec uv run ixforge "$@"
