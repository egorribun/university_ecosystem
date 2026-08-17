"""Weekly maintenance tasks for the platform."""

from __future__ import annotations

import asyncio
import re
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from sqlalchemy import delete, select
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import async_session, engine
from app.core.logging import get_logger
from app.models import PushSubscription, User

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = get_logger(__name__)

STALE_SUBSCRIPTION_DAYS = 180

# RZ-20-01 (audit 2026-03-24): Whitelist-validate database identifiers before
# embedding them in DDL.  PostgreSQL identifiers are max 63 bytes, ASCII
# alphanumeric + underscore.  Any name that doesn't match is either malicious
# or an edge-case that should not be REINDEXed without manual intervention.
_SAFE_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,62}$")


async def _delete_orphaned_subscriptions(session: AsyncSession) -> int:
    total_orphaned = 0
    while True:
        stmt = (
            delete(PushSubscription)
            .where(~PushSubscription.user_id.in_(select(User.id)))
            .returning(PushSubscription.id)
        )

        result = await session.execute(stmt)
        orphaned = result.scalars().fetchmany(1000)

        if not orphaned:
            break

        total_orphaned += len(orphaned)
        await session.commit()

    if total_orphaned:
        logger.info(
            "weekly_cleanup.deleted_orphaned_subscriptions",
            extra={"count": total_orphaned},
        )
    return total_orphaned


async def _delete_stale_subscriptions(session: AsyncSession) -> int:
    cutoff = datetime.now(UTC) - timedelta(days=STALE_SUBSCRIPTION_DAYS)
    total_stale = 0

    while True:
        stmt = (
            delete(PushSubscription)
            .where(
                (PushSubscription.last_seen_at.is_(None))
                | (PushSubscription.last_seen_at < cutoff)
            )
            .returning(PushSubscription.id)
        )

        result = await session.execute(stmt)
        stale = result.scalars().fetchmany(1000)

        if not stale:
            break

        total_stale += len(stale)
        await session.commit()

    if total_stale:
        logger.info(
            "weekly_cleanup.deleted_stale_subscriptions", extra={"count": total_stale}
        )
    return total_stale


async def _reindex_database() -> None:
    url = make_url(settings.database_url)
    database_name = url.database
    if not database_name:
        logger.warning("Skipping database reindex: database name is empty")
        return

    # RZ-20-01 (audit 2026-03-24): Whitelist-validate the identifier instead of
    # relying on manual escaping (replace('"', '""')).  DDL statements cannot use
    # bind parameters, so the only safe approach is strict validation followed by
    # dialect-aware quoting via identifier_preparer.quote().
    if not _SAFE_IDENTIFIER_RE.match(database_name):
        logger.error(
            "weekly_cleanup.reindex_skipped: database name %r failed identifier validation — "
            "refusing to embed in DDL to prevent injection (CWE-89)",
            database_name,
        )
        return

    async with engine.connect() as conn:
        preparer = conn.dialect.identifier_preparer
        safe_name = preparer.quote(database_name)
        autocommit_conn = await conn.execution_options(isolation_level="AUTOCOMMIT")
        await autocommit_conn.exec_driver_sql(f"REINDEX DATABASE {safe_name}")
    logger.info("weekly_cleanup.reindex_completed", extra={"database": database_name})


async def run_weekly_cleanup() -> dict[str, int | None]:
    """Perform database reindexing and cleanup stale push subscriptions."""

    removed_orphaned = 0
    removed_stale = 0
    async with async_session() as session:
        removed_orphaned = await _delete_orphaned_subscriptions(session)
        removed_stale = await _delete_stale_subscriptions(session)
    await _reindex_database()
    stats: dict[str, int | None] = {
        "subscriptions_removed": removed_orphaned + removed_stale,
        "subscriptions_orphaned": removed_orphaned,
        "subscriptions_stale": removed_stale,
    }
    logger.info("weekly_cleanup.completed", extra=stats)
    return stats


def main() -> None:
    stats = asyncio.run(run_weekly_cleanup())
    logger.info("Weekly cleanup finished: %s", stats)  # LOW-W19: lazy logging


if __name__ == "__main__":
    main()
