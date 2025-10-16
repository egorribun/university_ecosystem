import pytest
from datetime import datetime, timedelta, timezone

from app.auth.security import get_password_hash
from app.models import models


async def _login(async_client, email: str, password: str) -> dict[str, str]:
    response = await async_client.post(
        "/auth/login",
        data={"username": email, "password": password},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert response.status_code == 200
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.anyio
async def test_events_localization(async_client, db_session, user_factory):
    password = "TestEvent123!"
    hashed = get_password_hash(password)
    admin = await user_factory(role="admin")
    student = await user_factory(hashed_password=hashed, is_active=True)

    now = datetime.now(timezone.utc)
    primary = models.Event(
        title="Русское событие",
        description="Описание по-русски",
        location="Москва",
        event_type="лекция",
        about="Подробности",
        title_en="English Event",
        description_en="Description in English",
        location_en="Moscow",
        event_type_en="Lecture",
        about_en="More details",
        starts_at=now + timedelta(days=1),
        ends_at=now + timedelta(days=1, hours=2),
        created_by=admin.id,
        is_active=True,
    )
    fallback = models.Event(
        title="Только русский",
        description="Без перевода",
        location="Санкт-Петербург",
        event_type="встреча",
        about="Описание только на русском",
        starts_at=now + timedelta(days=2),
        ends_at=now + timedelta(days=2, hours=3),
        created_by=admin.id,
        is_active=True,
    )

    db_session.add_all([primary, fallback])
    await db_session.commit()
    await db_session.refresh(primary)
    await db_session.refresh(fallback)

    headers = await _login(async_client, student.email, password)

    response_en = await async_client.get(
        "/events",
        headers={**headers, "Accept-Language": "en"},
    )
    assert response_en.status_code == 200
    payload_en = {item["id"]: item for item in response_en.json()}

    assert payload_en[primary.id]["title"] == "English Event"
    assert payload_en[primary.id]["description"] == "Description in English"
    assert payload_en[primary.id]["location"] == "Moscow"
    assert payload_en[primary.id]["event_type"] == "Lecture"
    assert payload_en[primary.id]["about"] == "More details"
    assert payload_en[primary.id]["title_en"] == "English Event"
    assert payload_en[primary.id]["description_en"] == "Description in English"

    assert payload_en[fallback.id]["title"] == "Только русский"
    assert payload_en[fallback.id]["description"] == "Без перевода"
    assert payload_en[fallback.id]["location"] == "Санкт-Петербург"
    assert payload_en[fallback.id]["event_type"] == "встреча"
    assert payload_en[fallback.id]["about"] == "Описание только на русском"
    assert payload_en[fallback.id]["title_en"] is None

    response_ru = await async_client.get(
        "/events",
        headers={**headers, "Accept-Language": "ru"},
    )
    assert response_ru.status_code == 200
    payload_ru = {item["id"]: item for item in response_ru.json()}

    assert payload_ru[primary.id]["title"] == "Русское событие"
    assert payload_ru[primary.id]["description"] == "Описание по-русски"
    assert payload_ru[primary.id]["location"] == "Москва"
    assert payload_ru[primary.id]["event_type"] == "лекция"
    assert payload_ru[primary.id]["about"] == "Подробности"
    assert payload_ru[fallback.id]["title"] == "Только русский"
    assert payload_ru[fallback.id]["description"] == "Без перевода"
