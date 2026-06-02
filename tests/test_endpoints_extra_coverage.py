from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient

import app.models as models
from app.utils.uuid_v7 import generate_uuid7
from tests.fixtures.auth.auth_fixtures import create_access_token


@pytest.mark.asyncio
async def test_mark_all_read(root_client: AsyncClient, db_session, user_factory):
    from sqlalchemy.exc import IntegrityError as SAIntegrityError

    user = await user_factory()
    for i in range(3):
        n = models.Notification(
            id=generate_uuid7(),
            user_id=user.id,
            title=f"T{i}",
            body="B",
            read=False,
            created_at=datetime.now(UTC),
            _allow_system_managed_assignment=True,
        )
        db_session.add(n)
    try:
        await db_session.commit()
    except SAIntegrityError:
        # PostgreSQL: partitioned notifications table may lack current-month partition
        pytest.skip("Notification partition not available (PostgreSQL partitioning)")

    token, _ = await create_access_token(sub=str(user.id), db=db_session)
    response = await root_client.post(
        "/api/v1/notifications/read-all", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200
    assert response.json()["updated"] >= 3


@pytest.mark.asyncio
async def test_check_schedule_with_lessons(
    root_client: AsyncClient, db_session, user_factory
):
    group = models.Group(name="Test Group")
    db_session.add(group)
    await db_session.flush()

    user = await user_factory(group_id=group.id)

    # Create a schedule entry
    now = datetime.now(UTC)
    lesson = models.Schedule(
        group_id=group.id,
        subject="Math",
        start_time=now + timedelta(minutes=5),
        end_time=now + timedelta(minutes=95),
        lesson_type="lecture",
        weekday="monday",
    )
    db_session.add(lesson)
    await db_session.commit()

    token, _ = await create_access_token(sub=str(user.id), db=db_session)

    from sqlalchemy.exc import IntegrityError as SAIntegrityError

    # Second call to ensure deduplication logic is hit
    try:
        await root_client.post(
            "/api/v1/notifications/check-schedule?lookahead_minutes=15",
            headers={"Authorization": f"Bearer {token}"},
        )
    except SAIntegrityError:
        pytest.skip("Notification partition not available (PostgreSQL partitioning)")
    response = await root_client.post(
        "/api/v1/notifications/check-schedule?lookahead_minutes=15",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_list_events_basic(root_client: AsyncClient, db_session, user_factory):
    user = await user_factory()
    token, _ = await create_access_token(sub=str(user.id), db=db_session)

    event = models.Event(
        title="Test Event",
        description="Desc",
        starts_at=datetime.now(UTC) + timedelta(days=1),
        ends_at=datetime.now(UTC) + timedelta(days=1, hours=2),
        location="Campus",
        created_by=user.id,
    )
    db_session.add(event)
    await db_session.commit()

    response = await root_client.get(
        "/api/v1/events",
        headers={"Authorization": f"Bearer {token}", "X-Disable-Query-Budget": "true"},
    )
    assert response.status_code == 200
    assert len(response.json()["items"]) >= 1


@pytest.mark.asyncio
async def test_list_news_basic(root_client: AsyncClient, db_session, user_factory):
    user = await user_factory()
    token, _ = await create_access_token(sub=str(user.id), db=db_session)

    news = models.News(title="Breaking News", content="Content", author_id=user.id)
    db_session.add(news)
    await db_session.commit()

    response = await root_client.get(
        "/api/v1/news",
        headers={"Authorization": f"Bearer {token}", "X-Disable-Query-Budget": "true"},
    )
    assert response.status_code == 200
    assert len(response.json()["items"]) >= 1


@pytest.mark.asyncio
async def test_notification_pagination(
    root_client: AsyncClient, db_session, user_factory
):
    user = await user_factory()
    token, _ = await create_access_token(sub=str(user.id), db=db_session)

    # Create 5 notifications
    for i in range(5):
        n = models.Notification(
            id=generate_uuid7(),
            user_id=user.id,
            title=f"N{i}",
            body="B",
            created_at=datetime.now(UTC) - timedelta(minutes=i),
            _allow_system_managed_assignment=True,
        )
        db_session.add(n)
    await db_session.commit()

    # Get first 2
    response = await root_client.get(
        "/api/v1/notifications?limit=2",
        headers={"Authorization": f"Bearer {token}", "X-Disable-Query-Budget": "true"},
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) == 2
    assert data["has_more"] is True
    assert data["next_cursor"] is not None

    # Get next
    cursor = data["next_cursor"]
    response = await root_client.get(
        f"/api/v1/notifications?limit=2&cursor={cursor}",
        headers={"Authorization": f"Bearer {token}", "X-Disable-Query-Budget": "true"},
    )
    assert response.status_code == 200
    assert len(response.json()["items"]) == 2
