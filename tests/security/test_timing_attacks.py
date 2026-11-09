"""Security regressions for constant-time comparisons at an app request boundary."""

from __future__ import annotations

import secrets
from collections.abc import Callable
from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI

import app.core.csrf as csrf_module


@pytest.fixture
def csrf_credentials() -> tuple[str, str]:
    """Use fresh non-secret-shaped values for each isolated request test."""
    return secrets.token_urlsafe(32), secrets.token_hex(16)


def _patch_csrf_comparator(
    monkeypatch: pytest.MonkeyPatch,
    comparator: Callable[[str, str], bool],
) -> None:
    """Replace only the CSRF module's comparator while keeping token helpers."""
    secrets_module = csrf_module.secrets
    monkeypatch.setattr(
        csrf_module,
        "secrets",
        SimpleNamespace(
            compare_digest=comparator,
            token_hex=secrets_module.token_hex,
            token_urlsafe=secrets_module.token_urlsafe,
        ),
    )


async def _post_signed_csrf_token(
    token: str, csrf_secret: str, anon_nonce: str
) -> httpx.Response:
    app = FastAPI()

    @app.post("/mut")
    async def mutate() -> dict[str, bool]:
        return {"ok": True}

    app.add_middleware(
        csrf_module.CSRFMiddleware,
        csrf_hmac_secret=csrf_secret,
        cookie_secure=False,
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        client.cookies.set(csrf_module.CSRF_COOKIE_NAME, token)
        client.cookies.set(csrf_module._ANON_NONCE_COOKIE_NAME, anon_nonce)
        return await client.post("/mut", headers={csrf_module.CSRF_HEADER_NAME: token})


@pytest.mark.security
@pytest.mark.asyncio
async def test_signed_csrf_request_uses_constant_time_comparator(
    monkeypatch: pytest.MonkeyPatch,
    csrf_credentials: tuple[str, str],
) -> None:
    """The actual middleware uses compare_digest for both token and HMAC checks."""
    csrf_secret, anon_nonce = csrf_credentials
    session_id = f"anon:{anon_nonce}"
    token = csrf_module._build_signed_token(session_id, csrf_secret.encode("ascii"))
    token_mac = token.partition(".")[2]
    original_compare_digest = csrf_module.secrets.compare_digest
    comparisons: list[tuple[str, str]] = []

    def compare_digest(left: str, right: str) -> bool:
        comparisons.append((left, right))
        return original_compare_digest(left, right)

    _patch_csrf_comparator(monkeypatch, compare_digest)

    response = await _post_signed_csrf_token(token, csrf_secret, anon_nonce)

    assert response.status_code == 200
    assert comparisons == [(token, token), (token_mac, token_mac)]


@pytest.mark.security
@pytest.mark.asyncio
async def test_signed_csrf_request_rejects_when_hmac_comparison_fails(
    monkeypatch: pytest.MonkeyPatch,
    csrf_credentials: tuple[str, str],
) -> None:
    """A negative control proves HMAC acceptance depends on the app comparator."""
    csrf_secret, anon_nonce = csrf_credentials
    session_id = f"anon:{anon_nonce}"
    token = csrf_module._build_signed_token(session_id, csrf_secret.encode("ascii"))
    token_mac = token.partition(".")[2]
    original_compare_digest = csrf_module.secrets.compare_digest
    comparisons: list[tuple[str, str]] = []

    def reject_hmac_comparison(left: str, right: str) -> bool:
        comparisons.append((left, right))
        actual_result = original_compare_digest(left, right)
        if len(comparisons) == 2:
            assert actual_result is True
            return False
        return actual_result

    _patch_csrf_comparator(monkeypatch, reject_hmac_comparison)

    response = await _post_signed_csrf_token(token, csrf_secret, anon_nonce)

    assert response.status_code == 403
    assert comparisons == [(token, token), (token_mac, token_mac)]
