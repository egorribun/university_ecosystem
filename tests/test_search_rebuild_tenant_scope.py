"""Rebuilds validate the operator's tenant before touching search indices."""

from __future__ import annotations

import asyncio
import uuid
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import HTTPException
from typer.testing import CliRunner

from app.cli import search as search_cli
from app.core.config import settings
from app.core.db.listeners import set_pg_tenant_context
from app.core.tenant import bypass_rls_ctx, get_current_tenant, tenant_id_ctx
from app.models import Tenant
from app.services import search_indexer

TENANT = uuid.UUID("a1111111-1111-4111-8111-111111111111")
FOREIGN = uuid.UUID("b2222222-2222-4222-8222-222222222222")


@pytest.fixture
def boundaries(monkeypatch):
    service = SimpleNamespace(
        ensure_index=AsyncMock(),
        publish_rebuilt_indices=AsyncMock(),
        delete_index=AsyncMock(),
        close=AsyncMock(),
        bulk_index=AsyncMock(),
    )
    build = Mock(return_value=service)
    monkeypatch.setattr(search_indexer, "build_search_service", build)
    monkeypatch.setattr(settings, "mvp_tenant_id", TENANT)
    tenant = tenant_id_ctx.set("")
    bypass = bypass_rls_ctx.set(False)
    try:
        yield service, build
    finally:
        bypass_rls_ctx.reset(bypass)
        tenant_id_ctx.reset(tenant)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("scope", "configured", "bypass"),
    [
        (scope, configured, bypass)
        for scope in ("", str(TENANT), str(FOREIGN))
        for configured in (False, True)
        for bypass in (False, True)
        if not (configured and not bypass and scope in ("", str(TENANT)))
    ],
)
async def test_invalid_scope_never_opens_database_or_search(
    boundaries, monkeypatch, scope, configured, bypass
):
    _, build = boundaries
    database = Mock(side_effect=AssertionError("database must not open"))
    monkeypatch.setattr(search_indexer, "async_session", database)
    monkeypatch.setattr(settings, "mvp_tenant_id", TENANT if configured else None)
    tenant_token = tenant_id_ctx.set(scope)
    bypass_token = bypass_rls_ctx.set(bypass)
    try:
        with pytest.raises(ValueError, match=r"tenant|Tenant|MVP_TENANT_ID"):
            await search_indexer.reindex_all()
        assert get_current_tenant() == scope
        assert bypass_rls_ctx.get() is bypass
        database.assert_not_called()
        build.assert_not_called()
    finally:
        bypass_rls_ctx.reset(bypass_token)
        tenant_id_ctx.reset(tenant_token)


@pytest.mark.asyncio
@pytest.mark.parametrize("exists", [False, True])
async def test_missing_or_inactive_tenant_preserves_existing_search(
    boundaries, monkeypatch, db_session, exists
):
    _, build = boundaries
    if exists:
        db_session.add(
            Tenant(id=TENANT, name="Synthetic", slug="synthetic", is_active=False)
        )
        await db_session.flush()

    @asynccontextmanager
    async def session():
        assert get_current_tenant() == str(TENANT)
        yield db_session

    monkeypatch.setattr(search_indexer, "async_session", session)
    with pytest.raises(HTTPException) as error:
        await search_indexer.reindex_all()
    assert error.value.status_code == 503
    assert get_current_tenant() == ""
    build.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("initial_scope", ["", str(TENANT)])
@pytest.mark.parametrize("outcome", ["success", "failure", "cancel"])
async def test_validated_scope_is_used_and_restored(
    boundaries, monkeypatch, db_session, initial_scope, outcome
):
    service, build = boundaries
    db_session.add(
        Tenant(id=TENANT, name="Synthetic", slug="synthetic", is_active=True)
    )
    await db_session.flush()
    validation_queries = []
    original_execute = db_session.execute

    async def execute(statement, *args, **kwargs):
        validation_queries.append(str(statement))
        return await original_execute(statement, *args, **kwargs)

    monkeypatch.setattr(db_session, "execute", execute)

    @asynccontextmanager
    async def session():
        assert get_current_tenant() == str(TENANT)
        yield db_session

    def create_service():
        assert len(validation_queries) == 1
        assert "tenants.is_active IS true" in validation_queries[0]
        assert get_current_tenant() == str(TENANT)
        return service

    build.side_effect = create_service
    if outcome == "failure":
        service.ensure_index.side_effect = RuntimeError("synthetic failure")
    elif outcome == "cancel":
        service.ensure_index.side_effect = asyncio.CancelledError()
    monkeypatch.setattr(search_indexer, "async_session", session)
    token = tenant_id_ctx.set(initial_scope)
    try:
        if outcome == "success":
            assert await search_indexer.reindex_all() == {"news": 0, "events": 0}
            service.publish_rebuilt_indices.assert_awaited_once()
        else:
            expected = RuntimeError if outcome == "failure" else asyncio.CancelledError
            with pytest.raises(expected):
                await search_indexer.reindex_all()
            service.publish_rebuilt_indices.assert_not_awaited()
        assert get_current_tenant() == initial_scope
        assert bypass_rls_ctx.get() is False
        service.close.assert_awaited_once()
    finally:
        tenant_id_ctx.reset(token)


def test_cli_binds_the_postgres_listener_before_rebuild(boundaries, monkeypatch):
    service, build = boundaries
    emitted = []
    queries = []

    @asynccontextmanager
    async def session():
        connection = SimpleNamespace(
            dialect=SimpleNamespace(name="postgresql"),
            execute=lambda statement, params=None: emitted.append(
                (str(statement), params)
            ),
        )
        set_pg_tenant_context(None, None, connection)

        async def execute(statement):
            queries.append(str(statement))
            return SimpleNamespace(
                scalar_one_or_none=lambda: TENANT,
                scalars=lambda: SimpleNamespace(all=lambda: []),
            )

        yield SimpleNamespace(execute=execute)

    monkeypatch.setattr(search_indexer, "async_session", session)
    result = CliRunner().invoke(search_cli.app, ["reindex"])
    assert result.exit_code == 0, result.exception
    assert emitted == [
        (
            "SELECT set_config('app.current_tenant', :tenant_id, true);",
            {"tenant_id": str(TENANT)},
        )
    ]
    assert "tenants.is_active IS true" in queries[0]
    assert len(queries) == 3
    assert "news: 0 documents indexed" in result.output
    service.publish_rebuilt_indices.assert_awaited_once()
    build.assert_called_once()
    assert get_current_tenant() == ""
