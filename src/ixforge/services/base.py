"""Base service utilities: cursor-based pagination helper."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from sqlalchemy import Select, asc, literal, nulls_last, tuple_

from ixforge.schemas.common import CursorPage, CursorParams, decode_cursor, encode_cursor

if TYPE_CHECKING:
    import uuid

    from pydantic import BaseModel
    from sqlalchemy.ext.asyncio import AsyncSession


async def paginate[T: BaseModel](
    session: AsyncSession,
    stmt: Select[tuple[Any]],
    params: CursorParams,
    sort_column: Any,
    id_column: Any,
    schema: type[T],
) -> CursorPage[T]:
    """Apply cursor-based keyset pagination to a SELECT statement.

    The cursor encodes the sort_column value and the row id, enabling
    deterministic forward pagination without OFFSET.  Rows are ordered by
    (sort_column ASC, id_column ASC).
    """
    stmt = stmt.order_by(nulls_last(asc(sort_column)), asc(id_column))

    if params.cursor is not None:
        cursor_value, cursor_id = decode_cursor(params.cursor)
        stmt = stmt.where(
            tuple_(sort_column, id_column) > tuple_(literal(cursor_value), literal(cursor_id))
        )

    # Fetch one extra row to determine has_more
    stmt = stmt.limit(params.limit + 1)

    result = await session.execute(stmt)
    rows = list(result.scalars().all())

    has_more = len(rows) > params.limit
    if has_more:
        rows = rows[: params.limit]

    items = [schema.model_validate(row) for row in rows]

    next_cursor: str | None = None
    if has_more and rows:
        last = rows[-1]
        sort_val = str(getattr(last, sort_column.key))
        row_id = cast("uuid.UUID", getattr(last, id_column.key))
        next_cursor = encode_cursor(sort_val, row_id)

    return CursorPage(items=items, next_cursor=next_cursor, has_more=has_more)
