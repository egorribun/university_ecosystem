from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select, text, update

from app.api.notifications import _serialize_notification
from app.auth.security import get_password_hash
from app.core.config import settings
from app.core.database import async_session
from app.localization import translate
from app.models.models import Notification, Schedule
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
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _with_internal(headers: dict[str, str]) -> dict[str, str]:
    token = settings.internal_auth_token
    header_name = settings.internal_auth_header
    if token and header_name:
        return {**headers, header_name: token}
    return headers


@pytest.mark.anyio
async def test_clear_notifications_removes_only_current_user(
    async_client: AsyncClient,
    user_factory,
    db_session,
):
    password = "ClearIt123!"
    hashed = get_password_hash(password)
    user = await user_factory(hashed_password=hashed, is_active=True)
    other = await user_factory(hashed_password=hashed, is_active=True)

    headers = await _login(async_client, user.email, password)

    notices = [
        Notification(user_id=user.id, title="Первое уведомление", body="Тест 1"),
        Notification(user_id=user.id, title="Второе уведомление"),
        Notification(user_id=other.id, title="Чужое уведомление"),
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


@pytest.mark.anyio
async def test_list_notifications_handles_missing_created_at(
    async_client: AsyncClient,
    user_factory,
    db_session,
):
    password = "MissingTime123!"
    hashed = get_password_hash(password)
    user = await user_factory(hashed_password=hashed, is_active=True)

    headers = await _login(async_client, user.email, password)

    notification = Notification(user_id=user.id, title="Без времени", body="Тест")
    db_session.add(notification)
    await db_session.commit()

    await db_session.execute(
        update(Notification)
        .where(Notification.id == notification.id)
        .values(created_at=None)
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
    assert first["title"] == "Без времени"
    assert first["created_at"], "created_at should be populated even if missing in DB"


@pytest.mark.anyio
async def test_list_notifications_handles_invalid_data(
    async_client: AsyncClient,
    user_factory,
    db_session,
):
    password = "DataMismatch123!"
    hashed = get_password_hash(password)
    user = await user_factory(hashed_password=hashed, is_active=True)

    headers = await _login(async_client, user.email, password)

    notification = Notification(
        user_id=user.id,
        title="Странное уведомление",
        body="Странное тело",
        read=True,
    )
    db_session.add(notification)
    await db_session.commit()

    await db_session.execute(
        text(
            """
            UPDATE notifications
            SET title_en = :title_en,
                body_en = :body_en,
                type = :type_value,
                url = :url_value,
                created_at = :created_at,
                read_at = :read_at
            WHERE id = :id
            """
        ),
        {
            "title_en": 123,
            "body_en": b"bytes",
            "type_value": "{'kind': 'system'}",
            "url_value": 456,
            "created_at": "not-a-valid-date",
            "read_at": " ",
            "id": notification.id,
        },
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
    assert first["title_en"] == "123"
    assert first["body_en"] == "bytes"
    assert first["type"] == "{'kind': 'system'}"
    assert first["url"] == "456"
    assert first["read"] is True
    assert first["read_at"] is None

    created_at = first["created_at"]
    assert created_at
    # Should be parseable as ISO datetime
    from datetime import datetime

    datetime.fromisoformat(created_at.replace("Z", "+00:00"))


@pytest.mark.anyio
async def test_list_notifications_sets_language_and_cache_headers(
    async_client: AsyncClient,
    user_factory,
    db_session,
):
    password = "Headers123!"
    hashed = get_password_hash(password)
    user = await user_factory(hashed_password=hashed, is_active=True)

    headers = await _login(async_client, user.email, password)

    now = datetime.now(UTC)
    notifications = [
        Notification(
            user_id=user.id,
            title="First",
            body="Test",
            created_at=now - timedelta(minutes=5),
        ),
        Notification(
            user_id=user.id,
            title="Second",
            body="Test",
            created_at=now,
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


@pytest.mark.anyio
async def test_notifications_list_returns_bilingual_fields(
    async_client: AsyncClient,
    user_factory,
    db_session,
):
    password = "Bilingual123!"
    hashed = get_password_hash(password)
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
    notification = Notification(
        id=42,
        user_id=10,
        title="Прямой доступ",
        body="Проверка",
        type="system",
        url="/test",
        read=True,
    )

    serialized = _serialize_notification(notification, locale="ru")

    assert serialized.id == 42
    assert serialized.title == "Прямой доступ"
    assert serialized.body == "Проверка"
    assert serialized.type == "system"
    assert serialized.url == "/test"
    assert serialized.read is True


def test_serialize_notification_normalizes_id_and_read_flag():
    payload = {
        "id": " 105 ",
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

    assert serialized.id == 105
    assert serialized.read is False
    assert serialized.created_at.tzinfo is not None


@pytest.mark.anyio
async def test_check_schedule_creates_notifications(
    async_client: AsyncClient,
    user_factory,
    db_session,
):
    password = "ScheduleCheck123!"
    hashed = get_password_hash(password)
    user = await user_factory(hashed_password=hashed, is_active=True, group_id=10)
    
    headers = await _login(async_client, user.email, password)

    # Create schedule
    now = datetime.now(UTC)
    start = now + timedelta(minutes=10)
    end = start + timedelta(hours=1)
    
    lesson = Schedule(
        group_id=10,
        start_time=start,
        end_time=end,
        subject="Math",
        teacher="Mr. Smith",
        room="101"
    )
    db_session.add(lesson)
    await db_session.commit()
    
    response = await async_client.post(
        "/notifications/check-schedule?lookahead_minutes=30",
        headers=headers
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






