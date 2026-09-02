"""Behavior and failure-path tests for notification core services.

Pure-function branches (``_current_local_time``, ``_plain_text``,
``_coerce_optional_text``, ``_normalize_translation_map``, ``_build_delivery_row``,
``_ensure_aware``) plus real-DB coverage for ``_fetch_active_user_ids`` /
``_fetch_admin_ids`` (L159-194) including the broadcast safety-limit warning.
"""

from __future__ import annotations

import datetime as dt
import uuid
from datetime import UTC
from types import SimpleNamespace

import pytest

from app.services.notifications import core

# ---------------------------------------------------------------------------
# _current_local_time
# ---------------------------------------------------------------------------


def test_current_local_time_no_user_uses_utc():
    result = core._current_local_time(None)
    assert isinstance(result, dt.time)
    assert result.tzinfo is None


def test_current_local_time_valid_timezone():
    user = SimpleNamespace(preferences=SimpleNamespace(timezone="Europe/Moscow"))
    result = core._current_local_time(user)
    assert isinstance(result, dt.time)


def test_current_local_time_invalid_timezone_falls_back_to_utc():
    user = SimpleNamespace(preferences=SimpleNamespace(timezone="Not/AZone"))
    result = core._current_local_time(user)
    assert isinstance(result, dt.time)


def test_current_local_time_blank_and_non_string_timezones():
    blank = SimpleNamespace(preferences=SimpleNamespace(timezone="   "))
    non_str = SimpleNamespace(preferences=SimpleNamespace(timezone=123))
    no_prefs = SimpleNamespace(preferences=None)
    for user in (blank, non_str, no_prefs):
        assert isinstance(core._current_local_time(user), dt.time)


# ---------------------------------------------------------------------------
# _plain_text / _coerce_optional_text
# ---------------------------------------------------------------------------


def test_plain_text_none_and_blank():
    assert core._plain_text(None) is None
    assert core._plain_text("   ") is None
    assert core._plain_text("<p>  </p>") is None


def test_plain_text_strips_html_and_collapses_whitespace():
    assert core._plain_text("<p>Hello   <b>world</b></p>") == "Hello world"


def test_plain_text_limit_shortens():
    long_text = "word " * 50
    result = core._plain_text(long_text, limit=20)
    assert result is not None
    assert len(result) <= 20
    assert result.endswith("…")


def test_coerce_optional_text():
    assert core._coerce_optional_text(None) is None
    assert core._coerce_optional_text("  ") is None
    assert core._coerce_optional_text("  x  ") == "x"
    assert core._coerce_optional_text(42) == "42"


# ---------------------------------------------------------------------------
# _normalize_translation_map
# ---------------------------------------------------------------------------


def test_normalize_translation_map_empty_inputs():
    assert core._normalize_translation_map(None) == {}
    assert core._normalize_translation_map({}) == {}


def test_normalize_translation_map_filters_unsupported_and_empty():
    result = core._normalize_translation_map(
        {
            "RU": "  Привет  ",
            "en": "Hello",
            "xx": "skip-unsupported",
            "de": None,
            "ru ": "",
        }
    )
    assert result == {"ru": "Привет", "en": "Hello"}


# ---------------------------------------------------------------------------
# _build_delivery_row
# ---------------------------------------------------------------------------


def test_build_delivery_row_minimal():
    nid = uuid.uuid4()
    created = dt.datetime.now(UTC)
    row = core._build_delivery_row(nid, created, status="skipped")
    assert row["notification_id"] == nid
    assert row["status"] == "skipped"
    assert row["delivered_at"] is None
    # Delivery rows intentionally keep a uniform INSERT shape across
    # PostgreSQL batches; absent response metadata is represented as NULL.
    assert row["status_code"] is None
    assert row["detail"] is None


def test_build_delivery_row_full():
    nid = uuid.uuid4()
    created = dt.datetime.now(UTC)
    attempted = created + dt.timedelta(seconds=1)
    row = core._build_delivery_row(
        nid,
        created,
        status="sent",
        subscription_id=uuid.uuid4(),
        attempted_at=attempted,
        delivered=True,
        status_code=201,
        detail="ok",
    )
    assert row["delivered_at"] == attempted
    assert row["status_code"] == 201
    assert row["detail"] == "ok"


# ---------------------------------------------------------------------------
# _ensure_aware
# ---------------------------------------------------------------------------


def test_ensure_aware_none_returns_now():
    before = dt.datetime.now(UTC)
    result = core._ensure_aware(None)
    after = dt.datetime.now(UTC)
    assert before <= result <= after


def test_ensure_aware_naive_gets_utc():
    naive = dt.datetime(2026, 6, 1, 12, 0, 0)
    result = core._ensure_aware(naive)
    assert result.tzinfo is UTC


def test_ensure_aware_aware_passthrough():
    aware = dt.datetime(2026, 6, 1, 12, 0, 0, tzinfo=UTC)
    assert core._ensure_aware(aware) is aware


# ---------------------------------------------------------------------------
# _fetch_active_user_ids / _fetch_admin_ids (real DB)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fetch_active_user_ids_filters_and_excludes(db_session, user_factory):
    active_a = await user_factory()
    active_b = await user_factory()
    inactive = await user_factory(is_active=False)

    ids = await core._fetch_active_user_ids(db_session)
    assert active_a.id in ids
    assert active_b.id in ids
    assert inactive.id not in ids

    excluded = await core._fetch_active_user_ids(
        db_session, exclude=[active_a.id, None]
    )
    assert active_a.id not in excluded
    assert active_b.id in excluded


@pytest.mark.asyncio
async def test_fetch_active_user_ids_warns_at_safety_limit(
    db_session, user_factory, monkeypatch, caplog
):
    await user_factory()
    await user_factory()
    monkeypatch.setattr(core, "_MAX_BROADCAST_RECIPIENTS", 1)

    with caplog.at_level("WARNING"):
        ids = await core._fetch_active_user_ids(db_session)
    assert len(ids) == 1
    assert any("PERF-20-01" in rec.message for rec in caplog.records)


@pytest.mark.asyncio
async def test_fetch_admin_ids_only_active_admins(db_session, user_factory):
    admin = await user_factory(role="admin")
    inactive_admin = await user_factory(role="admin", is_active=False)
    student = await user_factory(role="student")

    ids = await core._fetch_admin_ids(db_session)
    assert admin.id in ids
    assert inactive_admin.id not in ids
    assert student.id not in ids
