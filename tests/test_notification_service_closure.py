"""Closure tests for the top-level notification service facade."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

import pytest

from app.services.notification_service import NotificationService


@pytest.mark.asyncio
async def test_send_security_notification_converts_uuid_and_integer_ids():
    service = NotificationService(db=AsyncMock())
    user_id = uuid4()

    with patch(
        "app.services.notification_service.create_notifications_for_users",
        new=AsyncMock(return_value=2),
    ) as create:
        result = await service.send_security_notification([user_id, 5], "Title", "Body")

    assert result == 2
    assert create.await_args.kwargs["user_ids"] == [user_id, UUID(int=5)]


def test_dispatch_helpers_are_removed_from_the_notification_service():
    """AUD-198: the dispatch helpers dropped work on NATS failure and had no callers."""
    assert not hasattr(NotificationService, "dispatch_event_created")
    assert not hasattr(NotificationService, "dispatch_news_created")
    assert not hasattr(NotificationService, "dispatch_comment_created")
