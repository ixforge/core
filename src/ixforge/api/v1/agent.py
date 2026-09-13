"""Agent communication endpoints: config polling, status reporting, heartbeats."""

import contextlib
import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ixforge.api.deps import DBSession
from ixforge.database import tenant_context as _tenant_context
from ixforge.enums import BGPOperState, PrefixEventType
from ixforge.exceptions import ForbiddenError, NotFoundError, UnauthorizedError
from ixforge.metrics import (
    bgp_session_prefixes_exported,
    bgp_session_prefixes_imported,
    bgp_sessions_active,
)
from ixforge.models.api_key import APIKey
from ixforge.models.bgp_prefix import BGPPrefixEvent, BGPSessionPrefix
from ixforge.models.bgp_session import BGPSession
from ixforge.models.config import ConfigVersion
from ixforge.models.ip import IPAssignment, IPPool
from ixforge.models.member import Member
from ixforge.models.route_server import RouteServer
from ixforge.models.route_server_peer import RouteServerPeer
from ixforge.models.trunk import Trunk, TrunkVLAN
from ixforge.schemas.agent import (
    AgentConfigApplied,
    AgentConfigFailed,
    AgentConfigResponse,
    AgentHeartbeat,
    AgentHeartbeatResponse,
    AgentPrefixReport,
    AgentPrefixReportResponse,
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


async def _sesiones_por_peer(
    db: AsyncSession,
    route_server_id: uuid.UUID,
) -> dict[tuple[str, int], BGPSession]:
    """Las sesiones de un route server, indexadas por la IP del peer y familia

    El agente identifica una sesion por la IP del vecino, que no es una columna:
    sale de la IP asignada al trunk_vlan en el pool de esa familia. El DISTINCT
    ON evita duplicados cuando un trunk_vlan tiene varias IPs de la misma familia
    """
    ip_subq = (
        select(
            IPAssignment.trunk_vlan_id,
            IPAssignment.address,
            IPPool.af,
        )
        .join(IPPool, IPAssignment.pool_id == IPPool.id)
        .distinct(IPAssignment.trunk_vlan_id, IPPool.af)
        .order_by(IPAssignment.trunk_vlan_id, IPPool.af, IPAssignment.address)
        .subquery()
    )

    stmt = (
        select(BGPSession, ip_subq.c.address)
        .join(
            ip_subq,
            (BGPSession.trunk_vlan_id == ip_subq.c.trunk_vlan_id)
            & (BGPSession.af == ip_subq.c.af),
        )
        .where(BGPSession.route_server_id == route_server_id)
    )
    result = await db.execute(stmt)
    return {(str(addr), s.af): s for s, addr in result.all()}


def _publicar_conteo(
    *,
    route_server_id: uuid.UUID,
    peer_asn: int,
    af: int,
    imported: int | None,
    exported: int | None,
) -> None:
    """Publica el conteo de prefijos como metrica, o borra la serie si no hay

    Borrar y no publicar cero: el gauge se queda con el ultimo valor para
    siempre si nadie lo saca, asi que una sesion caida seguiria reportando los
    prefijos que tenia cuando estaba arriba. Sin serie el grafico dibuja un
    hueco, que es lo que realmente pasa
    """
    etiquetas = (str(route_server_id), str(peer_asn), str(af))
    for gauge, valor in (
        (bgp_session_prefixes_imported, imported),
        (bgp_session_prefixes_exported, exported),
    ):
        if valor is None:
            # KeyError si nunca tuvo serie, que es donde queremos que quede
            with contextlib.suppress(KeyError):
                gauge.remove(*etiquetas)
        else:
            gauge.labels(*etiquetas).set(valor)


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

    sessions_by_peer = await _sesiones_por_peer(db, route_server_id)

    peers_por_ip = {
        str(p.peer_ip): p
        for p in (
            await db.execute(
                select(RouteServerPeer).where(
                    RouteServerPeer.route_server_id == route_server_id
                )
            )
        ).scalars()
    }

    # Pre-load ASN mapping for event data
    stmt_asn = (
        select(TrunkVLAN.id, Member.asn)
        .join(Trunk, TrunkVLAN.trunk_id == Trunk.id)
        .join(Member, Trunk.member_id == Member.id)
        .where(TrunkVLAN.id.in_(
            select(BGPSession.trunk_vlan_id)
            .where(BGPSession.route_server_id == route_server_id)
        ))
    )
    asn_result = await db.execute(stmt_asn)
    asn_by_tv: dict[uuid.UUID, int] = {row[0]: row[1] for row in asn_result.all()}

    updated = 0
    unchanged = 0
    not_found = 0

    for report in body.sessions:
        session = sessions_by_peer.get((report.peer_ip, report.af))
        if session is None:
            # El agente reporta todos los protocolos de BIRD sin distinguir, asi
            # que aca tambien llegan los peers que no son de un miembro: el
            # upstream del IXP, los colectores. Antes se descartaban y por eso
            # figuraban siempre en estado desconocido
            peer = peers_por_ip.get(report.peer_ip)
            if peer is None:
                not_found += 1
                continue

            nuevo_estado = BGPOperState(report.oper_state)
            if peer.oper_state == nuevo_estado:
                unchanged += 1
            else:
                peer.oper_state = nuevo_estado
                updated += 1
            peer.prefixes_imported = report.prefixes_imported
            peer.prefixes_exported = report.prefixes_exported
            continue

        peer_asn = asn_by_tv.get(session.trunk_vlan_id, 0)

        # El conteo se guarda SIEMPRE, antes de mirar el estado: el caso normal
        # es una sesion que lleva dias arriba y cuyo unico dato que se mueve es
        # este. Si se escribiera despues del corte por "estado sin cambios", el
        # numero quedaria congelado en el primer reporte
        #
        # Se copia tal cual lo reportado, incluido el None: el conteo de una
        # sesion caida no se conserva, porque un numero viejo mostrado como
        # actual miente peor que un dato ausente
        session.prefixes_imported = report.prefixes_imported
        session.prefixes_exported = report.prefixes_exported
        _publicar_conteo(
            route_server_id=route_server_id,
            peer_asn=peer_asn,
            af=report.af,
            imported=report.prefixes_imported,
            exported=report.prefixes_exported,
        )

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
                    "peer_ip": report.peer_ip,
                    "peer_asn": peer_asn,
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
                    "peer_ip": report.peer_ip,
                    "peer_asn": peer_asn,
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
    config.apply_error = None
    config.apply_error_at = None

    await db.flush()


@agent_router.post(
    "/{route_server_id}/agent/config/failed",
    status_code=204,
)
async def report_agent_config_failed(
    route_server_id: uuid.UUID,
    body: AgentConfigFailed,
    db: DBSession,
    _agent_key: AgentKey,
) -> None:
    """Agent reports that a config could not be applied (e.g. bird -p failed).

    Stores the error on the matching config version so the portal can surface
    why the config is stuck as pending. Returns 404 if no matching version.

    Requires an API key with the ``agent:route_server`` scope linked to this
    route server.
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

    config.apply_error = body.error
    config.apply_error_at = datetime.now(UTC)

    await db.flush()


@agent_router.post(
    "/{route_server_id}/agent/prefixes",
    response_model=AgentPrefixReportResponse,
)
async def report_agent_prefixes(
    route_server_id: uuid.UUID,
    body: AgentPrefixReport,
    db: DBSession,
    _agent_key: AgentKey,
) -> AgentPrefixReportResponse:
    """El agente reporta que prefijos anuncia cada peer.

    Lo guardado es un espejo del ultimo reporte, no un acumulado: lo que el peer
    retiro se borra. El historial de que cambio vive en bgp_prefix_events, que
    se llena comparando este reporte con el anterior.

    Requires an API key with the ``agent:route_server`` scope linked
    to this route server.
    """
    rs = await db.get(RouteServer, route_server_id)
    if rs is None:
        raise NotFoundError("RouteServer", str(route_server_id))

    sessions_by_peer = await _sesiones_por_peer(db, route_server_id)

    sessions_updated = 0
    prefixes_added = 0
    prefixes_removed = 0
    ahora = datetime.now(UTC)

    for reporte in body.sessions:
        session = sessions_by_peer.get((reporte.peer_ip, reporte.af))
        if session is None:
            continue
        sessions_updated += 1

        guardados = {
            fila.prefix: fila
            for fila in (
                await db.execute(
                    select(BGPSessionPrefix).where(
                        BGPSessionPrefix.bgp_session_id == session.id
                    )
                )
            ).scalars()
        }
        reportados = {p.prefix: p for p in reporte.prefixes}

        for prefix, reportado in reportados.items():
            fila = guardados.get(prefix)
            if fila is None:
                db.add(BGPSessionPrefix(
                    ixp_id=rs.ixp_id,
                    bgp_session_id=session.id,
                    prefix=prefix,
                    as_path=reportado.as_path,
                    communities=reportado.communities,
                    first_seen_at=ahora,
                    last_seen_at=ahora,
                ))
                db.add(BGPPrefixEvent(
                    ixp_id=rs.ixp_id,
                    bgp_session_id=session.id,
                    prefix=prefix,
                    event_type=PrefixEventType.announced,
                    as_path=reportado.as_path,
                    communities=reportado.communities,
                    occurred_at=ahora,
                ))
                prefixes_added += 1
                continue

            # El prefijo sigue: solo deja rastro si cambio algo. Sin esto el
            # historial seria una fila de "sigue ahi" cada cinco minutos
            if fila.as_path != reportado.as_path or fila.communities != reportado.communities:
                db.add(BGPPrefixEvent(
                    ixp_id=rs.ixp_id,
                    bgp_session_id=session.id,
                    prefix=prefix,
                    event_type=PrefixEventType.updated,
                    as_path=reportado.as_path,
                    previous_as_path=fila.as_path,
                    communities=reportado.communities,
                    previous_communities=fila.communities,
                    occurred_at=ahora,
                ))
                fila.as_path = reportado.as_path
                fila.communities = reportado.communities
            fila.last_seen_at = ahora

        for prefix, fila in guardados.items():
            if prefix in reportados:
                continue
            db.add(BGPPrefixEvent(
                ixp_id=rs.ixp_id,
                bgp_session_id=session.id,
                prefix=prefix,
                event_type=PrefixEventType.withdrawn,
                as_path=fila.as_path,
                communities=fila.communities,
                occurred_at=ahora,
            ))
            await db.delete(fila)
            prefixes_removed += 1

    await db.flush()

    return AgentPrefixReportResponse(
        sessions_updated=sessions_updated,
        prefixes_added=prefixes_added,
        prefixes_removed=prefixes_removed,
    )
