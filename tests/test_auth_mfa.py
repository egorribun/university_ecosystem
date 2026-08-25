import base64
import datetime as dt
import json
import logging
from typing import Any, cast
from uuid import UUID

import pyotp
import pytest
from fastapi import status
from sqlalchemy import select

import app.models as models
from app.auth import mfa
from app.auth.mfa.email_otp import _parse_challenge_id
from app.auth.security import get_password_hash
from app.core.config import settings
from app.core.localization import translate
from app.management import reset_mfa


@pytest.fixture(autouse=True)
def _set_query_budget(async_client):
    async_client.headers["X-Query-Budget"] = "15"


@pytest.fixture(autouse=True)
def _bind_direct_challenge_issuance(monkeypatch: pytest.MonkeyPatch):
    original = mfa.issue_challenge

    async def issue_bound(*args, **kwargs):
        kwargs.setdefault("flow", "login")
        kwargs.setdefault("session_identifier", "auth-mfa-direct-session")
        kwargs.setdefault("client_fingerprint", "f" * 64)
        return await original(*args, **kwargs)

    monkeypatch.setattr(mfa, "issue_challenge", issue_bound)


def _base64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("utf-8").rstrip("=")


async def _login_for_token(async_client, email: str, password: str) -> str:
    response = await async_client.post(
        "/auth/login",
        data={"username": email, "password": password},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    if response.status_code == status.HTTP_202_ACCEPTED:
        pytest.fail("Login unexpectedly returned an MFA challenge")
    assert response.status_code == status.HTTP_200_OK, response.text
    return cast(str, response.cookies.get("access_token_v2"))


def _get_method_entry(payload: dict, method: str) -> dict:
    for entry in payload.get("methods", []):
        if entry.get("method") == method:
            return cast(dict, entry)
    raise AssertionError(f"MFA method {method!r} not found in {payload}")


async def _enroll_totp(async_client, user, password: str, db_session) -> str:
    token = await _login_for_token(async_client, user.email, password)
    headers = {"Authorization": f"Bearer {token}"}

    start_response = await async_client.post("/auth/mfa/totp/start", headers=headers)
    assert start_response.status_code == status.HTTP_200_OK, start_response.text
    data = start_response.json()
    secret = data["secret"]
    enrollment_id = data["enrollment"]["id"]

    totp = pyotp.TOTP(secret)
    confirm_response = await async_client.post(
        "/auth/mfa/totp/confirm",
        headers=headers,
        json={"enrollment_id": enrollment_id, "code": totp.now()},
    )
    assert confirm_response.status_code == status.HTTP_200_OK, confirm_response.text
    await db_session.refresh(user)
    assert user.mfa_default_method == mfa.MFA_METHOD_TOTP
    assert user.mfa_required is True
    return cast(str, secret)


@pytest.mark.asyncio
async def test_totp_enrollment_pending_state(async_client, user_factory, db_session):
    password = "PendingTotp123!"
    user = await user_factory(
        email="mfa-pending@example.com",
        hashed_password=await get_password_hash(password),
    )

    token = await _login_for_token(async_client, user.email, password)
    headers = {"Authorization": f"Bearer {token}"}

    start_response = await async_client.post("/auth/mfa/totp/start", headers=headers)
    assert start_response.status_code == status.HTTP_200_OK, start_response.text
    start_payload = start_response.json()
    assert start_payload["enrollment"]["is_active"] is False
    assert start_payload["enrollment"]["confirmed_at"] is None

    list_response = await async_client.get("/auth/mfa/totp", headers=headers)
    assert list_response.status_code == status.HTTP_200_OK
    assert list_response.json() == []

    totp = pyotp.TOTP(start_payload["secret"])
    confirm_response = await async_client.post(
        "/auth/mfa/totp/confirm",
        headers=headers,
        json={
            "enrollment_id": start_payload["enrollment"]["id"],
            "code": totp.now(),
        },
    )
    assert confirm_response.status_code == status.HTTP_200_OK, confirm_response.text

    list_after_confirm = await async_client.get("/auth/mfa/totp", headers=headers)
    assert list_after_confirm.status_code == status.HTTP_200_OK
    rows = list_after_confirm.json()
    assert len(rows) == 1
    assert rows[0]["is_active"] is True
    assert rows[0]["confirmed_at"] is not None


@pytest.mark.asyncio
async def test_totp_start_requires_reuse(async_client, user_factory):
    password = "TotpReuseRequired123!"
    user = await user_factory(
        email="mfa-totp-reuse-required@example.com",
        hashed_password=await get_password_hash(password),
    )

    token = await _login_for_token(async_client, user.email, password)
    headers = {"Authorization": f"Bearer {token}"}

    first_start = await async_client.post("/auth/mfa/totp/start", headers=headers)
    assert first_start.status_code == status.HTTP_200_OK, first_start.text

    second_start = await async_client.post("/auth/mfa/totp/start", headers=headers)
    assert second_start.status_code == status.HTTP_400_BAD_REQUEST
    assert second_start.json()["detail"] == translate(
        "errors.mfa.totp_enrollment_pending", locale="en"
    )


@pytest.mark.asyncio
async def test_totp_start_reuse_returns_same_secret(async_client, user_factory):
    password = "TotpReuseSameSecret123!"
    user = await user_factory(
        email="mfa-totp-reuse@example.com",
        hashed_password=await get_password_hash(password),
    )

    token = await _login_for_token(async_client, user.email, password)
    headers = {"Authorization": f"Bearer {token}"}

    first_start = await async_client.post("/auth/mfa/totp/start", headers=headers)
    assert first_start.status_code == status.HTTP_200_OK, first_start.text
    first_payload = first_start.json()

    reuse_response = await async_client.post(
        "/auth/mfa/totp/start",
        headers=headers,
        json={"reuse_existing": True},
    )
    assert reuse_response.status_code == status.HTTP_200_OK, reuse_response.text
    reuse_payload = reuse_response.json()

    assert reuse_payload["secret"] == first_payload["secret"]
    assert reuse_payload["enrollment"]["id"] == first_payload["enrollment"]["id"]


@pytest.mark.asyncio
async def test_pending_totp_enrollment_can_be_cancelled(
    async_client, user_factory, db_session
):
    password = "TotpCancelPending123!"
    user = await user_factory(
        email="mfa-totp-cancel-pending@example.com",
        hashed_password=await get_password_hash(password),
    )

    token = await _login_for_token(async_client, user.email, password)
    headers = {"Authorization": f"Bearer {token}"}

    start_response = await async_client.post("/auth/mfa/totp/start", headers=headers)
    assert start_response.status_code == status.HTTP_200_OK, start_response.text
    enrollment_id = start_response.json()["enrollment"]["id"]

    cancel_response = await async_client.delete(
        f"/auth/mfa/totp/pending/{enrollment_id}",
        headers=headers,
    )
    assert cancel_response.status_code == status.HTTP_204_NO_CONTENT

    await db_session.flush()
    assert await db_session.get(models.MfaTotpEnrollment, UUID(enrollment_id)) is None

    restart_response = await async_client.post("/auth/mfa/totp/start", headers=headers)
    assert restart_response.status_code == status.HTTP_200_OK, restart_response.text


@pytest.mark.asyncio
async def test_pending_totp_enrollment_cancel_rejected_for_confirmed(
    async_client, user_factory
):
    password = "TotpCancelConfirmed123!"
    user = await user_factory(
        email="mfa-totp-cancel-confirmed@example.com",
        hashed_password=await get_password_hash(password),
    )

    token = await _login_for_token(async_client, user.email, password)
    headers = {"Authorization": f"Bearer {token}"}

    start_response = await async_client.post("/auth/mfa/totp/start", headers=headers)
    assert start_response.status_code == status.HTTP_200_OK, start_response.text
    start_payload = start_response.json()
    enrollment_id = start_payload["enrollment"]["id"]

    totp = pyotp.TOTP(start_payload["secret"])
    confirm_response = await async_client.post(
        "/auth/mfa/totp/confirm",
        headers=headers,
        json={"enrollment_id": enrollment_id, "code": totp.now()},
    )
    assert confirm_response.status_code == status.HTTP_200_OK, confirm_response.text

    cancel_response = await async_client.delete(
        f"/auth/mfa/totp/pending/{enrollment_id}",
        headers=headers,
    )
    assert cancel_response.status_code == status.HTTP_400_BAD_REQUEST
    assert cancel_response.json()["detail"] == "Enrollment is not pending"


@pytest.mark.asyncio
async def test_totp_start_rejects_when_active_factor_exists(
    async_client, user_factory, db_session
):
    password = "TotpStepUpStart123!"
    user = await user_factory(
        email="mfa-stepup-start@example.com",
        hashed_password=await get_password_hash(password),
    )

    token = await _login_for_token(async_client, user.email, password)
    headers = {"Authorization": f"Bearer {token}"}

    start_response = await async_client.post("/auth/mfa/totp/start", headers=headers)
    assert start_response.status_code == status.HTTP_200_OK, start_response.text
    start_payload = start_response.json()
    totp = pyotp.TOTP(start_payload["secret"])
    confirm_response = await async_client.post(
        "/auth/mfa/totp/confirm",
        headers=headers,
        json={
            "enrollment_id": start_payload["enrollment"]["id"],
            "code": totp.now(),
        },
    )
    assert confirm_response.status_code == status.HTTP_200_OK, confirm_response.text
    await db_session.refresh(user)
    assert user.mfa_default_method == mfa.MFA_METHOD_TOTP

    # After TOTP enrollment, subsequent MFA management requests require step-up.
    # Log in again to get an MFA challenge, then verify to get a fresh token.
    mfa_login = await async_client.post(
        "/auth/login",
        data={"username": user.email, "password": password},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert mfa_login.status_code == status.HTTP_202_ACCEPTED
    mfa_challenge = _get_method_entry(mfa_login.json(), mfa.MFA_METHOD_TOTP)
    fresh_verify = await async_client.post(
        "/auth/mfa/verify",
        json={
            "method": mfa.MFA_METHOD_TOTP,
            "challenge_token": mfa_challenge["challenge_token"],
            "code": totp.now(),
        },
    )
    assert fresh_verify.status_code == status.HTTP_200_OK
    fresh_token = fresh_verify.cookies.get("access_token_v2")
    fresh_headers = {"Authorization": f"Bearer {fresh_token}"}

    second_start = await async_client.post(
        "/auth/mfa/totp/start", headers=fresh_headers
    )
    assert second_start.status_code == status.HTTP_400_BAD_REQUEST
    assert second_start.json()["detail"] == translate(
        "errors.mfa.totp_limit_reached", locale="en"
    )


def _find_audit_event(caplog, logger_name: str, event: str) -> dict:
    for record in caplog.records:
        if record.name != logger_name:
            continue
        try:
            payload = json.loads(record.message)
        except json.JSONDecodeError:
            continue
        if payload.get("event") == event:
            return cast(dict[Any, Any], payload)

    # Print diagnostics so CI failures are actionable (mirrors test_audit_logs._find_event).
    lg = logging.getLogger(logger_name)
    print(f"\n--- LOGGER DIAGNOSTICS FOR {logger_name} ---")
    print(f"Level: {lg.level}")
    print(f"Effective Level: {lg.getEffectiveLevel()}")
    print(f"Propagate: {lg.propagate}")
    print(f"Disabled: {lg.disabled}")
    print(f"Handlers: {lg.handlers}")
    print(f"Root Handlers: {logging.getLogger().handlers}")
    print(f"Root Level: {logging.getLogger().level}")
    print(f"--- CAPLOG RECORDS (looking for {logger_name!r} / {event!r}) ---")
    for r in caplog.records:
        print(f"  logger={r.name} level={r.levelname} msg={r.getMessage()!r}")
    print("-----------------------------------------------------------\n")
    raise AssertionError(f"Audit event {event!r} not found for logger {logger_name!r}")


def _setup_audit_logger(caplog, logger_name: str = "app.users.audit") -> None:
    """Defensive logger setup for caplog capture — mirrors test_audit_logs._setup_logger.

    On Python 3.13, Manager._clear_cache() can leave a stale False entry in
    a newly-created logger's _cache.  The explicit .clear() call below ensures
    the very next isEnabledFor() call recomputes the result with the level we
    just set via caplog.set_level().
    """
    caplog.set_level(logging.INFO, logger=logger_name)
    lg = logging.getLogger(logger_name)
    lg.disabled = False
    lg.propagate = True  # Guard against any xdist cross-test propagation change.
    if hasattr(lg, "_cache"):
        lg._cache.clear()
    caplog.clear()


@pytest.mark.asyncio
async def test_totp_enrollment_and_verification_flow(
    async_client, user_factory, db_session
):
    password = "TotpFlowPass123!"
    user = await user_factory(
        email="mfa-totp@example.com",
        hashed_password=await get_password_hash(password),
    )

    secret = await _enroll_totp(async_client, user, password, db_session)

    pending_response = await async_client.post(
        "/auth/login",
        data={"username": user.email, "password": password},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert pending_response.status_code == status.HTTP_202_ACCEPTED
    pending = pending_response.json()
    assert pending["status"] == "mfa_required"
    assert pending["user_id"] == str(user.id)
    assert pending["default_method"] == mfa.MFA_METHOD_TOTP

    totp_method = _get_method_entry(pending, mfa.MFA_METHOD_TOTP)
    assert "challenge_token" in totp_method
    assert "challenge_expires_at" in totp_method

    totp = pyotp.TOTP(secret)
    valid_code = totp.now()
    invalid_candidate = (int(valid_code) + 1) % 1_000_000
    invalid_code = f"{invalid_candidate:06d}"
    if invalid_code == valid_code:
        invalid_code = "123456" if valid_code != "123456" else "654321"

    failure = await async_client.post(
        "/auth/mfa/verify",
        json={
            "method": mfa.MFA_METHOD_TOTP,
            "challenge_token": totp_method["challenge_token"],
            "code": invalid_code,
        },
    )
    assert failure.status_code == status.HTTP_400_BAD_REQUEST
    assert failure.json()["detail"] == "MFA verification failed"

    success = await async_client.post(
        "/auth/mfa/verify",
        json={
            "method": mfa.MFA_METHOD_TOTP,
            "challenge_token": totp_method["challenge_token"],
            "code": totp.now(),
        },
    )
    assert success.status_code == status.HTTP_200_OK
    body = success.json()
    assert body["token_type"] == "bearer"
    assert success.cookies.get("access_token_v2")
    assert body["user"]["id"] == str(user.id)
    session = body.get("session")
    assert session is not None
    assert isinstance(session.get("signing_key"), str)
    assert session["signing_key"]

    result = await db_session.execute(
        select(models.MfaChallenge).where(
            models.MfaChallenge.id
            == _parse_challenge_id(totp_method["challenge_token"])
        )
    )
    challenge_row = result.scalars().first()
    assert challenge_row is not None
    assert challenge_row.consumed_at is not None


@pytest.mark.asyncio
async def test_totp_login_requires_mfa_even_when_toggle_disabled(
    async_client, user_factory, db_session, monkeypatch
):
    password = "TotpOptIn123!"
    user = await user_factory(
        email="mfa-toggle@example.com",
        hashed_password=await get_password_hash(password),
    )

    await _enroll_totp(async_client, user, password, db_session)

    monkeypatch.setattr(settings, "mfa_enabled", False)

    pending_response = await async_client.post(
        "/auth/login",
        data={"username": user.email, "password": password},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert pending_response.status_code == status.HTTP_202_ACCEPTED
    pending = pending_response.json()
    assert pending["status"] == "mfa_required"
    assert pending["user_id"] == str(user.id)
    assert pending["default_method"] == mfa.MFA_METHOD_TOTP


@pytest.mark.asyncio
async def test_totp_login_rejects_legacy_records_without_confirmed_at(
    async_client, user_factory, db_session
):
    password = "TotpLegacy123!"
    user = await user_factory(
        email="mfa-legacy@example.com",
        hashed_password=await get_password_hash(password),
    )

    secret = await _enroll_totp(async_client, user, password, db_session)

    result = await db_session.execute(
        select(models.MfaTotpEnrollment)
        .where(models.MfaTotpEnrollment.user_id == user.id)
        .limit(1)
    )
    enrollment = result.scalars().first()
    assert enrollment is not None
    enrollment.confirmed_at = None
    user.mfa_required = False
    await db_session.commit()

    pending_response = await async_client.post(
        "/auth/login",
        data={"username": user.email, "password": password},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert pending_response.status_code == status.HTTP_202_ACCEPTED
    pending = pending_response.json()
    totp_method = _get_method_entry(pending, mfa.MFA_METHOD_TOTP)

    totp = pyotp.TOTP(secret)
    verify = await async_client.post(
        "/auth/mfa/verify",
        json={
            "method": mfa.MFA_METHOD_TOTP,
            "challenge_token": totp_method["challenge_token"],
            "code": totp.now(),
        },
    )
    assert verify.status_code == status.HTTP_400_BAD_REQUEST
    assert verify.json()["detail"] == "MFA verification failed"


@pytest.mark.asyncio
async def test_totp_challenge_expiry_blocks_verification(
    async_client, user_factory, db_session
):
    password = "TotpExpiryPass123!"
    user = await user_factory(
        email="mfa-expiry@example.com",
        hashed_password=await get_password_hash(password),
    )

    secret = await _enroll_totp(async_client, user, password, db_session)

    pending_response = await async_client.post(
        "/auth/login",
        data={"username": user.email, "password": password},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert pending_response.status_code == status.HTTP_202_ACCEPTED
    pending = pending_response.json()
    totp_method = _get_method_entry(pending, mfa.MFA_METHOD_TOTP)

    result = await db_session.execute(
        select(models.MfaChallenge).where(
            models.MfaChallenge.id
            == _parse_challenge_id(totp_method["challenge_token"])
        )
    )
    challenge = result.scalars().one()
    challenge.expires_at = dt.datetime.now(dt.UTC) - dt.timedelta(seconds=1)
    await db_session.commit()

    verify = await async_client.post(
        "/auth/mfa/verify",
        json={
            "method": mfa.MFA_METHOD_TOTP,
            "challenge_token": totp_method["challenge_token"],
            "code": pyotp.TOTP(secret).now(),
        },
    )
    assert verify.status_code == status.HTTP_400_BAD_REQUEST
    assert verify.json()["detail"] == "MFA verification failed"


@pytest.mark.asyncio
async def test_totp_attempt_limit_blocks_challenge(
    async_client, user_factory, db_session, monkeypatch
):
    password = "TotpLockPass123!"
    user = await user_factory(
        email="mfa-totp-lock@example.com",
        hashed_password=await get_password_hash(password),
    )

    secret = await _enroll_totp(async_client, user, password, db_session)
    monkeypatch.setattr(settings, "mfa_totp_attempt_limit", 2)

    pending_response = await async_client.post(
        "/auth/login",
        data={"username": user.email, "password": password},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert pending_response.status_code == status.HTTP_202_ACCEPTED
    pending = pending_response.json()
    totp_method = _get_method_entry(pending, mfa.MFA_METHOD_TOTP)

    totp = pyotp.TOTP(secret)
    valid_code = totp.now()
    invalid_candidate = (int(valid_code) + 1) % 1_000_000
    invalid_code = f"{invalid_candidate:06d}"
    if invalid_code == valid_code:
        invalid_code = "987654"

    first_failure = await async_client.post(
        "/auth/mfa/verify",
        json={
            "method": mfa.MFA_METHOD_TOTP,
            "challenge_token": totp_method["challenge_token"],
            "code": invalid_code,
        },
    )
    assert first_failure.status_code == status.HTTP_400_BAD_REQUEST

    second_failure = await async_client.post(
        "/auth/mfa/verify",
        json={
            "method": mfa.MFA_METHOD_TOTP,
            "challenge_token": totp_method["challenge_token"],
            "code": invalid_code,
        },
    )
    assert second_failure.status_code == status.HTTP_429_TOO_MANY_REQUESTS
    assert second_failure.json()["detail"] == translate(
        "errors.auth.mfa_challenge_locked", locale="en"
    )

    result = await db_session.execute(
        select(models.MfaChallenge).where(
            models.MfaChallenge.id
            == _parse_challenge_id(totp_method["challenge_token"])
        )
    )
    challenge_row = result.scalars().first()
    assert challenge_row is not None
    assert challenge_row.attempt_count == 2
    assert challenge_row.locked_at is not None


@pytest.mark.asyncio
async def test_login_fails_when_mfa_required_but_no_totp(async_client, user_factory):
    password = "MissingTotp123!"
    user = await user_factory(
        email="missing-totp@example.com",
        hashed_password=await get_password_hash(password),
        mfa_required=True,
    )

    response = await async_client.post(
        "/auth/login",
        data={"username": user.email, "password": password},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.json()["detail"] == translate(
        "errors.auth.mfa_totp_missing", locale="en"
    )


@pytest.mark.asyncio
async def test_step_up_request_without_enrollment_returns_error(
    async_client, user_factory
):
    password = "StepUpNone123!"
    user = await user_factory(
        email="stepup-missing@example.com",
        hashed_password=await get_password_hash(password),
    )

    token = await _login_for_token(async_client, user.email, password)
    response = await async_client.post(
        "/auth/mfa/step-up",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.json()["detail"] == translate(
        "errors.auth.mfa_totp_missing", locale="en"
    )


@pytest.mark.asyncio
async def test_disabling_last_factor_clears_mfa_requirement(
    async_client, user_factory, db_session
):
    password = "LastFactorLoop123!"
    user = await user_factory(
        email="mfa-last-factor@example.com",
        hashed_password=await get_password_hash(password),
    )

    secret = await _enroll_totp(async_client, user, password, db_session)

    result = await db_session.execute(
        select(models.MfaTotpEnrollment)
        .where(models.MfaTotpEnrollment.user_id == user.id)
        .order_by(models.MfaTotpEnrollment.id.desc())
    )
    enrollment = result.scalars().first()
    assert enrollment is not None

    user.mfa_required = True
    await db_session.commit()

    pending = await async_client.post(
        "/auth/login",
        data={"username": user.email, "password": password},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert pending.status_code == status.HTTP_202_ACCEPTED
    challenge = _get_method_entry(pending.json(), mfa.MFA_METHOD_TOTP)

    totp = pyotp.TOTP(secret)
    verify = await async_client.post(
        "/auth/mfa/verify",
        json={
            "method": mfa.MFA_METHOD_TOTP,
            "challenge_token": challenge["challenge_token"],
            "code": totp.now(),
        },
    )
    assert verify.status_code == status.HTTP_200_OK
    token = verify.cookies.get("access_token_v2")
    assert token

    headers = {"Authorization": f"Bearer {token}"}
    delete_response = await async_client.delete(
        f"/auth/mfa/totp/{enrollment.id}", headers=headers
    )
    assert delete_response.status_code == status.HTTP_200_OK
    body = delete_response.json()
    assert body["disabled"] is True
    assert body["mfa_default_method"] is None
    assert body["mfa_required"] is False

    await db_session.refresh(user)
    assert user.mfa_default_method is None
    assert user.mfa_required is False

    post_delete_login = await async_client.post(
        "/auth/login",
        data={"username": user.email, "password": password},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert post_delete_login.status_code == status.HTTP_200_OK, post_delete_login.text
    assert post_delete_login.cookies.get("access_token_v2")


@pytest.mark.asyncio
async def test_admin_reset_endpoint_clears_mfa_state(
    async_client, user_factory, db_session, monkeypatch, caplog
):
    _setup_audit_logger(caplog)

    admin_password = "AdminResetPass123!"
    admin = await user_factory(
        email="admin-reset@example.com",
        hashed_password=await get_password_hash(admin_password),
        role="admin",
    )

    target = await user_factory(email="target-reset@example.com")

    enrollment, secret, _ = await mfa.start_totp_enrollment(
        db_session, user=target, label="target-reset"
    )
    await mfa.complete_totp_enrollment(
        db_session, enrollment=enrollment, code=pyotp.TOTP(secret).now()
    )
    await mfa.issue_challenge(
        db_session,
        user_id=target.id,
        challenge_type=mfa.CHALLENGE_TYPE_TOTP_VERIFY,
    )
    target.mfa_required = True
    target.mfa_default_method = mfa.MFA_METHOD_TOTP
    target.mfa_last_verified_at = dt.datetime.now(dt.UTC)
    await db_session.commit()

    notifications: list[dict] = []

    async def fake_create_notifications_for_users(db: Any, **kwargs: Any) -> int:
        notifications.append({"user_ids": list(kwargs.get("user_ids", []))})
        return len(kwargs.get("user_ids", []))

    monkeypatch.setattr(
        "app.services.notification_service.create_notifications_for_users",
        fake_create_notifications_for_users,
    )

    caplog.clear()

    token = await _login_for_token(async_client, admin.email, admin_password)
    response = await async_client.patch(
        f"/users/{target.id}",
        headers={"Authorization": f"Bearer {token}"},
        json={"reset_mfa": True},
    )
    assert response.status_code == status.HTTP_200_OK

    result = await db_session.execute(
        select(models.MfaTotpEnrollment).where(
            models.MfaTotpEnrollment.user_id == target.id
        )
    )
    assert result.scalars().all() == []

    result = await db_session.execute(
        select(models.MfaChallenge).where(models.MfaChallenge.user_id == target.id)
    )
    assert result.scalars().all() == []

    await db_session.refresh(target)
    assert target.mfa_required is False
    assert target.mfa_default_method is None
    assert target.mfa_last_verified_at is None

    assert notifications == [{"user_ids": [target.id]}]

    audit_event = _find_audit_event(caplog, "app.users.audit", "users.mfa.reset")
    assert audit_event["user_id"] == str(target.id)
    assert audit_event["reason"] == "admin_reset"


@pytest.mark.asyncio
async def test_reset_mfa_command_resets_state(
    user_factory, db_session, caplog, monkeypatch
):
    _setup_audit_logger(caplog)

    user = await user_factory(email="cli-reset@example.com")

    enrollment, secret, _ = await mfa.start_totp_enrollment(
        db_session, user=user, label="cli-reset"
    )
    await mfa.complete_totp_enrollment(
        db_session, enrollment=enrollment, code=pyotp.TOTP(secret).now()
    )
    await mfa.issue_challenge(
        db_session,
        user_id=user.id,
        challenge_type=mfa.CHALLENGE_TYPE_TOTP_VERIFY,
    )
    user.mfa_required = True
    user.mfa_default_method = mfa.MFA_METHOD_TOTP
    user.mfa_last_verified_at = dt.datetime.now(dt.UTC)
    await db_session.commit()

    notifications: list[list[int]] = []

    async def fake_create_notifications(db: Any, **kwargs: Any) -> int:
        notifications.append(list(kwargs.get("user_ids", [])))
        return len(kwargs.get("user_ids", []))

    monkeypatch.setattr(
        reset_mfa, "create_notifications_for_users", fake_create_notifications
    )

    caplog.clear()

    reset_user, stats = await reset_mfa._reset_user_mfa(
        user_id=user.id, email=None, notify=True
    )

    assert reset_user.id == user.id
    assert stats.totp_deleted == 1
    assert stats.challenges_revoked == 1
    assert stats.fields_cleared is True
    assert stats.changed is True

    result = await db_session.execute(
        select(models.MfaTotpEnrollment).where(
            models.MfaTotpEnrollment.user_id == user.id
        )
    )
    assert result.scalars().all() == []
    result = await db_session.execute(
        select(models.MfaChallenge).where(models.MfaChallenge.user_id == user.id)
    )
    assert result.scalars().all() == []

    await db_session.refresh(user)
    assert user.mfa_required is False
    assert user.mfa_default_method is None
    assert user.mfa_last_verified_at is None

    assert notifications == [[user.id]]

    audit_event = _find_audit_event(caplog, "app.users.audit", "users.mfa.reset")
    assert audit_event["user_id"] == str(user.id)
    assert audit_event["reason"] == "admin_reset"


@pytest.mark.asyncio
async def test_reset_mfa_command_noop_logs_reason(user_factory, caplog, monkeypatch):
    _setup_audit_logger(caplog)

    user = await user_factory(email="cli-noop@example.com")

    async def fake_create_notifications(db, **kwargs):
        raise AssertionError("Notifications should not be sent for noop reset")

    monkeypatch.setattr(
        reset_mfa, "create_notifications_for_users", fake_create_notifications
    )

    caplog.clear()

    _, stats = await reset_mfa._reset_user_mfa(
        user_id=user.id, email=None, notify=False
    )

    assert stats.changed is True
    assert stats.totp_deleted == 0
    assert stats.challenges_revoked == 0

    audit_event = _find_audit_event(caplog, "app.users.audit", "users.mfa.reset")
    assert audit_event["user_id"] == str(user.id)
    assert audit_event["reason"] == "admin_reset"


@pytest.mark.asyncio
async def test_mfa_verification_rejects_revoked_session(
    async_client, user_factory, db_session
):
    password = "RevokedSession123!"
    user = await user_factory(
        email="mfa-revoked@example.com",
        hashed_password=await get_password_hash(password),
    )

    enrollment = models.MfaTotpEnrollment(
        user_id=user.id,
        secret="JBSWY3DPEHPK3PXP",
        is_active=True,
        confirmed_at=dt.datetime.now(dt.UTC),
    )
    session = models.ActiveSession(
        user_id=user.id,
        jti="revoked-token",
        expires_at=dt.datetime.now(dt.UTC) + dt.timedelta(hours=1),
        revoked_at=dt.datetime.now(dt.UTC),
    )
    db_session.add_all([enrollment, session])
    await db_session.flush()

    challenge = await mfa.issue_challenge(
        db_session,
        user_id=user.id,
        session_id=session.id,
        challenge_type=mfa.CHALLENGE_TYPE_TOTP_VERIFY,
    )
    await db_session.commit()

    response = await async_client.post(
        "/auth/mfa/verify",
        json={
            "challenge_token": challenge.challenge_token,
            "method": mfa.MFA_METHOD_TOTP,
            "code": "000000",
        },
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.json()["detail"] == "MFA verification failed"


@pytest.mark.asyncio
async def test_totp_reenrollment_after_reset(async_client, user_factory, db_session):
    password = "ReenrollMfa123!"
    user = await user_factory(
        email="mfa-reenroll@example.com",
        hashed_password=await get_password_hash(password),
    )

    await _enroll_totp(async_client, user, password, db_session)
    await mfa.reset_user_mfa(db_session, user=user)
    await db_session.commit()
    await db_session.refresh(user)

    assert user.mfa_default_method is None
    assert user.mfa_required is False

    await _enroll_totp(async_client, user, password, db_session)
    await db_session.refresh(user)

    assert user.mfa_default_method == mfa.MFA_METHOD_TOTP
    assert user.mfa_required is True
