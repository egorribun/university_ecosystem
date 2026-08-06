"""Closure tests for CSP development, HSTS, and policy wrapper branches."""

from __future__ import annotations

import pytest

from app.core.config.mixins.csp_settings import CspSettingsMixin


def _settings(**values: object) -> CspSettingsMixin:
    instance = object.__new__(CspSettingsMixin)
    instance.__dict__.update(values)
    return instance


def test_development_connect_overrides_deduplicate_and_derive_ws_origins():
    settings = _settings(
        is_development=True,
        security_connect_src_values=[
            "http://127.0.0.1:8000",
            "ws://localhost:5173",
        ],
        frontend_origins_list=[
            "/",
            "http://app.example.com/",
            "HTTP://APP.EXAMPLE.COM",
            "https://secure.example.com",
            "ftp://files.example.com",
            "http:///missing-host",
        ],
    )

    overrides = settings._development_connect_overrides()

    assert "http://127.0.0.1:8000" not in overrides
    assert "ws://localhost:5173" not in overrides
    assert "http://app.example.com" in overrides
    assert "ws://app.example.com" in overrides
    assert "https://secure.example.com" in overrides
    assert "wss://secure.example.com" in overrides
    assert "ftp://files.example.com" in overrides
    assert "/" not in overrides


def test_csp_cached_flags_and_hsts_effective_paths():
    enabled = _settings(
        enable_coop=True,
        enable_coep=False,
        enable_corp=True,
        strict_security_headers_enabled=True,
        security_hsts_enabled=True,
        security_hsts_behind_proxy=False,
        app_base_url_clean="https://example.com",
    )
    assert enabled.coop_enabled is True
    assert enabled.coep_enabled is False
    assert enabled.corp_enabled is True
    assert enabled.security_hsts_enabled_effective is True

    behind_proxy = _settings(
        strict_security_headers_enabled=True,
        security_hsts_enabled=True,
        security_hsts_behind_proxy=True,
        app_base_url_clean="https://example.com",
    )
    assert behind_proxy.security_hsts_enabled_effective is False

    insecure = _settings(
        strict_security_headers_enabled=True,
        security_hsts_enabled=True,
        security_hsts_behind_proxy=False,
        app_base_url_clean="http://example.com",
    )
    assert insecure.security_hsts_enabled_effective is False

    hsts_disabled = _settings(
        strict_security_headers_enabled=True,
        security_hsts_enabled=False,
        security_hsts_behind_proxy=False,
        app_base_url_clean="https://example.com",
    )
    assert hsts_disabled.security_hsts_enabled_effective is False

    disabled = _settings(
        strict_security_headers_enabled=False,
        security_hsts_enabled=True,
        security_hsts_behind_proxy=False,
        app_base_url_clean="https://example.com",
    )
    assert disabled.security_hsts_enabled_effective is False


def test_build_csp_policy_uses_policy_engine_wrapper():
    settings = _settings(
        security_connect_src_values=["'self'"],
        security_csp_report_only_effective=False,
        strict_security_headers_enabled=True,
        security_csp_report_uri="",
        security_csp="",
        is_development=False,
    )

    policy = settings.build_csp_policy(nonce="nonce-value", report_only=False)

    assert "connect-src" in policy
    assert "nonce-value" in policy


def test_csp_validators_reject_unsupported_security_header_values():
    with pytest.raises(ValueError, match="COEP_VALUE"):
        CspSettingsMixin._validate_coep_value("unsafe")
    with pytest.raises(ValueError, match="CORP_VALUE"):
        CspSettingsMixin._validate_corp_value("unsafe")
    with pytest.raises(ValueError, match="SECURITY_COOKIE_SAMESITE_OVERRIDE"):
        CspSettingsMixin._validate_cookie_samesite_override("invalid")

    assert CspSettingsMixin._validate_coep_value(" Credentialless ") == "credentialless"
    assert CspSettingsMixin._validate_corp_value(" Cross-Origin ") == "cross-origin"
    assert CspSettingsMixin._validate_cookie_samesite_override(" Strict ") == "strict"
    assert CspSettingsMixin._validate_cookie_samesite_override(" ") == ""


def test_csp_properties_cover_overrides_and_deduplicate_connect_sources():
    settings = _settings(
        is_development=False,
        security_connect_src_extra=[
            "https://api.example",
            "HTTPS://API.EXAMPLE",
            " https://other.example wss://socket.example ",
        ],
        security_csp_report_only=True,
        enable_strict_security_headers=False,
        security_cookie_samesite_override="strict",
        enable_coep=True,
        coep_value="credentialless",
        enable_corp=False,
        corp_value="cross-origin",
    )

    assert settings.security_connect_src_values == [
        "'self'",
        "https://api.example",
        "https://other.example",
        "wss://socket.example",
    ]
    assert settings._development_connect_overrides() == []
    assert settings.strict_security_headers_enabled is False
    assert settings.cookie_secure is False
    assert settings.cookie_samesite == "strict"
    assert settings.security_csp_report_only_effective is True
    assert settings.should_inject_csp_nonce is False
    assert settings.coep_header_value == "credentialless"
    assert settings.corp_header_value == "cross-origin"
    assert settings.coep_enabled is True
    assert settings.corp_enabled is False


def test_csp_effective_flags_and_strict_policy_cover_remaining_paths():
    explicit = _settings(
        is_development=False,
        security_csp_report_only=False,
        enable_strict_security_headers=True,
        security_hsts_enabled=True,
        security_hsts_behind_proxy=False,
        app_base_url_clean="https://example.com",
        security_connect_src_extra="https://api.example",
        security_csp_report_uri="/csp-report",
        security_csp="",
    )
    assert explicit.security_csp_report_only_effective is False
    assert explicit.should_inject_csp_nonce is True
    assert "nonce-{nonce}" in explicit.strict_security_csp

    development_default = _settings(
        is_development=True,
        enable_strict_security_headers=None,
        security_csp_report_only=None,
        security_connect_src_extra="",
    )
    assert development_default.strict_security_headers_enabled is False
    assert development_default.security_csp_report_only_effective is True
    assert development_default.should_inject_csp_nonce is False

    forced_strict = _settings(
        is_development=True,
        enable_strict_security_headers=True,
        security_csp_report_only=None,
        security_connect_src_extra="",
    )
    assert forced_strict.security_csp_report_only_effective is False
