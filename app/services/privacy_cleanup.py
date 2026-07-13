"""Retention helpers for privacy-sensitive artifacts."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, delete, or_

from app.core.database import async_session
from app.core.logging import get_logger
from app.core.observability import get_periodic_task_metrics
from app.core.protocols import AsyncDatabaseSession as AsyncSession
from app.models import (
    ActiveSession,
    FailedLoginAttempt,
    MfaChallenge,
    MfaTotpEnrollment,
)
from app.services.data_access import cleanup_access_logs

logger = get_logger(__name__)

_METRICS = get_periodic_task_metrics("privacy_cleanup")


def _now() -> datetime:
    return datetime.now(UTC)


def _cutoff(retention_days: int) -> datetime:
    return _now() - timedelta(days=max(0, int(retention_days)))


async def _cleanup_sessions(db: AsyncSession, retention_days: int) -> int:
    cutoff = _cutoff(retention_days)
    stmt = delete(ActiveSession).where(
        and_(
            ActiveSession.expires_at < cutoff,
            or_(ActiveSession.revoked_at.is_(None), ActiveSession.revoked_at < cutoff),
        )
    )
    result = await db.execute(stmt.execution_options(synchronize_session=False))
    return int(result.rowcount or 0)  # type: ignore[attr-defined]


async def _cleanup_mfa_challenges(db: AsyncSession, retention_days: int) -> int:
    cutoff = _cutoff(retention_days)
    stmt = delete(MfaChallenge).where(MfaChallenge.expires_at < cutoff)
    result = await db.execute(stmt.execution_options(synchronize_session=False))
    return int(result.rowcount or 0)  # type: ignore[attr-defined]


async def _cleanup_mfa_enrollments(db: AsyncSession, retention_days: int) -> int:
    cutoff = _cutoff(retention_days)
    stmt = delete(MfaTotpEnrollment).where(
        and_(
            MfaTotpEnrollment.revoked_at.is_not(None),
            MfaTotpEnrollment.revoked_at < cutoff,
        )
    )
    result = await db.execute(stmt.execution_options(synchronize_session=False))
    return int(result.rowcount or 0)  # type: ignore[attr-defined]


async def _cleanup_failed_logins(db: AsyncSession, retention_days: int) -> int:
    cutoff = _cutoff(retention_days)
    stmt = delete(FailedLoginAttempt).where(FailedLoginAttempt.attempted_at < cutoff)
    result = await db.execute(stmt.execution_options(synchronize_session=False))
    return int(result.rowcount or 0)  # type: ignore[attr-defined]


@dataclass(slots=True)
class PrivacyCleanupConfig:
    session_retention_days: int = 90
    mfa_retention_days: int = 30
    failed_login_retention_days: int = 30
    audit_log_retention_days: int = 180
    interval_seconds: int = 86_400

    def normalized_interval(self) -> int:
        return max(60, int(self.interval_seconds))


async def cleanup_privacy_artifacts(
    *, db: AsyncSession | None = None, config: PrivacyCleanupConfig
) -> dict[str, int]:
    owns_session = db is None
    if owns_session:
        async with async_session() as session:
            return await cleanup_privacy_artifacts(db=session, config=config)

    counts: dict[str, int] = {}
    assert db is not None  # noqa: S101
    async with _METRICS.track_execution() as run:
        counts["sessions"] = await _cleanup_sessions(db, config.session_retention_days)
        counts["mfa_challenges"] = await _cleanup_mfa_challenges(
            db, config.mfa_retention_days
        )
        counts["mfa_enrollments"] = await _cleanup_mfa_enrollments(
            db, config.mfa_retention_days
        )
        counts["failed_logins"] = await _cleanup_failed_logins(
            db, config.failed_login_retention_days
        )
        counts["access_logs"] = await cleanup_access_logs(
            db=db, retention_days=config.audit_log_retention_days
        )
        run.observe_deleted(sum(counts.values()))
    await db.commit()
    return counts


async def start_privacy_cleanup_scheduler(
    *, config: PrivacyCleanupConfig
) -> Callable[[], Awaitable[None]]:
    interval = config.normalized_interval()

    async def _loop() -> None:
        try:
            while True:
                try:
                    deleted = await cleanup_privacy_artifacts(config=config)
                    logger.info("Privacy cleanup run completed: %s", deleted)
                except asyncio.CancelledError:
                    raise
                except OSError, ConnectionError:
                    # RZ-20-04: Narrowed — DB/network errors only.
                    logger.exception("Failed to run privacy cleanup")
                await asyncio.sleep(interval)
        except asyncio.CancelledError:
            logger.info("Privacy cleanup loop cancelled")
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
