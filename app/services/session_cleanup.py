"""Utilities for removing or revoking authentication sessions."""

from __future__ import annotations

import asyncio
import logging
import secrets
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import delete, or_, select

from app.auth.redis_session import get_session_backend
from app.core.database import async_session
from app.core.observability import get_periodic_task_metrics
from app.models.models import ActiveSession, MfaChallenge

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from sqlalchemy.sql.elements import ClauseElement

    from app.core.protocols import AsyncDatabaseSession as AsyncSession

logger = logging.getLogger(__name__)


_METRICS = get_periodic_task_metrics("session_cleanup")


def _now() -> datetime:
    return datetime.now(UTC)


async def delete_sessions_matching(
    *,
    db: AsyncSession,
    whereclause: ClauseElement[bool],  # type: ignore[type-arg]
) -> int:
    """Delete sessions (and their MFA challenges) matching *whereclause*."""

    bind = db.get_bind()
    dialect = bind.dialect

    if dialect.name == "sqlite":
        subquery = select(ActiveSession.id).where(whereclause)  # type: ignore[arg-type]
        challenge_delete_stmt = delete(MfaChallenge).where(
            MfaChallenge.session_id.in_(subquery)
        )
    else:
        challenge_delete_stmt = (
            delete(MfaChallenge)
            .where(MfaChallenge.session_id == ActiveSession.id)
            .where(whereclause)  # type: ignore[arg-type]
            .execution_options(synchronize_session=False)
        )
    await db.execute(challenge_delete_stmt)

    delete_stmt = delete(ActiveSession).where(whereclause)  # type: ignore[arg-type]
    supports_returning = bool(getattr(dialect, "delete_returning", False))
    supports_rowcount_returning = bool(
        getattr(dialect, "supports_sane_rowcount_returning", False)
    )
    if supports_returning:
        delete_stmt = delete_stmt.returning(ActiveSession.id)  # type: ignore[assignment]
        delete_result = await db.execute(delete_stmt)
        rowcount: int | None = None
        if supports_rowcount_returning:
            rowcount = getattr(delete_result, "rowcount", None)
            if rowcount is None and hasattr(delete_result, "raw"):
                rowcount = getattr(delete_result.raw, "rowcount", None)
        if rowcount is not None:
            deleted = int(rowcount)
        else:
            deleted = len(delete_result.fetchall())
    else:
        delete_result = await db.execute(delete_stmt)
        deleted = int(delete_result.rowcount or 0)  # type: ignore[attr-defined]
    return deleted


async def revoke_sessions_matching(
    *,
    db: AsyncSession,
    whereclause: ClauseElement[bool],  # type: ignore[type-arg]
    rotate_signing_key: bool = True,
) -> int:
    """Mark matching sessions as revoked without deleting their rows."""

    stmt = select(ActiveSession).where(whereclause).execution_options(yield_per=1000)  # type: ignore[arg-type]
    exec_result = await db.stream(stmt)

    session_backend = await get_session_backend()
    now = datetime.now(UTC)
    revoked = 0

    async for session in exec_result.scalars():
        revoked += 1
        if session.revoked_at is None:
            session.revoked_at = now
            # Best effort revocation in backend
            with suppress(Exception):
                await session_backend.revoke_session(session.jti)

        if rotate_signing_key:
            session.signing_key = secrets.token_urlsafe(32)

    return revoked


async def cleanup_expired_sessions(
    *, db: AsyncSession | None = None, now: datetime | None = None
) -> int:
    """Remove sessions where the expiry or revocation timestamp has passed."""

    owns_session = db is None
    if now is None:
        now = _now()
    if owns_session:
        async with async_session() as session:
            return await cleanup_expired_sessions(db=session, now=now)

    expiry_condition = or_(
        ActiveSession.expires_at <= now, ActiveSession.revoked_at <= now
    )

    assert db is not None  # nosec B101
    deleted = await delete_sessions_matching(db=db, whereclause=expiry_condition)
    await db.commit()
    if deleted:
        logger.info("Removed %s expired sessions", deleted)
    return deleted


@dataclass(slots=True)
class SessionCleanupConfig:
    interval_seconds: int = 900

    def normalized_interval(self) -> int:
        return max(30, int(self.interval_seconds))


async def start_session_cleanup_scheduler(
    *, config: SessionCleanupConfig | None = None
) -> Callable[[], Awaitable[None]]:
    """Start background cleanup task for expired sessions."""

    cfg = config or SessionCleanupConfig()
    interval = cfg.normalized_interval()

    async def _loop() -> None:
        try:
            while True:
                try:
                    async with _METRICS.track_execution() as run:
                        deleted = await cleanup_expired_sessions()
                        run.observe_deleted(deleted)
                except asyncio.CancelledError:
                    raise
                except Exception:  # pragma: no cover - defensive logging
                    logger.exception("Failed to cleanup expired sessions")
                await asyncio.sleep(interval)
        except asyncio.CancelledError:
            logger.info("Session cleanup loop cancelled")
            raise

    loop = asyncio.get_running_loop()
    task = loop.create_task(_loop())

    async def _stop() -> None:
        if task.done():
            with suppress(Exception):
                task.result()
            return
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task

    return _stop


if __name__ == "__main__":  # pragma: no cover - convenience entrypoint
    asyncio.run(cleanup_expired_sessions())
