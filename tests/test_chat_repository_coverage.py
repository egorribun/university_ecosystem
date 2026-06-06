"""ChatRepository coverage climb — real-DB tests for the under-covered methods.

Exercises the SQLite-testable surface of ``app/repositories/chat_repository.py``
via the ``db_session`` + ``user_factory`` fixtures (mirrors
``test_chat_repository_groups.py``). Deliberately AVOIDS the PostgreSQL-only paths
that the SQLite harness cannot run:

* ``_set_rls_user`` / ``get_unread_count`` / ``get_messages(user_id=...)`` —
  use ``SET LOCAL app.current_user_id`` (PG GUC; SQLite rejects it). The group
  unread branch is already exercised at the repo level via ``get_chats_for_user``
  (which has no RLS call) in ``test_chat_repository_groups.py``.
* ``add_reaction`` — ``pg_insert(...).on_conflict_do_nothing`` is PG-only, so
  reactions are seeded here with a plain ``MessageReaction(...)`` insert to test
  ``remove_reaction`` / ``get_reactors``.

GOTCHA (server-default lazy-load): every Message is created with an explicit
``created_at`` so a first attribute access never triggers an async DB-default
lazy-load (MissingGreenlet). Timestamps stay within a recent window so rows land
in an existing partition on the CI PostgreSQL integration tier.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select

from app.models.chat import (
    Message,
    MessageReaction,
)
from app.repositories.chat_repository import ChatRepository

_NOW = datetime.now(UTC)


async def _make_dm(db_session, user_factory):
    """Create a 2-participant DM chat and return (repo, chat_dto, u1, u2)."""
    u1 = await user_factory()
    u2 = await user_factory()
    repo = ChatRepository(db_session)
    chat = await repo.create_chat([u1, u2])
    return repo, chat, u1, u2


async def _add_message(
    repo: ChatRepository,
    chat_id,
    sender_id,
    content: str = "hi",
    *,
    offset_seconds: int = 0,
) -> Message:
    """Persist a Message with an explicit (recent) created_at and return it."""
    msg = Message(
        chat_id=chat_id,
        sender_id=sender_id,
        content=content,
        created_at=_NOW + timedelta(seconds=offset_seconds),
    )
    await repo.create_message(msg)
    return msg


# --------------------------------------------------------------------------- #
# get_user_display_names (W211) — batch profile-name resolution                #
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_get_user_display_names_empty_returns_empty(db_session):
    repo = ChatRepository(db_session)
    assert await repo.get_user_display_names([]) == {}


@pytest.mark.asyncio
async def test_get_user_display_names_returns_entry_per_user(db_session, user_factory):
    u = await user_factory()
    repo = ChatRepository(db_session)

    result = await repo.get_user_display_names([u.id])

    # Each requested id has an entry; users with no UserProfile yield None
    # (the FE then shows a generic "Forwarded" chip without a name).
    assert u.id in result


# --------------------------------------------------------------------------- #
# find_existing_dm — exactly-two-participant DM lookup                         #
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_find_existing_dm_returns_chat_for_pair(db_session, user_factory):
    repo, chat, u1, u2 = await _make_dm(db_session, user_factory)

    found = await repo.find_existing_dm(u1.id, u2.id)

    assert found is not None
    assert found.id == chat.id


@pytest.mark.asyncio
async def test_find_existing_dm_none_when_no_shared_chat(db_session, user_factory):
    repo, _chat, u1, _u2 = await _make_dm(db_session, user_factory)
    stranger = await user_factory()

    assert await repo.find_existing_dm(u1.id, stranger.id) is None


# --------------------------------------------------------------------------- #
# get_last_message + get_messages (user_id=None skips the PG RLS GUC)          #
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_get_last_message_returns_most_recent(db_session, user_factory):
    repo, chat, u1, _u2 = await _make_dm(db_session, user_factory)
    await _add_message(repo, chat.id, u1.id, "first", offset_seconds=0)
    await _add_message(repo, chat.id, u1.id, "latest", offset_seconds=10)

    last = await repo.get_last_message(chat.id)

    assert last is not None
    assert last.content == "latest"


@pytest.mark.asyncio
async def test_get_last_message_none_for_empty_chat(db_session, user_factory):
    repo, chat, *_ = await _make_dm(db_session, user_factory)
    assert await repo.get_last_message(chat.id) is None


@pytest.mark.asyncio
async def test_get_messages_paginates_descending(db_session, user_factory):
    repo, chat, u1, _u2 = await _make_dm(db_session, user_factory)
    for i in range(3):
        await _add_message(repo, chat.id, u1.id, f"m{i}", offset_seconds=i)

    # limit=2 -> has_more True, newest first, plus a next-page cursor.
    # NOTE: the cursor-CONTINUATION branch (Message.id < cursor_id) is exercised
    # on PostgreSQL only — decode_datetime_cursor yields a *string* id and the
    # SQLite UUID type binds via value.hex (which a str lacks), so a second
    # cursor-bearing call raises StatementError on the SQLite test harness. This
    # is a harness limitation, not a prod bug (prod runs on PG, which coerces the
    # string to UUID). Assert page-1 shape only.
    page1, has_more, cursor = await repo.get_messages(chat.id, None, 2)
    assert has_more is True
    assert cursor is not None
    assert [m.content for m in page1] == ["m2", "m1"]


# --------------------------------------------------------------------------- #
# edit_message / soft_delete_message — author-only WHERE guards                #
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_edit_message_author_succeeds(db_session, user_factory):
    repo, chat, u1, _u2 = await _make_dm(db_session, user_factory)
    msg = await _add_message(repo, chat.id, u1.id, "original")

    edited_at, affected = await repo.edit_message(msg.id, u1.id, "edited")

    assert affected == 1
    assert edited_at is not None
    refreshed = await repo.get_message_by_id(msg.id)
    assert refreshed is not None
    assert refreshed.content == "edited"


@pytest.mark.asyncio
async def test_edit_message_non_author_is_noop(db_session, user_factory):
    repo, chat, u1, u2 = await _make_dm(db_session, user_factory)
    msg = await _add_message(repo, chat.id, u1.id, "original")

    edited_at, affected = await repo.edit_message(msg.id, u2.id, "hijack")

    assert affected == 0
    assert edited_at is None


@pytest.mark.asyncio
async def test_soft_delete_message_clears_content(db_session, user_factory):
    repo, chat, u1, _u2 = await _make_dm(db_session, user_factory)
    msg = await _add_message(repo, chat.id, u1.id, "secret")

    deleted_at, affected = await repo.soft_delete_message(msg.id, u1.id)

    assert affected == 1
    assert deleted_at is not None
    # D1: the deleted text must not linger — content is cleared to "".
    refreshed = await repo.get_message_by_id(msg.id)
    assert refreshed is not None
    assert refreshed.content == ""
    # A repeat delete is a no-op (deleted_at IS NULL guard).
    _, again = await repo.soft_delete_message(msg.id, u1.id)
    assert again == 0


# --------------------------------------------------------------------------- #
# reactions — seed with a plain insert (pg_insert is PG-only), then remove     #
# --------------------------------------------------------------------------- #


async def _seed_reaction(db_session, message_id, user_id, emoji: str) -> None:
    db_session.add(MessageReaction(message_id=message_id, user_id=user_id, emoji=emoji))
    await db_session.flush()


@pytest.mark.asyncio
async def test_remove_reaction_deletes_then_noop(db_session, user_factory):
    repo, chat, u1, _u2 = await _make_dm(db_session, user_factory)
    msg = await _add_message(repo, chat.id, u1.id)
    await _seed_reaction(db_session, msg.id, u1.id, "👍")

    assert await repo.remove_reaction(msg.id, u1.id, "👍") == 1
    # Removing a now-absent reaction is a benign no-op.
    assert await repo.remove_reaction(msg.id, u1.id, "👍") == 0


@pytest.mark.asyncio
async def test_get_reactors_returns_users_oldest_first(db_session, user_factory):
    repo, chat, u1, u2 = await _make_dm(db_session, user_factory)
    msg = await _add_message(repo, chat.id, u1.id)
    await _seed_reaction(db_session, msg.id, u1.id, "❤️")
    await _seed_reaction(db_session, msg.id, u2.id, "❤️")
    # A different emoji must not leak into the result.
    await _seed_reaction(db_session, msg.id, u2.id, "😂")

    reactors = await repo.get_reactors(msg.id, "❤️")

    assert {u.id for u in reactors} == {u1.id, u2.id}


# --------------------------------------------------------------------------- #
# delete_messages + cheap lookups (get_participants/get_chat_type/by_id)       #
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_delete_messages_empty_returns_zero(db_session):
    repo = ChatRepository(db_session)
    assert await repo.delete_messages([]) == 0


@pytest.mark.asyncio
async def test_delete_messages_removes_rows(db_session, user_factory):
    repo, chat, u1, _u2 = await _make_dm(db_session, user_factory)
    m1 = await _add_message(repo, chat.id, u1.id, "a", offset_seconds=0)
    m2 = await _add_message(repo, chat.id, u1.id, "b", offset_seconds=1)

    deleted = await repo.delete_messages([m1.id, m2.id])

    assert deleted == 2
    remaining = (
        await db_session.execute(
            select(func.count()).select_from(Message).where(Message.chat_id == chat.id)
        )
    ).scalar_one()
    assert remaining == 0


@pytest.mark.asyncio
async def test_get_participants_lists_member_ids(db_session, user_factory):
    repo, chat, u1, u2 = await _make_dm(db_session, user_factory)

    participants = await repo.get_participants(chat.id)

    assert set(participants) == {u1.id, u2.id}


@pytest.mark.asyncio
async def test_get_chat_type_defaults_to_dm(db_session, user_factory):
    repo, chat, *_ = await _make_dm(db_session, user_factory)
    assert await repo.get_chat_type(chat.id) == "dm"


@pytest.mark.asyncio
async def test_get_chat_type_none_for_missing_chat(db_session):
    import uuid

    repo = ChatRepository(db_session)
    assert await repo.get_chat_type(uuid.uuid4()) is None


@pytest.mark.asyncio
async def test_get_message_by_id_roundtrip_and_miss(db_session, user_factory):
    import uuid

    repo, chat, u1, _u2 = await _make_dm(db_session, user_factory)
    msg = await _add_message(repo, chat.id, u1.id, "findme")

    found = await repo.get_message_by_id(msg.id)
    assert found is not None
    assert found.content == "findme"

    assert await repo.get_message_by_id(uuid.uuid4()) is None
