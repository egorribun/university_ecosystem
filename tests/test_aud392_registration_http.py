"""AUD-392: deployed defaults enforce HIBP through the registration route."""

from __future__ import annotations

import os
import secrets

import httpx
import pytest
from sqlalchemy import select

from app.auth import security
from app.core.config import Settings
from app.models import User
from app.services.user import compliance_service
from tests.test_aud467_settings_integration_environment import (
    _valid_production_settings,
)


@pytest.fixture(autouse=True)
def offline_flagd(monkeypatch: pytest.MonkeyPatch) -> list[bool]:
    """Prevent the unrelated app-lifespan flag provider from opening a connection."""
    calls: list[bool] = []

    async def no_flag_provider() -> None:
        calls.append(True)

    monkeypatch.setattr(
        "app.core.feature_flags.initialize_feature_flags", no_flag_provider
    )
    return calls


@pytest.mark.parametrize("environment", ["staging", "production"])
@pytest.mark.parametrize(
    "outcome", ["clean", "breached", "http_error", "timeout", "malformed"]
)
async def test_default_hibp_policy_through_registration_http(
    offline_flagd, async_client, db_session, monkeypatch, environment: str, outcome: str
) -> None:
    for name in ("PASSWORD_HIBP_CHECK_ENABLED", "PASSWORD_HIBP_FAIL_OPEN"):
        monkeypatch.delenv(name, raising=False)
    for name in tuple(os.environ):
        if name.endswith("_FILE"):
            monkeypatch.delenv(name, raising=False)

    values = _valid_production_settings()
    synthetic_url = httpx.URL(
        scheme="https", host=f"hibp-{secrets.token_hex(8)}.invalid", path="/range"
    )
    values.update(
        environment=environment,
        elasticsearch_password=secrets.token_urlsafe(32),
        password_hibp_api_url=str(synthetic_url),
        _env_file=None,
    )
    assert "password_hibp_check_enabled" not in values
    assert "password_hibp_fail_open" not in values
    production_settings = Settings(**values)
    assert production_settings.password_hibp_check_enabled is True
    assert production_settings.password_hibp_fail_open is False
    assert "password_hibp_fail_open" not in production_settings.model_fields_set
    monkeypatch.setattr(compliance_service, "settings", production_settings)
    monkeypatch.setattr(security, "settings", production_settings)

    candidate = secrets.token_urlsafe(24) + "Aa1!"
    digest = security._calculate_lookup_hash(candidate)
    requests: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if outcome == "timeout":
            raise httpx.ReadTimeout("synthetic timeout", request=request)
        if outcome == "http_error":
            return httpx.Response(503, text="synthetic outage")
        if outcome == "malformed":
            return httpx.Response(200, text="synthetic malformed response")
        count = 1 if outcome == "breached" else 0
        return httpx.Response(200, text=f"{digest[5:]}:{count}\r\n")

    transport = httpx.MockTransport(respond)
    email = f"aud392-{environment}-{outcome}@example.com"
    async with httpx.AsyncClient(transport=transport, trust_env=False) as hibp_client:

        async def synthetic_hibp_client() -> httpx.AsyncClient:
            return hibp_client

        monkeypatch.setattr(security, "_get_hibp_client", synthetic_hibp_client)
        response = await async_client.post(
            "/auth/register",
            json={"email": email, "password": candidate, "full_name": "Synthetic Test"},
        )

    assert offline_flagd == [True]
    assert len(requests) == 1
    assert (
        str(requests[0].url)
        == f"{production_settings.password_hibp_api_url.rstrip('/')}/{digest[:5]}"
    )
    assert requests[0].method == "GET"
    assert candidate not in str(requests[0].url)
    assert digest not in str(requests[0].url)
    stored = (
        await db_session.execute(select(User).where(User.email == email))
    ).scalar_one_or_none()
    if outcome == "clean":
        assert response.status_code == 200, response.text
        assert response.json() == {"status": "ok"}
        assert stored is not None
        assert stored.hashed_password.startswith("$argon2")
    else:
        assert response.status_code == 400, response.text
        key = "compromised" if outcome == "breached" else "hibp_unavailable"
        assert response.json()["detail"] == security.translate(
            f"errors.auth.password_policy_{key}"
        )
        assert stored is None
