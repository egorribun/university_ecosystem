from datetime import UTC, datetime, timedelta

import pytest
from fastapi import status

from app.auth.security import get_password_hash


async def _login(async_client, email: str, password: str) -> dict[str, str]:
    response = await async_client.post(
        "/auth/login",
        data={"username": email, "password": password},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert response.status_code == status.HTTP_200_OK
    token = response.cookies.get("access_token_v2")
    return {"Authorization": f"Bearer {token}", "X-Query-Budget": "15"}


@pytest.mark.asyncio
async def test_create_event_frontend_payload_reproduction(async_client, user_factory):
    password = "EventFix123!"
    teacher = await user_factory(
        role="teacher",
        hashed_password=await get_password_hash(password),
        is_active=True,
    )

    headers = await _login(async_client, teacher.email, password)

    # Simulate Date.now() + 1h
    # Frontend logic allows starts == ends because checks `ends < starts` (not <=)
    # But Backend EventCreate validator checks `ends_at <= starts_at`
    # -> raises ValueError -> returns 422

    now = datetime.now(UTC)
    starts_at = (now + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M")
    # Same time for end
    ends_at = starts_at

    # Payload similar to what frontend sends (empty strings for optionals)
    payload = {
        "title": "Frontend Event",
        "title_en": "",
        "description": "",
        "description_en": "",
        "event_type": "",
        "event_type_en": "",
        "location": "Loc",
        "location_en": "",
        "starts_at": starts_at,
        "ends_at": ends_at,
        "speaker": "",
        "image_url": "",
        "about": "",
        "about_en": "",
    }

    # Expecting 422
    response = await async_client.post(
        "/events",
        headers=headers,
        json=payload,
    )

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    # print(f"\nConfimed 422 Error for equal times: {response.json()}")


@pytest.mark.asyncio
async def test_create_event_success_db(async_client, user_factory):
    """
    Test that a fully valid payload successfully creates an event in the DB.
    This verifies that the 'search_vector' (Computed) issue is resolved,
    as we expect the INSERT to succeed now.
    """
    password = "EventFix123!"
    teacher = await user_factory(
        role="teacher",
        hashed_password=await get_password_hash(password),
        is_active=True,
    )

    headers = await _login(async_client, teacher.email, password)

    now = datetime.now(UTC)
    # Explicitly valid times
    starts_at = (now + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M")
    ends_at = (now + timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M")

    payload = {
        "title": "Valid DB Event",
        "title_en": "Valid DB Event EN",
        "description": "Desc",
        "description_en": "Desc EN",
        "event_type": "lecture",
        "event_type_en": "Lecture",
        "location": "Room 101",
        "location_en": "Room 101",
        "starts_at": starts_at,
        "ends_at": ends_at,
        "speaker": "Prof X",
        "image_url": "",
        "about": "",
        "about_en": "",
    }

    response = await async_client.post(
        "/events",
        headers=headers,
        json=payload,
    )

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    # Use 'in' to handle potential localization (Valid DB Event or Valid DB Event EN)
    assert "Valid DB Event" in data["title"]
    assert data["id"] is not None
