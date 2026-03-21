import unittest.mock as mock
import uuid

import pytest

from app.core.csrf import _extract_session_id
from app.core.events import _EVENT_REGISTRY
from app.models.users import User, UserProfile
from app.repositories.user_repository import UserRepository
from app.workers.outbox import StoredEvent


@pytest.mark.asyncio
async def test_user_repository_like_escaping(db_session):
    """Verify that LIKE wildcards are properly escaped in UserRepository."""
    repo = UserRepository(db_session)

    # Create two users
    user1 = User(email="normal@example.com", hashed_password="pw", is_active=True)
    user1.profile = UserProfile(full_name="Normal User")

    user2 = User(email="wildcard@example.com", hashed_password="pw", is_active=True)
    user2.profile = UserProfile(full_name="User % with percent")

    db_session.add(user1)
    db_session.add(user2)
    # Ensure they are in the DB
    await db_session.flush()

    # Verify we can find user2 by its literal name with percent
    # Search for '%' — safe_query becomes '\%' -> pattern becomes '%\%%'
    results = await repo.search_by_name("%")

    assert len(results) >= 1, f"Expected at least 1 result for '%', got {len(results)}"
    emails = [u.email for u in results]
    assert "wildcard@example.com" in emails, (
        f"wildcard user missing from results: {emails}"
    )
    assert "normal@example.com" not in emails, (
        f"normal user incorrectly included in results: {emails}"
    )

    # Search for '_' — should return nothing if no one has underscore
    # safe_query becomes '\_' -> pattern becomes '%\_%'
    results = await repo.search_by_name("_")
    emails = [u.email for u in results]
    assert "wildcard@example.com" not in emails, (
        f"wildcard user incorrectly included for '_': {emails}"
    )


@pytest.mark.asyncio
async def test_event_registry_contains_all_events():
    """Verify that all standard domain events are registered."""
    expected_events = {
        "UserCreated",
        "UserUpdated",
        "UserDeleted",
        "UserLoggedIn",
        "MfaEnabled",
        "EventCreated",
        "EventUpdated",
        "EventRegistration",
        "NewsCreated",
        "NewsUpdated",
        "NotificationSent",
    }
    for event_name in expected_events:
        assert event_name in _EVENT_REGISTRY, f"{event_name} missing from registry"


def test_csrf_anonymous_session_binding():
    """Verify that anonymous CSRF binding uses a client fingerprint (RZ-03), not empty string."""

    class MockRequest:
        def __init__(self):
            self.state = type("State", (), {"session_id": None})
            self.cookies = {}

    request = MockRequest()
    session_id = _extract_session_id(request, cookie_token="nonce:hmac")
    # RZ-03: anonymous requests bind to "anon:{client_host}:{user_agent}" fingerprint
    # to prevent subdomain-origin token spraying.
    assert session_id.startswith("anon:")


@pytest.mark.asyncio
async def test_outbox_worker_safe_reconstruction(db_session):
    """Verify that OutboxWorker uses the registry and filters payload."""
    from app.core.events import UserCreated
    from app.workers.outbox import OutboxWorker

    worker = OutboxWorker()

    # Create a stored event for UserCreated
    se = StoredEvent(
        event_type="UserCreated",
        payload={
            "user_id": str(uuid.uuid4()),
            "email": "test@example.com",
            "malicious_attr": "evil",  # Should be filtered out
        },
    )
    # Add dummy metadata to avoid missing field errors if any
    se.metadata_ = {"event_id": str(uuid.uuid4())}

    from app.core.events import event_bus

    # We use the actual registry key
    assert "UserCreated" in _EVENT_REGISTRY

    with mock.patch.object(
        event_bus, "publish", new_callable=mock.AsyncMock
    ) as mock_publish:
        await worker._dispatch_event(se)

        assert mock_publish.called
        event = mock_publish.call_args[0][0]
        assert isinstance(event, UserCreated)
        assert event.email == "test@example.com"
        assert not hasattr(event, "malicious_attr")
