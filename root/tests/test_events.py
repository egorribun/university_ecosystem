"""Tests for Domain Events System."""

from unittest.mock import AsyncMock

import pytest

from app.core.events import (
    EventBus,
    EventCreated,
    NotificationSent,
    UserCreated,
    UserLoggedIn,
    event_bus,
)


def test_user_created_event():
    """Test UserCreated event properties."""
    event = UserCreated(user_id=1, email="test@example.com")

    assert event.event_type == "user.created"
    assert event.user_id == 1
    assert event.email == "test@example.com"
    assert event.event_id is not None
    assert event.occurred_at is not None


def test_user_logged_in_event():
    """Test UserLoggedIn event properties."""
    event = UserLoggedIn(user_id=1, ip_address="192.168.1.1")

    assert event.event_type == "auth.login"
    assert event.user_id == 1
    assert event.ip_address == "192.168.1.1"


def test_event_created_event():
    """Test EventCreated event properties."""
    event = EventCreated(event_id_entity=10, organizer_id=1, title="Test Event")

    assert event.event_type == "event.created"
    assert event.event_id_entity == 10
    assert event.organizer_id == 1
    assert event.title == "Test Event"


def test_notification_sent_event():
    """Test NotificationSent event properties."""
    event = NotificationSent(
        notification_id="abc123", user_id=1, notification_type="push"
    )

    assert event.event_type == "notification.sent"
    assert event.notification_id == "abc123"
    assert event.user_id == 1
    assert event.notification_type == "push"


def test_event_bus_subscribe():
    """Test EventBus subscription."""
    bus = EventBus()
    handler = AsyncMock()

    bus.subscribe("user.created", handler)

    assert handler in bus._handlers["user.created"]


def test_event_bus_subscribe_all():
    """Test EventBus subscribe to all events."""
    bus = EventBus()
    handler = AsyncMock()

    bus.subscribe_all(handler)

    assert handler in bus._all_handlers


def test_event_bus_unsubscribe():
    """Test EventBus unsubscription."""
    bus = EventBus()
    handler = AsyncMock()

    bus.subscribe("user.created", handler)
    bus.unsubscribe("user.created", handler)

    assert handler not in bus._handlers["user.created"]


@pytest.mark.anyio
async def test_event_bus_publish():
    """Test EventBus publishes to correct handlers."""
    bus = EventBus()
    handler = AsyncMock()
    bus.subscribe("user.created", handler)

    event = UserCreated(user_id=1, email="test@example.com")
    await bus.publish(event)

    handler.assert_called_once_with(event)


@pytest.mark.anyio
async def test_event_bus_publish_to_all_handlers():
    """Test EventBus publishes to wildcard handlers."""
    bus = EventBus()
    specific_handler = AsyncMock()
    all_handler = AsyncMock()

    bus.subscribe("user.created", specific_handler)
    bus.subscribe_all(all_handler)

    event = UserCreated(user_id=1, email="test@example.com")
    await bus.publish(event)

    specific_handler.assert_called_once_with(event)
    all_handler.assert_called_once_with(event)


@pytest.mark.anyio
async def test_event_bus_handles_handler_errors():
    """Test EventBus handles failing handlers gracefully."""
    bus = EventBus()
    failing_handler = AsyncMock(side_effect=ValueError("handler error"))
    success_handler = AsyncMock()

    bus.subscribe("user.created", failing_handler)
    bus.subscribe("user.created", success_handler)

    event = UserCreated(user_id=1, email="test@example.com")
    # Should not raise
    await bus.publish(event)

    # Both handlers were called
    failing_handler.assert_called_once()
    success_handler.assert_called_once()


def test_global_event_bus_exists():
    """Test global event_bus singleton exists."""
    assert event_bus is not None
    assert isinstance(event_bus, EventBus)
