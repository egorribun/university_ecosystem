"""Behaviour-level negative security regressions from roadmap Phase 9.1."""

from __future__ import annotations

import jwt
import pytest

from app.auth.security import decode_token
from app.core.cache_versioning import CacheVersionManager
from app.core.config import settings


@pytest.mark.security
@pytest.mark.asyncio
async def test_forged_admin_role_claim_cannot_elevate_student(
    root_client, user_factory
) -> None:
    """The server-side role/permission source must defeat a forged JWT role."""

    password = "NegativeSecurityPass123!"
    from app.auth.security import get_password_hash

    student = await user_factory(
        role="student",
        email="negative-security-student@example.com",
        hashed_password=await get_password_hash(password),
    )
    login = await root_client.post(
        "/api/v1/auth/login",
        data={"username": student.email, "password": password},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert login.status_code == 200

    issued_token = login.cookies.get("access_token_v2")
    assert issued_token
    payload = decode_token(issued_token)
    assert payload is not None

    forged_payload = {**payload, "role": "admin"}
    forged_token = jwt.encode(
        forged_payload,
        settings.jwt_signing_active_secret,
        algorithm=settings.algorithm,
        headers={"kid": settings.jwt_signing_active_kid},
    )
    response = await root_client.get(
        "/admin/audit",
        headers={"Authorization": f"Bearer {forged_token}"},
    )

    assert response.status_code == 403


@pytest.mark.security
def test_cache_version_key_separates_tenants() -> None:
    """Tenant context must participate in cache identity, preventing poisoning."""

    manager = CacheVersionManager(prefix="events:list")
    tenant_a_key = manager.build_cache_key(
        locale="en", version="1", tenant_id="tenant-a", page=1
    )
    tenant_b_key = manager.build_cache_key(
        locale="en", version="1", tenant_id="tenant-b", page=1
    )

    assert tenant_a_key != tenant_b_key
