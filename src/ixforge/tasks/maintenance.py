"""Maintenance background tasks.

Periodic housekeeping tasks for cleaning up old events and config versions.
"""

from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy import delete, func, select

from ixforge.database import get_session_factory
from ixforge.models.config import ConfigVersion
from ixforge.models.event import Event
from ixforge.tasks.setup import app

logger = structlog.get_logger()

# Default retention settings
DEFAULT_EVENT_RETENTION_DAYS = 90
DEFAULT_CONFIG_VERSIONS_KEEP = 100


@app.periodic(cron="0 3 * * *")  # type: ignore[untyped-decorator]
@app.task(name="cleanup_old_events", queue="maintenance")
async def cleanup_old_events(retention_days: int = DEFAULT_EVENT_RETENTION_DAYS) -> dict[str, int]:
    """Delete events older than the configured retention period.

    Parameters
    ----------
    retention_days:
        Number of days to retain events.  Events older than this are deleted.
        Defaults to 90.

    Returns
    -------
    dict with ``deleted_count``.
    """
    log = logger.bind(retention_days=retention_days)
    log.info("cleanup_old_events.started")

    cutoff = datetime.now(UTC) - timedelta(days=retention_days)

    session_factory = get_session_factory()
    async with session_factory() as session:
        try:
            stmt = delete(Event).where(Event.created_at < cutoff)
            result = await session.execute(stmt)
            deleted_count: int = result.rowcount  # type: ignore[attr-defined]
            await session.commit()
            log.info("cleanup_old_events.completed", deleted_count=deleted_count)
            return {"deleted_count": deleted_count}
        except Exception:
            await session.rollback()
            log.exception("cleanup_old_events.failed")
            raise


@app.periodic(cron="0 4 * * 0")  # type: ignore[untyped-decorator]
@app.task(name="cleanup_config_versions", queue="maintenance")
async def cleanup_config_versions(
    keep_last: int = DEFAULT_CONFIG_VERSIONS_KEEP,
) -> dict[str, int]:
    """Remove old config versions, keeping the last N per route server.

    For each route server, the most recent ``keep_last`` versions are retained.
    Additionally, any version that has been applied (``applied_at IS NOT NULL``)
    is never deleted, regardless of its position in the history.

    Parameters
    ----------
    keep_last:
        Number of most recent config versions to keep per route server.
        Defaults to 100.

    Returns
    -------
    dict with ``deleted_count``.
    """
    log = logger.bind(keep_last=keep_last)
    log.info("cleanup_config_versions.started")

    session_factory = get_session_factory()
    async with session_factory() as session:
        try:
            # Get all distinct route server IDs that have config versions.
            rs_stmt = select(ConfigVersion.route_server_id).distinct()
            rs_result = await session.execute(rs_stmt)
            rs_ids = [row[0] for row in rs_result.all()]

            total_deleted = 0

            for rs_id in rs_ids:
                # Find the IDs of the most recent `keep_last` versions for
                # this route server (these are always preserved).
                latest_stmt = (
                    select(ConfigVersion.id)
                    .where(ConfigVersion.route_server_id == rs_id)
                    .order_by(ConfigVersion.generated_at.desc())
                    .limit(keep_last)
                )
                latest_result = await session.execute(latest_stmt)
                keep_ids = {row[0] for row in latest_result.all()}

                # Also protect any version that has been applied.
                applied_stmt = select(ConfigVersion.id).where(
                    ConfigVersion.route_server_id == rs_id,
                    ConfigVersion.applied_at.isnot(None),
                )
                applied_result = await session.execute(applied_stmt)
                keep_ids.update(row[0] for row in applied_result.all())

                # Proteger la version mas reciente independientemente de applied_at
                newest_stmt = (
                    select(ConfigVersion.id)
                    .where(ConfigVersion.route_server_id == rs_id)
                    .order_by(ConfigVersion.generated_at.desc())
                    .limit(1)
                )
                newest_result = await session.execute(newest_stmt)
                newest_row = newest_result.first()
                if newest_row is not None:
                    keep_ids.add(newest_row[0])

                # Count how many versions exist for this route server.
                count_stmt = (
                    select(func.count())
                    .select_from(ConfigVersion)
                    .where(ConfigVersion.route_server_id == rs_id)
                )
                count_result = await session.execute(count_stmt)
                total_for_rs = count_result.scalar_one()

                # Only delete if there are more versions than we want to keep.
                if total_for_rs <= keep_last:
                    continue

                # Delete versions that are not in the keep set.
                del_stmt = delete(ConfigVersion).where(
                    ConfigVersion.route_server_id == rs_id,
                    ConfigVersion.id.notin_(keep_ids),
                )
                result = await session.execute(del_stmt)
                total_deleted += result.rowcount  # type: ignore[attr-defined]

            await session.commit()
            log.info("cleanup_config_versions.completed", deleted_count=total_deleted)
            return {"deleted_count": total_deleted}
        except Exception:
            await session.rollback()
            log.exception("cleanup_config_versions.failed")
            raise
