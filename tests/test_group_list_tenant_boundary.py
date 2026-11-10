"""Group list responses must use this request's database visibility.

The database boundary below is a controlled test double. These tests exercise
real tenant middleware, HTTP routing, service/repository code and L1 caching;
they do not claim PostgreSQL RLS or deployed-system execution evidence.
"""

from __future__ import annotations

import hashlib
import hmac
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import httpx
import pytest
from dishka import Provider, Scope, make_async_container, provide
from dishka.integrations.fastapi import setup_dishka
from fastapi import FastAPI

import app.repositories.schedule_repository as repository_module
from app.api.users import groups_router
from app.core.cache import MultiLayerCache
from app.core.middleware.tenant import TenantContextMiddleware
from app.core.tenant import bypass_rls_ctx, get_current_tenant, tenant_id_ctx
from app.repositories.schedule_repository import GroupRepository
from app.schemas.dtos import GroupDTO
from app.services.group_service import GroupService

TENANT_A = str(UUID(int=1))
TENANT_B = str(UUID(int=2))
GROUP_A = UUID(int=11)
GROUP_B = UUID(int=22)


@pytest.fixture
def isolated_group_cache(monkeypatch):
    cache = MultiLayerCache()
    monkeypatch.setattr(repository_module, "schedule_cache", cache)
    return cache


def _database(rows):
    result = MagicMock()
    result.scalars.return_value.all.return_value = rows
    return MagicMock(execute=AsyncMock(return_value=result))


def _headers(tenant, secret):
    user = str(uuid4())
    session = str(uuid4())
    signature = hmac.new(
        secret.encode(), f"{user}:{session}:{tenant}".encode(), hashlib.sha256
    ).hexdigest()
    return {
        "x-user-id": user,
        "x-session-id": session,
        "x-tenant-id": tenant,
        "x-internal-signature": signature,
    }


def _app(secret, *, mvp_tenant=None):
    scopes = []

    class GroupProvider(Provider):
        @provide(scope=Scope.REQUEST)
        def group_service(self) -> GroupService:
            scope = get_current_tenant()
            rows = {
                TENANT_A: [
                    SimpleNamespace(
                        id=GROUP_A,
                        name="Tenant A group",
                        created_at=datetime(2026, 1, 1, tzinfo=UTC),
                    )
                ],
                TENANT_B: [
                    SimpleNamespace(
                        id=GROUP_B,
                        name="Tenant B group",
                        created_at=datetime(2026, 1, 1, tzinfo=UTC),
                    )
                ],
            }.get(scope, [])
            db = _database(rows)
            original_execute = db.execute

            async def execute(statement):
                scopes.append(scope)
                return await original_execute(statement)

            db.execute = execute
            return GroupService(db, GroupRepository(db))

    app = FastAPI()
    app.include_router(groups_router, prefix="/api/v1")
    container = make_async_container(GroupProvider())
    setup_dishka(container, app)
    app.add_middleware(
        TenantContextMiddleware,
        internal_hmac_secret=secret,
        mvp_tenant_id=mvp_tenant,
    )
    return app, container, scopes


@pytest.mark.asyncio
@pytest.mark.parametrize("recipient", ["other-tenant", "anonymous", "forged-tenant"])
async def test_http_group_list_never_reuses_another_scope(
    isolated_group_cache, recipient
):
    secret = uuid4().hex
    app, container, scopes = _app(secret)
    if recipient == "other-tenant":
        headers = _headers(TENANT_B, secret)
        expected = [
            {
                "created_at": "2026-01-01T00:00:00Z",
                "id": str(GROUP_B),
                "name": "Tenant B group",
                "course": None,
                "faculty": None,
            }
        ]
        expected_scope = TENANT_B
    else:
        headers = {} if recipient == "anonymous" else {"x-tenant-id": TENANT_A}
        expected = []
        expected_scope = ""
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            first = await client.get(
                "/api/v1/groups", headers=_headers(TENANT_A, secret)
            )
            second = await client.get("/api/v1/groups", headers=headers)
        assert first.status_code == second.status_code == 200
        assert first.json()[0]["id"] == str(GROUP_A)
        assert second.json() == expected
        assert scopes == [TENANT_A, expected_scope]
    finally:
        await container.close()


@pytest.mark.asyncio
async def test_configured_mvp_rejects_foreign_identity_but_routes_anonymous(
    isolated_group_cache,
):
    """Single configured-tenant HTTP is not a cross-tenant leakage claim."""
    secret = uuid4().hex
    app, container, _scopes = _app(secret, mvp_tenant=UUID(TENANT_A))
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            own = await client.get("/api/v1/groups", headers=_headers(TENANT_A, secret))
            foreign = await client.get(
                "/api/v1/groups", headers=_headers(TENANT_B, secret)
            )
            anonymous = await client.get("/api/v1/groups")
        assert own.status_code == anonymous.status_code == 200
        assert foreign.status_code == 401
        assert own.json() == anonymous.json()
        assert anonymous.json()[0]["id"] == str(GROUP_A)
    finally:
        await container.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("first_scope,first_bypass", [("", False), (TENANT_A, True)])
async def test_empty_or_privileged_result_cannot_prime_an_ordinary_request(
    isolated_group_cache, first_scope, first_bypass
):
    privileged = [GroupDTO(id=GROUP_B, name="Tenant B group")] if first_bypass else []
    t_token = tenant_id_ctx.set(first_scope)
    b_token = bypass_rls_ctx.set(first_bypass)
    try:
        await GroupRepository(_database(privileged)).list_groups()
        tenant_id_ctx.set(TENANT_A)
        bypass_rls_ctx.set(False)
        rows = await GroupRepository(
            _database([GroupDTO(id=GROUP_A, name="Tenant A group")])
        ).list_groups()
        assert [(row.id, row.name) for row in rows] == [(GROUP_A, "Tenant A group")]
    finally:
        bypass_rls_ctx.reset(b_token)
        tenant_id_ctx.reset(t_token)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "current_rows", [[], [GroupDTO(id=GROUP_A, name="Renamed group")]]
)
async def test_group_list_observes_committed_database_changes(
    isolated_group_cache, current_rows
):
    await GroupRepository(
        _database([GroupDTO(id=GROUP_A, name="Previous group")])
    ).list_groups()
    result = await GroupRepository(_database(current_rows)).list_groups()
    assert [(row.id, row.name) for row in result] == [
        (row.id, row.name) for row in current_rows
    ]


@pytest.mark.asyncio
async def test_group_list_does_not_hide_database_failure_with_cached_data(
    isolated_group_cache,
):
    await isolated_group_cache.set(
        "schedule:groups",
        [GroupDTO(id=GROUP_B, name="Foreign group").model_dump(mode="json")],
    )
    db = _database([])
    db.execute.side_effect = RuntimeError("database unavailable")
    with pytest.raises(RuntimeError, match="database unavailable"):
        await GroupRepository(db).list_groups()


@pytest.mark.asyncio
async def test_group_list_retains_database_order_and_safety_limit(
    isolated_group_cache, db_session
):
    """SQLite validates query ordering/capping, not tenant RLS."""
    from app.models import Group

    db_session.add_all(
        Group(id=uuid4(), name=f"Group {number:04d}") for number in range(1001, -1, -1)
    )
    await db_session.flush()
    rows = await GroupRepository(db_session).list_groups()
    assert len(rows) == 1000
    assert [row.name for row in rows] == [
        f"Group {number:04d}" for number in range(1000)
    ]
