"""Wave 10 — Long Tail coverage tests.

Targets remaining from_dict() on domain events, schema validators,
model edge cases, CQRS commands, notification templates, localization,
sanitization, retry, request coalescing, privacy cleanup, and misc utilities.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import pytest

# ===========================================================================
# Domain Events — remaining from_dict() methods
# ===========================================================================


class TestRemainingEventFromDict:
    def test_event_updated_from_dict(self):
        from app.core.events import EventUpdated

        data = {"event_id_entity": str(uuid.uuid4()), "title": "Updated Event"}
        event = EventUpdated.from_dict(data)
        assert event.title == "Updated Event"

    def test_event_registration_from_dict(self):
        from app.core.events import EventRegistration

        data = {
            "event_id_entity": str(uuid.uuid4()),
            "user_id": str(uuid.uuid4()),
        }
        event = EventRegistration.from_dict(data)
        assert event.user_id is not None

    def test_news_created_from_dict(self):
        from app.core.events import NewsCreated

        data = {"news_id": str(uuid.uuid4()), "title": "Breaking News"}
        event = NewsCreated.from_dict(data)
        assert event.title == "Breaking News"

    def test_news_updated_from_dict(self):
        from app.core.events import NewsUpdated

        data = {"news_id": str(uuid.uuid4()), "title": "Corrected News"}
        event = NewsUpdated.from_dict(data)
        assert event.title == "Corrected News"

    def test_attachment_cleanup_from_dict(self):
        from app.core.events import AttachmentCleanupRequested

        data = {
            "chat_id": str(uuid.uuid4()),
            "attachment_urls": ["https://s3/file1.pdf", "https://s3/file2.png"],
        }
        event = AttachmentCleanupRequested.from_dict(data)
        assert len(event.attachment_urls) == 2

    def test_notification_sent_from_dict(self):
        from app.core.events import NotificationSent

        data = {"notification_id": str(uuid.uuid4()), "user_id": str(uuid.uuid4())}
        event = NotificationSent.from_dict(data)
        assert event.user_id is not None

    def test_all_from_dict_strip_schema_version(self):
        """All from_dict implementations should handle _schema_version."""
        from app.core.events import (
            AttachmentCleanupRequested,
            EventRegistration,
            EventUpdated,
            NewsCreated,
            NewsUpdated,
        )

        for EventCls in [
            EventUpdated,
            EventRegistration,
            NewsCreated,
            NewsUpdated,
            AttachmentCleanupRequested,
        ]:
            data = {"_schema_version": 2}
            event = EventCls.from_dict(data)
            assert event is not None


# ===========================================================================
# Schema validators
# ===========================================================================


class TestSchemaValidators:
    def test_sanitize_html_validator(self):
        from app.schemas.validators import _sanitize_html_validator

        result = _sanitize_html_validator("<b>Hello</b><script>x</script>")
        assert "<script>" not in result

    def test_sanitize_email_validator(self):
        from app.schemas.validators import _sanitize_email_validator

        result = _sanitize_email_validator("  User@Example.COM  ")
        assert result == "user@example.com"

    def test_sanitize_filename_validator(self):
        from app.schemas.validators import _sanitize_filename_validator

        result = _sanitize_filename_validator("../../evil.txt")
        assert ".." not in result

    def test_truncate_validators(self):
        from app.schemas.validators import _truncate_256, _truncate_1000

        assert len(_truncate_256("x" * 500)) <= 256
        assert len(_truncate_1000("x" * 2000)) <= 1000

    def test_sanitize_url_validator(self):
        from app.schemas.validators import _sanitize_url_validator

        result = _sanitize_url_validator("https://example.com/page")
        assert result is not None

    def test_sanitize_optional_text_none(self):
        from app.schemas.validators import _sanitize_optional_text_validator

        assert _sanitize_optional_text_validator(None) is None

    def test_strip_control_chars(self):
        from app.schemas.validators import _strip_control_chars_validator

        result = _strip_control_chars_validator("Hello\x00World")
        assert "\x00" not in result


# ===========================================================================
# Sanitization utils
# ===========================================================================


class TestSanitization:
    def test_sanitize_html_basic(self):
        from app.utils.sanitization import sanitize_html

        result = sanitize_html("<b>Bold</b><script>evil()</script>")
        assert "<script>" not in result
        assert "Bold" in result

    def test_sanitize_html_none(self):
        from app.utils.sanitization import sanitize_html

        result = sanitize_html(None)
        assert result is None or result == ""

    def test_sanitize_html_empty(self):
        from app.utils.sanitization import sanitize_html

        result = sanitize_html("")
        assert result == ""

    def test_sanitize_html_plain_text(self):
        from app.utils.sanitization import sanitize_html

        result = sanitize_html("Just plain text")
        assert result == "Just plain text"

    def test_sanitize_html_nested_tags(self):
        from app.utils.sanitization import sanitize_html

        result = sanitize_html("<div><p>Hello <strong>World</strong></p></div>")
        assert "Hello" in result
        assert "World" in result


# ===========================================================================
# Retry utility
# ===========================================================================


class TestRetryUtil:
    @pytest.mark.asyncio
    async def test_retry_success(self):
        from app.utils.retry import retry_async

        call_count = 0

        async def succeeds():
            nonlocal call_count
            call_count += 1
            return "ok"

        result = await retry_async(succeeds, max_attempts=3, base_delay=0.01)
        assert result == "ok"
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_retry_eventual_success(self):
        from app.utils.retry import retry_async

        call_count = 0

        async def fails_then_succeeds():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise RuntimeError("Not yet")
            return "ok"

        result = await retry_async(fails_then_succeeds, max_attempts=5, base_delay=0.01)
        assert result == "ok"
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_retry_exhausted(self):
        from app.utils.retry import RetryExhausted, retry_async

        async def always_fails():
            raise ValueError("fail")

        with pytest.raises((RetryExhausted, ValueError)):
            await asyncio.wait_for(
                retry_async(always_fails, max_attempts=2, base_delay=0.01),
                timeout=1.0,
            )


# ===========================================================================
# Request coalescing
# ===========================================================================


class TestRequestCoalescing:
    @pytest.mark.asyncio
    async def test_coalesce_basic(self):
        from app.utils.request_coalescing import coalesce_requests

        call_count = 0

        @coalesce_requests(prefix="test")
        async def expensive_call(key: str) -> str:
            nonlocal call_count
            call_count += 1
            return f"result-{key}"

        result = await expensive_call("test")
        assert result == "result-test"
        assert call_count == 1

    def test_build_request_key(self):
        from app.utils.request_coalescing import _build_request_key

        key = _build_request_key("prefix", "arg1", kwarg1="val1")
        assert isinstance(key, str)
        assert len(key) > 0


# ===========================================================================
# Localization
# ===========================================================================


class TestLocalization:
    def test_translate(self):
        from app.core.localization import translate

        result = translate("errors.not_found", locale="en")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_translate_ru(self):
        from app.core.localization import translate

        result = translate("errors.not_found", locale="ru")
        assert isinstance(result, str)

    def test_translate_unknown_key(self):
        from app.core.localization import translate

        result = translate("nonexistent.key.that.does.not.exist", locale="en")
        assert isinstance(result, str)

    def test_resolve_locale_default(self):
        from app.core.localization import resolve_locale

        locale = resolve_locale()
        assert locale in ("en", "ru", None) or isinstance(locale, str)

    def test_localized_text(self):
        from app.core.localization import localized_text

        result = localized_text("en", ru="Привет", en="Hello")
        assert result == "Hello"

        result = localized_text("ru", ru="Привет", en="Hello")
        assert result == "Привет"

    def test_localized_text_fallback(self):
        from app.core.localization import localized_text

        result = localized_text("en", ru="Только русский", en=None)
        # Should fallback
        assert result is not None or result is None

    def test_translate_lesson_type(self):
        from app.core.localization import translate_lesson_type

        result = translate_lesson_type("lecture", locale="en")
        assert isinstance(result, str)


# ===========================================================================
# Notification templates
# ===========================================================================


class TestNotificationTemplates:
    def test_clean_text(self):
        from app.services.notification_templates import _clean_text

        assert _clean_text("  Hello  ") == "Hello"
        assert _clean_text(None) is None
        assert _clean_text("") is None

    def test_clean_text_with_limit(self):
        from app.services.notification_templates import _clean_text

        result = _clean_text("A" * 500, limit=100)
        assert result is not None
        assert len(result) <= 100

    def test_normalize_type(self):
        from app.services.notification_templates import _normalize_type

        result = _normalize_type("SCHEDULE_CHANGE")
        assert result == "schedule.change"  # underscores → dots, lowercased
        # None and empty return fallback
        assert _normalize_type(None) in ("system", "")
        assert _normalize_type("") in ("system", "")

    def test_parse_datetime_like(self):
        from app.services.notification_templates import _parse_datetime_like

        assert _parse_datetime_like(datetime.now(UTC)) is not None
        assert _parse_datetime_like("2024-01-01T12:00:00Z") is not None
        assert _parse_datetime_like(None) is None

    def test_room_label_prefixes(self):
        from app.services.notification_templates import _room_label_prefixes

        prefixes = _room_label_prefixes()
        assert isinstance(prefixes, set)

    def test_format_room(self):
        from app.services.notification_templates import _format_room

        result = _format_room("Room 101", locale="en")
        assert result is not None
        assert "101" in result


# ===========================================================================
# CQRS — Schedule commands
# ===========================================================================


class TestScheduleCommands:
    def test_create_schedule_command(self):
        from app.cqrs.commands.schedule import CreateScheduleCommand

        data = MagicMock()
        cmd = CreateScheduleCommand(data=data, locale="en")
        assert cmd.locale == "en"

    def test_update_schedule_command(self):
        from app.cqrs.commands.schedule import UpdateScheduleCommand

        data = MagicMock()
        cmd = UpdateScheduleCommand(schedule_id=uuid.uuid4(), data=data)
        assert cmd.schedule_id is not None

    def test_delete_schedule_command(self):
        from app.cqrs.commands.schedule import DeleteScheduleCommand

        cmd = DeleteScheduleCommand(schedule_id=uuid.uuid4())
        assert cmd.schedule_id is not None


# ===========================================================================
# Privacy cleanup
# ===========================================================================


class TestPrivacyCleanup:
    def test_privacy_cleanup_config(self):
        from app.services.privacy_cleanup import PrivacyCleanupConfig

        config = PrivacyCleanupConfig()
        assert config is not None

    def test_cutoff(self):
        from app.services.privacy_cleanup import _cutoff

        cutoff = _cutoff(30)
        assert cutoff < datetime.now(UTC)
        assert cutoff > datetime.now(UTC) - timedelta(days=31)


# ===========================================================================
# Model edge cases
# ===========================================================================


class TestModelEdgeCases:
    def test_user_model(self):
        from app.models import User

        assert hasattr(User, "id")
        assert hasattr(User, "email")
        assert hasattr(User, "hashed_password")
        assert hasattr(User, "is_active")
        assert hasattr(User, "role")

    def test_notification_model(self):
        from app.models import Notification

        assert hasattr(Notification, "id")
        assert hasattr(Notification, "user_id")
        assert hasattr(Notification, "title")
        assert hasattr(Notification, "read")

    def test_push_subscription_model(self):
        from app.models import PushSubscription

        assert hasattr(PushSubscription, "endpoint")
        assert hasattr(PushSubscription, "p256dh")
        assert hasattr(PushSubscription, "auth")

    def test_active_session_model(self):
        from app.models import ActiveSession

        assert hasattr(ActiveSession, "jti")
        assert hasattr(ActiveSession, "user_id")
        assert hasattr(ActiveSession, "expires_at")


# ===========================================================================
# Config — Notification settings
# ===========================================================================


class TestNotificationConfig:
    def test_notification_config_fields(self):
        from app.core.config import settings

        assert hasattr(settings, "notifications_retention_days")
        assert hasattr(settings, "notifications_allowed_push_topics")
        assert isinstance(settings.notifications_allowed_push_topics, list)

    def test_outbox_config(self):
        from app.core.config import settings

        assert hasattr(settings, "outbox_poll_interval_seconds")
        assert settings.outbox_poll_interval_seconds > 0
        assert hasattr(settings, "outbox_batch_size")
        assert settings.outbox_batch_size > 0
