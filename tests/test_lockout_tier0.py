"""Behavioral Tier0 tests for lockout policy boundaries."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest


def _attempt(attempted_at: datetime) -> SimpleNamespace:
    return SimpleNamespace(attempted_at=attempted_at)


def test_lockout_rules_discard_invalid_entries_and_sort_thresholds(monkeypatch) -> None:
    from app.core.config import settings
    from app.services.auth.lockout import LockoutService

    monkeypatch.setattr(
        settings.security,
        "auth_lockout_thresholds",
        "bad, 5:20, 2:x, 0:3, 2:10, :4",
    )

    service = LockoutService(AsyncMock())

    assert service._lockout_rules() == [(2, 10), (5, 20)]
    assert service._max_lockout_threshold() == 5


def test_lockout_rules_accept_sequence_settings(monkeypatch) -> None:
    from app.core.config import settings
    from app.services.auth.lockout import LockoutService

    monkeypatch.setattr(settings.security, "auth_lockout_thresholds", ["", 3, "4:8"])

    service = LockoutService(AsyncMock())

    assert service._lockout_rules() == [(4, 8)]


def test_calculate_lock_until_normalizes_naive_time_and_keeps_longest_window(
    monkeypatch,
) -> None:
    from app.core.config import settings
    from app.services.auth.lockout import LockoutService

    monkeypatch.setattr(settings.security, "auth_lockout_thresholds", "2:10,3:20")
    service = LockoutService(AsyncMock())
    now = datetime(2026, 7, 23, 12, tzinfo=UTC)

    lock_until = service._calculate_lock_until(
        [
            _attempt(datetime(2026, 7, 23, 11, 59, 55)),
            _attempt(datetime(2026, 7, 23, 11, 59, 58)),
            _attempt(datetime(2026, 7, 23, 11, 59, 59)),
        ],
        now,
    )

    assert lock_until == datetime(2026, 7, 23, 12, 0, 15, tzinfo=UTC)


def test_calculate_lock_until_skips_unmet_and_expired_rules(monkeypatch) -> None:
    from app.core.config import settings
    from app.services.auth.lockout import LockoutService

    monkeypatch.setattr(settings.security, "auth_lockout_thresholds", "2:10")
    service = LockoutService(AsyncMock())
    now = datetime(2026, 7, 23, 12, tzinfo=UTC)

    assert (
        service._calculate_lock_until(
            [_attempt(datetime(2026, 7, 23, 11, 59, 59))],
            now,
        )
        is None
    )
    assert (
        service._calculate_lock_until(
            [
                _attempt(now - timedelta(seconds=20)),
                _attempt(now - timedelta(seconds=19)),
            ],
            now,
        )
        is None
    )


@pytest.mark.asyncio
async def test_prune_stale_attempts_flushes_transaction(monkeypatch) -> None:
    from app.core.config import settings
    from app.services.auth.lockout import LockoutService

    monkeypatch.setattr(settings.security, "auth_lockout_thresholds", "2:10")
    monkeypatch.setattr(settings.security, "auth_lockout_history_minutes", 5)
    db = AsyncMock()
    service = LockoutService(db)
    service.repo.prune_stale_failed_attempts = AsyncMock()

    await service._prune_stale_attempts("stale@example.com")

    service.repo.prune_stale_failed_attempts.assert_awaited_once()
    db.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_fetch_recent_attempts_clamps_limit_and_reverses_db_order(
    monkeypatch,
) -> None:
    from app.core.config import settings
    from app.services.auth.lockout import LockoutService

    monkeypatch.setattr(settings.security, "auth_lockout_thresholds", "2:10")
    service = LockoutService(AsyncMock())
    first = _attempt(datetime.now(UTC) - timedelta(seconds=2))
    second = _attempt(datetime.now(UTC) - timedelta(seconds=1))
    service.repo.get_failed_attempts = AsyncMock(return_value=[first, second])

    attempts = await service._fetch_recent_attempts("ordered@example.com", 0)

    assert attempts == [second, first]
    service.repo.get_failed_attempts.assert_awaited_once_with("ordered@example.com", 1)
    service.repo.get_failed_attempts.reset_mock()

    await service._fetch_recent_attempts("ordered@example.com", 2)

    service.repo.get_failed_attempts.assert_awaited_once_with("ordered@example.com", 2)


@pytest.mark.asyncio
async def test_prune_stale_attempts_skips_when_history_is_disabled(monkeypatch) -> None:
    from app.core.config import settings
    from app.services.auth.lockout import LockoutService

    monkeypatch.setattr(settings.security, "auth_lockout_thresholds", "2:10")
    monkeypatch.setattr(settings.security, "auth_lockout_history_minutes", 0)
    service = LockoutService(AsyncMock())
    service.repo.prune_stale_failed_attempts = AsyncMock()

    await service._prune_stale_attempts("no-history@example.com")

    service.repo.prune_stale_failed_attempts.assert_not_awaited()


@pytest.mark.asyncio
async def test_get_active_lockout_prunes_and_reads_recent_attempts(monkeypatch) -> None:
    from app.core.config import settings
    from app.services.auth.lockout import LockoutService

    monkeypatch.setattr(settings.security, "auth_lockout_thresholds", "1:10")
    service = LockoutService(AsyncMock())
    service._prune_stale_attempts = AsyncMock()
    service._fetch_recent_attempts = AsyncMock(
        return_value=[_attempt(datetime.now(UTC))]
    )

    lock_until = await service.get_active_lockout("active@example.com")

    assert lock_until is not None
    service._prune_stale_attempts.assert_awaited_once_with("active@example.com")
    service._fetch_recent_attempts.assert_awaited_once_with("active@example.com", 1)


@pytest.mark.asyncio
async def test_get_active_lockout_without_rules_does_not_query_repository(
    monkeypatch,
) -> None:
    from app.core.config import settings
    from app.services.auth.lockout import LockoutService

    monkeypatch.setattr(settings.security, "auth_lockout_thresholds", "invalid")
    service = LockoutService(AsyncMock())
    service.repo.get_failed_attempts = AsyncMock()

    assert await service.get_active_lockout("no-rules@example.com") is None
    assert service._max_lockout_threshold() == 0
    service.repo.get_failed_attempts.assert_not_awaited()


def test_expired_lockout_message_returns_base_without_retry(monkeypatch) -> None:
    from app.core.config import settings
    from app.services.auth.lockout import LockoutService

    monkeypatch.setattr(settings.security, "auth_lockout_thresholds", "2:10")
    service = LockoutService(AsyncMock())

    with patch(
        "app.services.auth.lockout.translate", return_value="Account locked"
    ) as translate:
        detail, retry_after = service.get_lockout_message(
            "en", datetime.now(UTC) - timedelta(seconds=1)
        )

    assert detail == "Account locked"
    assert retry_after == 0
    translate.assert_called_once_with("errors.auth.account_locked", locale="en")


@pytest.mark.asyncio
async def test_register_failed_attempt_uses_postgres_advisory_lock(monkeypatch) -> None:
    from app.core.config import settings
    from app.services.auth.lockout import LockoutService

    monkeypatch.setattr(settings.security, "auth_lockout_thresholds", "1:30")
    db = AsyncMock()
    service = LockoutService(db)
    service._is_postgresql = True
    service._prune_stale_attempts = AsyncMock()
    service._fetch_recent_attempts = AsyncMock(return_value=[])
    attempt = _attempt(datetime.now(UTC))
    service.repo.create_failed_attempt = AsyncMock(return_value=attempt)

    lock_until, triggered, count = await service.register_failed_attempt(
        "postgres@example.com", None
    )

    assert lock_until is not None
    assert triggered is True
    assert count == 1
    db.execute.assert_awaited_once()
    db.flush.assert_awaited_once()
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_register_failed_attempt_skips_postgres_lock_for_sqlite(
    monkeypatch,
) -> None:
    from app.core.config import settings
    from app.services.auth.lockout import LockoutService

    monkeypatch.setattr(settings.security, "auth_lockout_thresholds", "1:30")
    db = AsyncMock()
    service = LockoutService(db)
    service._is_postgresql = False
    service._prune_stale_attempts = AsyncMock()
    service._fetch_recent_attempts = AsyncMock(return_value=[])
    service.repo.create_failed_attempt = AsyncMock(
        return_value=_attempt(datetime.now(UTC))
    )

    await service.register_failed_attempt("sqlite@example.com", None)

    db.execute.assert_not_awaited()
    db.flush.assert_awaited_once()
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_clear_failed_attempts_commits_and_returns_count(monkeypatch) -> None:
    from app.core.config import settings
    from app.services.auth.lockout import LockoutService

    monkeypatch.setattr(settings.security, "auth_lockout_thresholds", "2:10")
    db = AsyncMock()
    service = LockoutService(db)
    service.repo.clear_failed_attempts = AsyncMock(return_value=4)

    count = await service.clear_failed_attempts("clear@example.com")

    assert count == 4
    service.repo.clear_failed_attempts.assert_awaited_once_with("clear@example.com")
    db.commit.assert_awaited_once()
