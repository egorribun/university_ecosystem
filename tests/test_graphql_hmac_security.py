"""Regression tests for the GraphQL gateway identity trust boundary."""

import hashlib
import hmac
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

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
