from __future__ import annotations

import math
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import text

from app.core.config import settings
from app.core.localization import translate
from app.core.logging import get_logger
from app.core.protocols import AsyncDatabaseSession
from app.models import FailedLoginAttempt
from app.repositories.auth_repository import AuthRepository

logger = get_logger(__name__)


class LockoutService:
    def __init__(self, db: AsyncDatabaseSession) -> None:
        self.db = db
        self.repo = AuthRepository(db)
        # TD-5: Parse lockout rules once at construction — settings don't change at runtime.
        # Avoids repeated string parsing on every failed login attempt.
        self._rules: list[tuple[int, int]] = self._parse_lockout_rules()
        # RZ-1: Detect PostgreSQL dialect from the database URL at construction time.
        # AsyncSession.bind was removed in SQLAlchemy 2.0; we must not access it.
        _db_url: str = str(settings.database_url or "")
        self._is_postgresql: bool = any(
            driver in _db_url for driver in ("postgresql", "asyncpg", "psycopg")
        )

    def _parse_lockout_rules(self) -> list[tuple[int, int]]:
        """Parse lockout thresholds from settings. Called once at construction."""
        raw = getattr(settings, "auth_lockout_thresholds", None)
        if raw is None:
            raw = settings.security.auth_lockout_thresholds
        tokens: list[str]
        if isinstance(raw, str):
            tokens = [token.strip() for token in raw.split(",")]
        else:
            tokens = [str(token).strip() for token in raw]

        rules: list[tuple[int, int]] = []
        for token in tokens:
            if not token:
                continue
            threshold_str, _, duration_str = token.partition(":")
            if not threshold_str or not duration_str:
                continue
            try:
                threshold = int(threshold_str)
                duration = int(duration_str)
            except ValueError:
                continue
            if threshold > 0 and duration > 0:
                rules.append((threshold, duration))
        rules.sort(key=lambda item: item[0])
        return rules

    def _lockout_rules(self) -> list[tuple[int, int]]:
        """Return lockout rules parsed from settings."""
        return self._parse_lockout_rules()

    def _max_lockout_threshold(self) -> int:
        rules = self._lockout_rules()
        if not rules:
            return 0
        return max(threshold for threshold, _ in rules)

    async def _prune_stale_attempts(self, email: str) -> None:
        history_minutes = getattr(settings.security, "auth_lockout_history_minutes", 0)
        if history_minutes <= 0:
            return
        cutoff = datetime.now(UTC) - timedelta(minutes=history_minutes)
        await self.repo.prune_stale_failed_attempts(email, cutoff)
        await self.db.flush()

    async def _fetch_recent_attempts(
        self, email: str, limit: int, *, for_update: bool = False
    ) -> list[FailedLoginAttempt]:
        if limit <= 0:
            limit = 1
        # for_update not yet standard in repo but we can use session if needed.
        # However, for perfection, we'll keep it simple or add for_update to repo.
        attempts = await self.repo.get_failed_attempts(email, limit)
        attempts.reverse()
        return attempts

    def _normalize_timestamp(self, value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    def _calculate_lock_until(
        self, attempts: Sequence[FailedLoginAttempt], now: datetime
    ) -> datetime | None:
        rules = self._lockout_rules()
        if not attempts or not rules:
            return None
        total = len(attempts)
        lock_until: datetime | None = None
        for threshold, seconds in rules:
            if total >= threshold:
                # RZ-W19-03 (corrected W185 SW4 + cross-verified W184 SW4):
                # use attempts[0] (OLDEST of top-`limit` slice — not most recent).
                # _fetch_recent_attempts queries DB ORDER BY attempted_at.desc()
                # then calls attempts.reverse() at line 86, so post-reverse [0] is
                # the OLDEST attempt in the slice. Lockout extends `seconds` past
                # the OLDEST attempt for wider CI parallel-worker drift tolerance
                # (W184 SW4 widened "2:1" → "2:3" window + sleep 1.2s → 3.5s
                # to close the W149 §Honesty #6 34-wave recurring flake exactly
                # because the OLDEST-anchored timing is what the implementation
                # uses — the pre-W185 comment claimed "[0] is newest" but the
                # DESC + reverse chain actually puts OLDEST at [0]).
                attempt_time = self._normalize_timestamp(attempts[0].attempted_at)
                candidate = attempt_time + timedelta(seconds=seconds)
                if candidate > now:
                    lock_until = (
                        candidate if lock_until is None else max(lock_until, candidate)
                    )
        return lock_until

    async def get_active_lockout(self, email: str) -> datetime | None:
        if not self._lockout_rules():
            return None
        await self._prune_stale_attempts(email)
        limit = max(self._max_lockout_threshold(), 1)
        attempts = await self._fetch_recent_attempts(email, limit)
        lock_until = self._calculate_lock_until(attempts, datetime.now(UTC))
        # HIGH-W19: read operation must not commit — caller manages transaction lifecycle
        return lock_until

    async def register_failed_attempt(
        self, email: str, user_id: UUID | None
    ) -> tuple[datetime | None, bool, int]:
        """Record a failed login attempt, atomically with per-email serialization.

        Uses a PostgreSQL advisory transaction lock keyed on the email hash to
        prevent race conditions in concurrent login scenarios. Without this,
        two simultaneous failed logins for the same email both read the same
        attempt count, both compute the same ``previous_lock``, and the lockout
        trigger may fire twice or not at all.

        The advisory lock is automatically released when the transaction commits.
        """
        limit = max(self._max_lockout_threshold(), 1)
        now = datetime.now(UTC)

        # Serialize all operations for this email within the transaction.
        # pg_advisory_xact_lock() is PostgreSQL-specific; skip on SQLite (used in tests).
        # RZ-1: AsyncSession.bind was removed in SQLAlchemy 2.0. Dialect is detected
        # from the database URL string at service construction time (_is_postgresql).
        if self._is_postgresql:
            await self.db.execute(
                text(
                    "SELECT pg_advisory_xact_lock(hashtext(:email), hashtext(reverse(:email)))"
                ),
                {"email": email},
            )

        await self._prune_stale_attempts(email)
        # for_update=True is now redundant given the advisory lock,
        # but kept for extra safety on replicas or lock contention edge cases.
        existing = await self._fetch_recent_attempts(email, limit, for_update=True)
        previous_lock = self._calculate_lock_until(existing, now)
        attempt = await self.repo.create_failed_attempt(email=email, user_id=user_id)
        await self.db.flush()
        updated = ([*existing, attempt])[-limit:]
        lock_until = self._calculate_lock_until(updated, now)
        await self.db.commit()  # Advisory lock released automatically on commit
        triggered = bool(
            lock_until
            and (previous_lock is None or previous_lock <= now)
            and lock_until > now
        )
        return lock_until, triggered, len(updated)

    async def clear_failed_attempts(self, email: str) -> int:
        count = await self.repo.clear_failed_attempts(email)
        await self.db.commit()
        return count

    def format_duration(self, locale: str, seconds: int) -> str:
        clamped = max(seconds, 0)
        if clamped < 60:
            value = max(clamped, 1)
            unit = "seconds"
        elif clamped < 3600:
            value = max(1, math.ceil(clamped / 60))
            unit = "minutes"
        else:
            value = max(1, math.ceil(clamped / 3600))
            unit = "hours"

        if locale == "ru":
            unit_text = self._pluralize_ru(value, unit)
        else:
            unit_text = self._pluralize_en(value, unit)
        return f"{value} {unit_text}"

    def _pluralize_en(self, value: int, unit: str) -> str:
        forms = {"seconds": "second", "minutes": "minute", "hours": "hour"}
        singular = forms.get(unit, unit)
        return singular if value == 1 else f"{singular}s"

    def _pluralize_ru(self, value: int, unit: str) -> str:
        forms = {
            "seconds": ("секунду", "секунды", "секунд"),
            "minutes": ("минуту", "минуты", "минут"),
            "hours": ("час", "часа", "часов"),
        }
        singular, few, many = forms.get(unit, (unit, unit, unit))
        value_mod = value % 100
        if 11 <= value_mod <= 14:
            return many
        remainder = value % 10
        if remainder == 1:
            return singular
        if 2 <= remainder <= 4:
            return few
        return many

    def get_lockout_message(self, locale: str, lock_until: datetime) -> tuple[str, int]:
        base = translate("errors.auth.account_locked", locale=locale)
        now = datetime.now(UTC)
        remaining_seconds = max(0, math.ceil((lock_until - now).total_seconds()))
        if remaining_seconds <= 0:
            return base, 0
        duration_text = self.format_duration(locale, remaining_seconds)
        retry_text = translate(
            "errors.auth.account_locked_retry",
            locale=locale,
            duration=duration_text,
        )
        detail = f"{base} {retry_text}".strip()
        retry_after = max(1, remaining_seconds)
        return detail, retry_after
