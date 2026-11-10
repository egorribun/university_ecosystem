"""Owned PostgreSQL/HTTP group visibility through ordinary request sessions.

Mixed-scope cases are defensive isolation proofs, not a supported multi-tenant
MVP deployment claim (ADR-053). Gateway HMAC assertions are controlled external
identity inputs: the public groups route does not authenticate durable sessions.
Database visibility, request sessions, transaction listener and RLS are real.
This module must only execute in the acknowledged owned PostgreSQL hosted lane.
"""

from __future__ import annotations

import hashlib
import hmac
import os
from collections.abc import AsyncIterator, Iterator
from contextlib import aclosing, asynccontextmanager
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID, uuid4

import httpx
import pytest
import sqlalchemy as sa
from dishka import Provider, Scope, make_async_container, provide
from dishka.integrations.fastapi import setup_dishka
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import app.repositories.schedule_repository as repository_module
from app.api.users import groups_router
from app.core.cache import MultiLayerCache
from app.core.config import settings
from app.core.db.listeners import register_tenant_listeners
from app.core.di.content import ContentProvider
from app.core.di.infrastructure import InfrastructureProvider
from app.core.middleware.tenant import TenantContextMiddleware
from app.core.protocols import AsyncDatabaseSession
from app.core.tenant import bypass_rls_ctx, get_current_tenant, tenant_id_ctx
from tests.fixtures import owned_baseline_postgres as owned

initialize_database_for_tests = owned.initialize_database_for_tests
prepare_database = owned.prepare_database
clean_database = owned.clean_database
default_database_guard = owned.default_database_guard
owned_baseline_server = owned.owned_baseline_server

pytestmark = [
    pytest.mark.integration,
    pytest.mark.timeout(300, method="thread", func_only=False),
    pytest.mark.skipif(
        os.getenv("RUN_INTEGRATION_TESTS") != "1",
        reason="Requires the hosted owned PostgreSQL acceptance lane",
    ),
]


@dataclass
class _OwnedGroups:
    ordinary_url: sa.URL = field(repr=False)
    admin: sa.Engine = field(repr=False)
    role: str
    tenant_a: UUID
    tenant_b: UUID
    group_a: UUID
    group_b: UUID


@pytest.fixture
def owned_groups(request: pytest.FixtureRequest) -> Iterator[_OwnedGroups]:
    assert request.config.getoption("timeout_disable_debugger_detection", False), (
        "Group HTTP acceptance requires --timeout-disable-debugger-detection"
    )
    server = request.getfixturevalue("owned_baseline_server")
    with owned.committed_baseline(server) as baseline:
        role = "group_reader_" + uuid4().hex
        credential = uuid4().hex + uuid4().hex
        tenant_a, tenant_b, group_a, group_b, unowned = (uuid4() for _ in range(5))
        admin = sa.create_engine(
            baseline.url,
            hide_parameters=True,
            poolclass=sa.pool.NullPool,
            connect_args={"connect_timeout": 5},
        )
        try:
            with admin.begin() as connection:
                # Generated role and credential live only on the verified owned server.
                connection.exec_driver_sql(
                    f'CREATE ROLE "{role}" LOGIN NOSUPERUSER NOBYPASSRLS '
                    f"NOCREATEDB NOCREATEROLE NOREPLICATION NOINHERIT PASSWORD '{credential}'"
                )
                connection.exec_driver_sql(f'GRANT USAGE ON SCHEMA public TO "{role}"')
                connection.exec_driver_sql(
                    f'GRANT SELECT ON public.groups, public.tenants TO "{role}"'
                )
                connection.execute(
                    sa.text(
                        "INSERT INTO tenants(id, name, slug) VALUES "
                        "(:a, 'A', 'group-proof-a'), (:b, 'B', 'group-proof-b')"
                    ),
                    {"a": tenant_a, "b": tenant_b},
                )
                connection.execute(
                    sa.text(
                        "INSERT INTO groups(id, name, tenant_id) VALUES "
                        "(:a, 'A group', :ta), (:b, 'B group', :tb), "
                        "(:unowned, 'Unowned group', NULL)"
                    ),
                    {
                        "a": group_a,
                        "b": group_b,
                        "ta": tenant_a,
                        "tb": tenant_b,
                        "unowned": unowned,
                    },
                )
            yield _OwnedGroups(
                baseline.url.set(username=role, password=credential),
                admin,
                role,
                tenant_a,
                tenant_b,
                group_a,
                group_b,
            )
        finally:
            admin.dispose()


@dataclass
class _Evidence:
    opened: int = 0
    sessions: list[AsyncSession] = field(default_factory=list)
    backend_ids: list[int] = field(default_factory=list)
    scopes: list[str] = field(default_factory=list)
    group_queries: int = 0
    sql_statements: int = 0


class _GroupHTTPProvider(Provider):
    # Reuse production construction rather than a fake GroupService/repository.
    group_service = ContentProvider.group_service

    def __init__(self, sessions, role: str, evidence: _Evidence) -> None:
        super().__init__()
        self.sessions = sessions
        self.role = role
        self.evidence = evidence

    @provide(scope=Scope.REQUEST)
    async def db(self) -> AsyncIterator[AsyncDatabaseSession]:
        self.evidence.opened += 1
        # Exact production provider owns the real session and MVP registry gate.
        # aclosing also releases it if an assertion or HTTP handler raises.
        async with aclosing(InfrastructureProvider().db(self.sessions)) as request_db:
            async for session in request_db:
                role = (
                    await session.execute(
                        sa.text(
                            "SELECT current_user, session_user, rolsuper, rolbypassrls, "
                            "rolcreatedb, rolcreaterole, rolreplication, rolinherit, "
                            "pg_has_role(current_user, 'ue_rls_bypass', 'MEMBER') "
                            "FROM pg_roles WHERE rolname = current_user"
                        )
                    )
                ).one()
                assert tuple(role) == (
                    self.role,
                    self.role,
                    False,
                    False,
                    False,
                    False,
                    False,
                    False,
                    False,
                )
                boundary = (
                    await session.execute(
                        sa.text(
                            "SELECT c.relrowsecurity, c.relforcerowsecurity, "
                            "row_security_active('public.groups'), "
                            "pg_get_userbyid(c.relowner) = current_user, "
                            "has_table_privilege('public.groups', 'SELECT'), "
                            "has_table_privilege('public.groups', 'INSERT'), "
                            "has_table_privilege('public.groups', 'UPDATE'), "
                            "has_table_privilege('public.groups', 'DELETE'), "
                            "has_table_privilege('public.groups', 'TRUNCATE'), "
                            "has_schema_privilege('public', 'CREATE'), "
                            "pg_backend_pid(), current_setting('app.current_tenant', true) "
                            "FROM pg_class c WHERE c.oid = 'public.groups'::regclass"
                        )
                    )
                ).one()
                assert tuple(boundary[:10]) == (
                    True,
                    True,
                    True,
                    False,
                    True,
                    False,
                    False,
                    False,
                    False,
                    False,
                )
                assert boundary[11] == get_current_tenant()
                assert bypass_rls_ctx.get() is False
                self.evidence.sessions.append(session)
                self.evidence.backend_ids.append(boundary[10])
                self.evidence.scopes.append(boundary[11])
                yield session


def _signed_headers(tenant: UUID, secret: str) -> dict[str, str]:
    user, session = uuid4(), uuid4()
    signature = hmac.new(
        secret.encode(), f"{user}:{session}:{tenant}".encode(), hashlib.sha256
    ).hexdigest()
    return {
        "x-user-id": str(user),
        "x-session-id": str(session),
        "x-tenant-id": str(tenant),
        "x-internal-signature": signature,
    }


@dataclass
class _HTTPGroups:
    client: httpx.AsyncClient
    engine: Any = field(repr=False)
    evidence: _Evidence
    secret: str = field(repr=False)
    cache: MultiLayerCache
    last_payload: list[dict[str, Any]] | None = None
    primed_payload: list[dict[str, Any]] | None = None

    async def prime(self, payload: list[dict[str, Any]]) -> None:
        await self.cache.set("schedule:groups", payload)
        self.primed_payload = payload

    async def prime_last_result(self) -> None:
        assert self.last_payload is not None
        await self.prime(self.last_payload)

    async def get(
        self, headers=None, *, scope: str, rows: list[tuple[UUID, str]]
    ) -> None:
        before_opened = self.evidence.opened
        before_queries = self.evidence.group_queries
        if self.primed_payload is not None:
            # Prove that this request confronts a live legacy entry, including
            # an empty-list entry; do not rely only on configured wall time.
            assert await self.cache.get("schedule:groups") == self.primed_payload
        response = await self.client.get("/api/v1/groups", headers=headers)
        assert response.status_code == 200
        assert [(row["id"], row["name"]) for row in response.json()] == [
            (str(identifier), name) for identifier, name in rows
        ]
        self.last_payload = [
            {key: row[key] for key in ("id", "name", "created_at")}
            for row in response.json()
        ]
        assert self.evidence.opened == before_opened + 1
        assert self.evidence.group_queries == before_queries + 1
        assert self.evidence.scopes[-1] == scope
        assert all(not session.in_transaction() for session in self.evidence.sessions)
        assert len({id(session) for session in self.evidence.sessions}) == len(
            self.evidence.sessions
        )
        assert len(set(self.evidence.backend_ids)) == 1
        # Raw connection reuse does not run Session.after_begin. It must not
        # inherit the tenant GUC from the just-closed request transaction.
        async with self.engine.connect() as connection:
            pid, tenant = (
                await connection.execute(
                    sa.text(
                        "SELECT pg_backend_pid(), "
                        "COALESCE(current_setting('app.current_tenant', true), '')"
                    )
                )
            ).one()
        assert pid == self.evidence.backend_ids[-1]
        assert tenant == ""
        assert tenant_id_ctx.get() == ""
        assert bypass_rls_ctx.get() is False


@asynccontextmanager
async def _http_stack(
    state: _OwnedGroups, *, mvp: bool = False
) -> AsyncIterator[_HTTPGroups]:
    register_tenant_listeners()
    engine = create_async_engine(
        state.ordinary_url,
        hide_parameters=True,
        pool_size=1,
        max_overflow=0,
        connect_args={"connect_timeout": 5},
    )
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    evidence = _Evidence()
    # Outlive the entire 300-second case watchdog, including fixture/probe SQL.
    # Production TTL settings remain unchanged.
    cache = MultiLayerCache(l1_ttl=600.0)
    secret = uuid4().hex
    container = None
    tenant_token = tenant_id_ctx.set("")
    bypass_token = bypass_rls_ctx.set(False)

    def observe_sql(connection, cursor, statement, parameters, context, executemany):
        evidence.sql_statements += 1
        assert evidence.sql_statements <= 96, "Unexpected unbounded request SQL"
        clause = context.compiled.statement if context.compiled is not None else None
        if isinstance(clause, sa.sql.Select) and any(
            getattr(table, "name", None) == "groups"
            for table in clause.get_final_froms()
        ):
            evidence.group_queries += 1
            assert evidence.group_queries <= 4, "Unexpected extra group-list queries"

    sa.event.listen(engine.sync_engine, "before_cursor_execute", observe_sql)
    try:
        with pytest.MonkeyPatch.context() as patch:
            patch.setattr(settings, "mvp_tenant_id", state.tenant_a if mvp else None)
            patch.setattr(repository_module, "schedule_cache", cache)
            container = make_async_container(
                _GroupHTTPProvider(sessions, state.role, evidence)
            )
            app = FastAPI()
            app.include_router(groups_router, prefix="/api/v1")
            setup_dishka(container, app)
            app.add_middleware(
                TenantContextMiddleware,
                internal_hmac_secret=secret,
                mvp_tenant_id=state.tenant_a if mvp else None,
            )
            try:
                async with httpx.AsyncClient(
                    transport=httpx.ASGITransport(app=app), base_url="http://test"
                ) as client:
                    yield _HTTPGroups(client, engine, evidence, secret, cache)
            finally:
                await container.close()
    finally:
        try:
            sa.event.remove(engine.sync_engine, "before_cursor_execute", observe_sql)
        finally:
            cache.l1.clear()
            try:
                await engine.dispose()
            finally:
                bypass_rls_ctx.reset(bypass_token)
                tenant_id_ctx.reset(tenant_token)


@pytest.mark.asyncio
async def test_mixed_scope_group_http_a_then_b(owned_groups):
    state = owned_groups
    async with _http_stack(state) as http:
        await http.get(
            _signed_headers(state.tenant_a, http.secret),
            scope=str(state.tenant_a),
            rows=[(state.group_a, "A group")],
        )
        await http.prime_last_result()
        await http.get(
            _signed_headers(state.tenant_b, http.secret),
            scope=str(state.tenant_b),
            rows=[(state.group_b, "B group")],
        )
        await http.get(
            _signed_headers(state.tenant_a, http.secret),
            scope=str(state.tenant_a),
            rows=[(state.group_a, "A group")],
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("identity", ["anonymous", "unsigned-hint", "bad-signature"])
async def test_mixed_scope_group_http_a_then_unscoped(owned_groups, identity):
    state = owned_groups
    async with _http_stack(state) as http:
        await http.get(
            _signed_headers(state.tenant_a, http.secret),
            scope=str(state.tenant_a),
            rows=[(state.group_a, "A group")],
        )
        await http.prime_last_result()
        headers = {}
        if identity == "unsigned-hint":
            headers = {"x-tenant-id": str(state.tenant_a)}
        elif identity == "bad-signature":
            headers = _signed_headers(state.tenant_a, uuid4().hex)
        await http.get(headers, scope="", rows=[])


@pytest.mark.asyncio
async def test_mixed_scope_group_http_unscoped_then_a(owned_groups):
    state = owned_groups
    async with _http_stack(state) as http:
        await http.get(scope="", rows=[])
        await http.prime_last_result()
        await http.get(
            _signed_headers(state.tenant_a, http.secret),
            scope=str(state.tenant_a),
            rows=[(state.group_a, "A group")],
        )


@pytest.mark.asyncio
async def test_group_http_ignores_legacy_foreign_cache(owned_groups):
    state = owned_groups
    async with _http_stack(state) as http:
        await http.prime([{"id": str(state.group_a), "name": "Stale foreign group"}])
        await http.get(
            _signed_headers(state.tenant_b, http.secret),
            scope=str(state.tenant_b),
            rows=[(state.group_b, "B group")],
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("mutation", ["rename", "delete"])
async def test_group_http_observes_committed_change(owned_groups, mutation):
    state = owned_groups
    async with _http_stack(state) as http:
        headers = _signed_headers(state.tenant_a, http.secret)
        await http.get(
            headers, scope=str(state.tenant_a), rows=[(state.group_a, "A group")]
        )
        await http.prime_last_result()
        # The owned fixture operator changes only its synthetic row; the HTTP
        # reader retains SELECT-only permissions and never acquires admin access.
        statement = (
            "UPDATE groups SET name = 'Renamed group' WHERE id = :id"
            if mutation == "rename"
            else "DELETE FROM groups WHERE id = :id"
        )
        with state.admin.begin() as connection:
            assert (
                connection.execute(sa.text(statement), {"id": state.group_a}).rowcount
                == 1
            )
        expected = [(state.group_a, "Renamed group")] if mutation == "rename" else []
        await http.get(headers, scope=str(state.tenant_a), rows=expected)


@pytest.mark.asyncio
async def test_mvp_group_http_anonymous_uses_configured_tenant(owned_groups):
    state = owned_groups
    async with _http_stack(state, mvp=True) as http:
        await http.get(scope=str(state.tenant_a), rows=[(state.group_a, "A group")])
        await http.prime_last_result()
        await http.get(
            {"x-tenant-id": str(state.tenant_b)},
            scope=str(state.tenant_a),
            rows=[(state.group_a, "A group")],
        )


@pytest.mark.asyncio
async def test_mvp_group_http_foreign_identity_rejected_before_session(owned_groups):
    state = owned_groups
    async with _http_stack(state, mvp=True) as http:
        await http.get(scope=str(state.tenant_a), rows=[(state.group_a, "A group")])
        await http.prime_last_result()
        opened, queries = http.evidence.opened, http.evidence.group_queries
        statements = http.evidence.sql_statements
        assert await http.cache.get("schedule:groups") == http.primed_payload
        response = await http.client.get(
            "/api/v1/groups", headers=_signed_headers(state.tenant_b, http.secret)
        )
        assert response.status_code == 401
        assert http.evidence.opened == opened
        assert http.evidence.group_queries == queries
        assert http.evidence.sql_statements == statements
        assert all(not session.in_transaction() for session in http.evidence.sessions)
        assert tenant_id_ctx.get() == "" and bypass_rls_ctx.get() is False
        await http.get(scope=str(state.tenant_a), rows=[(state.group_a, "A group")])
