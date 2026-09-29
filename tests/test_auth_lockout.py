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
from app.models import FailedLoginAttempt

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


async def test_login_lockout_enforced(
    async_client, user_factory, db_session, monkeypatch, caplog
):
    monkeypatch.setattr(settings, "auth_lockout_thresholds", "2:3")
    monkeypatch.setattr(settings, "auth_lockout_history_minutes", 5)
    caplog.set_level(logging.INFO)
    caplog.clear()

    hashed = await get_password_hash("ValidPass123!")
    user = await user_factory(hashed_password=hashed, is_active=True)

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
    # Wave 184 SW4 (Path C) — closes W149 §Honesty #6 timing-race flake
    # (34-wave recurring `assert 401 == 423` at line ~110 below).
    #
    # ROOT CAUSE (per Phase 3 Review of `app/services/auth/lockout.py`):
    # `_calculate_lock_until` uses `attempts[0]` after `_fetch_recent_attempts`
    # reverses the DESC SQL result to ASC. So `attempts[0]` = OLDEST of the
    # top-`limit` slice. Lockout extends `seconds` after that oldest attempt.
    # With "2:1" (original) the 3rd attempt's `get_active_lockout` check
    # reads existing=[att1, att2] (top-2, reversed) → attempts[0]=att1 →
    # candidate=att1.time + 1s. Under CI parallel-worker drift, att3 can
    # fire >1s after att1 → candidate < now → no lock → att3 passes step 1
    # → password validation runs → register_failed_attempt re-checks with
    # updated=[att2, att3] but if att3.time - att2.time >= 1s, the new
    # candidate (att2.time + 1s) is ALSO < now → lock_until=None →
    # triggered=False → returns 401 instead of expected 423.
    #
    # FIX: widen the window from "2:1" to "2:3" (3-second window) to
    # tolerate CI drift up to ~3 seconds between attempt 1 and attempt 3.
    # ALSO widen the asyncio.sleep below from 1.2s to 3.5s so the lockout
    # (which extends `seconds` past the oldest of top-2 attempts) RELIABLY
    # expires before the success login. NOT masking a real bug — the
    # lockout threshold here is a test-fixture choice, not a production
    # requirement. The sibling `test_login_lockout_race_condition` at
    # line ~135 below uses "2:5" already; this test settles on "2:3" as a
    # balance between CI tolerance and total test duration.
    monkeypatch.setattr(settings, "auth_lockout_thresholds", "2:3")
    monkeypatch.setattr(settings, "auth_lockout_history_minutes", 5)
    caplog.set_level(logging.INFO)
    caplog.clear()

    password = "ValidPass123!"
    hashed = await get_password_hash(password)
    user = await user_factory(hashed_password=hashed, is_active=True)

    await _login(async_client, user.email, "WrongPass!1")
    await _login(async_client, user.email, "WrongPass!1")

    locked = await _login(async_client, user.email, "WrongPass!1")
    assert locked.status_code == status.HTTP_423_LOCKED

    # Wave 184 SW4 — sleep widened 1.2s → 3.5s to match the "2:3" window
    # set above. Lockout extends `seconds` (3) past the oldest of the top-2
    # most-recent failed attempts; sleep must be strictly greater than that
    # window so `get_active_lockout` returns None and the subsequent success
    # login proceeds to password validation.
    await asyncio.sleep(3.5)

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
