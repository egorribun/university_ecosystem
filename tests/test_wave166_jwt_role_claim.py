"""W166 SW1 — JWT payload contract tests for `role` claim.

Closes W165 NEW W166+ candidate #1 (admin auth JWT-no-role-claim race on cold-
cache `/admin/*` URL navigation). Asserts that the access_token_v2 JWT issued
by ``SessionService.create_access_token`` carries the ``role`` claim that
``frontend/src/ssrAuth.ts:127`` reads via the SSR auth bridge.

Pre-W166 the claim was missing from backend JWTs (only ``sub``/``aud``/``iat``/
``nbf``/``exp``/``jti``/``is_active`` were embedded; ``is_active`` added in
W136 SW1). ``ssrAuth.ts:127`` `validateJwt` defaulted any cookie-authed cold-
cache request to ``role="student"``, so ``_admin.tsx:34`` beforeLoad's check
``user.role !== "admin"`` redirected admin users to ``/dashboard`` until
async ``/users/me`` settled with the real role — visible as a brief flicker
on direct ``/admin/*`` URL navigation.

W166 SW1 threads ``role`` alongside ``is_active`` from ``LoginSessionManager.
finalize_login`` through ``SessionService.create_access_token`` ``extra_claims``
parameter into ``_mint_jwt``'s payload. ``UserRole`` is a ``StrEnum``
(``app/models/enums.py:4-15``), so ``user.role.value`` returns the canonical
string ("student", "teacher", "admin", "superuser", "anonymous") matching the
shape ssrAuth.ts expects.

Mirrors W136 SW1 ``tests/test_auth_jwt_payload.py`` pattern exactly —
contract tests on the JWT minting chokepoint that decode the produced token
and assert claim shape, plus end-to-end finalize_login tests that exercise
the full Set-Cookie chain.
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

    Mirrors W136 SW1 ``test_auth_jwt_payload.py:_make_session_service``.
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
async def test_create_access_token_with_role_admin_extra_claim(db_session, test_user):
    """extra_claims={'role': 'admin'} → JWT carries role=admin (ssrAuth.ts:127 path)."""
    service = _make_session_service(db_session)

    token, _ = await service.create_access_token(
        sub=test_user.id,
        extra_claims={"role": "admin"},
    )

    decoded = _decode_jwt(token)
    assert "role" in decoded, "role claim must be embedded for SSR auth-at-edge bridge"
    assert decoded["role"] == "admin"

    for claim in ("sub", "aud", "iat", "nbf", "exp", "jti"):
        assert claim in decoded, f"required claim {claim} missing"


@pytest.mark.asyncio
async def test_create_access_token_with_role_student_extra_claim(db_session, test_user):
    """extra_claims={'role': 'student'} → JWT carries role=student (ssrAuth.ts:127 default match)."""
    service = _make_session_service(db_session)

    token, _ = await service.create_access_token(
        sub=test_user.id,
        extra_claims={"role": "student"},
    )

    decoded = _decode_jwt(token)
    assert decoded["role"] == "student"


@pytest.mark.asyncio
async def test_create_access_token_role_alongside_is_active(db_session, test_user):
    """W136 SW1 + W166 SW1: both ``is_active`` and ``role`` claims coexist.

    Verifies that adding the role claim does NOT regress the W136 SW1
    is_active claim — both flow through the same ``extra_claims`` dict and
    ``payload.update(extra)`` at ``session_service.py:211``.
    """
    service = _make_session_service(db_session)

    token, _ = await service.create_access_token(
        sub=test_user.id,
        extra_claims={"is_active": True, "role": "admin"},
    )

    decoded = _decode_jwt(token)
    assert decoded["is_active"] is True
    assert decoded["role"] == "admin"


@pytest.mark.asyncio
async def test_finalize_login_embeds_role_for_admin_user(db_session, user_factory):
    """End-to-end: LoginSessionManager.finalize_login() for admin user → JWT carries role="admin"."""
    from app.services.auth.login_session_manager import LoginSessionManager

    user = await user_factory(role="admin", is_active=True)
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

    assert "role" in decoded
    assert decoded["role"] == "admin"
    # W136 SW1 regression guard: is_active must still be embedded
    assert decoded["is_active"] is True


@pytest.mark.asyncio
async def test_finalize_login_embeds_role_for_student_user(db_session, user_factory):
    """End-to-end: LoginSessionManager.finalize_login() for student user → JWT carries role="student"."""
    from app.services.auth.login_session_manager import LoginSessionManager

    user = await user_factory(role="student", is_active=True)
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

    assert decoded["role"] == "student"


@pytest.mark.asyncio
async def test_finalize_login_role_uses_strenum_canonical_value(
    db_session, user_factory
):
    """``user.role.value`` returns the canonical string, NOT ``UserRole.ADMIN`` repr.

    ``UserRole`` is a ``StrEnum`` (``app/models/enums.py:4``), so ``.value`` on
    ``UserRole.ADMIN`` returns ``"admin"`` (the underlying string value), NOT
    ``"UserRole.ADMIN"`` (the str() representation). This is the shape
    ``ssrAuth.ts:127`` expects.

    Regression guard: if a future refactor swaps StrEnum for a regular Enum
    subclass, the test fails with a value like ``"UserRole.ADMIN"`` that breaks
    ssrAuth.ts string equality.
    """
    from app.services.auth.login_session_manager import LoginSessionManager

    user = await user_factory(role="admin", is_active=True)
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

    # The canonical StrEnum value is the bare role string; NOT the qualified
    # "UserRole.ADMIN" repr. ssrAuth.ts:127 reads ``payload.role`` as plain
    # string equality.
    assert decoded["role"] == "admin"
    assert decoded["role"] != "UserRole.ADMIN"
    assert not decoded["role"].startswith("UserRole")
