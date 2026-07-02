import uuid
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
