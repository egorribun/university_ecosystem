"""Branch-only closure tests for AuthService helpers and lifecycle paths."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from fastapi import BackgroundTasks

import app.models as models
import app.services.auth_service as auth_module
from app.schemas import schemas
from app.services.auth_service import (
    AuthService,
    _hash_token,
    attach_pending_email,
    attach_pending_email_sync,
)


def _service() -> AuthService:
    audit = MagicMock()
    auth_repo = MagicMock()
    auth_repo.db = MagicMock()
    user_repo = MagicMock()
    session_repo = MagicMock()
    uow = MagicMock()
    uow.__aenter__ = AsyncMock(return_value=uow)
    uow.__aexit__ = AsyncMock(return_value=False)
    uow.commit = AsyncMock()
    uow.session.refresh = AsyncMock()
    return AuthService(audit, auth_repo, user_repo, session_repo, uow)


async def test_initiate_password_reset_skips_sleep_when_timing_budget_elapsed(
    monkeypatch,
):
    service = _service()
    service.user_repo.get_by_email = AsyncMock(return_value=None)
    request = MagicMock()
    monkeypatch.setenv("ENVIRONMENT", "test")

    with (
        patch("app.core.ratelimit.enforce_rate_limit", new=AsyncMock()),
        patch("app.core.ratelimit.get_default_strategy", return_value="email"),
        patch("time.perf_counter", side_effect=[0.0, 1.0]),
        patch("asyncio.sleep", new=AsyncMock()) as sleep,
    ):
        await service.initiate_password_reset(
            "missing@example.com", request, BackgroundTasks()
        )

    sleep.assert_not_awaited()


async def test_initiate_email_change_skips_dto_refresh_and_second_attach():
    service = _service()
    user = SimpleNamespace(
        id=uuid4(),
        email="old@example.com",
        hashed_password="hash",
        profile=SimpleNamespace(full_name="User"),
        model_dump=MagicMock(),
    )
    payload = schemas.UserEmailChangeIn(
        email="new@example.com", password="correct-password"
    )
    service.user_repo.check_email_exists = AsyncMock(return_value=False)
    service.user_repo.get = AsyncMock(return_value=user)
    service.auth_repo.create_email_change_token = AsyncMock()
    attach = AsyncMock(return_value=user)

    with (
        patch("app.services.auth_service.resolve_locale", return_value="en"),
        patch("app.auth.security.verify_password", new=AsyncMock(return_value=True)),
        patch.object(
            auth_module,
            "ensure_mfa_relationships_loaded",
            new=AsyncMock(return_value=user),
        ),
        patch.object(auth_module, "attach_pending_email", new=attach),
        patch.object(auth_module.send_auth_email, "kick", new=AsyncMock()),
    ):
        result = await service.initiate_email_change(
            user, payload, MagicMock(), BackgroundTasks()
        )

    assert result is user
    service.uow.session.refresh.assert_not_awaited()
    attach.assert_awaited_once_with(service.auth_repo.db, user)


async def test_confirm_email_change_skips_second_attach_for_same_db_user():
    service = _service()
    user = MagicMock()
    user.id = uuid4()
    record = SimpleNamespace(
        id=7,
        user_id=user.id,
        used=False,
        new_email="new@example.com",
        expires_at=datetime.now(UTC) + timedelta(minutes=10),
    )
    service.auth_repo.get_valid_email_change_token = AsyncMock(return_value=record)
    service.user_repo.check_email_exists = AsyncMock(return_value=False)
    service.user_repo.update = AsyncMock(return_value=user)
    service.auth_repo.mark_email_change_token_used = AsyncMock()
    service.auth_repo.invalidate_other_email_change_tokens = AsyncMock()
    attach = AsyncMock(return_value=user)

    with (
        patch("app.services.auth_service.resolve_locale", return_value="en"),
        patch.object(
            auth_module,
            "ensure_mfa_relationships_loaded",
            new=AsyncMock(return_value=user),
        ),
        patch.object(auth_module, "attach_pending_email", new=attach),
        patch("app.core.csrf.signal_csrf_rotation"),
    ):
        result = await service.confirm_email_change(user, "token", MagicMock())

    assert result is user
    attach.assert_awaited_once_with(service.auth_repo.db, user)


async def test_change_password_updates_model_user_instance(monkeypatch):
    class FakeUser:
        def __init__(self):
            self.id = uuid4()
            self.hashed_password = "old-hash"

    service = _service()
    user = FakeUser()
    request = MagicMock()
    request.state.active_session = None
    payload = schemas.UserPasswordChangeIn(
        current_password="old-password", new_password="new-password"
    )
    service.user_repo.update = AsyncMock()
    service.session_repo.revoke_all_for_user = AsyncMock(return_value=1)

    with (
        patch.object(auth_module.models, "User", FakeUser),
        patch.object(auth_module, "resolve_locale", return_value="en"),
        patch.object(
            auth_module, "verify_password", new=AsyncMock(side_effect=[True, False])
        ),
        patch.object(auth_module, "validate_password_hibp", new=AsyncMock()),
        patch.object(
            auth_module, "get_password_hash", new=AsyncMock(return_value="new-hash")
        ),
        patch("app.core.csrf.signal_csrf_rotation"),
    ):
        ok, revoked = await service.change_password(user, payload, request)

    assert (ok, revoked) == (True, 1)
    assert user.hashed_password == "new-hash"


def test_hash_token_falls_back_to_secret_key_in_testing(monkeypatch):
    monkeypatch.setattr(
        auth_module,
        "settings",
        SimpleNamespace(
            token_hmac_secret=None,
            environment="testing",
            secret_key="fallback-secret",
        ),
    )

    assert len(_hash_token("token")) == 64


def test_hash_token_uses_explicit_hmac_secret(monkeypatch):
    monkeypatch.setattr(
        auth_module,
        "settings",
        SimpleNamespace(
            token_hmac_secret="explicit-secret",
            environment="testing",
            secret_key="unused-secret",
        ),
    )

    assert len(_hash_token("token")) == 64


async def test_attach_pending_email_returns_loaded_orm_relationship(monkeypatch):
    user = models.User()
    user.id = uuid4()
    marker = object()
    monkeypatch.setattr(
        auth_module,
        "inspect",
        lambda _user: SimpleNamespace(unloaded=set()),
    )
    monkeypatch.setattr(auth_module, "attach_pending_email_sync", lambda *_: marker)

    assert await attach_pending_email(MagicMock(), user) is marker


async def test_attach_pending_email_uses_repository_for_non_orm_user():
    user = SimpleNamespace(id=uuid4())
    repo = MagicMock()
    repo.get_active_email_change_request = AsyncMock(
        return_value=SimpleNamespace(new_email="pending@example.com")
    )

    with patch.object(auth_module, "AuthRepository", return_value=repo):
        result = await attach_pending_email(MagicMock(), user)

    assert result.pending_email == "pending@example.com"


async def test_attach_pending_email_uses_repository_when_relationship_unloaded(
    monkeypatch,
):
    user = models.User()
    user.id = uuid4()
    repo = MagicMock()
    repo.get_active_email_change_request = AsyncMock(return_value=None)
    monkeypatch.setattr(auth_module, "AuthRepository", MagicMock(return_value=repo))
    monkeypatch.setattr(
        auth_module,
        "inspect",
        lambda _user: SimpleNamespace(unloaded={"email_change_tokens"}),
    )

    result = await attach_pending_email(MagicMock(), user)

    assert result is user
    assert user.pending_email is None


def test_attach_pending_email_sync_selects_latest_unexpired_token():
    user = models.User()
    user.id = uuid4()
    now = datetime.now(UTC)
    user.__dict__["email_change_tokens"] = [
        SimpleNamespace(
            used=False,
            expires_at=now.replace(tzinfo=None) + timedelta(minutes=5),
            created_at=now - timedelta(minutes=2),
            new_email="older@example.com",
        ),
        SimpleNamespace(
            used=False,
            expires_at=now + timedelta(minutes=10),
            created_at=now - timedelta(minutes=1),
            new_email="latest@example.com",
        ),
        SimpleNamespace(
            used=True,
            expires_at=now + timedelta(minutes=20),
            created_at=now,
            new_email="used@example.com",
        ),
    ]

    result = attach_pending_email_sync(user, None)

    assert result is user
    assert user.pending_email == "latest@example.com"


def test_attach_pending_email_sync_clears_pending_when_no_token_is_active():
    user = models.User()
    user.id = uuid4()
    user.__dict__["email_change_tokens"] = []

    result = attach_pending_email_sync(user, None)

    assert result is user
    assert user.pending_email is None


def test_attach_pending_email_sync_leaves_plain_object_unchanged_without_email():
    user = SimpleNamespace(id=uuid4())

    result = attach_pending_email_sync(user, None)

    assert result is user
    assert not hasattr(user, "pending_email")
