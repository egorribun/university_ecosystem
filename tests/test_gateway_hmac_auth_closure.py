"""Security contracts for backend verification of gateway identity proofs."""

from __future__ import annotations

import hashlib
import hmac
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException, status

from app.api.deps import auth as auth_module

_HMAC_SECRET = "backend-hmac-closure-synthetic-secret"  # pragma: allowlist secret -- synthetic HMAC test key


def _independent_gateway_signature(
    secret: str, user_id: str, session_id: str, tenant_id: str = ""
) -> str:
    """Calculate the documented gateway wire format without using gateway code."""
    payload = f"{user_id}:{session_id}"
    if tenant_id:
        payload = f"{payload}:{tenant_id}"
    return hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()


def _gateway_headers(
    user_id: str,
    session_id: str,
    *,
    tenant_id: str = "",
    signature: str | None = None,
) -> dict[str, str]:
    headers = {"X-User-ID": user_id, "X-Session-ID": session_id}
    if tenant_id:
        headers["X-Tenant-ID"] = tenant_id
    if signature is not None:
        headers["X-Internal-Signature"] = signature
    return headers


def _auth_harness(
    monkeypatch: pytest.MonkeyPatch,
    headers: dict[str, str],
    *,
    secret: str,
    environment: str,
) -> SimpleNamespace:
    user_id = UUID(headers["X-User-ID"])
    session_id = headers["X-Session-ID"]
    user = SimpleNamespace(id=user_id, is_active=True, mfa_epoch=0)
    session = SimpleNamespace(
        id=uuid4(),
        user_id=user_id,
        jti=session_id,
        revoked_at=None,
        expires_at=datetime.now(UTC) + timedelta(hours=1),
        user_agent="synthetic-agent",
        ip_address="127.0.0.1",
        accept_language="en",
        fingerprint_hash=None,
        mfa_verified_at=None,
        mfa_epoch=0,
    )

    request = MagicMock()
    request.headers = headers
    request.state = SimpleNamespace()
    db = AsyncMock()
    db.get.side_effect = [user, session]
    redis_service = AsyncMock()
    redis_service.get_session.return_value = {
        "user_id": str(user_id),
        "session_id": str(session.id),
    }
    revocation_client = AsyncMock()
    revocation_client.exists.return_value = False
    revocation_factory = AsyncMock(return_value=revocation_client)

    repository_factory = MagicMock()
    security_service = MagicMock()
    security_service.validate_session_expiry = MagicMock()
    security_service.handle_mfa_ttl = AsyncMock()
    security_service.sync_last_seen = AsyncMock()
    fingerprint_service = MagicMock()
    fingerprint_service.validate_fingerprint = AsyncMock()

    monkeypatch.setattr(auth_module, "resolve_locale", lambda **_kwargs: "en")
    monkeypatch.setattr(auth_module, "get_revocation_redis_client", revocation_factory)
    monkeypatch.setattr(auth_module, "ActiveSessionRepository", repository_factory)
    monkeypatch.setattr(
        auth_module, "AuthSecurityService", MagicMock(return_value=security_service)
    )
    monkeypatch.setattr(
        auth_module,
        "AuthFingerprintService",
        MagicMock(return_value=fingerprint_service),
    )
    monkeypatch.setattr(
        auth_module,
        "settings",
        SimpleNamespace(internal_hmac_secret=secret, environment=environment),
    )

    return SimpleNamespace(
        request=request,
        db=db,
        redis_service=redis_service,
        revocation_client=revocation_client,
        revocation_factory=revocation_factory,
        repository_factory=repository_factory,
        user=user,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "tenant_id",
    ["", str(uuid4())],
    ids=["two-field-proof", "tenant-bound-proof"],
)
async def test_release_accepts_independently_computed_exact_gateway_hmac(
    monkeypatch: pytest.MonkeyPatch, tenant_id: str
) -> None:
    user_id = str(uuid4())
    session_id = "backend-contract-session"
    signature = _independent_gateway_signature(
        _HMAC_SECRET, user_id, session_id, tenant_id
    )
    headers = _gateway_headers(
        user_id,
        session_id,
        tenant_id=tenant_id,
        signature=signature,
    )
    harness = _auth_harness(
        monkeypatch, headers, secret=_HMAC_SECRET, environment="production"
    )

    result = await auth_module._resolve_current_user(
        harness.request, None, harness.db, harness.redis_service
    )

    assert result is harness.user
    harness.revocation_factory.assert_awaited_once()
    harness.redis_service.get_session.assert_awaited_once_with(session_id)
    assert harness.db.get.await_count == 2


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "proof_case",
    [
        "missing signature",
        "forged signature",
        "tampered subject",
        "tampered session",
        "tampered tenant",
        "two-field signature with tenant",
    ],
)
async def test_release_rejects_missing_forged_or_tampered_hmac_before_state_access(
    monkeypatch: pytest.MonkeyPatch, proof_case: str
) -> None:
    user_id = str(uuid4())
    session_id = "release-session-original"
    tenant_id = str(uuid4())
    exact_signature = _independent_gateway_signature(
        _HMAC_SECRET, user_id, session_id, tenant_id
    )
    headers = _gateway_headers(
        user_id, session_id, tenant_id=tenant_id, signature=exact_signature
    )

    if proof_case == "missing signature":
        headers.pop("X-Internal-Signature")
    elif proof_case == "forged signature":
        headers["X-Internal-Signature"] = "synthetic-forged-proof"
    elif proof_case == "tampered subject":
        headers["X-User-ID"] = str(uuid4())
    elif proof_case == "tampered session":
        headers["X-Session-ID"] = "release-session-tampered"
    elif proof_case == "tampered tenant":
        headers["X-Tenant-ID"] = str(uuid4())
    elif proof_case == "two-field signature with tenant":
        headers["X-Internal-Signature"] = _independent_gateway_signature(
            _HMAC_SECRET, user_id, session_id
        )
    else:
        pytest.fail(f"unhandled proof case: {proof_case}")

    harness = _auth_harness(
        monkeypatch, headers, secret=_HMAC_SECRET, environment="production"
    )

    with pytest.raises(HTTPException) as exc_info:
        await auth_module._resolve_current_user(
            harness.request, None, harness.db, harness.redis_service
        )

    assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
    harness.revocation_factory.assert_not_awaited()
    harness.redis_service.get_session.assert_not_awaited()
    harness.db.get.assert_not_awaited()
    harness.repository_factory.assert_not_called()


@pytest.mark.asyncio
async def test_release_rejects_gateway_identity_when_shared_secret_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    headers = _gateway_headers(str(uuid4()), "release-session")
    harness = _auth_harness(monkeypatch, headers, secret="", environment="production")

    with pytest.raises(HTTPException) as exc_info:
        await auth_module._resolve_current_user(
            harness.request, None, harness.db, harness.redis_service
        )

    assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
    harness.revocation_factory.assert_not_awaited()
    harness.redis_service.get_session.assert_not_awaited()
    harness.db.get.assert_not_awaited()


@pytest.mark.asyncio
async def test_development_without_shared_secret_keeps_configured_compatibility(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_id = str(uuid4())
    session_id = "development-session"
    headers = _gateway_headers(user_id, session_id)
    harness = _auth_harness(monkeypatch, headers, secret="", environment="development")

    result = await auth_module._resolve_current_user(
        harness.request, None, harness.db, harness.redis_service
    )

    assert result is harness.user
    harness.revocation_factory.assert_awaited_once()
    harness.redis_service.get_session.assert_awaited_once_with(session_id)
