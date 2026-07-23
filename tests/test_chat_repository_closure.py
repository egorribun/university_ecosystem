"""Focused branch-closure tests for ChatRepository."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import app.repositories.chat_repository as chat_module
from app.models import User
from app.repositories.chat_repository import ChatRepository

CHAT_ID = uuid.UUID("019c1468-f495-7980-9ad0-d8f31705df79")
USER_ID = uuid.UUID("019c1468-f495-7980-9ad0-d8f31705df7a")
OTHER_ID = uuid.UUID("019c1468-f495-7980-9ad0-d8f31705df7b")
NOW = datetime(2026, 7, 23, 9, 0, tzinfo=UTC)


class _FakeMessageDTO:
    @classmethod
    def model_validate(cls, value: object) -> tuple[str, object]:
        return ("message-dto", value)


def _result(
    *,
    rows: list[object] | None = None,
    scalar: object = None,
    scalar_one: object = 0,
    scalar_one_or_none: object = None,
    rowcount: int | None = 0,
) -> MagicMock:
    result = MagicMock()
    result.all.return_value = rows or []
    result.scalar.return_value = scalar
    result.scalar_one.return_value = scalar_one
    result.scalar_one_or_none.return_value = scalar_one_or_none
    result.rowcount = rowcount
    result.scalars.return_value.all.return_value = rows or []
    result.scalars.return_value.first.return_value = scalar_one_or_none
    return result


def _repo() -> tuple[ChatRepository, MagicMock]:
    db = MagicMock()
    db.execute = AsyncMock()
    db.get = AsyncMock()
    db.flush = AsyncMock()
    db.in_transaction.return_value = True
    return ChatRepository(db), db


async def test_properties_rls_and_get_by_id_variants() -> None:
    repo, db = _repo()
    assert repo.model is chat_module.Chat
    assert repo.dto_class is chat_module.ChatDTO

    await repo._set_rls_user(USER_ID)
    db.execute.assert_awaited_once()
    db.in_transaction.return_value = False
    with pytest.raises(AssertionError, match="active transaction"):
        await repo._set_rls_user(USER_ID)

    row = SimpleNamespace(id=CHAT_ID)
    repo._to_dto = MagicMock(return_value="chat-dto")  # type: ignore[method-assign]
    db.get.return_value = row
    assert await repo.get_by_id(CHAT_ID) == "chat-dto"
    assert await repo.get_by_id(CHAT_ID, load_messages=True) == "chat-dto"
    db.get.return_value = None
    assert await repo.get_by_id(CHAT_ID) is None


async def test_get_chats_for_user_covers_cursor_pagination_and_empty_result() -> None:
    repo, db = _repo()
    repo._to_dto = MagicMock(side_effect=lambda value: f"dto:{value.id}")  # type: ignore[method-assign]
    chat_a = SimpleNamespace(id=CHAT_ID, updated_at=NOW)
    chat_b = SimpleNamespace(id=OTHER_ID, updated_at=NOW)
    db.execute.return_value = _result(
        rows=[
            (chat_a, 1, None),
            (chat_b, 2, uuid.UUID(int=4)),
            (chat_a, 3, uuid.UUID(int=5)),
        ]
    )

    with patch.object(
        chat_module, "encode_datetime_cursor", return_value="next"
    ) as encode:
        items, has_more, next_cursor = await repo.get_chats_for_user(USER_ID, None, 2)

    assert items == [
        ("dto:" + str(CHAT_ID), 1, None),
        ("dto:" + str(OTHER_ID), 2, str(uuid.UUID(int=4))),
    ]
    assert has_more is True
    assert next_cursor == "next"
    encode.assert_called_once_with(NOW, OTHER_ID)

    db.execute.return_value = _result(rows=[])
    with patch.object(
        chat_module, "decode_datetime_cursor", return_value=(NOW, CHAT_ID)
    ):
        items, has_more, next_cursor = await repo.get_chats_for_user(
            USER_ID, "cursor", 10
        )
    assert items == []
    assert has_more is False
    assert next_cursor is None


async def test_message_and_user_lookup_helpers() -> None:
    repo, db = _repo()
    message_a = SimpleNamespace(id=CHAT_ID)
    message_b = SimpleNamespace(id=OTHER_ID)
    db.execute.return_value = _result(rows=[message_a, message_b])

    with patch.object(chat_module, "MessageDTO", _FakeMessageDTO):
        assert await repo.get_last_messages([]) == {}
        result = await repo.get_last_messages([CHAT_ID])
    assert result == {
        CHAT_ID: ("message-dto", message_a),
        OTHER_ID: ("message-dto", message_b),
    }

    assert await repo.get_user_display_names([]) == {}
    users = [
        SimpleNamespace(id=USER_ID, profile=SimpleNamespace(full_name="Alice")),
        SimpleNamespace(id=OTHER_ID, profile=None),
    ]
    db.execute.return_value = _result(rows=users)
    assert await repo.get_user_display_names([USER_ID, OTHER_ID]) == {
        USER_ID: "Alice",
        OTHER_ID: None,
    }


async def test_dm_creation_and_participant_mutations() -> None:
    repo, db = _repo()
    repo._to_dto = MagicMock(return_value="chat-dto")  # type: ignore[method-assign]
    user = User(id=USER_ID, email="one@example.com")
    other = User(id=OTHER_ID, email="two@example.com")

    db.execute.return_value = _result(scalar_one_or_none=None)
    assert await repo.find_existing_dm(USER_ID, OTHER_ID) is None
    db.execute.return_value = _result(scalar_one_or_none=SimpleNamespace(id=CHAT_ID))
    assert await repo.find_existing_dm(USER_ID, OTHER_ID) == "chat-dto"

    assert await repo.create_chat([user, other]) == "chat-dto"
    db.flush.assert_awaited()

    with patch.object(
        repo, "check_participant", new_callable=AsyncMock, return_value=True
    ):
        assert await repo.add_participant(CHAT_ID, USER_ID) is False
    with patch.object(
        repo, "check_participant", new_callable=AsyncMock, return_value=False
    ):
        assert await repo.add_participant(CHAT_ID, USER_ID) is True

    db.execute.return_value = _result(rowcount=3)
    assert await repo.remove_participant(CHAT_ID, USER_ID) == 3
    db.execute.return_value = _result(rowcount=0)
    assert await repo.remove_participant(CHAT_ID, USER_ID) == 0
    db.execute.return_value = _result(rowcount=-1)
    assert await repo.remove_participant(CHAT_ID, USER_ID) == 0
    db.execute.return_value = _result(rowcount=2)
    assert await repo.rename_chat(CHAT_ID, "Renamed") == 2


async def test_group_creation_deduplicates_creator_and_members() -> None:
    repo, db = _repo()
    repo._to_dto = MagicMock(return_value="group-dto")  # type: ignore[method-assign]
    creator = User(id=USER_ID, email="creator@example.com")
    member = User(id=OTHER_ID, email="member@example.com")

    assert await repo.create_group(creator, "Group", [creator, member]) == "group-dto"
    created = db.add.call_args.args[0]
    assert created.chat_type == "group"
    assert created.name == "Group"
    assert [user.id for user in created.participants] == [USER_ID, OTHER_ID]


async def test_unread_and_last_message_paths() -> None:
    repo, db = _repo()
    db.execute.return_value = _result(scalar_one=4)
    with patch.object(repo, "_set_rls_user", new_callable=AsyncMock):
        assert await repo.get_unread_count(CHAT_ID, USER_ID, "dm") == 4
        assert await repo.get_unread_count(CHAT_ID, USER_ID, "group") == 4

    with patch.object(chat_module, "MessageDTO", _FakeMessageDTO):
        db.execute.return_value = _result(scalar_one_or_none=None)
        assert await repo.get_last_message(CHAT_ID) is None
        message = SimpleNamespace(id=OTHER_ID)
        db.execute.return_value = _result(scalar_one_or_none=message)
        assert await repo.get_last_message(CHAT_ID) == ("message-dto", message)


async def test_get_messages_covers_rls_cursor_and_next_cursor() -> None:
    repo, db = _repo()
    repo._set_rls_user = AsyncMock()  # type: ignore[method-assign]
    messages = [
        SimpleNamespace(id=CHAT_ID, created_at=NOW),
        SimpleNamespace(id=OTHER_ID, created_at=NOW),
        SimpleNamespace(id=uuid.UUID(int=6), created_at=NOW),
    ]
    db.execute.return_value = _result(rows=messages)
    with (
        patch.object(chat_module, "MessageDTO", _FakeMessageDTO),
        patch.object(
            chat_module, "decode_datetime_cursor", return_value=(NOW, CHAT_ID)
        ),
        patch.object(
            chat_module, "encode_datetime_cursor", return_value="cursor-next"
        ) as encode,
    ):
        result, has_more, next_cursor = await repo.get_messages(
            CHAT_ID, "cursor", 2, user_id=USER_ID
        )
    assert result == [("message-dto", messages[0]), ("message-dto", messages[1])]
    assert has_more is True
    assert next_cursor == "cursor-next"
    encode.assert_called_once_with(NOW, str(OTHER_ID))
    repo._set_rls_user.assert_awaited_once_with(USER_ID)

    db.execute.return_value = _result(rows=[])
    with patch.object(chat_module, "MessageDTO", _FakeMessageDTO):
        result, has_more, next_cursor = await repo.get_messages(CHAT_ID, None, 2)
    assert result == []
    assert has_more is False
    assert next_cursor is None


async def test_create_message_and_mark_read_dm_and_group() -> None:
    repo, db = _repo()
    message = SimpleNamespace(id=CHAT_ID)
    with patch.object(chat_module, "MessageDTO", _FakeMessageDTO):
        assert await repo.create_message(message) == ("message-dto", message)
    db.flush.assert_awaited()

    db.execute.return_value = _result(rowcount=3)
    read_at, affected = await repo.mark_messages_read(CHAT_ID, USER_ID, "dm")
    assert read_at.tzinfo is not None
    assert affected == 3
    db.execute.return_value = _result(rowcount=-1)
    _, affected = await repo.mark_messages_read(CHAT_ID, USER_ID, "dm")
    assert affected == 0

    old_read = _result(scalar_one_or_none=None)
    count = _result(scalar_one=2)
    insert_result = _result()
    db.execute.side_effect = [old_read, count, insert_result]
    _, affected = await repo.mark_messages_read(CHAT_ID, USER_ID, "group")
    assert affected == 2

    old_read = _result(scalar_one_or_none=NOW)
    count = _result(scalar_one=1)
    update_result = _result()
    db.execute.side_effect = [old_read, count, update_result]
    _, affected = await repo.mark_messages_read(CHAT_ID, USER_ID, "group")
    assert affected == 1
    db.execute.side_effect = None


async def test_edit_delete_exists_and_reactions_cover_rowcount_edges() -> None:
    repo, db = _repo()
    db.execute.return_value = _result(rowcount=1)
    edited_at, affected = await repo.edit_message(CHAT_ID, USER_ID, "new")
    assert edited_at is not None and affected == 1
    db.execute.return_value = _result(rowcount=0)
    edited_at, affected = await repo.edit_message(CHAT_ID, USER_ID, "new")
    assert edited_at is None and affected == 0
    db.execute.return_value = _result(rowcount=-1)
    _, affected = await repo.edit_message(CHAT_ID, USER_ID, "new")
    assert affected == 0

    db.execute.return_value = _result(rowcount=1)
    deleted_at, affected = await repo.soft_delete_message(CHAT_ID, USER_ID)
    assert deleted_at is not None and affected == 1
    db.execute.return_value = _result(rowcount=0)
    deleted_at, affected = await repo.soft_delete_message(CHAT_ID, USER_ID)
    assert deleted_at is None and affected == 0
    db.execute.return_value = _result(rowcount=-1)
    _, affected = await repo.soft_delete_message(CHAT_ID, USER_ID)
    assert affected == 0

    db.execute.return_value = _result(scalar=True)
    assert await repo.message_exists_in_chat(CHAT_ID, CHAT_ID) is True
    db.execute.return_value = _result(scalar=False)
    assert await repo.message_exists_in_chat(CHAT_ID, CHAT_ID) is False

    db.execute.return_value = _result(rowcount=1)
    assert await repo.add_reaction(CHAT_ID, USER_ID, "👍") is True
    db.execute.return_value = _result(rowcount=0)
    assert await repo.add_reaction(CHAT_ID, USER_ID, "👍") is False
    db.execute.return_value = _result(rowcount=2)
    assert await repo.remove_reaction(CHAT_ID, USER_ID, "👍") == 2
    db.execute.return_value = _result(rowcount=0)
    assert await repo.remove_reaction(CHAT_ID, USER_ID, "👍") == 0


async def test_reactors_deletes_and_simple_crud_helpers() -> None:
    repo, db = _repo()
    users = [SimpleNamespace(id=USER_ID), SimpleNamespace(id=OTHER_ID)]
    db.execute.return_value = _result(rows=users)
    assert await repo.get_reactors(CHAT_ID, "👍") == users

    assert await repo.delete_messages([]) == 0
    db.execute.return_value = _result(rowcount=4)
    assert await repo.delete_messages([CHAT_ID]) == 4
    db.execute.return_value = _result(rowcount=-1)
    assert await repo.delete_messages([CHAT_ID]) == 0

    await repo.delete_chat(CHAT_ID)
    await repo.update_timestamp_by_id(CHAT_ID, NOW)
    db.get.return_value = "user-row"
    assert await repo.get_user(USER_ID) == "user-row"


async def test_participants_receipts_type_message_and_presence() -> None:
    repo, db = _repo()
    db.execute.return_value = _result(scalar=True)
    assert await repo.check_participant(CHAT_ID, USER_ID) is True
    db.execute.return_value = _result(scalar=False)
    assert await repo.check_participant(CHAT_ID, USER_ID) is False

    db.execute.return_value = _result(rows=[(USER_ID,), (OTHER_ID,)])
    assert await repo.get_participants(CHAT_ID) == [USER_ID, OTHER_ID]
    db.execute.return_value = _result(rows=[(USER_ID, NOW)])
    assert await repo.get_read_receipts(CHAT_ID) == [(USER_ID, NOW)]

    db.execute.return_value = _result(scalar_one_or_none="group")
    assert await repo.get_chat_type(CHAT_ID) == "group"

    with patch.object(chat_module, "MessageDTO", _FakeMessageDTO):
        db.execute.return_value = _result(scalar_one_or_none=None)
        assert await repo.get_message_by_id(CHAT_ID) is None
        message = SimpleNamespace(id=CHAT_ID)
        db.execute.return_value = _result(scalar_one_or_none=message)
        assert await repo.get_message_by_id(CHAT_ID) == ("message-dto", message)

    db.execute.return_value = _result(rows=[(USER_ID,), (OTHER_ID,), (USER_ID,)])
    assert await repo.get_presence_audience(USER_ID) == {OTHER_ID}


def test_repository_factory() -> None:
    repo, db = _repo()
    assert chat_module.get_chat_repository(db).db is db
    assert repo.db is db
