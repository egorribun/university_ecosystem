"""Closure tests for CSP development, HSTS, and policy wrapper branches."""

from __future__ import annotations

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
