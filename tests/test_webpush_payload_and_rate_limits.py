"""Payload, transport, and rate-limit tests for app/services/webpush.py.

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

import asyncio
import uuid
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

import app.services.webpush as webpush_module
from app.services.webpush import (
    _get_sync_url,
    _initialize_sync_resources,
    _mask_endpoint,
    _normalize_payload,
    _redact_urls_in_error,
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

    def test_ipv6_endpoint_mask_keeps_brackets_and_hides_path(self) -> None:
        endpoint_path = "push-token-fixture"

        masked = _mask_endpoint(f"https://[2001:4860:4860::8888]/{endpoint_path}")

        assert masked is not None
        assert masked.startswith("https://[2001:4860:4860::8888]/…#")
        assert endpoint_path not in masked


class TestEndpointValidationEdges:
    def test_ip_literal_guard_ignores_an_endpoint_without_hostname(self) -> None:
        webpush_module._reject_non_global_endpoint_host("/relative/path")

    @pytest.mark.parametrize("resolver_answer", [object(), "not-an-ip-address"])
    def test_reject_non_global_addresses_rejects_malformed_answers(
        self, resolver_answer: object
    ) -> None:
        with pytest.raises(ValueError, match="invalid address"):
            webpush_module._reject_non_global_resolved_addresses(
                [resolver_answer]  # type: ignore[list-item]
            )

    @pytest.mark.asyncio
    async def test_endpoint_without_hostname_fails_before_dns(self) -> None:
        with pytest.raises(ValueError, match="no hostname"):
            await webpush_module._validate_public_endpoint_dns("/relative/path")

    @pytest.mark.asyncio
    async def test_global_ip_literal_skips_dns_lookup(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        lookup = AsyncMock(side_effect=AssertionError("unexpected DNS lookup"))
        monkeypatch.setattr(asyncio.BaseEventLoop, "getaddrinfo", lookup)

        await webpush_module._validate_public_endpoint_dns("https://8.8.8.8/send")

        lookup.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_empty_dns_answer_fails_closed(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        lookup = AsyncMock(return_value=[])
        monkeypatch.setattr(asyncio.BaseEventLoop, "getaddrinfo", lookup)

        with pytest.raises(ValueError, match="returned no addresses"):
            await webpush_module._validate_public_endpoint_dns(
                "https://push.example.test/send"
            )

    @pytest.mark.parametrize(
        "resolver_result",
        [
            ["not-a-getaddrinfo-tuple"],
            [(0, 0, 0, "", "not-a-sockaddr-tuple")],
            [(0, 0, 0, "", ("93.184.216.34",))],
            [(0, 0, 0, "", (123, 443))],
        ],
    )
    @pytest.mark.asyncio
    async def test_malformed_dns_shapes_fail_closed(
        self,
        monkeypatch: pytest.MonkeyPatch,
        resolver_result: list[object],
    ) -> None:
        lookup = AsyncMock(return_value=resolver_result)
        monkeypatch.setattr(asyncio.BaseEventLoop, "getaddrinfo", lookup)

        with pytest.raises(ValueError, match="invalid address"):
            await webpush_module._validate_public_endpoint_dns(
                "https://push.example.test/send"
            )


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

        monkeypatch.setattr(
            webpush_module,
            "validate_and_resolve",
            lambda _url: [("93.184.216.34", 443)],
        )
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

    def test_transport_timeout_bounds_the_worker_thread_call(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A timed-out async caller must not leave an unbounded HTTP worker."""
        captured: dict[str, Any] = {}

        class _Session:
            def close(self) -> None:
                pass

        monkeypatch.setattr(
            webpush_module, "validate_public_https_url", lambda _url: None
        )
        monkeypatch.setattr(
            webpush_module, "validate_and_resolve", lambda _url: ["93.184.216.35"]
        )
        monkeypatch.setattr(
            webpush_module,
            "_create_pinned_webpush_session",
            lambda _url, _ip: _Session(),
        )
        monkeypatch.setattr(
            webpush_module, "webpush", lambda **kwargs: captured.update(kwargs)
        )

        result = send_web_push(
            SimpleNamespace(
                id=uuid.uuid4(),
                endpoint="https://push.example.test/send",
                user_id=uuid.uuid4(),
                p256dh="synthetic-public-key",
                auth="synthetic-auth",
                user=None,
            ),
            {"title": "T"},
        )

        assert result.status == "sent"
        assert captured.get("timeout") == webpush_module._PUSH_CALL_TIMEOUT_SECONDS

    def test_send_rejects_unspecified_dns_answer_before_transport(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        endpoint = "https://push.example.test/unspecified-address-fixture"
        factory = MagicMock()
        transport = MagicMock()
        monkeypatch.setattr(
            webpush_module, "validate_public_https_url", lambda _url: None
        )
        monkeypatch.setattr(
            webpush_module,
            "validate_and_resolve",
            lambda _url: [("::", 443)],
        )
        monkeypatch.setattr(webpush_module, "_create_pinned_webpush_session", factory)
        monkeypatch.setattr(webpush_module, "webpush", transport)

        result = send_web_push(
            SimpleNamespace(
                id=uuid.uuid4(),
                endpoint=endpoint,
                user_id=uuid.uuid4(),
                p256dh="synthetic-public-key",
                auth="synthetic-auth",
                user=None,
            ),
            {"title": "T"},
        )

        assert result.status == "error"
        assert result.error == "URL resolved to an unspecified address"
        factory.assert_not_called()
        transport.assert_not_called()

    def test_transport_error_redacts_endpoint_path_from_logs_and_detail(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        endpoint_path = "push-" + "token-fixture"
        endpoint = "https://push.example.test/" + endpoint_path

        class _Session:
            def close(self) -> None:
                pass

        monkeypatch.setattr(
            webpush_module, "validate_public_https_url", lambda _url: None
        )
        monkeypatch.setattr(
            webpush_module, "validate_and_resolve", lambda _url: ["93.184.216.35"]
        )
        monkeypatch.setattr(
            webpush_module,
            "_create_pinned_webpush_session",
            lambda _url, _ip: _Session(),
        )

        def fail_with_endpoint(**_kwargs: Any) -> None:
            raise ConnectionError(f"connection failed for {endpoint}")

        monkeypatch.setattr(webpush_module, "webpush", fail_with_endpoint)
        caplog.set_level("ERROR")

        result = send_web_push(
            SimpleNamespace(
                id=uuid.uuid4(),
                endpoint=endpoint,
                user_id=uuid.uuid4(),
                p256dh="public-key-fixture",
                auth="auth-fixture",
                user=None,
            ),
            {"title": "T"},
        )

        assert result.status == "error"
        assert endpoint_path not in (result.error or "")
        assert endpoint_path not in caplog.text

    def test_provider_error_redacts_endpoint_path_from_detail(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from pywebpush import WebPushException

        endpoint_path = "push-" + "token-fixture"
        endpoint = "https://push.example.test/" + endpoint_path

        class _Session:
            def close(self) -> None:
                pass

        monkeypatch.setattr(
            webpush_module, "validate_public_https_url", lambda _url: None
        )
        monkeypatch.setattr(
            webpush_module, "validate_and_resolve", lambda _url: ["93.184.216.35"]
        )
        monkeypatch.setattr(
            webpush_module,
            "_create_pinned_webpush_session",
            lambda _url, _ip: _Session(),
        )

        def fail_with_endpoint(**_kwargs: Any) -> None:
            raise WebPushException(f"provider failed for {endpoint}")

        monkeypatch.setattr(webpush_module, "webpush", fail_with_endpoint)

        result = send_web_push(
            SimpleNamespace(
                id=uuid.uuid4(),
                endpoint=endpoint,
                user_id=uuid.uuid4(),
                p256dh="public-key-fixture",
                auth="auth-fixture",
                user=None,
            ),
            {"title": "T"},
        )

        assert result.status == "error"
        assert endpoint_path not in (result.error or "")

    def test_error_redaction_matches_case_insensitive_url_schemes(self) -> None:
        endpoint_path = "push-token-fixture"

        result = _redact_urls_in_error(
            f"Provider returned HTTPS://push.example.test/{endpoint_path}"
        )

        assert endpoint_path not in result
        assert "push.example.test" in result
