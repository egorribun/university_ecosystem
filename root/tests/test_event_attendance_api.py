import pytest
from datetime import datetime, timedelta, timezone
from fastapi import status

from app.auth.security import get_password_hash
from app.localization import translate
from app.models import models


async def _login(async_client, email: str, password: str) -> dict[str, str]:
    response = await async_client.post(
        "/auth/login",
        data={"username": email, "password": password},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert response.status_code == status.HTTP_200_OK
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.anyio
async def test_attend_registers_event(async_client, db_session, user_factory):
    password = "AttendSuccess123!"
    student = await user_factory(
        hashed_password=get_password_hash(password),
        is_active=True,
    )
    admin = await user_factory(role="admin")

    now = datetime.now(timezone.utc)
    event = models.Event(
        title="Register me",
        starts_at=now + timedelta(hours=1),
        ends_at=now + timedelta(hours=2),
        created_by=admin.id,
        is_active=True,
    )
    db_session.add(event)
    await db_session.commit()
    await db_session.refresh(event)

    headers = await _login(async_client, student.email, password)
    base_headers = {**headers, "Accept-Language": "en"}

    response = await async_client.post(
        "/events/attendance",
        headers=base_headers,
        json={"event_id": event.id},
    )
    assert response.status_code == status.HTTP_200_OK
    payload = response.json()
    assert payload["event_id"] == event.id
    assert payload["user_id"] == student.id
    assert payload["qr_code"]


@pytest.mark.anyio
async def test_attend_missing_event_returns_not_found(
    async_client, db_session, user_factory
):
    password = "AttendMissing123!"
    student = await user_factory(
        hashed_password=get_password_hash(password),
        is_active=True,
    )

    headers = await _login(async_client, student.email, password)
    base_headers = {**headers, "Accept-Language": "en"}

    response = await async_client.post(
        "/events/attendance",
        headers=base_headers,
        json={"event_id": 999999},
    )
    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.json()["detail"] == translate(
        "errors.events.not_found", locale="en"
    )


@pytest.mark.anyio
async def test_attend_registration_closed_returns_conflict(
    async_client, db_session, user_factory
):
    password = "AttendClosed123!"
    student = await user_factory(
        hashed_password=get_password_hash(password),
        is_active=True,
    )
    admin = await user_factory(role="admin")

    now = datetime.now(timezone.utc)
    event = models.Event(
        title="Too late",
        starts_at=now - timedelta(hours=2),
        ends_at=now - timedelta(hours=1),
        created_by=admin.id,
        is_active=True,
    )
    db_session.add(event)
    await db_session.commit()
    await db_session.refresh(event)

    headers = await _login(async_client, student.email, password)
    base_headers = {**headers, "Accept-Language": "en"}

    response = await async_client.post(
        "/events/attendance",
        headers=base_headers,
        json={"event_id": event.id},
    )
    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.json()["detail"] == translate(
        "errors.events.registration_closed", locale="en"
    )
