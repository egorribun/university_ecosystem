"""AUD-392: production registration refuses breached passwords without an explicit flag.

The production-resolved Settings object (flag left unset) drives the real
registration service, and the real HIBP validator performs the k-anonymity
lookup against a mocked transport.  No flag is patched on the service.
"""

from __future__ import annotations

import secrets
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import httpx
import pytest

from app.auth import security
from app.core.config import Settings
from app.schemas import schemas
from app.services.user import compliance_service
from app.services.user.compliance_service import UserComplianceService
from tests.test_aud467_settings_integration_environment import (
    _valid_production_settings,
)


class _Uow:
    def __init__(self, repo: AsyncMock) -> None:
        self.users = repo
        self.session = repo.db
        self.commit = AsyncMock()
        self.rollback = AsyncMock()

    async def __aenter__(self) -> _Uow:
        return self

    async def __aexit__(self, *args: object) -> None:
        return None


def _production_settings_without_hibp_flag() -> Settings:
    values = _valid_production_settings()
    values["environment"] = "production"
    values["elasticsearch_password"] = secrets.token_urlsafe(32)
    values["_env_file"] = None
    assert "password_hibp_check_enabled" not in values
    return Settings(**values)


def _registration_payload(password: str) -> schemas.UserCreate:
    return schemas.UserCreate(
        email="aud392.production@example.com",
        password=password,
        full_name="AUD Production",
    )


@pytest.mark.asyncio
async def test_aud392_production_registration_rejects_breached_password(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    password = secrets.token_urlsafe(32)
    suffix = security._calculate_lookup_hash(password)[5:]
    lookups: list[httpx.Request] = []

    def _breached(request: httpx.Request) -> httpx.Response:
        lookups.append(request)
        return httpx.Response(status_code=200, text=f"{suffix}:42\r\n")

    transport = httpx.MockTransport(_breached)
    async with httpx.AsyncClient(transport=transport, trust_env=False) as client:

        async def get_client() -> httpx.AsyncClient:
            return client

        monkeypatch.setattr(security, "_get_hibp_client", get_client)
        monkeypatch.setattr(security, "translate", lambda key, **_: key)
        monkeypatch.setattr(
            compliance_service,
            "settings",
            _production_settings_without_hibp_flag(),
        )

        repo = AsyncMock()
        repo.db = AsyncMock()
        repo.check_email_exists.return_value = False
        repo.create_with_invite.return_value = MagicMock(id=uuid4())
        get_hash = AsyncMock(return_value="hashed")
        service = UserComplianceService(_Uow(repo), audit=MagicMock())

        with (
            patch(
                "app.core.tenant.require_mvp_tenant",
                new=AsyncMock(return_value=uuid4()),
            ),
            patch.object(compliance_service, "get_password_hash", new=get_hash),
            pytest.raises(ValueError, match="password_policy_compromised"),
        ):
            await service.register_user(_registration_payload(password))

    assert len(lookups) == 1
    assert lookups[0].url.path.endswith(security._calculate_lookup_hash(password)[:5])
    get_hash.assert_not_awaited()
    repo.create_with_invite.assert_not_awaited()
