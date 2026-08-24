from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest


def _lockout_service(monkeypatch, thresholds: str = "2:10,5:20"):
    from app.core.config import settings
    from app.services.auth.lockout import LockoutService

    monkeypatch.setattr(settings, "auth_lockout_thresholds", thresholds)
    return LockoutService(AsyncMock())


def test_lockout_duration_formats_all_units_and_russian_plural_forms(monkeypatch):
    service = _lockout_service(monkeypatch)

    assert service.format_duration("en", -1) == "1 second"
    assert service.format_duration("en", 2) == "2 seconds"
    assert service.format_duration("en", 60) == "1 minute"
    assert service.format_duration("en", 3600) == "1 hour"
    assert service.format_duration("ru", 1) == "1 секунду"
    assert service.format_duration("ru", 22 * 60) == "22 минуты"
    assert service.format_duration("ru", 11 * 60) == "11 минут"
    assert service._pluralize_ru(5, "unknown") == "unknown"


def test_lockout_message_includes_retry_details_for_active_lock(monkeypatch):
    service = _lockout_service(monkeypatch)
    translated = {
        "errors.auth.account_locked": "Account locked",
        "errors.auth.account_locked_retry": "Try again in {duration}",
    }

    def translate(key: str, *, locale: str, **kwargs: object) -> str:
        del locale
        return translated[key].format(**kwargs)

    with patch("app.services.auth.lockout.translate", side_effect=translate):
        detail, retry_after = service.get_lockout_message(
            "en", datetime.now(UTC) + timedelta(seconds=61)
        )

    assert detail.startswith("Account locked Try again in ")
    assert retry_after >= 60


def test_lockout_parser_and_empty_rule_paths_are_defensive(monkeypatch):
    from app.core.config import settings
    from app.services.auth.lockout import LockoutService

    monkeypatch.setattr(
        settings,
        "auth_lockout_thresholds",
        ["", "malformed", "1:2:3", "not-int:5", "3:not-int", "0:5", "5:0", "2:10"],
    )
    monkeypatch.setattr(settings, "auth_lockout_history_minutes", 0)
    service = LockoutService(AsyncMock())

    assert service._rules == [(2, 10)]
    assert service._max_lockout_threshold() == 2
    assert service._normalize_timestamp(datetime.now(UTC)).tzinfo is UTC
    assert service._calculate_lock_until([], datetime.now(UTC)) is None


@pytest.mark.asyncio
async def test_lockout_zero_limits_and_disabled_rules_return_safely(monkeypatch):
    from app.core.config import settings
    from app.services.auth.lockout import LockoutService

    monkeypatch.setattr(settings, "auth_lockout_thresholds", [])
    monkeypatch.setattr(settings, "auth_lockout_history_minutes", 0)
    service = LockoutService(AsyncMock())
    service.repo.get_failed_attempts = AsyncMock(return_value=[])

    assert service._max_lockout_threshold() == 0
    await service._prune_stale_attempts("user@example.com")
    assert await service._fetch_recent_attempts("user@example.com", 0) == []
    assert await service.get_active_lockout("user@example.com") is None
    service.repo.get_failed_attempts.assert_awaited_once_with("user@example.com", 1)


@pytest.mark.asyncio
async def test_lockout_register_uses_postgres_advisory_lock(monkeypatch):
    from app.core.config import settings
    from app.services.auth.lockout import LockoutService

    monkeypatch.setattr(settings, "auth_lockout_thresholds", "1:60")
    monkeypatch.setattr(settings, "auth_lockout_history_minutes", 0)
    db = AsyncMock()
    service = LockoutService(db)
    service._is_postgresql = True
    service._prune_stale_attempts = AsyncMock()
    service._fetch_recent_attempts = AsyncMock(return_value=[])
    attempt = SimpleNamespace(attempted_at=datetime.now(UTC))
    service.repo.create_failed_attempt = AsyncMock(return_value=attempt)

    lock_until, triggered, count = await service.register_failed_attempt(
        "user@example.com", None
    )

    assert lock_until is not None
    assert triggered is True
    assert count == 1
    db.execute.assert_awaited_once()
    service.repo.create_failed_attempt.assert_awaited_once_with(
        email="user@example.com", user_id=None
    )


def test_lockout_message_returns_base_for_expired_lock(monkeypatch):
    service = _lockout_service(monkeypatch)

    with patch("app.services.auth.lockout.translate", return_value="Account locked"):
        assert service.get_lockout_message(
            "en", datetime.now(UTC) - timedelta(seconds=1)
        ) == ("Account locked", 0)


@pytest.mark.asyncio
async def test_graphql_validator_rejects_redis_revocation_before_db(monkeypatch):
    from app.services.auth.graphql_token_validator import GraphQLTokenValidator

    redis = AsyncMock()
    redis.exists.return_value = True
    monkeypatch.setattr(
        "app.services.auth.graphql_token_validator.get_revocation_redis_client",
        AsyncMock(return_value=redis),
    )
    validator = GraphQLTokenValidator(MagicMock(), AsyncMock())
    validator._load_db_session = AsyncMock()

    assert await validator.validate(str(uuid4()), "revoked-jti") is None
    validator._load_db_session.assert_not_awaited()

    redis.exists.return_value = False
    assert await validator._redis_jti_check("live-jti") is True


@pytest.mark.asyncio
async def test_graphql_validator_allows_active_user_without_legacy_fingerprint():
    from app.services.auth.graphql_token_validator import GraphQLTokenValidator

    user_id = uuid4()
    active_session = SimpleNamespace(
        jti="live-jti",
        expires_at=datetime.now(UTC) + timedelta(minutes=5),
        fingerprint_hash=None,
    )
    user = SimpleNamespace(id=user_id, is_active=True)
    session_result = MagicMock()
    session_result.scalar_one_or_none.return_value = active_session
    user_result = MagicMock()
    user_result.scalar_one_or_none.return_value = user
    session = AsyncMock()
    session.execute.side_effect = [session_result, user_result]
    redis = AsyncMock()
    redis.exists.return_value = False

    with patch(
        "app.services.auth.graphql_token_validator.get_revocation_redis_client",
        AsyncMock(return_value=redis),
    ):
        result = await GraphQLTokenValidator(MagicMock(), session).validate(
            str(user_id), "live-jti"
        )

    assert result is user
    assert session.execute.await_count == 2


@pytest.mark.asyncio
async def test_graphql_validator_redis_failure_falls_back_to_database(monkeypatch):
    from app.services.auth.graphql_token_validator import GraphQLTokenValidator

    monkeypatch.setattr(
        "app.services.auth.graphql_token_validator.get_revocation_redis_client",
        AsyncMock(side_effect=ConnectionError("redis unavailable")),
    )

    validator = GraphQLTokenValidator(MagicMock(), AsyncMock())

    assert await validator._redis_jti_check("jti") is True


@pytest.mark.asyncio
async def test_graphql_validator_database_failure_denies_request():
    from app.services.auth.graphql_token_validator import GraphQLTokenValidator

    session = AsyncMock()
    session.execute.side_effect = OSError("database unavailable")
    validator = GraphQLTokenValidator(MagicMock(), session)

    assert await validator._load_db_session("jti") is None


@pytest.mark.asyncio
async def test_graphql_validator_rejects_expired_and_inactive_users():
    from app.services.auth.graphql_token_validator import GraphQLTokenValidator

    validator = GraphQLTokenValidator(MagicMock(), AsyncMock())
    validator._redis_jti_check = AsyncMock(return_value=True)
    validator._check_fingerprint = AsyncMock(return_value=True)
    expired = SimpleNamespace(
        expires_at=datetime.now(UTC) - timedelta(seconds=1), fingerprint_hash=None
    )
    validator._load_db_session = AsyncMock(return_value=expired)
    validator._load_user = AsyncMock()

    assert await validator.validate(str(uuid4()), "expired") is None
    validator._load_user.assert_not_awaited()

    active = SimpleNamespace(
        expires_at=datetime.now(UTC) + timedelta(minutes=5), fingerprint_hash=None
    )
    inactive = SimpleNamespace(is_active=False)
    validator._load_db_session = AsyncMock(return_value=active)
    validator._load_user = AsyncMock(return_value=inactive)

    assert await validator.validate(str(uuid4()), "inactive") is None
    validator._check_fingerprint.assert_not_awaited()


@pytest.mark.asyncio
async def test_graphql_validator_load_user_handles_invalid_and_non_string_subjects():
    from app.services.auth.graphql_token_validator import GraphQLTokenValidator

    session = AsyncMock()
    result = MagicMock()
    user = SimpleNamespace(is_active=True)
    result.scalar_one_or_none.return_value = user
    session.execute.return_value = result
    validator = GraphQLTokenValidator(MagicMock(), session)

    assert await validator._load_user("not-a-uuid") is None
    session.execute.assert_not_awaited()
    assert await validator._load_user(None) is user


@pytest.mark.asyncio
async def test_graphql_validator_fingerprint_success_and_failure_are_fail_closed():
    from app.services.auth.graphql_token_validator import GraphQLTokenValidator

    request = MagicMock()
    validator = GraphQLTokenValidator(request, AsyncMock())
    user = SimpleNamespace(id=uuid4(), is_active=True)
    active_session = SimpleNamespace(
        fingerprint_hash="stored",
        jti="jti",
        expires_at=datetime.now(UTC) + timedelta(minutes=5),
    )

    with (
        patch("app.services.auth.fingerprint_service.AuthFingerprintService") as fp_cls,
        patch("app.services.auth.redis_session.RedisSessionService") as redis_cls,
    ):
        fp_cls.return_value.validate_fingerprint = AsyncMock()
        assert await validator._check_fingerprint(user, active_session) is True
        fp_cls.return_value.validate_fingerprint.assert_awaited_once_with(
            user, active_session, validator._session, redis_cls.return_value
        )

        fp_cls.return_value.validate_fingerprint = AsyncMock(
            side_effect=RuntimeError("fingerprint mismatch")
        )
        assert await validator._check_fingerprint(user, active_session) is False

    validator._redis_jti_check = AsyncMock(return_value=True)
    validator._load_db_session = AsyncMock(return_value=active_session)
    validator._load_user = AsyncMock(return_value=user)
    validator._check_fingerprint = AsyncMock(return_value=False)

    assert await validator.validate(str(user.id), active_session.jti) is None


@pytest.mark.asyncio
async def test_graphql_validator_rejects_missing_db_session():
    from app.services.auth.graphql_token_validator import GraphQLTokenValidator

    validator = GraphQLTokenValidator(MagicMock(), AsyncMock())
    validator._redis_jti_check = AsyncMock(return_value=True)
    validator._load_db_session = AsyncMock(return_value=None)

    assert await validator.validate(str(uuid4()), "missing-jti") is None


@pytest.mark.asyncio
async def test_graphql_validator_loads_active_session_and_normalizes_naive_expiry():
    from app.services.auth.graphql_token_validator import GraphQLTokenValidator

    session = AsyncMock()
    result = MagicMock()
    active_session = SimpleNamespace(
        expires_at=datetime.now(UTC) + timedelta(minutes=5)
    )
    result.scalar_one_or_none.return_value = active_session
    session.execute.return_value = result
    validator = GraphQLTokenValidator(MagicMock(), session)

    assert await validator._load_db_session("active-jti") is active_session
    naive_future = SimpleNamespace(
        expires_at=datetime.now(UTC).replace(tzinfo=None) + timedelta(minutes=5)
    )
    assert validator._check_expiry(naive_future) is True


@pytest.mark.asyncio
async def test_login_session_manager_uses_model_copy_for_mfa_user():
    from app.services.auth.login_session_manager import LoginSessionManager

    user_id = uuid4()
    copied_user = SimpleNamespace(
        id=user_id,
        is_active=True,
        role=SimpleNamespace(value="student"),
    )
    user = SimpleNamespace(
        id=user_id,
        is_active=True,
        role=SimpleNamespace(value="student"),
        model_copy=MagicMock(return_value=copied_user),
    )
    session = SimpleNamespace(jti=uuid4(), mfa_verified_at=datetime.now(UTC))
    manager = LoginSessionManager(AsyncMock(), AsyncMock(), MagicMock(), MagicMock())
    manager.session_service.create_access_token.return_value = ("token", session)
    manager.extract_client_info = MagicMock(return_value=(None, None))
    manager.build_token_response = AsyncMock(return_value=MagicMock())
    request = MagicMock()

    with (
        patch(
            "app.services.auth.login_session_manager.extract_fingerprint",
            return_value=SimpleNamespace(accept_language=None, fingerprint_hash=None),
        ),
        patch("app.services.auth.login_session_manager.metrics.record_login_success"),
    ):
        # signal_csrf_rotation is imported inside finalize_login; provide the
        # module through sys.modules so the import remains isolated from globals.
        with patch.dict(
            "sys.modules",
            {"app.core.csrf": SimpleNamespace(signal_csrf_rotation=MagicMock())},
        ):
            await manager.finalize_login(
                user,
                request,
                MagicMock(),
                MagicMock(),
                MagicMock(),
                mfa_completed=True,
                method="totp",
            )

    user.model_copy.assert_called_once()
    assert (
        manager.session_service.create_access_token.await_args.kwargs["sub"] == user_id
    )


@pytest.mark.asyncio
async def test_build_token_response_covers_no_pending_email_and_no_signing_key():
    from app.services.auth import login_session_manager as module

    user = SimpleNamespace(id=uuid4())
    session = SimpleNamespace(signing_key="")
    manager = module.LoginSessionManager(
        MagicMock(), MagicMock(), MagicMock(), MagicMock()
    )

    with (
        patch.object(
            module, "ensure_mfa_relationships_loaded", new=AsyncMock(return_value=user)
        ),
        patch(
            "app.services.auth_service.attach_pending_email",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "app.schemas.schemas.UserOut.model_validate",
            return_value=MagicMock(),
        ),
        patch.object(
            module.schemas, "TokenWithProfile", return_value=MagicMock()
        ) as token_model,
    ):
        result = await manager.build_token_response(
            user, "token", session, MagicMock(), include_token=True
        )

    assert result is token_model.return_value
    assert token_model.call_args.kwargs["session"] is None
