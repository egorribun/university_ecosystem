import base64
import datetime as dt
import json
import logging
from types import SimpleNamespace

import pyotp
import pytest
from fastapi import status
from sqlalchemy import select

from app.api import users as users_api
from app.auth import mfa
from app.auth.security import get_password_hash
from app.core.config import settings
from app.management import reset_mfa
from app.models import models


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
    return response.json()["access_token"]


def _get_method_entry(payload: dict, method: str) -> dict:
    for entry in payload.get("methods", []):
        if entry.get("method") == method:
            return entry
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
    return secret


def _find_audit_event(caplog, logger_name: str, event: str) -> dict:
    for record in caplog.records:
        if record.name != logger_name:
            continue
        try:
            payload = json.loads(record.message)
        except json.JSONDecodeError:  # pragma: no cover - defensive guard
            continue
        if payload.get("event") == event:
            return payload
    raise AssertionError(f"Audit event {event!r} not found for logger {logger_name!r}")


@pytest.mark.anyio
async def test_totp_enrollment_and_verification_flow(
    async_client, user_factory, db_session, monkeypatch
):
    password = "TotpFlowPass123!"
    user = await user_factory(
        email="mfa-totp@example.com",
        hashed_password=get_password_hash(password),
    )

    secret = await _enroll_totp(async_client, user, password, db_session)

    monkeypatch.setattr(settings, "mfa_enabled", True)

    pending_response = await async_client.post(
        "/auth/login",
        data={"username": user.email, "password": password},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert pending_response.status_code == status.HTTP_202_ACCEPTED
    pending = pending_response.json()
    assert pending["status"] == "mfa_required"
    assert pending["user_id"] == user.id
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
    assert failure.json()["detail"] == "Invalid verification code"

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
    assert body["access_token"]

    result = await db_session.execute(
        select(models.MfaChallenge).where(
            models.MfaChallenge.token == totp_method["challenge_token"]
        )
    )
    challenge_row = result.scalars().first()
    assert challenge_row is not None
    assert challenge_row.consumed_at is not None


@pytest.mark.anyio
async def test_totp_challenge_expiry_blocks_verification(
    async_client, user_factory, db_session, monkeypatch
):
    password = "TotpExpiryPass123!"
    user = await user_factory(
        email="mfa-expiry@example.com",
        hashed_password=get_password_hash(password),
    )

    secret = await _enroll_totp(async_client, user, password, db_session)

    monkeypatch.setattr(settings, "mfa_enabled", True)

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
            models.MfaChallenge.token == totp_method["challenge_token"]
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
    assert verify.json()["detail"] == "Invalid or expired challenge"


@pytest.mark.anyio
async def test_recovery_code_login_flow(
    async_client, user_factory, db_session, monkeypatch
):
    password = "RecoveryLoginPass123!"
    user = await user_factory(
        email="mfa-recovery@example.com",
        hashed_password=get_password_hash(password),
    )

    codes = await mfa.create_recovery_codes(db_session, user=user, count=2)
    await db_session.commit()

    monkeypatch.setattr(settings, "mfa_enabled", True)

    pending_response = await async_client.post(
        "/auth/login",
        data={"username": user.email, "password": password},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert pending_response.status_code == status.HTTP_202_ACCEPTED
    pending = pending_response.json()
    assert pending["default_method"] is None

    recovery_method = _get_method_entry(pending, mfa.MFA_METHOD_RECOVERY)

    success = await async_client.post(
        "/auth/mfa/verify",
        json={
            "method": mfa.MFA_METHOD_RECOVERY,
            "challenge_token": recovery_method["challenge_token"],
            "code": codes[0],
        },
    )
    assert success.status_code == status.HTTP_200_OK
    token = success.json()["access_token"]
    assert token

    used_hash = mfa.hash_recovery_code(codes[0])
    result = await db_session.execute(
        select(models.MfaRecoveryCode).where(
            models.MfaRecoveryCode.user_id == user.id,
            models.MfaRecoveryCode.code_hash == used_hash,
        )
    )
    used_record = result.scalars().one()
    assert used_record.used_at is not None

    # Attempt to reuse the same code should fail and an unused code should still work.
    second_pending = await async_client.post(
        "/auth/login",
        data={"username": user.email, "password": password},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert second_pending.status_code == status.HTTP_202_ACCEPTED
    second_method = _get_method_entry(second_pending.json(), mfa.MFA_METHOD_RECOVERY)

    reuse = await async_client.post(
        "/auth/mfa/verify",
        json={
            "method": mfa.MFA_METHOD_RECOVERY,
            "challenge_token": second_method["challenge_token"],
            "code": codes[0],
        },
    )
    assert reuse.status_code == status.HTTP_400_BAD_REQUEST
    assert reuse.json()["detail"] == "Invalid recovery code"

    fallback = await async_client.post(
        "/auth/mfa/verify",
        json={
            "method": mfa.MFA_METHOD_RECOVERY,
            "challenge_token": second_method["challenge_token"],
            "code": codes[1],
        },
    )
    assert fallback.status_code == status.HTTP_200_OK
    assert fallback.json()["access_token"]


@pytest.mark.anyio
async def test_webauthn_attestation_and_assertion_flow(
    async_client, user_factory, db_session, monkeypatch
):
    password = "WebAuthnPass123!"
    user = await user_factory(
        email="mfa-webauthn@example.com",
        hashed_password=get_password_hash(password),
    )

    registration_challenge = b"reg-challenge"
    assertion_challenge = b"assert-challenge"
    credential_id = b"credential-id"
    public_key = b"public-key"

    def fake_generate_registration_options(**kwargs):
        class _Options:
            challenge = registration_challenge

            def __init__(self, user_id: str):
                self._user_id = user_id.encode("utf-8")

            def model_dump(self):
                return {
                    "challenge": registration_challenge,
                    "user": {"id": self._user_id},
                    "exclude_credentials": [],
                }

        return _Options(kwargs["user_id"])

    def fake_verify_registration_response(**kwargs):
        assert kwargs["expected_challenge"] == registration_challenge
        return SimpleNamespace(
            credential_id=credential_id,
            credential_public_key=public_key,
            sign_count=1,
            transports=["internal"],
            credential_backed_up=False,
        )

    def fake_generate_authentication_options(**kwargs):
        class _Options:
            challenge = assertion_challenge

            def model_dump(self):
                return {
                    "challenge": assertion_challenge,
                    "allow_credentials": [{"id": credential_id}],
                }

        return _Options()

    def fake_verify_authentication_response(**kwargs):
        assert kwargs["expected_challenge"] == assertion_challenge
        assert kwargs["credential_public_key"] == public_key
        return SimpleNamespace(
            new_sign_count=kwargs["credential_current_sign_count"] + 1,
            credential_backed_up=True,
        )

    monkeypatch.setattr(
        mfa, "generate_registration_options", fake_generate_registration_options
    )
    monkeypatch.setattr(
        mfa, "verify_registration_response", fake_verify_registration_response
    )
    monkeypatch.setattr(
        mfa, "generate_authentication_options", fake_generate_authentication_options
    )
    monkeypatch.setattr(
        mfa, "verify_authentication_response", fake_verify_authentication_response
    )

    token = await _login_for_token(async_client, user.email, password)
    headers = {"Authorization": f"Bearer {token}"}

    start = await async_client.post(
        "/auth/mfa/webauthn/attestation/start",
        headers=headers,
    )
    assert start.status_code == status.HTTP_200_OK
    start_body = start.json()
    assert start_body["options"]["challenge"] == _base64url(registration_challenge)
    challenge_token = start_body["challenge_token"]

    encoded_raw_id = _base64url(credential_id)
    finish = await async_client.post(
        "/auth/mfa/webauthn/attestation/finish",
        headers=headers,
        json={
            "challenge_token": challenge_token,
            "credential": {
                "rawId": encoded_raw_id,
                "response": {
                    "clientDataJSON": "{}",
                    "attestationObject": "{}",
                },
                "type": "public-key",
            },
            "device_name": "pytest-key",
        },
    )
    assert finish.status_code == status.HTTP_200_OK
    credential_body = finish.json()
    assert credential_body["credential_id"] == encoded_raw_id

    await db_session.refresh(user)
    assert user.mfa_default_method == mfa.MFA_METHOD_WEBAUTHN

    monkeypatch.setattr(settings, "mfa_enabled", True)

    pending = await async_client.post(
        "/auth/login",
        data={"username": user.email, "password": password},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert pending.status_code == status.HTTP_202_ACCEPTED
    payload = pending.json()
    assert payload["default_method"] == mfa.MFA_METHOD_WEBAUTHN
    webauthn_method = _get_method_entry(payload, mfa.MFA_METHOD_WEBAUTHN)
    assert webauthn_method["options"]["challenge"] == _base64url(assertion_challenge)

    verify = await async_client.post(
        "/auth/mfa/verify",
        json={
            "method": mfa.MFA_METHOD_WEBAUTHN,
            "challenge_token": webauthn_method["challenge_token"],
            "credential": {
                "rawId": encoded_raw_id,
                "response": {
                    "clientDataJSON": "{}",
                    "authenticatorData": "",
                    "signature": "",
                },
                "type": "public-key",
            },
        },
    )
    assert verify.status_code == status.HTTP_200_OK
    assert verify.json()["access_token"]

    result = await db_session.execute(
        select(models.MfaWebAuthnCredential).where(
            models.MfaWebAuthnCredential.user_id == user.id
        )
    )
    credential = result.scalars().one()
    assert credential.sign_count == 2
    assert credential.last_used_at is not None
    assert credential.clone_warning is False


@pytest.mark.anyio
async def test_admin_reset_endpoint_clears_mfa_state(
    async_client, user_factory, db_session, monkeypatch, caplog
):
    caplog.set_level(logging.INFO, logger="app.users.audit")

    admin_password = "AdminResetPass123!"
    admin = await user_factory(
        email="admin-reset@example.com",
        hashed_password=get_password_hash(admin_password),
        role="admin",
    )

    target = await user_factory(email="target-reset@example.com")

    enrollment, secret, _ = await mfa.start_totp_enrollment(
        db_session, user=target, label="target-reset"
    )
    await mfa.complete_totp_enrollment(
        db_session, enrollment=enrollment, code=pyotp.TOTP(secret).now()
    )
    credential = models.MfaWebAuthnCredential(
        user_id=target.id,
        credential_id="credential-reset",
        public_key="public-key",
        sign_count=0,
        is_active=True,
    )
    db_session.add(credential)
    await mfa.create_recovery_codes(db_session, user=target, count=2)
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

    async def fake_create_notifications_for_users(db, **kwargs):
        notifications.append({"user_ids": list(kwargs.get("user_ids", []))})
        return len(kwargs.get("user_ids", []))

    monkeypatch.setattr(
        users_api,
        "create_notifications_for_users",
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
        select(models.MfaWebAuthnCredential).where(
            models.MfaWebAuthnCredential.user_id == target.id
        )
    )
    assert result.scalars().all() == []

    result = await db_session.execute(
        select(models.MfaRecoveryCode).where(
            models.MfaRecoveryCode.user_id == target.id
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
    assert target.mfa_recovery_codes_generated_at is None

    assert notifications == [{"user_ids": [target.id]}]

    audit_event = _find_audit_event(caplog, "app.users.audit", "users.mfa.reset")
    assert audit_event["user_id"] == str(target.id)
    assert audit_event["reason"] == "admin_reset"


@pytest.mark.anyio
async def test_reset_mfa_command_resets_state(
    user_factory, db_session, caplog, monkeypatch
):
    caplog.set_level(logging.INFO, logger="app.users.audit")

    user = await user_factory(email="cli-reset@example.com")

    enrollment, secret, _ = await mfa.start_totp_enrollment(
        db_session, user=user, label="cli-reset"
    )
    await mfa.complete_totp_enrollment(
        db_session, enrollment=enrollment, code=pyotp.TOTP(secret).now()
    )
    db_session.add(
        models.MfaWebAuthnCredential(
            user_id=user.id,
            credential_id="cli-credential",
            public_key="cli-public",
            sign_count=5,
            is_active=True,
        )
    )
    await mfa.create_recovery_codes(db_session, user=user, count=1)
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

    async def fake_create_notifications(db, **kwargs):
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
    assert stats.webauthn_deleted == 1
    assert stats.recovery_codes_deleted == 1
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
        select(models.MfaWebAuthnCredential).where(
            models.MfaWebAuthnCredential.user_id == user.id
        )
    )
    assert result.scalars().all() == []
    result = await db_session.execute(
        select(models.MfaRecoveryCode).where(models.MfaRecoveryCode.user_id == user.id)
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
    assert user.mfa_recovery_codes_generated_at is None

    assert notifications == [[user.id]]

    audit_event = _find_audit_event(caplog, "app.users.audit", "users.mfa.reset")
    assert audit_event["user_id"] == str(user.id)
    assert audit_event["reason"] == "admin_reset"


@pytest.mark.anyio
async def test_reset_mfa_command_noop_logs_reason(user_factory, caplog, monkeypatch):
    caplog.set_level(logging.INFO, logger="app.users.audit")

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

    assert stats.changed is False
    assert stats.totp_deleted == 0
    assert stats.webauthn_deleted == 0
    assert stats.recovery_codes_deleted == 0
    assert stats.challenges_revoked == 0

    audit_event = _find_audit_event(caplog, "app.users.audit", "users.mfa.reset")
    assert audit_event["user_id"] == str(user.id)
    assert audit_event["reason"] == "admin_reset_noop"
