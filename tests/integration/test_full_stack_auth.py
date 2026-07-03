"""Integration tests for full stack auth token signature verification and delegation."""

from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_full_stack_auth_unauthenticated_rejected(async_client: AsyncClient):
    """Protected endpoints must reject requests without auth headers."""
    resp = await async_client.get("/users/me")
    assert resp.status_code == 401
    assert "detail" in resp.json()


@pytest.mark.asyncio
async def test_full_stack_auth_invalid_token_rejected(async_client: AsyncClient):
    """Protected endpoints must reject requests with invalid/malformed tokens."""
    headers = {"Authorization": "Bearer invalid-token-sig"}
    resp = await async_client.get("/users/me", headers=headers)
    assert resp.status_code == 401
