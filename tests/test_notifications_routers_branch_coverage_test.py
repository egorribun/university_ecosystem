import pytest
import uuid
from unittest.mock import AsyncMock, MagicMock, patch
from sqlalchemy.exc import IntegrityError
from fastapi import Request, HTTPException
from starlette.datastructures import Headers

from app.routers.notifications import (
    _refresh_user_topic_preferences,
    subscribe,
    unsubscribe,
    get_subscriptions
)
from app.models import User
from app.schemas.notifications import PushSubscriptionIn
from app.core.ratelimit.middleware import RateLimitExceeded, RateLimitInfo

@pytest.fixture
def mock_db():
    db = AsyncMock()
    nested_cm = AsyncMock()
    db.begin_nested.return_value = nested_cm
    return db

@pytest.fixture
def test_user():
    user = MagicMock(spec=User)
    user.id = uuid.uuid4()
    return user

@pytest.fixture
def test_request():
    req = MagicMock(spec=Request)
    req.client.host = "127.0.0.1"
    req.headers = Headers({"accept-language": "en"})
    return req

@pytest.mark.asyncio
@patch("app.routers.notifications.sort_topics", return_value=["test_topic"])
async def test_refresh_user_topic_preferences_integrity_error(mock_sort, mock_db, test_user):
    # Raise IntegrityError on the first flush
    mock_db.flush.side_effect = [IntegrityError("msg", "params", "orig"), None]
    
    mock_scalars = MagicMock()
    mock_scalars.scalars.return_value = [["topic1"]]
    
    mock_execute_scalar_1 = MagicMock()
    mock_execute_scalar_1.scalar_one_or_none.return_value = None
    
    mock_execute_scalar_2 = MagicMock()
    mock_record = MagicMock()
    mock_execute_scalar_2.scalar_one_or_none.return_value = mock_record

    # 1. select PushSubscription.topics
    # 2. select UserPushTopic inside begin_nested
    # 3. select UserPushTopic inside except block
    mock_db.execute.side_effect = [mock_scalars, mock_execute_scalar_1, mock_execute_scalar_2]

    await _refresh_user_topic_preferences(mock_db, user_id=test_user.id)
    
    assert mock_record.topics == ["test_topic"]
    assert mock_db.flush.call_count == 2

@pytest.mark.asyncio
@patch("app.routers.notifications.enforce_rate_limit")
async def test_subscribe_rate_limit(mock_enforce, mock_db, test_user, test_request):
    mock_enforce.side_effect = RateLimitExceeded(RateLimitInfo(False, 0, 10))
    payload = PushSubscriptionIn(
        endpoint="https://example.com/push",
        keys={"p256dh": "A"*43, "auth": "B"*22}
    )
    
    with pytest.raises(HTTPException) as exc:
        await subscribe(payload, test_request, mock_db, test_user)
    
    assert exc.value.status_code == 429

@pytest.mark.asyncio
@patch("app.routers.notifications.enforce_rate_limit")
async def test_unsubscribe_rate_limit(mock_enforce, mock_db, test_user, test_request):
    mock_enforce.side_effect = RateLimitExceeded(RateLimitInfo(False, 0, 10))
    
    with pytest.raises(HTTPException) as exc:
        await unsubscribe("https://example.com/push", test_request, mock_db, test_user)
    
    assert exc.value.status_code == 429

@pytest.mark.asyncio
@patch("app.routers.notifications.enforce_rate_limit")
async def test_get_subscriptions_rate_limit(mock_enforce, mock_db, test_user, test_request):
    mock_enforce.side_effect = RateLimitExceeded(RateLimitInfo(False, 0, 10))
    
    with pytest.raises(HTTPException) as exc:
        await get_subscriptions(test_request, mock_db, test_user)
    
    assert exc.value.status_code == 429
