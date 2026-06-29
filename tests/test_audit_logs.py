import json
import logging
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from unittest.mock import AsyncMock, patch

import pytest

import app.models as models
from app.auth.security import get_password_hash
from app.services.auth_service import _hash_token
from app.utils.email import RESET_TOKEN_EXPIRY_MINUTES

pytestmark = pytest.mark.asyncio(loop_scope="session")


def _find_event(caplog, logger_name: str, event: str) -> dict:
    for record in reversed(caplog.records):
        if record.name != logger_name:
            continue
        try:
            payload = json.loads(record.message)
        except json.JSONDecodeError:
            continue
        if payload.get("event") == event:
            return cast(dict[Any, Any], payload)

    # Print diagnostics
    logger = logging.getLogger(logger_name)
    print(f"\n--- LOGGER DIAGNOSTICS FOR {logger_name} ---")
    print(f"Level: {logger.level}")
    print(f"Effective Level: {logger.getEffectiveLevel()}")
    print(f"Propagate: {logger.propagate}")
    print(f"Handlers: {logger.handlers}")
    print(f"Root Handlers: {logging.getLogger().handlers}")
    print(f"Root Level: {logging.getLogger().level}")
    print(f"--- CAPLOG RECORDS (looking for {logger_name} / {event}) ---")
    for r in caplog.records:
        print(f"logger={r.name} level={r.levelname} message={r.message}")
    print("-----------------------------------------------------------\n")
    raise AssertionError(f"event {event!r} not found for logger {logger_name!r}")


async def test_login_success_logs_audit(async_client, user_factory, caplog):
    caplog.set_level(logging.INFO, logger="app.auth")
    logger = logging.getLogger("app.auth")
    print(
        f"\n[TEST DEBUG AUTH] level={logger.level} effective={logger.getEffectiveLevel()} enabled={logger.isEnabledFor(logging.INFO)} disable={logging.root.manager.disable}\n"
    )
    caplog.clear()
    hashed = await get_password_hash("StrongPass123!")
    user = await user_factory(hashed_password=hashed, is_active=True)

    response = await async_client.post(
        "/auth/login",
        data={"username": user.email, "password": "StrongPass123!"},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )

    assert response.status_code == 200

    event = _find_event(caplog, "app.auth", "auth.login.success")
    assert event["user_id"] == str(user.id)
    assert event["reason"] == "authenticated"
    assert "ip" in event or "request_id" in event


async def test_login_failure_logs_audit(async_client, user_factory, caplog):
    caplog.set_level(logging.INFO, logger="app.auth")
    caplog.clear()
    hashed = await get_password_hash("ValidPass123!")
    user = await user_factory(hashed_password=hashed, is_active=True)

    response = await async_client.post(
        "/auth/login",
        data={"username": user.email, "password": "WrongPass!"},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )

    assert response.status_code == 401

    event = _find_event(caplog, "app.auth", "auth.login.failure")
    assert event.get("reason") == "invalid_credentials"
    assert "ip" in event or "request_id" in event


async def test_logout_revocation_logs_audit(async_client, user_factory, caplog):
    caplog.set_level(logging.INFO, logger="app.auth")
    caplog.clear()
    hashed = await get_password_hash("LogoutPass123!")
    user = await user_factory(hashed_password=hashed, is_active=True)

    login_response = await async_client.post(
        "/auth/login",
        data={"username": user.email, "password": "LogoutPass123!"},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert login_response.status_code == 200
    token = login_response.cookies.get("access_token_v2")

    logout_response = await async_client.post(
        "/auth/logout",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert logout_response.status_code == 200

    event = _find_event(caplog, "app.auth", "auth.logout.revoked")
    assert event["user_id"] == str(user.id)
    assert event["reason"] == "user_initiated"


async def test_password_reset_completed_audit(
    async_client, user_factory, db_session, caplog
):
    caplog.set_level(logging.INFO, logger="app.users.audit")
    logger = logging.getLogger("app.users.audit")
    print(
        f"\n[TEST DEBUG RESET Completed] level={logger.level} effective={logger.getEffectiveLevel()} enabled={logger.isEnabledFor(logging.INFO)} disable={logging.root.manager.disable}\n"
    )
    caplog.clear()
    hashed = await get_password_hash("ResetCompletePass123!")
    user = await user_factory(hashed_password=hashed, is_active=True)

    token = "reset-token-value"
    token_hash = _hash_token(token)
    expires = datetime.now(UTC) + timedelta(minutes=RESET_TOKEN_EXPIRY_MINUTES)
    db_session.add(
        models.PasswordResetToken(
            user_id=user.id,
            token_hash=token_hash,
            expires_at=expires,
            used=False,
        )
    )
    await db_session.commit()

    with patch("app.auth.security.validate_password_hibp", new_callable=AsyncMock):
        response = await async_client.post(
            "/password/reset",
            json={"token": token, "password": "BrandNewPass123!"},
        )

    assert response.status_code == 200

    event = _find_event(caplog, "app.users.audit", "password.reset.completed")
    assert event["user_id"] == str(user.id)
    assert event["reason"] == "completed"


async def test_password_reset_initiation_audit(async_client, user_factory, caplog):
    caplog.set_level(logging.INFO, logger="app.users.audit")
    caplog.clear()
    hashed = await get_password_hash("ResetInitPass123!")
    user = await user_factory(hashed_password=hashed, is_active=True)

    response = await async_client.post(
        "/password/forgot",
        json={"email": user.email},
    )

    assert response.status_code == 200

    event = _find_event(caplog, "app.users.audit", "password.reset.initiated")
    assert event["user_id"] == str(user.id)
    assert event["reason"] == "initiated"
