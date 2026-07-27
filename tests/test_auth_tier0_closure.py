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


@pytest.mark.asyncio
async def test_graphql_validator_rejects_redis_revocation_before_db(monkeypatch):
    from app.services.auth.graphql_token_validator import GraphQLTokenValidator

    redis = AsyncMock()
    redis.exists.return_value = True
    monkeypatch.setattr(
        "app.deps.cache.get_cache_client", AsyncMock(return_value=redis)
    )
    validator = GraphQLTokenValidator(MagicMock(), AsyncMock())
    validator._load_db_session = AsyncMock()

    assert await validator.validate(str(uuid4()), "revoked-jti") is None
    validator._load_db_session.assert_not_awaited()

    redis.exists.return_value = False
    assert await validator._redis_jti_check("live-jti") is True


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
