"""Enable PostgreSQL Row-Level Security on messages table.

MOD-02 (audit Wave 11): Defense-in-depth — even if an application-layer bug
bypasses the Python/SpiceDB authorization checks, PostgreSQL RLS prevents a
user from reading messages in chats they are not a participant of.

The policy ``messages_participant_isolation`` uses a subquery against
``chat_participants`` filtered by ``current_setting('app.current_user_id')``
which the application sets per-request via ``SET LOCAL``.

Application wiring:
    Before any query that touches the ``messages`` table, call:
        await conn.execute(
            text("SET LOCAL app.current_user_id = :uid"),
            {"uid": str(user_id)},
        )
    The ``SET LOCAL`` is automatically scoped to the current transaction, so
    no explicit cleanup is needed when using ``async with session.begin()``.

Revision ID: 202603170003
Revises: 202603170002
Create Date: 2026-03-17 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "202603170003"
down_revision: str | None = "202603170002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _is_postgres() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    if not _is_postgres():
        return

    conn = op.get_bind()

    # 1. Enable RLS on the messages table.
    #    FORCE ROW LEVEL SECURITY also applies the policy to the table owner
    #    (the application DB user), preventing bypass via super-user-like role.
    conn.execute(op.inline_literal("ALTER TABLE messages ENABLE ROW LEVEL SECURITY"))
    conn.execute(op.inline_literal("ALTER TABLE messages FORCE ROW LEVEL SECURITY"))

    # 2. Create the participant-isolation policy.
    #    A row in ``messages`` is visible only if the current user is a
    #    participant of the chat that owns the message.
    #    The ``current_setting('app.current_user_id', TRUE)`` call uses the
    #    second argument (missing_ok=TRUE) so that sessions without the GUC
    #    set return NULL rather than raising an error — those sessions see no
    #    rows (fail-closed, correct behaviour for unauthenticated contexts).
    conn.execute(
        op.inline_literal(
            """
            CREATE POLICY messages_participant_isolation ON messages
                AS PERMISSIVE
                FOR ALL
                TO PUBLIC
                USING (
                    chat_id IN (
                        SELECT chat_id
                        FROM   chat_participants
                        WHERE  user_id = (
                            current_setting('app.current_user_id', TRUE)::uuid
                        )
                    )
                )
            """
        )
    )


def downgrade() -> None:
    if not _is_postgres():
        return

    conn = op.get_bind()

    conn.execute(
        op.inline_literal(
            "DROP POLICY IF EXISTS messages_participant_isolation ON messages"
        )
    )
    conn.execute(op.inline_literal("ALTER TABLE messages NO FORCE ROW LEVEL SECURITY"))
    conn.execute(op.inline_literal("ALTER TABLE messages DISABLE ROW LEVEL SECURITY"))
