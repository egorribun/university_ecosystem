"""Weekly maintenance tasks for the platform."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import async_session
from app.core.logging import get_logger
from app.models import PushSubscription, User

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = get_logger(__name__)

STALE_SUBSCRIPTION_DAYS = 180


_ORPHAN_FK_WITNESS = text("""
SELECT EXISTS (
    SELECT 1
    FROM pg_catalog.pg_constraint AS fk
    JOIN pg_catalog.pg_attribute AS child
      ON child.attrelid = fk.conrelid AND child.attname = 'user_id'
    JOIN pg_catalog.pg_attribute AS parent
      ON parent.attrelid = fk.confrelid AND parent.attname = 'id'
    WHERE fk.conname = 'fk_push_subscriptions_user_id'
      AND fk.contype = 'f'
      AND fk.convalidated
      AND NOT fk.condeferrable
      AND NOT fk.condeferred
      AND fk.confdeltype = 'c'
      AND fk.conkey = ARRAY[child.attnum]
      AND fk.confkey = ARRAY[parent.attnum]
      AND NOT child.attisdropped AND child.attnotnull
      AND NOT parent.attisdropped AND parent.attnotnull
      AND child.atttypid = 'pg_catalog.uuid'::pg_catalog.regtype
      AND parent.atttypid = 'pg_catalog.uuid'::pg_catalog.regtype
      AND fk.conrelid = pg_catalog.to_regclass('public.push_subscriptions')
      AND fk.confrelid = pg_catalog.to_regclass('public.users')
      AND fk.conrelid = pg_catalog.to_regclass('push_subscriptions')
      AND fk.confrelid = pg_catalog.to_regclass('users')
)
""")


async def _delete_orphaned_subscriptions(session: AsyncSession) -> int:
    dialect = session.get_bind().dialect.name
    if dialect == "postgresql":
        # RLS-hidden parents are not orphans. Under the supported canonical FK,
        # ordinary writes/cascades maintain integrity without this scan. Return a
        # deleted-count of zero, not an empirical count of existing orphan rows.
        result = await session.execute(_ORPHAN_FK_WITNESS)
        if result.scalar_one() is not True:
            raise RuntimeError(
                "Canonical subscription foreign key could not be verified"
            )
        return 0
    if dialect != "sqlite":
        raise RuntimeError("Unsupported subscription cleanup dialect")

    # SQLite legacy/test databases have no RLS and may predate the canonical FK.
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


async def run_weekly_cleanup() -> dict[str, int | None]:
    """Verify subscription integrity and clean up stale push subscriptions."""

    removed_orphaned = 0
    removed_stale = 0
    async with async_session() as session:
        removed_orphaned = await _delete_orphaned_subscriptions(session)
        removed_stale = await _delete_stale_subscriptions(session)
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
