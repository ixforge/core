"""Config generation and versioning endpoints."""

import uuid

from fastapi import APIRouter, Query
from sqlalchemy import select

from ixforge.api.deps import AdminUser, DBSession
from ixforge.exceptions import NotFoundError
from ixforge.models.config import ConfigVersion
from ixforge.models.route_server import RouteServer
from ixforge.schemas.common import CursorPage, decode_cursor, encode_cursor
from ixforge.schemas.config import ConfigDiff, ConfigVersionRead
from ixforge.services.config_generation import generate_config, get_diff

config_router = APIRouter(
    prefix="/route-servers/{route_server_id}/config",
    tags=["config"],
)


async def _ensure_route_server_exists(db: DBSession, route_server_id: uuid.UUID) -> RouteServer:
    """Fetch a route server or raise NotFoundError."""
    rs = await db.get(RouteServer, route_server_id)
    if rs is None:
        raise NotFoundError("RouteServer", str(route_server_id))
    return rs


@config_router.post("/generate", response_model=ConfigVersionRead, status_code=201)
async def trigger_generation(
    route_server_id: uuid.UUID,
    db: DBSession,
    admin: AdminUser,
) -> ConfigVersion:
    await _ensure_route_server_exists(db, route_server_id)
    return await generate_config(db, route_server_id, generated_by_id=admin.id)


@config_router.get("/history", response_model=CursorPage[ConfigVersionRead])
async def list_config_history(
    route_server_id: uuid.UUID,
    db: DBSession,
    _admin: AdminUser,
    cursor: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
) -> CursorPage[ConfigVersionRead]:
    await _ensure_route_server_exists(db, route_server_id)

    stmt = (
        select(ConfigVersion)
        .where(ConfigVersion.route_server_id == route_server_id)
        .order_by(ConfigVersion.generated_at.desc(), ConfigVersion.id.desc())
    )

    if cursor is not None:
        cursor_value, cursor_id = decode_cursor(cursor)
        stmt = stmt.where(
            (ConfigVersion.generated_at < cursor_value)
            | ((ConfigVersion.generated_at == cursor_value) & (ConfigVersion.id < cursor_id))
        )

    stmt = stmt.limit(limit + 1)
    result = await db.execute(stmt)
    rows = list(result.scalars().all())

    has_more = len(rows) > limit
    items = rows[:limit]

    next_cursor = None
    if has_more and items:
        last = items[-1]
        next_cursor = encode_cursor(last.generated_at.isoformat(), last.id)

    return CursorPage[ConfigVersionRead](
        items=[ConfigVersionRead.model_validate(item) for item in items],
        next_cursor=next_cursor,
        has_more=has_more,
    )


@config_router.get("/current", response_model=ConfigVersionRead)
async def get_current_config(
    route_server_id: uuid.UUID,
    db: DBSession,
    _admin: AdminUser,
) -> ConfigVersion:
    await _ensure_route_server_exists(db, route_server_id)

    stmt = (
        select(ConfigVersion)
        .where(ConfigVersion.route_server_id == route_server_id)
        .order_by(ConfigVersion.generated_at.desc())
        .limit(1)
    )
    result = await db.execute(stmt)
    config_version = result.scalar_one_or_none()

    if config_version is None:
        raise NotFoundError("ConfigVersion", f"route_server={route_server_id}")
    return config_version


@config_router.get("/diff", response_model=ConfigDiff)
async def diff_config_versions(
    route_server_id: uuid.UUID,
    db: DBSession,
    _admin: AdminUser,
    from_version: uuid.UUID = Query(alias="from"),
    to_version: uuid.UUID = Query(alias="to"),
) -> ConfigDiff:
    await _ensure_route_server_exists(db, route_server_id)

    diff_text = await get_diff(db, from_version, to_version)

    from_config = await db.get(ConfigVersion, from_version)
    to_config = await db.get(ConfigVersion, to_version)

    return ConfigDiff(
        current_hash=from_config.config_hash if from_config else None,
        new_hash=to_config.config_hash if to_config else "",
        diff=diff_text,
    )
