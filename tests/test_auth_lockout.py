import asyncio
import json
import logging
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import status
from sqlalchemy import select

from app.auth.security import get_password_hash
from app.core.config import settings
from app.core.localization import translate
from app.models.models import FailedLoginAttempt

pytestmark = pytest.mark.anyio("asyncio")

_HEADERS = {"Content-Type": "application/x-www-form-urlencoded"}


def _find_event(caplog, event: str) -> dict | None:
    for record in reversed(caplog.records):
        if record.name != "app.auth":
            continue
        try:
            payload = json.loads(record.message)
        except json.JSONDecodeError:  # pragma: no cover - defensive guard
            continue
        if payload.get("event") == event:
            return payload
    return None


async def _login(async_client, email: str, password: str):
    return await async_client.post(
        "/auth/login",
        data={"username": email, "password": password},
        headers=_HEADERS,
    )


async def test_login_lockout_enforced(
    async_client, user_factory, db_session, monkeypatch, caplog
):
    monkeypatch.setattr(settings, "auth_lockout_thresholds", "2:3")
    monkeypatch.setattr(settings, "auth_lockout_history_minutes", 5)
    caplog.set_level(logging.INFO)
    caplog.clear()

    hashed = get_password_hash("ValidPass123!")
    user = await user_factory(hashed_password=hashed, is_active=True)

    first = await _login(async_client, user.email, "WrongPass!1")
    assert first.status_code == status.HTTP_401_UNAUTHORIZED

    with patch("app.auth.auth.send_lockout_alert") as mock_alert:
        mock_alert.kiq = AsyncMock()

        second = await _login(async_client, user.email, "WrongPass!1")
        assert second.status_code == status.HTTP_423_LOCKED

        mock_alert.kiq.assert_called_once()
        args = mock_alert.kiq.call_args[0]
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
    monkeypatch.setattr(settings, "auth_lockout_thresholds", "2:1")
    monkeypatch.setattr(settings, "auth_lockout_history_minutes", 5)
    caplog.set_level(logging.INFO)
    caplog.clear()

    password = "ValidPass123!"
    hashed = get_password_hash(password)
    user = await user_factory(hashed_password=hashed, is_active=True)

    await _login(async_client, user.email, "WrongPass!1")
    await _login(async_client, user.email, "WrongPass!1")

    locked = await _login(async_client, user.email, "WrongPass!1")
    assert locked.status_code == status.HTTP_423_LOCKED

    await asyncio.sleep(1.2)

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

    hashed = get_password_hash("RacePass123!")
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
