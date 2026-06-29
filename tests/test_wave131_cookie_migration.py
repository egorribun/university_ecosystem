"""Wave 131 SW6 — Phase 4 deploy infrastructure cookie SameSite migration.

Tests target the production `app.core.config.security.SecuritySettings`
(NOT the legacy `app.config.security` shadow module which is used only by
``tests/test_config_modules.py``). The production class composes
``CspSettingsMixin`` which carries the ``security_cookie_samesite_override``
field + the migrated ``cookie_samesite`` property.

Pre-W131 behavior: dev returned ``"lax"``, prod returned ``"strict"``.
Strict blocked the access_token_v2 / csrf_token cookies on cross-site GET
(direct link clicks from search engines, email, social media) — defeating
SSR auth-at-edge for the very flow that benefits most from it.

Post-W131: both default to ``"lax"``. ``SECURITY_COOKIE_SAMESITE_OVERRIDE``
env var provides an emergency rollback knob ("strict" / "lax" / "none";
"" or unset = use default).

CSRF compatibility verified by inspection: ``app.core.csrf.CSRFMiddleware``
uses Signed Double-Submit + HMAC-SHA256 + X-CSRF-Token header check. Cross-
site state-change attempts cannot set custom X-CSRF-Token (CORS preflight
blocks), so SameSite=Lax does not open new attack surface.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.config.security import SecuritySettings


class TestWave131CookieSameSiteMigration:
    def test_default_is_lax(self):
        """Default cookie_samesite resolves to 'lax' (was 'strict' for prod pre-W131)."""
        settings = SecuritySettings()
        assert settings.cookie_samesite == "lax"
        assert settings.security_cookie_samesite_override == ""

    def test_override_strict_restores_pre_w131_prod(self, monkeypatch):
        """SECURITY_COOKIE_SAMESITE_OVERRIDE=strict restores pre-W131 prod behavior."""
        monkeypatch.setenv("SECURITY_COOKIE_SAMESITE_OVERRIDE", "strict")
        settings = SecuritySettings()
        assert settings.security_cookie_samesite_override == "strict"
        assert settings.cookie_samesite == "strict"

    def test_override_lax_explicit(self, monkeypatch):
        """Explicit SECURITY_COOKIE_SAMESITE_OVERRIDE=lax matches the new default."""
        monkeypatch.setenv("SECURITY_COOKIE_SAMESITE_OVERRIDE", "lax")
        settings = SecuritySettings()
        assert settings.cookie_samesite == "lax"

    def test_override_none_for_cross_site_embeds(self, monkeypatch):
        """SECURITY_COOKIE_SAMESITE_OVERRIDE=none allowed (e.g. iframe embeds)."""
        monkeypatch.setenv("SECURITY_COOKIE_SAMESITE_OVERRIDE", "none")
        settings = SecuritySettings()
        assert settings.cookie_samesite == "none"

    def test_override_empty_string_falls_through_to_default(self, monkeypatch):
        """Empty SECURITY_COOKIE_SAMESITE_OVERRIDE keeps the default behavior."""
        monkeypatch.setenv("SECURITY_COOKIE_SAMESITE_OVERRIDE", "")
        settings = SecuritySettings()
        assert settings.cookie_samesite == "lax"

    def test_override_case_insensitive(self, monkeypatch):
        """Override value is normalized to lowercase by the validator."""
        monkeypatch.setenv("SECURITY_COOKIE_SAMESITE_OVERRIDE", "STRICT")
        settings = SecuritySettings()
        assert settings.security_cookie_samesite_override == "strict"
        assert settings.cookie_samesite == "strict"

    def test_override_invalid_value_raises(self, monkeypatch):
        """Invalid override raises ValidationError at config-load time (RZ-131-01)."""
        monkeypatch.setenv("SECURITY_COOKIE_SAMESITE_OVERRIDE", "looose")
        with pytest.raises(ValidationError) as exc:
            SecuritySettings()
        assert "SECURITY_COOKIE_SAMESITE_OVERRIDE" in str(exc.value)

    def test_csrf_middleware_cookie_uses_lax_default(self):
        """CSRFMiddleware constructed with the migrated samesite emits lax cookies."""
        from app.core.csrf import CSRFMiddleware

        async def _stub(scope, receive, send):
            return None

        settings = SecuritySettings()
        # Realistic construction — match the call site at
        # `app/core/middleware/setup.py:57`.
        middleware = CSRFMiddleware(
            _stub,
            cookie_secure=settings.cookie_secure,
            cookie_samesite=settings.cookie_samesite,
            csrf_hmac_secret="0" * 32,
        )
        assert middleware._cookie_samesite == "lax"
        # _build_set_cookie_header emits the SameSite attribute correctly.
        header = middleware._build_set_cookie_header("token-value").decode("latin-1")
        assert "SameSite=lax" in header
