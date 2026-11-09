"""Real CLI and tenant listener controls; recorder is not PostgreSQL/RLS proof."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest
from sqlalchemy.dialects import postgresql
from typer.testing import CliRunner

from app.cli import db as cli
from app.core.db.listeners import set_pg_tenant_context
from app.core.tenant import (
    bypass_rls_ctx,
    get_bypass_rls,
    get_current_tenant,
    tenant_id_ctx,
)

A = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
B = UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")


@pytest.fixture
def harness(monkeypatch):
    def build(
        *, ambient="", bypass=False, configured=A, tenant=A, existing=None, fail=None
    ):
        monkeypatch.setattr(cli.settings, "mvp_tenant_id", configured)
        events = []
        statements = []
        gucs = []
        inserted = []
        transaction = False
        db = AsyncMock()
        db.add = MagicMock()
        connection = SimpleNamespace(
            dialect=postgresql.dialect(),
            execute=lambda sql, parameters=None: gucs.append(parameters),
        )

        def scope():
            assert get_current_tenant() == str(A)
            assert get_bypass_rls() is False

        def begin():
            nonlocal transaction
            scope()
            if not transaction:
                set_pg_tenant_context(None, None, connection)
                transaction = True

        async def enter():
            scope()
            events.append("enter")
            if fail == "enter":
                raise RuntimeError(fail)
            return db

        async def execute(statement):
            begin()
            compiled = statement.compile(dialect=postgresql.dialect())
            statements.append(compiled)
            if fail == "lookup":
                raise RuntimeError(fail)
            is_tenant = "FROM tenants" in str(compiled)
            if is_tenant:
                assert "tenants.is_active IS true" in str(compiled)
                assert A in compiled.params.values()
            else:
                assert "users.tenant_id =" in str(compiled)
                assert A in compiled.params.values()
                assert str(compiled).endswith("FOR UPDATE")
            return SimpleNamespace(
                scalar_one_or_none=lambda: tenant if is_tenant else existing
            )

        def add(user):
            scope()
            if fail == "add":
                raise RuntimeError(fail)
            inserted.append(user)

        async def commit():
            nonlocal transaction
            scope()
            events.append("commit")
            if fail == "commit":
                raise RuntimeError(fail)
            transaction = False

        async def refresh(user):
            begin()
            events.append("refresh")
            if fail == "refresh":
                raise RuntimeError(fail)
            assert user.tenant_id == A

        async def exit_session(*args):
            scope()
            events.append("exit")
            return None

        db.__aenter__.side_effect = enter
        db.__aexit__.side_effect = exit_session
        db.execute.side_effect = execute
        db.add.side_effect = add
        db.commit.side_effect = commit
        db.refresh.side_effect = refresh
        factory = MagicMock(return_value=db)
        monkeypatch.setattr(cli, "async_session", factory)
        digest = uuid4().hex
        hasher = AsyncMock(return_value=digest)
        if fail == "hash":
            hasher.side_effect = RuntimeError(fail)
        revoker = AsyncMock(return_value=2)
        if fail == "revoke":
            revoker.side_effect = RuntimeError(fail)
        monkeypatch.setattr(cli, "get_password_hash", hasher)
        monkeypatch.setattr(cli, "revoke_sessions_matching", revoker)
        real_run = asyncio.run

        def run(coro):
            async def check():
                tenant_token = tenant_id_ctx.set(ambient)
                bypass_token = bypass_rls_ctx.set(bypass)
                try:
                    try:
                        return await coro
                    finally:
                        assert get_current_tenant() == ambient
                        assert get_bypass_rls() == bypass
                        events.append("restored")
                finally:
                    bypass_rls_ctx.reset(bypass_token)
                    tenant_id_ctx.reset(tenant_token)

            return real_run(check())

        monkeypatch.setattr(cli.asyncio, "run", run)
        result = CliRunner().invoke(cli.app, ["create-admin", "--password", "newpass"])
        return SimpleNamespace(
            result=result,
            db=db,
            factory=factory,
            hasher=hasher,
            revoker=revoker,
            gucs=gucs,
            inserted=inserted,
            events=events,
            statements=statements,
            digest=digest,
        )

    return build


@pytest.mark.parametrize("ambient", ["", str(B)])
@pytest.mark.parametrize("bypass", [False, True])
def test_new_admin_scopes_first_lookup_and_post_commit_refresh(
    harness, ambient, bypass
):
    state = harness(ambient=ambient, bypass=bypass)
    assert state.result.exit_code == 0, state.result.exception
    assert state.inserted[0].tenant_id == A
    assert state.gucs == [{"tenant_id": str(A)}, {"tenant_id": str(A)}]
    assert state.events == ["enter", "commit", "refresh", "exit", "restored"]
    state.revoker.assert_not_awaited()


def test_existing_owner_resets_in_place_without_duplicate(harness):
    owner = SimpleNamespace(
        id=uuid4(), tenant_id=A, hashed_password=uuid4().hex, mfa_epoch=3
    )
    state = harness(existing=owner, ambient=str(B), bypass=True)
    assert state.result.exit_code == 0, state.result.exception
    assert owner.hashed_password == state.digest
    assert owner.mfa_epoch == 4
    assert not state.inserted
    state.revoker.assert_awaited_once()
    state.db.refresh.assert_not_awaited()
    assert state.gucs == [{"tenant_id": str(A)}]


@pytest.mark.parametrize("owner", [B, None])
def test_foreign_or_unowned_returned_row_cannot_be_reset(harness, owner):
    original = uuid4().hex
    user = SimpleNamespace(
        id=uuid4(), tenant_id=owner, hashed_password=original, mfa_epoch=3
    )
    state = harness(existing=user)
    assert state.result.exit_code != 0
    assert "tenant" in str(state.result.exception).lower()
    assert user.hashed_password == original
    assert user.mfa_epoch == 3
    state.hasher.assert_not_awaited()
    state.revoker.assert_not_awaited()
    state.db.commit.assert_not_awaited()


@pytest.mark.parametrize("configured", [None, "invalid"])
def test_invalid_configuration_fails_before_session(harness, configured):
    state = harness(configured=configured)
    assert state.result.exit_code != 0
    state.factory.assert_not_called()
    state.hasher.assert_not_awaited()
    assert state.events == ["restored"]


@pytest.mark.parametrize("tenant", [None, B])
def test_missing_inactive_or_wrong_persisted_tenant_rejected(harness, tenant):
    state = harness(tenant=tenant, ambient=str(B), bypass=True)
    assert state.result.exit_code != 0
    assert len(state.statements) == 1
    state.hasher.assert_not_awaited()
    state.db.add.assert_not_called()
    state.db.commit.assert_not_awaited()
    assert state.events[-1] == "restored"


@pytest.mark.parametrize(
    "fail", ["enter", "lookup", "add", "hash", "commit", "refresh"]
)
def test_failure_restores_caller_scope(harness, fail):
    state = harness(fail=fail, ambient=str(B), bypass=True)
    assert isinstance(state.result.exception, RuntimeError)
    assert str(state.result.exception) == fail
    assert state.events[-1] == "restored"


@pytest.mark.parametrize("fail", ["hash", "revoke", "commit"])
def test_reset_failure_restores_caller_scope(harness, fail):
    owner = SimpleNamespace(
        id=uuid4(), tenant_id=A, hashed_password=uuid4().hex, mfa_epoch=3
    )
    state = harness(existing=owner, fail=fail, ambient=str(B), bypass=True)
    assert isinstance(state.result.exception, RuntimeError)
    assert str(state.result.exception) == fail
    assert state.events[-1] == "restored"
    state.db.refresh.assert_not_awaited()


@pytest.fixture
def sqlite_cli(tmp_path, monkeypatch):
    """Real SQL constraints/transactions, deliberately no PostgreSQL RLS claim."""
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.pool import NullPool

    from app.core.database import Base
    from app.models import ActiveSession, Group, User
    from app.models.tenant import Tenant
    from app.models.users import UserProfile

    engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'cli.sqlite'}", poolclass=NullPool
    )
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def setup():
        async with engine.begin() as connection:
            await connection.run_sync(
                Base.metadata.create_all,
                tables=[
                    Tenant.__table__,
                    Group.__table__,
                    User.__table__,
                    UserProfile.__table__,
                    ActiveSession.__table__,
                ],
            )
        async with factory() as session:
            session.add_all(
                [Tenant(id=A, name="A", slug="a"), Tenant(id=B, name="B", slug="b")]
            )
            await session.commit()

    asyncio.run(setup())
    monkeypatch.setattr(cli.settings, "mvp_tenant_id", A)
    monkeypatch.setattr(cli, "async_session", factory)
    hasher = AsyncMock(return_value=uuid4().hex)
    revoker = AsyncMock(return_value=0)
    monkeypatch.setattr(cli, "get_password_hash", hasher)
    monkeypatch.setattr(cli, "revoke_sessions_matching", revoker)
    try:
        yield SimpleNamespace(
            factory=factory, engine=engine, hasher=hasher, revoker=revoker
        )
    finally:
        asyncio.run(engine.dispose())


def invoke_admin():
    return CliRunner().invoke(cli.app, ["create-admin", "--password", "newpass"])


@pytest.mark.parametrize("owner", [B, None])
def test_real_unique_email_rejects_foreign_or_null_owner_without_mutation(
    sqlite_cli, owner
):
    from datetime import UTC, datetime, timedelta

    from sqlalchemy import select
    from sqlalchemy.exc import IntegrityError

    from app.models import ActiveSession, User

    original = uuid4().hex

    async def setup():
        async with sqlite_cli.factory() as session:
            user = User(
                email="admin@example.com",
                tenant_id=owner,
                hashed_password=original,
                mfa_epoch=3,
            )
            session.add(user)
            await session.flush()
            active = ActiveSession(
                user_id=user.id,
                jti=str(uuid4()),
                expires_at=datetime.now(UTC) + timedelta(hours=1),
            )
            session.add(active)
            await session.commit()
            return user.id, active.id

    user_id, active_id = asyncio.run(setup())
    result = invoke_admin()
    assert isinstance(result.exception, IntegrityError)
    sqlite_cli.revoker.assert_not_awaited()

    async def check():
        async with sqlite_cli.factory() as session:
            users = list((await session.execute(select(User))).scalars())
            assert len(users) == 1
            assert users[0].id == user_id
            assert users[0].tenant_id == owner
            assert users[0].hashed_password == original
            assert users[0].mfa_epoch == 3
            active = await session.get(ActiveSession, active_id)
            assert active is not None and active.revoked_at is None

    asyncio.run(check())


@pytest.mark.parametrize("state", ["missing", "inactive"])
def test_real_persisted_tenant_must_exist_and_be_active(sqlite_cli, state):
    from sqlalchemy import delete, select, update

    from app.models import User
    from app.models.tenant import Tenant

    async def disable():
        async with sqlite_cli.factory() as session:
            statement = (
                delete(Tenant).where(Tenant.id == A)
                if state == "missing"
                else update(Tenant).where(Tenant.id == A).values(is_active=False)
            )
            await session.execute(statement)
            await session.commit()

    asyncio.run(disable())
    result = invoke_admin()
    assert isinstance(result.exception, ValueError)
    sqlite_cli.hasher.assert_not_awaited()
    sqlite_cli.revoker.assert_not_awaited()

    async def check():
        async with sqlite_cli.factory() as session:
            assert (await session.execute(select(User))).scalar_one_or_none() is None

    asyncio.run(check())


def test_real_create_then_reset_preserves_single_owner(sqlite_cli):
    from sqlalchemy import select

    from app.models import User

    first = invoke_admin()
    assert first.exit_code == 0, first.exception

    async def identity():
        async with sqlite_cli.factory() as session:
            user = (await session.execute(select(User))).scalar_one()
            return user.id, user.tenant_id, user.mfa_epoch

    before = asyncio.run(identity())
    second = invoke_admin()
    assert second.exit_code == 0, second.exception
    after = asyncio.run(identity())
    assert after == (before[0], A, before[2] + 1)
    sqlite_cli.revoker.assert_awaited_once()


def test_real_refresh_failure_is_after_durable_create(sqlite_cli, monkeypatch):
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from app.models import User

    class FailedRefresh(AsyncSession):
        async def refresh(self, instance, *args, **kwargs):
            assert get_current_tenant() == str(A)
            assert not get_bypass_rls()
            raise RuntimeError("refresh")

    monkeypatch.setattr(
        cli,
        "async_session",
        async_sessionmaker(
            sqlite_cli.engine, class_=FailedRefresh, expire_on_commit=False
        ),
    )
    result = invoke_admin()
    assert isinstance(result.exception, RuntimeError)
    assert str(result.exception) == "refresh"

    async def check():
        async with sqlite_cli.factory() as session:
            user = (await session.execute(select(User))).scalar_one()
            assert user.tenant_id == A

    asyncio.run(check())
