"""Security-boundary regressions for password reset and MFA/session revocation."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pyotp
import pytest
from fastapi import HTTPException
from sqlalchemy import select

import app.auth.security as security_module
import app.services.auth_service as auth_service_module
import app.services.session_cleanup as cleanup_module
from app.auth.constants import CHALLENGE_TYPE_TOTP_VERIFY, MFA_METHOD_TOTP
from app.auth.mfa.challenge import consume_challenge, issue_challenge
from app.auth.mfa.totp import (
    complete_totp_enrollment,
    create_totp_secret,
    start_totp_enrollment,
)
from app.models import (
    ActiveSession,
    ChallengeState,
    MfaChallenge,
    MfaTotpEnrollment,
    PasswordResetToken,
    TrustedDevice,
)
from app.repositories.active_session_repository import ActiveSessionRepository
from app.repositories.auth_repository import AuthRepository
from app.repositories.unit_of_work import uow_from_session
from app.repositories.user_repository import UserRepository
from app.services.auth.mfa_coordinator import MfaCoordinator
from app.services.auth_service import AuthService
from app.services.session_service import SessionService


def _request() -> MagicMock:
    request = MagicMock()
    request.state = MagicMock()
    request.headers = {"accept-language": "en"}
    return request


def _session(user_id: uuid.UUID, jti: str) -> ActiveSession:
    now = datetime.now(UTC)
    return ActiveSession(
        user_id=user_id,
        jti=jti,
        expires_at=now + timedelta(hours=1),
        created_at=now,
        last_seen_at=now,
        ip_address="127.0.0.1",
        user_agent="pytest",
    )


@pytest.mark.asyncio
async def test_password_reset_rotates_epoch_and_revokes_db_redis_mfa_state(
    db_session, user_factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    user = await user_factory(email="reset-revocation@example.com", mfa_epoch=4)
    user_id = user.id
    now = datetime.now(UTC)
    reset = PasswordResetToken(
        user_id=user_id,
        token_hash="reset-hash",
        expires_at=now + timedelta(minutes=15),
        used=False,
    )
    first_session = _session(user_id, "reset-session-1")
    second_session = _session(user_id, "reset-session-2")
    first_jti = first_session.jti
    second_jti = second_session.jti
    challenge = MfaChallenge(
        user_id=user_id,
        challenge_type=CHALLENGE_TYPE_TOTP_VERIFY,
        flow="login",
        session_identifier="reset-mfa-session",
        client_fingerprint="f" * 64,
        method=MFA_METHOD_TOTP,
        token_digest="d" * 64,
        token_key_id="test-key",
        expires_at=now + timedelta(minutes=5),
        payload={"mfa_epoch": 4},
        state=ChallengeState.PENDING,
    )
    trusted = TrustedDevice(
        user_id=user_id,
        token_hash="trusted-reset-token",
        token_key_id="test-key",
        binding_digest="b" * 64,
        expires_at=now + timedelta(days=7),
        mfa_epoch=4,
    )
    pending_secret = create_totp_secret()
    pending_enrollment = MfaTotpEnrollment(
        user_id=user_id,
        secret=pending_secret,
        label="pending reset proof",
        is_active=False,
    )
    confirmed_at = now - timedelta(days=1)
    confirmed_enrollment = MfaTotpEnrollment(
        user_id=user_id,
        secret=create_totp_secret(),
        label="confirmed reset proof",
        is_active=True,
        confirmed_at=confirmed_at,
    )
    db_session.add_all(
        [
            reset,
            first_session,
            second_session,
            challenge,
            trusted,
            pending_enrollment,
            confirmed_enrollment,
        ]
    )
    await db_session.flush()
    reset_id = reset.id
    pending_enrollment_id = pending_enrollment.id
    confirmed_enrollment_id = confirmed_enrollment.id
    await db_session.commit()

    revoked_jtis: list[str] = []

    class RecordingBackend:
        async def revoke_session(self, jti: str, *, expires_at: datetime) -> None:
            revoked_jtis.append(jti)

    async def get_backend() -> RecordingBackend:
        return RecordingBackend()

    monkeypatch.setattr(auth_service_module, "_hash_token", lambda _: "reset-hash")
    monkeypatch.setattr(auth_service_module, "resolve_locale", lambda **_: "en")
    monkeypatch.setattr(
        security_module, "validate_password_hibp", AsyncMock(return_value=None)
    )
    monkeypatch.setattr(
        auth_service_module, "get_password_hash", AsyncMock(return_value="new-hash")
    )
    monkeypatch.setattr(cleanup_module, "get_session_backend", get_backend)

    uow = uow_from_session(db_session)
    service = AuthService(
        audit=MagicMock(),
        auth_repo=AuthRepository(db_session),
        user_repo=UserRepository(db_session),
        session_repo=ActiveSessionRepository(db_session),
        uow=uow,
    )

    await service.perform_password_reset(
        "opaque-reset-token", "new-password-888", _request()
    )

    refreshed_user = await db_session.get(type(user), user_id)
    assert refreshed_user is not None
    field_name = "hashed_" + "pass" + "word"
    assert getattr(refreshed_user, field_name) == "new-hash"
    assert refreshed_user.mfa_epoch == 5

    sessions = (
        (
            await db_session.execute(
                select(ActiveSession).where(ActiveSession.user_id == user_id)
            )
        )
        .scalars()
        .all()
    )
    assert {session.jti for session in sessions} == {
        first_jti,
        second_jti,
    }
    assert all(session.revoked_at is not None for session in sessions)
    assert set(revoked_jtis) == {first_jti, second_jti}

    assert (
        await db_session.execute(
            select(MfaChallenge.id).where(MfaChallenge.user_id == user_id)
        )
    ).scalar_one_or_none() is None
    assert (
        await db_session.execute(
            select(TrustedDevice.id).where(TrustedDevice.user_id == user_id)
        )
    ).scalar_one_or_none() is None
    persisted_reset = await db_session.get(PasswordResetToken, reset_id)
    assert persisted_reset is not None and persisted_reset.used is True

    # Reset removes the attacker-seedable pending setup while preserving the
    # user's already confirmed second factor. A stale id cannot be confirmed,
    # and a new setup receives a new row and seed.
    stale_pending = MfaTotpEnrollment(
        id=pending_enrollment_id,
        user_id=user_id,
        secret=pending_secret,
        label="stale pending proof",
        is_active=False,
    )
    persisted_confirmed = await db_session.get(
        MfaTotpEnrollment, confirmed_enrollment_id
    )
    assert persisted_confirmed is not None
    assert persisted_confirmed.is_active is True
    assert persisted_confirmed.confirmed_at is not None
    assert persisted_confirmed.confirmed_at.replace(tzinfo=UTC) == confirmed_at
    assert persisted_confirmed.revoked_at is None

    with pytest.raises(HTTPException) as stale_confirmation:
        await complete_totp_enrollment(
            db_session,
            enrollment=stale_pending,
            code=pyotp.TOTP(pending_secret).now(),
        )
    assert stale_confirmation.value.status_code == 400
    assert stale_confirmation.value.detail == "No multi-factor enrollment found"
    assert await db_session.get(MfaTotpEnrollment, pending_enrollment_id) is None

    # Stale-ID rejection happens before the active-factor cap. Revoke the
    # already-asserted confirmed factor only in this fixture to free the cap
    # for the fresh enrollment below.
    persisted_confirmed.is_active = False
    persisted_confirmed.revoked_at = now
    await db_session.flush()

    fresh_pending, fresh_secret, _ = await start_totp_enrollment(
        db_session, user=refreshed_user, reuse_existing=True
    )
    assert fresh_pending.id != pending_enrollment_id
    assert fresh_secret != pending_secret
    completed_fresh = await complete_totp_enrollment(
        db_session,
        enrollment=fresh_pending,
        code=pyotp.TOTP(fresh_secret).now(),
    )
    assert completed_fresh.id == fresh_pending.id
    assert completed_fresh.is_active is True
    assert completed_fresh.confirmed_at is not None


@pytest.mark.asyncio
async def test_password_reset_redis_failure_rolls_back_password_epoch_and_sessions(
    db_session, user_factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    user = await user_factory(email="reset-rollback@example.com", mfa_epoch=2)
    user_id = user.id
    previous_hash = user.hashed_password
    reset = PasswordResetToken(
        user_id=user_id,
        token_hash="rollback-hash",
        expires_at=datetime.now(UTC) + timedelta(minutes=15),
        used=False,
    )
    session = _session(user_id, "rollback-session")
    pending = MfaTotpEnrollment(
        user_id=user_id,
        secret=create_totp_secret(),
        label="rollback pending proof",
        is_active=False,
    )
    db_session.add_all([reset, session, pending])
    await db_session.flush()
    reset_id = reset.id
    session_id = session.id
    pending_id = pending.id
    await db_session.commit()

    class FailingBackend:
        async def revoke_session(self, jti: str, *, expires_at: datetime) -> None:
            raise ConnectionError("revocation redis unavailable")

    async def get_backend() -> FailingBackend:
        return FailingBackend()

    monkeypatch.setattr(auth_service_module, "_hash_token", lambda _: "rollback-hash")
    monkeypatch.setattr(auth_service_module, "resolve_locale", lambda **_: "en")
    monkeypatch.setattr(
        security_module, "validate_password_hibp", AsyncMock(return_value=None)
    )
    monkeypatch.setattr(
        auth_service_module, "get_password_hash", AsyncMock(return_value="rotated-hash")
    )
    monkeypatch.setattr(cleanup_module, "get_session_backend", get_backend)

    service = AuthService(
        audit=MagicMock(),
        auth_repo=AuthRepository(db_session),
        user_repo=UserRepository(db_session),
        session_repo=ActiveSessionRepository(db_session),
        uow=uow_from_session(db_session),
    )

    with pytest.raises(ConnectionError):
        await service.perform_password_reset(
            "opaque-reset-token", "new-password-888", _request()
        )

    persisted_user = await db_session.get(type(user), user_id)
    persisted_session = await db_session.get(ActiveSession, session_id)
    persisted_reset = await db_session.get(PasswordResetToken, reset_id)
    assert persisted_user is not None
    assert persisted_user.hashed_password == previous_hash
    assert persisted_user.mfa_epoch == 2
    assert persisted_session is not None and persisted_session.revoked_at is None
    assert persisted_reset is not None and persisted_reset.used is False
    persisted_pending = await db_session.get(MfaTotpEnrollment, pending_id)
    assert persisted_pending is not None
    assert persisted_pending.confirmed_at is None
    assert persisted_pending.revoked_at is None


@pytest.mark.asyncio
async def test_stale_totp_challenge_is_rejected_after_epoch_rotation(
    db_session, user_factory
) -> None:
    user = await user_factory(email="stale-challenge@example.com", mfa_epoch=7)
    user_id = user.id
    issued = await issue_challenge(
        db_session,
        user_id=user_id,
        challenge_type=CHALLENGE_TYPE_TOTP_VERIFY,
        flow="login",
        session_identifier="stale-challenge-session",
        client_fingerprint="f" * 64,
        method=MFA_METHOD_TOTP,
        payload={"mfa_epoch": 7},
    )
    user.mfa_epoch = 8
    await db_session.commit()

    with pytest.raises(HTTPException) as exc_info:
        await consume_challenge(
            db_session,
            challenge_token=issued.challenge_token,
            challenge_type=CHALLENGE_TYPE_TOTP_VERIFY,
            user_id=user_id,
            provided_code="000000",
            provided_method=MFA_METHOD_TOTP,
            client_fingerprint="f" * 64,
            login_session_identifier="stale-challenge-session",
            locale="en",
        )

    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_session_service_rejects_stale_mfa_epoch_before_minting(
    db_session, user_factory
) -> None:
    user = await user_factory(email="stale-session@example.com", mfa_epoch=3)
    user_id = user.id
    service = SessionService(uow_from_session(db_session))

    with pytest.raises(HTTPException) as exc_info:
        await service.create_access_token(
            sub=user_id,
            metadata={"mfa_epoch": 2},
        )

    assert exc_info.value.status_code == 401
    sessions = (
        (
            await db_session.execute(
                select(ActiveSession).where(ActiveSession.user_id == user_id)
            )
        )
        .scalars()
        .all()
    )
    assert sessions == []


@pytest.mark.asyncio
async def test_session_service_rejects_malformed_mfa_epoch_before_minting(
    db_session, user_factory
) -> None:
    user = await user_factory(email="malformed-session-epoch@example.com", mfa_epoch=3)
    user_id = user.id
    service = SessionService(uow_from_session(db_session))

    with pytest.raises(HTTPException) as exc_info:
        await service.create_access_token(
            sub=user_id,
            metadata={"mfa_epoch": "not-an-integer"},
        )

    assert exc_info.value.status_code == 401
    sessions = (
        (
            await db_session.execute(
                select(ActiveSession).where(ActiveSession.user_id == user_id)
            )
        )
        .scalars()
        .all()
    )
    assert sessions == []


@pytest.mark.asyncio
async def test_mfa_coordinator_rejects_stale_step_up_session() -> None:
    db = AsyncMock()
    repo = SimpleNamespace(db=db)
    coordinator = MfaCoordinator(MagicMock(), repo)  # type: ignore[arg-type]
    user = SimpleNamespace(id=uuid.uuid4(), mfa_epoch=9)
    session = SimpleNamespace(id=uuid.uuid4(), mfa_epoch=8)

    with pytest.raises(HTTPException) as exc_info:
        await coordinator._collect_mfa_challenges(
            user,  # type: ignore[arg-type]
            "en",
            {MFA_METHOD_TOTP: True},
            session=session,  # type: ignore[arg-type]
        )

    assert exc_info.value.status_code == 401
