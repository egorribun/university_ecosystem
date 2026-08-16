"""Session-11 — config-mixin validator/property coverage.

Targets the UNtested validators + cached_property/property accessors of the five
Pydantic config mixins composed by ``app.core.config.security.SecuritySettings``:
``JwtSettingsMixin``, ``CspSettingsMixin``, ``CorsSettingsMixin``,
``MfaSettingsMixin``, ``RateLimitSettingsMixin``.

Idiom (mirrors ``tests/test_wave131_cookie_migration.py``): instantiate a FRESH
``SecuritySettings()`` per test + ``monkeypatch.setenv``. NEVER mutate the global
``settings`` singleton or any class descriptor — that is the mutmut-isolation
landmine (mutmut forks per-mutant and shared module/class state corrupts the run).

ENVIRONMENT NOTE: ``tests/conftest.py`` sets OS env at import — ``ENVIRONMENT=testing``,
``SECRET_KEY=<32-char>``, ``ALGORITHM=HS256``, ``RATE_LIMIT_STORAGE_BACKEND=memory``…
OS env overrides ``.env`` in pydantic-settings, so default-branch tests run under a
DEV environment (production guards bypassed). Production-branch tests use the
``prod_env`` fixture which sets ``ENVIRONMENT=production`` PLUS neutralizes the
unrelated prod-only validators (``AUDIT_LOG_SECRET`` / ``SECRET_KEY`` /
``INTERNAL_HMAC_SECRET`` / ``ALGORITHM``) so ONLY the validator under test can raise.

``SecuritySettings`` inherits ``BaseAppSettings`` directly (NOT ``AppGeneralSettings``),
so it has NO ``environment`` / ``is_development`` field. The CSP/CORS mixins key off
``getattr(self, "is_development", False)`` → False, so on a bare ``SecuritySettings()``
``strict_security_headers_enabled`` is True (the non-dev branch) — asserted explicitly.

Two branches are intentionally NOT covered here (honest scope — they are unreachable
from ``SecuritySettings``):
  * ``CorsSettingsMixin.cors_allow_credentials_effective`` strict-mode per-origin
    https loop (shadowed — ``cors_allow_origins_list`` already filters non-https
    non-local origins before that loop runs).
  * ``CspSettingsMixin._development_connect_overrides`` populated branch (requires
    ``is_development=True``, only present on the full ``Settings`` model).
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.config.security import SecuritySettings


@pytest.fixture
def prod_env(monkeypatch):
    """Production environment with all UNRELATED prod-only validators neutralized,
    so a single prod-branch test can isolate one validator's raise.

    Individual tests override ONE of these (last-write-wins on ``monkeypatch.setenv``)
    to drive the specific prod validator under test (e.g. a SHORT ``SECRET_KEY`` or
    an ``HS256`` ``ALGORITHM``).
    """
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("AUDIT_LOG_SECRET", "a" * 32)  # pragma: allowlist secret
    monkeypatch.setenv("SECRET_KEY", "p" * 48)  # pragma: allowlist secret
    monkeypatch.setenv("INTERNAL_HMAC_SECRET", "i" * 48)  # pragma: allowlist secret
    monkeypatch.setenv("ALGORITHM", "RS256")
    monkeypatch.setenv("JWT_PRIVATE_KEY_PATH", "")
    return monkeypatch


# ─────────────────────────────────────────────────────────────────────────────
# JwtSettingsMixin
# ─────────────────────────────────────────────────────────────────────────────
class TestJwtSettingsMixin:
    # ── secret_key file loading (J1) ──────────────────────────────────────
    def test_secret_key_file_env_reads_file(self, tmp_path, monkeypatch):
        key_file = tmp_path / "secret_key"
        expected = (
            "file-loaded-secret-key-32-chars-minimum-xx"  # pragma: allowlist secret
        )
        key_file.write_text(expected, encoding="utf-8")
        monkeypatch.setenv("SECRET_KEY_FILE", str(key_file))
        s = SecuritySettings()
        assert s.secret_key == expected

    def test_secret_key_file_nonreadable_raises(self, tmp_path, monkeypatch):
        monkeypatch.setenv("SECRET_KEY_FILE", str(tmp_path / "does-not-exist"))
        with pytest.raises(ValidationError) as exc:
            SecuritySettings()
        assert "SECRET_KEY_FILE" in str(exc.value)
        assert "non-readable file" in str(exc.value)

    # ── secret_key entropy (J2, J3, J4) ───────────────────────────────────
    def test_secret_key_empty_raises(self, monkeypatch):
        monkeypatch.setenv("SECRET_KEY", "")
        with pytest.raises(ValidationError) as exc:
            SecuritySettings()
        assert "SECRET_KEY must not be empty" in str(exc.value)

    def test_secret_key_short_in_production_raises(self, prod_env):
        prod_env.setenv("SECRET_KEY", "tooshort")  # pragma: allowlist secret
        with pytest.raises(ValidationError) as exc:
            SecuritySettings()
        assert "SECRET_KEY must be at least 32 characters long in production" in str(
            exc.value
        )

    def test_secret_key_short_in_dev_allowed(self, monkeypatch):
        # conftest ENVIRONMENT=testing → dev branch; short key allowed
        monkeypatch.setenv("SECRET_KEY", "shortdevkey")  # pragma: allowlist secret
        s = SecuritySettings()
        assert s.secret_key == "shortdevkey"  # pragma: allowlist secret

    # ── jwt_signing_keys entropy (J5, J6, J7) ─────────────────────────────
    def test_jwt_signing_keys_short_hmac_in_prod_raises(self, prod_env):
        prod_env.setenv("JWT_SIGNING_KEYS", "kid1:short")  # pragma: allowlist secret
        with pytest.raises(ValidationError) as exc:
            SecuritySettings()
        assert (
            "JWT_SIGNING_KEYS entries must be at least 32 characters long in production"
            in str(exc.value)
        )

    def test_jwt_signing_keys_pem_block_exempt_in_prod(self, prod_env):
        prod_env.setenv(
            "JWT_SIGNING_KEYS",
            "kid1:-----BEGIN PRIVATE KEY-----",  # pragma: allowlist secret
        )
        # PEM blocks are exempt from the 32-char entropy rule → construction succeeds.
        s = SecuritySettings()
        assert "kid1" in str(s.jwt_signing_keys)

    def test_jwt_signing_keys_empty_returns_unchanged(self, monkeypatch):
        monkeypatch.setenv("JWT_SIGNING_KEYS", "")
        s = SecuritySettings()
        assert s.jwt_signing_keys == ""

    # ── algorithm (J8, J9, J10, J17) ──────────────────────────────────────
    def test_algorithm_hs256_in_prod_raises(self, prod_env):
        prod_env.setenv("ALGORITHM", "HS256")
        with pytest.raises(ValidationError) as exc:
            SecuritySettings()
        assert "HS256 is prohibited in non-local environments" in str(exc.value)

    def test_algorithm_hs256_in_dev_allowed_and_uppercased(self, monkeypatch):
        monkeypatch.setenv("ENVIRONMENT", "development")
        monkeypatch.setenv("ALGORITHM", "hs256")
        with pytest.warns(UserWarning, match="HS256 is not recommended"):
            s = SecuritySettings()
        assert s.algorithm == "HS256"  # validate_jwt_algorithm uppercases
        assert s.ALGORITHM == "HS256"  # cached_property delegates (J17)

    def test_algorithm_rs256_passthrough_uppercase(self, monkeypatch):
        monkeypatch.setenv("ALGORITHM", "rs256")
        s = SecuritySettings()
        assert s.algorithm == "RS256"

    # ── jwt_audience (J11, J12) ───────────────────────────────────────────
    def test_jwt_audience_empty_raises(self, monkeypatch):
        monkeypatch.setenv("JWT_AUDIENCE", "   ")
        with pytest.raises(ValidationError) as exc:
            SecuritySettings()
        assert "JWT_AUDIENCE must not be empty" in str(exc.value)

    def test_jwt_audience_default_and_strip(self, monkeypatch):
        s = SecuritySettings()
        assert s.jwt_audience == "university-ecosystem-api"
        monkeypatch.setenv("JWT_AUDIENCE", "  custom-aud  ")
        s2 = SecuritySettings()
        assert s2.jwt_audience == "custom-aud"

    # ── signing key registry / active kid / active secret (J13, J15, J16) ─
    def test_signing_key_registry_multi_key_parse_and_cache(self, monkeypatch):
        monkeypatch.setenv(
            "JWT_SIGNING_KEYS",
            "k1:secret-one-32-characters-padding-xxx,"  # pragma: allowlist secret
            "k2:secret-two-32-characters-padding-x",  # pragma: allowlist secret
        )
        monkeypatch.setenv("JWT_ACTIVE_KID", "k2")
        s = SecuritySettings()
        reg = s.jwt_signing_key_registry
        assert reg == {
            "k1": "secret-one-32-characters-padding-xxx",  # pragma: allowlist secret
            "k2": "secret-two-32-characters-padding-x",  # pragma: allowlist secret
        }
        # value-keyed cache: second access returns the SAME object
        assert s.jwt_signing_key_registry is reg
        assert "_jwt_registry_cache" in s.__dict__
        assert s.jwt_signing_active_kid == "k2"
        assert (
            s.jwt_signing_active_secret
            == "secret-two-32-characters-padding-x"  # pragma: allowlist secret
        )

    def test_signing_key_registry_fallback_to_secret_key(self, monkeypatch):
        # No JWT_SIGNING_KEYS; HS256 (conftest) + no RS256 key path → fallback to secret_key.
        monkeypatch.setenv("JWT_SIGNING_KEYS", "")
        monkeypatch.setenv("JWT_PRIVATE_KEY_PATH", "")  # forces the else-branch
        s = SecuritySettings()
        reg = s.jwt_signing_key_registry
        assert list(reg.keys()) == ["primary"]
        assert reg["primary"] == s.secret_key
        assert s.jwt_signing_active_kid == "primary"
        # SECRET_KEY cached_property delegates to the active secret (J17 secret half)
        assert s.SECRET_KEY == s.jwt_signing_active_secret == s.secret_key

    def test_active_kid_mismatch_raises(self, monkeypatch):
        monkeypatch.setenv(
            "JWT_SIGNING_KEYS",
            "k1:secret-one-32-characters-padding-xxx",  # pragma: allowlist secret
        )
        monkeypatch.setenv("JWT_ACTIVE_KID", "nonexistent")
        s = SecuritySettings()
        with pytest.raises(RuntimeError) as exc:
            _ = s.jwt_signing_active_kid
        assert (
            "JWT_ACTIVE_KID must match one of the configured JWT_SIGNING_KEYS"
            in str(exc.value)
        )

    # ── _build_jwt_signing_key_entries malformed (J14, lazy RuntimeError) ──
    @pytest.mark.parametrize(
        ("value", "substr"),
        [
            ("badkeynocolon", "must be in '<kid>:<secret>' format"),
            (
                ":secretonly",
                "must specify a non-empty kid value",
            ),  # pragma: allowlist secret
            (
                "kid1:",
                "must specify a non-empty secret value",
            ),  # pragma: allowlist secret
            (
                "dup:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa,"  # pragma: allowlist secret
                "dup:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",  # pragma: allowlist secret
                "must use unique kid values",
            ),
        ],
    )
    def test_signing_keys_malformed_raises_runtimeerror(
        self, value, substr, monkeypatch
    ):
        # Run in default (testing) env: the entropy validator skips non-':' entries
        # and accepts ':' entries, so construction succeeds; the RuntimeError fires
        # lazily at registry access (_build_jwt_signing_key_entries).
        monkeypatch.setenv("JWT_SIGNING_KEYS", value)
        s = SecuritySettings()
        with pytest.raises(RuntimeError) as exc:
            _ = s.jwt_signing_key_registry
        assert substr in str(exc.value)


# ─────────────────────────────────────────────────────────────────────────────
# CspSettingsMixin (UNtested half only — cookie_samesite covered by test_wave131)
# ─────────────────────────────────────────────────────────────────────────────
class TestCspSettingsMixin:
    def test_coep_value_valid_normalized(self, monkeypatch):
        monkeypatch.setenv("COEP_VALUE", "  CREDENTIALLESS  ")
        s = SecuritySettings()
        assert s.coep_value == "credentialless"
        assert s.coep_header_value == "credentialless"

    def test_coep_value_invalid_raises(self, monkeypatch):
        monkeypatch.setenv("COEP_VALUE", "bogus")
        with pytest.raises(ValidationError) as exc:
            SecuritySettings()
        assert "COEP_VALUE must be either 'require-corp' or 'credentialless'" in str(
            exc.value
        )

    def test_corp_value_valid_normalized(self, monkeypatch):
        monkeypatch.setenv("CORP_VALUE", "Cross-Origin")
        s = SecuritySettings()
        assert s.corp_value == "cross-origin"
        assert s.corp_header_value == "cross-origin"

    def test_corp_value_invalid_raises(self, monkeypatch):
        monkeypatch.setenv("CORP_VALUE", "nope")
        with pytest.raises(ValidationError) as exc:
            SecuritySettings()
        assert (
            "CORP_VALUE must be one of 'same-origin', 'same-site', or 'cross-origin'"
            in str(exc.value)
        )

    def test_strict_security_headers_default_true_without_is_development(self):
        # SecuritySettings has no is_development → getattr(..., False)=False → not False = True
        s = SecuritySettings()
        assert s.strict_security_headers_enabled is True
        assert s.cookie_secure is True
        assert s.security_csp_report_only_effective is False
        assert s.should_inject_csp_nonce is True

    def test_strict_security_headers_explicit_false(self, monkeypatch):
        monkeypatch.setenv("ENABLE_STRICT_SECURITY_HEADERS", "false")
        s = SecuritySettings()
        assert s.strict_security_headers_enabled is False
        assert s.cookie_secure is False
        # report_only_effective = not strict = True (inferred branch)
        assert s.security_csp_report_only_effective is True
        assert s.should_inject_csp_nonce is False  # report_only True → return False

    def test_csp_report_only_effective_explicit(self, monkeypatch):
        monkeypatch.setenv("SECURITY_CSP_REPORT_ONLY", "true")
        s = SecuritySettings()
        assert s.security_csp_report_only_effective is True

    def test_coep_corp_enabled_flags(self, monkeypatch):
        monkeypatch.setenv("ENABLE_COEP", "true")
        monkeypatch.setenv("ENABLE_CORP", "false")
        s = SecuritySettings()
        assert s.coep_enabled is True
        assert s.corp_enabled is False

    def test_connect_src_values_dedup_and_self_prepend(self, monkeypatch):
        monkeypatch.setenv(
            "SECURITY_CONNECT_SRC_EXTRA",
            "https://api.spotify.com,https://api.spotify.com,'self'",
        )
        s = SecuritySettings()
        vals = s.security_connect_src_values
        assert vals[0] == "'self'"
        # dedup: spotify appears once; 'self' appears once even though re-listed
        assert vals.count("https://api.spotify.com") == 1
        assert vals.count("'self'") == 1

    def test_development_connect_overrides_empty_without_is_development(self):
        s = SecuritySettings()
        assert s._development_connect_overrides() == []


# ─────────────────────────────────────────────────────────────────────────────
# CorsSettingsMixin
# ─────────────────────────────────────────────────────────────────────────────
class TestCorsSettingsMixin:
    def test_frontend_origins_list_dedup_and_rstrip(self, monkeypatch):
        monkeypatch.setenv(
            "FRONTEND_ORIGINS", "https://a.com/,https://a.com,https://b.com"
        )
        monkeypatch.setenv("FRONTEND_ORIGIN", "")
        monkeypatch.setenv("APP_BASE_URL", "")
        monkeypatch.setenv("WEBAUTHN_ORIGIN", "")
        s = SecuritySettings()
        assert s.frontend_origins_list == ["https://a.com", "https://b.com"]

    def test_frontend_origins_no_localhost_autoadd_without_is_development(
        self, monkeypatch
    ):
        monkeypatch.setenv("FRONTEND_ORIGINS", "https://prod.com")
        monkeypatch.setenv("FRONTEND_ORIGIN", "")
        monkeypatch.setenv("APP_BASE_URL", "")
        monkeypatch.setenv("WEBAUTHN_ORIGIN", "")
        s = SecuritySettings()
        assert "http://localhost:5173" not in s.frontend_origins_list

    def test_cors_allow_origins_https_filter_excludes_nonlocal_http(self, monkeypatch):
        # strict_security_headers_enabled defaults True → https-only filter active
        monkeypatch.setenv("FRONTEND_ORIGINS", "http://evil.com")
        monkeypatch.setenv("FRONTEND_ORIGIN", "")
        monkeypatch.setenv("APP_BASE_URL", "")
        monkeypatch.setenv("WEBAUTHN_ORIGIN", "")
        s = SecuritySettings()
        assert "http://evil.com" not in s.cors_allow_origins_list

    def test_cors_allow_origins_keeps_localhost_http(self, monkeypatch):
        monkeypatch.setenv("FRONTEND_ORIGINS", "http://localhost:5173")
        monkeypatch.setenv("FRONTEND_ORIGIN", "")
        monkeypatch.setenv("APP_BASE_URL", "")
        monkeypatch.setenv("WEBAUTHN_ORIGIN", "")
        s = SecuritySettings()
        assert "http://localhost:5173" in s.cors_allow_origins_list

    def test_cors_credentials_effective_false_when_disabled(self, monkeypatch):
        monkeypatch.setenv("CORS_ALLOW_CREDENTIALS", "false")
        s = SecuritySettings()
        assert s.cors_allow_credentials_effective is False

    def test_cors_credentials_effective_false_when_no_origins(self, monkeypatch):
        monkeypatch.setenv("FRONTEND_ORIGINS", "")
        monkeypatch.setenv("FRONTEND_ORIGIN", "")
        monkeypatch.setenv("APP_BASE_URL", "")
        monkeypatch.setenv("WEBAUTHN_ORIGIN", "")
        s = SecuritySettings()
        assert s.cors_allow_origins_list == []
        assert s.cors_allow_credentials_effective is False

    def test_cors_credentials_effective_true_happy(self, monkeypatch):
        monkeypatch.setenv("FRONTEND_ORIGINS", "https://prod.com")
        monkeypatch.setenv("FRONTEND_ORIGIN", "")
        monkeypatch.setenv("APP_BASE_URL", "")
        monkeypatch.setenv("WEBAUTHN_ORIGIN", "")
        s = SecuritySettings()
        assert s.cors_allow_credentials_effective is True

    def test_trusted_hosts_list_str_and_list(self, monkeypatch):
        monkeypatch.setenv("TRUSTED_HOSTS", "a.com, b.com ,")
        s = SecuritySettings()
        assert s.trusted_hosts_list == ["a.com", "b.com"]

    def test_allowed_hosts_empty_no_dev_defaults(self, monkeypatch):
        monkeypatch.setenv("ALLOWED_HOSTS", "")
        s = SecuritySettings()  # no is_development → result stays []
        assert s.allowed_hosts_list == []

    def test_allowed_vs_trusted_hosts_are_distinct(self, monkeypatch):
        # Middleware reads allowed_hosts_list, NOT trusted_hosts_list (CLAUDE.md gotcha).
        monkeypatch.setenv("TRUSTED_HOSTS", "trusted.example")
        monkeypatch.setenv("ALLOWED_HOSTS", "allowed.example")
        s = SecuritySettings()
        assert s.trusted_hosts_list == ["trusted.example"]
        assert s.allowed_hosts_list == ["allowed.example"]
        assert s.allowed_hosts_list != s.trusted_hosts_list

    def test_internal_allowed_ips_list(self, monkeypatch):
        monkeypatch.setenv("INTERNAL_ALLOWED_IPS", "10.0.0.1, 10.0.0.2 ,")
        s = SecuritySettings()
        assert s.internal_allowed_ips_list == ["10.0.0.1", "10.0.0.2"]

    def test_cors_methods_custom_and_default(self, monkeypatch):
        monkeypatch.setenv("CORS_ALLOW_METHODS", "GET,POST")
        s = SecuritySettings()
        assert s.cors_allow_methods_list == ["GET", "POST"]
        monkeypatch.setenv("CORS_ALLOW_METHODS", "")
        s2 = SecuritySettings()
        assert s2.cors_allow_methods_list == [
            "GET",
            "POST",
            "PUT",
            "PATCH",
            "DELETE",
            "OPTIONS",
        ]

    def test_cors_headers_custom_and_default(self, monkeypatch):
        monkeypatch.setenv("CORS_ALLOW_HEADERS", "X-Custom")
        s = SecuritySettings()
        assert s.cors_allow_headers_list == ["X-Custom"]
        monkeypatch.setenv("CORS_ALLOW_HEADERS", "")
        s2 = SecuritySettings()
        assert s2.cors_allow_headers_list == ["Authorization", "Content-Type"]

    def test_cors_expose_headers_appends_request_and_trace(self, monkeypatch):
        monkeypatch.setenv("CORS_EXPOSE_HEADERS", "X-Foo")
        monkeypatch.setenv("REQUEST_ID_HEADER", "x-request-id")
        monkeypatch.setenv("TRACE_HEADER", "x-trace-id")
        s = SecuritySettings()
        exposed = s.cors_expose_headers_list
        assert "X-Foo" in exposed
        assert "x-request-id" in exposed
        assert "x-trace-id" in exposed

    def test_trusted_proxies_list(self, monkeypatch):
        monkeypatch.setenv("TRUSTED_PROXIES", "10.0.0.0/8, 192.168.0.0/16")
        s = SecuritySettings()
        assert s.trusted_proxies_list == ["10.0.0.0/8", "192.168.0.0/16"]


# ─────────────────────────────────────────────────────────────────────────────
# MfaSettingsMixin (env-independent validators — run in default env)
# ─────────────────────────────────────────────────────────────────────────────
class TestMfaSettingsMixin:
    def test_totp_issuer_empty_raises(self, monkeypatch):
        monkeypatch.setenv("MFA_TOTP_ISSUER", "   ")
        with pytest.raises(ValidationError) as exc:
            SecuritySettings()
        assert "MFA_TOTP_ISSUER must not be empty" in str(exc.value)

    def test_totp_issuer_valid(self, monkeypatch):
        monkeypatch.setenv("MFA_TOTP_ISSUER", "  My University  ")
        s = SecuritySettings()
        assert s.mfa_totp_issuer == "My University"

    @pytest.mark.parametrize(
        ("env_name", "msg"),
        [
            (
                "MFA_CHALLENGE_TTL_SECONDS",
                "MFA_CHALLENGE_TTL_SECONDS must be greater than zero",
            ),
            (
                "MFA_CHALLENGE_MAX_ATTEMPTS",
                "MFA_CHALLENGE_MAX_ATTEMPTS must be greater than zero",
            ),
            (
                "MFA_STEP_UP_TTL_SECONDS",
                "MFA_STEP_UP_TTL_SECONDS must be greater than zero",
            ),
        ],
    )
    def test_positive_mfa_values_zero_raises(self, env_name, msg, monkeypatch):
        monkeypatch.setenv(env_name, "0")
        with pytest.raises(ValidationError) as exc:
            SecuritySettings()
        assert msg in str(exc.value)

    def test_password_min_length_zero_raises(self, monkeypatch):
        monkeypatch.setenv("PASSWORD_MIN_LENGTH", "0")
        with pytest.raises(ValidationError) as exc:
            SecuritySettings()
        assert "PASSWORD_MIN_LENGTH must be greater than zero" in str(exc.value)

    def test_password_max_less_than_min_raises(self, monkeypatch):
        monkeypatch.setenv("PASSWORD_MIN_LENGTH", "50")
        monkeypatch.setenv("PASSWORD_MAX_LENGTH", "10")
        with pytest.raises(ValidationError) as exc:
            SecuritySettings()
        assert "PASSWORD_MAX_LENGTH must be >= PASSWORD_MIN_LENGTH" in str(exc.value)

    @pytest.mark.parametrize("bad", ["-1", "5"])
    def test_password_character_classes_out_of_range_raises(self, bad, monkeypatch):
        monkeypatch.setenv("PASSWORD_MIN_CHARACTER_CLASSES", bad)
        with pytest.raises(ValidationError) as exc:
            SecuritySettings()
        assert "PASSWORD_MIN_CHARACTER_CLASSES must be between 0 and 4" in str(
            exc.value
        )

    @pytest.mark.parametrize("bad", ["-1", "5"])
    def test_password_zxcvbn_score_out_of_range_raises(self, bad, monkeypatch):
        monkeypatch.setenv("PASSWORD_ZXCVBN_MIN_SCORE", bad)
        with pytest.raises(ValidationError) as exc:
            SecuritySettings()
        assert "PASSWORD_ZXCVBN_MIN_SCORE must be between 0 and 4" in str(exc.value)

    def test_password_hibp_timeout_zero_raises(self, monkeypatch):
        monkeypatch.setenv("PASSWORD_HIBP_TIMEOUT_SECONDS", "0")
        with pytest.raises(ValidationError) as exc:
            SecuritySettings()
        assert "PASSWORD_HIBP_TIMEOUT_SECONDS must be greater than zero" in str(
            exc.value
        )

    def test_totp_skew_negative_raises(self, monkeypatch):
        monkeypatch.setenv("MFA_TOTP_INITIAL_SKEW_WINDOWS", "-1")
        with pytest.raises(ValidationError) as exc:
            SecuritySettings()
        assert "MFA_TOTP_INITIAL_SKEW_WINDOWS must be zero or positive" in str(
            exc.value
        )

    def test_totp_skew_zero_allowed(self, monkeypatch):
        monkeypatch.setenv("MFA_TOTP_INITIAL_SKEW_WINDOWS", "0")
        s = SecuritySettings()
        assert s.mfa_totp_initial_skew_windows == 0

    def test_character_classes_and_zxcvbn_boundaries_ok(self, monkeypatch):
        # boundary happy values lock the passing branches (0..4 inclusive)
        monkeypatch.setenv("PASSWORD_MIN_CHARACTER_CLASSES", "4")
        monkeypatch.setenv("PASSWORD_ZXCVBN_MIN_SCORE", "0")
        s = SecuritySettings()
        assert s.password_min_character_classes == 4
        assert s.password_zxcvbn_min_score == 0


# ─────────────────────────────────────────────────────────────────────────────
# RateLimitSettingsMixin
# ─────────────────────────────────────────────────────────────────────────────
class TestRateLimitSettingsMixin:
    """The config layer ONLY validates ``rate_limit_storage_backend`` ∈ {memory, redis}.
    There is NO validator on ``rate_limit_storage_uri`` — the "memory:// is not a valid
    Redis scheme" rule lives at the consumption sites (``app/core/ratelimit/logic.py``,
    ``app/core/middleware/setup.py``), NOT in this mixin. conftest sets
    ``RATE_LIMIT_STORAGE_BACKEND=memory`` + ``RATE_LIMIT_STORAGE_URI=redis://localhost``
    (a harmless dev mismatch — the URI is unused when backend=memory).
    """

    def test_storage_backend_redis_normalized(self, monkeypatch):
        monkeypatch.setenv("RATE_LIMIT_STORAGE_BACKEND", "  REDIS  ")
        s = SecuritySettings()
        assert s.rate_limit_storage_backend == "redis"

    def test_storage_backend_memory_normalized(self, monkeypatch):
        monkeypatch.setenv("RATE_LIMIT_STORAGE_BACKEND", "Memory")
        s = SecuritySettings()
        assert s.rate_limit_storage_backend == "memory"

    def test_storage_backend_invalid_raises(self, monkeypatch):
        monkeypatch.setenv("RATE_LIMIT_STORAGE_BACKEND", "postgres")
        with pytest.raises(ValidationError) as exc:
            SecuritySettings()
        assert "RATE_LIMIT_STORAGE_BACKEND must be 'memory' or 'redis'" in str(
            exc.value
        )

    def test_rate_limit_default_list_coerces_csv(self, monkeypatch):
        monkeypatch.setenv("RATE_LIMIT_DEFAULT", "100/minute, 1000/hour ,")
        s = SecuritySettings()
        assert s.rate_limit_default_list == ["100/minute", "1000/hour"]

    def test_rate_limit_default_list_single(self, monkeypatch):
        monkeypatch.setenv("RATE_LIMIT_DEFAULT", "200/minute")
        s = SecuritySettings()
        assert s.rate_limit_default_list == ["200/minute"]

    def test_rate_limit_sensitive_value_coercion(self, monkeypatch):
        monkeypatch.setenv("RATE_LIMIT_SENSITIVE", "  3/minute  ")
        s = SecuritySettings()
        assert s.rate_limit_sensitive_value == "3/minute"

    def test_rate_limit_sensitive_value_empty_to_none(self, monkeypatch):
        monkeypatch.setenv("RATE_LIMIT_SENSITIVE", "   ")
        s = SecuritySettings()
        assert s.rate_limit_sensitive_value is None
