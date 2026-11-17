"""Cached session primary keys must remain hints bound to signed user/JTI."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException
from redis.exceptions import ConnectionError as RedisConnectionError

from app.api.deps import auth
from app.models import ActiveSession


def _session(user_id, jti):
    return ActiveSession(
        id=uuid4(),
        user_id=user_id,
        jti=jti,
        revoked_at=None,
        expires_at=datetime.now(UTC) + timedelta(hours=1),
        mfa_epoch=0,
    )


def _harness(monkeypatch):
    user = SimpleNamespace(id=uuid4(), is_active=True, mfa_epoch=0)
    jti = "signed-session"
    session = _session(user.id, jti)
    request = MagicMock()
    request.headers = {}
    request.state = SimpleNamespace()
    db = AsyncMock()
    cache = AsyncMock()
    cache.get_session.return_value = {
        "user_id": str(user.id),
        "session_id": str(session.id),
    }
    revocations = AsyncMock()
    revocations.exists.return_value = False
    security = MagicMock()
    security.handle_mfa_ttl = AsyncMock()
    security.sync_last_seen = AsyncMock()
    fingerprint = MagicMock()
    fingerprint.validate_fingerprint = AsyncMock()
    monkeypatch.setattr(auth, "resolve_locale", lambda **kwargs: "en")
    monkeypatch.setattr(auth, "settings", SimpleNamespace(mvp_tenant_id=None))
    monkeypatch.setattr(
        auth.AuthTokenService,
        "extract_and_decode_token",
        lambda *args: {"sub": str(user.id), "jti": jti},
    )
    monkeypatch.setattr(
        auth.AuthTokenService, "validate_payload", lambda *args: (user.id, jti)
    )
    monkeypatch.setattr(
        auth, "get_revocation_redis_client", AsyncMock(return_value=revocations)
    )
    monkeypatch.setattr(auth, "AuthSecurityService", lambda *args: security)
    monkeypatch.setattr(auth, "AuthFingerprintService", lambda *args: fingerprint)
    return SimpleNamespace(
        user=user,
        jti=jti,
        session=session,
        request=request,
        db=db,
        cache=cache,
        revocations=revocations,
        security=security,
        fingerprint=fingerprint,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("cached", ["other-user", "other-jti", "revoked", "missing"])
@pytest.mark.parametrize("authoritative", ["active", "revoked", "missing"])
async def test_cached_pk_requires_matching_authoritative_identity(
    monkeypatch, cached, authoritative
):
    h = _harness(monkeypatch)
    candidate = _session(h.user.id, h.jti)
    if cached == "other-user":
        candidate.user_id = uuid4()
    elif cached == "other-jti":
        candidate.jti = "unrelated-session"
    elif cached == "revoked":
        candidate.revoked_at = datetime.now(UTC)
    else:
        candidate = None
    h.db.get.side_effect = [h.user, candidate]
    fallback = h.session
    if authoritative == "revoked":
        fallback.revoked_at = datetime.now(UTC)
    elif authoritative == "missing":
        fallback = None
    result = MagicMock()
    result.scalars.return_value.first.return_value = fallback
    h.db.execute.return_value = result

    if authoritative == "active":
        resolved = await auth._resolve_current_user(h.request, "token", h.db, h.cache)
        assert resolved is h.user
        assert h.request.state.active_session is h.session
        h.security.validate_session_expiry.assert_called_once_with(h.session)
        h.fingerprint.validate_fingerprint.assert_awaited_once_with(
            h.user, h.session, h.db, h.cache
        )
    else:
        with pytest.raises(HTTPException) as denied:
            await auth._resolve_current_user(h.request, "token", h.db, h.cache)
        assert denied.value.status_code == 401
        assert not hasattr(h.request.state, "active_session")
        h.security.validate_session_expiry.assert_not_called()
        h.fingerprint.validate_fingerprint.assert_not_awaited()

    h.db.execute.assert_awaited_once()
    statement = h.db.execute.await_args.args[0]
    compiled = statement.compile()
    assert "active_sessions.user_id =" in str(compiled)
    assert "active_sessions.jti =" in str(compiled)
    assert h.user.id in compiled.params.values()
    assert h.jti in compiled.params.values()


@pytest.mark.asyncio
async def test_matching_cached_pk_keeps_fast_path(monkeypatch):
    h = _harness(monkeypatch)
    h.db.get.side_effect = [h.user, h.session]

    assert await auth._resolve_current_user(h.request, "token", h.db, h.cache) is h.user

    assert h.request.state.active_session is h.session
    h.db.execute.assert_not_awaited()
    h.security.validate_session_expiry.assert_called_once_with(h.session)


@pytest.mark.asyncio
@pytest.mark.parametrize("unavailable", [False, True])
async def test_revocation_authority_precedes_cached_pk(monkeypatch, unavailable):
    h = _harness(monkeypatch)
    if unavailable:
        h.revocations.exists.side_effect = RedisConnectionError("unavailable")
    else:
        h.revocations.exists.return_value = True

    with pytest.raises(HTTPException) as denied:
        await auth._resolve_current_user(h.request, "token", h.db, h.cache)

    assert denied.value.status_code == (503 if unavailable else 401)
    h.cache.get_session.assert_not_awaited()
    h.db.get.assert_not_awaited()
    h.db.execute.assert_not_awaited()
