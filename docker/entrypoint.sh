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

# El portal no migra: es una UI que habla con la API por HTTP y no tiene, ni
# debe tener, credenciales de base de datos. Darselas para que pueda migrar
# seria ampliar su superficie por comodidad
case "$1" in
    ui) migrar=no ;;
    *)  migrar="${IXFORGE_AUTO_MIGRATE:-true}" ;;
esac

if [ "$migrar" = "true" ]; then
    echo "entrypoint: aplicando migraciones (IXFORGE_AUTO_MIGRATE=true)"
    uv run ixforge upgrade
else
    echo "entrypoint: sin migrar (comando '$1')"
fi

exec uv run ixforge "$@"
