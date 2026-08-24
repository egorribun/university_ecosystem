"""Pure-function and lifecycle tests for app/services/webpush.py.

Targets lightweight utilities that do not require database connections or
real VAPID credentials.
"""

from __future__ import annotations

from datetime import time
from unittest.mock import MagicMock, patch

from app.services import webpush as webpush_mod
from app.services.webpush import (
    _current_local_time,
    _is_user_in_quiet_hours,
    _mask_endpoint,
    _sanitize_vibrate,
    cleanup,
    json_dumps,
)

# ---------------------------------------------------------------------------
# json_dumps
# ---------------------------------------------------------------------------


def test_json_dumps_basic():
    assert json_dumps({"key": "value"}) == '{"key": "value"}'


def test_json_dumps_unicode_not_escaped():
    """Non-ASCII characters should NOT be escaped."""
    result = json_dumps({"msg": "Привет"})
    assert "Привет" in result


def test_json_dumps_empty_dict():
    assert json_dumps({}) == "{}"


# ---------------------------------------------------------------------------
# _mask_endpoint
# ---------------------------------------------------------------------------


def test_mask_endpoint_none():
    assert _mask_endpoint(None) is None


def test_mask_endpoint_empty_string():
    assert _mask_endpoint("") is None


def test_mask_endpoint_whitespace_only():
    assert _mask_endpoint("   ") is None


def test_mask_endpoint_valid_url():
    result = _mask_endpoint("https://fcm.googleapis.com/push/abc123")
    assert result is not None
    assert "https://fcm.googleapis.com" in result
    assert "#" in result  # includes digest


def test_mask_endpoint_no_scheme():
    result = _mask_endpoint("just-a-path/no-scheme")
    assert result is not None
    assert "#" in result  # just digest format


# ---------------------------------------------------------------------------
# _sanitize_vibrate
# ---------------------------------------------------------------------------


def test_sanitize_vibrate_list_of_ints():
    assert _sanitize_vibrate([100, 50, 200]) == [100, 50, 200]


def test_sanitize_vibrate_mixed_types():
    result = _sanitize_vibrate([100, "bad", 200.5, None])
    assert result == [100, 200]


def test_sanitize_vibrate_empty_list():
    assert _sanitize_vibrate([]) == []


def test_sanitize_vibrate_not_a_list():
    assert _sanitize_vibrate("not a list") == []
    assert _sanitize_vibrate(None) == []  # type: ignore[arg-type]
    assert _sanitize_vibrate(42) == []  # type: ignore[arg-type]


def test_sanitize_vibrate_tuple():
    """Tuples are also accepted."""
    result = _sanitize_vibrate((100, 200))
    assert result == [100, 200]


# ---------------------------------------------------------------------------
# _current_local_time
# ---------------------------------------------------------------------------


def test_current_local_time_no_user():
    t = _current_local_time(None)
    assert isinstance(t, time)
    # timezone-naive
    assert t.tzinfo is None


def test_current_local_time_user_with_valid_tz():
    mock_prefs = MagicMock()
    mock_prefs.timezone = "Europe/Warsaw"
    mock_user = MagicMock()
    mock_user.preferences = mock_prefs

    t = _current_local_time(mock_user)
    assert isinstance(t, time)
    assert t.tzinfo is None  # stripped


def test_current_local_time_user_with_invalid_tz():
    mock_prefs = MagicMock()
    mock_prefs.timezone = "Not/AReal/TZ"
    mock_user = MagicMock()
    mock_user.preferences = mock_prefs

    # Falls back to UTC without raising
    t = _current_local_time(mock_user)
    assert isinstance(t, time)


def test_current_local_time_user_with_no_preferences():
    mock_user = MagicMock()
    mock_user.preferences = None

    t = _current_local_time(mock_user)
    assert isinstance(t, time)


def test_current_local_time_user_tz_empty_string():
    mock_prefs = MagicMock()
    mock_prefs.timezone = "   "  # whitespace-only — falls back to UTC
    mock_user = MagicMock()
    mock_user.preferences = mock_prefs

    t = _current_local_time(mock_user)
    assert isinstance(t, time)


# ---------------------------------------------------------------------------
# _is_user_in_quiet_hours
# ---------------------------------------------------------------------------


def test_is_user_in_quiet_hours_no_user():
    assert not _is_user_in_quiet_hours(None)


def test_is_user_in_quiet_hours_dnd_disabled():
    mock_prefs = MagicMock()
    mock_prefs.dnd_enabled = False
    mock_user = MagicMock()
    mock_user.preferences = mock_prefs

    assert not _is_user_in_quiet_hours(mock_user)


def test_is_user_in_quiet_hours_no_start_end():
    """If start/end are None but dnd_enabled, returns True (all day DND)."""
    mock_prefs = MagicMock()
    mock_prefs.dnd_enabled = True
    mock_prefs.dnd_start = None
    mock_prefs.dnd_end = None
    mock_user = MagicMock()
    mock_user.preferences = mock_prefs

    assert _is_user_in_quiet_hours(mock_user)


def test_is_user_in_quiet_hours_same_start_end():
    """If start == end, returns True (all-day DND)."""
    t = time(10, 0)
    mock_prefs = MagicMock()
    mock_prefs.dnd_enabled = True
    mock_prefs.dnd_start = t
    mock_prefs.dnd_end = t
    mock_user = MagicMock()
    mock_user.preferences = mock_prefs

    assert _is_user_in_quiet_hours(mock_user)


def test_is_user_in_quiet_hours_within_daytime_window():
    """now_time between start and end (start < end) → in quiet hours."""
    start = time(22, 0)
    end = time(8, 0)
    # Overnight window: 22:00 to 08:00
    # now = 23:00 → in quiet hours
    now = time(23, 0)
    mock_prefs = MagicMock()
    mock_prefs.dnd_enabled = True
    mock_prefs.dnd_start = start
    mock_prefs.dnd_end = end
    mock_user = MagicMock()
    mock_user.preferences = mock_prefs

    assert _is_user_in_quiet_hours(mock_user, now_time=now)


def test_is_user_in_quiet_hours_outside_daytime_window():
    """now_time outside the overnight window → not in quiet hours."""
    start = time(22, 0)
    end = time(8, 0)
    now = time(12, 0)  # noon
    mock_prefs = MagicMock()
    mock_prefs.dnd_enabled = True
    mock_prefs.dnd_start = start
    mock_prefs.dnd_end = end
    mock_user = MagicMock()
    mock_user.preferences = mock_prefs

    assert not _is_user_in_quiet_hours(mock_user, now_time=now)


def test_is_user_in_quiet_hours_simple_daytime_window():
    """start < end (simple daytime window): 09:00-12:00."""
    start = time(9, 0)
    end = time(12, 0)
    mock_prefs = MagicMock()
    mock_prefs.dnd_enabled = True
    mock_prefs.dnd_start = start
    mock_prefs.dnd_end = end
    mock_user = MagicMock()
    mock_user.preferences = mock_prefs

    assert _is_user_in_quiet_hours(mock_user, now_time=time(10, 30))
    assert not _is_user_in_quiet_hours(mock_user, now_time=time(13, 0))


# ---------------------------------------------------------------------------
# cleanup()
# ---------------------------------------------------------------------------


def test_cleanup_no_op_when_nothing_initialized():
    """cleanup() should not raise when no engine is initialized."""
    # Reset module state
    original_engine = webpush_mod._sync_engine
    original_session = webpush_mod._Session
    webpush_mod._sync_engine = None
    webpush_mod._Session = None

    try:
        cleanup()  # should not raise
    finally:
        webpush_mod._sync_engine = original_engine
        webpush_mod._Session = original_session


def test_cleanup_disposes_engine():
    """cleanup() disposes of the engine and clears state."""
    mock_engine = MagicMock()
    mock_session = MagicMock()

    original_engine = webpush_mod._sync_engine
    original_session = webpush_mod._Session
    webpush_mod._sync_engine = mock_engine
    webpush_mod._Session = mock_session

    try:
        cleanup()
        mock_engine.dispose.assert_called_once()
        assert webpush_mod._sync_engine is None
        assert webpush_mod._Session is None
    finally:
        webpush_mod._sync_engine = original_engine
        webpush_mod._Session = original_session


# ---------------------------------------------------------------------------
# _get_sync_url
# ---------------------------------------------------------------------------


def test_get_sync_url_asyncpg_converts_to_psycopg():
    """asyncpg driver suffix should be replaced with psycopg."""
    from app.services.webpush import _get_sync_url

    original_cache = webpush_mod._sync_url_cache
    webpush_mod._sync_url_cache = None

    try:
        with patch("app.services.webpush.settings") as mock_settings:
            mock_settings.database_url = "postgresql+asyncpg://user:pass@localhost/db"  # pragma: allowlist secret
            url = _get_sync_url()
            assert "asyncpg" not in url.drivername
            assert "psycopg" in url.drivername
    finally:
        webpush_mod._sync_url_cache = original_cache


def test_get_sync_url_aiosqlite_converts_to_sqlite():
    """aiosqlite driver suffix should be replaced with sqlite."""
    from app.services.webpush import _get_sync_url

    original_cache = webpush_mod._sync_url_cache
    webpush_mod._sync_url_cache = None

    try:
        with patch("app.services.webpush.settings") as mock_settings:
            mock_settings.database_url = "sqlite+aiosqlite:///./test.db"
            url = _get_sync_url()
            assert "aiosqlite" not in url.drivername
            assert url.drivername == "sqlite"
    finally:
        webpush_mod._sync_url_cache = original_cache


def test_get_sync_url_caches_result():
    """Second call returns same cached URL without re-computation."""
    from app.services.webpush import _get_sync_url

    original_cache = webpush_mod._sync_url_cache
    webpush_mod._sync_url_cache = None

    try:
        with patch("app.services.webpush.settings") as mock_settings:
            mock_settings.database_url = "sqlite+aiosqlite:///./test.db"
            url1 = _get_sync_url()
            url2 = _get_sync_url()
            assert url1 is url2
    finally:
        webpush_mod._sync_url_cache = original_cache


def test_cleanup_branches():
    """Test all branches of engine/session cleanup."""
    from app.services.webpush import cleanup

    # 1. Both None
    with (
        patch("app.services.webpush._sync_engine", None),
        patch("app.services.webpush._Session", None),
    ):
        cleanup()

    # 2. _Session is not None, engine is None
    mock_session = MagicMock()
    with (
        patch("app.services.webpush._sync_engine", None),
        patch("app.services.webpush._Session", mock_session),
    ):
        cleanup()

    # 3. _Session is None, engine is not None
    mock_engine = MagicMock()
    with (
        patch("app.services.webpush._sync_engine", mock_engine),
        patch("app.services.webpush._Session", None),
    ):
        cleanup()
        mock_engine.dispose.assert_called_once()

    # 4. Engine dispose raises error
    mock_engine_err = MagicMock()
    mock_engine_err.dispose.side_effect = OSError("dispose failed")
    with (
        patch("app.services.webpush._sync_engine", mock_engine_err),
        patch("app.services.webpush._Session", None),
        patch("app.services.webpush.logger") as mock_logger,
    ):
        cleanup()
        mock_logger.exception.assert_called_once()


def test_get_push_semaphore_cached():
    """Test that _get_push_semaphore returns cached semaphore when not None."""
    from app.services.webpush import _get_push_semaphore

    mock_sem = MagicMock()
    with patch("app.services.webpush._push_semaphore", mock_sem):
        assert _get_push_semaphore() is mock_sem


def test_log_event_branches():
    """Test log event under various logger configurations and endpoints."""
    from app.services.webpush import _log_event

    # 1. Root logger is logger (same)
    with (
        patch("app.services.webpush.logger") as mock_logger,
        patch("logging.getLogger", return_value=mock_logger),
    ):
        _log_event("test_event", level=10, key="val")
        mock_logger.log.assert_called_once()

    # 2. Endpoint missing from fields
    with patch("app.services.webpush.logger") as mock_logger:
        _log_event("test_event", key="val")
        mock_logger.log.assert_called_once()


def test_current_local_time_invalid_timezone():
    """Test current local time using fallback UTC on invalid timezone."""
    from app.services.webpush import _current_local_time

    mock_user = MagicMock()
    mock_user.preferences.timezone = "Invalid/Timezone"

    result = _current_local_time(mock_user)
    assert result is not None
