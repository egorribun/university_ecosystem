"""Behavioral coverage for authentication route boundaries without app bootstrap."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException, status

from app.api.auth import login as login_api
from app.auth.schemas import (
    LoginIn,
    MfaMethodChallengeOut,
    PendingMfaResponse,
)
from app.core.localization import translate


def _original(name: str):
    return getattr(login_api, name).__dishka_orig_func__


def _pending_response() -> PendingMfaResponse:
    return PendingMfaResponse(
        user_id=uuid4(),
        methods=[
            MfaMethodChallengeOut(
                method="totp",
                challenge_token="t" * 32,
                challenge_expires_at=datetime.now(UTC) + timedelta(minutes=5),
            )
        ],
    )


@pytest.mark.asyncio
async def test_login_and_json_commit_only_for_pending_mfa():
    pending = _pending_response()
    login_service = MagicMock()
    login_service.perform_login = AsyncMock(
        side_effect=[pending, "login-token", "token-result", pending]
    )
    db = MagicMock()
    db.commit = AsyncMock()

    result_pending = await _original("login")(
        MagicMock(),
        MagicMock(),
        MagicMock(),
        login_service,
        db,
        True,
        SimpleNamespace(  # pragma: allowlist secret
            username="student@example.com",
            password="password",  # pragma: allowlist secret
        ),
    )
    result_login_token = await _original("login")(
        MagicMock(),
        MagicMock(),
        MagicMock(),
        login_service,
        db,
        False,
        SimpleNamespace(  # pragma: allowlist secret
            username="student@example.com",
            password="password",  # pragma: allowlist secret
        ),
    )
    result_token = await _original("login_json")(
        LoginIn(  # pragma: allowlist secret
            email="student@example.com",
            password="password",  # pragma: allowlist secret
        ),
        MagicMock(),
        MagicMock(),
        MagicMock(),
        login_service,
        db,
    )
    result_json_pending = await _original("login_json")(
        LoginIn(  # pragma: allowlist secret
            email="student@example.com",
            password="password",  # pragma: allowlist secret
        ),
        MagicMock(),
        MagicMock(),
        MagicMock(),
        login_service,
        db,
    )

    assert result_pending is pending
    assert result_login_token == "login-token"
    assert result_token == "token-result"
    assert result_json_pending is pending
    assert db.commit.await_count == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("route_name", ["login", "login_json"])
@pytest.mark.parametrize(
    ("status_code", "message_key", "headers"),
    [
        (
            status.HTTP_401_UNAUTHORIZED,
            "errors.auth.credentials_invalid",
            {"WWW-Authenticate": "Bearer"},
        ),
        (
            status.HTTP_423_LOCKED,
            "errors.auth.account_locked",
            {"Retry-After": "17"},
        ),
    ],
)
async def test_login_rejection_locale_does_not_reveal_account_preferences(
    route_name: str,
    status_code: int,
    message_key: str,
    headers: dict[str, str],
) -> None:
    request = SimpleNamespace(query_params={}, headers={"Accept-Language": "en"})
    login_service = MagicMock()
    login_service.perform_login = AsyncMock(
        side_effect=HTTPException(
            status_code,
            detail=translate(message_key, locale="ru"),
            headers=headers,
        )
    )
    response = MagicMock()
    bg_tasks = MagicMock()
    db = MagicMock()

    invalid_login_marker = uuid4().hex

    with pytest.raises(HTTPException) as caught:
        if route_name == "login":
            await _original("login")(
                response,
                request,
                bg_tasks,
                login_service,
                db,
                False,
                SimpleNamespace(
                    username="student@example.edu",
                    password=f"invalid-{invalid_login_marker}",
                ),
            )
        else:
            await _original("login_json")(
                LoginIn(
                    email="student@example.edu",
                    password=f"invalid-{invalid_login_marker}",
                ),
                response,
                request,
                bg_tasks,
                login_service,
                db,
            )

    assert caught.value.status_code == status_code
    assert caught.value.detail == translate(message_key, locale="en")
    assert caught.value.headers == headers
    login_service.perform_login.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("route_name", ["login", "login_json"])
async def test_login_preserves_non_auth_http_errors(route_name: str) -> None:
    request = SimpleNamespace(query_params={}, headers={"Accept-Language": "en"})
    error = HTTPException(
        status.HTTP_400_BAD_REQUEST,
        detail={"error": "invalid_input"},
        headers={"X-Contract": "preserved"},
    )
    login_service = MagicMock()
    login_service.perform_login = AsyncMock(side_effect=error)
    response = MagicMock()
    bg_tasks = MagicMock()
    db = MagicMock()

    invalid_login_marker = uuid4().hex
    with pytest.raises(HTTPException) as caught:
        if route_name == "login":
            await _original("login")(
                response,
                request,
                bg_tasks,
                login_service,
                db,
                False,
                SimpleNamespace(
                    username="student@example.edu",
                    password=f"invalid-{invalid_login_marker}",
                ),
            )
        else:
            await _original("login_json")(
                LoginIn(
                    email="student@example.edu",
                    password=f"invalid-{invalid_login_marker}",
                ),
                response,
                request,
                bg_tasks,
                login_service,
                db,
            )

    assert caught.value is error


@pytest.mark.asyncio
async def test_csrf_cookie_and_signing_key_routes():
    assert await login_api.get_csrf_cookie() == {"detail": "CSRF cookie set"}

    request = SimpleNamespace(state=SimpleNamespace(active_session=None))
    with pytest.raises(HTTPException) as caught:
        await login_api.get_session_signing_key(request, MagicMock())
    assert caught.value.status_code == status.HTTP_400_BAD_REQUEST

    request.state.active_session = SimpleNamespace(signing_key="key-1")
    result = await login_api.get_session_signing_key(request, MagicMock())
    assert result.signing_key == "key-1"


@pytest.mark.asyncio
async def test_register_returns_success_and_maps_service_errors():
    user = SimpleNamespace(id=uuid4())
    compliance = MagicMock()
    compliance.register_user = AsyncMock(return_value=user)
    db = AsyncMock()
    request = MagicMock()

    result = await _original("register")(
        SimpleNamespace(email="student@example.com"),
        request,
        compliance,
        MagicMock(),
        db,
    )
    assert result == {"status": "ok", "id": user.id}

    compliance.register_user = AsyncMock(side_effect=ValueError("duplicate"))
    with pytest.raises(HTTPException) as caught:
        await _original("register")(
            SimpleNamespace(email="student@example.com"),
            request,
            compliance,
            MagicMock(),
            db,
        )
    assert caught.value.status_code == status.HTTP_400_BAD_REQUEST
    db.rollback.assert_awaited()

    compliance.register_user = AsyncMock(side_effect=RuntimeError("backend"))
    with (
        patch.object(login_api, "resolve_locale", return_value="en"),
        patch.object(login_api, "translate", return_value="create failed"),
    ):
        with pytest.raises(HTTPException) as caught:
            await _original("register")(
                SimpleNamespace(email="student@example.com"),
                request,
                compliance,
                MagicMock(),
                db,
            )
    assert caught.value.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.asyncio
async def test_concurrent_failed_attempts_serialize_lockout_threshold() -> None:
    """Concurrent bad credentials must not lose attempts or double-trigger a threshold."""
    import asyncio

    from app.services.auth.lockout import LockoutService

    email = "failed-login@example.test"
    committed_attempts: list[SimpleNamespace] = []
    advisory_lock = asyncio.Lock()

    class FakeSession:
        def __init__(self) -> None:
            self.pending_attempts: list[SimpleNamespace] = []

        async def execute(self, statement: object, _parameters: object = None) -> None:
            assert "pg_advisory_xact_lock" in str(statement)
            await advisory_lock.acquire()

        async def flush(self) -> None:
            # Let the competing coroutine reach the transaction lock while this
            # attempt remains invisible in its transaction.
            await asyncio.sleep(0)

        async def commit(self) -> None:
            committed_attempts.extend(self.pending_attempts)
            self.pending_attempts.clear()
            advisory_lock.release()

    class FakeRepository:
        def __init__(self, session: FakeSession) -> None:
            self.session = session

        async def create_failed_attempt(
            self, *, email: str, user_id: object | None
        ) -> SimpleNamespace:
            attempt = SimpleNamespace(
                email=email,
                user_id=user_id,
                attempted_at=datetime.now(UTC),
            )
            self.session.pending_attempts.append(attempt)
            return attempt

    async def run_failed_attempt() -> tuple[datetime | None, bool, int]:
        session = FakeSession()
        service = LockoutService(session)  # type: ignore[arg-type]
        service._is_postgresql = True
        service._lockout_rules = lambda: [(2, 60)]  # type: ignore[method-assign]
        service._max_lockout_threshold = lambda: 2  # type: ignore[method-assign]
        service._prune_stale_attempts = AsyncMock()  # type: ignore[method-assign]
        service.repo = FakeRepository(session)  # type: ignore[assignment]

        async def fetch_recent_attempts(
            requested_email: str, limit: int, *, for_update: bool = False
        ) -> list[SimpleNamespace]:
            del for_update
            rows = [row for row in committed_attempts if row.email == requested_email]
            return sorted(rows, key=lambda row: row.attempted_at, reverse=True)[:limit][
                ::-1
            ]

        service._fetch_recent_attempts = fetch_recent_attempts  # type: ignore[method-assign]
        return await service.register_failed_attempt(email, None)

    outcomes = await asyncio.gather(run_failed_attempt(), run_failed_attempt())

    assert len(committed_attempts) == 2
    assert sorted(outcome[2] for outcome in outcomes) == [1, 2]
    assert sorted(outcome[1] for outcome in outcomes) == [False, True]


def test_lockout_database_dialect_detection_uses_url_driver(monkeypatch) -> None:
    from app.core.config import settings
    from app.services.auth.lockout import LockoutService

    monkeypatch.setattr(settings, "database_url", "sqlite+aiosqlite:///asyncpg.db")
    sqlite_service = LockoutService(MagicMock())
    assert sqlite_service._is_postgresql is False

    monkeypatch.setattr(settings, "database_url", "postgresql+asyncpg://localhost/test")
    postgres_service = LockoutService(MagicMock())
    assert postgres_service._is_postgresql is True
