"""Reply-author names survive real batched repository reads and serialization."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from sqlalchemy import delete, event, inspect, select
from sqlalchemy.orm import selectinload

from app.api.ws.serializers import serialize_message
from app.models import User, UserProfile
from app.models.chat import Chat, Message
from app.repositories.chat_repository import ChatRepository
from app.schemas.chat import ReplyPreview
from app.schemas.dtos.chat import ChatParticipantDTO, MessageDTO
from app.services.chat.query_service import ChatQueryService

_NOW = datetime(2035, 1, 1, 12, tzinfo=UTC)


@contextmanager
def _statements(session):
    statements = []
    engine = session.get_bind()

    def record(_conn, _cursor, statement, _parameters, _context, _many):
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", record)
    try:
        yield statements
    finally:
        event.remove(engine, "before_cursor_execute", record)


@contextmanager
def _sender_batches(session):
    batches = []
    engine = session.get_bind()

    def record(_conn, _cursor, _sql, parameters, context, _many):
        statement = context.compiled.statement
        columns = getattr(statement, "selected_columns", ())
        selected = [(column.table.name, column.name) for column in columns]
        if ("user_profiles", "full_name") in selected:
            batches.append((selected, set(parameters)))

    event.listen(engine, "before_cursor_execute", record)
    try:
        yield batches
    finally:
        event.remove(engine, "before_cursor_execute", record)


async def _seed(session, factory, names, *, missing=False, tombstone=False):
    reader = await factory(full_name="Reader")
    authors = [await factory(full_name=name, is_active=False) for name in names]
    chat = Chat(participants=[reader, *authors])
    session.add(chat)
    await session.flush()
    originals = [
        Message(
            chat_id=chat.id,
            sender_id=author.id,
            content="" if tombstone else "Original " + "x" * 220,
            deleted_at=_NOW if tombstone else None,
            created_at=_NOW - timedelta(minutes=index + 1),
        )
        for index, author in enumerate(authors)
    ]
    session.add_all(originals)
    await session.flush()
    replies = [
        Message(
            chat_id=chat.id,
            sender_id=reader.id,
            content="Reply",
            reply_to_message_id=original.id,
            created_at=_NOW + timedelta(seconds=index),
        )
        for index, original in enumerate(originals)
    ]
    session.add_all(replies)
    if missing:
        await session.execute(
            delete(UserProfile).where(UserProfile.user_id.in_([a.id for a in authors]))
        )
    await session.commit()
    result = SimpleNamespace(
        reader=reader,
        chat_id=chat.id,
        reply_ids=[message.id for message in replies],
        original_ids=[message.id for message in originals],
        expected={
            author.id: (None if missing else name, author.email)
            for author, name in zip(authors, names, strict=True)
        },
    )
    session.expunge_all()
    return result


async def _read(repository, seeded, path, limit):
    if path == "page":
        rows, _, _ = await repository.get_messages(
            seeded.chat_id, None, limit, user_id=seeded.reader.id
        )
        return rows
    if path == "batch":
        return list(
            (
                await repository.get_last_messages(
                    seeded.reply_ids[:limit], user_id=seeded.reader.id
                )
            ).values()
        )
    row = await repository.get_message_by_id(
        seeded.reply_ids[0], user_id=seeded.reader.id, chat_id=seeded.chat_id
    )
    assert row is not None
    return [row]


@pytest.mark.parametrize("path", ["page", "batch", "single"])
@pytest.mark.parametrize(
    "name,missing,tombstone",
    [
        ("Alice", False, False),
        ("Алиса", False, False),
        (None, False, False),
        ("Not public", True, False),
        ("Deleted User", False, False),
        ("Alice", False, True),
    ],
)
async def test_reply_sender_uses_current_profile_without_private_fallback(
    db_session, user_factory, path, name, missing, tombstone
):
    seeded = await _seed(
        db_session, user_factory, [name], missing=missing, tombstone=tombstone
    )
    repository = ChatRepository(db_session)
    rows = await _read(repository, seeded, path, 1)
    assert len(rows) == 1
    target = rows[0].replied_to
    assert target is not None and target.id == seeded.original_ids[0]
    assert target.sender is not None
    expected_name, expected_email = seeded.expected[target.sender_id]
    assert (
        target.sender.id,
        target.sender.full_name,
        target.sender.email,
        target.sender.is_active,
        target.sender.avatar_url,
    ) == (target.sender_id, expected_name, expected_email, False, None)
    db_session.expunge_all()
    with _statements(db_session) as serialized:
        preview = ReplyPreview.from_message(target)
        assert preview is not None
        payload = preview.model_dump(mode="json")
        assert payload["sender_name"] == expected_name
        assert set(payload) == {
            "id",
            "sender_id",
            "sender_name",
            "content",
            "deleted_at",
        }
        assert payload["content"] == ("" if tombstone else "Original " + "x" * 191)
        assert (payload["deleted_at"] is not None) == tombstone
    assert serialized == []


@pytest.mark.parametrize("path", ["page", "batch"])
async def test_reply_sender_queries_are_batched_for_distinct_authors(
    db_session, user_factory, path
):
    seeded = await _seed(db_session, user_factory, [f"Author {i}" for i in range(8)])
    counts = []
    for size in [1, 8]:
        db_session.expunge_all()
        with (
            _statements(db_session) as statements,
            _sender_batches(db_session) as batches,
        ):
            rows = await _read(ChatRepository(db_session), seeded, path, size)
        counts.append(len(statements))
        assert len(rows) == size
        for row in rows:
            assert row.replied_to is not None
            assert (
                ReplyPreview.from_message(row.replied_to).sender_name
                == seeded.expected[row.replied_to.sender_id][0]
            )
        assert len(batches) == 1
        columns, sender_ids = batches[0]
        assert columns == [
            ("users", "id"),
            ("users", "email"),
            ("users", "is_active"),
            ("user_profiles", "full_name"),
        ]
        expected_ids = {row.replied_to.sender_id.hex for row in rows}
        if path == "batch":
            expected_ids.add(seeded.reader.id.hex)
        else:
            assert all(row.sender is None for row in rows)
        assert sender_ids == expected_ids
        assert not any(
            "hashed_password" in sql or "password_hash" in sql for sql in statements
        )
    assert counts[0] == counts[1]
    assert counts[0] <= 5  # Existing page read cost, never raised for extra authors.


async def test_message_page_names_include_quote_authors_outside_the_page(
    db_session, user_factory
):
    seeded = await _seed(db_session, user_factory, ["Alice", "Алиса"])
    service = ChatQueryService(db_session, ChatRepository(db_session))
    with patch(
        "app.services.chat.query_service.build_presence_map",
        new=AsyncMock(return_value={}),
    ):
        response = await service.get_messages(
            seeded.chat_id, seeded.reader, None, 2, "en"
        )
    assert response.has_more is True and response.next_cursor is not None
    assert {message.id for message in response.items} == set(seeded.reply_ids)
    assert {message.reply_to.sender_name for message in response.items} == {
        "Alice",
        "Алиса",
    }
    assert all(message.sender.full_name == "Reader" for message in response.items)


async def test_root_target_name_reaches_live_serializer(db_session, user_factory):
    seeded = await _seed(db_session, user_factory, ["Alice"])
    repository = ChatRepository(db_session)
    target = await repository.get_message_by_id(
        seeded.original_ids[0], user_id=seeded.reader.id, chat_id=seeded.chat_id
    )
    assert target is not None
    reply = (
        await repository.get_last_messages(seeded.reply_ids, user_id=seeded.reader.id)
    )[seeded.reply_ids[0]]
    db_session.expunge_all()
    with _statements(db_session) as serialized:
        frame = serialize_message(reply, replied=target)
    assert serialized == []
    assert frame["reply_to"]["sender_name"] == "Alice"
    assert frame["reply_to"]["sender_id"] == target.sender_id


@pytest.mark.parametrize("state", ["noload", "loaded", "deferred", "dirty"])
async def test_reply_projection_does_not_depend_on_or_overwrite_profile_state(
    db_session, user_factory, state
):
    seeded = await _seed(db_session, user_factory, ["Alice"])
    author_id = next(iter(seeded.expected))
    stmt = select(User).where(User.id == author_id)
    if state != "noload":
        loader = selectinload(User.profile)
        if state == "deferred":
            loader = loader.defer(UserProfile.full_name)
        stmt = stmt.options(loader)
    author = (await db_session.scalars(stmt)).one()
    if state == "dirty":
        author.profile.full_name = "Unsaved name"
    with db_session.no_autoflush, _statements(db_session) as statements:
        rows = await _read(ChatRepository(db_session), seeded, "single", 1)
    assert ReplyPreview.from_message(rows[0].replied_to).sender_name == "Alice"
    assert all(sql.lstrip().upper().startswith("SELECT") for sql in statements)
    if state == "noload":
        assert author.profile is None
    elif state == "deferred":
        assert "full_name" in inspect(author.profile).unloaded
    elif state == "dirty":
        assert author.profile.full_name == "Unsaved name"
        assert inspect(author.profile).attrs.full_name.history.added == ["Unsaved name"]
    else:
        assert author.profile.full_name == "Alice"


async def test_empty_and_missing_message_reads_remain_empty(db_session, user_factory):
    user = await user_factory()
    repository = ChatRepository(db_session)
    with _statements(db_session) as statements:
        assert await repository.get_last_messages([], user_id=user.id) == {}
    assert statements == []
    assert await repository.get_message_by_id(uuid4(), user_id=user.id) is None
    rows, more, cursor = await repository.get_messages(
        uuid4(), None, 20, user_id=user.id
    )
    assert (rows, more, cursor) == ([], False, None)


async def test_missing_author_does_not_retain_stale_sender_data(db_session):
    """An author removed between reads cannot leave an old name in the DTO."""
    sender_id = uuid4()
    message = MessageDTO(
        id=uuid4(),
        chat_id=uuid4(),
        sender_id=sender_id,
        content="Synthetic",
        created_at=_NOW,
        sender=ChatParticipantDTO(id=sender_id, full_name="Old name"),
    )
    await ChatRepository(db_session)._hydrate_message_senders(
        [message], include_root_senders=True
    )
    assert message.sender is None
    assert ReplyPreview.from_message(message).sender_name is None


@pytest.mark.parametrize("path", ["page", "batch", "single"])
@pytest.mark.parametrize("preloaded", ["reply", "root"])
async def test_deferred_sender_identity_map_never_triggers_lazy_io(
    db_session, user_factory, path, preloaded
):
    seeded = await _seed(db_session, user_factory, ["Alice"])
    message_id = seeded.original_ids[0] if preloaded == "reply" else seeded.reply_ids[0]
    cached = (
        await db_session.scalars(
            select(Message)
            .where(Message.id == message_id)
            .options(
                selectinload(Message.sender).load_only(User.id),
                selectinload(Message.replied_to),
            )
        )
    ).one()
    assert cached.sender is not None
    assert {"email", "is_active"} <= inspect(cached.sender).unloaded
    rows = await _read(ChatRepository(db_session), seeded, path, 1)
    target = rows[0].replied_to
    assert target is not None and target.sender is not None
    assert (target.sender.full_name, target.sender.email) == (
        "Alice",
        seeded.expected[target.sender_id][1],
    )
    if path == "page":
        assert rows[0].sender is None
    else:
        assert rows[0].sender.full_name == "Reader"
    assert {"email", "is_active"} <= inspect(cached.sender).unloaded
