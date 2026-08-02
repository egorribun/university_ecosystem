"""Focused closure tests for auth session API defensive branches."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from app.api import sessions
from app.models.enums import UserRole


def _request(headers: list[tuple[bytes, bytes]] | None = None):
    return sessions.Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/auth/sessions",
            "headers": headers or [],
            "client": ("127.0.0.1", 1234),
        }
    )


def test_token_and_jti_extraction_defensive_paths(monkeypatch):
    assert sessions._extract_token(_request()) is None
    cookie_request = sessions.Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/auth/sessions",
            "headers": [(b"cookie", b"access_token_v2=cookie-token")],
            "client": ("127.0.0.1", 1234),
        }
    )
    assert sessions._extract_token(cookie_request) == "cookie-token"
    assert (
        sessions._extract_token(_request(headers=[(b"authorization", b"Bearer ")]))
        is None
    )
    assert (
        sessions._extract_token(
            _request(headers=[(b"authorization", b"Basic not-a-bearer")])
        )
        is None
    )

    bearer = _request(headers=[(b"authorization", b"Bearer token")])
    monkeypatch.setattr(sessions, "decode_token", lambda _token: None)
    assert sessions._extract_jti(bearer) is None
    assert sessions._extract_jti(_request()) is None

    monkeypatch.setattr(sessions, "decode_token", lambda _token: {})
    assert sessions._extract_jti(bearer) is None

    monkeypatch.setattr(sessions, "decode_token", lambda _token: {"jti": ""})
    assert sessions._extract_jti(bearer) is None


@pytest.mark.asyncio
async def test_resolve_target_user_reports_missing_admin_target():
    admin = SimpleNamespace(id=uuid.uuid4(), role=UserRole.ADMIN)
    repo = SimpleNamespace(get=AsyncMock(return_value=None))

    with pytest.raises(HTTPException) as exc:
        await sessions._resolve_target_user(
            user_repo=repo,
            current_user=admin,
            requested_user_id=uuid.uuid4(),
            locale="en",
        )

    assert exc.value.status_code == 404
    repo.get.assert_awaited_once()


@pytest.mark.asyncio
async def test_resolve_target_user_returns_admin_target():
    admin = SimpleNamespace(id=uuid.uuid4(), role=UserRole.ADMIN)
    target = SimpleNamespace(id=uuid.uuid4(), role=UserRole.STUDENT)
    repo = SimpleNamespace(get=AsyncMock(return_value=target))

    with patch.object(sessions, "require_admin") as require_admin:
        target_id, resolved = await sessions._resolve_target_user(
            user_repo=repo,
            current_user=admin,
            requested_user_id=target.id,
            locale="en",
        )

    assert target_id == target.id
    assert resolved is target
    require_admin.assert_called_once_with(admin, "en")


def _active_session(*, user_id: uuid.UUID, jti: str) -> SimpleNamespace:
    now = datetime.now(UTC)
    return SimpleNamespace(
        id=uuid.uuid4(),
        user_id=user_id,
        jti=jti,
        created_at=now,
        expires_at=now,
        revoked_at=None,
        ip_address="127.0.0.1",
        user_agent="pytest",
        last_seen_at=now,
        mfa_required=False,
        mfa_completed_at=None,
        mfa_method=None,
        mfa_verified_at=None,
    )


@pytest.mark.asyncio
async def test_list_sessions_marks_current_token():
    user = SimpleNamespace(id=uuid.uuid4(), role=UserRole.STUDENT)
    sessions_result = [
        _active_session(user_id=user.id, jti="current"),
        _active_session(user_id=user.id, jti="other"),
    ]
    service = MagicMock()
    service.get_active_sessions_for_user = AsyncMock(return_value=sessions_result)
    request = _request(headers=[(b"authorization", b"Bearer token")])

    with (
        patch.object(sessions, "resolve_locale", return_value="en"),
        patch.object(sessions, "decode_token", return_value={"jti": "current"}),
    ):
        result = await sessions.list_sessions(request, user, AsyncMock(), service)

    assert [item.is_current for item in result] == [True, False]
    service.get_active_sessions_for_user.assert_awaited_once_with(user.id)


@pytest.mark.asyncio
async def test_revoke_session_handles_service_returning_none():
    user = SimpleNamespace(id=uuid.uuid4(), role=UserRole.STUDENT)
    session = SimpleNamespace(user_id=user.id)
    service = MagicMock()
    service.get_session_by_id = AsyncMock(return_value=session)
    service.revoke_session_by_id = AsyncMock(return_value=None)

    with patch.object(sessions, "resolve_locale", return_value="en"):
        with pytest.raises(HTTPException) as exc:
            await sessions.revoke_session(
                uuid.uuid4(), _request(), None, user, AsyncMock(), service
            )

    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_revoke_session_reports_missing_session():
    user = SimpleNamespace(id=uuid.uuid4(), role=UserRole.STUDENT)
    service = MagicMock()
    service.get_session_by_id = AsyncMock(return_value=None)

    with patch.object(sessions, "resolve_locale", return_value="en"):
        with pytest.raises(HTTPException) as exc:
            await sessions.revoke_session(
                uuid.uuid4(), _request(), None, user, AsyncMock(), service
            )

    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_revoke_session_serializes_success_and_current_flag():
    user = SimpleNamespace(id=uuid.uuid4(), role=UserRole.STUDENT)
    existing = _active_session(user_id=user.id, jti="old")
    revoked = _active_session(user_id=user.id, jti="current")
    service = MagicMock()
    service.get_session_by_id = AsyncMock(return_value=existing)
    service.revoke_session_by_id = AsyncMock(return_value=revoked)
    request = _request(headers=[(b"authorization", b"Bearer token")])

    with (
        patch.object(sessions, "resolve_locale", return_value="en"),
        patch.object(sessions, "decode_token", return_value={"jti": "current"}),
    ):
        result = await sessions.revoke_session(
            existing.id, request, None, user, AsyncMock(), service
        )

    assert result.id == revoked.id
    assert result.is_current is True


@pytest.mark.asyncio
async def test_revoke_other_sessions_returns_bulk_count_and_current_jti():
    user = SimpleNamespace(id=uuid.uuid4(), role=UserRole.STUDENT)
    service = MagicMock()
    service.revoke_other_sessions = AsyncMock(return_value=2)
    request = _request(headers=[(b"authorization", b"Bearer token")])

    with (
        patch.object(sessions, "resolve_locale", return_value="en"),
        patch.object(sessions, "decode_token", return_value={"jti": "current"}),
    ):
        result = await sessions.revoke_other_sessions(
            request, None, user, AsyncMock(), service
        )

    assert result.revoked == 2
    service.revoke_other_sessions.assert_awaited_once_with(user.id, "current")
