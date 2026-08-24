"""Runtime tests for development config branches and timing error paths.

Targets branches unreachable from a bare ``SecuritySettings`` (which has
no ``is_development`` field):

  * ``CspSettingsMixin._development_connect_overrides`` populated branch +
    ``strict_security_csp`` dev-override path — reachable only via the FULL
    ``Settings`` model. ``ENVIRONMENT=testing`` (set by conftest) is in
    ``_DEVELOPMENT_ENVIRONMENTS``, so a fresh ``Settings()`` has
    ``is_development=True`` without any extra env.
  * ``app.core.fingerprint.store_mfa_challenge_fingerprints`` Redis-error
    graceful-degradation arm.
  * ``app.core.timing.RequestTimingMiddleware`` non-HTTP scope passthrough.

Idiom mirrors the existing config tests: construct a FRESH model per test +
``monkeypatch.setenv``; NEVER mutate the global ``settings`` singleton (mutmut
isolation). Constructing a new ``Settings()`` is fine — it is not the global.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException


class _Client:
    def __init__(self, host: str) -> None:
        self.host = host


class _FakeRequest:
    """Minimal duck-typed Request for the fingerprint helpers (headers dict + client)."""

    def __init__(self, headers: dict[str, str], client: _Client | None = None) -> None:
        self.headers = headers
        self.client = client


# ─────────────────────────────────────────────────────────────────────────────
# CspSettingsMixin — development connect-src overrides (full Settings model)
# ─────────────────────────────────────────────────────────────────────────────
class TestCspDevelopmentConnectOverrides:
    def test_development_connect_overrides_populated(self, monkeypatch):
        # A frontend origin exercises the http→ws derivation loop as well.
        monkeypatch.setenv("FRONTEND_ORIGINS", "https://app.example.com")
        monkeypatch.setenv("FRONTEND_ORIGIN", "")
        monkeypatch.setenv("APP_BASE_URL", "")
        monkeypatch.setenv("WEBAUTHN_ORIGIN", "")
        from app.core.config import Settings

        s = Settings()
        assert s.is_development is True  # conftest ENVIRONMENT=testing ∈ dev set
        overrides = s._development_connect_overrides()
        assert overrides, "dev overrides must be non-empty when is_development"
        # localhost/127.0.0.1 dev hosts + their ws:// variants
        assert any("localhost:5173" in o for o in overrides)
        assert any(o.startswith("ws://") for o in overrides)
        # frontend origin + derived wss:// both present
        assert "https://app.example.com" in overrides
        assert "wss://app.example.com" in overrides

    def test_development_connect_overrides_dedup_against_existing(self, monkeypatch):
        # If a dev host is already in security_connect_src_values it is not re-added.
        monkeypatch.setenv("SECURITY_CONNECT_SRC_EXTRA", "http://localhost:5173")
        from app.core.config import Settings

        s = Settings()
        overrides = s._development_connect_overrides()
        assert overrides.count("http://localhost:5173") == 0

    def test_strict_security_csp_includes_dev_connect_overrides(self):
        from app.core.config import Settings

        s = Settings()
        csp = s.strict_security_csp
        assert isinstance(csp, str)
        assert "connect-src" in csp
        # dev overrides flow into the generated connect-src directive
        assert "localhost:5173" in csp


# ─────────────────────────────────────────────────────────────────────────────
# app.core.fingerprint — store_mfa_challenge_fingerprints graceful degradation
# ─────────────────────────────────────────────────────────────────────────────
class TestStoreMfaFingerprintsRedisError:
    @pytest.mark.asyncio
    async def test_redis_unavailable_degrades_without_raising(self, monkeypatch):
        import app.deps.cache as cache_mod
        from app.core import fingerprint as fp_mod

        async def _raise() -> Any:
            raise ConnectionError("redis down")

        monkeypatch.setattr(cache_mod, "get_cache_client", _raise)
        req = _FakeRequest({"X-Forwarded-For": "1.2.3.4", "user-agent": "UA"})
        # Must return (not raise) — replay protection degrades gracefully.
        await fp_mod.store_mfa_challenge_fingerprints(req, [])

    def test_extract_fingerprint_uses_client_host_without_forwarded(self):
        from app.core.fingerprint import extract_request_fingerprint

        # No X-Forwarded-For → falls back to request.client.host (the other arm
        # of the `if not ip and request.client` branch).
        req = _FakeRequest({"user-agent": "UA"}, client=_Client("9.9.9.9"))
        fp = extract_request_fingerprint(req)
        assert isinstance(fp, str) and len(fp) == 64


# ─────────────────────────────────────────────────────────────────────────────
# app.core.timing — RequestTimingMiddleware non-HTTP scope passthrough
# ─────────────────────────────────────────────────────────────────────────────
class TestTimingMiddlewarePassthrough:
    @pytest.mark.asyncio
    async def test_non_http_scope_delegates_without_timing(self):
        from app.core.timing import RequestTimingMiddleware

        app = AsyncMock()
        mw = RequestTimingMiddleware(app)
        scope = {"type": "lifespan"}
        receive, send = AsyncMock(), AsyncMock()
        await mw(scope, receive, send)
        app.assert_awaited_once_with(scope, receive, send)


# ─────────────────────────────────────────────────────────────────────────────
# AuthFingerprintService — production fingerprint-mismatch revocation path
# ─────────────────────────────────────────────────────────────────────────────
class TestAuthFingerprintServiceRevocation:
    def _build(self, monkeypatch, *, redis_service):
        """Wire a guaranteed fingerprint mismatch in a production environment.

        Patches ``extract_fingerprint`` (current request) + the suspicious-activity
        detector so the mismatch branch fires deterministically without crafting
        real request headers; ENVIRONMENT=production drives the revocation arm.
        """
        import app.services.auth.fingerprint_service as svc

        monkeypatch.setenv("ENVIRONMENT", "production")
        current_fp = SimpleNamespace(
            fingerprint_hash="CURRENT_HASH",  # differs from the stored hash
            accept_language="en-US",
            user_agent="cur-ua",
        )
        monkeypatch.setattr(svc, "extract_fingerprint", lambda _request: current_fp)
        event = SimpleNamespace(to_log_record=lambda: {"suspicious": True})
        detector = SimpleNamespace(check_fingerprint_mismatch=lambda **_kw: event)
        monkeypatch.setattr(svc, "get_suspicious_activity_detector", lambda: detector)

        session = SimpleNamespace(
            fingerprint_hash="STORED_HASH",
            user_agent="stored-ua",
            accept_language="en-US",
            ip_address="1.1.1.1",
            id=uuid.uuid4(),
            jti="jti-1",
            revoked_at=None,
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
        user = SimpleNamespace(id=uuid.uuid4())
        db = AsyncMock()
        service = svc.AuthFingerprintService(request=object(), locale="en")
        return service, user, session, db

    @pytest.mark.asyncio
    async def test_production_mismatch_revokes_commits_and_raises(self, monkeypatch):
        redis_service = AsyncMock()
        service, user, session, db = self._build(
            monkeypatch, redis_service=redis_service
        )

        with pytest.raises(HTTPException) as exc:
            await service.validate_fingerprint(user, session, db, redis_service)

        assert exc.value.status_code == 403
        assert session.revoked_at is not None
        db.commit.assert_awaited_once()
        redis_service.revoke_session.assert_awaited_once_with(
            "jti-1", expires_at=session.expires_at
        )

    @pytest.mark.asyncio
    async def test_production_mismatch_redis_failure_still_raises(self, monkeypatch):
        redis_service = AsyncMock()
        redis_service.revoke_session.side_effect = ConnectionError("redis down")
        service, user, session, db = self._build(
            monkeypatch, redis_service=redis_service
        )

        # Redis revocation is fail-closed and happens before the DB commit. If the
        # durable tombstone cannot be written, roll back instead of exposing a
        # partially committed revocation that other services cannot enforce.
        with pytest.raises(ConnectionError, match="redis down"):
            await service.validate_fingerprint(user, session, db, redis_service)

        assert session.revoked_at is not None
        db.commit.assert_not_awaited()
        db.rollback.assert_awaited_once()
