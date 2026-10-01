from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.models.enums import UserRole
from scripts import seed_demo_data


class ExistingDemoAccountSession:
    def __init__(self, user: SimpleNamespace) -> None:
        self.user = user
        self.scalar_call = 0
        self.added: list[object] = []
        self.flush_count = 0

    async def scalar(self, _statement: object) -> object:
        result = (self.user, self.user, self.user.id, self.user.id)[
            self.scalar_call % 4
        ]
        self.scalar_call += 1
        return result

    def add(self, entity: object) -> None:
        self.added.append(entity)

    async def flush(self) -> None:
        self.flush_count += 1


class OwnershipAwareDemoAccountSession:
    def __init__(
        self,
        *,
        account_by_email: object | None = None,
        account_by_seed_key: object | None = None,
        profile_exists: bool = False,
        education_exists: bool = False,
    ) -> None:
        self.account_by_email = account_by_email
        self.account_by_seed_key = account_by_seed_key
        self.profile_exists = profile_exists
        self.education_exists = education_exists
        self.added: list[object] = []
        self.flush_count = 0

    async def scalar(self, statement: object) -> object | None:
        entity = statement.column_descriptions[0].get("entity")
        parameters = statement.compile().params
        if entity is seed_demo_data.User:
            if any(name.startswith("email_") for name in parameters):
                return self.account_by_email
            if any(name.startswith("demo_seed_key_") for name in parameters):
                return self.account_by_seed_key
        if entity is seed_demo_data.UserProfile:
            return self.account_by_email.id if self.profile_exists else None
        if entity is seed_demo_data.EducationPath:
            return self.account_by_email.id if self.education_exists else None
        raise AssertionError(f"Unexpected demo-account query: {entity!r}")

    def add(self, entity: object) -> None:
        self.added.append(entity)

    async def flush(self) -> None:
        self.flush_count += 1


@pytest.mark.asyncio
async def test_rerun_preserves_existing_synthetic_account_and_owned_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_group_id = uuid4()
    user = SimpleNamespace(
        id=uuid4(),
        email=seed_demo_data.DEMO_PRIMARY_USER_EMAIL,
        demo_seed_key=seed_demo_data.DEMO_PRIMARY_USER_SEED_KEY,
        role=UserRole.STUDENT,
        hashed_password="synthetic-hash-sentinel",  # pragma: allowlist secret -- synthetic seed-account test password
        group_id=original_group_id,
    )
    profile = SimpleNamespace(
        user_id=user.id,
        full_name="Synthetic account owner",
        about="Synthetic user-authored biography",
        telegram="@synthetic_profile",
        status="Synthetic custom status",
        avatar_url="https://example.test/synthetic-avatar.png",
    )
    education_path = SimpleNamespace(
        user_id=user.id,
        institute="Synthetic institute",
        program="Synthetic custom program",
        record_book_number="SYNTHETIC-001",
    )
    user.profile = profile
    user.education_path = education_path
    database = ExistingDemoAccountSession(user)
    group = SimpleNamespace(id=uuid4())

    monkeypatch.setattr(
        seed_demo_data,
        "get_password_hash_sync",
        lambda *_args: pytest.fail("reusing an account must not hash a new password"),
    )

    first = await seed_demo_data.seed_user(database, group)
    second = await seed_demo_data.seed_user(database, group)

    assert first is user
    assert second is user
    assert user.hashed_password == "synthetic-hash-sentinel"  # pragma: allowlist secret
    assert user.group_id == original_group_id
    assert profile.full_name == "Synthetic account owner"
    assert profile.about == "Synthetic user-authored biography"
    assert profile.telegram == "@synthetic_profile"
    assert profile.status == "Synthetic custom status"
    assert profile.avatar_url == "https://example.test/synthetic-avatar.png"
    assert education_path.institute == "Synthetic institute"
    assert education_path.program == "Synthetic custom program"
    assert education_path.record_book_number == "SYNTHETIC-001"
    assert database.added == []
    assert database.flush_count == 2


@pytest.mark.asyncio
async def test_new_primary_account_is_marked_with_private_ownership_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database = OwnershipAwareDemoAccountSession()
    monkeypatch.setattr(
        seed_demo_data,
        "get_password_hash_sync",
        lambda _password: "synthetic-hash",  # pragma: allowlist secret -- synthetic password-hash test stub
    )

    user = await seed_demo_data.seed_user(database, SimpleNamespace(id=uuid4()))

    assert user.email == seed_demo_data.DEMO_PRIMARY_USER_EMAIL
    assert user.demo_seed_key == seed_demo_data.DEMO_PRIMARY_USER_SEED_KEY
    assert user in database.added


@pytest.mark.asyncio
async def test_primary_owner_key_collision_fails_without_creating_an_account(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    unrelated_owner = SimpleNamespace(
        id=uuid4(),
        email="unrelated.synthetic@example.test",
        demo_seed_key=seed_demo_data.DEMO_PRIMARY_USER_SEED_KEY,
    )
    database = OwnershipAwareDemoAccountSession(account_by_seed_key=unrelated_owner)
    monkeypatch.setattr(
        seed_demo_data,
        "get_password_hash_sync",
        lambda *_args: pytest.fail("an occupied owner key must not create a user"),
    )

    with pytest.raises(
        RuntimeError, match="canonical demo account ownership key is already occupied"
    ):
        await seed_demo_data.seed_user(database, SimpleNamespace(id=uuid4()))

    assert database.added == []
    assert database.flush_count == 0


@pytest.mark.asyncio
async def test_unmarked_canonical_account_collision_fails_before_any_mutation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_group_id = None
    user = SimpleNamespace(
        id=uuid4(),
        email="test@university.dev",
        demo_seed_key=None,
        role=UserRole.STUDENT,
        hashed_password="synthetic-preserved-hash",  # pragma: allowlist secret -- synthetic seed-account test password
        group_id=original_group_id,
    )
    database = OwnershipAwareDemoAccountSession(account_by_email=user)

    monkeypatch.setattr(
        seed_demo_data,
        "get_password_hash_sync",
        lambda *_args: pytest.fail("an occupied account must not be recreated"),
    )

    with pytest.raises(RuntimeError, match="canonical demo account is unowned"):
        await seed_demo_data.seed_user(database, SimpleNamespace(id=uuid4()))

    assert user.group_id is original_group_id
    assert user.demo_seed_key is None
    assert (
        user.hashed_password == "synthetic-preserved-hash"  # pragma: allowlist secret
    )
    assert database.added == []
    assert database.flush_count == 0


@pytest.mark.asyncio
async def test_canonical_account_and_owner_key_must_resolve_to_same_user() -> None:
    user = SimpleNamespace(
        id=uuid4(),
        email=seed_demo_data.DEMO_PRIMARY_USER_EMAIL,
        demo_seed_key=None,
        role=UserRole.STUDENT,
        hashed_password="synthetic-preserved-hash",  # pragma: allowlist secret
        group_id=None,
    )
    unrelated_owner = SimpleNamespace(
        id=uuid4(),
        email="unrelated.synthetic@example.test",
        demo_seed_key=seed_demo_data.DEMO_PRIMARY_USER_SEED_KEY,
    )
    database = OwnershipAwareDemoAccountSession(
        account_by_email=user,
        account_by_seed_key=unrelated_owner,
    )

    with pytest.raises(RuntimeError, match="canonical demo account is unowned"):
        await seed_demo_data.seed_user(database, SimpleNamespace(id=uuid4()))

    assert user.demo_seed_key is None
    assert user.group_id is None
    assert database.added == []
    assert database.flush_count == 0
