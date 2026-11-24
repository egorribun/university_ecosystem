"""R29 HTTP over an owned PostgreSQL baseline with a non-bypass request role.

Synthetic gateway identities use the real HMAC and active-session authorization
path. Redis and ws-hub are local doubles, so this is not signed-stand evidence.
The owned-server fixture must only run in an explicitly allocated DB slot.
"""

from __future__ import annotations

import hashlib
import hmac
import os
from collections.abc import AsyncIterator, Iterator
from contextlib import aclosing, asynccontextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import fakeredis.aioredis
import httpx
import pytest
import sqlalchemy as sa
from dishka import Provider, Scope, make_async_container, provide
from dishka.integrations.fastapi import setup_dishka
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.chat import router as chat_router
from app.core.config import settings
from app.core.db.listeners import register_tenant_listeners
from app.core.di.chat import ChatProvider
from app.core.di.infrastructure import InfrastructureProvider
from app.core.localization.dictionary import TRANSLATIONS
from app.core.middleware.tenant import TenantContextMiddleware
from app.core.protocols import AsyncDatabaseSession
from app.core.tenant import bypass_rls_ctx, get_current_tenant, tenant_id_ctx
from app.deps.cache import MemoryCache
from app.repositories.unit_of_work import UnitOfWork, uow_from_session
from app.services.auth.redis_session import RedisSessionService
from app.services.chat.attachment_service import ChatAttachmentService
from app.services.chat.command_service import ChatMaintenanceService
from tests.fixtures import owned_baseline_postgres as owned
from tests.fixtures.rls_runtime_role import (
    RUNTIME_ROLE_FLAGS_QUERY,
    runtime_role_statements,
)

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
        reason="Requires the acknowledged owned PostgreSQL integration slot",
    ),
]


@dataclass(frozen=True)
class _Actor:
    user_id: UUID
    jti: UUID = field(repr=False)


@dataclass(frozen=True)
class _OwnedChat:
    url: sa.URL = field(repr=False)
    admin: sa.Engine = field(repr=False)
    role: str
    tenant: UUID
    group: UUID
    dm: UUID
    actors: dict[str, _Actor] = field(repr=False)


@pytest.fixture
def owned_chat(request: pytest.FixtureRequest) -> Iterator[_OwnedChat]:
    assert request.config.getoption("timeout_disable_debugger_detection", False), (
        "Owned PostgreSQL acceptance requires --timeout-disable-debugger-detection"
    )
    server = request.getfixturevalue("owned_baseline_server")
    with owned.committed_baseline(server) as baseline:
        role = "r29_" + uuid4().hex
        credential = uuid4().hex + uuid4().hex
        tenant, group, dm = uuid4(), uuid4(), uuid4()
        actors = {
            label: _Actor(uuid4(), uuid4())
            for label in ("owner", "member", "other", "outsider", "add1", "add2")
        }
        admin = sa.create_engine(
            baseline.url,
            poolclass=sa.pool.NullPool,
            hide_parameters=True,
            connect_args={"connect_timeout": 5},
        )
        try:
            with admin.begin() as connection:
                try:
                    for statement in runtime_role_statements(role, credential):
                        connection.exec_driver_sql(statement)
                except sa.exc.SQLAlchemyError:
                    raise AssertionError(
                        "Synthetic runtime role setup failed"
                    ) from None
                flags = connection.execute(
                    sa.text(RUNTIME_ROLE_FLAGS_QUERY), {"role": role}
                ).one()
                assert tuple(flags) == (False, False, False)
                connection.execute(
                    sa.text(
                        "INSERT INTO tenants(id, name, slug) VALUES (:id, :name, :slug)"
                    ),
                    {"id": tenant, "name": "R29 owned", "slug": f"r29-{tenant.hex}"},
                )
                connection.execute(
                    sa.text(
                        "INSERT INTO users (id, email, hashed_password, is_active, role, "
                        "mfa_required, mfa_epoch, tenant_id) VALUES "
                        "(:id, :email, 'unused', true, 'student', false, 0, :tenant)"
                    ),
                    [
                        {
                            "id": actor.user_id,
                            "email": f"r29-{actor.user_id.hex}@example.invalid",
                            "tenant": tenant,
                        }
                        for actor in actors.values()
                    ],
                )
                now = datetime.now(UTC)
                connection.execute(
                    sa.text(
                        "INSERT INTO active_sessions "
                        "(id, user_id, jti, expires_at, last_seen_at, signing_key) "
                        "VALUES (:id, :user_id, :jti, :expires, :seen, :key)"
                    ),
                    [
                        {
                            "id": uuid4(),
                            "user_id": actor.user_id,
                            "jti": str(actor.jti),
                            "expires": now + timedelta(hours=1),
                            "seen": now,
                            "key": uuid4().hex,
                        }
                        for actor in actors.values()
                    ],
                )
                connection.execute(
                    sa.text(
                        "INSERT INTO chats (id, chat_type, name, created_by, tenant_id) "
                        "VALUES (:group_id, 'group', 'Original', :owner, :tenant), "
                        "(:dm_id, 'dm', NULL, NULL, :tenant)"
                    ),
                    {
                        "group_id": group,
                        "dm_id": dm,
                        "owner": actors["owner"].user_id,
                        "tenant": tenant,
                    },
                )
                connection.execute(
                    sa.text(
                        "INSERT INTO chat_participants (chat_id, user_id) "
                        "VALUES (:chat_id, :user_id)"
                    ),
                    [
                        {"chat_id": chat, "user_id": actors[label].user_id}
                        for chat, labels in (
                            (group, ("owner", "member", "other")),
                            (dm, ("owner", "member")),
                        )
                        for label in labels
                    ],
                )
            yield _OwnedChat(
                baseline.url.set(username=role, password=credential),
                admin,
                role,
                tenant,
                group,
                dm,
                actors,
            )
        finally:
            admin.dispose()


@dataclass
class _Evidence:
    sessions: list[AsyncDatabaseSession] = field(default_factory=list)
    maintenance_sessions: list[AsyncDatabaseSession] = field(default_factory=list)


class _ChatHTTPProvider(Provider):
    def __init__(self, sessions: Any, role: str, tenant: UUID, evidence: _Evidence):
        super().__init__()
        self.sessions = sessions
        self.role = role
        self.tenant = tenant
        self.evidence = evidence

    @provide(scope=Scope.REQUEST)
    async def db(self) -> AsyncIterator[AsyncDatabaseSession]:
        async with aclosing(InfrastructureProvider().db(self.sessions)) as request_db:
            async for session in request_db:
                role = (
                    await session.execute(
                        sa.text(
                            "SELECT current_user, session_user, rolsuper, rolbypassrls, "
                            "pg_has_role(current_user, 'ue_rls_bypass', 'MEMBER') "
                            "FROM pg_roles WHERE rolname = current_user"
                        )
                    )
                ).one()
                assert tuple(role) == (self.role, self.role, False, False, False)
                boundary = (
                    await session.execute(
                        sa.text(
                            "SELECT c.relrowsecurity, c.relforcerowsecurity, "
                            "row_security_active('public.chats'), "
                            "row_security_active('public.users'), "
                            "pg_get_userbyid(c.relowner) = current_user, "
                            "has_table_privilege('public.chats', 'SELECT'), "
                            "has_table_privilege('public.chats', 'UPDATE'), "
                            "has_table_privilege('public.chat_participants', 'INSERT'), "
                            "has_table_privilege('public.chat_participants', 'DELETE'), "
                            "has_table_privilege('public.chats', 'TRUNCATE'), "
                            "has_schema_privilege('public', 'CREATE'), "
                            "current_setting('app.current_tenant', true) "
                            "FROM pg_class c WHERE c.oid = 'public.chats'::regclass"
                        )
                    )
                ).one()
                assert tuple(boundary[:11]) == (
                    True,
                    True,
                    True,
                    True,
                    False,
                    True,
                    True,
                    True,
                    True,
                    False,
                    False,
                )
                assert boundary[11] == str(self.tenant) == get_current_tenant()
                assert bypass_rls_ctx.get() is False
                self.evidence.sessions.append(session)
                yield session

    @provide(scope=Scope.REQUEST)
    def uow(self, db: AsyncDatabaseSession) -> UnitOfWork:
        return uow_from_session(db)

    @provide(scope=Scope.REQUEST)
    def maintenance(self, uow: UnitOfWork) -> ChatMaintenanceService:
        assert uow.session is self.evidence.sessions[-1]
        self.evidence.maintenance_sessions.append(uow.session)
        return ChatProvider().chat_maintenance_service(uow, ChatAttachmentService())

    @provide(scope=Scope.APP)
    def redis_session(self) -> RedisSessionService:
        return RedisSessionService(redis_url="redis://r29-test.invalid/0")


async def _operation(
    client: httpx.AsyncClient,
    kind: str,
    chat_id: str,
    headers: dict[str, str],
    target: UUID,
) -> httpx.Response:
    if kind == "add":
        return await client.post(
            f"/chats/{chat_id}/participants",
            json={"user_id": str(target)},
            headers=headers,
        )
    if kind == "remove":
        return await client.delete(
            f"/chats/{chat_id}/participants/{target}", headers=headers
        )
    assert kind == "rename"
    return await client.patch(
        f"/chats/{chat_id}", json={"name": "New group title"}, headers=headers
    )


def _headers(actor: _Actor, tenant: UUID, secret: str) -> dict[str, str]:
    user_id, jti, tenant_id = str(actor.user_id), str(actor.jti), str(tenant)
    signature = hmac.new(
        secret.encode(), f"{user_id}:{jti}:{tenant_id}".encode(), hashlib.sha256
    ).hexdigest()
    return {
        "x-user-id": user_id,
        "x-session-id": jti,
        "x-tenant-id": tenant_id,
        "x-internal-signature": signature,
    }


def _snapshot(state: _OwnedChat, chat_id: UUID) -> tuple[str | None, set[UUID]]:
    # Operator reads only rows created by this fixture, never a shared database.
    with state.admin.connect() as connection:
        name = connection.scalar(
            sa.text("SELECT name FROM chats WHERE id = :id"), {"id": chat_id}
        )
        members = set(
            connection.scalars(
                sa.text("SELECT user_id FROM chat_participants WHERE chat_id = :id"),
                {"id": chat_id},
            ).all()
        )
    return name, members


@asynccontextmanager
async def _http_stack(
    state: _OwnedChat,
) -> AsyncIterator[tuple[httpx.AsyncClient, _Evidence, str]]:
    register_tenant_listeners()
    engine = create_async_engine(
        state.url,
        hide_parameters=True,
        pool_size=1,
        max_overflow=0,
        connect_args={"connect_timeout": 5},
    )
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    evidence = _Evidence()
    secret = uuid4().hex
    cache = MemoryCache(default_ttl=600)
    session_redis = fakeredis.aioredis.FakeRedis()
    revocation_redis = fakeredis.aioredis.FakeRedis()
    tenant_token = tenant_id_ctx.set("")
    bypass_token = bypass_rls_ctx.set(False)

    async def session_client(_url: str) -> Any:
        return session_redis

    async def revocation_client() -> Any:
        return revocation_redis

    try:
        with pytest.MonkeyPatch.context() as patch:
            patch.setattr(settings, "mvp_tenant_id", state.tenant)
            patch.setattr(settings, "internal_hmac_secret", secret)
            patch.setattr(settings, "rate_limit_storage_backend", "memory")
            patch.setattr("app.deps.cache._cache_backend", cache)
            patch.setattr(
                "app.services.auth.redis_session._get_shared_client", session_client
            )
            patch.setattr(
                "app.api.deps.auth.get_revocation_redis_client", revocation_client
            )
            patch.setattr(
                "app.services.ws_hub_client.invalidate_ws_hub_cache", AsyncMock()
            )
            container = make_async_container(
                _ChatHTTPProvider(sessions, state.role, state.tenant, evidence)
            )
            app = FastAPI()
            app.include_router(chat_router, prefix="/api/v1")
            setup_dishka(container, app)
            app.add_middleware(
                TenantContextMiddleware,
                internal_hmac_secret=secret,
                mvp_tenant_id=state.tenant,
            )
            try:
                async with httpx.AsyncClient(
                    transport=httpx.ASGITransport(app=app),
                    base_url="http://test/api/v1",
                ) as client:
                    yield client, evidence, secret
            finally:
                await container.close()
    finally:
        await session_redis.aclose()
        await revocation_redis.aclose()
        await engine.dispose()
        tenant_id_ctx.reset(tenant_token)
        bypass_rls_ctx.reset(bypass_token)


@pytest.mark.asyncio
async def test_r29_group_and_dm_http_using_non_bypass_request_role(
    owned_chat: _OwnedChat,
):
    state = owned_chat
    actors = state.actors
    async with _http_stack(state) as (client, evidence, secret):
        headers = {
            label: _headers(actor, state.tenant, secret)
            for label, actor in actors.items()
        }

        async def operation(kind: str, chat_id: UUID, actor: str, target: UUID):
            before = len(evidence.sessions)
            response = await _operation(
                client, kind, str(chat_id), headers[actor], target
            )
            assert len(evidence.sessions) == before + 1
            assert len(evidence.maintenance_sessions) == before + 1
            assert evidence.sessions[-1] is evidence.maintenance_sessions[-1]
            return response

        original_group = _snapshot(state, state.group)
        original_dm = _snapshot(state, state.dm)
        assert original_group == (
            "Original",
            {actors[label].user_id for label in ("owner", "member", "other")},
        )
        assert original_dm == (
            None,
            {actors[label].user_id for label in ("owner", "member")},
        )

        for kind in ("add", "rename", "remove"):
            target = (
                actors["add1"].user_id if kind == "add" else actors["owner"].user_id
            )
            group = await operation(kind, state.group, "outsider", target)
            dm = await operation(kind, state.dm, "outsider", target)
            assert group.status_code == dm.status_code == 403
            assert group.json()["detail"] == dm.json()["detail"]
            assert (
                group.json()["detail"]
                in TRANSLATIONS["errors.chat.not_participant"].values()
            )
            assert _snapshot(state, state.group) == original_group
            assert _snapshot(state, state.dm) == original_dm

        for kind in ("add", "rename", "remove"):
            target = (
                actors["add1"].user_id if kind == "add" else actors["owner"].user_id
            )
            response = await operation(kind, state.dm, "owner", target)
            assert response.status_code == 400
            assert (
                response.json()["detail"]
                in TRANSLATIONS["errors.chat.not_a_group"].values()
            )
            assert _snapshot(state, state.dm) == original_dm

        expected_members = set(original_group[1])
        for actor, target in (("owner", "add1"), ("member", "add2")):
            response = await operation(
                "add", state.group, actor, actors[target].user_id
            )
            assert response.status_code == 200
            expected_members.add(actors[target].user_id)
            assert _snapshot(state, state.group) == ("Original", expected_members)

        for actor, name in (("owner", "Owner title"), ("member", "Member title")):
            before = len(evidence.sessions)
            response = await client.patch(
                f"/chats/{state.group}", json={"name": name}, headers=headers[actor]
            )
            assert response.status_code == 200
            assert (
                len(evidence.sessions)
                == len(evidence.maintenance_sessions)
                == before + 1
            )
            assert _snapshot(state, state.group) == (name, expected_members)

        denied = await operation(
            "remove", state.group, "member", actors["other"].user_id
        )
        assert denied.status_code == 403
        assert (
            denied.json()["detail"]
            in TRANSLATIONS["errors.chat.remove_forbidden"].values()
        )
        assert _snapshot(state, state.group) == ("Member title", expected_members)
        for actor, target in (("owner", "other"), ("member", "member")):
            response = await operation(
                "remove", state.group, actor, actors[target].user_id
            )
            assert response.status_code == 200
            expected_members.remove(actors[target].user_id)
            assert _snapshot(state, state.group) == ("Member title", expected_members)
