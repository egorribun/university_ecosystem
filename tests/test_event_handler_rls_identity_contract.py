from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any, cast
from uuid import UUID

from sqlalchemy import UUID as SQLAlchemyUUID
from sqlalchemy import Column, MetaData, Table, insert
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.sql.elements import TextClause

from app.models.chat import chat_participants
from app.services import event_handlers

_CHAT_ID = UUID("c0000000-0000-4000-8000-00000000000a")
_FIRST_MEMBER = UUID("a1111111-1111-4111-8111-111111111111")
_SECOND_MEMBER = UUID("b2222222-2222-4222-8222-222222222222")
_SET_CONFIG_SQL = "SELECT set_config('app.current_user_id', :uid, true)"

# Minimal referenced tables satisfy SQLite foreign keys while the association
# table itself keeps the production SQLAlchemy metadata and UUID column types.
_MINIMAL_METADATA = MetaData()
_USERS = Table(
    "users",
    _MINIMAL_METADATA,
    Column("id", SQLAlchemyUUID(as_uuid=True), primary_key=True),
)
_CHATS = Table(
    "chats",
    _MINIMAL_METADATA,
    Column("id", SQLAlchemyUUID(as_uuid=True), primary_key=True),
)


class _PostgresBranchSession:
    """Use SQLite for membership SQL and observe the PostgreSQL config call."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self.config_calls: list[dict[str, str]] = []

    async def execute(self, statement: Any, parameters: Any = None) -> Any:
        if isinstance(statement, TextClause):
            if str(statement) != _SET_CONFIG_SQL:
                raise AssertionError("rls_identity_set_config_statement")
            if parameters != {"uid": str(_FIRST_MEMBER)}:
                raise AssertionError("rls_identity_set_config_parameter")
            self.config_calls.append(dict(parameters))
            return object()
        return await self._session.execute(statement, parameters)

    def get_bind(self) -> SimpleNamespace:
        return SimpleNamespace(dialect=SimpleNamespace(name="postgresql"))


async def _exercise_two_member_identity_contract() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(_MINIMAL_METADATA.create_all)
            await connection.run_sync(chat_participants.create)
            await connection.execute(
                insert(_USERS),
                [{"id": _FIRST_MEMBER}, {"id": _SECOND_MEMBER}],
            )
            await connection.execute(insert(_CHATS), [{"id": _CHAT_ID}])
            await connection.execute(
                insert(chat_participants),
                [
                    {"chat_id": _CHAT_ID, "user_id": _SECOND_MEMBER},
                    {"chat_id": _CHAT_ID, "user_id": _FIRST_MEMBER},
                ],
            )

        async with AsyncSession(engine) as session:
            observed = _PostgresBranchSession(session)
            member_id = await event_handlers._set_message_rls_identity(
                cast(AsyncSession, observed), _CHAT_ID
            )

        if member_id != _FIRST_MEMBER:
            raise AssertionError("rls_identity_selects_one_ordered_member")
        if observed.config_calls != [{"uid": str(_FIRST_MEMBER)}]:
            raise AssertionError("rls_identity_sets_transaction_local_member")
    finally:
        await engine.dispose()


def test_message_rls_identity_uses_one_ordered_live_member() -> None:
    asyncio.run(_exercise_two_member_identity_contract())
