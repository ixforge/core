"""Prefijos que anuncia un miembro, y su historial.

Los escribe el agente por sesion BGP; aca salen por miembro, que es como los
consume la ficha publica
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Query

from ixforge.api.deps import CurrentUser, DBSession, IXPId
from ixforge.models.member import Member
from ixforge.schemas.prefijos_bgp import EventoDePrefijoRead, PrefijoAnunciadoRead
from ixforge.services import members as members_svc
from ixforge.services import prefijos_bgp as svc

prefijos_bgp_router = APIRouter(prefix="/members/{member_id}", tags=["member-prefixes"])


@prefijos_bgp_router.get("/prefixes")
async def listar_prefijos(
    member_id: uuid.UUID,
    db: DBSession,
    ixp_id: IXPId,
    _user: CurrentUser,
    prefix: Annotated[str | None, Query(max_length=43)] = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 100,
) -> dict[str, list[PrefijoAnunciadoRead]]:
    """Los prefijos que el miembro esta anunciando ahora"""
    await _verificar_miembro(db, ixp_id, member_id)
    filas = await svc.prefijos(db, ixp_id, member_id, prefix, limit)
    return {"items": [PrefijoAnunciadoRead(**f) for f in filas]}


@prefijos_bgp_router.get("/prefix-events")
async def listar_eventos(
    member_id: uuid.UUID,
    db: DBSession,
    ixp_id: IXPId,
    _user: CurrentUser,
    prefix: Annotated[str | None, Query(max_length=43)] = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 100,
) -> dict[str, list[EventoDePrefijoRead]]:
    """Que prefijos aparecieron, desaparecieron o cambiaron de camino"""
    await _verificar_miembro(db, ixp_id, member_id)
    filas = await svc.eventos(db, ixp_id, member_id, prefix, limit)
    return {"items": [EventoDePrefijoRead(**f) for f in filas]}


async def _verificar_miembro(db: DBSession, ixp_id: uuid.UUID, member_id: uuid.UUID) -> Member:
    """Un miembro que no existe da 404 y no una lista vacia

    La lista vacia es una respuesta legitima de un miembro que no anuncia nada,
    asi que confundirla con un id inexistente esconde el error de quien llama
    """
    return await members_svc.get(db, ixp_id, member_id)
