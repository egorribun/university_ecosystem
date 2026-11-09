import asyncio
import json
import logging
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import status
from sqlalchemy import select

from app.auth.security import get_password_hash
from app.core.config import settings
from app.core.localization import translate
from app.models import FailedLoginAttempt
from app.services.auth.lockout import LockoutService

pytestmark = pytest.mark.asyncio(loop_scope="session")

_HEADERS = {"Content-Type": "application/x-www-form-urlencoded"}


from typing import Any


def _find_event(caplog: Any, event: str) -> dict[Any, Any] | None:
    for record in reversed(caplog.records):
        if record.name != "app.auth":
            continue
        try:
            payload = json.loads(record.getMessage())
            if isinstance(payload, dict) and payload.get("event") == event:
                return payload
        except json.JSONDecodeError:
            continue
    return None


async def _login(async_client, email: str, password: str):
    return await async_client.post(
        "/auth/login",
        data={"username": email, "password": password},
        headers=_HEADERS,
    )


async def test_malformed_database_url_uses_non_postgresql_lockout_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "database_url", "malformed database URL")

    service = LockoutService(AsyncMock())  # type: ignore[arg-type]

    assert service._is_postgresql is False


async def test_login_lockout_enforced(
    async_client, user_factory, db_session, monkeypatch, caplog
):
    monkeypatch.setattr(settings, "auth_lockout_thresholds", "2:3")
    monkeypatch.setattr(settings, "auth_lockout_history_minutes", 5)
    caplog.set_level(logging.INFO)
    caplog.clear()

    hashed = await get_password_hash("ValidPass123!")
    user = await user_factory(
        hashed_password=hashed,
        is_active=True,
        email_verified_at=datetime.now(UTC),
    )

    first = await _login(async_client, user.email, "WrongPass!1")
    assert first.status_code == status.HTTP_401_UNAUTHORIZED

    with patch("app.tasks.email.send_lockout_alert") as mock_alert_func:
        mock_alert_func.kick = AsyncMock()
        second = await _login(async_client, user.email, "WrongPass!1")
        assert second.status_code == status.HTTP_423_LOCKED

        mock_alert_func.kick.assert_called_once()
        args = mock_alert_func.kick.call_args[0]
        assert args[0] == user.email

    detail = second.json()["detail"]
    assert translate("errors.auth.account_locked", locale="en") in detail
    retry_after = int(second.headers["Retry-After"])
    assert retry_after >= 1

    result = await db_session.execute(
        select(FailedLoginAttempt).where(FailedLoginAttempt.email == user.email)
    )
    attempts = result.scalars().all()
    assert len(attempts) == 2

    locked_event = _find_event(caplog, "auth.login.locked")
    assert locked_event is not None
    assert locked_event.get("reason") == "lockout"


async def test_login_lockout_clears_after_success(
    async_client, user_factory, db_session, monkeypatch, caplog
):
    # Drive lockout expiry with a deterministic clock instead of wall time.
    monkeypatch.setattr(settings, "auth_lockout_thresholds", "2:3")
    monkeypatch.setattr(settings, "auth_lockout_history_minutes", 5)
    caplog.set_level(logging.INFO)
    caplog.clear()

    password = "ValidPass123!"
    hashed = await get_password_hash(password)
    user = await user_factory(hashed_password=hashed, is_active=True)

    from app.models import auth as auth_models
    from app.services.auth import credential_validator as credential_validator_module
    from app.services.auth import lockout as lockout_module

    class _MutableClock:
        current = datetime(2040, 1, 1, tzinfo=UTC)

        @classmethod
        def now(cls, tz=None):
            if tz is None:
                return cls.current.replace(tzinfo=None)
            return cls.current.astimezone(tz)

        @classmethod
        def advance(cls, seconds: int) -> None:
            cls.current += timedelta(seconds=seconds)

    monkeypatch.setattr(lockout_module, "datetime", _MutableClock)
    monkeypatch.setattr(credential_validator_module, "datetime", _MutableClock)
    # FailedLoginAttempt's Python default calls datetime.now at insert time.
    # Freeze it only while attempts are created, then restore auth-model time
    # before successful-login session rows are written.
    with monkeypatch.context() as attempt_clock:
        attempt_clock.setattr(auth_models, "datetime", _MutableClock)
        await _login(async_client, user.email, "WrongPass!1")
        await _login(async_client, user.email, "WrongPass!1")

        locked = await _login(async_client, user.email, "WrongPass!1")
        assert locked.status_code == status.HTTP_423_LOCKED

    # Lockout ends at T+3s; advance to T+4s so the success path is unambiguous.
    _MutableClock.advance(seconds=4)
    success = await _login(async_client, user.email, password)
    assert success.status_code == status.HTTP_200_OK

    result = await db_session.execute(
        select(FailedLoginAttempt).where(FailedLoginAttempt.email == user.email)
    )
    assert not result.scalars().all()

    unlocked_event = _find_event(caplog, "auth.login.unlocked")
    assert unlocked_event is not None
    assert unlocked_event.get("reason") == "successful_login"


async def test_login_lockout_race_condition(
    async_client, user_factory, db_session, monkeypatch
):
    monkeypatch.setattr(settings, "auth_lockout_thresholds", "2:5")
    monkeypatch.setattr(settings, "auth_lockout_history_minutes", 5)

    hashed = await get_password_hash("RacePass123!")
    user = await user_factory(hashed_password=hashed, is_active=True)

    async def attempt():
        return await _login(async_client, user.email, "WrongPass!1")

    first, second = await asyncio.gather(attempt(), attempt())
    assert {first.status_code, second.status_code} <= {
        status.HTTP_401_UNAUTHORIZED,
        status.HTTP_423_LOCKED,
    }

    third = await _login(async_client, user.email, "WrongPass!1")
    assert third.status_code == status.HTTP_423_LOCKED

    result = await db_session.execute(
        select(FailedLoginAttempt).where(FailedLoginAttempt.email == user.email)
    )
    assert len(result.scalars().all()) >= 2
