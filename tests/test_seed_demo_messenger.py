from __future__ import annotations

from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

from app.api.ws import presence
from app.models.chat import Chat
from app.models.enums import UserRole
from app.models.users import EducationPath, User, UserProfile
from scripts import seed_demo_data


class ScalarRows:
    def __init__(self, rows: list[object]) -> None:
        self.rows = rows

    def all(self) -> list[object]:
        return self.rows


class DemoMessengerSession:
    def __init__(
        self,
        scalar_responses: list[object],
        user_owner_responses: list[object] | None = None,
    ) -> None:
        self.scalar_responses = scalar_responses
        self.user_owner_responses = list(user_owner_responses or [])
        self.added: list[object] = []
        self.chats: list[Chat] = []
        self.chat_queries: list[object] = []
        self.flush_count = 0

    async def scalar(self, statement: object) -> object:
        entity = statement.column_descriptions[0].get("entity")
        if entity is Chat:
            parameters = statement.compile().params
            key = next(
                (
                    value
                    for value in parameters.values()
                    if isinstance(value, str) and value.startswith("ue-demo-v1:")
                ),
                None,
            )
            return next(
                (chat for chat in self.chats if chat.demo_seed_key == key), None
            )
        if entity is User:
            parameters = statement.compile().params
            key = next(
                (
                    value
                    for value in parameters.values()
                    if isinstance(value, str) and value.startswith("ue-demo-v1:user:")
                ),
                None,
            )
            if key is not None:
                return self.user_owner_responses.pop(0)
        return self.scalar_responses.pop(0)

    async def scalars(self, statement: object) -> ScalarRows:
        self.chat_queries.append(statement)
        parameters = statement.compile().params
        participant_ids = {
            value for value in parameters.values() if isinstance(value, UUID)
        }
        rows = [
            chat
            for chat in self.chats
            if chat.chat_type == "dm"
            and {participant.id for participant in chat.participants} == participant_ids
        ]
        return ScalarRows(rows)

    def add(self, entity: object) -> None:
        self.added.append(entity)
        if isinstance(entity, User) and entity.id is None:
            entity.id = uuid4()
        if isinstance(entity, Chat):
            if entity.id is None:
                entity.id = uuid4()
            self.chats.append(entity)

    async def flush(self) -> None:
        self.flush_count += 1


@pytest.mark.asyncio
async def test_demo_peer_and_dm_are_owned_idempotent_and_preserve_custom_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        seed_demo_data,
        "get_password_hash_sync",
        lambda value: "synthetic-argon-hash" if value else pytest.fail("empty input"),
    )
    monkeypatch.setattr(
        seed_demo_data.secrets,
        "token_urlsafe",
        lambda _length: "synthetic-discarded-demo-input",
    )
    invalidations: list[tuple[str, tuple[object, ...]]] = []

    async def record_invalidation(chat_id, participant_ids) -> None:
        invalidations.append(("chat", (chat_id,)))
        invalidations.append(("presence", participant_ids))

    monkeypatch.setattr(
        seed_demo_data, "_invalidate_demo_chat_caches", record_invalidation
    )

    group = SimpleNamespace(id=uuid4())
    owner = User(
        email="synthetic.owner@example.test",
        hashed_password="synthetic-owner-hash",  # pragma: allowlist secret -- synthetic messenger test password
        role=UserRole.STUDENT,
        is_active=True,
    )
    owner.id = uuid4()
    database = DemoMessengerSession([None], user_owner_responses=[None])

    peer = await seed_demo_data.seed_demo_peer_user(database, group)
    third_participant = User(
        email="synthetic.third@example.test",
        hashed_password="synthetic-third-hash",  # pragma: allowlist secret -- synthetic messenger test password
        role=UserRole.STUDENT,
    )
    third_participant.id = uuid4()
    existing_group = Chat(
        chat_type="group",
        name="Synthetic user-created group",
        created_by=owner.id,
        participants=[owner, peer, third_participant],
    )
    database.chats.append(existing_group)
    dm = await seed_demo_data.seed_demo_dm(database, owner, peer)

    assert peer.role is UserRole.STUDENT
    assert peer.group_id == group.id
    assert peer.email.endswith("@example.test")
    peer_profile = next(
        item for item in database.added if isinstance(item, UserProfile)
    )
    peer_education = next(
        item for item in database.added if isinstance(item, EducationPath)
    )
    assert peer_profile.user_id == peer.id
    assert peer_education.user_id == peer.id
    assert peer.demo_seed_key == seed_demo_data.DEMO_PEER_USER_SEED_KEY
    assert peer_education.record_book_number is None
    assert isinstance(dm, Chat)
    assert dm.chat_type == "dm"
    assert dm.created_by is None
    assert dm.id is not None
    assert {participant.id for participant in dm.participants} == {owner.id, peer.id}
    assert len(database.chats) == 2
    assert sum(chat.chat_type == "dm" for chat in database.chats) == 1
    assert existing_group.name == "Synthetic user-created group"
    query_sql = str(database.chat_queries[0].compile()).lower()
    query_params = database.chat_queries[0].compile().params
    assert "chat_participants" in query_sql
    assert "chat_type" in query_sql
    assert {owner.id, peer.id}.issubset(
        {value for value in query_params.values() if isinstance(value, UUID)}
    )
    assert "2" in {str(value) for value in query_params.values()}

    peer_password_hash = peer.hashed_password
    custom_group_id = uuid4()
    peer.group_id = custom_group_id
    peer_profile.about = "Synthetic user-edited profile"
    peer_education.program = "Synthetic user-edited program"
    peer_education.record_book_number = "SYNTHETIC-USER-EDITED-008"

    database.scalar_responses.append(peer)
    database.user_owner_responses.append(peer)
    reused_peer = await seed_demo_data.seed_demo_peer_user(database, group)
    reused_dm = await seed_demo_data.seed_demo_dm(database, owner, peer)

    assert reused_peer is peer
    assert reused_dm is dm
    assert peer.hashed_password == peer_password_hash
    assert peer.group_id == custom_group_id
    assert peer_profile.about == "Synthetic user-edited profile"
    assert peer_education.program == "Synthetic user-edited program"
    assert peer_education.record_book_number == "SYNTHETIC-USER-EDITED-008"
    assert len(database.chats) == 2
    assert invalidations == [("chat", (dm.id,)), ("presence", (owner.id, peer.id))]


@pytest.mark.asyncio
async def test_reserved_peer_identity_conflict_fails_without_mutation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    peer = SimpleNamespace(
        id=uuid4(),
        email="demo.peer@example.test",
        role=UserRole.STUDENT,
        group_id=uuid4(),
        hashed_password="synthetic-preserved-hash",  # pragma: allowlist secret -- synthetic messenger test password
    )
    database = DemoMessengerSession([peer], user_owner_responses=[None])
    monkeypatch.setattr(
        seed_demo_data,
        "get_password_hash_sync",
        lambda *_args: pytest.fail("an existing identity must never be reset"),
    )

    with pytest.raises(RuntimeError, match="reserved demo peer identity is occupied"):
        await seed_demo_data.seed_demo_peer_user(database, SimpleNamespace(id=uuid4()))

    assert database.added == []
    assert (
        peer.hashed_password == "synthetic-preserved-hash"  # pragma: allowlist secret
    )


@pytest.mark.asyncio
async def test_reserved_peer_seed_key_collision_is_not_claimed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    key_owner = User(
        email="synthetic.unrelated@example.test",
        hashed_password="synthetic-hash",  # pragma: allowlist secret -- synthetic messenger test password
        role=UserRole.STUDENT,
    )
    key_owner.id = uuid4()
    database = DemoMessengerSession([None], user_owner_responses=[key_owner])
    monkeypatch.setattr(
        seed_demo_data,
        "get_password_hash_sync",
        lambda *_args: pytest.fail("an occupied owner key must not create a user"),
    )

    with pytest.raises(
        RuntimeError, match="reserved demo peer ownership key is occupied"
    ):
        await seed_demo_data.seed_demo_peer_user(database, SimpleNamespace(id=uuid4()))

    assert database.added == []


@pytest.mark.asyncio
async def test_reserved_peer_with_another_role_is_not_promoted_or_reset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    account = SimpleNamespace(
        id=uuid4(),
        email="demo.peer@example.test",
        role=UserRole.TEACHER,
        hashed_password="synthetic-preserved-hash",  # pragma: allowlist secret
    )
    database = DemoMessengerSession([account], user_owner_responses=[None])
    monkeypatch.setattr(
        seed_demo_data,
        "get_password_hash_sync",
        lambda *_args: pytest.fail("an existing identity must never be reset"),
    )

    with pytest.raises(RuntimeError, match="reserved demo peer identity is occupied"):
        await seed_demo_data.seed_demo_peer_user(database, SimpleNamespace(id=uuid4()))

    assert account.role is UserRole.TEACHER
    expected_hash = "synthetic-preserved-hash"  # pragma: allowlist secret
    assert account.hashed_password == expected_hash
    assert database.added == []


@pytest.mark.asyncio
async def test_duplicate_exact_dms_fail_closed_instead_of_choosing_one() -> None:
    owner = User(
        email="synthetic.owner@example.test",
        hashed_password="synthetic-owner-hash",  # pragma: allowlist secret
        role=UserRole.STUDENT,
    )
    owner.id = uuid4()
    peer = User(
        email="synthetic.peer@example.test",
        hashed_password="synthetic-peer-hash",  # pragma: allowlist secret -- synthetic messenger test password
        role=UserRole.STUDENT,
    )
    peer.id = uuid4()
    first = Chat(chat_type="dm", participants=[owner, peer])
    second = Chat(chat_type="dm", participants=[owner, peer])
    database = DemoMessengerSession([])
    database.chats.extend([first, second])

    with pytest.raises(
        RuntimeError, match="reserved demo DM participant pair is already occupied"
    ):
        await seed_demo_data.seed_demo_dm(database, owner, peer)

    assert database.added == []
    assert len(database.chats) == 2


def test_messenger_demo_seed_requires_a_verified_live_stand(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = "ue-live-0123456789abcdef"
    monkeypatch.setenv("LIVE_STAND_OWNER_VERIFIED", "1")
    monkeypatch.setenv("LIVE_STAND_SEED_PROJECT", project)
    monkeypatch.setenv("COMPOSE_PROJECT_NAME", project)
    monkeypatch.delenv("UE_SEED_TARGET", raising=False)

    assert seed_demo_data._is_live_stand_demo_target(project)

    monkeypatch.setenv("UE_SEED_TARGET", "admin-smoke")
    assert not seed_demo_data._is_live_stand_demo_target(project)

    monkeypatch.delenv("LIVE_STAND_OWNER_VERIFIED", raising=False)
    monkeypatch.delenv("LIVE_STAND_SEED_PROJECT", raising=False)
    monkeypatch.delenv("COMPOSE_PROJECT_NAME", raising=False)
    monkeypatch.delenv("UE_SEED_TARGET", raising=False)
    assert not seed_demo_data._is_live_stand_demo_target(project)


@pytest.mark.asyncio
async def test_dm_cache_invalidation_uses_existing_presence_hooks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    chat_id = uuid4()
    participant_ids = (uuid4(), uuid4())
    invalidations: list[tuple[str, tuple[object, ...]]] = []

    async def record_chat(chat_id: UUID) -> None:
        invalidations.append(("chat", (chat_id,)))

    async def record_presence(*user_ids: UUID) -> None:
        invalidations.append(("presence", user_ids))

    monkeypatch.setattr(presence, "invalidate_chat_participants_cache", record_chat)
    monkeypatch.setattr(presence, "invalidate_presence_audience_cache", record_presence)

    await seed_demo_data._invalidate_demo_chat_caches(chat_id, participant_ids)

    assert invalidations == [
        ("chat", (chat_id,)),
        ("presence", participant_ids),
    ]
