"""Closure tests for the CORS settings mixin's alternate input paths."""

from __future__ import annotations

from unittest.mock import patch

from app.core.config.mixins.cors_settings import CorsSettingsMixin
from app.core.config.security import SecuritySettings


def _settings(**values: object) -> CorsSettingsMixin:
    """Build a bare mixin instance so list-valued branches stay unit-scoped."""
    instance = object.__new__(CorsSettingsMixin)
    instance.__dict__.update(values)
    return instance


class TestCorsSettingsClosure:
    def test_frontend_origins_accepts_lists_and_development_defaults(self):
        settings = _settings(
            frontend_origins=[" https://A.example/ ", "", "https://a.example"],
            frontend_origin="",
            app_base_url="",
            is_development=True,
        )

        assert settings.frontend_origins_list == [
            "https://A.example",
            "https://login.example",
            "http://localhost:5173",
            "http://127.0.0.1:5173",
        ]

    def test_cors_origins_skip_wildcard_and_case_insensitive_duplicates(self):
        settings = _settings(
            frontend_origins_list=["*", "https://A.example", "https://a.example"],
            strict_security_headers_enabled=False,
        )

        assert settings.cors_allow_origins_list == ["https://A.example"]

    def test_strict_cors_origins_skip_non_https_external_origins(self):
        settings = _settings(
            frontend_origins_list=["http://external.example", "https://secure.example"],
            strict_security_headers_enabled=True,
        )

        assert settings.cors_allow_origins_list == ["https://secure.example"]

    def test_credentials_effective_allows_non_strict_origins(self):
        settings = _settings(
            cors_allow_credentials=True,
            frontend_origins="https://example.com",
            frontend_origin="",
            app_base_url="",
            strict_security_headers_enabled=False,
        )

        assert settings.cors_allow_credentials_effective is True

    def test_credentials_effective_disables_when_credentials_are_false_or_origins_empty(
        self,
    ):
        assert (
            _settings(
                cors_allow_credentials=False,
                cors_allow_origins_list=["https://example.com"],
            ).cors_allow_credentials_effective
            is False
        )
        assert (
            _settings(
                cors_allow_credentials=True,
                cors_allow_origins_list=[],
            ).cors_allow_credentials_effective
            is False
        )

    def test_credentials_effective_rejects_non_https_in_direct_allow_list(self):
        settings = _settings(
            cors_allow_credentials=True,
            strict_security_headers_enabled=True,
            cors_allow_origins_list=["http://example.com"],
        )

        assert settings.cors_allow_credentials_effective is False

    def test_credentials_effective_checks_localhost_then_https_origin(self):
        settings = _settings(
            cors_allow_credentials=True,
            strict_security_headers_enabled=True,
            cors_allow_origins_list=["http://localhost:5173", "https://example.com"],
        )

        assert settings.cors_allow_credentials_effective is True

    def test_trusted_and_allowed_hosts_accept_sequence_inputs(self):
        settings = _settings(
            trusted_hosts=[" a.example ", "", "b.example"],
            allowed_hosts=(" c.example ", ""),
        )

        assert settings.trusted_hosts_list == ["a.example", "b.example"]
        assert settings.allowed_hosts_list == ["c.example"]

    def test_trusted_hosts_accepts_comma_delimited_strings(self):
        settings = _settings(trusted_hosts=" a.example, ,b.example ")

        assert settings.trusted_hosts_list == ["a.example", "b.example"]

    def test_allowed_hosts_use_development_defaults_when_empty(self):
        settings = _settings(allowed_hosts="", is_development=True)

        assert settings.allowed_hosts_list == ["localhost", "127.0.0.1", "testserver"]

    def test_methods_and_headers_accept_lists_and_empty_defaults(self):
        custom = _settings(
            cors_allow_methods=["GET", " POST "],
            cors_allow_headers=["X-One", " X-Two "],
        )
        empty = _settings(cors_allow_methods="", cors_allow_headers="")

        assert custom.cors_allow_methods_list == ["GET", "POST"]
        assert custom.cors_allow_headers_list == ["X-One", "X-Two"]
        assert empty.cors_allow_methods_list == [
            "GET",
            "POST",
            "PUT",
            "PATCH",
            "DELETE",
            "OPTIONS",
        ]
        assert empty.cors_allow_headers_list == ["Authorization", "Content-Type"]

    def test_exposed_headers_and_proxy_lists_preserve_required_headers(self):
        settings = _settings(
            internal_allowed_ips=[" 127.0.0.1 ", "", "::1"],
            cors_expose_headers=[" X-Test ", ""],
            request_id_header="x-request-id",
            trace_header="x-trace-id",
            trusted_proxies=[" 10.0.0.1 ", ""],
        )

        assert settings.internal_allowed_ips_list == ["127.0.0.1", "::1"]
        assert settings.cors_expose_headers_list == [
            "X-Test",
            "x-request-id",
            "x-trace-id",
        ]
        assert settings.trusted_proxies_list == ["10.0.0.1"]

    def test_internal_auth_token_validator_warns_only_for_non_development(
        self, monkeypatch
    ):
        monkeypatch.setenv("ENVIRONMENT", "production")
        monkeypatch.setenv("AUDIT_LOG_SECRET", "a" * 32)  # pragma: allowlist secret
        monkeypatch.setenv("SECRET_KEY", "p" * 48)  # pragma: allowlist secret
        monkeypatch.setenv("INTERNAL_HMAC_SECRET", "i" * 48)  # pragma: allowlist secret
        monkeypatch.setenv("ALGORITHM", "RS256")
        monkeypatch.setenv("JWT_PRIVATE_KEY_PATH", "")

        with patch("app.core.logging.get_logger") as get_logger:
            SecuritySettings(internal_auth_token=None)

        message = get_logger.return_value.warning.call_args.args[0]
        assert "Internal route shared guard is not configured" in message

    def test_internal_auth_token_validator_returns_configured_value(self, monkeypatch):
        monkeypatch.setenv("ENVIRONMENT", "testing")

        settings = SecuritySettings(internal_auth_token="configured-token")

        assert settings.internal_auth_token == "configured-token"
