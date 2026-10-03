"""PostgreSQL regression tests for transaction-local message RLS identity."""

from __future__ import annotations

import os
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.chat_repository import ChatRepository

# Import the existing PostgreSQL fixtures into this module for pytest discovery.
from tests.integration.test_rls_messages import (  # noqa: F401
    non_superuser_engine,
    pg_engine,
    setup_rls_role,
)

_RUN = bool(os.getenv("RUN_INTEGRATION_TESTS"))
_PG_URL = os.getenv("DATABASE_URL", "")
_IS_PG = _PG_URL.startswith("postgresql")

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not (_RUN and _IS_PG),
        reason=(
            "Set RUN_INTEGRATION_TESTS=1 and DATABASE_URL=postgresql+asyncpg://... "
            "to run RLS integration tests"
        ),
    ),
]


@pytest.mark.asyncio
async def test_repository_rls_identity_does_not_leak_between_transactions(
    request: pytest.FixtureRequest,
):
    """A repository-set user identity expires at commit on the same PG connection."""
    request.getfixturevalue("setup_rls_role")
    admin_engine = request.getfixturevalue("pg_engine")
    rls_engine = request.getfixturevalue("non_superuser_engine")

    authorized_user_id = str(uuid.uuid4())
    unrelated_user_id = str(uuid.uuid4())
    chat_id = str(uuid.uuid4())
    message_id = str(uuid.uuid4())
    email_suffix = uuid.uuid4().hex

    try:
        # Commit the synthetic rows so they remain available across the two
        # top-level transactions exercised below.
        async with admin_engine.begin() as admin_conn:
            for user_id, email in (
                (authorized_user_id, f"rls_identity_a_{email_suffix}@example.test"),
                (unrelated_user_id, f"rls_identity_b_{email_suffix}@example.test"),
            ):
                await admin_conn.execute(
                    text(
                        "INSERT INTO users "
                        "(id, email, hashed_password, role, is_active, mfa_required) "
                        "VALUES (:id, :email, 'x', 'student', true, false)"
                    ),
                    {"id": user_id, "email": email},
                )
                await admin_conn.execute(
                    text(
                        "INSERT INTO user_profiles (user_id, full_name) "
                        "VALUES (:user_id, 'RLS identity test')"
                    ),
                    {"user_id": user_id},
                )

            await admin_conn.execute(
                text(
                    "INSERT INTO chats (id, created_at, updated_at) "
                    "VALUES (:id, NOW(), NOW())"
                ),
                {"id": chat_id},
            )
            await admin_conn.execute(
                text(
                    "INSERT INTO chat_participants (chat_id, user_id) "
                    "VALUES (:chat_id, :user_id)"
                ),
                {"chat_id": chat_id, "user_id": authorized_user_id},
            )
            await admin_conn.execute(
                text(
                    "INSERT INTO messages "
                    "(id, chat_id, sender_id, content, created_at, read_status) "
                    "VALUES (:id, :chat_id, :sender_id, 'transaction identity proof', NOW(), false)"
                ),
                {
                    "id": message_id,
                    "chat_id": chat_id,
                    "sender_id": authorized_user_id,
                },
            )

        # Keep one non-superuser connection checked out across both transactions
        # so a stale session setting would be observable by the next identity.
        async with rls_engine.connect() as connection:
            async with AsyncSession(bind=connection, expire_on_commit=False) as session:
                repo = ChatRepository(session)

                async with session.begin():
                    current_role = await session.scalar(text("SELECT current_user"))
                    assert current_role == "rls_test_user"
                    visible_messages, has_more, next_cursor = await repo.get_messages(
                        uuid.UUID(chat_id),
                        None,
                        10,
                        user_id=uuid.UUID(authorized_user_id),
                    )
                    assert [str(message.id) for message in visible_messages] == [
                        message_id
                    ]
                    assert not has_more
                    assert next_cursor is None

                async with session.begin():
                    # SET LOCAL from the first transaction must have reset.
                    current_identity = await session.scalar(
                        text("SELECT current_setting('app.current_user_id', TRUE)")
                    )
                    assert current_identity in (None, "")

                    # A different user supplied on the next repository call
                    # receives only that identity's RLS view.
                    unrelated_messages, has_more, next_cursor = await repo.get_messages(
                        uuid.UUID(chat_id),
                        None,
                        10,
                        user_id=uuid.UUID(unrelated_user_id),
                    )
                    assert unrelated_messages == []
                    assert not has_more
                    assert next_cursor is None
                    current_identity = await session.scalar(
                        text("SELECT current_setting('app.current_user_id', TRUE)")
                    )
                    assert current_identity == unrelated_user_id
    finally:
        # The test commits only isolated synthetic rows to cross a real
        # transaction boundary, then removes them even when an assertion fails.
        async with admin_engine.begin() as admin_conn:
            await admin_conn.execute(
                text("DELETE FROM chats WHERE id = :chat_id"),
                {"chat_id": chat_id},
            )
            for user_id in (authorized_user_id, unrelated_user_id):
                await admin_conn.execute(
                    text("DELETE FROM users WHERE id = :user_id"),
                    {"user_id": user_id},
                )
