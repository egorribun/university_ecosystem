"""Shared DTO consumers must remain safe with loaded or deferred profiles."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import event, inspect, select
from sqlalchemy.orm import selectinload

from app.models import User, UserProfile
from app.models.chat import Chat, Message
from app.repositories.chat_repository import ChatRepository
from app.repositories.unit_of_work import uow_from_session
from app.schemas.chat import ChatResponse, MessageResponse
from app.schemas.dtos.chat import ChatDTO, ChatParticipantDTO, MessageDTO
from app.services.chat.creation_service import ChatCreationService
from app.services.chat.query_service import ChatQueryService

_NOW = datetime(2026, 10, 1, 9, 0, tzinfo=UTC)


@contextmanager
def _query_count(session):
    statements = []
    engine = session.get_bind()

    def before_execute(_conn, _cursor, statement, _parameters, _context, _many):
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", before_execute)
    try:
        yield statements
    finally:
        event.remove(engine, "before_cursor_execute", before_execute)


async def _seed(session, factory):
    owner = await factory(avatar_url="/static/owner.png")
    peer = await factory(avatar_url="/static/peer.png")
    chat = Chat(participants=[owner, peer], created_at=_NOW, updated_at=_NOW)
    session.add(chat)
    await session.flush()
    message = Message(
        chat_id=chat.id, sender_id=peer.id, content="Message", created_at=_NOW
    )
    session.add(message)
    await session.commit()
    ids = SimpleNamespace(
        owner=owner.id, peer=peer.id, chat=chat.id, message=message.id
    )
    session.expunge_all()
    return ids


async def _users(session, ids, profile_state):
    statement = select(User).where(User.id.in_([ids.owner, ids.peer]))
    if profile_state != "clean":
        loader = selectinload(User.profile)
        if profile_state == "deferred":
            loader = loader.defer(UserProfile.avatar_url)
        statement = statement.options(loader)
    users = list((await session.scalars(statement)).all())
    for user in users:
        if profile_state == "clean":
            assert user.profile is None
        else:
            assert user.profile is not None
            assert ("avatar_url" in inspect(user.profile).unloaded) == (
                profile_state == "deferred"
            )
    return {user.id: user for user in users}


def _serialize_without_sql(session, values):
    session.expunge_all()
    with _query_count(session) as statements:
        for dto in values:
            assert dto is not None
            if isinstance(dto, ChatDTO):
                response = ChatResponse.model_validate(dto)
                assert all(p.avatar_url is None for p in dto.participants)
                for message in dto.messages:
                    MessageResponse.model_validate(message).model_dump(mode="json")
                    if message.sender is not None:
                        assert message.sender.avatar_url is None
            else:
                response = MessageResponse.model_validate(dto)
                if dto.sender is not None:
                    assert dto.sender.avatar_url is None
            response.model_dump(mode="json")
    assert statements == []


@pytest.mark.asyncio
@pytest.mark.parametrize("profile_state", ["clean", "loaded", "deferred"])
@pytest.mark.parametrize(
    "path",
    [
        "get_by_id",
        "get_by_id_with_messages",
        "find_existing_dm",
        "get_last_message",
        "get_last_messages",
        "get_messages",
        "get_message_by_id",
    ],
)
async def test_read_dto_consumers_are_profile_state_independent(
    db_session, user_factory, profile_state, path
):
    ids = await _seed(db_session, user_factory)
    users = await _users(db_session, ids, profile_state)
    repository = ChatRepository(db_session)
    if path == "get_by_id":
        values = [await repository.get_by_id(ids.chat)]
    elif path == "get_by_id_with_messages":
        values = [await repository.get_by_id(ids.chat, True, user_id=ids.owner)]
        assert len(values[0].messages) == 1
    elif path == "find_existing_dm":
        values = [await repository.find_existing_dm(ids.owner, ids.peer)]
    elif path == "get_last_message":
        values = [await repository.get_last_message(ids.chat, user_id=ids.owner)]
    elif path == "get_last_messages":
        values = list(
            (
                await repository.get_last_messages([ids.message], user_id=ids.owner)
            ).values()
        )
    elif path == "get_messages":
        values, has_more, cursor = await repository.get_messages(
            ids.chat, None, 20, user_id=ids.owner
        )
        assert has_more is False and cursor is None
    else:
        values = [
            await repository.get_message_by_id(
                ids.message, chat_id=ids.chat, user_id=ids.owner
            )
        ]
    assert len(values) == 1
    assert set(users) == {ids.owner, ids.peer}
    _serialize_without_sql(db_session, values)


@pytest.mark.asyncio
@pytest.mark.parametrize("profile_state", ["clean", "loaded", "deferred"])
@pytest.mark.parametrize("path", ["create_chat", "create_group", "create_message"])
async def test_create_dto_consumers_are_profile_state_independent(
    db_session, user_factory, profile_state, path
):
    ids = await _seed(db_session, user_factory)
    users = await _users(db_session, ids, profile_state)
    repository = ChatRepository(db_session)
    if path == "create_chat":
        result = await repository.create_chat([users[ids.owner], users[ids.peer]])
    elif path == "create_group":
        result = await repository.create_group(
            users[ids.owner], "Team", [users[ids.peer]]
        )
    else:
        result = await repository.create_message(
            Message(
                chat_id=ids.chat,
                sender_id=ids.peer,
                sender=users[ids.peer],
                content="Created",
                created_at=_NOW,
            )
        )
        assert result.sender is not None
    _serialize_without_sql(db_session, [result])


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ["get", "list", "list_after", "create", "update"])
async def test_inherited_chat_dto_consumers_serialize_detached(
    db_session, user_factory, path
):
    ids = await _seed(db_session, user_factory)
    repository = ChatRepository(db_session)
    if path == "get":
        values = [await repository.get(ids.chat)]
    elif path == "list":
        values = list(await repository.list())
    elif path == "list_after":
        values = list(await repository.list_after())
    elif path == "create":
        values = [await repository.create({"created_at": _NOW, "updated_at": _NOW})]
    else:
        values = [await repository.update(ids.chat, {"name": "Updated"})]
    assert len(values) == 1
    _serialize_without_sql(db_session, values)


@pytest.mark.asyncio
@pytest.mark.parametrize("detached", [False, True], ids=["attached", "detached"])
@pytest.mark.parametrize("kind", ["participant", "message"])
async def test_shared_dto_does_not_read_deferred_profile_avatar(
    db_session, user_factory, detached, kind
):
    ids = await _seed(db_session, user_factory)
    users = await _users(db_session, ids, "deferred")
    user = users[ids.peer]
    message = (
        await db_session.scalars(
            select(Message)
            .where(Message.id == ids.message)
            .options(selectinload(Message.sender))
        )
    ).one()
    assert message.sender is user
    assert "avatar_url" in inspect(user.profile).unloaded
    if detached:
        db_session.expunge_all()
    with _query_count(db_session) as statements:
        if kind == "participant":
            dto = ChatParticipantDTO.model_validate(user)
            assert dto.avatar_url is None
        else:
            dto = MessageDTO.model_validate(message)
            assert dto.sender is not None and dto.sender.avatar_url is None
        dto.model_dump(mode="json")
    assert statements == []


@pytest.mark.asyncio
@pytest.mark.parametrize("profile_state", ["loaded", "deferred"])
@pytest.mark.parametrize("existing", [False, True], ids=["new", "existing"])
async def test_direct_chat_service_serialization_with_profile_state(
    db_session, user_factory, profile_state, existing
):
    owner = await user_factory(avatar_url="/static/owner.png")
    peer = await user_factory(avatar_url="/static/peer.png")
    ids = SimpleNamespace(owner=owner.id, peer=peer.id)
    if existing:
        db_session.add(Chat(participants=[owner, peer]))
        await db_session.commit()
    db_session.expunge_all()
    users = await _users(db_session, ids, profile_state)
    lock = SimpleNamespace(acquire=AsyncMock(return_value=True), release=AsyncMock())
    client = SimpleNamespace(lock=MagicMock(return_value=lock))
    cache = SimpleNamespace(_get_client=AsyncMock(return_value=client))
    service = ChatCreationService(uow_from_session(db_session), db_session, cache)
    with (
        patch(
            "app.services.chat.creation_service.invalidate_chat_participants_cache",
            new=AsyncMock(),
        ),
        patch(
            "app.services.chat.creation_service.invalidate_presence_audience_cache",
            new=AsyncMock(),
        ),
        patch(
            "app.services.chat.creation_service.build_presence_map",
            new=AsyncMock(return_value={}),
        ),
    ):
        result = await service.create_chat(users[ids.owner], ids.peer, "en")
    db_session.expunge_all()
    with _query_count(db_session) as statements:
        assert {p.id for p in result.participants} == {ids.owner, ids.peer}
        assert all(p.avatar_url is None for p in result.participants)
        assert result.chat_type == "dm"
        result.model_dump(mode="json")
    assert statements == []
    lock.release.assert_awaited_once()


@pytest.mark.asyncio
async def test_chat_list_avatar_projection_has_constant_batched_query_count(
    db_session, user_factory
):
    owner = await user_factory(avatar_url="/static/owner.png")
    peer = await user_factory(avatar_url="/static/peer.png")
    ids = SimpleNamespace(owner=owner.id, peer=peer.id)
    db_session.add(Chat(participants=[owner, peer]))
    await db_session.commit()
    counts = []
    for size, profile_state in [(1, "clean"), (8, "loaded"), (8, "deferred")]:
        db_session.expunge_all()
        users = await _users(db_session, ids, profile_state)
        if size == 8 and len(counts) == 1:
            db_session.add_all(
                [
                    Chat(participants=[users[ids.owner], users[ids.peer]])
                    for _ in range(7)
                ]
            )
            await db_session.commit()
            db_session.expunge_all()
            users = await _users(db_session, ids, profile_state)
        service = ChatQueryService(db_session, ChatRepository(db_session))
        with (
            patch(
                "app.services.chat.query_service.build_presence_map",
                new=AsyncMock(return_value={}),
            ),
            _query_count(db_session) as statements,
        ):
            result = await service.get_chats(users[ids.owner], None, 20)
        counts.append(len(statements))
        assert len(result.items) == size
        for item in result.items:
            assert {p.id: p.avatar_url for p in item.participants} == {
                ids.owner: "/static/owner.png",
                ids.peer: "/static/peer.png",
            }
        db_session.expunge_all()
        with _query_count(db_session) as serialized:
            result.model_dump(mode="json")
        assert serialized == []
    assert counts[0] == counts[1] == counts[2]
    assert counts[0] <= 4
