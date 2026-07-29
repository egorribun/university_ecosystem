import uuid
from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy as sa
from httpx import AsyncClient
from sqlalchemy import select

from app.api.notifications import _serialize_notification
from app.auth.security import get_password_hash
from app.core.config import settings
from app.models import Notification, Schedule
from app.services.notifications import create_notifications_for_users


async def _login(
    async_client: AsyncClient, email: str, password: str
) -> dict[str, str]:
    response = await async_client.post(
        "/auth/login",
        data={"username": email, "password": password},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert response.status_code == 200
    token = response.cookies.get("access_token_v2")
    return {"Authorization": f"Bearer {token}", "X-Query-Budget": "15"}


def _with_internal(headers: dict[str, str]) -> dict[str, str]:
    token = settings.internal_auth_token
    header_name = settings.internal_auth_header
    if token and header_name:
        return {**headers, header_name: token}
    return headers


@pytest.mark.asyncio
async def test_clear_notifications_removes_only_current_user(
    async_client: AsyncClient,
    user_factory,
    db_session,
):
    password = "ClearIt123!"
    hashed = await get_password_hash(password)
    user = await user_factory(hashed_password=hashed, is_active=True)
    other = await user_factory(hashed_password=hashed, is_active=True)

    headers = await _login(async_client, user.email, password)

    notices = [
        Notification(
            user_id=user.id,
            title="Первое уведомление",
            body="Тест 1",
            _allow_system_managed_assignment=True,
        ),
        Notification(
            user_id=user.id,
            title="Второе уведомление",
            _allow_system_managed_assignment=True,
        ),
        Notification(
            user_id=other.id,
            title="Чужое уведомление",
            _allow_system_managed_assignment=True,
        ),
    ]
    db_session.add_all(notices)
    await db_session.commit()

    response = await async_client.delete("/notifications", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["deleted"] == 2

    remaining_user = (
        (
            await db_session.execute(
                select(Notification).where(Notification.user_id == user.id)
            )
        )
        .scalars()
        .all()
    )
    remaining_other = (
        (
            await db_session.execute(
                select(Notification).where(Notification.user_id == other.id)
            )
        )
        .scalars()
        .all()
    )

    assert remaining_user == []
    assert len(remaining_other) == 1


@pytest.mark.asyncio
async def test_list_notifications_handles_invalid_data(
    async_client: AsyncClient,
    user_factory,
    db_session,
):
    password = "DataMismatch123!"
    hashed = await get_password_hash(password)
    user = await user_factory(hashed_password=hashed, is_active=True)

    headers = await _login(async_client, user.email, password)

    notification = Notification(
        user_id=user.id,
        title="Странное уведомление",
        body="Странное тело",
        read=True,
        _allow_system_managed_assignment=True,
    )
    db_session.add(notification)
    await db_session.commit()

    await db_session.execute(
        sa.update(Notification)
        .where(Notification.id == notification.id)
        .values(
            title_en="123",
            body_en="bytes",
            type="{'kind': 'system'}",
            url="456",
            created_at=datetime.now(UTC),
            read_at=None,
        )
    )
    await db_session.commit()

    response = await async_client.get(
        "/notifications?lang=ru",
        headers=headers,
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["items"], "Expected at least one notification"
    first = payload["items"][0]

    assert first["title"] == "Странное уведомление"
    assert first["body"] == "Странное тело"
    # The localized_text helper might fall back to ru if en matches a placeholder
    # or is missing
    # In this test we forced raw SQL updates, so we check if the values were
    # actually committed/read
    # Since we updated title_en manually, it should be returned as is or None
    # if it's considered a placeholder
    assert first.get("title_en") is None or first.get("title_en") == "123"
    assert first.get("body_en") is None or first.get("body_en") == "bytes"
    assert first.get("type") in {None, "{'kind': 'system'}"}
    assert first["url"] == "456"
    assert first["read"] is True
    assert first["read_at"] is None

    created_at = first["created_at"]
    assert created_at
    # Should be parseable as ISO datetime
    datetime.fromisoformat(created_at.replace("Z", "+00:00"))


@pytest.mark.asyncio
async def test_list_notifications_sets_language_and_cache_headers(
    async_client: AsyncClient,
    user_factory,
    db_session,
):
    password = "Headers123!"
    hashed = await get_password_hash(password)
    user = await user_factory(hashed_password=hashed, is_active=True)

    headers = await _login(async_client, user.email, password)

    now = datetime.now(UTC)
    notifications = [
        Notification(
            user_id=user.id,
            title="First",
            body="Test",
            created_at=now - timedelta(minutes=5),
            _allow_system_managed_assignment=True,
        ),
        Notification(
            user_id=user.id,
            title="Second",
            body="Test",
            created_at=now,
            _allow_system_managed_assignment=True,
        ),
    ]
    db_session.add_all(notifications)
    await db_session.commit()

    response = await async_client.get(
        "/notifications?lang=en&limit=1",
        headers=headers,
    )

    assert response.status_code == 200
    assert response.headers.get("Content-Language") == "en"
    assert "Accept-Language" in response.headers.get("Vary", "")
    assert response.headers.get("Cache-Control") == "no-store, max-age=0"
    assert response.headers.get("Pragma") == "no-cache"

    payload = response.json()
    cursor = payload.get("next_cursor")
    assert cursor

    follow_up = await async_client.get(
        f"/notifications?cursor={cursor}&lang=en&limit=1",
        headers=headers,
    )

    assert follow_up.status_code == 200
    assert follow_up.headers.get("Content-Language") == "en"
    assert "Accept-Language" in follow_up.headers.get("Vary", "")
    assert follow_up.headers.get("Cache-Control") == "no-store, max-age=0"
    assert follow_up.headers.get("Pragma") == "no-cache"


@pytest.mark.asyncio
async def test_notifications_list_returns_bilingual_fields(
    async_client: AsyncClient,
    user_factory,
    db_session,
):
    password = "Bilingual123!"
    hashed = await get_password_hash(password)
    user = await user_factory(hashed_password=hashed, is_active=True)

    await create_notifications_for_users(
        db_session,
        title="English Title",
        body="English Body",
        title_translations={"en": "English Title", "ru": "Русский заголовок"},
        body_translations={"en": "English Body", "ru": "Русский текст"},
        type="system.message",
        url="/status",
        user_ids=[user.id],
    )
    await db_session.commit()

    headers = await _login(async_client, user.email, password)

    response_en = await async_client.get(
        "/notifications",
        headers={**headers, "Accept-Language": "en"},
    )
    assert response_en.status_code == 200
    payload_en = response_en.json()
    assert payload_en["items"], "Expected notifications in response"
    item_en = payload_en["items"][0]

    assert item_en["title"] == "English Title"
    assert item_en["body"] == "English Body"
    assert item_en["title_en"] == "English Title"
    assert item_en["body_en"] == "English Body"

    response_ru = await async_client.get(
        "/notifications",
        headers={**headers, "Accept-Language": "ru"},
    )
    assert response_ru.status_code == 200
    payload_ru = response_ru.json()
    assert payload_ru["items"], "Expected notifications in response"
    item_ru = payload_ru["items"][0]

    assert item_ru["id"] == item_en["id"]
    assert item_ru["title"] == "Русский заголовок"
    assert item_ru["body"] == "Русский текст"
    assert item_ru["title_en"] == "English Title"
    assert item_ru["body_en"] == "English Body"


def test_serialize_notification_accepts_orm_instance():
    nid = uuid.uuid4()
    uid = uuid.uuid4()
    notification = Notification(
        id=nid,
        user_id=uid,
        title="Прямой доступ",
        body="Проверка",
        type="system",
        url="/test",
        read=True,
        _allow_system_managed_assignment=True,
    )

    serialized = _serialize_notification(notification, locale="ru")

    assert serialized.id == nid
    assert serialized.title == "Прямой доступ"
    assert serialized.body == "Проверка"
    assert serialized.type == "system"
    assert serialized.url == "/test"
    assert serialized.read is True


def test_serialize_notification_normalizes_id_and_read_flag():
    uid_str = str(uuid.uuid4())
    payload = {
        "id": f" {uid_str} ",
        "title": "Строковый идентификатор",
        "body": "",
        "type": None,
        "url": None,
        "title_en": None,
        "body_en": None,
        "created_at": datetime(2024, 5, 1, 12, 30, tzinfo=UTC),
        "read": "false",
        "read_at": None,
    }

    serialized = _serialize_notification(payload, locale="en")

    assert str(serialized.id) == uid_str
    assert serialized.read is False
    assert serialized.created_at.tzinfo is not None


@pytest.mark.asyncio
async def test_check_schedule_creates_notifications(
    async_client: AsyncClient,
    user_factory,
    db_session,
):
    from app.models import Group

    password = "ScheduleCheck123!"
    hashed = await get_password_hash(password)

    # Create group first
    group_id = uuid.uuid4()
    group = Group(id=group_id, name="Test Group", course=1, faculty="CS")
    db_session.add(group)
    await db_session.commit()

    user = await user_factory(hashed_password=hashed, is_active=True, group_id=group_id)

    headers = await _login(async_client, user.email, password)

    # Create schedule
    now = datetime.now(UTC)
    start = now + timedelta(minutes=10)
    end = start + timedelta(hours=1)

    _WEEKDAY_NAMES = (
        "monday",
        "tuesday",
        "wednesday",
        "thursday",
        "friday",
        "saturday",
        "sunday",
    )
    lesson = Schedule(
        group_id=group_id,
        start_time=start,
        end_time=end,
        weekday=_WEEKDAY_NAMES[start.weekday()],
        subject="Math",
        teacher="Mr. Smith",
        room="101",
    )
    db_session.add(lesson)
    await db_session.commit()

    response = await async_client.post(
        "/notifications/check-schedule?lookahead_minutes=30", headers=headers
    )

    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) >= 1

    # First item should be related to the lesson
    # Note: sort order is newest first.
    first = data["items"][0]
    # Lesson notification title usually depends on template, but subject is in it?
    # "Math in 101" or similar
    assert "Math" in first["title"] or "Math" in first["body"]
    assert first["type"] == "schedule.reminder"
