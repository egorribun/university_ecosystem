"""Independent-review regressions for cache-free revocation and login races."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import Request


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "operation",
    ["backend", "cleanup", "single", "others", "compliance", "password_reset"],
)
async def test_cache_free_security_revocation_always_writes_tombstones(
    db_session, test_user, mock_global_redis, monkeypatch, operation
):
    from app.auth import redis_session
    from app.models import ActiveSession, PasswordResetToken
    from app.repositories.auth_repository import AuthRepository
    from app.repositories.unit_of_work import uow_from_session
    from app.repositories.user_repository import UserRepository
    from app.services.auth_service import AuthService, _hash_token
    from app.services.session_cleanup import revoke_sessions_matching
    from app.services.session_service import SessionService

    monkeypatch.setattr(redis_session.settings, "session_storage_backend", "memory")
    session = ActiveSession(
        user_id=test_user.id,
        jti=f"memory-{operation}",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    db_session.add(session)
    reset_token = "one-time-reset-test-token"
    if operation == "password_reset":
        db_session.add(
            PasswordResetToken(
                user_id=test_user.id,
                token_hash=_hash_token(reset_token),
                expires_at=datetime.now(UTC) + timedelta(minutes=10),
            )
        )
    await db_session.commit()
    uow = uow_from_session(db_session)
    session_service = SessionService(uow)
    if operation == "backend":
        backend = await redis_session.get_session_backend()
        await backend.revoke_session(session.jti, session.expires_at)
        assert not await backend.is_session_valid(session.jti)
    elif operation == "cleanup":
        await revoke_sessions_matching(
            db=db_session, whereclause=ActiveSession.id == session.id
        )
    elif operation == "single":
        await session_service.revoke_session_by_id(session.id)
    elif operation == "others":
        await session_service.revoke_other_sessions(test_user.id, None)
    elif operation == "compliance":
        from app.services.user.compliance_service import UserComplianceService

        await UserComplianceService(uow, MagicMock())._revoke_user_sessions(
            test_user.id
        )
    else:
        service = AuthService(
            audit=MagicMock(),
            auth_repo=AuthRepository(db_session),
            user_repo=UserRepository(db_session),
            session_repo=uow.sessions,
            uow=uow,
        )
        request = Request(
            {
                "type": "http",
                "headers": [],
                "query_string": b"",
                "path": "/",
                "method": "POST",
            }
        )
        with (
            patch("app.auth.security.validate_password_hibp", AsyncMock()),
            patch(
                "app.services.auth_service.get_password_hash",
                AsyncMock(return_value="new-password-hash"),
            ),
        ):
            await service.perform_password_reset(
                reset_token, "new-password-123", request
            )
    assert await mock_global_redis.exists(f"revoked:jti:memory-{operation}") == 1


@pytest.mark.asyncio
async def test_cache_free_revocation_propagates_security_store_failure(monkeypatch):
    from app.auth import redis_session

    monkeypatch.setattr(redis_session.settings, "session_storage_backend", "memory")
    backend = await redis_session.get_session_backend()
    with patch(
        "app.services.auth.redis_session.RedisSessionService.revoke_session",
        AsyncMock(side_effect=OSError("security store down")),
    ):
        with pytest.raises(OSError, match="security store down"):
            await backend.revoke_session("session")


@pytest.mark.asyncio
async def test_login_paused_after_old_password_validation_cannot_mint_after_change(
    db_session, test_user, mock_global_redis
):
    import asyncio

    from fastapi import BackgroundTasks, HTTPException, Response

    from app.auth.security import get_password_hash
    from app.models import ActiveSession
    from app.repositories.auth_repository import AuthRepository
    from app.repositories.unit_of_work import uow_from_session
    from app.repositories.user_repository import UserRepository
    from app.schemas.schemas import UserPasswordChangeIn
    from app.services.auth.credential_validator import CredentialValidator
    from app.services.auth.login_service import LoginService
    from app.services.auth.login_session_manager import LoginSessionManager
    from app.services.auth.redis_session import RedisSessionService
    from app.services.auth_service import AuthService
    from app.services.session_service import SessionService

    old_password = "Old-test-password-883!"  # pragma: allowlist secret
    new_password = "New-test-password-992!"  # pragma: allowlist secret
    test_user.hashed_password = await get_password_hash(old_password)
    test_user.mfa_epoch = 0
    stale_mfa = datetime.now(UTC) - timedelta(days=1)
    current = ActiveSession(
        user_id=test_user.id,
        jti="preserved-change-session",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
        mfa_epoch=0,
        mfa_verified_at=stale_mfa,
    )
    db_session.add(current)
    await db_session.commit()
    uow = uow_from_session(db_session)
    repo = UserRepository(db_session)
    redis_service = RedisSessionService()
    manager = LoginSessionManager(
        SessionService(uow), redis_service, MagicMock(), MagicMock()
    )
    validator = CredentialValidator(
        uow,
        repo,
        SimpleNamespace(get_auth_user_by_email=repo.get_auth_by_email),
        SimpleNamespace(
            get_active_lockout=AsyncMock(return_value=None),
            clear_failed_attempts=AsyncMock(return_value=0),
        ),
        MagicMock(),
        manager,
    )
    credentials_verified = asyncio.Event()
    resume_login = asyncio.Event()

    async def pause_after_validation(**_kwargs):
        credentials_verified.set()
        await resume_login.wait()
        return None

    coordinator = SimpleNamespace(
        repo=AuthRepository(db_session),
        check_and_issue_challenges=pause_after_validation,
    )
    login = LoginService(validator, coordinator, manager, db_session)
    request = Request(
        {
            "type": "http",
            "headers": [],
            "query_string": b"",
            "path": "/",
            "method": "POST",
        }
    )
    request.state.active_session = current
    await redis_service.create_session(
        current.jti, test_user.id, None, stale_mfa, session_id=current.id, mfa_epoch=0
    )
    pending_login = asyncio.create_task(
        login.perform_login(
            test_user.email, old_password, request, Response(), BackgroundTasks()
        )
    )
    await asyncio.wait_for(credentials_verified.wait(), timeout=5)
    auth = AuthService(MagicMock(), AuthRepository(db_session), repo, uow.sessions, uow)
    try:
        with patch("app.services.auth_service.validate_password_hibp", AsyncMock()):
            assert await auth.change_password(
                test_user,
                UserPasswordChangeIn(
                    current_password=old_password, new_password=new_password
                ),
                request,
            ) == (True, 0)
    finally:
        resume_login.set()
    with pytest.raises(HTTPException) as rejected:
        await pending_login
    assert rejected.value.status_code == 401
    assert test_user.mfa_epoch == 1
    assert current.mfa_epoch == 1
    assert current.revoked_at is None
    assert current.mfa_verified_at == stale_mfa
    assert await mock_global_redis.exists("session:v2:preserved-change-session") == 0
    assert await mock_global_redis.exists("revoked:jti:preserved-change-session") == 0

    # A fresh validation using the new password can still create a session.
    result = await login.perform_login(
        test_user.email, new_password, request, Response(), BackgroundTasks()
    )
    assert result.user.id == test_user.id


@pytest.mark.asyncio
async def test_late_password_rehash_cannot_restore_prechange_password(
    db_session, test_user
):
    import asyncio

    from fastapi import BackgroundTasks, HTTPException

    from app.auth.security import get_password_hash, verify_password
    from app.repositories.auth_repository import AuthRepository
    from app.repositories.unit_of_work import uow_from_session
    from app.repositories.user_repository import UserRepository
    from app.schemas.schemas import UserPasswordChangeIn
    from app.services.auth.credential_validator import CredentialValidator
    from app.services.auth_service import AuthService

    old_password = "Old-rehash-password-11!"  # pragma: allowlist secret
    new_password = "New-rehash-password-22!"  # pragma: allowlist secret
    test_user.hashed_password = await get_password_hash(old_password)
    test_user.mfa_epoch = 0
    await db_session.commit()
    uow = uow_from_session(db_session)
    repo = UserRepository(db_session)
    validator = CredentialValidator(
        uow,
        repo,
        SimpleNamespace(get_auth_user_by_email=repo.get_auth_by_email),
        SimpleNamespace(
            get_active_lockout=AsyncMock(return_value=None),
            clear_failed_attempts=AsyncMock(return_value=0),
        ),
        MagicMock(),
        MagicMock(),
    )
    request = Request(
        {
            "type": "http",
            "headers": [],
            "query_string": b"",
            "path": "/",
            "method": "POST",
        }
    )
    request.state.active_session = None
    credentials_verified = asyncio.Event()
    resume_rehash = asyncio.Event()

    async def verify_then_pause(password, encoded):
        assert await verify_password(password, encoded)
        upgraded = await get_password_hash(password)
        credentials_verified.set()
        await resume_rehash.wait()
        return True, upgraded

    with patch(
        "app.services.auth.credential_validator.verify_and_update_password",
        verify_then_pause,
    ):
        pending = asyncio.create_task(
            validator.validate_credentials(
                test_user.email, old_password, request, "en", BackgroundTasks()
            )
        )
        await asyncio.wait_for(credentials_verified.wait(), timeout=5)
        try:
            auth = AuthService(
                MagicMock(), AuthRepository(db_session), repo, uow.sessions, uow
            )
            with patch("app.services.auth_service.validate_password_hibp", AsyncMock()):
                await auth.change_password(
                    test_user,
                    UserPasswordChangeIn(
                        current_password=old_password, new_password=new_password
                    ),
                    request,
                )
        finally:
            resume_rehash.set()
        with pytest.raises(HTTPException) as rejected:
            await pending
    assert rejected.value.status_code == 401
    await db_session.refresh(test_user)
    assert await verify_password(new_password, test_user.hashed_password)
    assert not await verify_password(old_password, test_user.hashed_password)
    assert test_user.mfa_epoch == 1


@pytest.mark.asyncio
async def test_password_repository_rejects_stale_hash_and_rehash_preserves_epoch(
    db_session, test_user
):
    from app.repositories.user_repository import UserRepository

    old_hash = test_user.hashed_password
    upgraded_hash = uuid4().hex
    stale_rehash = uuid4().hex
    stale_password_hash = uuid4().hex
    test_user.mfa_epoch = 4
    await db_session.commit()
    repo = UserRepository(db_session)
    assert (
        await repo.rehash_password_if_current(
            test_user.id, expected_hash=old_hash, new_hash=upgraded_hash
        )
        is True
    )
    assert test_user.mfa_epoch == 4
    assert (
        await repo.rehash_password_if_current(
            test_user.id, expected_hash=old_hash, new_hash=stale_rehash
        )
        is False
    )
    assert (
        await repo.change_password_if_current(
            test_user.id, expected_hash=old_hash, new_hash=stale_password_hash
        )
        is None
    )
    assert test_user.hashed_password == upgraded_hash
    assert test_user.mfa_epoch == 4


@pytest.mark.asyncio
@pytest.mark.parametrize("cache_mode", ["disabled", "unavailable"])
async def test_optional_metadata_invalidation_does_not_require_cache(cache_mode):
    from app.services.auth.redis_session import RedisSessionService

    service = RedisSessionService()
    if cache_mode == "disabled":
        service.redis_url = ""
    with patch(
        "app.services.auth.redis_session._get_shared_client",
        AsyncMock(side_effect=OSError("cache unavailable")),
    ) as client:
        await service.invalidate_session_cache("preserved")
    if cache_mode == "disabled":
        client.assert_not_awaited()
    else:
        client.assert_awaited_once()


@pytest.mark.asyncio
async def test_cache_free_validity_check_fails_closed_when_revocation_store_is_down(
    monkeypatch,
):
    from app.auth import redis_session

    monkeypatch.setattr(redis_session.settings, "session_storage_backend", "memory")
    backend = await redis_session.get_session_backend()
    with patch.object(
        redis_session,
        "get_revocation_redis_client",
        AsyncMock(side_effect=OSError("revocation unavailable")),
    ):
        with pytest.raises(OSError, match="revocation unavailable"):
            await backend.is_session_valid("session")
