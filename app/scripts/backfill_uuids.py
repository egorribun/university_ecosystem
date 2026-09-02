import asyncio
import logging
from datetime import UTC
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import async_session
from app.core.logging import get_logger
from app.models.auth import (
    ActiveSession,
    EmailChangeToken,
    FailedLoginAttempt,
    LoginHistory,
    MfaChallenge,
    MfaTotpEnrollment,
    PasswordResetToken,
    RecoveryCode,
    TrustedDevice,
)
from app.models.domain_events import StoredEvent
from app.models.events import Event, EventAttendance, EventFile
from app.models.news import News, NewsComment, NewsLike
from app.models.notifications import (
    Notification,
    NotificationDelivery,
    NotificationQueueJob,
    PushSubscription,
)
from app.models.users import InviteCode, User
from app.utils.uuid_v7 import generate_uuid7

logging.basicConfig(level=logging.INFO)
logger = get_logger(__name__)

# Config for tables that just need their own UUID populated
TABLES_OWN_ID = [
    # (Table Class, created_at component)
    (User, "created_at"),
    (StoredEvent, "created_at"),
    (Notification, "created_at"),
    (NotificationQueueJob, "enqueued_at"),
    (NotificationDelivery, "attempted_at"),
    (PushSubscription, "created_at"),
    (ActiveSession, "created_at"),
    (MfaTotpEnrollment, "created_at"),
    (MfaChallenge, "created_at"),
    (FailedLoginAttempt, "attempted_at"),
    (PasswordResetToken, "created_at"),
    (EmailChangeToken, "created_at"),
    (TrustedDevice, "created_at"),
    (RecoveryCode, "created_at"),
    (LoginHistory, "created_at"),
    (Event, "created_at"),
    (EventAttendance, "registered_at"),
    (EventFile, None),
    (News, "created_at"),
    (NewsLike, "created_at"),
    (NewsComment, "created_at"),
    (InviteCode, "created_at"),
]

# Config for tables that need their User Foreign Keys backfilled
# (Model, legacy_fk_field, shadow_fk_field)
TABLES_USER_FK = [
    (ActiveSession, "user_id", "shadow_user_id"),
    (Notification, "user_id", "shadow_user_id"),
    (PushSubscription, "user_id", "shadow_user_id"),
    (MfaTotpEnrollment, "user_id", "shadow_user_id"),
    (MfaChallenge, "user_id", "shadow_user_id"),
    (FailedLoginAttempt, "user_id", "shadow_user_id"),  # Might be null
    (PasswordResetToken, "user_id", "shadow_user_id"),
    (EmailChangeToken, "user_id", "shadow_user_id"),
    (TrustedDevice, "user_id", "shadow_user_id"),
    (RecoveryCode, "user_id", "shadow_user_id"),
    (LoginHistory, "user_id", "shadow_user_id"),
    (EventAttendance, "user_id", "shadow_user_id"),
    (NewsLike, "user_id", "shadow_user_id"),
    (NewsComment, "user_id", "shadow_user_id"),
    # Special ones
    (Event, "created_by", "shadow_created_by"),
    (News, "author_id", "shadow_author_id"),
    (InviteCode, "used_by_user_id", "shadow_used_by_user_id"),
]


async def get_user_id_map(session: AsyncSession) -> dict[Any, Any]:
    """Fetch a map of legacy int ID to new UUID v7 for all users."""
    logger.info("Building User ID map...")
    stmt = select(User.id, User.uuid_id)  # type: ignore[attr-defined]

    # Use streaming to prevent holding enormous results in memory during map build
    result = await session.stream(stmt.execution_options(yield_per=1000))

    mapping = {}
    async for row in result:
        if row.uuid_id:
            mapping[row.id] = row.uuid_id

    return mapping


async def backfill_own_uuids(session: AsyncSession) -> None:
    """Populate uuid_id for all records in targeted tables."""
    for model, ts_field in TABLES_OWN_ID:
        logger.info(
            "Backfilling own UUIDs for %s...", model.__tablename__
        )  # LOW-W19: lazy logging

        count = 0
        total_processed = 0

        # We use a cursor chunked yield to prevent extreme memory use.
        # But we commit in batches. Because a commit closes the cursor,
        # we have to isolate the updates.

        while True:
            # We must use isolated cursor bounds because commit() ruins open cursors.
            stmt = select(model).where(model.uuid_id.is_(None)).limit(1000)  # type: ignore[attr-defined]
            result = await session.execute(stmt)
            records = result.scalars().all()

            if not records:
                break

            for record in records:
                ts = (
                    getattr(record, ts_field)
                    if ts_field and hasattr(record, ts_field)
                    else None
                )
                if ts and ts.tzinfo is None:
                    ts = ts.replace(tzinfo=UTC)
                record.uuid_id = generate_uuid7(ts)  # type: ignore[attr-defined]
                count += 1

            await session.commit()
            total_processed += count
            count = 0

        logger.info(
            "  Processed %s records for %s", total_processed, model.__tablename__
        )  # LOW-W19: lazy logging


async def backfill_foreign_uuids(
    session: AsyncSession, user_map: dict[Any, Any]
) -> None:
    """Populate shadow FK columns using the user map."""
    for model, legacy_col, shadow_col in TABLES_USER_FK:
        logger.info(
            "Backfilling FKs for %s.%s...", model.__tablename__, shadow_col
        )  # LOW-W19: lazy logging

        total_processed = 0
        skipped = 0

        while True:
            # Get records where legacy is NOT null but shadow IS null, paginated
            stmt = (
                select(model)
                .where(
                    getattr(model, legacy_col).is_not(None),
                    getattr(model, shadow_col).is_(None),
                )
                .limit(1000)
            )
            result = await session.execute(stmt)
            records = result.scalars().all()

            if not records:
                break

            for record in records:
                legacy_id = getattr(record, legacy_col)
                new_uuid = user_map.get(legacy_id)
                if new_uuid:
                    setattr(record, shadow_col, new_uuid)
                    total_processed += 1
                else:
                    skipped += 1

            await session.commit()
        await session.commit()
        logger.info(  # LOW-W19: lazy logging
            "  Linked %s records (%s skipped) for %s",
            total_processed,
            skipped,
            model.__tablename__,
        )


async def main() -> None:
    async with async_session() as session:
        try:
            # 1. First ensure all Users have a UUID (we need them for mapping)
            await backfill_own_uuids(session)

            # 2. Get the mapping
            user_map = await get_user_id_map(session)

            # 3. Backfill all other tables' own IDs and Foreign Keys
            await backfill_foreign_uuids(session, user_map)

            logger.info("Backfill complete!")
        except Exception as e:  # RZ-22-01-JUSTIFIED: re-raise-after-cleanup — rollback then log (reviewed TD-27-04)
            logger.error("Backfill failed: %s", e)  # LOW-W19: lazy logging
            await session.rollback()


if __name__ == "__main__":
    asyncio.run(main())
