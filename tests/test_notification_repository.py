from datetime import UTC, datetime, timedelta

import pytest

from app.models.notifications import Notification
from app.repositories.notification_repository import NotificationRepository
from app.schemas.dtos.notification import NotificationDTO


def test_notification_repository_factory_and_properties(db_session):
    from app.repositories.notification_repository import get_notification_repository

    repo = get_notification_repository(db_session)
    assert repo.model == Notification
    assert repo.db == db_session


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("unread_only", "expected_indices"),
    [(False, [2, 1]), (True, [2, 0])],
    ids=["all", "unread"],
)
async def test_get_for_user_filters_before_ordering_and_pagination(
    db_session, user_factory, unread_only, expected_indices
):
    owner = await user_factory()
    other = await user_factory()
    now = datetime.now(UTC)
    notifications = [
        Notification(
            user_id=owner.id,
            title=f"Notice {index}",
            body=f"Body {index}",
            url=f"/events/{index}",
            read=index == 1,
            created_at=now - timedelta(minutes=4 - index),
        )
        for index in range(4)
    ]
    db_session.add_all(
        [
            *notifications,
            Notification(user_id=other.id, title="Private", created_at=now),
        ]
    )
    await db_session.flush()
    repo = NotificationRepository(db_session)

    page = await repo.get_for_user(owner.id, skip=1, limit=2, unread_only=unread_only)

    assert all(isinstance(item, NotificationDTO) for item in page)
    assert [item.id for item in page] == [
        notifications[index].id for index in expected_indices
    ]
    for item, index in zip(page, expected_indices, strict=True):
        assert item.user_id == owner.id
        assert item.title == f"Notice {index}"
        assert item.body == f"Body {index}"
        assert item.url == f"/events/{index}"
        assert item.read is (index == 1)
    assert await repo.get_for_user(owner.id, skip=4) == []
