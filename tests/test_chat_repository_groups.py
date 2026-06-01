"""Wave 209 G1 — ChatRepository group-chat methods against a real DB session.

Exercises create_group / add_participant / remove_participant / rename_chat via
the db_session fixture (the test suite runs on SQLite; the schema is built from
the models, so the new Chat.chat_type/name/created_by columns are present).
Membership-count + name assertions use column-level SELECTs so they read fresh
DB state rather than the session identity map (a Core INSERT/UPDATE/DELETE does
not refresh mapped instances).
"""

import pytest
from sqlalchemy import func, select

from app.models.chat import Chat, chat_participants
from app.repositories.chat_repository import ChatRepository


async def _participant_count(db_session, chat_id) -> int:
    return (
        await db_session.execute(
            select(func.count())
            .select_from(chat_participants)
            .where(chat_participants.c.chat_id == chat_id)
        )
    ).scalar_one()


@pytest.mark.asyncio
async def test_create_group_sets_identity_and_members(db_session, user_factory):
    creator = await user_factory()
    m1 = await user_factory()
    m2 = await user_factory()
    repo = ChatRepository(db_session)

    dto = await repo.create_group(creator, "Team Chat", [m1, m2])

    assert dto.chat_type == "group"
    assert dto.name == "Team Chat"
    assert dto.created_by == creator.id
    assert {p.id for p in dto.participants} == {creator.id, m1.id, m2.id}
    assert await _participant_count(db_session, dto.id) == 3


@pytest.mark.asyncio
async def test_create_group_dedupes_creator(db_session, user_factory):
    creator = await user_factory()
    m1 = await user_factory()
    repo = ChatRepository(db_session)

    # The creator passed again in member_users must not be double-added.
    dto = await repo.create_group(creator, "Dup", [m1, creator])

    assert {p.id for p in dto.participants} == {creator.id, m1.id}
    assert await _participant_count(db_session, dto.id) == 2


@pytest.mark.asyncio
async def test_add_participant_is_idempotent(db_session, user_factory):
    creator = await user_factory()
    m1 = await user_factory()
    m2 = await user_factory()
    newcomer = await user_factory()
    repo = ChatRepository(db_session)
    dto = await repo.create_group(creator, "Team", [m1, m2])

    assert await repo.add_participant(dto.id, newcomer.id) is True
    assert await _participant_count(db_session, dto.id) == 4
    # Second add of the same user is a no-op.
    assert await repo.add_participant(dto.id, newcomer.id) is False
    assert await _participant_count(db_session, dto.id) == 4


@pytest.mark.asyncio
async def test_remove_participant_is_idempotent(db_session, user_factory):
    creator = await user_factory()
    m1 = await user_factory()
    m2 = await user_factory()
    repo = ChatRepository(db_session)
    dto = await repo.create_group(creator, "Team", [m1, m2])

    assert await repo.remove_participant(dto.id, m2.id) == 1
    assert await _participant_count(db_session, dto.id) == 2
    # Removing a non-member is a benign no-op.
    assert await repo.remove_participant(dto.id, m2.id) == 0
    assert await _participant_count(db_session, dto.id) == 2


@pytest.mark.asyncio
async def test_rename_chat_persists(db_session, user_factory):
    creator = await user_factory()
    m1 = await user_factory()
    m2 = await user_factory()
    repo = ChatRepository(db_session)
    dto = await repo.create_group(creator, "Old Name", [m1, m2])

    affected = await repo.rename_chat(dto.id, "New Name")
    assert affected == 1

    name = (
        await db_session.execute(select(Chat.name).where(Chat.id == dto.id))
    ).scalar_one()
    assert name == "New Name"
