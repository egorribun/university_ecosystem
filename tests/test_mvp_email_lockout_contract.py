"""Public login contract for the MVP's email-keyed lockout."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi import status
from sqlalchemy import select

from app.auth.security import get_password_hash
from app.core.config import settings
from app.core.localization import translate
from app.models import FailedLoginAttempt
from app.services.auth import credential_validator, lockout
from app.services.auth.lockout import LockoutService
from tests.helpers.synthetic_credentials import make_test_password

pytestmark = pytest.mark.asyncio(loop_scope="session")


@pytest.fixture
def lockout_clock(monkeypatch):
    class Clock(datetime):
        current = datetime.now(UTC).replace(microsecond=0)

        @classmethod
        def now(cls, tz=None):
            if tz is None:
                return cls.current.replace(tzinfo=None)
            return cls.current.astimezone(tz)

    monkeypatch.setattr(settings, "auth_lockout_thresholds", "5:30,8:300,10:3600")
    monkeypatch.setattr(settings, "auth_lockout_history_minutes", 1_440)
    monkeypatch.setattr(lockout, "datetime", Clock)
    monkeypatch.setattr(credential_validator, "datetime", Clock)
    return Clock


async def _seed_attempts(db_session, email, user_id, oldest, offsets):
    db_session.add_all(
        [
            FailedLoginAttempt(
                email=email,
                user_id=user_id,
                ip_address=("192.0.2.1" if index % 2 == 0 else "198.51.100.2"),
                attempted_at=oldest + timedelta(seconds=offset),
            )
            for index, offset in enumerate(offsets)
        ]
    )
    await db_session.commit()


async def _login(client, endpoint, email, password, locale):
    headers = {"Accept-Language": locale}
    if endpoint == "/auth/login":
        return await client.post(
            endpoint, data={"username": email, "password": password}, headers=headers
        )
    return await client.post(
        endpoint, json={"email": email, "password": password}, headers=headers
    )


def _assert_same_public_lockout(known, unknown, locale):
    assert known.status_code == unknown.status_code == status.HTTP_423_LOCKED
    assert known.headers["content-type"] == unknown.headers["content-type"]
    assert known.headers["content-type"].startswith("application/problem+json")
    assert known.headers["retry-after"] == unknown.headers["retry-after"]

    known_body, unknown_body = known.json(), unknown.json()
    # Trace IDs are request-specific, not authentication information.
    assert "trace_id" in known_body and "trace_id" in unknown_body
    known_body.pop("trace_id")
    unknown_body.pop("trace_id")
    assert known_body == unknown_body
    assert known_body["detail"] == translate(
        "errors.auth.account_locked", locale=locale
    )


@pytest.mark.parametrize(
    ("offsets", "duration"),
    [
        ((0, 1, 2, 3, 4), 30),
        ((0, 1, 2, 3, 4, 31, 32, 33), 300),
        ((0, 1, 2, 3, 4, 31, 32, 33, 301, 302), 3_600),
    ],
)
async def test_default_threshold_windows_expire_from_oldest_retained_attempt(
    db_session, lockout_clock, offsets, duration
):
    email = f"unknown-{uuid4().hex}@example.com"
    oldest = lockout_clock.current - timedelta(seconds=duration - 1)
    await _seed_attempts(db_session, email, None, oldest, offsets)
    service = LockoutService(db_session)

    assert await service.get_active_lockout(email) == oldest + timedelta(
        seconds=duration
    )
    lockout_clock.current += timedelta(seconds=1)
    assert await service.get_active_lockout(email) is None


@pytest.mark.parametrize("endpoint", ["/auth/login", "/auth/login/json"])
@pytest.mark.parametrize("locale", ["en", "ru"])
async def test_simulated_email_lockout_rejects_valid_password_and_expires(
    async_client, user_factory, db_session, lockout_clock, endpoint, locale
):
    assert type(settings).model_fields["auth_lockout_thresholds"].default == (
        "5:30,8:300,10:3600"
    )
    password = make_test_password()
    user = await user_factory(hashed_password=await get_password_hash(password))
    unknown_email = f"unknown-{uuid4().hex}@example.com"
    oldest = lockout_clock.current - timedelta(minutes=10)
    # The offsets respect the shorter 5- and 8-attempt lockout windows.
    offsets = (0, 1, 2, 3, 4, 31, 32, 33, 301, 302)
    await _seed_attempts(db_session, user.email, user.id, oldest, offsets)
    await _seed_attempts(db_session, unknown_email, None, oldest, offsets)

    expected_expiry = oldest + timedelta(hours=1)
    service = LockoutService(db_session)
    assert await service.get_active_lockout(user.email) == expected_expiry
    assert await service.get_active_lockout(unknown_email) == expected_expiry
    # get_active_lockout prunes stale rows in the caller's transaction.
    await db_session.commit()

    known = await _login(async_client, endpoint, user.email, password, locale)
    unknown = await _login(async_client, endpoint, unknown_email, password, locale)
    _assert_same_public_lockout(known, unknown, locale)
    assert int(known.headers["retry-after"]) == 3_000
    attempts = await db_session.execute(
        select(FailedLoginAttempt).where(FailedLoginAttempt.email == user.email)
    )
    assert len(attempts.scalars().all()) == 10
    await db_session.commit()

    lockout_clock.current = expected_expiry + timedelta(seconds=1)
    unlocked = await _login(async_client, endpoint, user.email, password, locale)
    assert unlocked.status_code == status.HTTP_200_OK
    attempts = await db_session.execute(
        select(FailedLoginAttempt).where(FailedLoginAttempt.email == user.email)
    )
    assert attempts.scalars().all() == []


@pytest.mark.parametrize("endpoint", ["/auth/login", "/auth/login/json"])
@pytest.mark.parametrize("locale", ["en", "ru"])
async def test_new_lockout_has_same_public_response_for_known_and_unknown_email(
    async_client, user_factory, db_session, lockout_clock, endpoint, locale
):
    password = make_test_password()
    incorrect = make_test_password(excluding=(password,))
    user = await user_factory(hashed_password=await get_password_hash(password))
    unknown_email = f"unknown-{uuid4().hex}@example.com"
    oldest = lockout_clock.current - timedelta(seconds=1)
    await _seed_attempts(db_session, user.email, user.id, oldest, (0, 0, 0, 0))
    await _seed_attempts(db_session, unknown_email, None, oldest, (0, 0, 0, 0))

    known = await _login(async_client, endpoint, user.email, incorrect, locale)
    unknown = await _login(async_client, endpoint, unknown_email, incorrect, locale)
    _assert_same_public_lockout(known, unknown, locale)
    assert int(known.headers["retry-after"]) == 29
