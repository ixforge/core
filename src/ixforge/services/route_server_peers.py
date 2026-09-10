"""Peers de route server que no pertenecen a un miembro: upstream y colectores."""

import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ixforge.exceptions import ConflictError, NotFoundError
from ixforge.models.route_server import RouteServer
from ixforge.models.route_server_peer import RouteServerPeer
from ixforge.schemas.common import CursorPage, CursorParams
from ixforge.schemas.route_server_peer import (
    RouteServerPeerCreate,
    RouteServerPeerRead,
    RouteServerPeerUpdate,
)
from ixforge.services.base import paginate


async def _assert_route_server(
    session: AsyncSession, ixp_id: uuid.UUID, route_server_id: uuid.UUID
) -> RouteServer:
    """El route server tiene que ser del IXP del request antes de tocar nada"""
    rs = await session.get(RouteServer, route_server_id)
    if rs is None or rs.ixp_id != ixp_id:
        raise NotFoundError("RouteServer", str(route_server_id))
    return rs


async def list_peers(
    session: AsyncSession,
    ixp_id: uuid.UUID,
    route_server_id: uuid.UUID,
    params: CursorParams,
) -> CursorPage[RouteServerPeerRead]:
    await _assert_route_server(session, ixp_id, route_server_id)
    stmt = select(RouteServerPeer).where(
        RouteServerPeer.ixp_id == ixp_id,
        RouteServerPeer.route_server_id == route_server_id,
    )
    return await paginate(
        session,
        stmt,
        params,
        sort_column=RouteServerPeer.created_at,
        id_column=RouteServerPeer.id,
        schema=RouteServerPeerRead,
    )


async def get(
    session: AsyncSession,
    ixp_id: uuid.UUID,
    route_server_id: uuid.UUID,
    peer_id: uuid.UUID,
) -> RouteServerPeer:
    await _assert_route_server(session, ixp_id, route_server_id)
    peer = await session.get(RouteServerPeer, peer_id)
    if peer is None or peer.ixp_id != ixp_id or peer.route_server_id != route_server_id:
        raise NotFoundError("RouteServerPeer", str(peer_id))
    return peer


async def create(
    session: AsyncSession,
    ixp_id: uuid.UUID,
    route_server_id: uuid.UUID,
    data: RouteServerPeerCreate,
) -> RouteServerPeer:
    await _assert_route_server(session, ixp_id, route_server_id)
    peer = RouteServerPeer(
        ixp_id=ixp_id,
        route_server_id=route_server_id,
        **data.model_dump(),
    )
    session.add(peer)
    try:
        await session.flush()
    except IntegrityError as exc:
        raise ConflictError(
            f"Ya existe un peer con la IP {data.peer_ip} en este route server"
        ) from exc

    from ixforge.tasks.config import defer_rs_config_regeneration

    await defer_rs_config_regeneration(route_server_id, "route_server_peer.created")
    return peer


async def update(
    session: AsyncSession,
    ixp_id: uuid.UUID,
    route_server_id: uuid.UUID,
    peer_id: uuid.UUID,
    data: RouteServerPeerUpdate,
) -> RouteServerPeer:
    peer = await get(session, ixp_id, route_server_id, peer_id)
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(peer, field, value)
    try:
        await session.flush()
    except IntegrityError as exc:
        raise ConflictError("El peer no se pudo actualizar por un conflicto") from exc
    # updated_at tiene onupdate: sin refresh, serializar el modelo intenta IO
    # lazy fuera del contexto async y revienta con MissingGreenlet
    await session.refresh(peer)

    from ixforge.tasks.config import defer_rs_config_regeneration

    await defer_rs_config_regeneration(route_server_id, "route_server_peer.updated")
    return peer


async def delete(
    session: AsyncSession,
    ixp_id: uuid.UUID,
    route_server_id: uuid.UUID,
    peer_id: uuid.UUID,
) -> None:
    peer = await get(session, ixp_id, route_server_id, peer_id)
    await session.delete(peer)
    await session.flush()

    from ixforge.tasks.config import defer_rs_config_regeneration

    await defer_rs_config_regeneration(route_server_id, "route_server_peer.deleted")
