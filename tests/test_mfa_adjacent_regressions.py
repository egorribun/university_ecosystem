from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import app.auth.mfa.trusted_device as trusted_device_module
from app.auth.mfa.challenge import consume_challenge, issue_challenge
from app.auth.mfa.email_otp import MfaSecurityUnavailable
from app.auth.mfa.lifecycle import (
    publish_mfa_session_revocations,
    record_mfa_success,
    reset_user_mfa,
    revoke_sibling_sessions_for_factor_change,
    user_has_active_factor,
    user_has_confirmed_interactive_factor,
)
from app.auth.mfa.recovery import generate_recovery_codes, verify_recovery_code
from app.auth.mfa.trusted_device import (
    create_trusted_device_token,
    verify_and_rotate_trusted_device_token,
    verify_trusted_device_token,
)
from app.auth.schemas import EmailOtpResendIn, MfaMethodChallengeOut, MfaVerifyIn
from app.core.config import settings
from app.core.fingerprint import extract_request_fingerprint
from app.models import ActiveSession, TrustedDevice, User


def test_public_mfa_contract_does_not_accept_or_expose_binding_internals() -> None:
    assert set(EmailOtpResendIn.model_fields) == {"challenge_token"}
    assert "flow" not in MfaVerifyIn.model_fields
    assert "session_identifier" not in MfaVerifyIn.model_fields
    assert "flow" not in MfaMethodChallengeOut.model_fields
    assert "session_identifier" not in MfaMethodChallengeOut.model_fields
    assert "trust_device" not in MfaVerifyIn.model_fields


@pytest.mark.asyncio
async def test_generic_consumption_has_no_unbound_internal_bypass(
    db_session: AsyncSession, test_user: User
) -> None:
    issued = await issue_challenge(
        db_session,
        user_id=test_user.id,
        challenge_type="totp-verify",
        flow="login",
        session_identifier="required-login-session",
        client_fingerprint="f" * 64,
        method="totp",
    )
    with pytest.raises(HTTPException):
        await consume_challenge(
            db_session,
            challenge_token=issued.challenge_token,
            challenge_type="totp-verify",
            provided_code="123456",
            provided_method="totp",
        )


@pytest.mark.asyncio
async def test_totp_opaque_challenge_rejects_wrong_fingerprint_fail_closed(
    db_session: AsyncSession, test_user: User
) -> None:
    issued = await issue_challenge(
        db_session,
        user_id=test_user.id,
        challenge_type="totp-verify",
        flow="login",
        session_identifier="required-login-session",
        client_fingerprint="f" * 64,
        method="totp",
    )

    with pytest.raises(HTTPException):
        await consume_challenge(
            db_session,
            challenge_token=issued.challenge_token,
            challenge_type="totp-verify",
            provided_code="123456",
            provided_method="totp",
            client_fingerprint="a" * 64,
            login_session_identifier="required-login-session",
        )


def test_request_fingerprint_uses_trusted_client_ip_resolver(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = Mock()
    request.headers = {"X-Forwarded-For": "198.51.100.66", "user-agent": "ua"}
    request.client = Mock(host="127.0.0.1")
    monkeypatch.setattr(
        "app.core.ratelimit.resolve_client_ip", lambda _request: "203.0.113.9"
    )
    trusted = extract_request_fingerprint(request)
    request.headers["X-Forwarded-For"] = "192.0.2.123"
    assert extract_request_fingerprint(request) == trusted


@pytest.mark.asyncio
async def test_trusted_device_is_bound_to_current_mfa_epoch(
    db_session: AsyncSession, test_user: User
) -> None:
    test_user.mfa_epoch = 7
    token, _ = await create_trusted_device_token(
        db_session, user=test_user, ip_address="203.0.113.8", user_agent="test"
    )
    assert await verify_trusted_device_token(
        db_session,
        user=test_user,
        token=token,
        request_ip="203.0.113.8",
        request_ua="test",
    )
    test_user.mfa_epoch = 8
    assert not await verify_trusted_device_token(
        db_session,
        user=test_user,
        token=token,
        request_ip="203.0.113.8",
        request_ua="test",
    )


@pytest.mark.asyncio
async def test_trusted_device_rotation_invalidates_the_presented_token(
    db_session: AsyncSession, test_user: User
) -> None:
    token, _ = await create_trusted_device_token(
        db_session, user=test_user, ip_address="203.0.113.8", user_agent="test"
    )
    rotated = await verify_and_rotate_trusted_device_token(
        db_session,
        user=test_user,
        token=token,
        request_ip="203.0.113.8",
        request_ua="test",
    )
    assert rotated and rotated != token
    # ``token_urlsafe(48)`` is 64 characters without padding; this bound is
    # part of the cookie/storage contract and catches accidental entropy drift.
    assert len(rotated) == 64
    assert not await verify_trusted_device_token(
        db_session,
        user=test_user,
        token=token,
        request_ip="203.0.113.8",
        request_ua="test",
    )


@pytest.mark.asyncio
async def test_trusted_device_keyring_outage_fails_closed_as_503_boundary(
    db_session: AsyncSession, test_user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "environment", "production")
    monkeypatch.setattr(settings, "mfa_trusted_device_hmac_keys", "")
    monkeypatch.setattr(settings, "mfa_trusted_device_active_hmac_key_id", "")
    with pytest.raises(MfaSecurityUnavailable):
        await verify_and_rotate_trusted_device_token(
            db_session,
            user=test_user,
            token="presented-token",
            request_ip="203.0.113.8",
            request_ua="test",
        )


@pytest.mark.asyncio
async def test_trusted_device_missing_key_id_never_uses_a_literal_fallback_key() -> (
    None
):
    """A malformed stored key id must be rejected, even if XXXX is configured."""

    key = b"k" * 32
    user = SimpleNamespace(id=uuid.uuid4(), mfa_epoch=3)
    device = SimpleNamespace(
        id=uuid.uuid4(),
        user_id=user.id,
        token_hash="ignored-by-query-double",
        token_key_id=None,
        binding_digest=trusted_device_module._binding_digest(
            key, "203.0.113.8", "test-agent"
        ),
        mfa_epoch=3,
        expires_at=datetime.now(UTC) + timedelta(minutes=5),
    )
    locked_result = MagicMock()
    locked_result.scalar_one_or_none.return_value = user
    device_result = MagicMock()
    device_result.scalars.return_value.first.return_value = device
    db = MagicMock()
    db.execute = AsyncMock(side_effect=[locked_result, device_result])
    db.delete = AsyncMock()
    db.flush = AsyncMock()

    with (
        patch.object(
            trusted_device_module,
            "_configured_keyring",
            return_value=({"XXXX": key}, "XXXX"),
        ),
        patch.object(trusted_device_module, "_utcnow", return_value=datetime.now(UTC)),
    ):
        result = await trusted_device_module._consume_trusted_device_token(
            db,
            user=user,
            token="presented-token",
            request_ip="203.0.113.8",
            request_ua="test-agent",
            rotate=False,
        )

    assert result is None
    db.delete.assert_awaited_once_with(device)
    db.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_trusted_device_binding_mismatch_log_keeps_user_identity() -> None:
    """Binding diagnostics retain only the non-sensitive user identifier."""

    key = b"k" * 32
    user = SimpleNamespace(id=uuid.uuid4(), mfa_epoch=3)
    device = SimpleNamespace(
        id=uuid.uuid4(),
        user_id=user.id,
        token_hash="ignored-by-query-double",
        token_key_id="active",
        binding_digest=trusted_device_module._binding_digest(
            key, "203.0.113.9", "test-agent"
        ),
        mfa_epoch=3,
        expires_at=datetime.now(UTC) + timedelta(minutes=5),
    )
    locked_result = MagicMock()
    locked_result.scalar_one_or_none.return_value = user
    device_result = MagicMock()
    device_result.scalars.return_value.first.return_value = device
    db = MagicMock()
    db.execute = AsyncMock(side_effect=[locked_result, device_result])
    db.delete = AsyncMock()
    db.flush = AsyncMock()

    with (
        patch.object(
            trusted_device_module,
            "_configured_keyring",
            return_value=({"active": key}, "active"),
        ),
        patch.object(
            trusted_device_module,
            "_utcnow",
            return_value=datetime.now(UTC),
        ),
        patch.object(trusted_device_module.logger, "warning") as warning,
    ):
        result = await trusted_device_module._consume_trusted_device_token(
            db,
            user=user,
            token="presented-token",
            request_ip="203.0.113.8",
            request_ua="test-agent",
            rotate=False,
        )

    assert result is None
    warning.assert_called_once_with(
        "trusted_device_binding_mismatch user_id=%s device_id=%s",
        user.id,
        device.id,
    )
    db.delete.assert_awaited_once_with(device)
    db.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_mfa_reset_increments_epoch_and_revokes_trusted_devices(
    db_session: AsyncSession, test_user: User
) -> None:
    test_user.mfa_epoch = 3
    test_user.email_mfa_enabled_at = datetime.now(UTC)
    db_session.add(
        TrustedDevice(
            user_id=test_user.id,
            token_hash="x" * 64,
            token_key_id="test-primary",
            binding_digest="b" * 64,
            expires_at=datetime.now(UTC) + timedelta(days=1),
            mfa_epoch=3,
        )
    )
    await db_session.flush()
    await reset_user_mfa(db_session, user=test_user)
    assert test_user.mfa_epoch == 4
    assert test_user.email_mfa_enabled_at is None
    assert not test_user.trusted_devices


@pytest.mark.asyncio
async def test_mfa_reset_rollback_never_publishes_redis_revocation(
    db_session: AsyncSession, test_user: User
) -> None:
    session = ActiveSession(
        user_id=test_user.id,
        jti="reset-rollback-session",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    db_session.add(session)
    await db_session.commit()
    backend = AsyncMock()

    with patch(
        "app.services.session_cleanup.get_session_backend",
        AsyncMock(return_value=backend),
    ):
        await reset_user_mfa(db_session, user=test_user)
        await db_session.rollback()

    backend.revoke_session.assert_not_awaited()


@pytest.mark.asyncio
async def test_trusted_device_consume_locks_user_before_device(
    db_session: AsyncSession, test_user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    token, _ = await create_trusted_device_token(
        db_session,
        user=test_user,
        user_agent="test-agent",
        ip_address="203.0.113.8",
    )
    before = (
        await db_session.execute(
            select(TrustedDevice).where(TrustedDevice.user_id == test_user.id)
        )
    ).scalar_one()
    before_hash = before.token_hash
    assert before.ip_address == "203.0.113.8"
    assert before.user_agent == "test-agent"
    assert before.expires_at is not None
    assert before.last_used_at is not None
    await db_session.commit()
    original_execute = db_session.execute
    locked_entities: list[object] = []
    lock_nowait: list[bool | None] = []

    async def traced_execute(statement, *args, **kwargs):
        if getattr(statement, "_for_update_arg", None) is not None:
            descriptions = getattr(statement, "column_descriptions", [])
            if descriptions:
                locked_entities.append(descriptions[0].get("entity"))
                lock_nowait.append(statement._for_update_arg.nowait)
        return await original_execute(statement, *args, **kwargs)

    monkeypatch.setattr(db_session, "execute", traced_execute)
    assert await verify_trusted_device_token(
        db_session,
        user=test_user,
        token=token,
        request_ip="203.0.113.8",
        request_ua="test-agent",
    )

    assert locked_entities[:2] == [User, TrustedDevice]
    assert lock_nowait[:2] == [False, False]
    await db_session.refresh(before)
    assert before.token_hash == before_hash


@pytest.mark.asyncio
async def test_factor_capabilities_ignore_stale_or_different_default(
    db_session: AsyncSession, test_user: User
) -> None:
    test_user.totp_enrollments = []
    test_user.mfa_default_method = "totp"
    test_user.email_mfa_enabled_at = None
    assert not user_has_confirmed_interactive_factor(test_user)
    assert not await user_has_active_factor(db_session, test_user)

    test_user.mfa_default_method = "totp"
    test_user.email_mfa_enabled_at = datetime.now(UTC)
    assert user_has_confirmed_interactive_factor(test_user)
    assert await user_has_active_factor(db_session, test_user)


@pytest.mark.asyncio
async def test_recovery_consume_is_locked_and_regeneration_requires_fresh_mfa(
    db_session: AsyncSession, test_user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    fresh = datetime.now(UTC)
    codes = await generate_recovery_codes(
        db_session, user=test_user, fresh_mfa_verified_at=fresh
    )
    monkeypatch.setattr(
        "app.auth.mfa.recovery.verify_password", AsyncMock(return_value=True)
    )
    assert await verify_recovery_code(db_session, user=test_user, code=codes[0])
    monkeypatch.setattr(
        "app.auth.mfa.recovery.verify_password", AsyncMock(return_value=False)
    )
    assert not await verify_recovery_code(db_session, user=test_user, code=codes[0])
    with pytest.raises(PermissionError, match="fresh MFA verification required"):
        await generate_recovery_codes(
            db_session,
            user=test_user,
            fresh_mfa_verified_at=fresh - timedelta(minutes=6),
        )
    test_user.mfa_last_verified_at = fresh
    with pytest.raises(PermissionError, match="fresh MFA verification required"):
        await generate_recovery_codes(db_session, user=test_user)


@pytest.mark.asyncio
async def test_record_success_syncs_only_current_session_to_new_epoch(
    db_session: AsyncSession, test_user: User
) -> None:
    test_user.mfa_epoch = 4
    current = ActiveSession(
        user_id=test_user.id,
        jti="current-epoch-session",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
        mfa_epoch=3,
    )
    sibling = ActiveSession(
        user_id=test_user.id,
        jti="stale-epoch-session",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
        mfa_epoch=3,
    )
    db_session.add_all([current, sibling])
    await db_session.flush()

    await record_mfa_success(db_session, user=test_user, session=current, method="totp")

    assert current.mfa_epoch == 4
    assert sibling.mfa_epoch == 3


@pytest.mark.asyncio
async def test_record_success_persists_a_detached_request_session(
    db_session: AsyncSession, test_user: User
) -> None:
    test_user.mfa_epoch = 6
    current = ActiveSession(
        user_id=test_user.id,
        jti="detached-epoch-session",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
        mfa_epoch=5,
    )
    db_session.add(current)
    await db_session.flush()
    current_id = current.id
    db_session.expunge(current)

    await record_mfa_success(db_session, user=test_user, session=current, method="totp")
    persisted = await db_session.get(ActiveSession, current_id)

    assert persisted is not None
    assert persisted.mfa_epoch == 6
    assert persisted.mfa_required is False
    assert persisted.mfa_method == "totp"
    assert persisted.mfa_verified_at is not None


@pytest.mark.asyncio
async def test_factor_change_revokes_siblings_then_publishes_after_commit(
    db_session: AsyncSession, test_user: User
) -> None:
    current = ActiveSession(
        user_id=test_user.id,
        jti="factor-change-current",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    sibling = ActiveSession(
        user_id=test_user.id,
        jti="factor-change-sibling",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    db_session.add_all([current, sibling])
    await db_session.flush()

    pending = await revoke_sibling_sessions_for_factor_change(
        db_session,
        user_id=test_user.id,
        current_session_id=current.id,
    )
    assert current.revoked_at is None
    assert sibling.revoked_at is not None
    assert [item.jti for item in pending] == ["factor-change-sibling"]

    await db_session.commit()
    backend = AsyncMock()
    with patch(
        "app.auth.redis_session.get_session_backend",
        AsyncMock(return_value=backend),
    ):
        await publish_mfa_session_revocations(pending)
    backend.revoke_session.assert_awaited_once_with(
        "factor-change-sibling",
        expires_at=sibling.expires_at,
    )


def test_step_up_contract_reuses_active_session() -> None:
    from app.services.auth.login_session_manager import LoginSessionManager

    assert hasattr(LoginSessionManager, "complete_step_up")
    assert (
        "create_access_token"
        not in LoginSessionManager.complete_step_up.__code__.co_names
    )


@pytest.mark.asyncio
async def test_complete_step_up_builds_a_session_response_without_access_token() -> (
    None
):
    from app.services.auth.login_session_manager import LoginSessionManager

    manager = LoginSessionManager(Mock(), Mock(), Mock(), Mock())
    user = SimpleNamespace(id=uuid.uuid4(), mfa_epoch=7)
    session = SimpleNamespace(id=uuid.uuid4(), mfa_epoch=0)
    db_session = object()
    expected_response = object()
    manager.build_token_response = AsyncMock(  # type: ignore[method-assign]
        return_value=expected_response
    )
    record_success = AsyncMock()

    with patch("app.auth.mfa.record_mfa_success", record_success):
        result = await manager.complete_step_up(
            user=user,
            session=session,
            request=Mock(),
            db_session=db_session,
            method="totp",
        )

    assert result is expected_response
    assert session.mfa_epoch == 7
    record_success.assert_awaited_once_with(
        db_session,
        user=user,
        session=session,
        method="totp",
    )
    manager.build_token_response.assert_awaited_once_with(  # type: ignore[attr-defined]
        user,
        "",
        session,
        db_session,
        include_token=False,
    )
