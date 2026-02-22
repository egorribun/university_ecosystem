import logging
import math
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.localization import translate
from app.models.models import FailedLoginAttempt
from app.repositories.auth_repository import AuthRepository

logger = logging.getLogger(__name__)


class LockoutService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = AuthRepository(db)

    def _lockout_rules(self) -> list[tuple[int, int]]:
        raw = settings.auth_lockout_thresholds
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

    def _max_lockout_threshold(self) -> int:
        rules = self._lockout_rules()
        if not rules:
            return 0
        return max(threshold for threshold, _ in rules)

    async def _prune_stale_attempts(self, email: str) -> None:
        history_minutes = getattr(settings, "auth_lockout_history_minutes", 0)
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
                attempt_time = self._normalize_timestamp(attempts[-1].attempted_at)
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
        await self.db.commit()
        return lock_until

    async def register_failed_attempt(
        self, email: str, user_id: UUID | None
    ) -> tuple[datetime | None, bool, int]:
        limit = max(self._max_lockout_threshold(), 1)
        await self._prune_stale_attempts(email)
        existing = await self._fetch_recent_attempts(email, limit, for_update=True)
        now = datetime.now(UTC)
        previous_lock = self._calculate_lock_until(existing, now)
        attempt = await self.repo.create_failed_attempt(
            email=email, user_id=user_id, attempted_at=now
        )
        await self.db.flush()
        updated = ([*existing, attempt])[-limit:]
        lock_until = self._calculate_lock_until(updated, now)
        await self.db.commit()
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
