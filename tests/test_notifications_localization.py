from datetime import UTC, datetime

import pytest

import app.models as models
from app.auth.security import get_password_hash


async def _login(async_client, email: str, password: str) -> dict[str, str]:
    response = await async_client.post(
        "/auth/login",
        data={"username": email, "password": password},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert response.status_code == 200
    token = response.cookies.get("access_token_v2")
    return {"Authorization": f"Bearer {token}", "X-Query-Budget": "15"}


@pytest.mark.asyncio
async def test_notifications_localization(async_client, db_session, user_factory):
    password = "Notify123!"
    hashed = await get_password_hash(password)
    user = await user_factory(hashed_password=hashed, is_active=True)

    now = datetime.now(UTC)
    primary = models.Notification(
        user_id=user.id,
        created_at=now,
        title="Новое уведомление",
        body="Русский текст",
        title_en="New notification",
        body_en="English body",
        _allow_system_managed_assignment=True,
    )
    fallback = models.Notification(
        user_id=user.id,
        created_at=now,
        title="Без перевода",
        body="Только русский текст",
        _allow_system_managed_assignment=True,
    )
    db_session.add_all([primary, fallback])
    await db_session.commit()
    await db_session.refresh(primary)
    await db_session.refresh(fallback)

    headers = await _login(async_client, user.email, password)

    response_en = await async_client.get(
        "/notifications",
        headers={**headers, "Accept-Language": "en"},
    )
    assert response_en.status_code == 200
    body_en = response_en.json()
    items_en = {item["id"]: item for item in body_en["items"]}

    assert items_en[str(primary.id)]["title"] == "New notification"
    assert items_en[str(primary.id)]["body"] == "English body"
    assert items_en[str(primary.id)]["title_en"] == "New notification"
    assert items_en[str(primary.id)]["body_en"] == "English body"

    assert items_en[str(fallback.id)]["title"] == "Без перевода"
    assert items_en[str(fallback.id)]["body"] == "Только русский текст"
    assert items_en[str(fallback.id)]["title_en"] is None
    assert items_en[str(fallback.id)]["body_en"] is None

    response_ru = await async_client.get(
        "/notifications",
        headers={**headers, "Accept-Language": "ru"},
    )
    assert response_ru.status_code == 200
    body_ru = response_ru.json()
    items_ru = {item["id"]: item for item in body_ru["items"]}

    assert items_ru[str(primary.id)]["title"] == "Новое уведомление"
    assert items_ru[str(primary.id)]["body"] == "Русский текст"
    assert items_ru[str(fallback.id)]["title"] == "Без перевода"
    assert items_ru[str(fallback.id)]["body"] == "Только русский текст"

    assert body_en["unread_count"] == 2
    assert body_ru["unread_count"] == 2
