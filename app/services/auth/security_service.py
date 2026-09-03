from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import or_, update

from app.api.validation import raise_unauthorized
from app.core.config import settings
from app.core.protocols import AsyncDatabaseSession
from app.models import ActiveSession


class AuthSecurityService:
    def __init__(self, db: AsyncDatabaseSession, locale: str):
        self.db = db
        self.locale = locale

    def validate_session_expiry(self, session: ActiveSession) -> None:
        now = datetime.now(UTC)
        expires_at = session.expires_at

        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)

        if expires_at <= now:
            self._fail()

    async def handle_mfa_ttl(self, session: ActiveSession) -> None:
        ttl = max(0, getattr(settings, "mfa_step_up_ttl_seconds", 0))
        if ttl > 0 and session.mfa_verified_at is not None:
            now = datetime.now(UTC)
            verified_at = session.mfa_verified_at
            if verified_at.tzinfo is None:
                verified_at = verified_at.replace(tzinfo=UTC)

            if now - verified_at > timedelta(seconds=ttl):
                session.mfa_verified_at = None
                await self.db.commit()

    async def sync_last_seen(
        self, session: ActiveSession, cached_session: bool = False
    ) -> None:
        now = datetime.now(UTC)
        last_seen_at = session.last_seen_at
        if last_seen_at is not None and last_seen_at.tzinfo is None:
            last_seen_at = last_seen_at.replace(tzinfo=UTC)

        # Increase sync window to 10 minutes if using Redis, else 5 mins
        sync_window = 600 if cached_session else 300

        if last_seen_at is None or (
            now - last_seen_at >= timedelta(seconds=sync_window)
        ):
            stmt = (
                update(ActiveSession)
                .where(ActiveSession.id == session.id)
                .where(
                    or_(
                        ActiveSession.last_seen_at.is_(None),
                        ActiveSession.last_seen_at
                        < now - timedelta(seconds=sync_window),
                    )
                )
                .values(last_seen_at=now)
                .execution_options(synchronize_session=False)
            )
            await self.db.execute(stmt)
            await self.db.commit()
            session.last_seen_at = now

    def _fail(self) -> None:
        raise_unauthorized(
            self.locale,
            "errors.auth.credentials_invalid",
            headers={"WWW-Authenticate": "Bearer"},
        )
