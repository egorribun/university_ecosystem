import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.notifications import Notification
from app.repositories.notification_repository import NotificationRepository
from app.utils.uuid_v7 import generate_uuid7


@pytest.mark.asyncio
async def test_notification_repository_crud(db_session, user_factory):
    user = await user_factory()
    repo = NotificationRepository(db_session)

    # 1. Create a notification
    notif = Notification(
        id=generate_uuid7(),
        user_id=user.id,
        title="Test Title",
        body="Test Body",
        type="system",
        dedupe_key="dedupe123",
        read=False,
    )
    db_session.add(notif)
    await db_session.commit()

    # 2. Test get_for_user
    notifs = await repo.get_for_user(user.id)
    assert len(notifs) == 1
    assert notifs[0].title == "Test Title"

    # 3. Test get_unread_for_user
    unread = await repo.get_unread_for_user(user.id)
    assert len(unread) == 1
    assert unread[0].id == notif.id

    # 4. Test count_unread
    count = await repo.count_unread(user.id)
    assert count == 1

    # 5. Test get_by_dedupe_key
    by_dedupe = await repo.get_by_dedupe_key(user.id, "dedupe123")
    assert by_dedupe is not None
    assert by_dedupe.id == notif.id

    missing_dedupe = await repo.get_by_dedupe_key(user.id, "nonexistent")
    assert missing_dedupe is None

    # 6. Test count_by_type
    type_counts = await repo.count_by_type(user.id)
    assert type_counts == {"system": 1}

    # 7. Test mark_as_read (empty list)
    assert await repo.mark_as_read([], user.id) == 0

    # 8. Test mark_as_read (with ID)
    updated = await repo.mark_as_read([notif.id], user.id)
    assert updated == 1

    # Verify marked as read
    assert await repo.count_unread(user.id) == 0

    # 9. Test mark_all_as_read when none is unread
    assert await repo.mark_all_as_read(user.id) == 0


@pytest.mark.asyncio
async def test_notification_repository_mark_all_as_read(db_session, user_factory):
    user = await user_factory()
    repo = NotificationRepository(db_session)

    # Seed 2 unread notifications
    n1 = Notification(
        id=generate_uuid7(),
        user_id=user.id,
        title="N1",
        body="B1",
        type="system",
        read=False,
    )
    n2 = Notification(
        id=generate_uuid7(),
        user_id=user.id,
        title="N2",
        body="B2",
        type="system",
        read=False,
    )
    db_session.add_all([n1, n2])
    await db_session.commit()

    assert await repo.count_unread(user.id) == 2

    # Mark all as read
    updated = await repo.mark_all_as_read(user.id)
    assert updated == 2
    assert await repo.count_unread(user.id) == 0


@pytest.mark.asyncio
async def test_notification_repository_defensive_rowcount(db_session):
    # Mock db session execute to return a result with rowcount = -1
    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.rowcount = -1
    mock_db.execute.return_value = mock_result

    repo = NotificationRepository(mock_db)
    user_id = uuid.uuid4()
    notif_id = uuid.uuid4()

    # Call mark_as_read
    rc_read = await repo.mark_as_read([notif_id], user_id)
    assert rc_read == 0

    # Call mark_all_as_read
    rc_all = await repo.mark_all_as_read(user_id)
    assert rc_all == 0


def test_notification_repository_factory_and_properties(db_session):
    from app.repositories.notification_repository import get_notification_repository

    repo = get_notification_repository(db_session)
    assert repo.model == Notification
    assert repo.db == db_session
