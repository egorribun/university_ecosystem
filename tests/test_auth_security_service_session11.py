"""Session 11 coverage: app/services/auth/security_service.py + analytics regression.

AuthSecurityService(db, locale) is tested with an AsyncMock db (the AsyncMock-db
idiom from tests/test_services_mock.py). ActiveSession instances are built as
plain un-flushed objects with only the attributes the methods read (expires_at,
mfa_verified_at, last_seen_at, id) — SQLAlchemy declarative __init__ accepts
arbitrary kwargs and unset Mapped columns read as None on a transient instance.

settings.mfa_step_up_ttl_seconds (default 300) is monkeypatched per test via the
imported singleton (same object as app.services.auth.security_service.settings).

NOTE: app/services/auth/security_service.py is already 100% covered (A0) via authed
integration fixtures; these are DIRECT unit tests that pin its expiry / MFA-TTL /
last-seen behavior precisely (a hot path on every authed request). They do not move
the coverage gate — they add regression protection.

Item-4 regression: AnalyticsService.get_user_activity raw SQL must reference the
real `event_attendance` table (app/models/events.py:126), NOT `event_attendees`.
analytics.py:200 was fixed `event_attendees` -> `event_attendance` in this session;
test_get_user_activity_sql_references_real_table guards it.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException, status

from app.core.config import settings
from app.models import ActiveSession
from app.services.analytics import AnalyticsService
from app.services.auth.security_service import AuthSecurityService


def _make_session(
    *,
    expires_at: datetime | None = None,
    mfa_verified_at: datetime | None = None,
    last_seen_at: datetime | None = None,
) -> ActiveSession:
    """Un-flushed ActiveSession with only the time fields the service reads.
    id is a real UUID so the sync_last_seen UPDATE .where(id == ...) compiles
    (never executed — db.execute is an AsyncMock)."""
    s = ActiveSession()
    s.id = uuid.uuid4()
    if expires_at is not None:
        s.expires_at = expires_at
    s.mfa_verified_at = mfa_verified_at
    s.last_seen_at = last_seen_at
    return s


@pytest.fixture
def db() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def svc(db: AsyncMock) -> AuthSecurityService:
    return AuthSecurityService(db=db, locale="en")


# ── validate_session_expiry ───────────────────────────────────────────────────
def test_validate_session_expiry_expired_raises(svc: AuthSecurityService) -> None:
    past = datetime.now(UTC) - timedelta(hours=1)
    session = _make_session(expires_at=past)
    with pytest.raises(HTTPException) as exc_info:
        svc.validate_session_expiry(session)
    assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
    assert exc_info.value.headers == {"WWW-Authenticate": "Bearer"}


def test_validate_session_expiry_future_passes(svc: AuthSecurityService) -> None:
    future = datetime.now(UTC) + timedelta(hours=1)
    session = _make_session(expires_at=future)
    assert svc.validate_session_expiry(session) is None


def test_validate_session_expiry_naive_expires_at_coerced(
    svc: AuthSecurityService,
) -> None:
    naive_future = (datetime.now(UTC) + timedelta(hours=1)).replace(tzinfo=None)
    session = _make_session(expires_at=naive_future)
    assert svc.validate_session_expiry(session) is None


def test_validate_session_expiry_naive_past_still_raises(
    svc: AuthSecurityService,
) -> None:
    naive_past = (datetime.now(UTC) - timedelta(hours=1)).replace(tzinfo=None)
    session = _make_session(expires_at=naive_past)
    with pytest.raises(HTTPException) as exc_info:
        svc.validate_session_expiry(session)
    assert exc_info.value.status_code == 401


# ── handle_mfa_ttl ─────────────────────────────────────────────────────────────
async def test_handle_mfa_ttl_zero_is_noop(
    svc: AuthSecurityService, db: AsyncMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "mfa_step_up_ttl_seconds", 0)
    old = datetime.now(UTC) - timedelta(days=7)
    session = _make_session(mfa_verified_at=old)
    await svc.handle_mfa_ttl(session)
    assert session.mfa_verified_at == old
    db.commit.assert_not_awaited()


async def test_handle_mfa_ttl_expired_clears_and_commits(
    svc: AuthSecurityService, db: AsyncMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "mfa_step_up_ttl_seconds", 300)
    session = _make_session(mfa_verified_at=datetime.now(UTC) - timedelta(seconds=600))
    await svc.handle_mfa_ttl(session)
    assert session.mfa_verified_at is None
    db.commit.assert_awaited_once()


async def test_handle_mfa_ttl_within_window_no_clear(
    svc: AuthSecurityService, db: AsyncMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "mfa_step_up_ttl_seconds", 300)
    recent = datetime.now(UTC) - timedelta(seconds=60)
    session = _make_session(mfa_verified_at=recent)
    await svc.handle_mfa_ttl(session)
    assert session.mfa_verified_at == recent
    db.commit.assert_not_awaited()


async def test_handle_mfa_ttl_none_verified_is_noop(
    svc: AuthSecurityService, db: AsyncMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "mfa_step_up_ttl_seconds", 300)
    session = _make_session(mfa_verified_at=None)
    await svc.handle_mfa_ttl(session)
    db.commit.assert_not_awaited()


async def test_handle_mfa_ttl_naive_verified_coerced_and_cleared(
    svc: AuthSecurityService, db: AsyncMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "mfa_step_up_ttl_seconds", 300)
    naive_old = (datetime.now(UTC) - timedelta(seconds=600)).replace(tzinfo=None)
    session = _make_session(mfa_verified_at=naive_old)
    await svc.handle_mfa_ttl(session)  # coercion prevents TypeError
    assert session.mfa_verified_at is None
    db.commit.assert_awaited_once()


# ── sync_last_seen ─────────────────────────────────────────────────────────────
async def test_sync_last_seen_none_writes(
    svc: AuthSecurityService, db: AsyncMock
) -> None:
    session = _make_session(last_seen_at=None)
    await svc.sync_last_seen(session)
    db.execute.assert_awaited_once()
    db.commit.assert_awaited_once()
    assert session.last_seen_at is not None


async def test_sync_last_seen_recent_no_write(
    svc: AuthSecurityService, db: AsyncMock
) -> None:
    recent = datetime.now(UTC) - timedelta(seconds=60)
    session = _make_session(last_seen_at=recent)
    await svc.sync_last_seen(session)  # cached_session defaults False (300s window)
    db.execute.assert_not_awaited()
    db.commit.assert_not_awaited()
    assert session.last_seen_at == recent


async def test_sync_last_seen_old_writes(
    svc: AuthSecurityService, db: AsyncMock
) -> None:
    old = datetime.now(UTC) - timedelta(seconds=400)  # 400s >= 300s
    session = _make_session(last_seen_at=old)
    await svc.sync_last_seen(session)
    db.execute.assert_awaited_once()
    db.commit.assert_awaited_once()
    assert session.last_seen_at > old


async def test_sync_last_seen_cached_uses_600s_window(
    svc: AuthSecurityService, db: AsyncMock
) -> None:
    # 400s ago: >= 300s (would write) but < 600s (cached => no write)
    age_400 = datetime.now(UTC) - timedelta(seconds=400)
    session = _make_session(last_seen_at=age_400)
    await svc.sync_last_seen(session, cached_session=True)
    db.execute.assert_not_awaited()
    db.commit.assert_not_awaited()
    assert session.last_seen_at == age_400


async def test_sync_last_seen_cached_writes_past_600s(
    svc: AuthSecurityService, db: AsyncMock
) -> None:
    age_700 = datetime.now(UTC) - timedelta(seconds=700)  # >= 600s
    session = _make_session(last_seen_at=age_700)
    await svc.sync_last_seen(session, cached_session=True)
    db.execute.assert_awaited_once()
    db.commit.assert_awaited_once()


async def test_sync_last_seen_naive_last_seen_coerced(
    svc: AuthSecurityService, db: AsyncMock
) -> None:
    naive_old = (datetime.now(UTC) - timedelta(seconds=400)).replace(tzinfo=None)
    session = _make_session(last_seen_at=naive_old)
    await svc.sync_last_seen(session)  # coercion prevents TypeError
    db.execute.assert_awaited_once()


# ── analytics.py:200 regression (event_attendees -> event_attendance) ─────────
async def test_get_user_activity_sql_references_real_table() -> None:
    """REGRESSION: get_user_activity's raw SQL must reference the real
    `event_attendance` table, not the non-existent `event_attendees`.
    Bug fixed at app/services/analytics.py:200 in session 11.
    """
    result_proxy = MagicMock()
    result_proxy.fetchall.return_value = []
    session = AsyncMock()
    session.execute = AsyncMock(return_value=result_proxy)
    svc = AnalyticsService()
    await svc.get_user_activity(session, uuid.uuid4())
    session.execute.assert_awaited_once()
    sql_text = str(session.execute.await_args.args[0])
    assert "event_attendance" in sql_text, (
        "get_user_activity SQL must FROM the real table event_attendance; "
        f"got:\n{sql_text}"
    )
    assert "event_attendees" not in sql_text, (
        "analytics.py:200 still references the non-existent table event_attendees"
    )
