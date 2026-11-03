"""Plain chat sends and reads run as the NOBYPASSRLS runtime role (ue_app).

Production runs the API as ue_app with the DML grants from
infrastructure/postgres-roles/bootstrap-app-roles.sql. The hosted integration
job connects as the PostgreSQL image's superuser, which bypasses RLS, so these
tests create ue_app on an owned, disposable baseline server and drive the real
ChatMessageDispatcher through it without an Idempotency-Key.
"""

from __future__ import annotations

import contextlib
import os
import uuid
from collections.abc import AsyncIterator, Iterator
from types import SimpleNamespace
from typing import cast

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.core.db.listeners import register_tenant_listeners
from app.core.events import register_event_listeners
from app.core.tenant import set_current_tenant, tenant_id_ctx
from app.models import User
from app.repositories.unit_of_work import uow_from_session
from app.services.chat.command_service import (
    AttachmentProcessorProtocol,
    ChatMessageDispatcher,
)
from app.services.chat.notification_service import ChatNotificationService
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
    pytest.mark.timeout(300),
    pytest.mark.skipif(
        os.getenv("RUN_INTEGRATION_TESTS") != "1",
        reason="Set RUN_INTEGRATION_TESTS=1 to run",
    ),
]
_RUNTIME_ROLE = "ue_app"
_TENANT = uuid.UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
_SENDER = uuid.UUID("22222222-2222-4222-8222-222222222222")
_PEER = uuid.UUID("33333333-3333-4333-8333-333333333333")
_CHAT = uuid.UUID("44444444-4444-4444-8444-444444444444")
_SEED_MESSAGE = uuid.UUID("55555555-5555-4555-8555-555555555555")


class _NoAttachments:
    async def process_upload(self, *_args: object, **_kwargs: object) -> None:
        raise AssertionError("no uploads in this test")

    async def cleanup_files(self, _urls: list[str]) -> None:
        return None


class _NoNotify:
    async def notify_new_message(self, *_args: object, **_kwargs: object) -> None:
        return None


def _create_runtime_role(connection: sa.Connection, credential: str) -> None:
    """Build the production-shaped ue_app login from the shared helper."""
    for statement in runtime_role_statements(_RUNTIME_ROLE, credential):
        connection.exec_driver_sql(statement)
    flags = connection.execute(
        sa.text(RUNTIME_ROLE_FLAGS_QUERY), {"role": _RUNTIME_ROLE}
    ).one()
    assert tuple(flags) == (False, False, False), "runtime role must not bypass RLS"


def _seed(connection: sa.Connection) -> None:
    """Insert a tenant, two participants, a DM and one message as the superuser."""
    connection.execute(
        sa.text(
            "INSERT INTO tenants (id, name, slug) VALUES (:id, 'send rls', 'send-rls')"
        ),
        {"id": _TENANT},
    )
    for user_id, email in (
        (_SENDER, "send-a@example.invalid"),
        (_PEER, "send-b@example.invalid"),
    ):
        connection.execute(
            sa.text(
                "INSERT INTO users (id, email, hashed_password, is_active, role, "
                "mfa_required, mfa_epoch, tenant_id) VALUES (:id, :email, 'x', true, "
                "'student', false, 0, :tenant)"
            ),
            {"id": user_id, "email": email, "tenant": _TENANT},
        )
    connection.execute(
        sa.text(
            "INSERT INTO chats (id, chat_type, tenant_id, created_by) "
            "VALUES (:id, 'dm', :tenant, :creator)"
        ),
        {"id": _CHAT, "tenant": _TENANT, "creator": _SENDER},
    )
    for user_id in (_SENDER, _PEER):
        connection.execute(
            sa.text(
                "INSERT INTO chat_participants (user_id, chat_id) VALUES (:user, :chat)"
            ),
            {"user": user_id, "chat": _CHAT},
        )
    connection.execute(
        sa.text(
            "INSERT INTO messages (id, chat_id, sender_id, content, tenant_id) "
            "VALUES (:id, :chat, :sender, 'seed message', :tenant)"
        ),
        {"id": _SEED_MESSAGE, "chat": _CHAT, "sender": _SENDER, "tenant": _TENANT},
    )


@pytest.fixture(scope="module")
def rls_database(request: pytest.FixtureRequest) -> Iterator[SimpleNamespace]:
    server = request.getfixturevalue("owned_baseline_server")
    with owned.committed_baseline(server) as baseline:
        credential = uuid.uuid4().hex + uuid.uuid4().hex
        admin = sa.create_engine(
            baseline.url,
            poolclass=sa.pool.NullPool,
            hide_parameters=True,
            connect_args={"connect_timeout": 5},
        )
        try:
            with admin.begin() as connection:
                assert baseline.url.database is not None
                _create_runtime_role(connection, credential)
                _seed(connection)
            yield SimpleNamespace(
                admin=admin,
                app_url=baseline.url.set(
                    drivername="postgresql+asyncpg",
                    username=_RUNTIME_ROLE,
                    password=credential,
                    query={},
                ),
            )
        finally:
            admin.dispose()


@pytest_asyncio.fixture(scope="module")
async def domain_event_listeners() -> None:
    # Registration is not idempotent, so it runs once for the module.
    await register_event_listeners()


@pytest_asyncio.fixture
async def runtime_session(rls_database: SimpleNamespace) -> AsyncIterator[AsyncSession]:
    # One pooled connection: a later transaction reuses the earlier connection.
    engine = create_async_engine(rls_database.app_url, pool_size=1, max_overflow=0)
    session = AsyncSession(engine, expire_on_commit=False)
    try:
        yield session
    finally:
        await session.close()
        await engine.dispose()


@contextlib.contextmanager
def _tenant_scope() -> Iterator[None]:
    """Bind the request tenant the way the API does, inside the running task."""
    register_tenant_listeners()
    token = set_current_tenant(_TENANT)
    try:
        yield
    finally:
        tenant_id_ctx.reset(token)


async def test_plain_send_without_idempotency_key_commits_as_nosuperuser(
    rls_database: SimpleNamespace,
    domain_event_listeners: None,
    runtime_session: AsyncSession,
) -> None:
    with _tenant_scope():
        identity = (
            await runtime_session.execute(
                sa.text(
                    "SELECT current_user, rolsuper, rolbypassrls FROM pg_roles "
                    "WHERE rolname = current_user"
                )
            )
        ).one()
        assert tuple(identity) == (_RUNTIME_ROLE, False, False)

        dispatcher = ChatMessageDispatcher(
            uow=uow_from_session(runtime_session),
            attachment_service=cast(AttachmentProcessorProtocol, _NoAttachments()),
            notification_service=cast(ChatNotificationService, _NoNotify()),
        )
        sender = cast(User, SimpleNamespace(id=_SENDER, role="student"))
        response = await dispatcher.send_message(
            _CHAT,
            sender,
            "plain send",
            [],
            locale="en",
        )

    assert response.content == "plain send"
    with rls_database.admin.connect() as connection:
        stored = connection.execute(
            sa.text("SELECT chat_id, sender_id FROM messages WHERE id = :id"),
            {"id": response.id},
        ).one()
    assert tuple(stored) == (_CHAT, _SENDER)


async def test_unbound_message_read_returns_no_rows_after_identity_ends(
    rls_database: SimpleNamespace,
    runtime_session: AsyncSession,
) -> None:
    """A pooled session that previously bound the GUC must not raise on a later read."""
    count_messages = sa.text("SELECT count(*) FROM messages")
    with rls_database.admin.connect() as connection:
        total = connection.scalar(
            sa.text("SELECT count(*) FROM messages WHERE chat_id = :chat"),
            {"chat": _CHAT},
        )
    assert total >= 1
    with _tenant_scope():
        # Never bound on this session: the read is empty, not an error.
        assert await runtime_session.scalar(count_messages) == 0
        await runtime_session.rollback()

        async with runtime_session.begin():
            await runtime_session.execute(
                sa.text("SELECT set_config('app.current_user_id', :uid, true)"),
                {"uid": str(_SENDER)},
            )
            assert await runtime_session.scalar(count_messages) == total

        # The transaction-local setting has ended on the same pooled connection.
        async with runtime_session.begin():
            assert await runtime_session.scalar(count_messages) == 0
