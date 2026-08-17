"""Coverage tests for app/services/webpush.py (testing session 10).

Direct-call tests targeting the previously-uncovered branches: lazy sync-URL
driver rewrites + idempotent init (L58, L81), ``_mask_endpoint`` urlparse
ValueError fallback (L188-189), the ``_normalize_payload`` edge zone
(L319-320, 326-328, 334, 338, 348-356, 359-361, 365-369, 374, 376-379, 381,
385, 395, 397), ``_check_rate_limit`` short-circuit / delegate / exceeded
paths (L492-502), ``build_payload`` template-merge + actions/vibrate/silent/
timestamp/ttl branches (L547, 574, 576, 579, 586-591, 598-601), and the
Urgency/Topic header lines in ``send_web_push`` (L618, 621).

Harness mirrors tests/test_webpush_service_full.py (MagicMock subscription +
mocked pywebpush transport) with monkeypatch.setattr patching at the
consuming module per the session conventions. No DB access needed.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

import app.services.webpush as webpush_module
from app.core.ratelimit import RateLimitExceeded, RateLimitInfo
from app.services.webpush import (
    _check_rate_limit,
    _get_sync_url,
    _initialize_sync_resources,
    _mask_endpoint,
    _normalize_payload,
    build_payload,
    send_web_push,
)

# ---------------------------------------------------------------------------
# Lazy sync URL + idempotent init (L58, L81)
# ---------------------------------------------------------------------------


class TestSyncUrlAndInit:
    def test_get_sync_url_rewrites_asyncpg_driver(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """asyncpg URLs are rewritten to the sync psycopg driver (L58)."""
        monkeypatch.setattr(webpush_module, "_sync_url_cache", None)
        monkeypatch.setattr(
            webpush_module,
            "settings",
            SimpleNamespace(
                database_url="postgresql+asyncpg://u:p@localhost:5432/db"  # pragma: allowlist secret
            ),
        )
        url = _get_sync_url()
        assert url.drivername == "postgresql+psycopg"

    def test_get_sync_url_rewrites_aiosqlite_driver(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """aiosqlite URLs are rewritten to plain sqlite (L59-60)."""
        monkeypatch.setattr(webpush_module, "_sync_url_cache", None)
        monkeypatch.setattr(
            webpush_module,
            "settings",
            SimpleNamespace(database_url="sqlite+aiosqlite:///./x.db"),
        )
        url = _get_sync_url()
        assert url.drivername == "sqlite"

    def test_initialize_sync_resources_early_return(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When _Session is already set, no new engine is created (L81)."""
        sentinel_factory = MagicMock()
        fake_create_engine = MagicMock()
        monkeypatch.setattr(webpush_module, "_Session", sentinel_factory)
        monkeypatch.setattr(webpush_module, "create_engine", fake_create_engine)
        _initialize_sync_resources()
        fake_create_engine.assert_not_called()
        assert webpush_module._Session is sentinel_factory


# ---------------------------------------------------------------------------
# _mask_endpoint urlparse failure (L188-189)
# ---------------------------------------------------------------------------


class TestMaskEndpoint:
    def test_invalid_url_falls_back_to_digest_only(self) -> None:
        """urlparse ValueError (invalid IPv6 bracket) hits the fallback (L188-189)."""
        masked = _mask_endpoint("http://[not-a-valid-ipv6")
        assert masked is not None
        assert masked.startswith("…#")

    def test_blank_endpoint_returns_none(self) -> None:
        assert _mask_endpoint("   ") is None


# ---------------------------------------------------------------------------
# _normalize_payload edge zone (L319-397)
# ---------------------------------------------------------------------------


class TestNormalizePayloadEdges:
    def test_meta_source_is_read_once_for_stateful_mapping(self) -> None:
        """A stateful Mapping must not be observed twice for the same meta value."""

        class _StatefulMetaMapping(dict[str, Any]):
            def __init__(self) -> None:
                super().__init__()
                self.meta_reads = 0

            def get(self, key: str, default: Any = None) -> Any:
                if key != "_meta":
                    return super().get(key, default)
                self.meta_reads += 1
                return {"ttl": "300"} if self.meta_reads == 1 else None

        raw = _StatefulMetaMapping()

        _payload, meta = _normalize_payload(raw)

        assert meta["ttl"] == 300
        assert raw.meta_reads == 1

    def test_meta_ttl_invalid_in_meta_source_skipped(self) -> None:
        """Non-int ttl inside _meta is dropped (L319-320)."""
        _payload, meta = _normalize_payload(
            {"title": "T", "_meta": {"ttl": "garbage", "urgency": "high"}}
        )
        assert "ttl" not in meta
        assert meta["urgency"] == "high"

    def test_actions_in_raw_without_options(self) -> None:
        """Top-level actions populate options + actionUrls data (L326-328)."""
        payload, _meta = _normalize_payload(
            {
                "title": "T",
                "actions": [{"action": "go", "title": "Go", "url": "/go"}],
            }
        )
        assert payload["options"]["actions"] == [{"action": "go", "title": "Go"}]
        assert payload["data"]["actionUrls"] == {"go": "/go"}

    def test_option_key_with_none_value_skipped(self) -> None:
        """None-valued option keys in raw are skipped (L334)."""
        payload, _meta = _normalize_payload({"title": "T", "icon": None, "tag": "x"})
        assert "icon" not in payload["options"]
        assert payload["options"]["tag"] == "x"

    def test_vibrate_in_raw_without_options(self) -> None:
        """Top-level vibrate is sanitized into options (L338)."""
        payload, _meta = _normalize_payload({"title": "T", "vibrate": [5, 10.5]})
        assert payload["options"]["vibrate"] == [5, 10]

    def test_meta_extracted_from_options_block(self) -> None:
        """ttl/urgency inside options move into meta (L350-352, 355-356)."""
        payload, meta = _normalize_payload(
            {"options": {"body": "B", "ttl": "240", "urgency": "high"}}
        )
        assert meta["ttl"] == 240
        assert meta["urgency"] == "high"
        assert "ttl" not in payload["options"]
        assert "urgency" not in payload["options"]

    def test_meta_ttl_invalid_in_options_skipped(self) -> None:
        """Non-int ttl inside options is dropped, not crashed (L353-354)."""
        _payload, meta = _normalize_payload({"options": {"body": "B", "ttl": "bad"}})
        assert "ttl" not in meta

    def test_meta_from_options_does_not_override_meta_source(self) -> None:
        """_meta wins over options for the same meta key (L348-349)."""
        _payload, meta = _normalize_payload(
            {"_meta": {"urgency": "low"}, "options": {"body": "B", "urgency": "high"}}
        )
        assert meta["urgency"] == "low"

    def test_actions_inside_options(self) -> None:
        """Valid actions in options are re-prepared + urls extracted (L359-361)."""
        payload, _meta = _normalize_payload(
            {
                "options": {
                    "body": "B",
                    "actions": [{"action": "a1", "title": "A1", "url": "/a1"}],
                }
            }
        )
        assert payload["options"]["actions"] == [{"action": "a1", "title": "A1"}]
        assert payload["data"]["actionUrls"] == {"a1": "/a1"}

    def test_invalid_actions_inside_options_popped(self) -> None:
        """Garbage actions in options are removed entirely (L363)."""
        payload, _meta = _normalize_payload(
            {"options": {"body": "B", "actions": "garbage"}}
        )
        assert "actions" not in payload["options"]

    def test_vibrate_inside_options_sanitized(self) -> None:
        """Valid vibrate in options is kept after sanitizing (L365-367)."""
        payload, _meta = _normalize_payload(
            {"options": {"body": "B", "vibrate": [1, 2.7]}}
        )
        assert payload["options"]["vibrate"] == [1, 2]

    def test_vibrate_inside_options_invalid_popped(self) -> None:
        """Non-numeric vibrate in options is popped (L368-369)."""
        payload, _meta = _normalize_payload(
            {"options": {"body": "B", "vibrate": ["loud"]}}
        )
        assert "vibrate" not in payload["options"]

    def test_boolean_flags_coerced(self) -> None:
        """renotify/requireInteraction/silent are coerced to bool (L374)."""
        payload, _meta = _normalize_payload(
            {"options": {"body": "B", "renotify": 1, "silent": 0}}
        )
        assert payload["options"]["renotify"] is True
        assert payload["options"]["silent"] is False

    def test_timestamp_inside_options_coerced_to_int(self) -> None:
        """String timestamps become ints (L376-377)."""
        payload, _meta = _normalize_payload(
            {"options": {"body": "B", "timestamp": "99"}}
        )
        assert payload["options"]["timestamp"] == 99

    def test_timestamp_inside_options_invalid_popped(self) -> None:
        """Un-castable timestamps are dropped (L378-379)."""
        payload, _meta = _normalize_payload(
            {"options": {"body": "B", "timestamp": "abc"}}
        )
        assert "timestamp" not in payload["options"]

    def test_body_defaulted_when_options_present_without_body(self) -> None:
        """Missing body in options branch is defaulted to '' (L381)."""
        payload, _meta = _normalize_payload({"options": {"tag": "t"}})
        assert payload["options"]["body"] == ""

    def test_unknown_option_keys_dropped(self) -> None:
        """Keys outside _OPTION_KEYS do not survive cleaning (L385)."""
        payload, _meta = _normalize_payload(
            {"options": {"body": "B", "custom_key": "z"}}
        )
        assert "custom_key" not in payload["options"]

    def test_url_and_type_propagate_to_data(self) -> None:
        """Top-level url + type land in payload data (L395, 397)."""
        payload, _meta = _normalize_payload(
            {"title": "T", "url": "  /dest  ", "type": "alert"}
        )
        assert payload["data"]["url"] == "/dest"
        assert payload["data"]["type"] == "alert"


# ---------------------------------------------------------------------------
# _check_rate_limit (L492-502)
# ---------------------------------------------------------------------------


class TestCheckRateLimit:
    async def test_zero_limit_short_circuits(self) -> None:
        """limit <= 0 returns an allow-all info without touching Redis (L492-493)."""
        info = await _check_rate_limit("user:1", namespace="webpush", limit=0)
        assert info.allowed is True
        assert info.remaining == 0
        assert info.retry_after == 0

    async def test_disabled_rate_limiting_short_circuits(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """settings.rate_limit_enabled=False short-circuits (L492-493)."""
        monkeypatch.setattr(
            webpush_module, "settings", SimpleNamespace(rate_limit_enabled=False)
        )
        info = await _check_rate_limit("user:1", namespace="webpush", limit=7)
        assert info.allowed is True
        assert info.remaining == 7

    async def test_delegates_to_enforce_rate_limit(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Enabled path delegates to enforce_rate_limit with the strategy (L494-500)."""
        monkeypatch.setattr(
            webpush_module, "settings", SimpleNamespace(rate_limit_enabled=True)
        )
        expected = RateLimitInfo(True, 4, 0)
        fake_enforce = AsyncMock(return_value=expected)
        strategy = object()
        monkeypatch.setattr(webpush_module, "enforce_rate_limit", fake_enforce)
        monkeypatch.setattr(
            webpush_module, "get_default_strategy", MagicMock(return_value=strategy)
        )
        info = await _check_rate_limit("user:42", namespace="webpush", limit=5)
        assert info is expected
        fake_enforce.assert_awaited_once_with(
            identifier="user:42",
            limit=5,
            window_seconds=60,
            strategy=strategy,
        )

    async def test_rate_limit_exceeded_returns_exc_info(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """RateLimitExceeded is swallowed and its info returned (L501-502)."""
        monkeypatch.setattr(
            webpush_module, "settings", SimpleNamespace(rate_limit_enabled=True)
        )
        denied = RateLimitInfo(False, 0, 30)
        fake_enforce = AsyncMock(side_effect=RateLimitExceeded(denied))
        monkeypatch.setattr(webpush_module, "enforce_rate_limit", fake_enforce)
        monkeypatch.setattr(
            webpush_module, "get_default_strategy", MagicMock(return_value=object())
        )
        info = await _check_rate_limit("user:9", namespace="webpush", limit=3)
        assert info is denied


# ---------------------------------------------------------------------------
# build_payload edge branches (L547, 574-601)
# ---------------------------------------------------------------------------


class TestBuildPayloadEdges:
    @pytest.fixture
    def no_template(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Force the template-less branch so source == raw input."""
        monkeypatch.setattr(
            webpush_module, "render_notification_template", lambda *a, **k: {}
        )

    def test_template_merge_skips_none_values(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """None input values do not override template defaults (L547)."""
        monkeypatch.setattr(
            webpush_module,
            "render_notification_template",
            lambda *a, **k: {"title": "Template Title", "body": "TB"},
        )
        result = build_payload("typed", {"title": None, "icon": "i.png"})
        assert result["title"] == "Template Title"
        assert result["options"]["body"] == "TB"
        assert result["options"]["icon"] == "i.png"

    def test_actions_and_action_urls(self, no_template: None) -> None:
        """Actions populate options + actionUrls data (L574, 576)."""
        result = build_payload(
            "t",
            {
                "title": "T",
                "actions": [{"action": "open", "title": "Open", "url": "/x"}],
            },
        )
        assert result["options"]["actions"] == [{"action": "open", "title": "Open"}]
        assert result["data"]["actionUrls"] == {"open": "/x"}

    def test_vibrate_sanitized(self, no_template: None) -> None:
        """Vibrate list survives into options (L579)."""
        result = build_payload("t", {"title": "T", "vibrate": [10, 20.5]})
        assert result["options"]["vibrate"] == [10, 20]

    def test_silent_with_valid_timestamp(self, no_template: None) -> None:
        """silent + castable timestamp produce both options (L586-591)."""
        result = build_payload("t", {"title": "T", "silent": True, "timestamp": "1234"})
        assert result["options"]["silent"] is True
        assert result["options"]["timestamp"] == 1234

    def test_silent_with_invalid_timestamp_suppressed(self, no_template: None) -> None:
        """Un-castable timestamp is suppressed without crashing (L588-590)."""
        result = build_payload("t", {"title": "T", "silent": 0, "timestamp": "nope"})
        assert result["options"]["silent"] is False
        assert "timestamp" not in result["options"]

    def test_meta_ttl_string_coerced(self, no_template: None) -> None:
        """String ttl is cast to int into _meta (L598-599)."""
        result = build_payload("t", {"title": "T", "ttl": "300"})
        assert result["_meta"]["ttl"] == 300

    def test_meta_ttl_invalid_skipped(self, no_template: None) -> None:
        """Un-castable ttl is skipped; other meta keys survive (L600-601)."""
        result = build_payload("t", {"title": "T", "ttl": "soon", "urgency": "high"})
        assert result["_meta"] == {"urgency": "high"}


# ---------------------------------------------------------------------------
# send_web_push Urgency/Topic headers (L618, 621)
# ---------------------------------------------------------------------------


class TestSendWebPushHeaders:
    def _make_sub(self) -> MagicMock:
        sub = MagicMock()
        sub.id = uuid.uuid4()
        sub.endpoint = "https://push.example.com/headers"
        sub.user_id = uuid.uuid4()
        sub.p256dh = "key"
        sub.auth = "auth"  # pragma: allowlist secret
        sub.user = None
        return sub

    def test_urgency_and_topic_headers_set(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """urgency/topic meta become Urgency/Topic headers (L618, 621)."""
        captured: dict[str, Any] = {}

        def fake_webpush(**kwargs: Any) -> None:
            captured.update(kwargs)

        monkeypatch.setattr(webpush_module, "webpush", fake_webpush)
        result = send_web_push(
            self._make_sub(),
            {"title": "T", "urgency": "high", "topic": "sys-updates"},
        )
        assert result.status == "sent"
        headers = captured["headers"]
        assert headers["Urgency"] == "high"
        assert headers["Topic"] == "sys-updates"
        # high urgency maps to the 5-minute TTL
        assert headers["TTL"] == "300"
        assert captured["ttl"] == 300
