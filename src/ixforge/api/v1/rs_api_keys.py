"""Route server agent API key endpoints (admin only)."""

import uuid
from typing import Any

from fastapi import APIRouter, Response
from sqlalchemy import select

from ixforge.api.deps import AdminUser, DBSession, IXPId
from ixforge.exceptions import NotFoundError
from ixforge.models.api_key import APIKey
from ixforge.models.route_server import RouteServer
from ixforge.schemas.auth import APIKeyCreateResponse, APIKeyRead, RSAPIKeyCreate
from ixforge.services.auth import generate_api_key

rs_api_keys_router = APIRouter(prefix="/route-servers", tags=["route-servers"])


async def _get_rs(db: DBSession, ixp_id: uuid.UUID, rs_id: uuid.UUID) -> RouteServer:
    """Get a route server within the tenant or raise NotFoundError"""
    rs = await db.get(RouteServer, rs_id)
    if rs is None or rs.ixp_id != ixp_id:
        raise NotFoundError("RouteServer", str(rs_id))
    return rs


@rs_api_keys_router.post(
    "/{rs_id}/api-keys", response_model=APIKeyCreateResponse, status_code=201,
)
async def create_rs_api_key(
    rs_id: uuid.UUID, body: RSAPIKeyCreate, db: DBSession, ixp_id: IXPId, _admin: AdminUser,
) -> dict[str, Any]:
    """Create an agent API key bound to a route server.

    The raw key is returned only once at creation time. Agent endpoints
    only accept keys bound to the route server they target
    """
    await _get_rs(db, ixp_id, rs_id)

    raw_key, key_hash, prefix = generate_api_key()
    api_key = APIKey(
        key_hash=key_hash,
        prefix=prefix,
        name=body.name,
        scopes=["agent:route_server"],
        route_server_id=rs_id,
    )
    db.add(api_key)
    await db.flush()

    return {
        "id": api_key.id,
        "prefix": api_key.prefix,
        "name": api_key.name,
        "scopes": api_key.scopes,
        "is_active": api_key.is_active,
        "last_used_at": api_key.last_used_at,
        "created_at": api_key.created_at,
        "raw_key": raw_key,
    }


@rs_api_keys_router.get("/{rs_id}/api-keys", response_model=list[APIKeyRead])
async def list_rs_api_keys(
    rs_id: uuid.UUID, db: DBSession, ixp_id: IXPId, _admin: AdminUser,
) -> list[APIKey]:
    """List agent API keys for a route server (without raw keys)."""
    await _get_rs(db, ixp_id, rs_id)
    result = await db.execute(
        select(APIKey).where(APIKey.route_server_id == rs_id).order_by(APIKey.created_at)
    )
    return list(result.scalars().all())


@rs_api_keys_router.delete("/{rs_id}/api-keys/{key_id}", status_code=204)
async def revoke_rs_api_key(
    rs_id: uuid.UUID, key_id: uuid.UUID, db: DBSession, ixp_id: IXPId, _admin: AdminUser,
) -> Response:
    """Revoke an agent API key."""
    await _get_rs(db, ixp_id, rs_id)
    api_key = await db.get(APIKey, key_id)
    if api_key is None or api_key.route_server_id != rs_id:
        raise NotFoundError("APIKey", str(key_id))
    await db.delete(api_key)
    await db.flush()
    return Response(status_code=204)
