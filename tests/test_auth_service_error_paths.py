"""Error-path and lifecycle tests for app/services/auth_service.py.

AsyncMock repo + MagicMock-UoW harness (mirrors tests/test_auth_service_coverage.py
style) targeting the previously-uncovered branches:

- perform_password_reset: token-invalid audit path (L160-166), naive expires_at
  normalization (L172), HIBP ValueError wrap (L204-205)
- initiate_email_change: wrong password (L233), invalid email (L239-240),
  same-email guard (L243), missing db user + full success path (L252-296)
- confirm_email_change: invalid record (L313), naive expires_at (L320),
  missing user after update (L346-347), full success path (L354-374)
- change_password: wrong current password (L387), same password (L389),
  HIBP ValueError wrap (L396-397), no-active-session revoke-all branch (L411)
- refresh_pending_email with a user (L441-443)
- _hash_token production guard (L457)
- attach_pending_email: None user (L478), DetachedInstanceError fallback +
  DB-query path (L485-488, L501-505), unexpected inspect error re-raise
  (L489-496), attach_pending_email_sync non-pydantic assignment (L517)
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException, Request
from sqlalchemy.orm import exc as orm_exc

import app.auth.security as security_module
import app.core.csrf as csrf_module
import app.models as models
import app.services.auth_service as auth_module
from app.core.exceptions.domain import EntityNotFound
from app.schemas import schemas
from app.services.auth_service import (
    AuthService,
    _hash_token,
    attach_pending_email,
    attach_pending_email_sync,
)


@pytest.fixture
def auth_service():
    audit = MagicMock()
    auth_repo = MagicMock()
    user_repo = MagicMock()
    session_repo = MagicMock()
    uow = MagicMock()
    uow.__aenter__.return_value = uow
    uow.__aexit__.return_value = None
    uow.commit = AsyncMock()
    uow.session = MagicMock()
    uow.session.refresh = AsyncMock()

    return AuthService(
        audit=audit,
        auth_repo=auth_repo,
        user_repo=user_repo,
        session_repo=session_repo,
        uow=uow,
    )


@pytest.fixture
def request_mock():
    req = MagicMock(spec=Request)
    req.state = MagicMock()
    req.headers = {"accept-language": "en"}
    return req


def _spec_user(email: str = "old@example.com") -> MagicMock:
    user = MagicMock(spec=models.User)
    user.id = uuid.uuid4()
    user.email = email
    user.hashed_password = "argon2-hash"  # pragma: allowlist secret
    return user


# ---------------------------------------------------------------------------
# perform_password_reset — token-invalid / naive-expiry / HIBP error (L160-205)
# ---------------------------------------------------------------------------


async def test_perform_password_reset_token_invalid(auth_service, request_mock):
    """Missing token record logs token_invalid and raises 400 (L160-166)."""
    auth_service.auth_repo.get_valid_password_reset_token = AsyncMock(return_value=None)

    with pytest.raises(HTTPException) as exc:
        await auth_service.perform_password_reset(
            "missing-token", "new-password-888", request_mock
        )

    assert exc.value.status_code == 400
    auth_service.audit.log.assert_called_with(
        "password.reset.failed",
        request_mock,
        level=logging.WARNING,
        reason="token_invalid",
    )


async def test_perform_password_reset_naive_expired_token(auth_service, request_mock):
    """Naive expires_at gets UTC attached (L172) before the expiry comparison."""
    rec = MagicMock()
    rec.user_id = uuid.uuid4()
    rec.expires_at = datetime.now(UTC).replace(tzinfo=None) - timedelta(minutes=5)
    auth_service.auth_repo.get_valid_password_reset_token = AsyncMock(return_value=rec)

    with pytest.raises(HTTPException) as exc:
        await auth_service.perform_password_reset(
            "naive-token", "new-password-888", request_mock
        )

    assert exc.value.status_code == 400
    auth_service.audit.log.assert_called_with(
        "password.reset.failed",
        request_mock,
        level=logging.WARNING,
        user_id=rec.user_id,
        reason="token_expired",
    )


async def test_perform_password_reset_hibp_rejection(
    auth_service, request_mock, monkeypatch
):
    """ValueError from the HIBP check maps to a 400 bad_request (L204-205)."""
    rec = MagicMock()
    rec.id = 7
    rec.user_id = uuid.uuid4()
    rec.expires_at = datetime.now(UTC) + timedelta(minutes=30)
    auth_service.auth_repo.get_valid_password_reset_token = AsyncMock(return_value=rec)

    user = MagicMock()
    user.is_active = True
    auth_service.user_repo.get = AsyncMock(return_value=user)
    auth_service.user_repo.update = AsyncMock()

    monkeypatch.setattr(
        security_module,
        "validate_password_hibp",
        AsyncMock(side_effect=ValueError("breached password")),
    )

    with pytest.raises(HTTPException) as exc:
        await auth_service.perform_password_reset(
            "valid-token", "new-password-888", request_mock
        )

    assert exc.value.status_code == 400
    auth_service.user_repo.update.assert_not_called()


# ---------------------------------------------------------------------------
# initiate_email_change — guard clauses + success path (L233-296)
# ---------------------------------------------------------------------------


async def test_initiate_email_change_wrong_password(
    auth_service, request_mock, monkeypatch
):
    """Wrong current password raises invalid_password (L233)."""
    user = _spec_user()
    payload = schemas.UserEmailChangeIn(
        email="new@example.com",
        password="wrong-password",  # pragma: allowlist secret
    )
    monkeypatch.setattr(
        security_module, "verify_password", AsyncMock(return_value=False)
    )

    with pytest.raises(HTTPException) as exc:
        await auth_service.initiate_email_change(
            user, payload, request_mock, MagicMock()
        )

    assert exc.value.status_code == 400


async def test_initiate_email_change_invalid_email(
    auth_service, request_mock, monkeypatch
):
    """Email that fails EmailStr re-validation raises invalid_email (L239-240)."""
    user = _spec_user()
    # model_construct bypasses schema validation so the service-level
    # TypeAdapter(EmailStr) re-validation branch executes.
    payload = schemas.UserEmailChangeIn.model_construct(
        email="not an email",
        password="pw",  # pragma: allowlist secret
    )
    monkeypatch.setattr(
        security_module, "verify_password", AsyncMock(return_value=True)
    )

    with pytest.raises(HTTPException) as exc:
        await auth_service.initiate_email_change(
            user, payload, request_mock, MagicMock()
        )

    assert exc.value.status_code == 400


async def test_initiate_email_change_same_email(
    auth_service, request_mock, monkeypatch
):
    """Requesting a change to the current email raises email_same (L243)."""
    user = _spec_user(email="same@example.com")
    payload = schemas.UserEmailChangeIn(
        email="same@example.com",
        password="correct-password",  # pragma: allowlist secret
    )
    monkeypatch.setattr(
        security_module, "verify_password", AsyncMock(return_value=True)
    )

    with pytest.raises(HTTPException) as exc:
        await auth_service.initiate_email_change(
            user, payload, request_mock, MagicMock()
        )

    assert exc.value.status_code == 400


async def test_initiate_email_change_missing_db_user(
    auth_service, request_mock, monkeypatch
):
    """Refetch returning no user raises EntityNotFound (L252-253)."""
    user = _spec_user()
    payload = schemas.UserEmailChangeIn(
        email="new@example.com",
        password="correct-password",  # pragma: allowlist secret
    )
    monkeypatch.setattr(
        security_module, "verify_password", AsyncMock(return_value=True)
    )
    auth_service.user_repo.check_email_exists = AsyncMock(return_value=False)
    auth_service.user_repo.get = AsyncMock(return_value=None)

    with pytest.raises(EntityNotFound):
        await auth_service.initiate_email_change(
            user, payload, request_mock, MagicMock()
        )


async def test_initiate_email_change_success(auth_service, request_mock, monkeypatch):
    """Full happy path: token creation, commit+refresh, email send, audit
    (L255-296)."""
    user = _spec_user()
    user.profile.full_name = "Test User"
    payload = schemas.UserEmailChangeIn(
        email="New.Address@Example.com",
        password="correct-password",  # pragma: allowlist secret
    )

    db_user = MagicMock(spec=models.User)
    db_user.id = user.id

    loaded_user = MagicMock()
    enriched_user = MagicMock()

    monkeypatch.setattr(
        security_module, "verify_password", AsyncMock(return_value=True)
    )
    monkeypatch.setattr(
        auth_module,
        "ensure_mfa_relationships_loaded",
        AsyncMock(return_value=loaded_user),
    )
    attach_mock = AsyncMock(return_value=enriched_user)
    monkeypatch.setattr(auth_module, "attach_pending_email", attach_mock)
    kick_mock = AsyncMock()
    monkeypatch.setattr(auth_module.send_auth_email, "kick", kick_mock)

    auth_service.user_repo.check_email_exists = AsyncMock(return_value=False)
    auth_service.user_repo.get = AsyncMock(return_value=db_user)
    auth_service.auth_repo.create_email_change_token = AsyncMock()

    result = await auth_service.initiate_email_change(
        user, payload, request_mock, MagicMock()
    )

    assert result is enriched_user
    auth_service.auth_repo.create_email_change_token.assert_awaited_once()
    create_kwargs = auth_service.auth_repo.create_email_change_token.await_args.kwargs
    assert create_kwargs["new_email"] == "new.address@example.com"
    # db_user is spec'd (no model_dump) so the ORM refresh branch executes (L269)
    auth_service.uow.session.refresh.assert_awaited_once_with(db_user)
    # enriched_user is not the original user → second attach call fires (L274-275)
    assert attach_mock.await_count == 2
    kick_mock.assert_awaited_once()
    assert kick_mock.await_args.args[0] == "new.address@example.com"
    auth_service.audit.log.assert_called_with(
        "users.email.change_requested",
        request_mock,
        user_id=user.id,
        reason="pending_confirmation",
    )


# ---------------------------------------------------------------------------
# confirm_email_change — guards + success path (L313-374)
# ---------------------------------------------------------------------------


async def test_confirm_email_change_missing_record(auth_service, request_mock):
    """No matching token record raises email_confirmation_invalid (L313)."""
    user = _spec_user()
    auth_service.auth_repo.get_valid_email_change_token = AsyncMock(return_value=None)

    with pytest.raises(HTTPException) as exc:
        await auth_service.confirm_email_change(user, "token", request_mock)

    assert exc.value.status_code == 400


async def test_confirm_email_change_naive_expired_token(auth_service, request_mock):
    """Naive expires_at gets UTC attached (L320) before the expiry check."""
    user = _spec_user()
    record = MagicMock()
    record.user_id = user.id
    record.used = False
    record.expires_at = datetime.now(UTC).replace(tzinfo=None) - timedelta(minutes=5)
    auth_service.auth_repo.get_valid_email_change_token = AsyncMock(return_value=record)

    with pytest.raises(HTTPException) as exc:
        await auth_service.confirm_email_change(user, "token", request_mock)

    assert exc.value.status_code == 400


async def test_confirm_email_change_update_missing_user(auth_service, request_mock):
    """Update returning no user raises EntityNotFound (L346-347)."""
    user = _spec_user()
    record = MagicMock()
    record.id = 11
    record.user_id = user.id
    record.used = False
    record.new_email = "confirmed@example.com"
    record.expires_at = datetime.now(UTC) + timedelta(minutes=30)

    auth_service.auth_repo.get_valid_email_change_token = AsyncMock(return_value=record)
    auth_service.user_repo.check_email_exists = AsyncMock(return_value=False)
    auth_service.user_repo._get_orm = AsyncMock(return_value=None)

    with pytest.raises(EntityNotFound):
        await auth_service.confirm_email_change(user, "token", request_mock)


async def test_confirm_email_change_success(auth_service, request_mock, monkeypatch):
    """Full happy path: token consumed, CSRF rotated, audit logged (L343-374)."""
    user = _spec_user()
    record = MagicMock()
    record.id = 12
    record.user_id = user.id
    record.used = False
    record.new_email = "confirmed@example.com"
    record.expires_at = datetime.now(UTC) + timedelta(minutes=30)

    db_user = MagicMock(spec=models.User)
    db_user.id = user.id
    db_user.mfa_epoch = 0
    db_user.mfa_default_method = None

    auth_service.auth_repo.get_valid_email_change_token = AsyncMock(return_value=record)
    auth_service.user_repo.check_email_exists = AsyncMock(return_value=False)
    auth_service.user_repo._get_orm = AsyncMock(return_value=db_user)
    auth_service.auth_repo.mark_email_change_token_used = AsyncMock()
    auth_service.auth_repo.invalidate_other_email_change_tokens = AsyncMock()
    auth_service.auth_repo.db = MagicMock()
    auth_service.auth_repo.db.execute = AsyncMock()

    attach_mock = AsyncMock()
    monkeypatch.setattr(auth_module, "attach_pending_email", attach_mock)
    monkeypatch.setattr(auth_module, "ensure_mfa_relationships_loaded", AsyncMock())
    monkeypatch.setattr(auth_module, "refresh_user_mfa_preferences", AsyncMock())
    csrf_mock = MagicMock()
    monkeypatch.setattr(csrf_module, "signal_csrf_rotation", csrf_mock)

    result = await auth_service.confirm_email_change(user, "token", request_mock)

    assert result is db_user
    assert db_user.email == record.new_email
    assert db_user.email_verified_at <= datetime.now(UTC)
    assert db_user.email_verified_at >= datetime.now(UTC) - timedelta(seconds=2)
    auth_service.auth_repo.mark_email_change_token_used.assert_awaited_once_with(12)
    # db_user is not the original user → second attach call fires (L359-360)
    assert attach_mock.await_count == 2
    csrf_mock.assert_called_once_with(request_mock)
    auth_service.audit.log.assert_called_with(
        "users.email.changed",
        request_mock,
        user_id=user.id,
        reason="confirmed",
    )


# ---------------------------------------------------------------------------
# change_password — guards + revoke-all branch (L387-411)
# ---------------------------------------------------------------------------


async def test_change_password_wrong_current_password(
    auth_service, request_mock, monkeypatch
):
    """Wrong current password raises invalid_password (L387)."""
    user = MagicMock()
    user.id = uuid.uuid4()
    user.hashed_password = "argon2-hash"  # pragma: allowlist secret
    payload = schemas.UserPasswordChangeIn(
        current_password="wrong-password",  # pragma: allowlist secret
        new_password="new-password-888",  # pragma: allowlist secret
    )
    monkeypatch.setattr(auth_module, "verify_password", AsyncMock(return_value=False))

    with pytest.raises(HTTPException) as exc:
        await auth_service.change_password(user, payload, request_mock)

    assert exc.value.status_code == 400


async def test_change_password_same_password(auth_service, request_mock, monkeypatch):
    """New password equal to the current one raises password_same (L389)."""
    user = MagicMock()
    user.id = uuid.uuid4()
    user.hashed_password = "argon2-hash"  # pragma: allowlist secret
    payload = schemas.UserPasswordChangeIn(
        current_password="current-pass-888",  # pragma: allowlist secret
        new_password="current-pass-888",  # pragma: allowlist secret
    )
    monkeypatch.setattr(
        auth_module, "verify_password", AsyncMock(side_effect=[True, True])
    )

    with pytest.raises(HTTPException) as exc:
        await auth_service.change_password(user, payload, request_mock)

    assert exc.value.status_code == 400


async def test_change_password_hibp_rejection(auth_service, request_mock, monkeypatch):
    """ValueError from the HIBP check maps to a 400 bad_request (L396-397)."""
    user = MagicMock()
    user.id = uuid.uuid4()
    user.hashed_password = "argon2-hash"  # pragma: allowlist secret
    payload = schemas.UserPasswordChangeIn(
        current_password="current-pass-888",  # pragma: allowlist secret
        new_password="new-password-888",  # pragma: allowlist secret
    )
    monkeypatch.setattr(
        auth_module, "verify_password", AsyncMock(side_effect=[True, False])
    )
    monkeypatch.setattr(
        auth_module,
        "validate_password_hibp",
        AsyncMock(side_effect=ValueError("breached password")),
    )

    with pytest.raises(HTTPException) as exc:
        await auth_service.change_password(user, payload, request_mock)

    assert exc.value.status_code == 400
    auth_service.user_repo.update.assert_not_called()


async def test_change_password_without_active_session_revokes_all(
    auth_service, request_mock, monkeypatch
):
    """No active session on the request revokes every session (L411)."""
    user = MagicMock()
    user.id = uuid.uuid4()
    user.hashed_password = "argon2-hash"  # pragma: allowlist secret
    request_mock.state.active_session = None
    payload = schemas.UserPasswordChangeIn(
        current_password="current-pass-888",  # pragma: allowlist secret
        new_password="new-password-888",  # pragma: allowlist secret
    )
    monkeypatch.setattr(
        auth_module, "verify_password", AsyncMock(side_effect=[True, False])
    )
    monkeypatch.setattr(auth_module, "validate_password_hibp", AsyncMock())
    monkeypatch.setattr(
        auth_module, "get_password_hash", AsyncMock(return_value="new-hash")
    )
    monkeypatch.setattr(csrf_module, "signal_csrf_rotation", MagicMock())

    auth_service.user_repo.update = AsyncMock()
    auth_service.session_repo.revoke_all_for_user = AsyncMock(return_value=3)

    ok, revoked = await auth_service.change_password(user, payload, request_mock)

    assert ok is True
    assert revoked == 3
    auth_service.session_repo.revoke_all_for_user.assert_awaited_once_with(
        user_id=user.id
    )


# ---------------------------------------------------------------------------
# refresh_pending_email with a user (L440-443)
# ---------------------------------------------------------------------------


async def test_refresh_pending_email_with_pending_request(auth_service):
    """Pending change request is attached via model_copy (L440-443)."""
    user = MagicMock()
    user.id = uuid.uuid4()
    auth_service.auth_repo.get_active_email_change_request = AsyncMock(
        return_value=SimpleNamespace(new_email="pending@example.com")
    )

    result = await auth_service.refresh_pending_email(user)

    user.model_copy.assert_called_once_with(
        update={"pending_email": "pending@example.com"}
    )
    assert result is user.model_copy.return_value


# ---------------------------------------------------------------------------
# _hash_token production guard (L457)
# ---------------------------------------------------------------------------


def test_hash_token_requires_secret_in_production(monkeypatch):
    """Unset TOKEN_HMAC_SECRET in production raises RuntimeError (L457)."""
    fake_settings = SimpleNamespace(
        token_hmac_secret=None,
        environment="production",
        secret_key="fallback-secret",  # pragma: allowlist secret
    )
    monkeypatch.setattr(auth_module, "settings", fake_settings)

    with pytest.raises(RuntimeError, match="TOKEN_HMAC_SECRET"):
        _hash_token("some-token")


# ---------------------------------------------------------------------------
# attach_pending_email / attach_pending_email_sync (L478, L485-505, L517)
# ---------------------------------------------------------------------------


async def test_attach_pending_email_none_user():
    """None user short-circuits to None (L478)."""
    assert await attach_pending_email(MagicMock(), None) is None


async def test_attach_pending_email_detached_instance_falls_back_to_db(monkeypatch):
    """DetachedInstanceError falls through to the DB query path
    (L485-488, L501-505) and sets pending_email on the ORM user (L517)."""
    user = models.User()
    user.id = uuid.uuid4()

    def _raise_detached(_obj):
        raise orm_exc.DetachedInstanceError("instance is detached")

    monkeypatch.setattr(auth_module, "inspect", _raise_detached)

    repo = MagicMock()
    repo.get_active_email_change_request = AsyncMock(
        return_value=SimpleNamespace(new_email="pending@example.com")
    )
    monkeypatch.setattr(auth_module, "AuthRepository", MagicMock(return_value=repo))

    result = await attach_pending_email(MagicMock(), user)

    assert result is user
    assert result.pending_email == "pending@example.com"
    repo.get_active_email_change_request.assert_awaited_once_with(user.id)


async def test_attach_pending_email_unexpected_inspect_error_reraises(monkeypatch):
    """Unexpected inspect() errors re-raise as RuntimeError (L489-496)."""
    user = models.User()
    user.id = uuid.uuid4()

    def _raise_value(_obj):
        raise ValueError("boom")

    monkeypatch.setattr(auth_module, "inspect", _raise_value)

    with pytest.raises(RuntimeError, match="unexpected inspect error"):
        await attach_pending_email(MagicMock(), user)


def test_attach_pending_email_sync_sets_attribute_for_plain_object():
    """Non-pydantic objects get pending_email assigned directly (L516-517)."""
    obj = SimpleNamespace()

    result = attach_pending_email_sync(obj, "direct@example.com")

    assert result is obj
    assert result.pending_email == "direct@example.com"
