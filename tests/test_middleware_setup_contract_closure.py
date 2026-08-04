from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, call, patch

from app.api.internal import INTERNAL_ROUTE_PREFIXES
from app.core.middleware import setup
from app.core.middleware.content_size import ContentSizeLimitMiddleware
from app.core.middleware.request_id import RequestIDMiddleware
from app.core.middleware.tenant import TenantContextMiddleware
from app.core.ratelimit import EndpointRateLimit, RateLimitMiddleware
from app.core.security_headers import SecurityHeadersMiddleware
from app.core.csrf import CSRFMiddleware


def _rate_settings(**overrides: object) -> SimpleNamespace:
    values: dict[str, object] = {
        "rate_limit_enabled": True,
        "rate_limit_storage_uri": "redis://rate-limit.example",
        "rate_limit_storage_backend": "memory",
        "rate_limit_default_list": ["100/minute"],
        "rate_limit_headers_enabled": True,
        "rate_limit_news": "10/minute",
        "rate_limit_events": "",
        "rate_limit_chat": "5/second",
        "rate_limit_auth_login": "",
        "rate_limit_auth_register": "",
        "rate_limit_auth_password_reset": "",
        "rate_limit_users_me": "",
        "rate_limit_graphql": "",
        "rate_limit_websocket": "",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_security_core_contract_passes_all_security_arguments():
    app = MagicMock()
    settings = SimpleNamespace(
        internal_allowed_ips_list=["10.0.0.1"],
        internal_auth_header="X-Internal-Auth",
        internal_auth_token="internal-token",
    )

    setup._configure_security_core(app, settings)

    assert app.add_middleware.call_args_list == [
        call(RequestIDMiddleware),
        call(TenantContextMiddleware),
        call(SecurityHeadersMiddleware, settings=settings),
        call(
            setup.InternalAccessMiddleware,
            allowed_ips=["10.0.0.1"],
            header_name="X-Internal-Auth",
            header_token="internal-token",
            internal_prefixes=INTERNAL_ROUTE_PREFIXES,
        ),
    ]


def test_csrf_contract_uses_exemptions_and_cookie_settings():
    app = MagicMock()
    settings = SimpleNamespace(
        cookie_secure=True,
        cookie_samesite="strict",
        access_token_expire_minutes=17,
        csrf_hmac_secret="csrf-test-secret",
    )

    setup._configure_csrf_middleware(app, settings)

    assert app.add_middleware.call_args == call(
        CSRFMiddleware,
        exempt_prefixes=(
            "/internal",
            "/api/v1/csp-report",
            "/api/v2/auth/token",
            "/api/v2/auth/webauthn",
        ),
        cookie_secure=True,
        cookie_samesite="strict",
        cookie_max_age=1020,
        csrf_hmac_secret="csrf-test-secret",
    )


def test_rate_limiting_contract_uses_fallbacks_and_endpoint_limits():
    app = MagicMock()

    setup._configure_rate_limiting(app, _rate_settings())

    middleware = app.add_middleware.call_args.args[0]
    kwargs = app.add_middleware.call_args.kwargs
    assert middleware is RateLimitMiddleware
    assert kwargs["redis_url"] is None
    assert kwargs["storage_backend"] == "memory"
    assert kwargs["limit"] == 100
    assert kwargs["window_seconds"] == 60
    assert kwargs["headers_enabled"] is True
    assert kwargs["endpoint_limits"] == (
        EndpointRateLimit("/api/v1/news", 10, 60),
        EndpointRateLimit("/api/v1/chat", 5, 1),
    )

    app.reset_mock()
    setup._configure_rate_limiting(
        app,
        _rate_settings(
            rate_limit_default_list=[],
            rate_limit_storage_backend=" REDIS ",
            rate_limit_news="invalid",
        ),
    )
    _, kwargs = app.add_middleware.call_args
    assert kwargs["redis_url"] == "redis://rate-limit.example"
    assert kwargs["storage_backend"] == "redis"
    assert kwargs["limit"] == 60
    assert kwargs["window_seconds"] == 60
    assert kwargs["endpoint_limits"] == (
        EndpointRateLimit("/api/v1/news", 60, 60),
        EndpointRateLimit("/api/v1/chat", 5, 1),
    )


def test_rate_limiting_disabled_is_a_strict_noop():
    app = MagicMock()

    setup._configure_rate_limiting(
        app,
        _rate_settings(rate_limit_enabled=False),
    )

    app.add_middleware.assert_not_called()


def test_cors_contract_passes_all_origin_and_header_options():
    app = MagicMock()
    settings = SimpleNamespace(
        cors_allow_origins_list=["https://example.test"],
        cors_allow_credentials_effective=True,
        cors_allow_methods_list=["GET", "POST"],
        cors_allow_headers_list=["Authorization"],
        cors_expose_headers_list=["X-Request-ID"],
    )

    setup._configure_cors_middleware(app, settings)

    assert app.add_middleware.call_args == call(
        setup.CORSMiddleware,
        allow_origins=["https://example.test"],
        allow_credentials=True,
        allow_methods=["GET", "POST"],
        allow_headers=["Authorization"],
        expose_headers=["X-Request-ID"],
    )


def test_configure_middleware_orchestrates_optional_layers_and_size_guard():
    app = MagicMock()
    decorator = MagicMock(side_effect=lambda handler: handler)
    app.middleware.return_value = decorator
    settings = SimpleNamespace(
        response_compression_enabled=True,
        trusted_proxies_list=["10.0.0.0/8"],
        allowed_hosts_list=["example.test"],
        max_upload_body_bytes=12345,
    )

    with (
        patch.object(setup, "_configure_security_core") as security,
        patch.object(setup, "_configure_csrf_middleware") as csrf,
        patch.object(setup, "_configure_rate_limiting") as rate,
        patch.object(setup, "_configure_cors_middleware") as cors,
    ):
        setup.configure_middleware(app, settings)

    security.assert_called_once_with(app, settings)
    csrf.assert_called_once_with(app, settings)
    rate.assert_called_once_with(app, settings)
    cors.assert_called_once_with(app, settings)
    decorator.assert_called_once_with(setup.http_response_hardening)
    assert app.add_middleware.call_args_list == [
        call(setup.BrotliMiddleware, minimum_size=512, gzip_fallback=True, quality=5),
        call(setup.ProxyHeadersMiddleware, trusted_hosts=["10.0.0.0/8"]),
        call(setup.TrustedHostMiddleware, allowed_hosts=["example.test"]),
        call(ContentSizeLimitMiddleware, max_bytes=12345),
    ]


def test_configure_middleware_skips_optional_layers_when_disabled_or_empty():
    app = MagicMock()
    decorator = MagicMock(side_effect=lambda handler: handler)
    app.middleware.return_value = decorator
    settings = SimpleNamespace(
        response_compression_enabled=False,
        trusted_proxies_list=[],
        allowed_hosts_list=None,
        max_upload_body_bytes=50,
    )

    with (
        patch.object(setup, "_configure_security_core"),
        patch.object(setup, "_configure_csrf_middleware"),
        patch.object(setup, "_configure_rate_limiting"),
        patch.object(setup, "_configure_cors_middleware"),
    ):
        setup.configure_middleware(app, settings)

    registered = [entry.args[0] for entry in app.add_middleware.call_args_list]
    assert setup.BrotliMiddleware not in registered
    assert setup.ProxyHeadersMiddleware not in registered
    assert setup.TrustedHostMiddleware not in registered
    assert registered == [ContentSizeLimitMiddleware]
