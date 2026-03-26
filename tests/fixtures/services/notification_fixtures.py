"""Fixtures for push notification tests."""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from unittest.mock import MagicMock, patch

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import PushSubscription, User


@pytest_asyncio.fixture
async def push_subscription_factory(
    db_session: AsyncSession,
) -> Callable[..., Awaitable[PushSubscription]]:
    """Create PushSubscription rows for testing."""

    async def _factory(
        user: User | None = None, *, user_id: uuid.UUID | None = None, **kwargs
    ) -> PushSubscription:
        uid = user_id or (user.id if user else uuid.uuid4())
        defaults = {
            "endpoint": f"https://push.example.com/{uuid.uuid4().hex}",
            "p256dh": "test_p256dh_key_for_push_subscription",
            "auth": "test_auth_key",
            "user_id": uid,
            "topics": [],
        }
        defaults.update(kwargs)
        sub = PushSubscription(**defaults)
        db_session.add(sub)
        await db_session.commit()
        await db_session.refresh(sub)
        return sub

    return _factory


@pytest.fixture
def mock_pywebpush():
    """Mock pywebpush.webpush to prevent real HTTP calls.

    Returns the mock so tests can configure return_value / side_effect.
    """
    with patch("app.services.webpush.webpush") as mock:
        mock.return_value = MagicMock(status_code=201)
        yield mock


@pytest.fixture
def mock_deliver_push():
    """Mock deliver_push_to_subscriptions to avoid real push delivery."""
    with patch("app.routers.notifications.deliver_push_to_subscriptions") as mock:
        mock.return_value = []
        yield mock


@pytest.fixture
def mock_send_web_push():
    """Mock send_web_push used by router's _deliver_to_subscription."""
    with patch("app.routers.notifications.send_web_push") as mock:
        yield mock
