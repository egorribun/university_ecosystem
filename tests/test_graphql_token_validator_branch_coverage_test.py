import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models import ActiveSession, User
from app.services.auth.graphql_token_validator import GraphQLTokenValidator


@pytest.fixture
def validator():
    request = MagicMock()
    session = AsyncMock()
    return GraphQLTokenValidator(request, session)


@pytest.mark.asyncio
@patch("app.deps.cache.get_cache_client", new_callable=AsyncMock)
async def test_redis_jti_check_connection_error(mock_get_cache, validator):
    redis_mock = AsyncMock()
    redis_mock.exists.side_effect = ConnectionError("Redis down")
    mock_get_cache.return_value = redis_mock

    # Should fall through and return True
    result = await validator._redis_jti_check("jti_123")
    assert result is True


@pytest.mark.asyncio
async def test_load_db_session_connection_error(validator):
    validator._session.execute.side_effect = ConnectionError("DB down")

    # Should return None
    result = await validator._load_db_session("jti_123")
    assert result is None


@pytest.mark.asyncio
async def test_load_user_value_error(validator):
    # Pass an invalid UUID string that raises ValueError
    result = await validator._load_user("invalid-uuid")
    assert result is None


@pytest.mark.asyncio
@patch("app.services.auth.fingerprint_service.AuthFingerprintService")
async def test_check_fingerprint_exception(mock_fp_service, validator):
    session = MagicMock(spec=ActiveSession, fingerprint_hash="hash", jti="jti_123")
    user = MagicMock(spec=User, id=uuid.uuid4())

    instance = mock_fp_service.return_value
    instance.validate_fingerprint = AsyncMock(
        side_effect=Exception("Fingerprint failed")
    )

    # Should return False on exception
    result = await validator._check_fingerprint(user, session)
    assert result is False


@pytest.mark.asyncio
async def test_validate_accepts_live_session_and_active_user(validator):
    """The complete GraphQL auth pipeline returns the validated user."""
    user_id = uuid.uuid4()
    active_session = MagicMock(
        expires_at=datetime.now(UTC) + timedelta(minutes=5),
        fingerprint_hash=None,
    )
    user = MagicMock(is_active=True)

    validator._redis_jti_check = AsyncMock(return_value=True)
    validator._load_db_session = AsyncMock(return_value=active_session)
    validator._load_user = AsyncMock(return_value=user)

    result = await validator.validate(str(user_id), "live-jti")

    assert result is user
    validator._load_db_session.assert_awaited_once_with("live-jti")
    validator._load_user.assert_awaited_once_with(str(user_id))


@pytest.mark.asyncio
async def test_validate_rejects_expired_session_before_loading_user(validator):
    """An expired active-session record must not trigger a user lookup."""
    active_session = MagicMock(
        expires_at=datetime.now(UTC) - timedelta(seconds=1),
        fingerprint_hash=None,
    )

    validator._redis_jti_check = AsyncMock(return_value=True)
    validator._load_db_session = AsyncMock(return_value=active_session)
    validator._load_user = AsyncMock()

    result = await validator.validate(str(uuid.uuid4()), "expired-jti")

    assert result is None
    validator._load_user.assert_not_awaited()


@pytest.mark.asyncio
async def test_validate_rejects_inactive_user(validator):
    """A live session cannot authenticate a deactivated user."""
    active_session = MagicMock(
        expires_at=datetime.now(UTC) + timedelta(minutes=5),
        fingerprint_hash=None,
    )
    validator._redis_jti_check = AsyncMock(return_value=True)
    validator._load_db_session = AsyncMock(return_value=active_session)
    validator._load_user = AsyncMock(return_value=MagicMock(is_active=False))

    result = await validator.validate(str(uuid.uuid4()), "inactive-jti")

    assert result is None


@pytest.mark.asyncio
async def test_validate_rejects_fingerprint_failure(validator):
    """Fingerprint rejection must fail closed after user validation."""
    active_session = MagicMock(
        expires_at=datetime.now(UTC) + timedelta(minutes=5),
        fingerprint_hash="hash",
    )
    user = MagicMock(is_active=True)
    validator._redis_jti_check = AsyncMock(return_value=True)
    validator._load_db_session = AsyncMock(return_value=active_session)
    validator._load_user = AsyncMock(return_value=user)
    validator._check_fingerprint = AsyncMock(return_value=False)

    result = await validator.validate(str(uuid.uuid4()), "fingerprint-jti")

    assert result is None
    validator._check_fingerprint.assert_awaited_once_with(user, active_session)


@pytest.mark.asyncio
async def test_load_user_returns_database_user_for_valid_uuid(validator):
    """A valid subject claim is resolved through the database result."""
    user_id = uuid.uuid4()
    user = MagicMock(spec=User)
    result = MagicMock()
    result.scalar_one_or_none.return_value = user
    validator._session.execute.return_value = result

    loaded = await validator._load_user(str(user_id))

    assert loaded is user
    validator._session.execute.assert_awaited_once()


@pytest.mark.asyncio
@patch("app.services.auth.redis_session.RedisSessionService")
@patch("app.services.auth.fingerprint_service.AuthFingerprintService")
async def test_check_fingerprint_accepts_matching_fingerprint(
    mock_fp_service, mock_redis_service, validator
):
    """A successful fingerprint check keeps the session authenticated."""
    session = MagicMock(spec=ActiveSession, fingerprint_hash="hash", jti="jti_123")
    user = MagicMock(spec=User, id=uuid.uuid4())
    mock_fp_service.return_value.validate_fingerprint = AsyncMock()

    result = await validator._check_fingerprint(user, session)

    assert result is True
    mock_fp_service.return_value.validate_fingerprint.assert_awaited_once_with(
        user,
        session,
        validator._session,
        mock_redis_service.return_value,
    )
