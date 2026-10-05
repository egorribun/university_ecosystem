"""ChatRepository coverage climb — real-DB tests for the under-covered methods.

Exercises the SQLite-testable surface of ``app/repositories/chat_repository.py``
via the ``db_session`` + ``user_factory`` fixtures (mirrors
``test_chat_repository_groups.py``). Deliberately AVOIDS the PostgreSQL-only paths
that the SQLite harness cannot run:

* PostgreSQL message reads and deletes require an explicit RLS ``user_id``.
  SQLite skips the PostgreSQL-only GUC write, so the same tests run on both
  dialects while retaining the production identity requirement.
* ``get_unread_count`` uses ``SET LOCAL app.current_user_id`` (PG GUC; SQLite
  rejects it). The group unread branch is exercised via ``get_chats_for_user``
  in ``test_chat_repository_groups.py``.
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
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.events import register_event_listeners
from app.models.chat import (
    Message,
    MessageReaction,
)
from app.models.domain_events import StoredEvent
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
# get_last_message + get_messages — explicit identity for PostgreSQL RLS        #
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_get_last_message_returns_most_recent(db_session, user_factory):
    repo, chat, u1, _u2 = await _make_dm(db_session, user_factory)
    await _add_message(repo, chat.id, u1.id, "first", offset_seconds=0)
    await _add_message(repo, chat.id, u1.id, "latest", offset_seconds=10)

    last = await repo.get_last_message(chat.id, user_id=u1.id)

    assert last is not None
    assert last.content == "latest"


@pytest.mark.asyncio
async def test_get_last_message_none_for_empty_chat(db_session, user_factory):
    repo, chat, u1, _u2 = await _make_dm(db_session, user_factory)
    assert await repo.get_last_message(chat.id, user_id=u1.id) is None


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
    page1, has_more, cursor = await repo.get_messages(chat.id, None, 2, user_id=u1.id)
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

    edited_at, affected = await repo.edit_message(
        msg.id, u1.id, "edited", chat_id=chat.id
    )

    assert affected == 1
    assert edited_at is not None
    refreshed = await repo.get_message_by_id(msg.id, user_id=u1.id)
    assert refreshed is not None
    assert refreshed.content == "edited"


@pytest.mark.asyncio
async def test_edit_message_non_author_is_noop(db_session, user_factory):
    repo, chat, u1, u2 = await _make_dm(db_session, user_factory)
    msg = await _add_message(repo, chat.id, u1.id, "original")

    edited_at, affected = await repo.edit_message(
        msg.id, u2.id, "hijack", chat_id=chat.id
    )

    assert affected == 0
    assert edited_at is None


@pytest.mark.asyncio
async def test_edit_message_preserves_committed_tombstone(db_session, user_factory):
    repo, chat, author, _peer = await _make_dm(db_session, user_factory)
    message = await _add_message(repo, chat.id, author.id, "deleted text")
    message.edited_at = _NOW
    message.read_status = True
    message.read_at = _NOW
    message_id, chat_id, author_id = message.id, chat.id, author.id

    deleted_at, deleted = await repo.soft_delete_message(
        message_id, author_id, chat_id=chat_id
    )
    assert deleted == 1
    assert deleted_at is not None
    await db_session.commit()

    sessions = async_sessionmaker(db_session.bind, expire_on_commit=False)
    stored_row = select(Message.__table__).where(Message.id == message_id)
    # Both calls use the real author and chat. SQLite proves the deleted_at
    # predicate here; PostgreSQL RLS still requires its integration tier.
    async with sessions.begin() as edit_session:
        edit_repo = ChatRepository(edit_session)
        await edit_repo.set_message_rls_user(author_id)
        before = dict((await edit_session.execute(stored_row)).mappings().one())
        assert before["content"] == ""
        assert before["deleted_at"] is not None
        assert before["edited_at"] is not None
        assert before["read_status"] is True
        assert before["read_at"] is not None

        edited_at, affected = await edit_repo.edit_message(
            message_id, author_id, "resurrected text", chat_id=chat_id
        )

    # Read every persisted column after commit in another session, so an ORM
    # identity-map value cannot hide resurrected content or changed metadata.
    async with sessions.begin() as read_session:
        await ChatRepository(read_session).set_message_rls_user(author_id)
        after = dict((await read_session.execute(stored_row)).mappings().one())

    assert after == before
    assert affected == 0
    assert edited_at is None


@pytest.mark.asyncio
async def test_edit_message_rejects_message_from_different_chat(
    db_session, user_factory
):
    repo, source_chat, author, source_peer = await _make_dm(db_session, user_factory)
    destination_peer = await user_factory()
    other_chat = await repo.create_chat([author, destination_peer])
    msg = await _add_message(repo, source_chat.id, author.id, "source text")
    assert await repo.remove_participant(source_chat.id, author.id) == 1
    assert await repo.check_participant(other_chat.id, author.id)

    edited_at, affected = await repo.edit_message(
        msg.id, author.id, "cross-chat edit", chat_id=other_chat.id
    )

    assert affected == 0
    assert edited_at is None
    refreshed = await repo.get_message_by_id(msg.id, user_id=source_peer.id)
    assert refreshed is not None
    assert refreshed.content == "source text"


@pytest.mark.asyncio
async def test_soft_delete_message_rejects_message_from_different_chat(
    db_session, user_factory
):
    repo, source_chat, author, source_peer = await _make_dm(db_session, user_factory)
    destination_peer = await user_factory()
    other_chat = await repo.create_chat([author, destination_peer])
    msg = await _add_message(repo, source_chat.id, author.id, "source text")
    assert await repo.remove_participant(source_chat.id, author.id) == 1
    assert await repo.check_participant(other_chat.id, author.id)

    deleted_at, affected = await repo.soft_delete_message(
        msg.id, author.id, chat_id=other_chat.id
    )

    assert affected == 0
    assert deleted_at is None
    refreshed = await repo.get_message_by_id(msg.id, user_id=source_peer.id)
    assert refreshed is not None
    assert refreshed.content == "source text"


@pytest.mark.asyncio
async def test_soft_delete_message_clears_content(db_session, user_factory):
    repo, chat, u1, _u2 = await _make_dm(db_session, user_factory)
    msg = await _add_message(repo, chat.id, u1.id, "secret")

    deleted_at, affected = await repo.soft_delete_message(
        msg.id, u1.id, chat_id=chat.id
    )

    assert affected == 1
    assert deleted_at is not None
    # D1: the deleted text must not linger — content is cleared to "".
    refreshed = await repo.get_message_by_id(msg.id, user_id=u1.id)
    assert refreshed is not None
    assert refreshed.content == ""
    # A repeat delete is a no-op (deleted_at IS NULL guard).
    _, again = await repo.soft_delete_message(msg.id, u1.id, chat_id=chat.id)
    assert again == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("operation", "event_type"),
    [
        ("edit", "chat.message_edited"),
        ("delete", "chat.message_deleted"),
    ],
)
async def test_message_mutation_outbox_event_commits_atomically(
    db_session, user_factory, operation, event_type
):
    await register_event_listeners()
    repo, chat, author, _peer = await _make_dm(db_session, user_factory)
    message = await _add_message(repo, chat.id, author.id, "original")
    message_id = message.id
    chat_id = chat.id
    author_id = author.id
    await db_session.commit()
    # Start the transaction used by the service's preceding chat read; the
    # identity map can satisfy get_by_id without SQL after the setup commit.
    await db_session.execute(select(1))

    if operation == "edit":
        timestamp, affected = await repo.edit_message(
            message_id, author_id, "edited", chat_id=chat_id
        )
    else:
        timestamp, affected = await repo.soft_delete_message(
            message_id, author_id, chat_id=chat_id
        )

    assert affected == 1
    assert timestamp is not None
    await db_session.commit()

    stored = await db_session.scalar(
        select(StoredEvent).where(
            StoredEvent.aggregate_type == "Message",
            StoredEvent.aggregate_id == str(message_id),
            StoredEvent.event_type == event_type,
        )
    )
    assert stored is not None
    assert stored.payload["message_id"] == str(message_id)
    assert stored.payload["chat_id"] == str(chat_id)
    # Outbox events carry identity only; handlers read the committed row rather
    # than duplicating message text in durable history.
    assert "content" not in stored.payload


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("operation", "event_type"),
    [
        ("edit", "chat.message_edited"),
        ("delete", "chat.message_deleted"),
    ],
)
async def test_message_mutation_rollback_discards_outbox_event(
    db_session, user_factory, operation, event_type
):
    await register_event_listeners()
    repo, chat, author, _peer = await _make_dm(db_session, user_factory)
    message = await _add_message(repo, chat.id, author.id, "original")
    message_id = message.id
    chat_id = chat.id
    author_id = author.id
    await db_session.commit()
    await db_session.execute(select(1))

    if operation == "edit":
        await repo.edit_message(message_id, author_id, "edited", chat_id=chat_id)
    else:
        await repo.soft_delete_message(message_id, author_id, chat_id=chat_id)

    # Force the ORM event capture/StoredEvent INSERT, then roll back the same
    # transaction that contains the message mutation and its outbox row.
    await db_session.flush()
    pending_count = await db_session.scalar(
        select(func.count())
        .select_from(StoredEvent)
        .where(
            StoredEvent.aggregate_type == "Message",
            StoredEvent.aggregate_id == str(message_id),
            StoredEvent.event_type == event_type,
        )
    )
    assert pending_count == 1
    await db_session.rollback()

    refreshed = await repo.get_message_by_id(message_id, user_id=author_id)
    assert refreshed is not None
    assert refreshed.content == "original"
    assert refreshed.deleted_at is None
    stored_count = await db_session.scalar(
        select(func.count())
        .select_from(StoredEvent)
        .where(
            StoredEvent.aggregate_type == "Message",
            StoredEvent.aggregate_id == str(message_id),
            StoredEvent.event_type == event_type,
        )
    )
    assert stored_count == 0


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

    reactors = await repo.get_reactors(msg.id, "❤️", user_id=u1.id)

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

    deleted = await repo.delete_messages([m1.id, m2.id], chat_id=chat.id, user_id=u1.id)

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
async def test_get_message_by_id_loads_reply_preview(db_session, user_factory):
    repo, chat, original_author, reply_author = await _make_dm(db_session, user_factory)
    original = await _add_message(repo, chat.id, original_author.id, "quoted content")
    reply = Message(
        chat_id=chat.id,
        sender_id=reply_author.id,
        content="reply",
        reply_to_message_id=original.id,
        created_at=_NOW + timedelta(seconds=1),
    )
    db_session.add(reply)
    await db_session.flush()

    found = await repo.get_message_by_id(
        reply.id, user_id=reply_author.id, chat_id=chat.id
    )

    assert found is not None
    assert found.replied_to is not None
    assert found.replied_to.id == original.id
    assert found.replied_to.content == "quoted content"


@pytest.mark.asyncio
async def test_get_message_by_id_roundtrip_and_miss(db_session, user_factory):
    import uuid

    repo, chat, u1, _u2 = await _make_dm(db_session, user_factory)
    msg = await _add_message(repo, chat.id, u1.id, "findme")

    found = await repo.get_message_by_id(msg.id, user_id=u1.id)
    assert found is not None
    assert found.content == "findme"

    assert await repo.get_message_by_id(uuid.uuid4(), user_id=u1.id) is None


@pytest.mark.asyncio
async def test_get_last_message_preserves_postgres_rls_identity(
    db_session, user_factory, monkeypatch
):
    repo, chat, owner, _other = await _make_dm(db_session, user_factory)
    await _add_message(repo, chat.id, owner.id, "latest visible message")

    dialect = repo.db.get_bind().dialect
    monkeypatch.setattr(dialect, "name", "postgresql")
    execute = repo.db.execute
    observed_identity = None

    async def execute_with_local_rls_setting(statement, *args, **kwargs):
        nonlocal observed_identity
        if str(statement).startswith("SELECT set_config('app.current_user_id'"):
            parameters = args[0] if args else kwargs.get("params", {})
            observed_identity = parameters.get("uid")
            return None
        return await execute(statement, *args, **kwargs)

    monkeypatch.setattr(repo.db, "execute", execute_with_local_rls_setting)

    latest = await repo.get_last_message(chat.id, user_id=owner.id)

    assert observed_identity == str(owner.id)
    assert latest is not None
    assert latest.content == "latest visible message"
