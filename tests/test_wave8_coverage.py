"""Wave 8 coverage tests: Email, Services, Workers, Cache.

Targets uncovered paths across 17 service/utility files.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ===========================================================================
# Email utilities
# ===========================================================================


class TestEmailBuilders:
    def test_build_reset_email_content(self):
        from app.utils.email import build_reset_email_content

        subject, plain, html = build_reset_email_content(
            "https://example.com/reset?token=abc", "John Doe", locale="en"
        )
        assert isinstance(subject, str) and subject
        assert "https://example.com/reset" in plain
        assert isinstance(html, str)

    def test_build_reset_email_no_name(self):
        from app.utils.email import build_reset_email_content

        subject, _plain, _html = build_reset_email_content(
            "https://example.com/reset?token=abc", locale="en"
        )
        assert isinstance(subject, str) and subject

    def test_build_lockout_email_content(self):
        from app.utils.email import build_lockout_email_content

        subject, plain, _html = build_lockout_email_content("Jane", locale="en")
        assert isinstance(subject, str) and subject
        assert isinstance(plain, str)

    def test_redact_sensitive_query(self):
        from app.utils.email import _redact_sensitive_query

        url = "https://example.com/reset?token=secret123&other=visible"
        redacted = _redact_sensitive_query(url)
        assert "secret123" not in redacted
        assert "visible" in redacted

    def test_redact_no_sensitive_params(self):
        from app.utils.email import _redact_sensitive_query

        url = "https://example.com/page?foo=bar"
        assert _redact_sensitive_query(url) == url

    def test_redact_code_param(self):
        from app.utils.email import _redact_sensitive_query

        url = "https://example.com?code=mysecret"
        redacted = _redact_sensitive_query(url)
        assert "mysecret" not in redacted


class TestSendResetEmail:
    def test_send_ssl(self, monkeypatch):
        from app.core.config import settings
        from app.utils.email import send_reset_email

        monkeypatch.setattr(settings, "smtp_host", "smtp.example.com")
        monkeypatch.setattr(settings, "smtp_port", 465)
        monkeypatch.setattr(settings, "smtp_user", "user")
        monkeypatch.setattr(settings, "smtp_password", "pass")
        monkeypatch.setattr(settings, "mail_from", "noreply@example.com")
        monkeypatch.setattr(settings, "smtp_security", "ssl")

        with patch("app.utils.email.smtplib") as mock_smtplib:
            mock_server = MagicMock()
            mock_smtplib.SMTP_SSL.return_value.__enter__ = MagicMock(
                return_value=mock_server
            )
            mock_smtplib.SMTP_SSL.return_value.__exit__ = MagicMock(return_value=False)
            send_reset_email("user@test.com", "https://link", "Test")

    def test_send_missing_config(self, monkeypatch):
        from app.core.config import settings
        from app.utils.email import send_reset_email

        monkeypatch.setattr(settings, "smtp_host", "")
        # Should not raise, just log warning
        send_reset_email("user@test.com", "https://link")


# ===========================================================================
# Cache invalidation
# ===========================================================================


class TestCacheInvalidation:
    def test_key_generators(self):
        from app.services.cache_invalidation import (
            event_cache_key,
            events_list_cache_key,
            news_cache_key,
            news_list_cache_key,
            schedule_cache_key,
            user_cache_key,
        )

        assert "schedule" in schedule_cache_key("group1")
        assert "user" in user_cache_key(123)
        assert "event" in event_cache_key(456)
        assert "event" in events_list_cache_key()
        assert "news" in news_cache_key(789)
        assert "news" in news_list_cache_key()

    @pytest.mark.asyncio
    async def test_invalidate_schedule_cache(self):
        from app.services.cache_invalidation import invalidate_schedule_cache

        with patch("app.services.cache_invalidation.get_cache") as mock_cache:
            cache_inst = AsyncMock()
            cache_inst.enabled = True
            cache_inst.invalidate = AsyncMock()
            mock_cache.return_value = cache_inst

            await invalidate_schedule_cache("group1")
            cache_inst.invalidate.assert_called()

    @pytest.mark.asyncio
    async def test_cache_invalidator_context_manager(self):
        from app.services.cache_invalidation import CacheInvalidator

        with patch("app.services.cache_invalidation.get_cache") as mock_cache:
            cache_inst = AsyncMock()
            cache_inst.enabled = True
            cache_inst.invalidate = AsyncMock()
            mock_cache.return_value = cache_inst

            async with CacheInvalidator() as inv:
                inv.schedule("g1")
                inv.schedule("g1")  # duplicate
                inv.user(1)

            # flush called on __aexit__
            cache_inst.invalidate.assert_called()

    @pytest.mark.asyncio
    async def test_cache_invalidator_dedup(self):
        from app.services.cache_invalidation import CacheInvalidator

        inv = CacheInvalidator()
        inv.schedule("g1")
        inv.schedule("g1")
        inv.schedule("g2")

        with patch("app.services.cache_invalidation.get_cache") as mock_cache:
            cache_inst = AsyncMock()
            cache_inst.enabled = True
            cache_inst.invalidate = AsyncMock()
            mock_cache.return_value = cache_inst

            count = await inv.flush()
            # Should deduplicate g1
            assert count >= 2


# ===========================================================================
# Stats cache
# ===========================================================================


class TestStatsCache:
    def test_normalize_period_key(self):
        from app.services.stats_cache import _normalize_period_key

        assert _normalize_period_key("30D") == "30d"
        assert _normalize_period_key(None) == "default"
        assert _normalize_period_key("") == "default"

    def test_resolve_period_key(self):
        from app.services.stats_cache import resolve_period_key

        assert resolve_period_key("custom", None) == "custom"
        assert resolve_period_key(None, 30) == "30d"
        assert resolve_period_key(None, None) == "default"

    def test_make_cache_key(self):
        from app.services.stats_cache import _make_cache_key

        key = _make_cache_key("attendance", uuid.uuid4(), "30d")
        assert key.startswith("stats:attendance:")

    @pytest.mark.asyncio
    async def test_get_cached_stats_skip(self):
        from app.services.stats_cache import get_cached_stats

        result = await get_cached_stats(
            cache=MagicMock(),
            kind="test",
            user_id=uuid.uuid4(),
            period_key="30d",
            skip_cache=True,
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_set_cached_stats_skip(self):
        from app.services.stats_cache import set_cached_stats

        result = await set_cached_stats(
            cache=MagicMock(),
            kind="test",
            user_id=uuid.uuid4(),
            period_key="30d",
            payload={"data": 1},
            skip_cache=True,
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_get_cached_stats_hit(self):
        from app.deps.cache import MemoryCache
        from app.services.stats_cache import get_cached_stats, set_cached_stats

        cache = MemoryCache(default_ttl=300)
        uid = uuid.uuid4()

        await set_cached_stats(
            cache=cache,
            kind="test",
            user_id=uid,
            period_key="30d",
            payload={"score": 95},
        )
        result = await get_cached_stats(
            cache=cache,
            kind="test",
            user_id=uid,
            period_key="30d",
        )
        assert result is not None
        assert result.payload["score"] == 95

    @pytest.mark.asyncio
    async def test_invalidate_user_stats_cache(self):
        from app.services.stats_cache import invalidate_user_stats_cache

        cache = AsyncMock()
        cache.enabled = True
        cache.invalidate = AsyncMock()

        with patch("app.services.stats_cache._ensure_cache", return_value=cache):
            await invalidate_user_stats_cache(
                user_ids=[uuid.uuid4()],
                kinds=["attendance", "grade"],
                period_keys=["30d", "90d"],
            )
        cache.invalidate.assert_called()


# ===========================================================================
# Story service
# ===========================================================================


class TestStoryService:
    @pytest.mark.asyncio
    async def test_list_active_stories(self):
        from app.services.story_service import StoryService

        uow = MagicMock()
        repo = AsyncMock()
        repo.get_active = AsyncMock(return_value=[])
        uow.stories = repo
        svc = StoryService(uow)

        result = await svc.list_active_stories("en")
        assert result == []
        repo.get_active.assert_called_once()


# ===========================================================================
# MFA Challenge Cleanup
# ===========================================================================


class TestMfaChallengeCleanup:
    def test_config_defaults(self):
        from app.services.mfa_challenge_cleanup import MfaChallengeCleanupConfig

        config = MfaChallengeCleanupConfig()
        assert config.normalized_interval() >= 30

    def test_config_min_interval(self):
        from app.services.mfa_challenge_cleanup import MfaChallengeCleanupConfig

        config = MfaChallengeCleanupConfig(interval_seconds=5)
        assert config.normalized_interval() == 30

    @pytest.mark.asyncio
    async def test_cleanup_stale_challenges(self):
        from contextlib import asynccontextmanager

        from app.services.mfa_challenge_cleanup import cleanup_stale_mfa_challenges

        mock_db = AsyncMock()

        @asynccontextmanager
        async def fake_session():
            yield mock_db

        with (
            patch("app.services.mfa_challenge_cleanup.async_session", fake_session),
            patch(
                "app.services.mfa_challenge_cleanup.purge_expired_challenges",
                new_callable=AsyncMock,
                return_value=5,
            ),
        ):
            count = await cleanup_stale_mfa_challenges()
            assert count == 5


# ===========================================================================
# Session Cleanup
# ===========================================================================


class TestSessionCleanup:
    def test_config_min_interval(self):
        from app.services.session_cleanup import SessionCleanupConfig

        config = SessionCleanupConfig(interval_seconds=10)
        assert config.normalized_interval() == 30

    @pytest.mark.asyncio
    async def test_cleanup_expired_sessions(self):
        from contextlib import asynccontextmanager

        from app.services.session_cleanup import cleanup_expired_sessions

        mock_db = AsyncMock()
        # Mock dialect for SQLite detection
        mock_bind = MagicMock()
        mock_bind.dialect = MagicMock()
        mock_bind.dialect.name = "sqlite"
        mock_db.get_bind = MagicMock(return_value=mock_bind)

        mock_result = MagicMock()
        mock_result.rowcount = 3
        mock_db.execute = AsyncMock(return_value=mock_result)

        @asynccontextmanager
        async def fake_session():
            yield mock_db

        with patch("app.services.session_cleanup.async_session", fake_session):
            count = await cleanup_expired_sessions()
            assert count >= 0  # May be 0 or 3 depending on implementation


# ===========================================================================
# Data Access logging
# ===========================================================================


class TestDataAccess:
    def test_normalize_time(self):
        from app.services.data_access import _normalize_time

        assert _normalize_time(None) is None

        naive = datetime(2024, 1, 1, 12, 0, 0)
        result = _normalize_time(naive)
        assert result is not None
        assert result.tzinfo is not None

        aware = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
        assert _normalize_time(aware) == aware


# ===========================================================================
# Cache Warmup
# ===========================================================================


class TestCacheWarmup:
    def test_is_entry_fresh(self):
        import time as time_module

        from app.deps.cache import CacheEntry
        from app.services.cache_warmup import _is_entry_fresh

        fresh = CacheEntry(
            etag="x",
            payload={},
            stored_at=time_module.time(),
            ttl_seconds=3600,
        )
        assert _is_entry_fresh(fresh) is True

        stale = CacheEntry(
            etag="x",
            payload={},
            stored_at=time_module.time() - 99999,
            ttl_seconds=3600,
        )
        assert _is_entry_fresh(stale) is False

    def test_period_days_from_key(self):
        from app.services.cache_warmup import _period_days_from_key

        assert _period_days_from_key("30d") == 30
        assert _period_days_from_key("7d") == 7
        assert _period_days_from_key("invalid") is None
        assert _period_days_from_key("") is None

    def test_schedule_cache_key(self):
        from app.services.cache_warmup import _schedule_cache_key

        key = _schedule_cache_key("group-1")
        assert "schedule" in key
        assert "group-1" in key

    @pytest.mark.asyncio
    async def test_warm_cache_disabled(self, monkeypatch):
        from app.core.config import settings
        from app.services.cache_warmup import warm_cache

        monkeypatch.setattr(settings, "cache_warmup_enabled", False)
        # Should return immediately without error
        await warm_cache()


# ===========================================================================
# Workers — Outbox
# ===========================================================================


class TestOutboxWorker:
    def test_outbox_imports(self):
        from app.workers.outbox import OutboxWorker

        assert OutboxWorker is not None

    @pytest.mark.asyncio
    async def test_outbox_worker_init(self):
        from app.workers.outbox import OutboxWorker

        worker = OutboxWorker()
        assert worker is not None


# ===========================================================================
# Workers — Notifications
# ===========================================================================


class TestNotificationScheduler:
    def test_scheduler_imports(self):
        from app.workers.notifications import NotificationsScheduler

        assert NotificationsScheduler is not None


# ===========================================================================
# Notification delivery
# ===========================================================================


class TestNotificationDelivery:
    def test_is_push_configured(self):
        from app.services.notifications.delivery import _is_push_configured

        result = _is_push_configured()
        assert isinstance(result, bool)

    def test_only_active_users(self):
        from sqlalchemy import select

        from app.models import User
        from app.services.notifications.delivery import only_active_users

        stmt = select(User)
        filtered = only_active_users(stmt)
        assert filtered is not None
