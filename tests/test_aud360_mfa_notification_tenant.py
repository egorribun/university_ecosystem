"""Real notification producer with a recording transaction (not PostgreSQL proof)."""

from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.sql.dml import Insert

from app.core.tenant import bypass_rls_ctx, get_current_tenant, tenant_id_ctx
from app.management import reset_mfa
from app.models.domain_events import StoredEvent
from app.services.notifications import delivery


class RecordingSession:
    """Record the real helper's SQL and GUC at its insert; do not emulate RLS."""

    def __init__(self, user, scope, failure=None):
        self.user = user
        self.scope = scope
        self.original_scope = scope
        self.failure = failure
        self.inserts = []
        self.events = []
        self.operations = []

    def get_bind(self):
        return SimpleNamespace(dialect=SimpleNamespace(name="postgresql"))

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return None

    async def get(self, *_):
        return self.user

    async def execute(self, statement, params=None):
        sql = str(statement)
        if "current_setting" in sql:
            return SimpleNamespace(scalar_one_or_none=lambda: self.scope)
        if "set_config" in sql:
            value = params["tenant_id"]
            if self.failure == "restore" and value == self.original_scope:
                raise SQLAlchemyError("restore failed")
            self.scope = value
            return None
        assert isinstance(statement, Insert)
        assert statement.table.name == "notifications"
        self.inserts.append(
            (
                self.scope,
                get_current_tenant(),
                statement.compile(dialect=postgresql.dialect()).params,
            )
        )
        self.operations.append("notification")
        if self.failure == "insert":
            raise SQLAlchemyError("insert failed")
        return None

    def add(self, item):
        assert isinstance(item, StoredEvent)
        self.events.append(item)

    async def flush(self):
        return None

    async def commit(self):
        self.operations.append("commit")
        if self.failure == "commit":
            raise SQLAlchemyError("commit failed")

    async def rollback(self):
        self.operations.append("rollback")


def prepare(monkeypatch, owner, scope, failure=None, changed=True):
    user = SimpleNamespace(id=uuid4(), tenant_id=owner)
    session = RecordingSession(user, scope, failure)
    monkeypatch.setattr(reset_mfa, "async_session", lambda: session)
    monkeypatch.setattr(reset_mfa, "resolve_locale", lambda **_: "en")
    monkeypatch.setattr(reset_mfa, "_audit_cli", lambda *_, **__: None)
    monkeypatch.setattr(delivery, "_is_push_configured", lambda: False)
    stats = SimpleNamespace(
        changed=changed, session_revocations=[], totp_deleted=0, challenges_revoked=0
    )

    async def reset(*_, **__):
        session.operations.append("reset")
        return stats

    async def publish(_):
        session.operations.append("publish")
        if failure == "publish":
            raise RuntimeError("publish failed")

    monkeypatch.setattr(reset_mfa.mfa, "reset_user_mfa", reset)
    monkeypatch.setattr(reset_mfa.mfa, "publish_mfa_session_revocations", publish)
    # Deliberately leave reset_mfa.create_notifications_for_users unmocked.
    assert (
        reset_mfa.create_notifications_for_users
        is delivery.create_notifications_for_users
    )
    return session


@pytest.mark.asyncio
@pytest.mark.parametrize("ambient", ["empty", "foreign"])
@pytest.mark.parametrize("bypass", [False, True])
async def test_mfa_real_notification_binds_target_not_ambient(
    monkeypatch, ambient, bypass
):
    owner = uuid4()
    scope = "" if ambient == "empty" else str(uuid4())
    session = prepare(monkeypatch, owner, scope)
    token = tenant_id_ctx.set(scope)
    bypass_token = bypass_rls_ctx.set(bypass)
    try:
        await reset_mfa._reset_user_mfa(
            user_id=session.user.id, email=None, notify=True
        )
        assert len(session.inserts) == 1
        database_scope, captured_scope, params = session.inserts[0]
        assert database_scope == captured_scope == str(owner)
        assert params["user_id_m0"] == session.user.id
        assert len(session.events) == 1
        assert session.events[0].metadata_ == {"tenant_id": str(owner)}
        assert session.scope == scope
        assert get_current_tenant() == scope
        assert bypass_rls_ctx.get() is bypass
        assert session.operations == ["reset", "notification", "publish", "commit"]
    finally:
        bypass_rls_ctx.reset(bypass_token)
        tenant_id_ctx.reset(token)


@pytest.mark.asyncio
async def test_mfa_null_owner_never_inherits_foreign_scope(monkeypatch):
    scope = str(uuid4())
    session = prepare(monkeypatch, None, scope)
    token = tenant_id_ctx.set(scope)
    try:
        with pytest.raises(ValueError, match="tenant"):
            await reset_mfa._reset_user_mfa(
                user_id=session.user.id, email=None, notify=True
            )
        assert session.inserts == session.events == []
        assert "publish" not in session.operations
        assert session.operations[-1] == "rollback"
        assert session.scope == get_current_tenant() == scope
    finally:
        tenant_id_ctx.reset(token)


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["insert", "restore", "publish", "commit"])
async def test_mfa_notification_failure_rolls_back_and_restores_context(
    monkeypatch, failure
):
    owner, scope = uuid4(), str(uuid4())
    session = prepare(monkeypatch, owner, scope, failure)
    token = tenant_id_ctx.set(scope)
    bypass_token = bypass_rls_ctx.set(True)
    try:
        with pytest.raises((SQLAlchemyError, RuntimeError), match=f"{failure} failed"):
            await reset_mfa._reset_user_mfa(
                user_id=session.user.id, email=None, notify=True
            )
        assert session.operations[-1] == "rollback"
        assert get_current_tenant() == scope
        assert bypass_rls_ctx.get() is True
        if failure != "restore":
            assert session.scope == scope
        if failure in {"insert", "restore"}:
            assert "publish" not in session.operations
        if failure != "commit":
            assert "commit" not in session.operations
    finally:
        bypass_rls_ctx.reset(bypass_token)
        tenant_id_ctx.reset(token)


@pytest.mark.asyncio
@pytest.mark.parametrize(("notify", "changed"), [(False, True), (True, False)])
async def test_mfa_no_notification_preserves_unowned_legacy_behavior(
    monkeypatch, notify, changed
):
    session = prepare(monkeypatch, None, "", changed=changed)
    await reset_mfa._reset_user_mfa(user_id=session.user.id, email=None, notify=notify)
    assert session.inserts == session.events == []
    assert session.operations == ["reset", "publish", "commit"]


@pytest.mark.asyncio
async def test_mfa_context_and_database_scope_restore_independently(monkeypatch):
    owner, ambient = uuid4(), str(uuid4())
    session = prepare(monkeypatch, owner, "")
    token = tenant_id_ctx.set(ambient)
    try:
        await reset_mfa._reset_user_mfa(
            user_id=session.user.id, email=None, notify=True
        )
        assert session.inserts[0][:2] == (str(owner), str(owner))
        assert session.events[0].metadata_ == {"tenant_id": str(owner)}
        assert session.scope == ""
        assert get_current_tenant() == ambient
    finally:
        tenant_id_ctx.reset(token)


@pytest.mark.asyncio
@pytest.mark.parametrize("dialect", ["sqlite", "unsupported"])
async def test_mfa_notification_dialect_contract(monkeypatch, dialect):
    owner = uuid4()
    session = prepare(monkeypatch, owner, "")
    session.get_bind = lambda: SimpleNamespace(dialect=SimpleNamespace(name=dialect))
    if dialect == "unsupported":
        with pytest.raises(RuntimeError, match="Unsupported"):
            await reset_mfa._reset_user_mfa(
                user_id=session.user.id, email=None, notify=True
            )
        assert session.inserts == session.events == []
        assert session.operations[-1] == "rollback"
    else:
        await reset_mfa._reset_user_mfa(
            user_id=session.user.id, email=None, notify=True
        )
        assert session.inserts[0][1] == str(owner)
        assert session.events[0].metadata_ == {"tenant_id": str(owner)}
        assert session.scope == ""


@pytest.mark.asyncio
async def test_mfa_original_insert_error_survives_restore_failure(monkeypatch):
    scope = str(uuid4())
    session = prepare(monkeypatch, uuid4(), scope, "restore")
    execute = session.execute
    original = SQLAlchemyError("original insert failure")

    async def fail_insert(statement, params=None):
        if isinstance(statement, Insert):
            raise original
        return await execute(statement, params)

    session.execute = fail_insert
    token = tenant_id_ctx.set(scope)
    try:
        with pytest.raises(SQLAlchemyError) as caught:
            await reset_mfa._reset_user_mfa(
                user_id=session.user.id, email=None, notify=True
            )
        assert caught.value is original
        assert caught.value.__notes__ == [
            "Tenant context restoration failed; roll back the transaction"
        ]
        assert session.operations == ["reset", "rollback"]
        assert get_current_tenant() == scope
        assert session.events == []
    finally:
        tenant_id_ctx.reset(token)


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["current_setting", "set_config"])
async def test_mfa_scope_setup_failure_cannot_reach_notification(
    monkeypatch, operation
):
    scope = str(uuid4())
    session = prepare(monkeypatch, uuid4(), scope)
    execute = session.execute
    original = SQLAlchemyError("scope setup failed")

    async def fail_setup(statement, params=None):
        if operation in str(statement) and (
            params is None or params["tenant_id"] != scope
        ):
            raise original
        return await execute(statement, params)

    session.execute = fail_setup
    token = tenant_id_ctx.set(scope)
    bypass_token = bypass_rls_ctx.set(True)
    try:
        with pytest.raises(SQLAlchemyError) as caught:
            await reset_mfa._reset_user_mfa(
                user_id=session.user.id, email=None, notify=True
            )
        assert caught.value is original
        assert session.inserts == session.events == []
        assert session.operations == ["reset", "rollback"]
        assert session.scope == get_current_tenant() == scope
        assert bypass_rls_ctx.get() is True
    finally:
        bypass_rls_ctx.reset(bypass_token)
        tenant_id_ctx.reset(token)


@pytest.mark.asyncio
async def test_concurrent_mfa_notification_scopes_are_task_local(monkeypatch):
    import asyncio

    monkeypatch.setattr(delivery, "_is_push_configured", lambda: False)
    sessions = [
        RecordingSession(SimpleNamespace(id=uuid4()), str(uuid4())) for _ in range(2)
    ]
    owners = [uuid4(), uuid4()]
    ready = asyncio.Event()
    arrived = 0

    async def run(session, owner):
        nonlocal arrived
        ambient = session.scope
        token = tenant_id_ctx.set(ambient)
        bypass_token = bypass_rls_ctx.set(True)
        execute = session.execute

        async def overlap(statement, params=None):
            nonlocal arrived
            if isinstance(statement, Insert):
                arrived += 1
                if arrived == 2:
                    ready.set()
                await ready.wait()
            return await execute(statement, params)

        session.execute = overlap
        try:
            async with reset_mfa._notification_tenant_scope(session, owner):
                await delivery.create_notifications_for_users(
                    session, title="reset", user_ids=[session.user.id]
                )
            assert session.inserts[0][:2] == (str(owner), str(owner))
            assert session.events[0].metadata_ == {"tenant_id": str(owner)}
            assert session.scope == get_current_tenant() == ambient
            assert bypass_rls_ctx.get() is True
        finally:
            bypass_rls_ctx.reset(bypass_token)
            tenant_id_ctx.reset(token)

    await asyncio.wait_for(
        asyncio.gather(*(run(s, t) for s, t in zip(sessions, owners, strict=True))),
        timeout=2,
    )
    assert arrived == 2


@pytest.mark.asyncio
async def test_cancelled_real_notification_restores_both_scopes(monkeypatch):
    import asyncio

    scope = str(uuid4())
    session = prepare(monkeypatch, uuid4(), scope)
    entered = asyncio.Event()
    execute = session.execute
    restored = []

    async def block_insert(statement, params=None):
        if isinstance(statement, Insert):
            entered.set()
            await asyncio.Future()
        return await execute(statement, params)

    session.execute = block_insert

    async def run():
        token = tenant_id_ctx.set(scope)
        bypass_token = bypass_rls_ctx.set(True)
        try:
            await reset_mfa._reset_user_mfa(
                user_id=session.user.id, email=None, notify=True
            )
        finally:
            restored.append((get_current_tenant(), bypass_rls_ctx.get()))
            bypass_rls_ctx.reset(bypass_token)
            tenant_id_ctx.reset(token)

    task = asyncio.create_task(run())
    await asyncio.wait_for(entered.wait(), timeout=2)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert session.scope == scope
    assert restored == [(scope, True)]
    assert session.events == []
    assert "publish" not in session.operations
    assert "commit" not in session.operations
