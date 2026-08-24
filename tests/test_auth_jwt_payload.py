"""W136 SW1 — JWT payload contract tests for is_active claim.

Closes W135 §Honesty #2 (gateway+backend JWT mismatch). Asserts that the
access_token_v2 JWT issued by SessionService.create_access_token carries the
``is_active`` claim that ``services/gateway/middleware/auth.go:720`` reads.

Pre-W136 the gateway returned 403 "user account is not active" for ALL authed
requests because the claim was missing from backend JWTs (only sub/aud/iat/
nbf/exp/jti were embedded). W136 SW1 threads ``is_active`` from
``LoginSessionManager.finalize_login`` through ``SessionService.create_access_token``
``extra_claims`` parameter into ``_mint_jwt``'s payload.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import jwt as jose_jwt
import pytest
from fastapi import BackgroundTasks, Request, Response

from app.core.config import settings


def _decode_jwt(token: str) -> dict:
    """Decode the JWT using the active signing secret. Skips revocation check."""
    return jose_jwt.decode(
        token,
        settings.jwt_signing_active_secret,
        algorithms=[settings.algorithm],
        audience=settings.jwt_audience,
        options={"require": ["sub", "jti", "exp", "iat", "aud"]},
    )


def _make_session_service(db_session):
    """Construct a SessionService bound to the test DB session.

    Production wiring uses ``async with UnitOfWork(...)`` which calls
    ``_bind_repositories(session)`` in ``__aenter__``. For unit tests we bypass
    the async-with pattern and bind repositories directly so we can construct
    SessionService synchronously.
    """
    from app.repositories.unit_of_work import UnitOfWork
    from app.services.session_service import SessionService

    uow = UnitOfWork(lambda: db_session)
    uow._session = db_session  # type: ignore[assignment]
    uow._bind_repositories(db_session)
    return SessionService(uow)


def _build_test_request(path: str = "/api/v1/auth/login") -> Request:
    """Minimal valid ASGI scope for FastAPI Request."""
    scope = {
        "type": "http",
        "method": "POST",
        "path": path,
        "headers": [(b"user-agent", b"pytest")],
        "query_string": b"",
        "scheme": "http",
        "server": ("testserver", 80),
        "client": ("testclient", 8080),
        "root_path": "",
    }
    return Request(scope)


def _extract_access_token_from_response(response: Response) -> str:
    """Pull access_token_v2 cookie value from response Set-Cookie headers."""
    cookies_set: list[str] = []
    for header_name, header_value in response.raw_headers:
        if header_name.lower() == b"set-cookie":
            cookies_set.append(header_value.decode())

    access_cookie = next(
        (c for c in cookies_set if c.startswith("access_token_v2=")),
        None,
    )
    assert access_cookie is not None, "access_token_v2 cookie not set"
    return access_cookie.split(";")[0].split("=", 1)[1]


@pytest.mark.asyncio
async def test_create_access_token_with_extra_claims_embeds_is_active_true(
    db_session, test_user
):
    """extra_claims={'is_active': True} → JWT carries is_active=True."""
    service = _make_session_service(db_session)

    token, _ = await service.create_access_token(
        sub=test_user.id,
        extra_claims={"is_active": True},
    )

    decoded = _decode_jwt(token)
    assert "is_active" in decoded, "is_active claim must be embedded for gateway"
    assert decoded["is_active"] is True

    for claim in ("sub", "aud", "iat", "nbf", "exp", "jti"):
        assert claim in decoded, f"required claim {claim} missing"


@pytest.mark.asyncio
async def test_create_access_token_with_extra_claims_embeds_is_active_false(
    db_session, test_user
):
    """extra_claims={'is_active': False} → JWT carries is_active=False (gateway 403s)."""
    service = _make_session_service(db_session)

    token, _ = await service.create_access_token(
        sub=test_user.id,
        extra_claims={"is_active": False},
    )

    decoded = _decode_jwt(token)
    assert decoded["is_active"] is False


@pytest.mark.asyncio
async def test_create_access_token_without_extra_claims_omits_is_active(
    db_session, test_user
):
    """Backwards-compat: no extra_claims → JWT lacks is_active.

    Pre-W136 JWTs in flight at deploy time follow this path. Gateway's Go json
    unmarshal defaults missing bool to false → 403 → user re-logs in. Documented
    invalidation behavior under no-deploy scope.
    """
    service = _make_session_service(db_session)

    token, _ = await service.create_access_token(sub=test_user.id)

    decoded = _decode_jwt(token)
    assert "is_active" not in decoded


@pytest.mark.asyncio
async def test_finalize_login_embeds_is_active_for_active_user(
    db_session, user_factory
):
    """Login JWT carries active state but no unresolved tenant scope."""
    from app.services.auth.login_session_manager import LoginSessionManager

    user = await user_factory(is_active=True)
    real_session_service = _make_session_service(db_session)

    mock_redis = AsyncMock()
    mock_redis.create_session = AsyncMock()

    mock_geolocation = MagicMock()
    mock_geolocation.resolve.return_value = MagicMock(
        country=None, city=None, latitude=None, longitude=None
    )

    mock_audit = MagicMock()

    manager = LoginSessionManager(
        session_service=real_session_service,
        redis_session_service=mock_redis,
        geolocation_service=mock_geolocation,
        audit=mock_audit,
    )

    request = _build_test_request()
    response = Response()
    bg_tasks = BackgroundTasks()

    await manager.finalize_login(
        user=user,
        request=request,
        response=response,
        bg_tasks=bg_tasks,
        db_session=db_session,
    )

    token = _extract_access_token_from_response(response)
    decoded = _decode_jwt(token)

    assert "is_active" in decoded
    assert decoded["is_active"] is True
    assert "tenant_id" not in decoded


@pytest.mark.asyncio
async def test_finalize_login_embeds_is_active_false_for_deactivated_user(
    db_session, user_factory
):
    """End-to-end: deactivated user → JWT carries is_active=False (gateway 403s)."""
    from app.services.auth.login_session_manager import LoginSessionManager

    user = await user_factory(is_active=False)
    real_session_service = _make_session_service(db_session)

    mock_redis = AsyncMock()
    mock_redis.create_session = AsyncMock()

    mock_geolocation = MagicMock()
    mock_geolocation.resolve.return_value = MagicMock(
        country=None, city=None, latitude=None, longitude=None
    )

    mock_audit = MagicMock()

    manager = LoginSessionManager(
        session_service=real_session_service,
        redis_session_service=mock_redis,
        geolocation_service=mock_geolocation,
        audit=mock_audit,
    )

    request = _build_test_request()
    response = Response()
    bg_tasks = BackgroundTasks()

    await manager.finalize_login(
        user=user,
        request=request,
        response=response,
        bg_tasks=bg_tasks,
        db_session=db_session,
    )

    token = _extract_access_token_from_response(response)
    decoded = _decode_jwt(token)

    assert decoded["is_active"] is False
