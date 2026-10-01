from __future__ import annotations

import importlib.util
import json
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType, SimpleNamespace
from uuid import UUID, uuid4

import pytest
from fastapi.encoders import jsonable_encoder
from sqlalchemy import String, UniqueConstraint

from app.models.chat import Chat, Message
from app.models.enums import UserRole
from app.models.schedule import Group
from app.models.users import EducationPath, User, UserProfile
from app.schemas.chat import ChatResponse
from app.schemas.dtos.chat import ChatDTO
from app.schemas.dtos.schedule import GroupDTO
from app.schemas.dtos.user import UserAuthDTO, UserDTO, UserListingDTO
from app.schemas.groups import GroupOut
from app.schemas.users import (
    UserAdminUpdate,
    UserBase,
    UserCreate,
    UserEducationBase,
    UserOut,
    UserPreferencesBase,
    UserProfileBase,
    UserProfileUpdate,
    UserPublicOut,
)
from scripts import seed_demo_data

ROOT = Path(__file__).resolve().parents[1]
MIGRATION_PATH = (
    ROOT / "alembic" / "versions" / "202609300001_add_chat_demo_seed_key.py"
)
GROUP_MIGRATION_PATH = (
    ROOT / "alembic" / "versions" / "202609300002_add_group_demo_seed_key.py"
)


class Rows:
    def __init__(self, rows: list[object]) -> None:
        self._rows = rows

    def all(self) -> list[object]:
        return list(self._rows)


class DemoOwnershipSession:
    def __init__(
        self,
        *,
        scalar_responses: list[object] | None = None,
        user_owner_responses: list[object] | None = None,
        chat_query_responses: list[list[Chat]] | None = None,
    ) -> None:
        self.scalar_responses = list(scalar_responses or [])
        self.user_owner_responses = list(user_owner_responses or [])
        self.chat_query_responses = list(chat_query_responses or [])
        self.added: list[object] = []
        self.chats: list[Chat] = []
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

    async def scalars(self, statement: object) -> Rows:
        entity = statement.column_descriptions[0].get("entity")
        if entity is Chat:
            response = self.chat_query_responses.pop(0)
            return Rows(response)
        raise AssertionError(f"Unexpected fake scalar query entity: {entity!r}")

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


class DemoGroupOwnershipSession:
    def __init__(
        self,
        *,
        canonical_group: Group | None = None,
        owner_group: Group | None = None,
    ) -> None:
        self.canonical_group = canonical_group
        self.owner_group = owner_group
        self.added: list[object] = []
        self.flush_count = 0

    async def scalar(self, statement: object) -> Group | None:
        parameters = statement.compile().params
        if "ue-demo-v1:group:class" in parameters.values():
            return self.owner_group
        return self.canonical_group

    def add(self, entity: object) -> None:
        self.added.append(entity)
        if isinstance(entity, Group) and entity.id is None:
            entity.id = uuid4()
        if isinstance(entity, Group):
            self.owner_group = entity

    async def flush(self) -> None:
        self.flush_count += 1


def _user(email: str) -> User:
    user = User(
        email=email,
        hashed_password="synthetic-hash",
        role=UserRole.STUDENT,
        is_active=True,
    )
    user.id = uuid4()
    return user


@pytest.mark.asyncio
async def test_seed_group_refuses_unmarked_canonical_collision_without_mutation() -> (
    None
):
    existing = Group(
        name="ЗИ-301",
        course=3,
        faculty="Институт информационных технологий",
    )
    existing.id = uuid4()
    database = DemoGroupOwnershipSession(canonical_group=existing)

    with pytest.raises(RuntimeError, match="canonical demo group is unowned"):
        await seed_demo_data.seed_group(database)

    assert existing.demo_seed_key is None
    assert database.added == []
    assert database.flush_count == 0


@pytest.mark.asyncio
async def test_seed_group_marks_new_group_and_reuses_it_after_user_edits() -> None:
    database = DemoGroupOwnershipSession()

    group = await seed_demo_data.seed_group(database)

    assert group.demo_seed_key == seed_demo_data.DEMO_CLASS_GROUP_SEED_KEY
    assert group.name == "ЗИ-301"
    assert group.course == 3
    assert group.faculty == "Институт информационных технологий"
    assert database.added == [group]
    assert database.flush_count == 1

    group.name = "User-edited study group"
    group.course = 4
    group.faculty = "User-edited faculty"
    reused = await seed_demo_data.seed_group(database)

    assert reused is group
    assert reused.name == "User-edited study group"
    assert reused.course == 4
    assert reused.faculty == "User-edited faculty"
    assert database.added == [group]
    assert database.flush_count == 1


def _load_migration() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "add_chat_demo_seed_key", MIGRATION_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_group_migration() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "add_group_demo_seed_key", GROUP_MIGRATION_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_chat_seed_key_is_nullable_unique_and_internal() -> None:
    column = Chat.__table__.c.demo_seed_key
    constraints = {
        constraint.name: constraint
        for constraint in Chat.__table__.constraints
        if isinstance(constraint, UniqueConstraint)
    }

    assert isinstance(column.type, String)
    assert column.type.length == 96
    assert column.nullable is True
    assert constraints["uq_chats_demo_seed_key"].columns.keys() == ["demo_seed_key"]
    assert "demo_seed_key" not in ChatDTO.model_fields
    assert "demo_seed_key" not in ChatResponse.model_fields


def test_group_seed_key_is_nullable_unique_and_internal() -> None:
    column = Group.__table__.c.demo_seed_key
    constraints = {
        constraint.name: constraint
        for constraint in Group.__table__.constraints
        if isinstance(constraint, UniqueConstraint)
    }

    assert isinstance(column.type, String)
    assert column.type.length == 96
    assert column.nullable is True
    assert constraints["uq_groups_demo_seed_key"].columns.keys() == ["demo_seed_key"]
    assert "demo_seed_key" not in GroupOut.model_fields
    assert "demo_seed_key" not in GroupDTO.model_fields


def test_user_demo_seed_key_is_nullable_unique_and_absent_from_public_and_write_schemas() -> (
    None
):
    assert hasattr(User, "demo_seed_key")
    column = User.__table__.c.demo_seed_key
    constraints = {
        constraint.name: constraint
        for constraint in User.__table__.constraints
        if isinstance(constraint, UniqueConstraint)
    }
    assert isinstance(column.type, String)
    assert column.type.length == 96
    assert column.nullable is True
    assert constraints["uq_users_demo_seed_key"].columns.keys() == ["demo_seed_key"]

    user_schemas = (
        UserAdminUpdate,
        UserAuthDTO,
        UserBase,
        UserCreate,
        UserDTO,
        UserEducationBase,
        UserListingDTO,
        UserOut,
        UserPreferencesBase,
        UserProfileBase,
        UserProfileUpdate,
        UserPublicOut,
    )
    assert all("demo_seed_key" not in schema.model_fields for schema in user_schemas)


def test_demo_seed_markers_never_appear_in_orm_backed_api_json() -> None:
    user = _user("demo-peer@example.com")
    user.demo_seed_key = "ue-demo-v1:user:synthetic-contract-marker"
    user.created_at = datetime(2026, 9, 30, tzinfo=UTC)
    user.mfa_required = False
    user.mfa_default_method = None
    user.mfa_last_verified_at = None
    user.mfa_epoch = 0

    chat = Chat()
    chat.id = uuid4()
    chat.created_at = user.created_at
    chat.updated_at = user.created_at
    chat.chat_type = "group"
    chat.name = "Synthetic demo group"
    chat.created_by = user.id
    chat.demo_seed_key = "ue-demo-v1:chat:synthetic-contract-marker"
    chat.participants = []
    chat.messages = []

    group = Group(
        name="Synthetic demo group",
        course=3,
        faculty="Synthetic faculty",
        demo_seed_key="ue-demo-v1:group:synthetic-contract-marker",
    )
    group.id = uuid4()
    group.created_at = user.created_at

    api_models = (
        UserOut.model_validate(user),
        UserPublicOut.model_validate(user),
        UserDTO.model_validate(user, from_attributes=True),
        ChatResponse.model_validate(chat),
        ChatDTO.model_validate(chat),
        GroupOut.model_validate(group),
        GroupDTO.model_validate(group, from_attributes=True),
    )
    private_markers = (
        "ue-demo-v1:user:synthetic-contract-marker",
        "ue-demo-v1:chat:synthetic-contract-marker",
        "ue-demo-v1:group:synthetic-contract-marker",
    )

    for api_model in api_models:
        response_json = json.dumps(jsonable_encoder(api_model), sort_keys=True)
        assert "demo_seed_key" not in response_json
        assert all(marker not in response_json for marker in private_markers)


@pytest.mark.asyncio
async def test_second_peer_uses_reserved_test_identity_and_is_reused_without_mutation(
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
        lambda _length: "synthetic-one-shot-input",
    )
    group = SimpleNamespace(id=uuid4())
    database = DemoOwnershipSession(
        scalar_responses=[None], user_owner_responses=[None]
    )

    peer = await seed_demo_data.seed_demo_second_peer_user(database, group)

    profile = next(item for item in database.added if isinstance(item, UserProfile))
    education = next(item for item in database.added if isinstance(item, EducationPath))
    assert peer.email == seed_demo_data.DEMO_SECOND_PEER_EMAIL
    assert peer.email.endswith(".test")
    assert peer.role is UserRole.STUDENT
    assert peer.group_id == group.id
    assert peer.demo_seed_key == seed_demo_data.DEMO_SECOND_PEER_USER_SEED_KEY
    assert education.record_book_number is None
    assert profile.user_id == peer.id

    original_hash = peer.hashed_password
    peer.group_id = uuid4()
    profile.about = "user-edited synthetic profile"
    education.program = "user-edited synthetic program"
    education.record_book_number = "SYNTHETIC-USER-EDITED-007"
    database.scalar_responses.append(peer)
    database.user_owner_responses.append(peer)

    reused = await seed_demo_data.seed_demo_second_peer_user(database, group)

    assert reused is peer
    assert peer.hashed_password == original_hash
    assert peer.group_id != group.id
    assert profile.about == "user-edited synthetic profile"
    assert education.program == "user-edited synthetic program"
    assert education.record_book_number == "SYNTHETIC-USER-EDITED-007"
    assert len([item for item in database.added if isinstance(item, User)]) == 1


@pytest.mark.asyncio
async def test_second_peer_seed_key_collision_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    existing_key_owner = _user("synthetic.unrelated@example.test")
    database = DemoOwnershipSession(
        scalar_responses=[None], user_owner_responses=[existing_key_owner]
    )
    monkeypatch.setattr(
        seed_demo_data,
        "get_password_hash_sync",
        lambda *_args: pytest.fail("an occupied key must not create a user"),
    )

    with pytest.raises(
        RuntimeError, match="reserved demo peer ownership key is occupied"
    ):
        await seed_demo_data.seed_demo_second_peer_user(
            database, SimpleNamespace(id=uuid4())
        )

    assert database.added == []


@pytest.mark.asyncio
async def test_demo_dm_uses_ownership_key_and_reuses_exact_members(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner = _user("synthetic.owner@example.test")
    peer = _user("synthetic.peer@example.test")
    database = DemoOwnershipSession(chat_query_responses=[[]])
    invalidations: list[tuple[UUID, tuple[UUID, ...]]] = []

    async def record_invalidation(chat_id: UUID, participant_ids: tuple[UUID, ...]):
        invalidations.append((chat_id, participant_ids))

    monkeypatch.setattr(
        seed_demo_data, "_invalidate_demo_chat_caches", record_invalidation
    )

    chat = await seed_demo_data.seed_demo_dm(database, owner, peer)

    assert chat.demo_seed_key == seed_demo_data.DEMO_DM_SEED_KEY
    assert chat.chat_type == "dm"
    assert chat.name is None
    assert chat.created_by is None
    assert {participant.id for participant in chat.participants} == {
        owner.id,
        peer.id,
    }
    assert invalidations == [(chat.id, (owner.id, peer.id))]
    prior_flush_count = database.flush_count

    reused = await seed_demo_data.seed_demo_dm(database, owner, peer)

    assert reused is chat
    assert database.flush_count == prior_flush_count
    assert len(database.chats) == 1
    assert invalidations == [(chat.id, (owner.id, peer.id))]


@pytest.mark.asyncio
async def test_demo_dm_does_not_adopt_unmarked_exact_pair() -> None:
    owner = _user("synthetic.owner@example.test")
    peer = _user("synthetic.peer@example.test")
    user_chat = Chat(chat_type="dm", participants=[owner, peer])
    database = DemoOwnershipSession(chat_query_responses=[[user_chat]])

    with pytest.raises(RuntimeError, match="reserved demo DM participant pair"):
        await seed_demo_data.seed_demo_dm(database, owner, peer)

    assert database.added == []
    assert database.flush_count == 0
    assert user_chat.demo_seed_key is None


@pytest.mark.asyncio
async def test_demo_dm_owner_key_with_member_drift_fails_closed() -> None:
    owner = _user("synthetic.owner@example.test")
    peer = _user("synthetic.peer@example.test")
    other = _user("synthetic.other@example.test")
    marked_chat = Chat(
        chat_type="dm",
        demo_seed_key=seed_demo_data.DEMO_DM_SEED_KEY,
        participants=[owner, other],
    )
    database = DemoOwnershipSession()
    database.chats.append(marked_chat)

    with pytest.raises(RuntimeError, match="demo DM ownership key has drifted"):
        await seed_demo_data.seed_demo_dm(database, owner, peer)

    assert database.added == []
    assert database.flush_count == 0


@pytest.mark.asyncio
async def test_demo_group_is_idempotent_and_preserves_user_edited_title(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner = _user("synthetic.owner@example.test")
    first_peer = _user(seed_demo_data.DEMO_PEER_EMAIL)
    second_peer = _user(seed_demo_data.DEMO_SECOND_PEER_EMAIL)
    database = DemoOwnershipSession(chat_query_responses=[[]])
    invalidations: list[tuple[UUID, tuple[UUID, ...]]] = []

    async def record_invalidation(chat_id: UUID, participant_ids: tuple[UUID, ...]):
        invalidations.append((chat_id, participant_ids))

    monkeypatch.setattr(
        seed_demo_data, "_invalidate_demo_chat_caches", record_invalidation
    )

    chat = await seed_demo_data.seed_demo_group(
        database, owner, [first_peer, second_peer]
    )

    expected_members = {owner.id, first_peer.id, second_peer.id}
    assert chat.demo_seed_key == seed_demo_data.DEMO_GROUP_SEED_KEY
    assert chat.chat_type == "group"
    assert chat.name == seed_demo_data.DEMO_GROUP_NAME
    assert chat.created_by == owner.id
    assert {participant.id for participant in chat.participants} == expected_members
    assert not chat.messages
    assert invalidations == [(chat.id, tuple(sorted(expected_members, key=str)))]
    prior_flush_count = database.flush_count

    chat.name = "user-edited demo title"
    preserved_message = Message(
        chat_id=chat.id,
        sender_id=owner.id,
        content="user-written synthetic message",
    )
    chat.messages.append(preserved_message)
    previous_messages = list(chat.messages)
    reused = await seed_demo_data.seed_demo_group(
        database, owner, [first_peer, second_peer]
    )

    assert reused is chat
    assert reused.name == "user-edited demo title"
    assert {participant.id for participant in reused.participants} == expected_members
    assert reused.messages == previous_messages
    assert database.flush_count == prior_flush_count
    assert len(database.chats) == 1
    assert invalidations == [(chat.id, tuple(sorted(expected_members, key=str)))]


@pytest.mark.asyncio
async def test_demo_group_key_with_partial_membership_fails_closed() -> None:
    owner = _user("synthetic.owner@example.test")
    first_peer = _user(seed_demo_data.DEMO_PEER_EMAIL)
    second_peer = _user(seed_demo_data.DEMO_SECOND_PEER_EMAIL)
    marked_group = Chat(
        chat_type="group",
        name="user-edited title",
        created_by=owner.id,
        demo_seed_key=seed_demo_data.DEMO_GROUP_SEED_KEY,
        participants=[owner, first_peer],
    )
    database = DemoOwnershipSession()
    database.chats.append(marked_group)

    with pytest.raises(RuntimeError, match="demo group ownership key has drifted"):
        await seed_demo_data.seed_demo_group(database, owner, [first_peer, second_peer])

    assert database.added == []
    assert database.flush_count == 0
    assert {participant.id for participant in marked_group.participants} == {
        owner.id,
        first_peer.id,
    }


@pytest.mark.asyncio
async def test_demo_group_without_key_fails_closed_on_partial_seed_peer_membership() -> (
    None
):
    owner = _user("synthetic.owner@example.test")
    first_peer = _user(seed_demo_data.DEMO_PEER_EMAIL)
    second_peer = _user(seed_demo_data.DEMO_SECOND_PEER_EMAIL)
    preexisting_group = Chat(
        chat_type="group",
        name="custom user group",
        created_by=owner.id,
        participants=[owner, first_peer],
    )
    database = DemoOwnershipSession(chat_query_responses=[[preexisting_group]])

    with pytest.raises(RuntimeError, match="reserved demo group peer membership"):
        await seed_demo_data.seed_demo_group(database, owner, [first_peer, second_peer])

    assert database.added == []
    assert database.flush_count == 0
    assert preexisting_group.name == "custom user group"
    assert {participant.id for participant in preexisting_group.participants} == {
        owner.id,
        first_peer.id,
    }


def test_seed_key_migration_is_additive_nullable_unique_and_reversible_by_metadata_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    migration = _load_migration()
    operations: list[tuple[object, ...]] = []

    class FakeOperations:
        def add_column(self, table_name: str, column: object) -> None:
            operations.append(("add_column", table_name, column))

        def create_unique_constraint(
            self, name: str, table_name: str, columns: list[str]
        ) -> None:
            operations.append(("create_unique_constraint", name, table_name, columns))

        def drop_constraint(self, name: str, table_name: str, type_: str) -> None:
            operations.append(("drop_constraint", name, table_name, type_))

        def drop_column(self, table_name: str, column_name: str) -> None:
            operations.append(("drop_column", table_name, column_name))

    monkeypatch.setattr(migration, "op", FakeOperations())

    migration.upgrade()

    add_user_column = operations[0]
    assert add_user_column[0:2] == ("add_column", "users")
    user_column = add_user_column[2]
    assert user_column.name == "demo_seed_key"
    assert isinstance(user_column.type, String)
    assert user_column.type.length == 96
    assert user_column.nullable is True
    assert operations[1] == (
        "create_unique_constraint",
        "uq_users_demo_seed_key",
        "users",
        ["demo_seed_key"],
    )
    add_chat_column = operations[2]
    assert add_chat_column[0:2] == ("add_column", "chats")
    chat_column = add_chat_column[2]
    assert chat_column.name == "demo_seed_key"
    assert isinstance(chat_column.type, String)
    assert chat_column.type.length == 96
    assert chat_column.nullable is True
    assert operations[3] == (
        "create_unique_constraint",
        "uq_chats_demo_seed_key",
        "chats",
        ["demo_seed_key"],
    )

    operations.clear()
    migration.downgrade()

    assert operations == [
        ("drop_constraint", "uq_chats_demo_seed_key", "chats", "unique"),
        ("drop_column", "chats", "demo_seed_key"),
        ("drop_constraint", "uq_users_demo_seed_key", "users", "unique"),
        ("drop_column", "users", "demo_seed_key"),
    ]
    assert all("drop_table" not in str(operation) for operation in operations)


def test_group_seed_key_migration_is_additive_and_does_not_adopt_existing_groups(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    migration = _load_group_migration()
    assert migration.revision == "202609300002"
    assert migration.down_revision == "202609300001"
    operations: list[tuple[object, ...]] = []

    class FakeOperations:
        def add_column(self, table_name: str, column: object) -> None:
            operations.append(("add_column", table_name, column))

        def create_unique_constraint(
            self, name: str, table_name: str, columns: list[str]
        ) -> None:
            operations.append(("create_unique_constraint", name, table_name, columns))

        def drop_constraint(self, name: str, table_name: str, type_: str) -> None:
            operations.append(("drop_constraint", name, table_name, type_))

        def drop_column(self, table_name: str, column_name: str) -> None:
            operations.append(("drop_column", table_name, column_name))

    monkeypatch.setattr(migration, "op", FakeOperations())

    migration.upgrade()

    assert len(operations) == 2
    add_column = operations[0]
    assert add_column[:2] == ("add_column", "groups")
    column = add_column[2]
    assert column.name == "demo_seed_key"
    assert isinstance(column.type, String)
    assert column.type.length == 96
    assert column.nullable is True
    assert operations[1] == (
        "create_unique_constraint",
        "uq_groups_demo_seed_key",
        "groups",
        ["demo_seed_key"],
    )

    operations.clear()
    migration.downgrade()

    assert operations == [
        ("drop_constraint", "uq_groups_demo_seed_key", "groups", "unique"),
        ("drop_column", "groups", "demo_seed_key"),
    ]
