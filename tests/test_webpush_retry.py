"""Unit tests for ``app.services.webpush`` deterministic helpers + send path.

The module is 761 LOC and gradually-typed; we focus on the pure functions
and the ``send_web_push`` outcome matrix (stub ``pywebpush.webpush`` to
raise / succeed without touching network or DB):

* ``_mask_endpoint`` — hashed privacy mask, scheme/netloc preservation;
* ``_sanitize_vibrate`` — list/tuple gating, type coercion, dedupe rejection;
* ``_prepare_actions`` — action/title required, optional icon/url, type guards;
* ``_resolve_ttl`` — explicit ttl > urgency-mapped > default fallback;
* ``_is_user_in_quiet_hours`` — DND disabled, missing window, normal window,
  midnight-straddle window, equal start/end (always quiet);
* ``send_web_push`` — 200 → sent, 404/410 → gone, 5xx → error,
  ConnectionError/TimeoutError → error (subscription expiry path).
"""

from __future__ import annotations

import uuid
from datetime import time
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from pywebpush import WebPushException

from app.services.webpush import (
    _DEFAULT_TTL_SECONDS,
    _TTL_BY_URGENCY,
    _is_user_in_quiet_hours,
    _mask_endpoint,
    _prepare_actions,
    _resolve_ttl,
    _sanitize_vibrate,
    send_web_push,
)

# ── 1. _mask_endpoint ────────────────────────────────────────────────────────


class TestMaskEndpoint:
    """Endpoints are PII-adjacent — never log them in clear."""

    @pytest.mark.parametrize("inp", [None, "", "   "])
    def test_blank_input_returns_none(self, inp: str | None) -> None:
        assert _mask_endpoint(inp) is None

    def test_preserves_scheme_and_netloc(self) -> None:
        masked = _mask_endpoint("https://fcm.googleapis.com/wp/abc123/very-long-id")
        assert masked is not None
        assert masked.startswith("https://fcm.googleapis.com/…#")
        # 10 hex chars after the '#'.
        digest = masked.split("#")[-1]
        assert len(digest) == 10
        assert all(c in "0123456789abcdef" for c in digest)

    def test_falls_back_when_no_netloc(self) -> None:
        """No scheme/netloc → just the digest with a '…#' prefix."""
        masked = _mask_endpoint("not-a-url")
        assert masked is not None
        assert masked.startswith("…#")
        assert len(masked.split("#")[-1]) == 10

    def test_deterministic_digest(self) -> None:
        a = _mask_endpoint("https://fcm.googleapis.com/wp/x")
        b = _mask_endpoint("https://fcm.googleapis.com/wp/x")
        assert a == b

    def test_distinct_endpoints_distinct_masks(self) -> None:
        a = _mask_endpoint("https://fcm.googleapis.com/wp/x")
        b = _mask_endpoint("https://fcm.googleapis.com/wp/y")
        # Hash digests for distinct paths must differ.
        assert a != b


# ── 2. _sanitize_vibrate ─────────────────────────────────────────────────────


class TestSanitizeVibrate:
    @pytest.mark.parametrize("invalid", [None, "100,200", 100, {"a": 1}, object()])
    def test_non_list_or_tuple_returns_empty(self, invalid: object) -> None:
        assert _sanitize_vibrate(invalid) == []

    def test_empty_list(self) -> None:
        assert _sanitize_vibrate([]) == []

    def test_keeps_int_and_float_coerces_to_int(self) -> None:
        assert _sanitize_vibrate([100, 200.5, 300]) == [100, 200, 300]

    def test_drops_non_numeric_entries(self) -> None:
        assert _sanitize_vibrate([100, "x", None, 300, [1]]) == [100, 300]

    def test_accepts_tuple(self) -> None:
        assert _sanitize_vibrate((50, 100)) == [50, 100]


# ── 3. _prepare_actions ──────────────────────────────────────────────────────


class TestPrepareActions:
    def test_non_list_returns_empty(self) -> None:
        actions, urls = _prepare_actions("not a list")
        assert actions == []
        assert urls == {}

    def test_filters_invalid_entries(self) -> None:
        """Each action must have a non-empty ``action`` + ``title``."""
        actions, urls = _prepare_actions(
            [
                {"action": "open", "title": "Open"},
                {"action": "open"},  # missing title
                {"title": "no action"},  # missing action
                "not a dict",
                {"action": "  ", "title": "blank action"},  # action whitespace-only
            ]
        )
        assert len(actions) == 1
        assert actions[0] == {"action": "open", "title": "Open"}
        assert urls == {}

    def test_optional_icon_and_url(self) -> None:
        actions, urls = _prepare_actions(
            [
                {
                    "action": "view",
                    "title": "View",
                    "icon": "https://x/icon.png",
                    "url": "https://x/path",
                }
            ]
        )
        assert actions[0]["icon"] == "https://x/icon.png"
        assert urls == {"view": "https://x/path"}

    def test_blank_icon_or_url_dropped(self) -> None:
        actions, urls = _prepare_actions(
            [{"action": "view", "title": "View", "icon": "  ", "url": "   "}]
        )
        assert actions[0] == {"action": "view", "title": "View"}
        assert urls == {}


# ── 4. _resolve_ttl ──────────────────────────────────────────────────────────


class TestResolveTtl:
    def test_explicit_int_takes_priority(self) -> None:
        """An explicit positive ``ttl`` overrides urgency mapping."""
        assert _resolve_ttl({"ttl": 42, "urgency": "high"}) == 42

    def test_explicit_negative_ignored_falls_back_to_urgency(self) -> None:
        assert _resolve_ttl({"ttl": -10, "urgency": "high"}) == _TTL_BY_URGENCY["high"]

    def test_explicit_zero_ignored_falls_back(self) -> None:
        assert _resolve_ttl({"ttl": 0, "urgency": "high"}) == _TTL_BY_URGENCY["high"]

    def test_string_ttl_coerced_to_int(self) -> None:
        assert _resolve_ttl({"ttl": "120"}) == 120

    def test_unparseable_string_ttl_falls_back_to_default(self) -> None:
        assert _resolve_ttl({"ttl": "not-a-number"}) == _DEFAULT_TTL_SECONDS

    def test_urgency_high(self) -> None:
        assert _resolve_ttl({"urgency": "high"}) == _TTL_BY_URGENCY["high"]

    def test_urgency_low(self) -> None:
        assert _resolve_ttl({"urgency": "low"}) == _TTL_BY_URGENCY["low"]

    def test_unknown_urgency_falls_back_to_default(self) -> None:
        assert _resolve_ttl({"urgency": "extreme"}) == _DEFAULT_TTL_SECONDS

    def test_no_meta_uses_default(self) -> None:
        assert _resolve_ttl({}) == _DEFAULT_TTL_SECONDS


# ── 5. _is_user_in_quiet_hours ───────────────────────────────────────────────


def _user_with_dnd(
    *,
    enabled: bool,
    start: time | None = None,
    end: time | None = None,
) -> SimpleNamespace:
    """Build a mock User with DND preferences."""
    prefs = SimpleNamespace(dnd_enabled=enabled, dnd_start=start, dnd_end=end)
    return SimpleNamespace(preferences=prefs)


class TestIsUserInQuietHours:
    def test_no_user_returns_false(self) -> None:
        assert _is_user_in_quiet_hours(None) is False

    def test_user_without_preferences_returns_false(self) -> None:
        user = SimpleNamespace(preferences=None)
        assert _is_user_in_quiet_hours(user) is False

    def test_dnd_disabled_returns_false(self) -> None:
        user = _user_with_dnd(enabled=False)
        assert _is_user_in_quiet_hours(user, now_time=time(2, 0)) is False

    def test_dnd_enabled_no_window_means_always_quiet(self) -> None:
        """When DND is on and no window is set → always quiet."""
        user = _user_with_dnd(enabled=True)  # start/end both None
        assert _is_user_in_quiet_hours(user, now_time=time(13, 0)) is True

    def test_normal_window_inside(self) -> None:
        user = _user_with_dnd(enabled=True, start=time(22, 0), end=time(7, 0))
        assert _is_user_in_quiet_hours(user, now_time=time(2, 0)) is True

    def test_normal_window_outside(self) -> None:
        user = _user_with_dnd(enabled=True, start=time(22, 0), end=time(7, 0))
        assert _is_user_in_quiet_hours(user, now_time=time(13, 0)) is False

    def test_simple_window_inside(self) -> None:
        """When start < end, the window does not straddle midnight."""
        user = _user_with_dnd(enabled=True, start=time(13, 0), end=time(15, 0))
        assert _is_user_in_quiet_hours(user, now_time=time(14, 0)) is True

    def test_simple_window_boundary_inclusive_start_exclusive_end(self) -> None:
        """Half-open window: ``start <= now < end``."""
        user = _user_with_dnd(enabled=True, start=time(13, 0), end=time(15, 0))
        assert _is_user_in_quiet_hours(user, now_time=time(13, 0)) is True
        assert _is_user_in_quiet_hours(user, now_time=time(15, 0)) is False

    def test_equal_start_and_end_means_always_quiet(self) -> None:
        """Sentinel: setting start == end is read as 'all day'."""
        user = _user_with_dnd(enabled=True, start=time(8, 0), end=time(8, 0))
        assert _is_user_in_quiet_hours(user, now_time=time(15, 0)) is True


# ── 6. send_web_push — outcome matrix with pywebpush stubbed ────────────────


def _make_subscription() -> MagicMock:
    """Construct a PushSubscription-shaped mock with deterministic id."""
    sub = MagicMock()
    sub.id = uuid.uuid4()
    sub.user_id = uuid.uuid4()
    sub.endpoint = "https://fcm.googleapis.com/wp/abc"
    sub.p256dh = "p256dh-key"
    sub.auth = "auth-key"
    sub.user = None  # bypass quiet-hours / locale resolution
    return sub


def test_send_web_push_returns_sent_on_success() -> None:
    sub = _make_subscription()
    with patch("app.services.webpush.webpush") as mocked:
        mocked.return_value = None  # pywebpush returns None on success
        result = send_web_push(sub, {"title": "Hi", "options": {"body": "Body"}})
    assert result.status == "sent"
    assert result.subscription_id == sub.id
    assert result.endpoint == sub.endpoint
    assert result.error is None
    mocked.assert_called_once()


def _make_webpush_exception(status_code: int) -> WebPushException:
    """Construct a WebPushException with a stub HTTP response."""
    response = SimpleNamespace(status_code=status_code)
    exc = WebPushException(f"http {status_code}")
    exc.response = response  # type: ignore[attr-defined]
    return exc


@pytest.mark.parametrize("status", [404, 410])
def test_send_web_push_returns_gone_on_404_and_410(status: int) -> None:
    """404 / 410 indicates the push subscription has expired."""
    sub = _make_subscription()
    with patch("app.services.webpush.webpush") as mocked:
        mocked.side_effect = _make_webpush_exception(status)
        result = send_web_push(sub, {"title": "Hi"})
    assert result.status == "gone"
    assert result.status_code == status
    assert result.subscription_id == sub.id


def test_send_web_push_returns_error_on_5xx() -> None:
    """5xx is a transient server error — mark as error, not gone."""
    sub = _make_subscription()
    with patch("app.services.webpush.webpush") as mocked:
        mocked.side_effect = _make_webpush_exception(503)
        result = send_web_push(sub, {"title": "Hi"})
    assert result.status == "error"
    assert result.status_code == 503


def test_send_web_push_falls_back_to_message_match_when_no_response() -> None:
    """If the exception lacks a response object, status is parsed from the message."""
    sub = _make_subscription()
    with patch("app.services.webpush.webpush") as mocked:
        # Exception with no .response attribute but '410' in message.
        exc = WebPushException("Subscription expired (410 Gone)")
        mocked.side_effect = exc
        result = send_web_push(sub, {"title": "Hi"})
    assert result.status == "gone"


@pytest.mark.parametrize(
    "exc_factory",
    [
        lambda: ConnectionError("network down"),
        lambda: TimeoutError("vendor slow"),
        lambda: OSError("system error"),
        lambda: ValueError("bad cert"),
    ],
)
def test_send_web_push_returns_error_on_transport_failures(exc_factory) -> None:
    """ConnectionError / TimeoutError / OSError / ValueError are treated as errors."""
    sub = _make_subscription()
    with patch("app.services.webpush.webpush") as mocked:
        mocked.side_effect = exc_factory()
        result = send_web_push(sub, {"title": "Hi"})
    assert result.status == "error"
    assert result.error is not None
    assert result.subscription_id == sub.id
