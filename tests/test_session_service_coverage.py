"""Coverage tests for app/services/session_service.py (testing session 9).

Targets the previously-uncovered service surface: session listing / lookup /
revocation methods (L237-296), the Redis-registration warn path (L41-52),
``_normalize_sub`` validation (L154-162) and the concurrent-session limit
branches (L164-192).

Harness mirrors tests/test_auth_jwt_rs256.py (``_make_session_service``) and
the real-DB recipe from tests/test_active_session_repository.py (explicit
``created_at``, real ``user_factory()`` ids through all FK columns).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ActiveSession
from app.services import session_service as session_service_module
from app.services.session_service import SessionService, register_session_bg


def _make_session_service(db_session: AsyncSession) -> SessionService:
    """Mirror W136 SW1 helper — bypasses async UnitOfWork pattern for unit tests."""
    from app.repositories.unit_of_work import UnitOfWork

    uow = UnitOfWork(lambda: db_session)
    uow._session = db_session  # type: ignore[assignment]
    uow._bind_repositories(db_session)
    return SessionService(uow)


async def _add_session(
    db: AsyncSession,
    user_id: uuid.UUID,
    *,
    jti: str | None = None,
    revoked: bool = False,
    created_offset_minutes: int = 0,
) -> ActiveSession:
    now = datetime.now(UTC)
    session = ActiveSession(
        user_id=user_id,
        jti=jti or str(uuid.uuid4()),
        created_at=now + timedelta(minutes=created_offset_minutes),
        expires_at=now + timedelta(hours=1),
        revoked_at=now if revoked else None,
        last_seen_at=now,
        ip_address="127.0.0.1",
        user_agent="pytest",
    )
    db.add(session)
    await db.flush()
    return session


# ---------------------------------------------------------------------------
# register_session_bg — Redis failure warn path (L41-52)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_register_session_bg_swallows_connection_error(monkeypatch):
    """Redis registration is fire-and-forget: ConnectionError is logged, not raised."""

    async def _raise_backend():
        raise ConnectionError("redis down")

    monkeypatch.setattr(session_service_module, "get_session_backend", _raise_backend)
    # Must not raise.
    await register_session_bg(
        uuid.uuid4(),
        "jti-bg",
        datetime.now(UTC) + timedelta(hours=1),
        "127.0.0.1",
        "pytest",
    )


@pytest.mark.asyncio
async def test_register_session_bg_happy_path(monkeypatch):
    """Successful path forwards metadata to the session backend."""
    calls: list[dict] = []

    class _Backend:
        async def register_session(self, **kwargs):
            calls.append(kwargs)

    async def _get_backend():
        return _Backend()

    monkeypatch.setattr(session_service_module, "get_session_backend", _get_backend)
    user_id = uuid.uuid4()
    await register_session_bg(
        user_id,
        "jti-ok",
        datetime.now(UTC) + timedelta(hours=1),
        "10.0.0.1",
        "agent",
    )
    assert len(calls) == 1
    assert calls[0]["user_id"] == str(user_id)
    assert calls[0]["jti"] == "jti-ok"
    assert calls[0]["metadata"]["ip_address"] == "10.0.0.1"


# ---------------------------------------------------------------------------
# _normalize_sub (L154-162)
# ---------------------------------------------------------------------------


def test_normalize_sub_uuid_passthrough(db_session):
    svc = _make_session_service(db_session)
    val = uuid.uuid4()
    assert svc._normalize_sub(val) is val


def test_normalize_sub_string_coerced(db_session):
    svc = _make_session_service(db_session)
    val = uuid.uuid4()
    assert svc._normalize_sub(str(val)) == val


def test_normalize_sub_invalid_raises(db_session):
    svc = _make_session_service(db_session)
    with pytest.raises(ValueError, match="must be a valid UUID"):
        svc._normalize_sub("not-a-uuid")


# ---------------------------------------------------------------------------
# _enforce_concurrent_limit (L164-192)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_enforce_limit_noop_when_limit_nonpositive(
    db_session, user_factory, monkeypatch
):
    """limit <= 0 short-circuits without querying active sessions."""
    user = await user_factory()
    svc = _make_session_service(db_session)
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setattr(session_service_module.settings, "max_sessions_per_user", 0)
    # Should return immediately; no exception even with no sessions.
    await svc._enforce_concurrent_limit(user.id, "jti-x", datetime.now(UTC))


@pytest.mark.asyncio
async def test_enforce_limit_raises_403_when_at_capacity(db_session, user_factory):
    """ENVIRONMENT=testing caps at 2 sessions; the third login is rejected."""
    user = await user_factory()
    await _add_session(db_session, user.id)
    await _add_session(db_session, user.id)
    svc = _make_session_service(db_session)

    with pytest.raises(HTTPException) as exc_info:
        await svc._enforce_concurrent_limit(user.id, "jti-new", datetime.now(UTC))
    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "too_many_sessions"


# ---------------------------------------------------------------------------
# create_access_token — full happy path with metadata merge (L69-152)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_access_token_persists_session_and_metadata(
    db_session, user_factory, monkeypatch
):
    captured: list[tuple] = []

    async def _fake_register(*args):
        captured.append(args)

    monkeypatch.setattr(session_service_module, "register_session_bg", _fake_register)

    user = await user_factory()
    svc = _make_session_service(db_session)
    now = datetime.now(UTC)
    token, session_dto = await svc.create_access_token(
        str(user.id),
        metadata={
            "ip_address": "192.0.2.1",
            "user_agent": "pytest-agent",
            "mfa_required": True,
            "mfa_completed_at": now,
            "mfa_verified_at": now,
        },
    )

    assert isinstance(token, str) and token.count(".") == 2
    assert session_dto.ip_address == "192.0.2.1"
    assert session_dto.user_agent == "pytest-agent"
    assert session_dto.mfa_required is True
    # Redis sync awaited with the freshly-minted jti
    assert len(captured) == 1
    assert captured[0][1] == session_dto.jti


# ---------------------------------------------------------------------------
# get_active_sessions_for_user / get_session_by_id (L237-255)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_active_sessions_excludes_revoked_and_orders_desc(
    db_session, user_factory
):
    user = await user_factory()
    older = await _add_session(db_session, user.id, created_offset_minutes=-10)
    newer = await _add_session(db_session, user.id, created_offset_minutes=-1)
    await _add_session(db_session, user.id, revoked=True)

    svc = _make_session_service(db_session)
    sessions = await svc.get_active_sessions_for_user(user.id)

    assert [s.jti for s in sessions] == [newer.jti, older.jti]


@pytest.mark.asyncio
async def test_get_session_by_id_found_and_missing(db_session, user_factory):
    user = await user_factory()
    row = await _add_session(db_session, user.id)
    svc = _make_session_service(db_session)

    found = await svc.get_session_by_id(row.id)
    assert found is not None
    assert found.jti == row.jti

    assert await svc.get_session_by_id(uuid.uuid4()) is None


# ---------------------------------------------------------------------------
# revoke_session_by_id / revoke_other_sessions (L257-296)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_revoke_session_by_id_revokes_and_rotates_key(
    db_session, user_factory, monkeypatch
):
    revoked_jtis: list[str] = []

    class _Backend:
        async def revoke_session(self, jti: str):
            revoked_jtis.append(jti)

    async def _get_backend():
        return _Backend()

    monkeypatch.setattr("app.auth.redis_session.get_session_backend", _get_backend)

    user = await user_factory()
    row = await _add_session(db_session, user.id)
    old_key = row.signing_key
    svc = _make_session_service(db_session)

    dto = await svc.revoke_session_by_id(row.id)
    assert dto is not None
    assert dto.revoked_at is not None
    assert dto.signing_key != old_key
    assert revoked_jtis == [row.jti]


@pytest.mark.asyncio
async def test_revoke_session_by_id_missing_returns_none(db_session):
    svc = _make_session_service(db_session)
    assert await svc.revoke_session_by_id(uuid.uuid4()) is None


@pytest.mark.asyncio
async def test_revoke_session_by_id_backend_error_is_suppressed(
    db_session, user_factory, monkeypatch
):
    class _Backend:
        async def revoke_session(self, jti: str):
            raise RuntimeError("backend down")

    async def _get_backend():
        return _Backend()

    monkeypatch.setattr("app.auth.redis_session.get_session_backend", _get_backend)

    user = await user_factory()
    row = await _add_session(db_session, user.id)
    svc = _make_session_service(db_session)

    dto = await svc.revoke_session_by_id(row.id)
    assert dto is not None
    assert dto.revoked_at is not None


@pytest.mark.asyncio
async def test_revoke_other_sessions_keeps_current_jti(db_session, user_factory):
    user = await user_factory()
    current = await _add_session(db_session, user.id, jti="current-jti")
    await _add_session(db_session, user.id)
    await _add_session(db_session, user.id)
    svc = _make_session_service(db_session)

    revoked = await svc.revoke_other_sessions(user.id, "current-jti")
    assert revoked == 2

    remaining = await svc.get_active_sessions_for_user(user.id)
    assert [s.jti for s in remaining] == [current.jti]


@pytest.mark.asyncio
async def test_revoke_other_sessions_without_current_revokes_all(
    db_session, user_factory
):
    user = await user_factory()
    await _add_session(db_session, user.id)
    await _add_session(db_session, user.id)
    svc = _make_session_service(db_session)

    revoked = await svc.revoke_other_sessions(user.id, None)
    assert revoked == 2
    assert await svc.get_active_sessions_for_user(user.id) == []
