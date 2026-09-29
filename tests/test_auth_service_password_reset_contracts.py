"""Collaborator-contract tests for the password-reset flow of ``AuthService``.

The reset flow is a security boundary: lock ordering, locale propagation,
session revocation scope and rate-limit parameters are all part of its
contract, so each is pinned here through the collaborators the service drives.
"""

from __future__ import annotations

import hashlib
import hmac
import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest
from fastapi import BackgroundTasks, HTTPException, Request

import app.api.validation as validation_module
import app.auth.security as security_module
import app.services.auth_service as auth_module
from app.core.localization import translate
from app.services.auth_service import (
    AuthService,
    _password_reset_rate_limit_identifier,
)

_LOCALE = "ru"
_TOKEN_DIGEST = "digest-of-token"  # pragma: allowlist secret
_NEW_PASSWORD = "new-password-888"  # pragma: allowlist secret
_EXPIRED_KEY = "errors.password.invalid_or_expired_link"


class _AsyncDatabase:
    """Minimal awaitable-``execute`` session so the production branch is taken."""

    def __init__(self) -> None:
        self.statements: list[Any] = []

    async def execute(self, statement: Any) -> None:
        self.statements.append(statement)


def _request() -> MagicMock:
    request = MagicMock(spec=Request)
    request.state = MagicMock()
    request.headers = {"accept-language": "en"}
    return request


def _service(*, db: object | None = None) -> AuthService:
    auth_repo = MagicMock()
    auth_repo.db = db if db is not None else MagicMock()
    auth_repo.mark_password_reset_token_used = AsyncMock()
    auth_repo.invalidate_all_user_password_reset_tokens = AsyncMock()
    uow = MagicMock()
    uow.__aenter__.return_value = uow
    uow.__aexit__.return_value = None
    uow.commit = AsyncMock()
    user_repo = MagicMock()
    user_repo.update = AsyncMock()
    return AuthService(
        audit=MagicMock(),
        auth_repo=auth_repo,
        user_repo=user_repo,
        session_repo=MagicMock(),
        uow=uow,
    )


def _record(
    user_id: uuid.UUID, *, expires_in: timedelta = timedelta(minutes=10)
) -> SimpleNamespace:
    return SimpleNamespace(
        id=7, user_id=user_id, expires_at=datetime.now(UTC) + expires_in
    )


def _user(user_id: uuid.UUID, **attributes: Any) -> SimpleNamespace:
    return SimpleNamespace(id=user_id, is_active=True, **attributes)


@pytest.fixture(autouse=True)
def _reset_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> list[tuple[str, dict[str, Any]]]:
    """Force the reset locale and spy on the translation lookups."""

    monkeypatch.setattr(auth_module, "resolve_locale", lambda **_: _LOCALE)
    monkeypatch.setattr(auth_module, "_hash_token", lambda _: _TOKEN_DIGEST)
    monkeypatch.setattr(
        security_module, "validate_password_hibp", AsyncMock(return_value=None)
    )
    monkeypatch.setattr(
        auth_module, "get_password_hash", AsyncMock(return_value="new-hash")
    )
    lookups: list[tuple[str, dict[str, Any]]] = []
    real_translate = validation_module.translate

    def _spy(message_key: str, **kwargs: Any) -> str:
        lookups.append((message_key, kwargs))
        return real_translate(message_key, **kwargs)

    monkeypatch.setattr(validation_module, "translate", _spy)
    return lookups


async def test_reset_success_pins_locks_arguments_and_revocation_scope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Every collaborator receives exactly the documented lock/scope arguments."""

    user_id = uuid.uuid4()
    db = _AsyncDatabase()
    service = _service(db=db)
    record = _record(user_id)
    service.auth_repo.get_valid_password_reset_token = AsyncMock(
        side_effect=[record, record]
    )
    service.user_repo.get = AsyncMock(return_value=_user(user_id, mfa_epoch=3))
    revoke = AsyncMock(return_value=5)
    monkeypatch.setattr(auth_module, "revoke_sessions_matching", revoke)
    request = _request()

    await service.perform_password_reset("opaque-token", _NEW_PASSWORD, request)

    assert service.auth_repo.get_valid_password_reset_token.await_args_list == [
        call(_TOKEN_DIGEST, with_for_update=False),
        call(_TOKEN_DIGEST, with_for_update=True),
    ]
    service.user_repo.get.assert_awaited_once_with(user_id, with_for_update=True)
    security_module.validate_password_hibp.assert_awaited_once_with(
        _NEW_PASSWORD, locale=_LOCALE
    )
    auth_module.get_password_hash.assert_awaited_once_with(
        _NEW_PASSWORD, locale=_LOCALE
    )
    service.user_repo.update.assert_awaited_once_with(
        user_id, {"hashed_password": "new-hash", "mfa_epoch": 4}
    )
    assert len(db.statements) == 2

    revoke.assert_awaited_once()
    assert revoke.await_args.kwargs["db"] is db
    assert revoke.await_args.kwargs["lock_rows"] is True
    whereclause = revoke.await_args.kwargs["whereclause"]
    compiled = whereclause.compile()
    assert str(compiled) == (
        "active_sessions.user_id = :user_id_1 AND active_sessions.revoked_at IS NULL"
    )
    assert compiled.params == {"user_id_1": user_id}

    service.auth_repo.mark_password_reset_token_used.assert_awaited_once_with(7)
    service.auth_repo.invalidate_all_user_password_reset_tokens.assert_awaited_once_with(
        user_id
    )
    service.audit.log.assert_called_once_with(
        "password.reset.completed",
        request,
        user_id=user_id,
        reason="completed",
        extra={"revoked_sessions": 5, "mfa_epoch": 4},
    )


async def test_reset_without_epoch_attribute_starts_from_zero_and_ignores_non_int_revoke(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A user lacking ``mfa_epoch`` rotates to 1; a non-integer revoke count is 0."""

    user_id = uuid.uuid4()
    service = _service()
    record = _record(user_id)
    service.auth_repo.get_valid_password_reset_token = AsyncMock(
        side_effect=[record, record]
    )
    service.user_repo.get = AsyncMock(return_value=_user(user_id))
    service.session_repo.revoke_all_for_user = MagicMock(return_value=None)
    request = _request()

    await service.perform_password_reset("opaque-token", _NEW_PASSWORD, request)

    service.user_repo.update.assert_awaited_once_with(
        user_id, {"hashed_password": "new-hash", "mfa_epoch": 1}
    )
    service.audit.log.assert_called_once_with(
        "password.reset.completed",
        request,
        user_id=user_id,
        reason="completed",
        extra={"revoked_sessions": 0, "mfa_epoch": 1},
    )


async def test_reset_hibp_value_error_is_reported_with_locale_and_reason(
    _reset_environment: list[tuple[str, dict[str, Any]]],
) -> None:
    """A rejected password surfaces a localized 400 that carries the reason."""

    user_id = uuid.uuid4()
    service = _service()
    record = _record(user_id)
    service.auth_repo.get_valid_password_reset_token = AsyncMock(
        side_effect=[record, record]
    )
    service.user_repo.get = AsyncMock(return_value=_user(user_id, mfa_epoch=0))
    service.uow.rollback = AsyncMock()
    security_module.validate_password_hibp.side_effect = ValueError("pwned-password")

    with pytest.raises(HTTPException) as exc:
        await service.perform_password_reset("opaque-token", _NEW_PASSWORD, _request())

    assert exc.value.status_code == 400
    assert _reset_environment == [
        (
            "errors.common.bad_request",
            {"locale": _LOCALE, "reason": "pwned-password"},
        )
    ]
    assert exc.value.detail == translate("errors.common.bad_request", locale=_LOCALE)
    service.user_repo.update.assert_not_awaited()
    service.uow.rollback.assert_called_once_with()


async def _reset_and_capture(service: AuthService) -> HTTPException:
    with pytest.raises(HTTPException) as exc:
        await service.perform_password_reset("opaque-token", _NEW_PASSWORD, _request())
    return exc.value


async def test_reset_unknown_token_is_reported_in_request_locale(
    _reset_environment: list[tuple[str, dict[str, Any]]],
) -> None:
    service = _service()
    service.auth_repo.get_valid_password_reset_token = AsyncMock(return_value=None)

    error = await _reset_and_capture(service)

    assert error.status_code == 400
    assert _reset_environment == [(_EXPIRED_KEY, {"locale": _LOCALE})]
    assert error.detail == translate(_EXPIRED_KEY, locale=_LOCALE)


async def test_reset_token_expired_at_discovery_is_reported_in_request_locale(
    _reset_environment: list[tuple[str, dict[str, Any]]],
) -> None:
    user_id = uuid.uuid4()
    service = _service()
    service.auth_repo.get_valid_password_reset_token = AsyncMock(
        return_value=_record(user_id, expires_in=timedelta(minutes=-1))
    )

    error = await _reset_and_capture(service)

    assert error.status_code == 400
    assert _reset_environment == [(_EXPIRED_KEY, {"locale": _LOCALE})]
    assert error.detail == translate(_EXPIRED_KEY, locale=_LOCALE)


async def test_reset_token_consumed_while_waiting_for_lock_is_reported_in_locale(
    _reset_environment: list[tuple[str, dict[str, Any]]],
) -> None:
    user_id = uuid.uuid4()
    service = _service()
    service.auth_repo.get_valid_password_reset_token = AsyncMock(
        side_effect=[_record(user_id), None]
    )
    service.user_repo.get = AsyncMock(return_value=_user(user_id, mfa_epoch=0))

    error = await _reset_and_capture(service)

    assert error.status_code == 400
    assert _reset_environment == [(_EXPIRED_KEY, {"locale": _LOCALE})]
    assert error.detail == translate(_EXPIRED_KEY, locale=_LOCALE)


async def test_reset_token_expired_while_waiting_for_lock_is_reported_in_locale(
    _reset_environment: list[tuple[str, dict[str, Any]]],
) -> None:
    user_id = uuid.uuid4()
    service = _service()
    service.auth_repo.get_valid_password_reset_token = AsyncMock(
        side_effect=[
            _record(user_id),
            _record(user_id, expires_in=timedelta(minutes=-1)),
        ]
    )
    service.user_repo.get = AsyncMock(return_value=_user(user_id, mfa_epoch=0))

    error = await _reset_and_capture(service)

    assert error.status_code == 400
    assert _reset_environment == [(_EXPIRED_KEY, {"locale": _LOCALE})]
    assert error.detail == translate(_EXPIRED_KEY, locale=_LOCALE)


async def test_initiate_reset_rate_limits_the_canonical_address() -> None:
    """The limiter receives the HMAC bucket of the normalized email and the policy."""

    service = _service()
    service.user_repo.get_by_email = AsyncMock(return_value=None)
    strategy = object()
    limiter = AsyncMock()

    with (
        patch("app.core.ratelimit.enforce_rate_limit", new=limiter),
        patch("app.core.ratelimit.get_default_strategy", return_value=strategy) as pick,
        patch("asyncio.sleep", new=AsyncMock()),
    ):
        await service.initiate_password_reset(
            "  Person@Example.COM ", _request(), BackgroundTasks()
        )

    limiter.assert_awaited_once_with(
        identifier=_password_reset_rate_limit_identifier("person@example.com"),
        limit=3,
        window_seconds=3600,
        strategy=strategy,
    )
    pick.assert_called_once_with("email")
    service.user_repo.get_by_email.assert_awaited_once_with("person@example.com")


def test_rate_limit_identifier_is_a_domain_separated_hmac_of_the_canonical_email(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Pin the exact keyed digest so the bucket is stable across releases."""

    monkeypatch.setattr(auth_module, "_token_hmac_secret", lambda: "sécret")
    expected = hmac.new(
        "sécret".encode(),
        b"password-reset-rate-limit-v1\x1f" + "üser@example.com".encode(),
        hashlib.sha256,
    ).hexdigest()

    assert (
        _password_reset_rate_limit_identifier(" ÜSER@Example.com ")
        == f"password-reset:{expected}"
    )
