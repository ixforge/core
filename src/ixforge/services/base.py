"""Base service utilities: cursor-based pagination helper."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any, cast

from sqlalchemy import Select, asc, literal, nulls_last, tuple_

from ixforge.exceptions import ValidationError
from ixforge.schemas.common import CursorPage, CursorParams, decode_cursor, encode_cursor

if TYPE_CHECKING:
    import uuid

    from pydantic import BaseModel
    from sqlalchemy.ext.asyncio import AsyncSession


async def paginate[T: BaseModel](
    session: AsyncSession,
    stmt: Select[Any],
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
    stmt = order_after_cursor(stmt, params, sort_column, id_column)

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


def order_after_cursor(
    stmt: Select[Any], params: CursorParams, sort_column: Any, id_column: Any
) -> Select[Any]:
    """Order by (sort_column, id_column) and keep only the rows after the cursor"""
    stmt = stmt.order_by(nulls_last(asc(sort_column)), asc(id_column))
    if params.cursor is None:
        return stmt
    raw_value, cursor_id = decode_cursor(params.cursor)
    sort_value = _parse_sort_value(raw_value, sort_column)
    return stmt.where(
        tuple_(sort_column, id_column)
        > tuple_(literal(sort_value, type_=sort_column.type), literal(cursor_id))
    )


def _parse_sort_value(raw: str, sort_column: Any) -> Any:
    """Convert the cursor text back to the sort column type so the comparison is typed"""
    python_type = sort_column.type.python_type
    try:
        return datetime.fromisoformat(raw) if python_type is datetime else python_type(raw)
    except ValueError as exc:
        raise ValidationError(
            "Invalid pagination cursor",
            details={"cursor": "Malformed or corrupted cursor value"},
        ) from exc
