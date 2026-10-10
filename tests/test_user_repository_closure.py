from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from app.models import (
    DataAccessLog,
    EducationPath,
    InviteCode,
    User,
    UserPreferences,
    UserProfile,
)
from app.models.enums import UserRole
from app.repositories.user_repository import UserRepository


class _Result:
    def __init__(self, *, obj=None, objects=(), scalar_value=None, rowcount=0):
        self.obj = obj
        self.objects = list(objects)
        self.scalar_value = scalar_value
        self.rowcount = rowcount

    def scalars(self):
        return self

    def first(self):
        return (
            self.obj
            if self.obj is not None
            else (self.objects[0] if self.objects else None)
        )

    def scalar_one_or_none(self):
        return self.first()

    def all(self):
        return list(self.objects) if self.obj is None else [self.obj]

    def scalar(self):
        return self.scalar_value

    def unique(self):
        return self

    def __iter__(self):
        return iter(self.objects)


class _DB:
    def __init__(self, results=()):
        self.results = list(results)
        self.added = []
        self.executed = []
        self.flushed = 0
        self.refreshed = 0
        self.deleted = []

    async def execute(self, statement):
        self.executed.append(statement)
        return self.results.pop(0) if self.results else _Result()

    async def scalar(self, statement):
        self.executed.append(statement)
        return self.results.pop(0).scalar_value if self.results else None

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        self.flushed += 1

    async def refresh(self, obj, **kwargs):
        self.refreshed += 1

    async def delete(self, obj):
        self.deleted.append(obj)


def _user(user_id=None):
    user_id = user_id or uuid.uuid4()
    return User(
        id=user_id,
        email="repo@example.com",
        hashed_password="hash",  # pragma: allowlist secret
        role=UserRole.STUDENT,
        group_id=None,
        is_active=True,
        mfa_required=False,
        mfa_default_method=None,
        mfa_last_verified_at=None,
        mfa_epoch=0,
        created_at=datetime.now(UTC),
        profile=UserProfile(user_id=user_id, full_name="Repo User"),
        preferences=UserPreferences(user_id=user_id, dnd_enabled=False),
        education_path=EducationPath(user_id=user_id, program="Program"),
    )


def test_repository_properties_and_private_helpers():
    repo = UserRepository(_DB())
    assert repo.model is User
    assert repo.dto_class.__name__ == "UserDTO"
    assert repo._escape_like(r"a%_\b") == r"a\%\_\\b"
    assert repo._cast_id(42) == 42
    value = uuid.uuid4()
    assert repo._cast_id(value) is value
    assert repo._cast_id(value.hex) == value
    with pytest.raises(ValueError):
        repo._cast_id("not-a-uuid")


@pytest.mark.asyncio
async def test_get_variants_and_auth_queries():
    user = _user()
    db = _DB(
        [
            _Result(obj=user),
            _Result(obj=user),
            _Result(obj=user),
            _Result(obj=user),
            _Result(obj=user),
        ]
    )
    repo = UserRepository(db)
    assert (await repo.get(user.id)).id == user.id
    assert (await repo.get(str(user.id), with_for_update=True)).id == user.id
    assert (await repo.get_by_email(" REPO@EXAMPLE.COM ")).id == user.id
    assert (await repo.get_auth_by_email(user.email)).id == user.id
    assert (await repo.get_auth_by_id(str(user.id))).id == user.id
    db.results.append(_Result(obj=user))
    assert (await repo.get_auth_by_id(user.id)).id == user.id
    assert await repo.get("invalid") is None
    assert await repo.get_auth_by_id("invalid") is None


@pytest.mark.asyncio
async def test_get_users_by_ids_handles_empty_and_bulk_lookup():
    user = _user()
    db = _DB([_Result(objects=[user])])
    repo = UserRepository(db)

    assert await repo.get_users_by_ids([]) == []
    assert db.executed == []

    result = await repo.get_users_by_ids([user.id])
    assert result == [user]
    assert len(db.executed) == 1


@pytest.mark.asyncio
async def test_invite_and_access_log_queries():
    user_id = uuid.uuid4()
    invite = InviteCode(code="CODE", role="student")
    logs = [DataAccessLog(actor_user_id=user_id)]
    db = _DB(
        [
            _Result(obj=invite),
            _Result(obj=invite),
            _Result(objects=logs),
            _Result(objects=logs),
            _Result(objects=logs),
        ]
    )
    repo = UserRepository(db)
    assert await repo.get_invite_code("CODE") is invite
    assert await repo.get_invite_code("CODE", with_for_update=False) is invite
    assert await repo.get_user_access_logs(str(user_id)) == logs
    assert await repo.get_user_access_logs(user_id, before_dt=datetime.now(UTC)) == logs
    assert (
        await repo.get_user_access_logs(
            user_id, before_dt=datetime.now(UTC), after_id=uuid.uuid4()
        )
        == logs
    )
    assert await repo.get_user_access_logs("bad") == []


def test_extract_and_build_user_aggregate():
    repo = UserRepository(_DB())
    core, profile, preferences, education = repo._extract_cqrs_data(
        {
            "email": "new@example.com",
            "hashed_password": "hash",  # pragma: allowlist secret
            "profile_status": "active",
            "profile_department": "CS",
            "full_name": "Full Name",
            "timezone": "UTC",
            "program": "Program",
        }
    )
    assert core["email"] == "new@example.com"
    assert profile == {"status": "active", "department": "CS", "full_name": "Full Name"}
    assert preferences == {"timezone": "UTC"}
    assert education == {"program": "Program"}
    user = repo._build_user_aggregate(core, profile, preferences, education)
    assert user.profile.status == "active"
    assert user.preferences.timezone == "UTC"
    assert user.education_path.program == "Program"


@pytest.mark.asyncio
async def test_create_update_and_child_upsert_paths():
    user = _user()
    db = _DB([_Result(obj=user), _Result(obj=None), _Result(obj=None)])
    repo = UserRepository(db)
    repo._to_dto = lambda obj: obj
    created = await repo.create(
        {
            "email": "created@example.com",
            "hashed_password": "hash",  # pragma: allowlist secret
        }
    )
    assert created.email == "created@example.com"
    assert db.flushed == 1

    class _CreateInput:
        def model_dump(self):
            return {
                "email": "model@example.com",
                "hashed_password": "hash",  # pragma: allowlist secret
            }

    model_created = await repo.create(_CreateInput())
    assert model_created.email == "model@example.com"

    db.results = [_Result()]
    assert await repo.update(str(uuid.uuid4()), {}) is None
    db.results = [_Result(obj=user), _Result(obj=None), _Result(obj=None)]
    updated = await repo.update(
        user.id, {"profile_status": "updated", "timezone": "UTC"}
    )
    assert updated is not None
    assert user.profile.status == "updated"
    assert user.preferences.timezone == "UTC"

    class _UpdateInput:
        def model_dump(self, **kwargs):
            return {"email": "updated@example.com"}

    db.results = [_Result(obj=user)]
    updated = await repo.update(user.id, _UpdateInput())
    assert updated.email == "updated@example.com"

    db.results = [_Result(obj=UserProfile(user_id=user.id))]
    await repo._upsert_child(user, "profile", UserProfile, {"full_name": "New"})
    assert user.profile.full_name == "New"
    db.results = [_Result(obj=None)]
    await repo._upsert_child(user, "education_path", EducationPath, {"program": "New"})
    assert user.education_path.program == "New"
    await repo._upsert_child(user, "profile", UserProfile, {})


@pytest.mark.asyncio
async def test_create_with_invite_and_sensitive_delete():
    db = _DB()
    repo = UserRepository(db)
    repo._to_dto = lambda obj: obj
    invite = InviteCode(code="INV", role="student")
    result = await repo.create_with_invite(
        {
            "email": "invited@example.com",
            "hashed_password": "hash",  # pragma: allowlist secret
        },
        invite,
    )
    assert result.email == "invited@example.com"
    assert invite.is_used is True
    assert invite.is_active is False
    await repo.create_with_invite(
        {
            "email": "plain@example.com",
            "hashed_password": "hash",  # pragma: allowlist secret
        },
        None,
    )

    await repo.delete_sensitive_data(uuid.uuid4())
    await repo.delete_sensitive_data(str(uuid.uuid4()))
    before = len(db.executed)
    await repo.delete_sensitive_data("invalid")
    assert len(db.executed) == before

    assert isinstance(
        __import__(
            "app.repositories.user_repository", fromlist=["get_user_repository"]
        ).get_user_repository(db),
        UserRepository,
    )
