"""Regression tests for the GraphQL gateway identity trust boundary."""

import hashlib
import hmac
import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

_SECRET = "graphql-internal-hmac-secret-for-tests"  # pragma: allowlist secret


def _request(headers: dict[str, str]) -> SimpleNamespace:
    return SimpleNamespace(headers=headers, query_params={})


def _signature(payload: str) -> str:
    return hmac.new(_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()


def test_gateway_signature_accepts_user_and_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.core.config import settings
    from app.graphql.schema import _verify_gateway_identity_signature

    monkeypatch.setattr(settings, "environment", "production")
    monkeypatch.setattr(settings, "internal_hmac_secret", _SECRET)
    request = _request(
        {
            "X-Internal-Signature": _signature("user:session"),
        }
    )

    _verify_gateway_identity_signature(request, "user", "session", "")


def test_gateway_signature_accepts_tenant_binding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.core.config import settings
    from app.graphql.schema import _verify_gateway_identity_signature

    monkeypatch.setattr(settings, "environment", "production")
    monkeypatch.setattr(settings, "internal_hmac_secret", _SECRET)
    request = _request(
        {
            "X-Internal-Signature": _signature("user:session:tenant"),
        }
    )

    _verify_gateway_identity_signature(request, "user", "session", "tenant")


def test_gateway_signature_rejects_invalid_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.core.config import settings
    from app.graphql.schema import _verify_gateway_identity_signature

    monkeypatch.setattr(settings, "environment", "production")
    monkeypatch.setattr(settings, "internal_hmac_secret", _SECRET)

    with pytest.raises(HTTPException) as exc_info:
        _verify_gateway_identity_signature(
            _request({"X-Internal-Signature": "forged"}),
            "user",
            "session",
            "",
        )
    assert exc_info.value.status_code == 401


def test_gateway_signature_requires_secret_in_production(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.core.config import settings
    from app.graphql.schema import _verify_gateway_identity_signature

    monkeypatch.setattr(settings, "environment", "production")
    monkeypatch.setattr(settings, "internal_hmac_secret", "")

    with pytest.raises(HTTPException) as exc_info:
        _verify_gateway_identity_signature(_request({}), "user", "session", "")
    assert exc_info.value.status_code == 401


def test_gateway_signature_can_be_disabled_for_development(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.core.config import settings
    from app.graphql.schema import _verify_gateway_identity_signature

    monkeypatch.setattr(settings, "environment", "testing")
    monkeypatch.setattr(settings, "internal_hmac_secret", "")

    _verify_gateway_identity_signature(_request({}), "user", "session", "")


def test_gateway_signature_defaults_are_fail_closed_and_secret_is_required(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Missing settings must not silently disable the production trust boundary."""
    from app.graphql import schema

    request = SimpleNamespace(headers={}, query_params={"lang": "ru"})

    # A testing deployment without an explicitly configured secret is allowed
    # to skip verification.  This exercises the safe empty-secret default and
    # prevents a non-empty mutation default from turning into a 401 challenge.
    monkeypatch.setattr(schema, "settings", SimpleNamespace(environment="testing"))
    schema._verify_gateway_identity_signature(request, "user", "session", "")

    # Conversely, an absent environment setting defaults to production and must
    # fail closed even when the settings object is only partially populated.
    monkeypatch.setattr(schema, "settings", SimpleNamespace(internal_hmac_secret=""))
    with pytest.raises(HTTPException) as exc_info:
        schema._verify_gateway_identity_signature(request, "user", "session", "")
    assert exc_info.value.status_code == 401


def test_gateway_signature_failure_preserves_locale_and_error_key(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Invalid signatures retain the request locale and canonical error key."""
    from app.graphql import schema

    monkeypatch.setattr(
        schema,
        "settings",
        SimpleNamespace(environment="production", internal_hmac_secret=_SECRET),
    )
    request = SimpleNamespace(
        headers={"X-Internal-Signature": "forged"}, query_params={"lang": "ru"}
    )
    rejection = MagicMock(side_effect=HTTPException(status_code=401))

    with patch.object(schema, "raise_unauthorized", rejection):
        with caplog.at_level(logging.WARNING):
            with pytest.raises(HTTPException):
                schema._verify_gateway_identity_signature(
                    request, "user", "session", ""
                )

    rejection.assert_called_once_with("ru", "errors.auth.credentials_invalid")
    assert "GraphQL gateway identity signature verification failed" in caplog.text


def test_gateway_signature_requires_header_for_authenticated_requests(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A missing internal signature is rejected as an ordinary 401."""
    from app.graphql import schema

    monkeypatch.setattr(
        schema,
        "settings",
        SimpleNamespace(environment="production", internal_hmac_secret=_SECRET),
    )

    with pytest.raises(HTTPException) as exc_info:
        schema._verify_gateway_identity_signature(_request({}), "user", "session", "")

    assert exc_info.value.status_code == 401


def test_missing_gateway_secret_preserves_locale_and_error_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Fail-closed missing-secret responses retain the canonical contract."""
    from app.graphql import schema

    monkeypatch.setattr(
        schema,
        "settings",
        SimpleNamespace(environment="production", internal_hmac_secret=""),
    )
    rejection = MagicMock(side_effect=HTTPException(status_code=401))
    request = SimpleNamespace(headers={}, query_params={"lang": "ru"})

    with patch.object(schema, "raise_unauthorized", rejection):
        with pytest.raises(HTTPException):
            schema._verify_gateway_identity_signature(request, "user", "session", "")

    rejection.assert_called_once_with("ru", "errors.auth.credentials_invalid")


def test_empty_gateway_environment_defaults_to_production(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An empty environment value cannot disable fail-closed verification."""
    from app.graphql import schema

    monkeypatch.setattr(
        schema,
        "settings",
        SimpleNamespace(environment="", internal_hmac_secret=""),
    )
    rejection = MagicMock(side_effect=HTTPException(status_code=401))

    with patch.object(schema, "raise_unauthorized", rejection):
        with pytest.raises(HTTPException):
            schema._verify_gateway_identity_signature(
                _request({}), "user", "session", ""
            )

    rejection.assert_called_once_with("en", "errors.auth.credentials_invalid")


def test_gateway_signature_development_warning_is_stable(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """The development-only bypass emits the canonical operational warning."""
    from app.graphql import schema

    monkeypatch.setattr(
        schema,
        "settings",
        SimpleNamespace(environment="testing", internal_hmac_secret=""),
    )

    with caplog.at_level(logging.WARNING):
        schema._verify_gateway_identity_signature(_request({}), "user", "session", "")

    assert (
        "INTERNAL_HMAC_SECRET not configured — skipping GraphQL gateway "
        "signature verification (acceptable in development only)"
    ) in caplog.text


@pytest.mark.asyncio
async def test_context_preserves_signature_unauthorized_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A forged gateway header remains a 401 instead of becoming a 503."""
    from app.core.config import settings
    from app.graphql.schema import get_context

    monkeypatch.setattr(settings, "environment", "production")
    monkeypatch.setattr(settings, "internal_hmac_secret", _SECRET)

    request = MagicMock()
    request.headers = {
        "X-User-ID": "user",
        "X-Session-ID": "session",
        "X-Internal-Signature": "forged",
    }
    request.app.dependency_overrides = {}
    request.state.dishka_container.get = AsyncMock(return_value=MagicMock())

    with pytest.raises(HTTPException) as exc_info:
        async for _ in get_context(request):
            pass
    assert exc_info.value.status_code == 401
