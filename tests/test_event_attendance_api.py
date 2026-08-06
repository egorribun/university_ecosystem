import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import status
from sqlalchemy import select

import app.models as models
from app.auth.security import get_password_hash
from app.core.localization import translate
from app.services import attendance_tokens


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
async def test_attend_registers_event(async_client, db_session, user_factory):
    password = "AttendSuccess123!"
    student = await user_factory(
        hashed_password=await get_password_hash(password),
        is_active=True,
    )
    admin = await user_factory(role="admin")

    now = datetime.now(UTC)
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
        json={"event_id": str(event.id)},
    )
    assert response.status_code == status.HTTP_200_OK
    payload = response.json()
    assert payload["event_id"] == str(event.id)
    assert payload["user_id"] == str(student.id)
    assert payload["qr_token"]


@pytest.mark.asyncio
async def test_attend_missing_event_returns_not_found(
    async_client, db_session, user_factory
):
    password = "AttendMissing123!"
    student = await user_factory(
        hashed_password=await get_password_hash(password),
        is_active=True,
    )

    headers = await _login(async_client, student.email, password)
    base_headers = {**headers, "Accept-Language": "en"}

    response = await async_client.post(
        "/events/attendance",
        headers=base_headers,
        json={"event_id": str(uuid.uuid4())},
    )
    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.json()["detail"] == translate(
        "errors.events.not_found", locale="en"
    )


@pytest.mark.asyncio
async def test_attend_registration_closed_returns_conflict(
    async_client, db_session, user_factory
):
    password = "AttendClosed123!"
    student = await user_factory(
        hashed_password=await get_password_hash(password),
        is_active=True,
    )
    admin = await user_factory(role="admin")

    now = datetime.now(UTC)
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
        json={"event_id": str(event.id)},
    )
    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.json()["detail"] == translate(
        "errors.events.registration_closed", locale="en"
    )


@pytest.mark.asyncio
async def test_attend_restores_missing_registration_timestamp(
    async_client, db_session, user_factory
):
    password = "AttendRestore123!"
    student = await user_factory(
        hashed_password=await get_password_hash(password),
        is_active=True,
    )
    admin = await user_factory(role="admin")

    now = datetime.now(UTC)
    event = models.Event(
        title="Restore timestamp",
        starts_at=now + timedelta(hours=1),
        ends_at=now + timedelta(hours=2),
        created_by=admin.id,
        is_active=True,
    )
    db_session.add(event)
    await db_session.commit()
    await db_session.refresh(event)

    secret = attendance_tokens.generate_secret()
    attendance = models.EventAttendance(
        user_id=student.id,
        event_id=event.id,
        registered_at=None,
        qr_secret=secret,
        qr_hmac=attendance_tokens.compute_secret_hmac(secret),
    )
    db_session.add(attendance)
    await db_session.commit()
    await db_session.refresh(attendance)

    headers = await _login(async_client, student.email, password)
    base_headers = {**headers, "Accept-Language": "en"}

    response = await async_client.post(
        "/events/attendance",
        headers=base_headers,
        json={"event_id": str(event.id)},
    )
    assert response.status_code == status.HTTP_200_OK
    payload = response.json()
    assert payload["event_id"] == str(event.id)
    assert payload["user_id"] == str(student.id)
    assert payload["qr_token"]
    assert payload["registered_at"] is not None

    await db_session.refresh(attendance)
    assert attendance.registered_at is not None
    assert attendance.qr_secret
    assert attendance.qr_hmac


async def _register_for_event(
    async_client,
    db_session,
    user_factory,
    *,
    locale: str = "en",
):
    password = "TokenFlow123!"
    student = await user_factory(
        hashed_password=await get_password_hash(password),
        is_active=True,
    )
    admin = await user_factory(role="admin")

    now = datetime.now(UTC)
    event = models.Event(
        title="Token event",
        starts_at=now + timedelta(hours=1),
        ends_at=now + timedelta(hours=2),
        created_by=admin.id,
        is_active=True,
    )
    db_session.add(event)
    await db_session.commit()
    await db_session.refresh(event)

    headers = await _login(async_client, student.email, password)
    base_headers = {**headers, "Accept-Language": locale}
    response = await async_client.post(
        "/events/attendance",
        headers=base_headers,
        json={"event_id": str(event.id)},
    )
    assert response.status_code == status.HTTP_200_OK
    token = response.json()["qr_token"]

    attendance = (
        await db_session.execute(
            select(models.EventAttendance).where(
                models.EventAttendance.event_id == event.id,
                models.EventAttendance.user_id == student.id,
            )
        )
    ).scalar_one()

    return token, attendance, event, student


@pytest.mark.asyncio
async def test_attendance_token_can_be_verified(async_client, db_session, user_factory):
    token, attendance, event, student = await _register_for_event(
        async_client, db_session, user_factory
    )
    payload = attendance_tokens.verify_token(token, attendance)
    assert str(payload.event_id) == str(event.id)
    assert str(payload.user_id) == str(student.id)


@pytest.mark.asyncio
async def test_attendance_token_reuse_rejected_after_expiry(
    async_client, db_session, user_factory, monkeypatch
):
    monkeypatch.setattr(attendance_tokens.settings, "attendance_token_ttl_seconds", 1)
    token, attendance, _, _ = await _register_for_event(
        async_client, db_session, user_factory
    )
    payload = attendance_tokens.verify_token(token, attendance)
    expired_at = datetime.fromtimestamp(payload.expires_at + 1, tz=UTC)
    with pytest.raises(attendance_tokens.AttendanceTokenExpired):
        attendance_tokens.verify_token(token, attendance, now=expired_at)


@pytest.mark.asyncio
async def test_attendance_token_signature_tampering(
    async_client, db_session, user_factory
):
    token, attendance, _, _ = await _register_for_event(
        async_client, db_session, user_factory
    )
    tampered = token[:-1] + ("A" if token[-1] != "A" else "B")
    with pytest.raises(attendance_tokens.AttendanceTokenInvalid):
        attendance_tokens.verify_token(tampered, attendance)
