import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException, Request

from app.api.deps import (
    get_chat_service,
    get_current_admin_user,
    get_current_user,
    get_event_service,
    get_locale,
    get_news_service,
    get_schedule_service,
    get_story_service,
    require_fresh_mfa,
)
from app.models.models import ActiveSession, User


@pytest.mark.asyncio
async def test_get_current_user_no_token():
    request = MagicMock(spec=Request)
    request.cookies = {}
    db = AsyncMock()

    with pytest.raises(HTTPException) as exc:
        await get_current_user(request, None, db)
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_get_current_user_invalid_token():
    request = MagicMock(spec=Request)
    db = AsyncMock()

    with patch("app.api.deps.decode_token", return_value=None):
        with pytest.raises(HTTPException) as exc:
            await get_current_user(request, "invalid", db)
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_get_current_user_redis_hit():
    request = MagicMock(spec=Request)
    request.state = MagicMock()
    db = AsyncMock()
    user_id = uuid.uuid4()
    jti = "test-jti"

    cached_session = {
        "user_id": str(user_id),
        "fingerprint_hash": "hash",
    }

    user = User(id=user_id, is_active=True)
    session = ActiveSession(
        id=uuid.uuid4(),
        jti=jti,
        user_id=user_id,
        expires_at=datetime.now(UTC) + timedelta(hours=1),
        fingerprint_hash="hash",
    )

    with (
        patch(
            "app.api.deps.decode_token", return_value={"sub": str(user_id), "jti": jti}
        ),
        patch("app.services.auth.redis_session.RedisSessionService") as mock_redis_cls,
        patch("app.auth.fingerprint.extract_fingerprint") as mock_fp,
    ):
        mock_redis = mock_redis_cls.return_value
        mock_redis.get_session = AsyncMock(return_value=cached_session)
        mock_redis.update_last_seen = AsyncMock()

        db.get = AsyncMock(return_value=user)

        # We still need to mock the session load if the logic falls through
        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = session
        db.execute = AsyncMock(return_value=mock_result)

        mock_fp.return_value.fingerprint_hash = "hash"

        result = await get_current_user(request, "token", db)
        assert result == user
        assert request.state.active_session == session


@pytest.mark.asyncio
async def test_get_current_admin_user():
    request = MagicMock(spec=Request)
    user = User(id=uuid.uuid4(), role="admin")
    checker = MagicMock()
    checker.check_admin = AsyncMock(return_value=True)

    result = await get_current_admin_user(request, user, checker)
    assert result == user

    checker.check_admin = AsyncMock(return_value=False)
    with patch("app.api.deps.resolve_locale"), pytest.raises(HTTPException) as exc:
        await get_current_admin_user(request, user, checker)
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_get_locale():
    request = MagicMock(spec=Request)
    user = User(id=uuid.uuid4())

    with patch("app.api.deps.resolve_locale", return_value="en"):
        # Test default
        assert get_locale(request, user) == "en"

        # Test with preferred_locale set (mocked since it's not in DB)
        with patch.object(User, "preferred_locale", "ru", create=True):
            assert get_locale(request, user) == "ru"


@pytest.mark.asyncio
async def test_require_fresh_mfa():
    request = MagicMock(spec=Request)
    user = User(id=uuid.uuid4())
    session = ActiveSession(mfa_verified_at=datetime.now(UTC) - timedelta(minutes=1))
    request.state.active_session = session

    with (
        patch(
            "app.api.deps.mfa.user_has_confirmed_interactive_factor", return_value=True
        ),
        patch("app.api.deps.settings") as mock_settings,
        patch("app.api.deps.resolve_locale"),
        patch("app.api.deps.ensure_mfa_relationships_loaded"),
    ):
        mock_settings.mfa_step_up_ttl_seconds = 300
        # Should not raise
        await require_fresh_mfa(request, user, AsyncMock())

        # Expired
        mock_settings.mfa_step_up_ttl_seconds = 30
        with pytest.raises(HTTPException) as exc:
            await require_fresh_mfa(request, user, AsyncMock())
        assert exc.value.status_code == 428


@pytest.mark.asyncio
async def test_service_factories():
    db = AsyncMock()
    vector = MagicMock()

    with patch("app.api.deps.get_vector_service", return_value=vector):
        get_chat_service(db)
        get_event_service(db, vector)
        get_news_service(db, vector)
        get_story_service(db)
        get_schedule_service(db)
        # Just check they don't crash
