"""Actual MVP baseline tenant, role, message-participant and trigger enforcement."""

from __future__ import annotations

import contextlib
import datetime as dt
import os
import uuid
from collections.abc import Iterator
from types import SimpleNamespace

import pytest
import sqlalchemy as sa
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.db.listeners import set_pg_tenant_context
from app.core.tenant import bypass_rls_ctx, tenant_id_ctx
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
        reason="Set RUN_INTEGRATION_TESTS=1 to run",
    ),
]
_CORE_TABLES = (
    "users",
    "groups",
    "schedule",
    "events",
    "chats",
    "messages",
    "news",
    "stories",
    "notifications",
)
_TENANT_A = uuid.UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
_TENANT_B = uuid.UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")
_USER_A = uuid.UUID("11111111-1111-4111-8111-111111111111")
_CHAT_A = uuid.UUID("22222222-2222-4222-8222-222222222222")
_CHAT_B = uuid.UUID("33333333-3333-4333-8333-333333333333")
# Every baseline table that carries tenant_id under forced RLS and the stamping trigger.
_TENANT_TABLES = (
    "chats",
    "events",
    "groups",
    "messages",
    "news",
    "notifications",
    "schedule",
    "stories",
    "users",
)


def _engine(url: sa.URL) -> sa.Engine:
    return sa.create_engine(
        url,
        poolclass=sa.pool.NullPool,
        hide_parameters=True,
        connect_args={"connect_timeout": 5},
    )


@pytest.fixture(scope="module")
def rls_schema(request: pytest.FixtureRequest) -> Iterator[SimpleNamespace]:
    assert request.config.getoption("timeout_disable_debugger_detection", False), (
        "Tenant RLS tests require --timeout-disable-debugger-detection"
    )
    server = request.getfixturevalue("owned_baseline_server")
    with owned.committed_baseline(server) as baseline:
        ordinary_role = "tenant_reader_" + uuid.uuid4().hex
        bypass_role = "tenant_member_" + uuid.uuid4().hex
        credential = uuid.uuid4().hex + uuid.uuid4().hex
        admin = _engine(baseline.url)
        try:
            with admin.begin() as connection:
                # Generated identifiers and hex credential belong only to this owned server.
                for role in (ordinary_role, bypass_role):
                    connection.exec_driver_sql(
                        f"CREATE ROLE \"{role}\" LOGIN NOSUPERUSER NOBYPASSRLS NOINHERIT PASSWORD '{credential}'"
                    )
                    connection.exec_driver_sql(
                        f'GRANT USAGE ON SCHEMA public TO "{role}"'
                    )
                    connection.exec_driver_sql(
                        f'GRANT SELECT, INSERT, UPDATE, DELETE ON public.news, public.messages, public.notifications TO "{role}"'
                    )
                    connection.exec_driver_sql(
                        f'GRANT SELECT ON public.chat_participants TO "{role}"'
                    )
                connection.exec_driver_sql(f'GRANT ue_rls_bypass TO "{bypass_role}"')
                connection.exec_driver_sql(
                    f'GRANT SELECT ON public.groups, public.schedule, public.users, public.tenants, public.user_push_topics TO "{bypass_role}"'
                )
                connection.exec_driver_sql(
                    f'GRANT SELECT, INSERT ON public.stored_events TO "{bypass_role}"'
                )
                # The CLI uses the ordinary role: no additional bypass membership.
                connection.exec_driver_sql(
                    f'GRANT SELECT ON public.tenants TO "{ordinary_role}"'
                )
                connection.exec_driver_sql(
                    f'GRANT SELECT, INSERT, UPDATE ON public.user_profiles, public.active_sessions TO "{ordinary_role}"'
                )
                connection.exec_driver_sql(
                    f'GRANT SELECT, DELETE ON public.push_subscriptions TO "{ordinary_role}"'
                )
                for table in _CORE_TABLES:
                    connection.exec_driver_sql(
                        f'ALTER TABLE public.{table} OWNER TO "{ordinary_role}"'
                    )
                for tenant, name in ((_TENANT_A, "a"), (_TENANT_B, "b")):
                    connection.execute(
                        sa.text(
                            "INSERT INTO tenants (id, name, slug) VALUES (:id, :name, :name)"
                        ),
                        {"id": tenant, "name": name},
                    )
                connection.execute(
                    sa.text(
                        "INSERT INTO users (id, email, hashed_password, tenant_id) VALUES (:id, 'tenant@example.invalid', :credential, :tenant)"
                    ),
                    {
                        "id": _USER_A,
                        "credential": "!" + uuid.uuid4().hex,
                        "tenant": _TENANT_A,
                    },
                )
                for chat in (_CHAT_A, _CHAT_B):
                    connection.execute(
                        sa.text(
                            "INSERT INTO chats (id, tenant_id) VALUES (:id, :tenant)"
                        ),
                        {"id": chat, "tenant": _TENANT_A},
                    )
                connection.execute(
                    sa.text(
                        "INSERT INTO chat_participants (chat_id, user_id) VALUES (:c, :u)"
                    ),
                    {"c": _CHAT_A, "u": _USER_A},
                )
                for identifier, tenant in ((1, _TENANT_A), (2, _TENANT_B), (3, None)):
                    connection.execute(
                        sa.text(
                            "INSERT INTO news (id, title, content, tenant_id) VALUES (:id, 'RLS', 'proof', :tenant)"
                        ),
                        {"id": uuid.UUID(int=identifier), "tenant": tenant},
                    )
                for identifier, tenant, chat in (
                    (11, _TENANT_A, _CHAT_A),
                    (12, _TENANT_B, _CHAT_A),
                    (13, None, _CHAT_A),
                    (14, _TENANT_A, _CHAT_B),
                ):
                    connection.execute(
                        sa.text(
                            "INSERT INTO messages (id, content, sender_id, chat_id, tenant_id) VALUES (:id, 'RLS proof', :u, :c, :tenant)"
                        ),
                        {
                            "id": uuid.UUID(int=identifier),
                            "u": _USER_A,
                            "c": chat,
                            "tenant": tenant,
                        },
                    )
            state = SimpleNamespace(
                admin=baseline.url,
                ordinary=baseline.url.set(username=ordinary_role, password=credential),
                bypass=baseline.url.set(username=bypass_role, password=credential),
            )
            for url, member in ((state.ordinary, False), (state.bypass, True)):
                with _rolled_back(url) as connection:
                    assert tuple(
                        connection.execute(
                            sa.text(
                                "SELECT rolsuper, rolbypassrls, pg_has_role(current_user, 'ue_rls_bypass', 'MEMBER') FROM pg_roles WHERE rolname = current_user"
                            )
                        ).one()
                    ) == (False, False, member)
                    assert (
                        connection.scalar(
                            sa.text("SELECT row_security_active('public.news')")
                        )
                        is True
                    )
            yield state
        finally:
            admin.dispose()


@contextlib.contextmanager
def _rolled_back(url: sa.URL) -> Iterator[Connection]:
    engine = _engine(url)
    try:
        with engine.connect() as connection:
            transaction = connection.begin()
            try:
                yield connection
            finally:
                if transaction.is_active:
                    transaction.rollback()
    finally:
        engine.dispose()


@contextlib.contextmanager
def _application_context(
    connection: Connection, *, tenant: uuid.UUID | None, bypass: bool = False
) -> Iterator[None]:
    """Apply the application's own session wiring for the given request scope."""
    tenant_token = tenant_id_ctx.set(str(tenant) if tenant else "")
    bypass_token = bypass_rls_ctx.set(bypass)
    try:
        set_pg_tenant_context(None, None, connection)
        yield
    finally:
        bypass_rls_ctx.reset(bypass_token)
        tenant_id_ctx.reset(tenant_token)


def _ids(connection: Connection, table: str) -> set[int]:
    statement = sa.select(sa.column("id")).select_from(sa.table(table))
    return {value.int for value in connection.execute(statement).scalars()}


def test_no_permissive_true_policy_remains_on_core_tables(
    rls_schema: SimpleNamespace,
) -> None:
    with _rolled_back(rls_schema.ordinary) as connection:
        policies = connection.execute(
            sa.text(
                "SELECT tablename, policyname, permissive, qual FROM pg_policies "
                "WHERE schemaname = current_schema() AND tablename = ANY(:tables)"
            ),
            {"tables": list(_CORE_TABLES)},
        ).all()
    assert not [row for row in policies if row.qual == "true"]
    assert not [
        row for row in policies if row.policyname == "default_permissive_policy"
    ]
    tenant = {
        row.tablename: row.permissive
        for row in policies
        if row.policyname == "tenant_isolation_policy"
    }
    assert set(tenant) == set(_CORE_TABLES)
    assert tenant["messages"] == "RESTRICTIVE"
    assert {tenant[t] for t in _CORE_TABLES if t != "messages"} == {"PERMISSIVE"}


def test_tenant_session_sees_only_its_rows_and_never_null_rows(
    rls_schema: SimpleNamespace,
) -> None:
    """AUD-360: NULL-tenant rows are hidden, and another tenant's rows stay hidden."""
    with _rolled_back(rls_schema.ordinary) as connection:
        with _application_context(connection, tenant=_TENANT_A):
            assert _ids(connection, "news") == {1}
    with _rolled_back(rls_schema.ordinary) as connection:
        with _application_context(connection, tenant=None):
            assert _ids(connection, "news") == set()


def test_guc_bypass_cannot_expose_other_tenants_or_null_rows(
    rls_schema: SimpleNamespace,
) -> None:
    """AUD-450: a hand-set app.bypass_rls GUC grants nothing, and the listener never sets it."""
    with _rolled_back(rls_schema.ordinary) as connection:
        with _application_context(connection, tenant=_TENANT_A):
            connection.execute(
                sa.text("SELECT set_config('app.bypass_rls', 'on', true)")
            )
            assert _ids(connection, "news") == {1}
    with _rolled_back(rls_schema.ordinary) as connection:
        with _application_context(connection, tenant=None, bypass=True):
            # The listener's bypass flag writes no GUC, so the setting stays unset.
            assert (
                connection.execute(
                    sa.text(
                        "SELECT coalesce(current_setting('app.bypass_rls', true), '')"
                    )
                ).scalar()
                == ""
            )
            assert _ids(connection, "news") == set()


def test_dedicated_bypass_role_member_sees_every_row(
    rls_schema: SimpleNamespace,
) -> None:
    """AUD-450 positive control: only membership in ue_rls_bypass bypasses the policy."""
    with _rolled_back(rls_schema.bypass) as connection:
        with _application_context(connection, tenant=None):
            assert _ids(connection, "news") == {1, 2, 3}


def test_ordinary_writes_are_stamped_with_the_session_tenant(
    rls_schema: SimpleNamespace,
) -> None:
    """AUD-360: an ORM-shaped INSERT that omits tenant_id is stamped by the trigger."""
    with _rolled_back(rls_schema.ordinary) as connection:
        with _application_context(connection, tenant=_TENANT_A):
            connection.execute(
                sa.text(
                    "INSERT INTO news (id, title, content) VALUES ('00000000-0000-0000-0000-000000000014', 'stamp', 'orm')"
                )
            )
            connection.execute(
                sa.text(
                    "INSERT INTO news (id, tenant_id, title, content) VALUES ('00000000-0000-0000-0000-000000000015', NULL, 'stamp', 'null')"
                )
            )
            # Message inserts also need the participant context the ORM sets.
            connection.execute(
                sa.text("SELECT set_config('app.current_user_id', :u, true)"),
                {"u": str(_USER_A)},
            )
            connection.execute(
                sa.text(
                    "INSERT INTO messages (id, chat_id, sender_id, content) VALUES ('00000000-0000-0000-0000-000000000016', :c, :u, 'm')"
                ),
                {"c": _CHAT_A, "u": _USER_A},
            )
            stamped = dict(
                connection.execute(
                    sa.text(
                        "SELECT id, tenant_id FROM news WHERE id IN ('00000000-0000-0000-0000-000000000014', '00000000-0000-0000-0000-000000000015')"
                    )
                ).all()
            )
            assert stamped == {
                uuid.UUID(int=20): _TENANT_A,
                uuid.UUID(int=21): _TENANT_A,
            }
            assert (
                connection.execute(
                    sa.text(
                        "SELECT tenant_id FROM messages WHERE id = '00000000-0000-0000-0000-000000000016'"
                    )
                ).scalar()
                == _TENANT_A
            )


@pytest.mark.asyncio
async def test_news_service_producer_is_stamped_and_rls_scoped(
    rls_schema: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AUD-360: the mapped News producer is owned by its transaction tenant."""
    from unittest.mock import MagicMock

    from app.core.db.listeners import register_tenant_listeners
    from app.core.tenant import bypass_rls_ctx, tenant_id_ctx
    from app.models.news import News
    from app.repositories.unit_of_work import uow_from_session
    from app.schemas import schemas
    from app.services.news_service import NewsService
    from app.services.vector_service import VectorService

    def suppress_outbox_event(_self: News, _event: object) -> None:
        return None

    monkeypatch.setattr(News, "record_event", suppress_outbox_event)
    register_tenant_listeners()
    engine = create_async_engine(
        rls_schema.ordinary.set(drivername="postgresql+asyncpg", query={}),
        poolclass=sa.pool.NullPool,
        hide_parameters=True,
        connect_args={"timeout": 5},
    )
    tenant_token = tenant_id_ctx.set(str(_TENANT_A))
    bypass_token = bypass_rls_ctx.set(False)
    news_id: uuid.UUID | None = None
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as session:
            service = NewsService(
                uow_from_session(session), vector_service=MagicMock(spec=VectorService)
            )
            record = await service.create_news(
                schemas.NewsCreate(
                    title="AUD-360 service ownership", content="trigger proof"
                )
            )
            news_id = record.id
    finally:
        bypass_rls_ctx.reset(bypass_token)
        tenant_id_ctx.reset(tenant_token)
        await engine.dispose()

    try:
        assert news_id is not None
        with _rolled_back(rls_schema.admin) as connection:
            owner = connection.execute(
                sa.text("SELECT tenant_id FROM news WHERE id = :id"),
                {"id": news_id},
            ).scalar_one_or_none()
        assert owner == _TENANT_A

        for tenant, expected in ((_TENANT_A, news_id), (_TENANT_B, None)):
            with _rolled_back(rls_schema.ordinary) as connection:
                with _application_context(connection, tenant=tenant):
                    visible = connection.execute(
                        sa.text("SELECT id FROM news WHERE id = :id"),
                        {"id": news_id},
                    ).scalar_one_or_none()
            assert visible == expected
    finally:
        if news_id is not None:
            cleanup_engine = _engine(rls_schema.admin)
            try:
                with cleanup_engine.begin() as connection:
                    connection.execute(
                        sa.text("DELETE FROM news WHERE id = :id"),
                        {"id": news_id},
                    )
            finally:
                cleanup_engine.dispose()


def test_writes_cannot_target_another_tenant_or_escape_the_session(
    rls_schema: SimpleNamespace,
) -> None:
    with _rolled_back(rls_schema.ordinary) as connection:
        with _application_context(connection, tenant=_TENANT_A):
            with pytest.raises(sa.exc.DBAPIError) as rejected:
                with connection.begin_nested():
                    connection.execute(
                        sa.text(
                            "INSERT INTO news (id, tenant_id, title, content) VALUES ('00000000-0000-0000-0000-00000000001e', :b, 'deny', 'x')"
                        ),
                        {"b": _TENANT_B},
                    )
            assert rejected.value.orig.sqlstate == "42501"
            with pytest.raises(sa.exc.DBAPIError) as rejected:
                with connection.begin_nested():
                    connection.execute(
                        sa.text(
                            "UPDATE news SET tenant_id = :b WHERE id = '00000000-0000-0000-0000-000000000001'"
                        ),
                        {"b": _TENANT_B},
                    )
            assert rejected.value.orig.sqlstate == "42501"
            with pytest.raises(sa.exc.DBAPIError) as rejected:
                with connection.begin_nested():
                    connection.execute(
                        sa.text(
                            "UPDATE news SET tenant_id = NULL WHERE id = '00000000-0000-0000-0000-000000000001'"
                        )
                    )
            assert rejected.value.orig.sqlstate == "42501"
    with _rolled_back(rls_schema.ordinary) as connection:
        # Without a tenant context an INSERT is refused rather than stored unowned.
        with _application_context(connection, tenant=None):
            with pytest.raises(sa.exc.DBAPIError) as rejected:
                with connection.begin_nested():
                    connection.execute(
                        sa.text(
                            "INSERT INTO news (id, title, content) VALUES ('00000000-0000-0000-0000-00000000001f', 'deny', 'x')"
                        )
                    )

            assert rejected.value.orig.sqlstate == "42501"


def test_messages_need_both_participation_and_the_session_tenant(
    rls_schema: SimpleNamespace,
) -> None:
    with _rolled_back(rls_schema.ordinary) as connection:
        with _application_context(connection, tenant=_TENANT_A):
            connection.execute(
                sa.text("SELECT set_config('app.current_user_id', :u, true)"),
                {"u": str(_USER_A)},
            )
            # Participant of chat A and tenant A: only 11. Row 12 is tenant B,
            # row 13 has a NULL tenant, and row 14 belongs to chat B.
            assert _ids(connection, "messages") == {11}


def test_every_tenant_table_forces_rls_and_stamps_unowned_inserts(
    rls_schema: SimpleNamespace,
) -> None:
    """AUD-360: each tenant-scoped table is forced under RLS and fills NULL tenants."""
    with _rolled_back(rls_schema.ordinary) as connection:
        rows = connection.execute(
            sa.text(
                "SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity, "
                "EXISTS (SELECT 1 FROM pg_trigger t WHERE t.tgrelid = c.oid "
                "AND t.tgname = 'ue_rls_assign_tenant' AND NOT t.tgisinternal "
                "AND t.tgenabled = 'O') AS stamps "
                "FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
                "WHERE n.nspname = 'public' AND c.relname = ANY(:tables)"
            ),
            {"tables": list(_TENANT_TABLES)},
        ).all()
    assert {row.relname for row in rows} == set(_TENANT_TABLES)
    assert all(
        row.relrowsecurity and row.relforcerowsecurity and row.stamps for row in rows
    )


def test_notification_producer_rows_are_owned_by_the_session_tenant(
    rls_schema: SimpleNamespace,
) -> None:
    """AUD-360: a producer insert without tenant is stamped; an unscoped one is refused."""
    notification = uuid.UUID(int=40)
    with _rolled_back(rls_schema.ordinary) as connection:
        with _application_context(connection, tenant=_TENANT_A):
            connection.execute(
                sa.text(
                    "INSERT INTO notifications (id, user_id, title, read, created_at) "
                    "VALUES (:id, :u, 'stamp', false, now())"
                ),
                {"id": notification, "u": _USER_A},
            )
            assert (
                connection.execute(
                    sa.text("SELECT tenant_id FROM notifications WHERE id = :id"),
                    {"id": notification},
                ).scalar()
                == _TENANT_A
            )
    with _rolled_back(rls_schema.ordinary) as connection:
        with _application_context(connection, tenant=None):
            with pytest.raises(sa.exc.DBAPIError) as rejected:
                with connection.begin_nested():
                    connection.execute(
                        sa.text(
                            "INSERT INTO notifications (id, user_id, title, read, created_at) "
                            "VALUES (:id, :u, 'deny', false, now())"
                        ),
                        {"id": uuid.UUID(int=41), "u": _USER_A},
                    )
            assert rejected.value.orig.sqlstate == "42501"


def test_worker_bypass_producer_must_write_its_tenant_explicitly(
    rls_schema: SimpleNamespace,
) -> None:
    """AUD-360: under bypass no session tenant exists, so the producer's tenant_id is the owner."""
    explicit, unowned = uuid.UUID(int=42), uuid.UUID(int=43)
    with _rolled_back(rls_schema.bypass) as connection:
        with _application_context(connection, tenant=None, bypass=True):
            connection.execute(
                sa.text(
                    "INSERT INTO notifications (id, user_id, title, read, created_at, tenant_id) "
                    "VALUES (:id, :u, 'owned', false, now(), :t)"
                ),
                {"id": explicit, "u": _USER_A, "t": _TENANT_B},
            )
            connection.execute(
                sa.text(
                    "INSERT INTO notifications (id, user_id, title, read, created_at) "
                    "VALUES (:id, :u, 'orphan', false, now())"
                ),
                {"id": unowned, "u": _USER_A},
            )
            owners = dict(
                connection.execute(
                    sa.text(
                        "SELECT id, tenant_id FROM notifications WHERE id = ANY(:ids)"
                    ),
                    {"ids": [explicit, unowned]},
                ).all()
            )
    assert owners[explicit] == _TENANT_B
    # Recorded residual: a bypass write without tenant_id stays unowned, and the
    # tenant-scoped policy hides it from every tenant. Producers must write it.
    assert owners[unowned] is None


@pytest.mark.asyncio
async def test_bypass_scheduler_persists_owned_reminders_and_outbox_events(
    rls_schema: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Exercise the actual worker against two tenants and invalid ownership."""
    from app.core.config import settings
    from app.core.db.listeners import register_tenant_listeners
    from app.services.notifications import delivery, schedule_reminders
    from app.workers import notifications as worker

    inactive = uuid.uuid4()
    groups = [uuid.uuid4() for _ in range(5)]
    users = [uuid.uuid4() for _ in range(7)]
    lessons = [uuid.uuid4() for _ in range(5)]
    stale = [uuid.uuid4(), uuid.uuid4()]
    fixed_now = dt.datetime(2026, 1, 4, 23, 55, tzinfo=dt.UTC)
    group_tenants = (_TENANT_A, _TENANT_B, None, _TENANT_B, inactive)
    lesson_tenants = (_TENANT_A, _TENANT_B, None, _TENANT_A, inactive)
    user_assignments = (
        (groups[0], _TENANT_A),
        (groups[1], _TENANT_B),
        (groups[0], _TENANT_B),
        (groups[0], None),
        (groups[2], _TENANT_A),
        (groups[3], _TENANT_A),
        (groups[4], inactive),
    )

    admin = _engine(rls_schema.admin)
    try:
        with admin.begin() as connection:
            connection.execute(
                sa.text(
                    "INSERT INTO tenants (id, name, slug, is_active) VALUES (:id, 'inactive', :slug, false)"
                ),
                {"id": inactive, "slug": inactive.hex},
            )
            for group, tenant in zip(groups, group_tenants, strict=True):
                connection.execute(
                    sa.text(
                        "INSERT INTO groups (id, name, tenant_id) VALUES (:id, 'group', :tenant)"
                    ),
                    {"id": group, "tenant": tenant},
                )
            for user, (group, tenant) in zip(users, user_assignments, strict=True):
                connection.execute(
                    sa.text(
                        "INSERT INTO users (id, email, hashed_password, group_id, tenant_id) "
                        "VALUES (:id, :email, '!', :group_id, :tenant)"
                    ),
                    {
                        "id": user,
                        "email": f"{user.hex}@example.invalid",
                        "group_id": group,
                        "tenant": tenant,
                    },
                )
            for lesson, group, tenant in zip(
                lessons, groups, lesson_tenants, strict=True
            ):
                connection.execute(
                    sa.text(
                        "INSERT INTO schedule (id, group_id, tenant_id, subject, weekday, start_time, end_time) "
                        "VALUES (:id, :group_id, :tenant, 'lesson', 'monday', "
                        "'1970-01-05 03:00:00+00', '1970-01-05 04:00:00+00')"
                    ),
                    {"id": lesson, "group_id": group, "tenant": tenant},
                )
            # These are the same user/key pairs as the due reminders, but one
            # row is unowned and the other belongs to the wrong tenant.
            for identifier, user, lesson, tenant in zip(
                stale, users[:2], lessons[:2], (None, _TENANT_A), strict=True
            ):
                connection.execute(
                    sa.text(
                        "INSERT INTO notifications "
                        "(id, user_id, tenant_id, title, url, dedupe_key, created_at) "
                        "VALUES (:id, :user_id, :tenant, 'stale', '/schedule', :key, :created)"
                    ),
                    {
                        "id": identifier,
                        "user_id": user,
                        "tenant": tenant,
                        "key": f"schedule-reminder:{lesson}",
                        "created": fixed_now,
                    },
                )

        class FixedDateTime(dt.datetime):
            @classmethod
            def now(cls, tz=None):
                return (
                    fixed_now.replace(tzinfo=None)
                    if tz is None
                    else fixed_now.astimezone(tz)
                )

        clock = SimpleNamespace(**vars(dt))
        clock.datetime = FixedDateTime
        monkeypatch.setattr(schedule_reminders, "dt", clock)
        monkeypatch.setattr(delivery, "dt", clock)
        monkeypatch.setattr(delivery, "_is_push_configured", lambda: False)
        monkeypatch.setattr(settings, "campus_timezone", "Europe/Istanbul")
        monkeypatch.setattr(settings, "mvp_tenant_id", _TENANT_B)
        register_tenant_listeners()

        worker_url = rls_schema.bypass.set(drivername="postgresql+asyncpg", query={})
        engine = create_async_engine(
            worker_url, poolclass=sa.pool.NullPool, hide_parameters=True
        )
        try:
            monkeypatch.setattr(
                worker,
                "async_session",
                async_sessionmaker(engine, expire_on_commit=False),
            )
            scheduler = worker.NotificationsScheduler(
                poll_seconds=1, window_minutes=10, max_backoff_seconds=1
            )
            assert await scheduler.run_once() == 2
            assert await scheduler.run_once() == 0
        finally:
            await engine.dispose()

        with admin.connect() as connection:
            rows = connection.execute(
                sa.text(
                    "SELECT id, user_id, tenant_id, dedupe_key FROM notifications WHERE user_id = ANY(:ids)"
                ),
                {"ids": users},
            ).all()
            new_rows = [row for row in rows if row.id not in stale]
            assert len(rows) == 4
            assert {(row.user_id, row.tenant_id) for row in new_rows} == {
                (users[0], _TENANT_A),
                (users[1], _TENANT_B),
            }
            assert {row.dedupe_key for row in new_rows} == {
                row.dedupe_key for row in rows if row.id in stale
            }
            events = connection.execute(
                sa.text(
                    "SELECT payload, metadata FROM stored_events WHERE event_type = 'notification.delivery_requested'"
                )
            ).all()
        assert len(events) == 2
        owners_by_notification = {str(row.id): str(row.tenant_id) for row in new_rows}
        assert {
            (event.payload["notification_ids"][0], event.metadata["tenant_id"])
            for event in events
        } == set(owners_by_notification.items())

        for tenant, expected_user in ((_TENANT_A, users[0]), (_TENANT_B, users[1])):
            with _rolled_back(rls_schema.ordinary) as connection:
                with _application_context(connection, tenant=tenant):
                    visible = (
                        connection.execute(
                            sa.text(
                                "SELECT user_id FROM notifications WHERE id = ANY(:ids)"
                            ),
                            {"ids": [row.id for row in new_rows]},
                        )
                        .scalars()
                        .all()
                    )
            assert visible == [expected_user]
    finally:
        admin.dispose()


def test_transaction_local_bypass_guc_is_cleared_by_rollback_on_same_backend(
    rls_schema: SimpleNamespace,
) -> None:
    """AUD-450: rollback clears caller-set local bypass GUC on a reused backend."""
    engine = _engine(rls_schema.ordinary)
    try:
        with engine.connect() as connection:
            first_transaction = connection.begin()
            first_backend = connection.scalar(sa.text("SELECT pg_backend_pid()"))
            try:
                with _application_context(connection, tenant=_TENANT_A):
                    connection.execute(
                        sa.text("SELECT set_config('app.bypass_rls', 'on', true)")
                    )
                    assert (
                        connection.execute(
                            sa.text("SELECT current_setting('app.bypass_rls', true)")
                        ).scalar_one()
                        == "on"
                    )
                    # The ordinary role cannot turn a caller-controlled GUC into
                    # cross-tenant or NULL-tenant visibility.
                    assert _ids(connection, "news") == {1}
            finally:
                if first_transaction.is_active:
                    first_transaction.rollback()

            with connection.begin():
                second_backend, bypass_setting = connection.execute(
                    sa.text(
                        "SELECT pg_backend_pid(), "
                        "coalesce(current_setting('app.bypass_rls', true), '')"
                    )
                ).one()
                assert second_backend == first_backend
                assert bypass_setting == ""
                with _application_context(connection, tenant=_TENANT_A):
                    assert _ids(connection, "news") == {1}
    finally:
        engine.dispose()


# Private batch addition: policy OR/AND causal discriminator.
def test_permissive_true_causality_depends_on_restrictive_tenant_policy(
    rls_schema: SimpleNamespace,
) -> None:
    """Separate permissive OR behavior from messages' restrictive tenant gate.

    The current canonical baseline is the input. This does not reconstruct or
    claim the removed historical migration's exact policy catalog.
    """
    with _rolled_back(rls_schema.ordinary) as connection:
        policies = connection.execute(
            sa.text(
                "SELECT tablename, policyname, permissive, qual "
                "FROM pg_policies WHERE schemaname = current_schema() "
                "AND tablename = ANY(:tables)"
            ),
            {"tables": list(_CORE_TABLES)},
        ).all()
        tenant_policies = {
            row.tablename: row.permissive
            for row in policies
            if row.policyname == "tenant_isolation_policy"
        }
        assert set(tenant_policies) == set(_CORE_TABLES)
        assert tenant_policies["news"] == "PERMISSIVE"
        assert tenant_policies["messages"] == "RESTRICTIVE"
        assert not any(
            row.qual is not None and row.qual.strip().casefold() == "true"
            for row in policies
        )

        # The existing tenant predicate, null-row handling, and GUC control are
        # distinct from the deliberately added permissive policy below.
        with _application_context(connection, tenant=_TENANT_A):
            assert _ids(connection, "news") == {1}
        with _application_context(connection, tenant=None):
            assert _ids(connection, "news") == set()
        with _application_context(connection, tenant=_TENANT_A):
            connection.execute(
                sa.text("SELECT set_config('app.bypass_rls', 'on', true)")
            )
            assert _ids(connection, "news") == {1}

        # A permissive TRUE policy joins the permissive-policy OR set. On news,
        # the current permissive tenant policy cannot constrain that result.
        connection.exec_driver_sql(
            "CREATE POLICY aud277_true_control ON public.news "
            "AS PERMISSIVE USING (true)"
        )
        # On messages, the independent restrictive tenant policy remains an
        # AND gate. TRUE widens participant visibility within tenant A only.
        connection.exec_driver_sql(
            "CREATE POLICY aud277_true_control ON public.messages "
            "AS PERMISSIVE USING (true)"
        )

        with _application_context(connection, tenant=_TENANT_A):
            assert _ids(connection, "news") == {1, 2, 3}
            connection.execute(
                sa.text("SELECT set_config('app.current_user_id', :user, true)"),
                {"user": str(_USER_A)},
            )
            assert _ids(connection, "messages") == {11, 14}

        # _rolled_back() rolls back both CREATE POLICY mutations. An actual
        # owned-PostgreSQL run is required before treating these expectations as
        # observed behavior or using this to classify the removed history.


@pytest.mark.asyncio
@pytest.mark.parametrize("ambient", ["", str(_TENANT_B)])
@pytest.mark.parametrize("owned_target", [True, False])
async def test_mfa_reset_real_producer_uses_target_owner_under_bypass(
    rls_schema: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
    ambient: str,
    owned_target: bool,
) -> None:
    """Actual helper/trigger/outbox, with target ownership independent of ambient B."""
    from app.management import reset_mfa
    from app.services.notifications import delivery

    target_id = uuid.uuid4()
    target_tenant = _TENANT_A if owned_target else None
    admin = _engine(rls_schema.admin)
    with admin.begin() as connection:
        connection.execute(
            sa.text(
                "INSERT INTO users (id, email, hashed_password, tenant_id) VALUES (:id, :email, :credential, :tenant)"
            ),
            {
                "id": target_id,
                "email": f"{target_id}@mfa.invalid",
                "credential": "!" + uuid.uuid4().hex,
                "tenant": target_tenant,
            },
        )
    from app.core.db.listeners import register_tenant_listeners

    register_tenant_listeners()
    engine = create_async_engine(
        rls_schema.bypass.set(drivername="postgresql+asyncpg", query={}),
        poolclass=sa.pool.NullPool,
        hide_parameters=True,
        connect_args={"timeout": 5},
    )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    session = session_factory()
    monkeypatch.setattr(reset_mfa, "async_session", lambda: session)
    monkeypatch.setattr(reset_mfa, "resolve_locale", lambda **_: "en")
    monkeypatch.setattr(reset_mfa, "_audit_cli", lambda *_, **__: None)
    monkeypatch.setattr(delivery, "_is_push_configured", lambda: False)

    # Isolate the MFA mutation from this producer proof; never mock the notifier.
    async def reset(*_, **__):
        return SimpleNamespace(
            changed=True, session_revocations=[], totp_deleted=0, challenges_revoked=0
        )

    restored = []

    async def publish(_):
        restored.append(
            await session.scalar(
                sa.text("SELECT current_setting('app.current_tenant', true)")
            )
        )

    monkeypatch.setattr(reset_mfa.mfa, "reset_user_mfa", reset)
    monkeypatch.setattr(reset_mfa.mfa, "publish_mfa_session_revocations", publish)
    assert (
        reset_mfa.create_notifications_for_users
        is delivery.create_notifications_for_users
    )
    tenant_token = tenant_id_ctx.set(ambient)
    bypass_token = bypass_rls_ctx.set(False)
    try:
        if owned_target:
            await reset_mfa._reset_user_mfa(user_id=target_id, email=None, notify=True)
            assert restored == [ambient]
        else:
            with pytest.raises(ValueError, match="tenant"):
                await reset_mfa._reset_user_mfa(
                    user_id=target_id, email=None, notify=True
                )
            assert restored == []
        assert tenant_id_ctx.get() == ambient
        assert bypass_rls_ctx.get() is False
        with admin.connect() as connection:
            rows = connection.execute(
                sa.text("SELECT id, tenant_id FROM notifications WHERE user_id = :id"),
                {"id": target_id},
            ).all()
            if not owned_target:
                assert rows == []
            else:
                assert len(rows) == 1
                notification_id, tenant = rows[0]
                assert tenant == _TENANT_A
                metadata = connection.execute(
                    sa.text(
                        "SELECT metadata FROM stored_events WHERE CAST(payload AS jsonb) -> 'notification_ids' @> CAST(:ids AS jsonb)"
                    ),
                    {"ids": '["' + str(notification_id) + '"]'},
                ).scalar_one()
                assert metadata == {"tenant_id": str(_TENANT_A)}
                for visible_tenant, count in (
                    (_TENANT_A, 1),
                    (_TENANT_B, 0),
                    (None, 0),
                ):
                    with _rolled_back(rls_schema.ordinary) as ordinary:
                        with _application_context(ordinary, tenant=visible_tenant):
                            assert (
                                ordinary.scalar(
                                    sa.text(
                                        "SELECT count(*) FROM notifications WHERE id = :id"
                                    ),
                                    {"id": notification_id},
                                )
                                == count
                            )
    finally:
        bypass_rls_ctx.reset(bypass_token)
        tenant_id_ctx.reset(tenant_token)
        await session.close()
        await engine.dispose()
        admin.dispose()


@contextlib.asynccontextmanager
async def _admin_cli(rls_schema, monkeypatch, *, configured=_TENANT_A):
    """Run the actual CLI coroutine against the ordinary owned PostgreSQL role."""
    from unittest.mock import AsyncMock

    from app.cli import db as cli
    from app.core.db.listeners import register_tenant_listeners

    register_tenant_listeners()
    engine = create_async_engine(
        rls_schema.ordinary.set(drivername="postgresql+asyncpg", query={}),
        poolclass=sa.pool.NullPool,
        hide_parameters=True,
        connect_args={"timeout": 5},
    )
    maker = async_sessionmaker(engine, expire_on_commit=False)
    scopes = []
    sessions = []

    def session_factory():
        assert tenant_id_ctx.get() == str(configured)
        assert bypass_rls_ctx.get() is False
        session = maker()
        sessions.append(session)

        def record(_session, _transaction, connection):
            assert tenant_id_ctx.get() == str(configured)
            assert bypass_rls_ctx.get() is False
            assert tuple(
                connection.execute(
                    sa.text(
                        "SELECT rolsuper, rolbypassrls, "
                        "pg_has_role(current_user, 'ue_rls_bypass', 'MEMBER'), "
                        "row_security_active('public.users') "
                        "FROM pg_roles WHERE rolname = current_user"
                    )
                ).one()
            ) == (False, False, False, True)
            scopes.append(
                connection.scalar(
                    sa.text("SELECT current_setting('app.current_tenant', true)")
                )
            )

        sa.event.listen(session.sync_session, "after_begin", record)
        return session

    captured = []
    monkeypatch.setattr(cli, "asyncio", SimpleNamespace(run=captured.append))
    monkeypatch.setattr(cli, "async_session", session_factory)
    monkeypatch.setattr(cli.settings, "mvp_tenant_id", configured)
    digest = uuid.uuid4().hex
    hasher = AsyncMock(return_value=digest)
    monkeypatch.setattr(cli, "get_password_hash", hasher)
    backend = AsyncMock()
    monkeypatch.setattr(
        "app.services.session_cleanup.get_session_backend",
        AsyncMock(return_value=backend),
    )

    async def run(email):
        before = (tenant_id_ctx.get(), bypass_rls_ctx.get())
        cli.create_admin(
            email=email, password=uuid.uuid4().hex, full_name="Tenant test"
        )
        assert len(captured) == 1
        try:
            await captured.pop()
        finally:
            assert (tenant_id_ctx.get(), bypass_rls_ctx.get()) == before

    try:
        yield SimpleNamespace(
            run=run,
            scopes=scopes,
            sessions=sessions,
            hasher=hasher,
            backend=backend,
            digest=digest,
        )
    finally:
        for session in sessions:
            await session.close()
        await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize("ambient", ["", str(_TENANT_B)], ids=["empty", "foreign"])
async def test_create_admin_real_producer_scopes_create_and_reset(
    rls_schema, monkeypatch, ambient
):
    identifier = uuid.uuid4()
    email = f"{identifier}@admin.invalid"
    admin = _engine(rls_schema.admin)
    tenant_token = tenant_id_ctx.set(ambient)
    bypass_token = bypass_rls_ctx.set(True)
    try:
        async with _admin_cli(rls_schema, monkeypatch) as cli:
            await cli.run(email)
            with admin.begin() as connection:
                user = connection.execute(
                    sa.text(
                        "SELECT id, tenant_id, mfa_epoch, hashed_password FROM users WHERE email = :email"
                    ),
                    {"email": email},
                ).one()
                assert user.tenant_id == _TENANT_A
                active_id = uuid.uuid4()
                jti = str(uuid.uuid4())
                connection.execute(
                    sa.text(
                        "INSERT INTO active_sessions (id, user_id, jti, expires_at, signing_key) VALUES (:id, :user, :jti, :expires, :key)"
                    ),
                    {
                        "id": active_id,
                        "user": user.id,
                        "jti": jti,
                        "key": uuid.uuid4().hex,
                        "expires": dt.datetime.now(dt.UTC) + dt.timedelta(hours=1),
                    },
                )
            assert user.hashed_password == cli.digest
            replacement = uuid.uuid4().hex
            assert replacement != user.hashed_password
            cli.hasher.return_value = replacement
            await cli.run(email)
            assert cli.scopes == [str(_TENANT_A)] * 3  # lookup, refresh, reset lookup
            cli.backend.revoke_session.assert_awaited_once()
            assert cli.backend.revoke_session.await_args.args == (jti,)
            with admin.connect() as connection:
                rows = connection.execute(
                    sa.text(
                        "SELECT id, tenant_id, mfa_epoch, hashed_password FROM users WHERE email = :email"
                    ),
                    {"email": email},
                ).all()
                assert len(rows) == 1
                assert tuple(rows[0]) == (
                    user.id,
                    _TENANT_A,
                    user.mfa_epoch + 1,
                    replacement,
                )
                assert (
                    connection.scalar(
                        sa.text(
                            "SELECT revoked_at IS NOT NULL FROM active_sessions WHERE id = :id"
                        ),
                        {"id": active_id},
                    )
                    is True
                )
            for tenant, count in ((_TENANT_A, 1), (_TENANT_B, 0), (None, 0)):
                with _rolled_back(rls_schema.ordinary) as connection:
                    with _application_context(connection, tenant=tenant):
                        assert (
                            connection.scalar(
                                sa.text("SELECT count(*) FROM users WHERE id = :id"),
                                {"id": user.id},
                            )
                            == count
                        )
    finally:
        bypass_rls_ctx.reset(bypass_token)
        tenant_id_ctx.reset(tenant_token)
        admin.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize("owner", [_TENANT_B, None], ids=["foreign", "null"])
async def test_create_admin_real_producer_rejects_foreign_email(
    rls_schema, monkeypatch, owner
):
    user_id, active_id = uuid.uuid4(), uuid.uuid4()
    email = f"{user_id}@admin.invalid"
    digest = uuid.uuid4().hex
    admin = _engine(rls_schema.admin)
    tenant_token = tenant_id_ctx.set(str(_TENANT_B))
    bypass_token = bypass_rls_ctx.set(True)
    try:
        with admin.begin() as connection:
            connection.execute(
                sa.text(
                    "INSERT INTO users (id, email, hashed_password, tenant_id, mfa_epoch) VALUES (:id, :email, :digest, :tenant, 3)"
                ),
                {"id": user_id, "email": email, "digest": digest, "tenant": owner},
            )
            connection.execute(
                sa.text(
                    "INSERT INTO active_sessions (id, user_id, jti, expires_at, signing_key) VALUES (:id, :user, :jti, :expires, :key)"
                ),
                {
                    "id": active_id,
                    "user": user_id,
                    "jti": str(uuid.uuid4()),
                    "key": uuid.uuid4().hex,
                    "expires": dt.datetime.now(dt.UTC) + dt.timedelta(hours=1),
                },
            )
        async with _admin_cli(rls_schema, monkeypatch) as cli:
            with pytest.raises(sa.exc.IntegrityError):
                await cli.run(email)
            assert cli.scopes == [str(_TENANT_A)]
            cli.backend.revoke_session.assert_not_awaited()
        with admin.connect() as connection:
            assert tuple(
                connection.execute(
                    sa.text(
                        "SELECT id, tenant_id, hashed_password, mfa_epoch FROM users WHERE email = :email"
                    ),
                    {"email": email},
                ).one()
            ) == (user_id, owner, digest, 3)
            assert (
                connection.scalar(
                    sa.text("SELECT revoked_at FROM active_sessions WHERE id = :id"),
                    {"id": active_id},
                )
                is None
            )
    finally:
        bypass_rls_ctx.reset(bypass_token)
        tenant_id_ctx.reset(tenant_token)
        admin.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize("state", ["missing", "inactive"])
async def test_create_admin_real_producer_requires_active_tenant(
    rls_schema, monkeypatch, state
):
    configured = uuid.uuid4()
    email = f"{configured}@admin.invalid"
    admin = _engine(rls_schema.admin)
    try:
        if state == "inactive":
            with admin.begin() as connection:
                connection.execute(
                    sa.text(
                        "INSERT INTO tenants (id, name, slug, is_active) VALUES (:id, :name, :name, false)"
                    ),
                    {"id": configured, "name": configured.hex},
                )
        async with _admin_cli(rls_schema, monkeypatch, configured=configured) as cli:
            with pytest.raises(ValueError, match="active"):
                await cli.run(email)
            cli.hasher.assert_not_awaited()
            assert cli.scopes == [str(configured)]
        with admin.connect() as connection:
            assert (
                connection.scalar(
                    sa.text("SELECT count(*) FROM users WHERE email = :email"),
                    {"email": email},
                )
                == 0
            )
    finally:
        admin.dispose()


@pytest.mark.asyncio
async def test_create_admin_real_producer_rejects_unconfigured_tenant(
    rls_schema, monkeypatch
):
    async with _admin_cli(rls_schema, monkeypatch, configured=None) as cli:
        with pytest.raises(ValueError, match="configured tenant"):
            await cli.run(f"{uuid.uuid4()}@admin.invalid")
        assert cli.sessions == []
        assert cli.scopes == []
        cli.hasher.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "ambient", ["", str(_TENANT_A), str(_TENANT_B)], ids=["empty", "a", "b"]
)
@pytest.mark.parametrize("bypass", [False, True], ids=["normal", "python-bypass"])
async def test_weekly_cleanup_preserves_rls_hidden_subscriptions(
    rls_schema, monkeypatch, ambient, bypass
):
    from app.core.db.listeners import register_tenant_listeners
    from app.management import weekly_cleanup

    admin = _engine(rls_schema.admin)
    engine = create_async_engine(
        rls_schema.ordinary.set(drivername="postgresql+asyncpg", query={}),
        poolclass=sa.pool.NullPool,
        hide_parameters=True,
        connect_args={"timeout": 5},
    )
    owners = (_TENANT_A, _TENANT_B, None)
    users = [uuid.uuid4() for _ in owners]
    subscriptions = [uuid.uuid4() for _ in owners]
    fresh = dt.datetime.now(dt.UTC)
    sql = []
    gucs = []
    register_tenant_listeners()

    @sa.event.listens_for(engine.sync_engine, "before_cursor_execute")
    def record_sql(_connection, _cursor, statement, _parameters, _context, _many):
        sql.append(statement)

    maker = async_sessionmaker(engine, expire_on_commit=False)

    def factory():
        session = maker()

        @sa.event.listens_for(session.sync_session, "after_begin")
        def record(_session, _transaction, connection):
            role = connection.execute(
                sa.text(
                    "SELECT rolsuper, rolbypassrls, pg_has_role(current_user, 'ue_rls_bypass', 'MEMBER'), row_security_active('public.users') FROM pg_roles WHERE rolname = current_user"
                )
            ).one()
            assert tuple(role) == (False, False, False, True)
            gucs.append(
                connection.scalar(
                    sa.text(
                        "SELECT coalesce(current_setting('app.current_tenant', true), '')"
                    )
                )
            )

        return session

    tenant_token = tenant_id_ctx.set(ambient)
    bypass_token = bypass_rls_ctx.set(bypass)
    try:
        with admin.begin() as connection:
            for user, subscription, owner in zip(
                users, subscriptions, owners, strict=True
            ):
                connection.execute(
                    sa.text(
                        "INSERT INTO users (id, email, hashed_password, tenant_id) VALUES (:id, :email, :digest, :owner)"
                    ),
                    {
                        "id": user,
                        "email": f"{user}@cleanup.invalid",
                        "digest": uuid.uuid4().hex,
                        "owner": owner,
                    },
                )
                connection.execute(
                    sa.text(
                        "INSERT INTO push_subscriptions (id, user_id, endpoint, p256dh, auth, last_seen_at) VALUES (:id, :user, :endpoint, :value, :value, :fresh)"
                    ),
                    {
                        "id": subscription,
                        "user": user,
                        "endpoint": f"https://{subscription}.invalid",
                        "value": uuid.uuid4().hex,
                        "fresh": fresh,
                    },
                )
        monkeypatch.setattr(weekly_cleanup, "async_session", factory)
        async with factory() as session:
            visible = (
                (
                    await session.execute(
                        sa.text("SELECT id FROM users WHERE id = ANY(:ids)"),
                        {"ids": users},
                    )
                )
                .scalars()
                .all()
            )
            expected = (
                []
                if bypass or not ambient
                else [users[0] if ambient == str(_TENANT_A) else users[1]]
            )
            assert visible == expected
            assert await weekly_cleanup._delete_orphaned_subscriptions(session) == 0
        assert await weekly_cleanup.run_weekly_cleanup() == {
            "subscriptions_removed": 0,
            "subscriptions_orphaned": 0,
            "subscriptions_stale": 0,
        }
        assert tenant_id_ctx.get() == ambient
        assert bypass_rls_ctx.get() is bypass
        assert gucs == ["" if bypass else ambient] * 2
        assert not any("user_id not in" in statement.lower() for statement in sql)
        with admin.connect() as connection:
            rows = connection.execute(
                sa.text(
                    "SELECT id, user_id, last_seen_at FROM push_subscriptions WHERE id = ANY(:ids)"
                ),
                {"ids": subscriptions},
            ).all()
            assert {(row.id, row.user_id, row.last_seen_at) for row in rows} == set(
                zip(subscriptions, users, [fresh] * 3, strict=True)
            )
    finally:
        bypass_rls_ctx.reset(bypass_token)
        tenant_id_ctx.reset(tenant_token)
        await engine.dispose()
        admin.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize("drift", ["missing-fk", "shadow-child", "shadow-parent"])
async def test_weekly_cleanup_schema_drift_rejects_before_stale_delete(
    rls_schema, monkeypatch, drift
):
    from unittest.mock import AsyncMock

    from app.core.db.listeners import register_tenant_listeners
    from app.management import weekly_cleanup

    register_tenant_listeners()
    engine = create_async_engine(
        rls_schema.admin.set(drivername="postgresql+asyncpg", query={}),
        poolclass=sa.pool.NullPool,
        hide_parameters=True,
        connect_args={"timeout": 5},
    )
    statements = []
    committed = []
    stale = AsyncMock(side_effect=AssertionError("stale cleanup must not run"))
    monkeypatch.setattr(weekly_cleanup, "_delete_stale_subscriptions", stale)
    tenant_token = tenant_id_ctx.set(str(_TENANT_A))
    bypass_token = bypass_rls_ctx.set(False)
    try:
        async with engine.connect() as connection:
            transaction = await connection.begin()
            try:
                await connection.execute(sa.text("SET LOCAL lock_timeout = '5s'"))
                await connection.execute(sa.text("SET LOCAL statement_timeout = '10s'"))
                if drift == "missing-fk":
                    await connection.execute(
                        sa.text(
                            "ALTER TABLE public.push_subscriptions DROP CONSTRAINT fk_push_subscriptions_user_id"
                        )
                    )
                elif drift == "shadow-child":
                    await connection.execute(
                        sa.text(
                            "CREATE TEMP TABLE push_subscriptions (id uuid, user_id uuid)"
                        )
                    )
                else:
                    await connection.execute(
                        sa.text("CREATE TEMP TABLE users (id uuid)")
                    )
                # Own the DDL and guard on one connection: no second connection
                # waits on an uncommitted ACCESS EXCLUSIVE table lock.
                role = rls_schema.ordinary.username
                assert role is not None and role.startswith("tenant_reader_")
                await connection.exec_driver_sql(f'SET LOCAL ROLE "{role}"')
                actual_role = (
                    await connection.execute(
                        sa.text(
                            "SELECT rolsuper, rolbypassrls, pg_has_role(current_user, 'ue_rls_bypass', 'MEMBER'), row_security_active('public.users') FROM pg_roles WHERE rolname = current_user"
                        )
                    )
                ).one()
                assert tuple(actual_role) == (False, False, False, True)
                maker = async_sessionmaker(
                    bind=connection,
                    expire_on_commit=False,
                    join_transaction_mode="create_savepoint",
                )

                def factory():
                    session = maker()
                    sa.event.listen(
                        session.sync_session,
                        "after_commit",
                        lambda _session: committed.append(True),
                    )
                    return session

                @sa.event.listens_for(
                    connection.sync_connection, "before_cursor_execute"
                )
                def capture(
                    _connection, _cursor, statement, _parameters, _context, _many
                ):
                    statements.append(statement)

                monkeypatch.setattr(weekly_cleanup, "async_session", factory)
                with pytest.raises(RuntimeError, match="foreign key"):
                    await weekly_cleanup.run_weekly_cleanup()
                stale.assert_not_awaited()
                assert committed == []
                assert not any(
                    statement.lstrip().lower().startswith("delete")
                    for statement in statements
                )
                assert tenant_id_ctx.get() == str(_TENANT_A)
                assert bypass_rls_ctx.get() is False
            finally:
                await transaction.rollback()
            # Transactional DDL and SET ROLE must be gone before fixture reuse.
            assert (
                await connection.scalar(
                    sa.text(
                        "SELECT EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid = 'public.push_subscriptions'::regclass AND conname = 'fk_push_subscriptions_user_id' AND convalidated)"
                    )
                )
                is True
            )
            assert (
                await connection.scalar(
                    sa.text(
                        "SELECT to_regclass('push_subscriptions') = to_regclass('public.push_subscriptions') AND to_regclass('users') = to_regclass('public.users')"
                    )
                )
                is True
            )
    finally:
        bypass_rls_ctx.reset(bypass_token)
        tenant_id_ctx.reset(tenant_token)
        await engine.dispose()
