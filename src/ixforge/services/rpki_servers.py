"""Servidores RTR para validacion RPKI."""

import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ixforge.enums import RPKITransport
from ixforge.exceptions import ConflictError, NotFoundError, ValidationError
from ixforge.models.route_server import RouteServer
from ixforge.models.rpki_server import RPKIServer
from ixforge.schemas.common import CursorPage, CursorParams
from ixforge.schemas.rpki_server import (
    RPKIServerCreate,
    RPKIServerRead,
    RPKIServerUpdate,
)
from ixforge.services.base import paginate


def _reject_unsupported_transport(transport: RPKITransport | None) -> None:
    """El generador solo emite TCP

    El transporte ssh necesita rutas de llaves que todavia no estan modeladas.
    Dejar que se configure produciria un config que no expresa lo pedido, y en
    silencio
    """
    if transport is RPKITransport.ssh:
        raise ValidationError(
            "el transporte ssh todavia no esta soportado por el generador, usa tcp"
        )


async def _assert_route_server(
    session: AsyncSession, ixp_id: uuid.UUID, route_server_id: uuid.UUID | None
) -> None:
    if route_server_id is None:
        return
    rs = await session.get(RouteServer, route_server_id)
    if rs is None or rs.ixp_id != ixp_id:
        raise NotFoundError("RouteServer", str(route_server_id))


async def _defer_affected(
    session: AsyncSession,
    ixp_id: uuid.UUID,
    route_server_id: uuid.UUID | None,
    triggered_by: str,
) -> None:
    """Regenera el route server apuntado, o todos los del IXP si aplica a todos"""
    from ixforge.tasks.config import defer_rs_config_regeneration

    if route_server_id is not None:
        await defer_rs_config_regeneration(route_server_id, triggered_by)
        return

    stmt = select(RouteServer.id).where(
        RouteServer.ixp_id == ixp_id, RouteServer.is_active.is_(True)
    )
    for (rs_id,) in (await session.execute(stmt)).all():
        await defer_rs_config_regeneration(rs_id, triggered_by)


async def list_servers(
    session: AsyncSession, ixp_id: uuid.UUID, params: CursorParams
) -> CursorPage[RPKIServerRead]:
    stmt = select(RPKIServer).where(RPKIServer.ixp_id == ixp_id)
    return await paginate(
        session,
        stmt,
        params,
        sort_column=RPKIServer.created_at,
        id_column=RPKIServer.id,
        schema=RPKIServerRead,
    )


async def get(
    session: AsyncSession, ixp_id: uuid.UUID, server_id: uuid.UUID
) -> RPKIServer:
    srv = await session.get(RPKIServer, server_id)
    if srv is None or srv.ixp_id != ixp_id:
        raise NotFoundError("RPKIServer", str(server_id))
    return srv


async def create(
    session: AsyncSession, ixp_id: uuid.UUID, data: RPKIServerCreate
) -> RPKIServer:
    _reject_unsupported_transport(data.transport)
    await _assert_route_server(session, ixp_id, data.route_server_id)

    srv = RPKIServer(ixp_id=ixp_id, **data.model_dump())
    session.add(srv)
    try:
        await session.flush()
    except IntegrityError as exc:
        raise ConflictError(
            f"Ya existe un servidor RPKI llamado {data.name} en este IXP"
        ) from exc

    await _defer_affected(session, ixp_id, data.route_server_id, "rpki_server.created")
    return srv


async def update(
    session: AsyncSession,
    ixp_id: uuid.UUID,
    server_id: uuid.UUID,
    data: RPKIServerUpdate,
) -> RPKIServer:
    _reject_unsupported_transport(data.transport)
    srv = await get(session, ixp_id, server_id)
    fields = data.model_dump(exclude_unset=True)
    if "route_server_id" in fields:
        await _assert_route_server(session, ixp_id, fields["route_server_id"])

    for field, value in fields.items():
        setattr(srv, field, value)
    try:
        await session.flush()
    except IntegrityError as exc:
        raise ConflictError("El servidor RPKI no se pudo actualizar") from exc
    await session.refresh(srv)

    await _defer_affected(session, ixp_id, srv.route_server_id, "rpki_server.updated")
    return srv


async def delete(
    session: AsyncSession, ixp_id: uuid.UUID, server_id: uuid.UUID
) -> None:
    srv = await get(session, ixp_id, server_id)
    route_server_id = srv.route_server_id
    await session.delete(srv)
    await session.flush()

    await _defer_affected(session, ixp_id, route_server_id, "rpki_server.deleted")
