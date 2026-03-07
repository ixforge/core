"""Agent communication endpoints: config polling, status reporting, heartbeats."""

import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ixforge.api.deps import DBSession
from ixforge.database import tenant_context as _tenant_context
from ixforge.enums import BGPOperState
from ixforge.exceptions import ForbiddenError, NotFoundError, UnauthorizedError
from ixforge.metrics import bgp_sessions_active
from ixforge.models.api_key import APIKey
from ixforge.models.bgp_session import BGPSession
from ixforge.models.config import ConfigVersion
from ixforge.models.route_server import RouteServer
from ixforge.schemas.agent import (
    AgentConfigApplied,
    AgentConfigResponse,
    AgentHeartbeat,
    AgentHeartbeatResponse,
    AgentStatusReport,
    AgentStatusResponse,
)
from ixforge.services.auth import hash_api_key
from ixforge.services.events import create_event

# Minimum agent version that is considered acceptable
# Agents older than this will receive an upgrade header
MINIMUM_AGENT_VERSION = "0.1.0"

agent_router = APIRouter(prefix="/route-servers", tags=["agent"])


async def _resolve_agent_api_key(
    db: AsyncSession,
    route_server_id: uuid.UUID,
    x_api_key: str | None,
) -> APIKey:
    """Validate an agent API key and ensure it is scoped to the given route server."""
    if x_api_key is None:
        raise UnauthorizedError("API key required for agent endpoints")

    key_hash = hash_api_key(x_api_key)
    stmt = select(APIKey).where(APIKey.key_hash == key_hash, APIKey.is_active.is_(True))
    result = await db.execute(stmt)
    api_key = result.scalar_one_or_none()

    if api_key is None:
        raise UnauthorizedError("Invalid API key")

    if "agent:route_server" not in api_key.scopes:
        raise ForbiddenError("API key missing 'agent:route_server' scope")

    if api_key.route_server_id != route_server_id:
        raise ForbiddenError("API key is not authorized for this route server")

    # Update last_used_at
    api_key.last_used_at = datetime.now(UTC)

    return api_key


async def _get_agent_key(
    db: DBSession,
    route_server_id: uuid.UUID,
    x_api_key: Annotated[str | None, Header()] = None,
) -> APIKey:
    """FastAPI dependency: resolve and validate agent API key."""
    api_key = await _resolve_agent_api_key(db, route_server_id, x_api_key)
    rs = await db.get(RouteServer, route_server_id)
    if rs is None:
        raise NotFoundError("RouteServer", str(route_server_id))
    _tenant_context.set(rs.ixp_id)
    return api_key


AgentKey = Annotated[APIKey, Depends(_get_agent_key)]


@agent_router.get(
    "/{route_server_id}/agent/config",
    response_model=AgentConfigResponse,
)
async def get_agent_config(
    route_server_id: uuid.UUID,
    db: DBSession,
    _agent_key: AgentKey,
) -> AgentConfigResponse:
    """Return the latest config for a route server.

    The agent polls this endpoint, compares the config hash with its
    local copy, and downloads the new configuration if the hash changed.

    Requires an API key with the ``agent:route_server`` scope linked
    to this route server.
    """
    # Verify route server exists
    rs = await db.get(RouteServer, route_server_id)
    if rs is None:
        raise NotFoundError("RouteServer", str(route_server_id))

    # Get the latest config version for this route server
    stmt = (
        select(ConfigVersion)
        .where(ConfigVersion.route_server_id == route_server_id)
        .order_by(ConfigVersion.generated_at.desc())
        .limit(1)
    )
    result = await db.execute(stmt)
    config = result.scalar_one_or_none()

    if config is None:
        raise NotFoundError("ConfigVersion", f"route_server_id={route_server_id}")

    return AgentConfigResponse(
        config_hash=config.config_hash,
        content=config.content,
        generated_at=config.generated_at,
    )


@agent_router.post(
    "/{route_server_id}/agent/status",
    response_model=AgentStatusResponse,
)
async def report_agent_status(
    route_server_id: uuid.UUID,
    body: AgentStatusReport,
    db: DBSession,
    _agent_key: AgentKey,
) -> AgentStatusResponse:
    """Agent reports BGP session operational states.

    Performs a bulk update of ``oper_state`` on BGP sessions matched by
    ``peer_ip``. Emits events for state transitions (up->down, down->up).
    Updates Prometheus gauges for active BGP sessions.

    Requires an API key with the ``agent:route_server`` scope linked
    to this route server.
    """
    # Verify route server exists and get its ixp_id for events
    rs = await db.get(RouteServer, route_server_id)
    if rs is None:
        raise NotFoundError("RouteServer", str(route_server_id))

    # Load all BGP sessions for this route server, keyed by (peer_ip, af)
    stmt = select(BGPSession).where(BGPSession.route_server_id == route_server_id)
    result = await db.execute(stmt)
    sessions_by_peer: dict[tuple[str, int], BGPSession] = {
        (s.peer_ip, s.af): s for s in result.scalars().all()
    }

    updated = 0
    unchanged = 0
    not_found = 0

    for report in body.sessions:
        session = sessions_by_peer.get((report.peer_ip, report.af))
        if session is None:
            not_found += 1
            continue

        old_state = session.oper_state
        new_state = BGPOperState(report.oper_state)

        if old_state == new_state:
            unchanged += 1
            continue

        session.oper_state = new_state
        updated += 1

        # Emit events for meaningful state transitions
        if old_state == BGPOperState.up and new_state == BGPOperState.down:
            await create_event(
                db,
                ixp_id=rs.ixp_id,
                event_type="bgp_session.down",
                actor_id=None,
                resource_type="bgp_session",
                resource_id=session.id,
                data={
                    "peer_ip": session.peer_ip,
                    "peer_asn": session.peer_asn,
                    "route_server_id": str(route_server_id),
                    "previous_state": old_state,
                    "new_state": new_state,
                },
            )
        elif (
            old_state in (BGPOperState.down, BGPOperState.unknown) and new_state == BGPOperState.up
        ):
            await create_event(
                db,
                ixp_id=rs.ixp_id,
                event_type="bgp_session.up",
                actor_id=None,
                resource_type="bgp_session",
                resource_id=session.id,
                data={
                    "peer_ip": session.peer_ip,
                    "peer_asn": session.peer_asn,
                    "route_server_id": str(route_server_id),
                    "previous_state": old_state,
                    "new_state": new_state,
                },
            )

    # Update Prometheus gauge: count all sessions currently "up" for this RS
    active_count = sum(1 for s in sessions_by_peer.values() if s.oper_state == BGPOperState.up)
    bgp_sessions_active.labels(route_server_id=str(route_server_id)).set(active_count)

    await db.flush()

    return AgentStatusResponse(
        updated=updated,
        unchanged=unchanged,
        not_found=not_found,
    )


@agent_router.post(
    "/{route_server_id}/agent/heartbeat",
    response_model=AgentHeartbeatResponse,
)
async def report_agent_heartbeat(
    route_server_id: uuid.UUID,
    body: AgentHeartbeat,
    db: DBSession,
    _agent_key: AgentKey,
    response: Response,
) -> AgentHeartbeatResponse:
    """Agent reports its health and metadata.

    Updates ``last_heartbeat_at`` and ``agent_version`` on the route server.
    Returns an ``X-IXForge-Agent-Upgrade`` header if the reported version
    is older than the minimum supported version.

    Requires an API key with the ``agent:route_server`` scope linked
    to this route server.
    """
    rs = await db.get(RouteServer, route_server_id)
    if rs is None:
        raise NotFoundError("RouteServer", str(route_server_id))

    # Update route server heartbeat fields
    rs.last_heartbeat_at = datetime.now(UTC)
    rs.agent_version = body.version

    # Check if config hash matches the latest config
    stmt = (
        select(ConfigVersion.config_hash)
        .where(ConfigVersion.route_server_id == route_server_id)
        .order_by(ConfigVersion.generated_at.desc())
        .limit(1)
    )
    result = await db.execute(stmt)
    latest_hash = result.scalar_one_or_none()

    config_hash_match = latest_hash is not None and latest_hash == body.current_config_hash

    # Check if agent version is too old and set upgrade header
    try:
        agent_ver = tuple(int(x) for x in body.version.split("."))
        min_ver = tuple(int(x) for x in MINIMUM_AGENT_VERSION.split("."))
        if agent_ver < min_ver:
            response.headers["X-IXForge-Agent-Upgrade"] = MINIMUM_AGENT_VERSION
    except (ValueError, TypeError):
        # If version string cannot be parsed, suggest upgrade
        response.headers["X-IXForge-Agent-Upgrade"] = MINIMUM_AGENT_VERSION

    await db.flush()

    return AgentHeartbeatResponse(
        acknowledged=True,
        config_hash_match=config_hash_match,
    )


@agent_router.post(
    "/{route_server_id}/agent/config/applied",
    status_code=204,
)
async def confirm_agent_config_applied(
    route_server_id: uuid.UUID,
    body: AgentConfigApplied,
    db: DBSession,
    _agent_key: AgentKey,
) -> None:
    """Agent confirms that a configuration was successfully applied.

    Updates ``applied_at`` on the matching config version.
    Returns 404 if no matching config version is found.

    Requires an API key with the ``agent:route_server`` scope linked
    to this route server.
    """
    rs = await db.get(RouteServer, route_server_id)
    if rs is None:
        raise NotFoundError("RouteServer", str(route_server_id))

    stmt = (
        select(ConfigVersion)
        .where(
            ConfigVersion.route_server_id == route_server_id,
            ConfigVersion.config_hash == body.config_hash,
        )
        .order_by(ConfigVersion.generated_at.desc())
        .limit(1)
    )
    result = await db.execute(stmt)
    config = result.scalar_one_or_none()

    if config is None:
        raise NotFoundError("ConfigVersion", f"config_hash={body.config_hash}")

    if config.applied_at is None:
        config.applied_at = datetime.now(UTC)

    await db.flush()
