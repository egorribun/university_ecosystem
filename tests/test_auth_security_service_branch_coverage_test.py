import pytest
from datetime import datetime, UTC, timedelta
from unittest.mock import AsyncMock, patch, MagicMock

from app.models import ActiveSession
from app.services.auth.security_service import AuthSecurityService
from fastapi import HTTPException


@pytest.fixture
def auth_security_service():
    db = AsyncMock()
    return AuthSecurityService(db=db, locale="en")


def test_validate_session_expiry_tzinfo_none(auth_security_service):
    # If tzinfo is None, it should attach UTC
    session = ActiveSession(expires_at=datetime.now() + timedelta(days=1))
    session.expires_at = session.expires_at.replace(tzinfo=None)
    
    # Should not raise exception
    auth_security_service.validate_session_expiry(session)


def test_validate_session_expiry_expired(auth_security_service):
    session = ActiveSession(expires_at=datetime.now(UTC) - timedelta(days=1))
    with pytest.raises(HTTPException) as exc:
        auth_security_service.validate_session_expiry(session)
    assert exc.value.status_code == 401


@pytest.mark.asyncio
@patch("app.services.auth.security_service.settings")
async def test_handle_mfa_ttl_no_ttl(mock_settings, auth_security_service):
    mock_settings.mfa_step_up_ttl_seconds = 0
    session = ActiveSession(mfa_verified_at=datetime.now(UTC) - timedelta(hours=1))
    await auth_security_service.handle_mfa_ttl(session)
    assert session.mfa_verified_at is not None
    auth_security_service.db.commit.assert_not_awaited()


@pytest.mark.asyncio
@patch("app.services.auth.security_service.settings")
async def test_handle_mfa_ttl_expired_with_no_tz(mock_settings, auth_security_service):
    mock_settings.mfa_step_up_ttl_seconds = 3600
    # expired
    verified_at = datetime.now() - timedelta(seconds=3601)
    verified_at = verified_at.replace(tzinfo=None)
    session = ActiveSession(mfa_verified_at=verified_at)
    
    await auth_security_service.handle_mfa_ttl(session)
    assert session.mfa_verified_at is None
    auth_security_service.db.commit.assert_awaited_once()


@pytest.mark.asyncio
@patch("app.services.auth.security_service.settings")
async def test_handle_mfa_ttl_not_expired(mock_settings, auth_security_service):
    mock_settings.mfa_step_up_ttl_seconds = 3600
    session = ActiveSession(mfa_verified_at=datetime.now(UTC) - timedelta(seconds=1800))
    await auth_security_service.handle_mfa_ttl(session)
    assert session.mfa_verified_at is not None


@pytest.mark.asyncio
async def test_sync_last_seen_none(auth_security_service):
    session = ActiveSession(id="123", last_seen_at=None)
    await auth_security_service.sync_last_seen(session)
    assert session.last_seen_at is not None
    auth_security_service.db.execute.assert_awaited_once()
    auth_security_service.db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_sync_last_seen_no_tz(auth_security_service):
    last_seen_at = datetime.now() - timedelta(seconds=400)
    last_seen_at = last_seen_at.replace(tzinfo=None)
    session = ActiveSession(id="123", last_seen_at=last_seen_at)
    await auth_security_service.sync_last_seen(session, cached_session=False)
    # Sync window 300, 400 > 300, so it updates
    assert session.last_seen_at.tzinfo == UTC
    auth_security_service.db.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_sync_last_seen_cached_session(auth_security_service):
    # cached_session=True uses 600 seconds
    last_seen_at = datetime.now(UTC) - timedelta(seconds=400)
    session = ActiveSession(id="123", last_seen_at=last_seen_at)
    await auth_security_service.sync_last_seen(session, cached_session=True)
    # 400 < 600, shouldn't update
    auth_security_service.db.execute.assert_not_awaited()

    # Now > 600
    last_seen_at = datetime.now(UTC) - timedelta(seconds=601)
    session.last_seen_at = last_seen_at
    await auth_security_service.sync_last_seen(session, cached_session=True)
    auth_security_service.db.execute.assert_awaited_once()
