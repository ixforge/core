"""BGP session service: CRUD, admin state management."""

import uuid
from typing import Any, cast

from sqlalchemy import Select, asc, literal, nulls_last, select, tuple_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ixforge.enums import BGPAdminState, BGPOperState, TrunkState
from ixforge.exceptions import ConflictError, NotFoundError, ValidationError
from ixforge.models.bgp_session import BGPSession
from ixforge.models.ip import IPAssignment, IPPool
from ixforge.models.member import Member
from ixforge.models.route_server import RouteServer
from ixforge.models.trunk import Trunk, TrunkVLAN
from ixforge.schemas.bgp_session import BGPSessionCreate, BGPSessionRead
from ixforge.schemas.common import CursorPage, CursorParams, decode_cursor, encode_cursor

_VALID_ADMIN_VALUES = {s.value for s in BGPAdminState}


async def _resolve_peer_info(
    session: AsyncSession,
    trunk_vlan_id: uuid.UUID,
    af: int,
) -> tuple[str, int]:
    """Resolve peer_ip from IPAssignment and peer_asn from Member"""
    # peer_ip: join IPAssignment -> IPPool where pool.af == af
    stmt_ip = (
        select(IPAssignment.address)
        .join(IPPool, IPAssignment.pool_id == IPPool.id)
        .where(IPAssignment.trunk_vlan_id == trunk_vlan_id, IPPool.af == af)
        .order_by(IPAssignment.address)
        .limit(1)
    )
    peer_ip = await session.scalar(stmt_ip)
    if peer_ip is None:
        raise ValidationError(
            f"No IPv{af} address assigned to this trunk VLAN. "
            "Assign an IP before creating a BGP session"
        )
    # peer_asn: join TrunkVLAN -> Trunk -> Member
    stmt_asn = (
        select(Member.asn)
        .join(Trunk, Member.id == Trunk.member_id)
        .join(TrunkVLAN, Trunk.id == TrunkVLAN.trunk_id)
        .where(TrunkVLAN.id == trunk_vlan_id)
    )
    peer_asn = await session.scalar(stmt_asn)
    if peer_asn is None:
        raise ValidationError("Could not resolve member ASN for this trunk VLAN")
    return str(peer_ip), peer_asn


async def to_read(session: AsyncSession, bgp: BGPSession) -> dict[str, Any]:
    """Build BGPSessionRead dict with computed peer_ip and peer_asn"""
    try:
        peer_ip, peer_asn = await _resolve_peer_info(session, bgp.trunk_vlan_id, bgp.af)
    except ValidationError:
        peer_ip = ""
        peer_asn = 0
    return {
        "id": bgp.id,
        "route_server_id": bgp.route_server_id,
        "trunk_vlan_id": bgp.trunk_vlan_id,
        "peer_ip": peer_ip,
        "peer_asn": peer_asn,
        "admin_state": bgp.admin_state,
        "oper_state": bgp.oper_state,
        "af": bgp.af,
        "max_prefixes": bgp.max_prefixes,
        "created_at": bgp.created_at,
        "updated_at": bgp.updated_at,
    }


async def _paginate_with_peers(
    session: AsyncSession,
    stmt: Select[tuple[Any]],
    params: CursorParams,
) -> CursorPage[BGPSessionRead]:
    """Paginate BGP sessions and enrich with computed peer_ip/peer_asn"""
    sort_column = BGPSession.created_at
    id_column = BGPSession.id

    stmt = stmt.order_by(nulls_last(asc(sort_column)), asc(id_column))

    if params.cursor is not None:
        cursor_value, cursor_id = decode_cursor(params.cursor)
        stmt = stmt.where(
            tuple_(sort_column, id_column) > tuple_(literal(cursor_value), literal(cursor_id))
        )

    stmt = stmt.limit(params.limit + 1)

    result = await session.execute(stmt)
    rows = list(result.scalars().all())

    has_more = len(rows) > params.limit
    if has_more:
        rows = rows[: params.limit]

    if not rows:
        return CursorPage(items=[], next_cursor=None, has_more=False)

    # Batch-resolve peer info to avoid N+1 queries
    tv_ids = list({row.trunk_vlan_id for row in rows})

    # Bulk query: IP addresses per trunk_vlan + AF
    stmt_ips = (
        select(IPAssignment.trunk_vlan_id, IPPool.af, IPAssignment.address)
        .join(IPPool, IPAssignment.pool_id == IPPool.id)
        .where(IPAssignment.trunk_vlan_id.in_(tv_ids))
    )
    ip_result = await session.execute(stmt_ips)
    ip_lookup: dict[tuple[uuid.UUID, int], str] = {}
    for tv_id, af, addr in ip_result.all():
        ip_lookup.setdefault((tv_id, af), str(addr))

    # Bulk query: ASN per trunk_vlan
    stmt_asns = (
        select(TrunkVLAN.id, Member.asn)
        .join(Trunk, TrunkVLAN.trunk_id == Trunk.id)
        .join(Member, Trunk.member_id == Member.id)
        .where(TrunkVLAN.id.in_(tv_ids))
    )
    asn_result = await session.execute(stmt_asns)
    asn_lookup: dict[uuid.UUID, int] = {tv_id: asn for tv_id, asn in asn_result.all()}

    items: list[BGPSessionRead] = []
    for row in rows:
        peer_ip = ip_lookup.get((row.trunk_vlan_id, row.af), "")
        peer_asn = asn_lookup.get(row.trunk_vlan_id, 0)
        d = {
            "id": row.id,
            "route_server_id": row.route_server_id,
            "trunk_vlan_id": row.trunk_vlan_id,
            "peer_ip": peer_ip,
            "peer_asn": peer_asn,
            "admin_state": row.admin_state,
            "oper_state": row.oper_state,
            "af": row.af,
            "max_prefixes": row.max_prefixes,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
        }
        items.append(BGPSessionRead.model_validate(d))

    next_cursor: str | None = None
    if has_more and rows:
        last = rows[-1]
        sort_val = str(getattr(last, sort_column.key))
        row_id = cast("uuid.UUID", getattr(last, id_column.key))
        next_cursor = encode_cursor(sort_val, row_id)

    return CursorPage(items=items, next_cursor=next_cursor, has_more=has_more)


async def create(
    session: AsyncSession,
    ixp_id: uuid.UUID,
    data: BGPSessionCreate,
) -> BGPSession:
    """Create a new BGP session."""
    rs = await session.get(RouteServer, data.route_server_id)
    if rs is None or rs.ixp_id != ixp_id:
        raise NotFoundError("RouteServer")

    trunk_vlan = await session.get(TrunkVLAN, data.trunk_vlan_id)
    if trunk_vlan is None or trunk_vlan.ixp_id != ixp_id:
        raise NotFoundError("TrunkVLAN")

    trunk = await session.get(Trunk, trunk_vlan.trunk_id)
    if trunk is None or trunk.state != TrunkState.active:
        raise ValidationError("Trunk must be active to create a BGP session")

    # Validate that IP and ASN can be resolved before creating
    await _resolve_peer_info(session, data.trunk_vlan_id, data.af)

    bgp_session = BGPSession(
        ixp_id=ixp_id,
        route_server_id=data.route_server_id,
        trunk_vlan_id=data.trunk_vlan_id,
        af=data.af,
        admin_state=BGPAdminState.up,
        oper_state=BGPOperState.unknown,
        max_prefixes=data.max_prefixes,
    )
    session.add(bgp_session)
    try:
        await session.flush()
    except IntegrityError:
        raise ConflictError(
            "BGP session already exists for this route server, connection, and address family"
        ) from None

    await session.refresh(bgp_session)

    from ixforge.tasks.config import defer_rs_config_regeneration

    await defer_rs_config_regeneration(data.route_server_id, "bgp_session.created")
    return bgp_session


async def get(session: AsyncSession, ixp_id: uuid.UUID, session_id: uuid.UUID) -> BGPSession:
    """Get a BGP session by id or raise NotFoundError."""
    bgp_session = await session.get(BGPSession, session_id)
    if bgp_session is None or bgp_session.ixp_id != ixp_id:
        raise NotFoundError("BGPSession", str(session_id))
    return bgp_session


async def list_sessions(
    session: AsyncSession,
    ixp_id: uuid.UUID,
    route_server_id: uuid.UUID,
    params: CursorParams,
) -> CursorPage[BGPSessionRead]:
    """List BGP sessions for a route server with cursor-based pagination."""
    stmt = select(BGPSession).where(
        BGPSession.route_server_id == route_server_id,
        BGPSession.ixp_id == ixp_id,
    )
    return await _paginate_with_peers(session, stmt, params)


async def list_sessions_for_member(
    session: AsyncSession,
    ixp_id: uuid.UUID,
    route_server_id: uuid.UUID,
    member_id: uuid.UUID | None,
    params: CursorParams,
) -> CursorPage[BGPSessionRead]:
    """List BGP sessions for a route server filtered by member's trunks."""
    stmt = (
        select(BGPSession)
        .join(TrunkVLAN, BGPSession.trunk_vlan_id == TrunkVLAN.id)
        .join(Trunk, TrunkVLAN.trunk_id == Trunk.id)
        .where(
            BGPSession.route_server_id == route_server_id,
            BGPSession.ixp_id == ixp_id,
            Trunk.member_id == member_id,
        )
    )
    return await _paginate_with_peers(session, stmt, params)


async def delete(
    session: AsyncSession,
    ixp_id: uuid.UUID,
    session_id: uuid.UUID,
) -> None:
    """Delete a BGP session."""
    bgp_session = await get(session, ixp_id, session_id)
    route_server_id = bgp_session.route_server_id
    await session.delete(bgp_session)
    await session.flush()

    from ixforge.tasks.config import defer_rs_config_regeneration

    await defer_rs_config_regeneration(route_server_id, "bgp_session.deleted")


async def update_admin_state(
    session: AsyncSession,
    ixp_id: uuid.UUID,
    session_id: uuid.UUID,
    admin_state: str,
) -> BGPSession:
    """Update the admin_state of a BGP session (up or down)."""
    if admin_state not in _VALID_ADMIN_VALUES:
        raise ValidationError(
            f"Invalid admin_state '{admin_state}': must be one of {sorted(_VALID_ADMIN_VALUES)}"
        )

    bgp_session = await get(session, ixp_id, session_id)
    bgp_session.admin_state = BGPAdminState(admin_state)
    await session.flush()
    await session.refresh(bgp_session)

    from ixforge.tasks.config import defer_rs_config_regeneration

    await defer_rs_config_regeneration(bgp_session.route_server_id, "bgp_session.admin_state_changed")
    return bgp_session
