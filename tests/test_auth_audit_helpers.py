from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import Request

from app.auth.auth import (
    _audit_log,
    _build_token_response,
    _collect_mfa_challenges,
    _extract_client_info,
    _resolve_mfa_capabilities,
)
from app.models.enums import UserRole
from app.models.models import ActiveSession, User


def create_mock_user(**kwargs):
    user = MagicMock(spec=User)
    # Default values for UserBase and UserOut
    defaults = {
        "id": uuid4(),
        "email": "test@example.com",
        "full_name": "Test User",
        "is_active": True,
        "role": UserRole.STUDENT,
        "group_id": None,
        "avatar_url": None,
        "cover_url": None,
        "about": None,
        "status": None,
        "institute": None,
        "course": None,
        "department": None,
        "position": None,
        "pending_email": None,
        "spotify_is_connected": False,
        "mfa_required": False,
        "mfa_default_method": None,
        "mfa_last_verified_at": None,
        "totp_enrollments": [],
        "mfa_challenges": [],
        "recovery_codes_left": 0,
        "record_book_number": None,
        "education_level": None,
        "track": None,
        "program": None,
        "telegram": None,
        "achievements": None,
        "spotify_connected": False,
        "spotify_display_name": None,
        "dnd_enabled": False,
        "dnd_start": None,
        "dnd_end": None,
        "timezone": None,
    }
    defaults.update(kwargs)
    for key, value in defaults.items():
        setattr(user, key, value)
    return user


@pytest.fixture
def mock_request():
    request = MagicMock(spec=Request)
    request.client = MagicMock()
    request.client.host = "127.0.0.1"
    request.headers = {"user-agent": "test-agent"}
    return request


def test_extract_client_info(mock_request):
    ip, ua = _extract_client_info(mock_request)
    assert ip == "127.0.0.1"
    assert ua == "test-agent"


def test_extract_client_info_no_client():
    request = MagicMock(spec=Request)
    request.client = None
    request.headers = {}
    ip, ua = _extract_client_info(request)
    assert ip is None
    assert ua is None


@patch("app.auth.auth.get_audit_service")
def test_audit_log(mock_get_service, mock_request):
    mock_service = MagicMock()
    mock_get_service.return_value = mock_service

    _audit_log(
        "test_event", mock_request, user_id=1, reason="test", extra={"foo": "bar"}
    )

    mock_service.log.assert_called_once_with(
        event="test_event", request=mock_request, user_id=1, reason="test", foo="bar"
    )


@pytest.mark.asyncio
@patch("app.auth.auth.mfa.has_totp_enabled", new_callable=AsyncMock)
@patch("app.auth.auth.mfa.has_webauthn_enabled", new_callable=AsyncMock)
async def test_resolve_mfa_capabilities(mock_webauthn, mock_totp):
    mock_totp.return_value = True
    mock_webauthn.return_value = False

    db = AsyncMock()
    user = User(id=uuid4())

    caps = await _resolve_mfa_capabilities(db, user)
    assert caps == {"totp": True, "webauthn": False}


@pytest.mark.asyncio
async def test_collect_mfa_challenges_totp():
    db = AsyncMock()
    user = User(id=uuid4())
    capabilities = {"totp": True}

    challenges = await _collect_mfa_challenges(db, user, "en", capabilities)
    assert len(challenges) == 1
    assert challenges[0].method == "totp"
    assert challenges[0].challenge_token is not None


@pytest.mark.asyncio
async def test_collect_mfa_challenges_none():
    db = AsyncMock()
    user = User(id=uuid4())
    capabilities = {"totp": False}

    challenges = await _collect_mfa_challenges(db, user, "en", capabilities)
    assert len(challenges) == 0


@pytest.mark.asyncio
async def test_build_token_response():
    db = AsyncMock()
    user = create_mock_user(email="test@example.com", full_name="Test User")
    session = ActiveSession(id=uuid4())

    response = await _build_token_response(db, user, "token123", session)
    assert response.access_token == "token123"
    assert response.token_type == "bearer"
    assert response.user.email == "test@example.com"
    assert response.user.full_name == "Test User"


@pytest.mark.asyncio
async def test_build_token_response_inactive_user():
    db = AsyncMock()
    user = create_mock_user(email="inactive@example.com", is_active=False)
    session = ActiveSession(id=uuid4())

    response = await _build_token_response(db, user, "token456", session)
    assert response.access_token == "token456"
    assert response.user.is_active is False
