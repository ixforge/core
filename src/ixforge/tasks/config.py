"""Config generation background tasks.

Tasks in this module are triggered when member or connection state changes
require BIRD configuration to be regenerated for affected route servers.
"""

import uuid

import structlog
from sqlalchemy import select

from ixforge.database import get_session_factory
from ixforge.models.bgp_session import BGPSession
from ixforge.models.connection import Connection
from ixforge.models.route_server import RouteServer
from ixforge.services.config_generation import generate_config
from ixforge.tasks.setup import app

logger = structlog.get_logger()


@app.task(name="generate_route_server_config", queue="config")
async def generate_route_server_config(
    route_server_id: str,
    triggered_by: str | None = None,
) -> dict[str, str]:
    """Regenerate BIRD config for a single route server.

    Parameters
    ----------
    route_server_id:
        UUID of the route server to regenerate config for.
    triggered_by:
        Optional description of what triggered this regeneration
        (e.g. ``"member.state_changed"``).

    Returns
    -------
    dict with ``route_server_id`` and ``config_version_id``.
    """
    rs_uuid = uuid.UUID(route_server_id)
    log = logger.bind(route_server_id=route_server_id, triggered_by=triggered_by)
    log.info("config_generation.started")

    session_factory = get_session_factory()
    async with session_factory() as session:
        try:
            rs = await session.get(RouteServer, rs_uuid)
            if rs is None:
                log.warning("config_generation.route_server_not_found")
                return {"route_server_id": route_server_id, "config_version_id": None}
            config_version = await generate_config(session, rs_uuid, ixp_id=rs.ixp_id)
            await session.commit()
            log.info(
                "config_generation.completed",
                config_version_id=str(config_version.id),
                config_hash=config_version.config_hash,
            )
            return {
                "route_server_id": route_server_id,
                "config_version_id": str(config_version.id),
            }
        except Exception:
            await session.rollback()
            log.exception("config_generation.failed")
            raise


@app.task(name="regenerate_configs_for_member", queue="config")
async def regenerate_configs_for_member(
    member_id: str,
    triggered_by: str | None = None,
) -> list[dict[str, str]]:
    """Regenerate config for all route servers that have sessions with a member.

    Looks up all route servers that have BGP sessions associated with
    connections belonging to the given member, then queues individual
    config generation tasks for each.

    Parameters
    ----------
    member_id:
        UUID of the member whose state changed.
    triggered_by:
        Optional description of the triggering event.

    Returns
    -------
    List of dicts with ``route_server_id`` for each queued generation.
    """
    member_uuid = uuid.UUID(member_id)
    log = logger.bind(member_id=member_id, triggered_by=triggered_by)
    log.info("regenerate_configs_for_member.started")

    session_factory = get_session_factory()
    async with session_factory() as session:
        # Find all distinct route servers that have BGP sessions linked to
        # connections owned by this member
        stmt = (
            select(RouteServer.id)
            .join(BGPSession, BGPSession.route_server_id == RouteServer.id)
            .join(Connection, BGPSession.connection_id == Connection.id)
            .where(Connection.member_id == member_uuid)
            .distinct()
        )
        result = await session.execute(stmt)
        rs_ids = [row[0] for row in result.all()]

    log.info("regenerate_configs_for_member.found_route_servers", count=len(rs_ids))

    results = []
    for rs_id in rs_ids:
        await generate_route_server_config.defer_async(
            route_server_id=str(rs_id),
            triggered_by=triggered_by,
        )
        results.append({"route_server_id": str(rs_id)})

    return results


@app.task(name="regenerate_configs_for_connection", queue="config")
async def regenerate_configs_for_connection(
    connection_id: str,
    triggered_by: str | None = None,
) -> list[dict[str, str]]:
    """Regenerate config for all route servers that have sessions on a connection.

    Parameters
    ----------
    connection_id:
        UUID of the connection whose state changed.
    triggered_by:
        Optional description of the triggering event.

    Returns
    -------
    List of dicts with ``route_server_id`` for each queued generation.
    """
    conn_uuid = uuid.UUID(connection_id)
    log = logger.bind(connection_id=connection_id, triggered_by=triggered_by)
    log.info("regenerate_configs_for_connection.started")

    session_factory = get_session_factory()
    async with session_factory() as session:
        stmt = (
            select(BGPSession.route_server_id)
            .where(BGPSession.connection_id == conn_uuid)
            .distinct()
        )
        result = await session.execute(stmt)
        rs_ids = [row[0] for row in result.all()]

    log.info("regenerate_configs_for_connection.found_route_servers", count=len(rs_ids))

    results = []
    for rs_id in rs_ids:
        await generate_route_server_config.defer_async(
            route_server_id=str(rs_id),
            triggered_by=triggered_by,
        )
        results.append({"route_server_id": str(rs_id)})

    return results
