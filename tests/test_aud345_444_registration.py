"""Registration privacy and invitation transaction regressions."""

from __future__ import annotations

import sqlite3
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import IntegrityError, OperationalError

import app.models as models
from app.core.exceptions.domain import EntityAlreadyExists
from app.repositories.user_repository import UserRepository
from app.services.user import compliance_service

pytestmark = pytest.mark.asyncio(loop_scope="session")


def _payload(email: str, **overrides: str) -> dict[str, str]:
    payload = {
        "email": email,
        "password": f"Aa1!{uuid4().hex}",
        "full_name": "Registration Test",
    }
    payload.update(overrides)
    return payload


async def test_registration_response_hides_email_and_preserves_existing_credentials(
    async_client, db_session
) -> None:
    email = "registration-privacy@example.com"
    payload = _payload(email)
    different_password = f"Aa1!{uuid4().hex}"
    first = await async_client.post("/auth/register", json=payload)
    assert first.status_code == 200
    user = (
        await db_session.execute(select(models.User).where(models.User.email == email))
    ).scalar_one()
    original_hash = user.hashed_password

    repeated = await async_client.post(
        "/auth/register",
        json=_payload(email.upper(), password=different_password),
    )

    assert first.status_code == repeated.status_code == 200
    assert first.json() == repeated.json() == {"status": "ok"}
    await db_session.refresh(user)
    assert user.hashed_password == original_hash
    assert await db_session.scalar(select(func.count()).select_from(models.User)) == 1

    login = await async_client.post(
        "/auth/login/json",
        json={"email": email, "password": payload["password"]},
    )
    assert login.status_code == 200
    rejected = await async_client.post(
        "/auth/login/json",
        json={"email": email, "password": different_password},
    )
    assert rejected.status_code == 401


async def test_duplicate_does_not_bypass_invalid_invitation_validation(
    async_client,
) -> None:
    existing = "registered-invite@example.com"
    created = await async_client.post("/auth/register", json=_payload(existing))
    assert created.status_code == 200
    options = {"role": "teacher", "invite_code": "not-an-invite"}
    occupied = await async_client.post(
        "/auth/register", json=_payload(existing, **options)
    )
    available = await async_client.post(
        "/auth/register", json=_payload("free-invite@example.com", **options)
    )
    assert occupied.status_code == available.status_code == 400
    assert occupied.json() == available.json()


@pytest.mark.parametrize("role", ["superuser", "anonymous"])
async def test_internal_roles_are_rejected_for_occupied_and_available_email(
    async_client, db_session, role
) -> None:
    occupied = "role-occupied@example.com"
    fresh = "role-available@example.com"
    assert (
        await async_client.post("/auth/register", json=_payload(occupied))
    ).status_code == 200
    existing = await async_client.post(
        "/auth/register", json=_payload(occupied, role=role)
    )
    available = await async_client.post(
        "/auth/register", json=_payload(fresh, role=role)
    )
    assert existing.status_code == available.status_code == 400
    assert existing.json() == available.json()
    assert await db_session.scalar(select(func.count()).select_from(models.User)) == 1
    account = await db_session.scalar(
        select(models.User).where(models.User.email == occupied)
    )
    assert account is not None and account.role == models.UserRole.STUDENT


@pytest.mark.parametrize("role", ["teacher", "admin"])
async def test_public_privileged_roles_require_a_matching_active_invite(
    async_client, db_session, role
) -> None:
    occupied = "valid-role-existing-" + role + "@example.com"
    assert (
        await async_client.post("/auth/register", json=_payload(occupied))
    ).status_code == 200
    email = "valid-role-" + role + "@example.com"
    missing = await async_client.post("/auth/register", json=_payload(email, role=role))
    occupied_missing = await async_client.post(
        "/auth/register", json=_payload(occupied, role=role)
    )
    assert missing.status_code == occupied_missing.status_code == 400
    assert missing.json() == occupied_missing.json()
    wrong_role = "admin" if role == "teacher" else "teacher"
    db_session.add_all(
        [
            models.InviteCode(code="AUD444-WRONG", role=wrong_role),
            models.InviteCode(code="AUD444-RIGHT", role=role),
        ]
    )
    await db_session.commit()
    wrong = await async_client.post(
        "/auth/register", json=_payload(email, role=role, invite_code="AUD444-WRONG")
    )
    assert wrong.status_code == 400
    accepted = await async_client.post(
        "/auth/register", json=_payload(email, role=role, invite_code="AUD444-RIGHT")
    )
    assert accepted.status_code == 200
    account = await db_session.scalar(
        select(models.User).where(models.User.email == email)
    )
    assert account is not None and account.role.value == role


async def test_missing_group_is_rejected_for_occupied_and_available_email(
    async_client, db_session
) -> None:
    occupied = "group-occupied@example.com"
    assert (
        await async_client.post("/auth/register", json=_payload(occupied))
    ).status_code == 200
    missing_group = str(uuid4())
    existing = await async_client.post(
        "/auth/register", json=_payload(occupied, group_id=missing_group)
    )
    available = await async_client.post(
        "/auth/register",
        json=_payload("group-available@example.com", group_id=missing_group),
    )
    assert existing.status_code == available.status_code == 400
    assert existing.json() == available.json()
    assert await db_session.scalar(select(func.count()).select_from(models.User)) == 1

    group = models.Group(name="AUD345 Group")
    db_session.add(group)
    await db_session.commit()
    group_id = group.id
    accepted = await async_client.post(
        "/auth/register",
        json=_payload("group-valid@example.com", group_id=str(group_id)),
    )
    assert accepted.status_code == 200
    account = await db_session.scalar(
        select(models.User).where(models.User.email == "group-valid@example.com")
    )
    assert account is not None and account.group_id == group_id


async def test_registration_group_lookup_uses_postgres_key_share_lock() -> None:
    db = MagicMock()
    group_id = uuid4()
    db.scalar = AsyncMock(return_value=group_id)
    repo = UserRepository(db)
    assert await repo.registration_group_exists(group_id)
    statement = db.scalar.await_args.args[0]
    sql = str(statement.compile(dialect=postgresql.dialect()))
    assert "FOR KEY SHARE" in sql
    assert "NOWAIT" not in sql and "SKIP LOCKED" not in sql
    db.scalar.return_value = None
    assert not await repo.registration_group_exists(uuid4())


async def test_duplicate_does_not_consume_a_valid_invitation(
    async_client, db_session
) -> None:
    email = "occupied-valid-invite@example.com"
    assert (
        await async_client.post("/auth/register", json=_payload(email))
    ).status_code == 200
    invite = models.InviteCode(code="AUD444-VALID", role="teacher")
    db_session.add(invite)
    await db_session.commit()
    invite_id = invite.id

    options = {"role": "teacher", "invite_code": "AUD444-VALID"}
    duplicate = await async_client.post(
        "/auth/register", json=_payload(email, **options)
    )
    assert duplicate.status_code == 200
    assert duplicate.json() == {"status": "ok"}
    db_session.expire_all()
    saved = await db_session.get(models.InviteCode, invite_id)
    assert saved is not None
    assert saved.is_active and not saved.is_used and saved.used_by_user_id is None

    new = await async_client.post(
        "/auth/register", json=_payload("free-valid-invite@example.com", **options)
    )
    assert new.status_code == 200
    await db_session.refresh(saved)
    assert saved.is_used and not saved.is_active and saved.used_by_user_id is not None
    replay = await async_client.post(
        "/auth/register", json=_payload("replay-valid-invite@example.com", **options)
    )
    assert replay.status_code == 400


async def test_unique_email_race_is_private_and_does_not_consume_invite(
    async_client, db_session, monkeypatch
) -> None:
    email = "race-registration@example.com"
    first = await async_client.post("/auth/register", json=_payload(email))
    assert first.status_code == 200

    invite = models.InviteCode(code="AUD444-REAL", role="teacher")
    db_session.add(invite)
    await db_session.commit()
    invite_id = invite.id
    monkeypatch.setattr(
        UserRepository, "check_email_exists", AsyncMock(return_value=False)
    )

    race = await async_client.post(
        "/auth/register",
        json=_payload(email, role="teacher", invite_code="AUD444-REAL"),
    )

    assert race.status_code == first.status_code
    assert race.json() == first.json() == {"status": "ok"}
    db_session.expire_all()
    saved_invite = await db_session.get(models.InviteCode, invite_id)
    assert saved_invite is not None
    assert saved_invite.is_active and not saved_invite.is_used
    assert saved_invite.used_by_user_id is None
    assert await db_session.scalar(select(func.count()).select_from(models.User)) == 1


@pytest.mark.parametrize(
    ("sqlstate", "constraint", "table", "expected_status"),
    [
        ("23505", "ix_users_email_lower", "users", 200),
        ("23505", "ux_users_lower_email", "users", 200),
        ("23505", "uq_users_email", "users", 200),
        ("23505", "users_email_key", "users", 200),
        ("23505", "ix_users_email", "users", 200),
        ("23505", "users_pkey", "users", 400),
        ("23505", "uq_users_email_extra", "users", 400),
        ("23505", "uq_users_email", "another_table", 400),
        ("23503", "uq_users_email", "users", 400),
        (None, "uq_users_email", "users", 400),
    ],
)
async def test_only_known_postgres_email_constraint_is_private_success(
    async_client, monkeypatch, sqlstate, constraint, table, expected_status
) -> None:
    class DriverError(Exception):
        pass

    driver = DriverError("synthetic database failure")
    driver.sqlstate = sqlstate
    driver.diag = SimpleNamespace(constraint_name=constraint, table_name=table)
    error = IntegrityError("INSERT", {}, driver)
    monkeypatch.setattr(
        UserRepository, "create_with_invite", AsyncMock(side_effect=error)
    )
    response = await async_client.post(
        "/auth/register", json=_payload("database-error@example.com")
    )
    assert response.status_code == expected_status
    if expected_status == 200:
        assert response.json() == {"status": "ok"}


async def test_duplicate_uses_same_password_hashing_path(
    async_client, monkeypatch
) -> None:
    hash_password = AsyncMock(wraps=compliance_service.get_password_hash)
    monkeypatch.setattr(compliance_service, "get_password_hash", hash_password)
    payload = _payload("same-work@example.com")
    assert (await async_client.post("/auth/register", json=payload)).status_code == 200
    await async_client.post("/auth/register", json=payload)
    assert hash_password.await_count == 2


async def test_password_policy_applies_equally_to_new_and_existing_email(
    async_client, monkeypatch
) -> None:
    existing = _payload("policy-occupied@example.com")
    assert (await async_client.post("/auth/register", json=existing)).status_code == 200
    policy = AsyncMock()
    monkeypatch.setattr(compliance_service, "validate_password_hibp", policy)
    monkeypatch.setattr(
        compliance_service.settings, "password_hibp_check_enabled", True
    )

    duplicate = await async_client.post("/auth/register", json=existing)
    fresh = await async_client.post(
        "/auth/register", json=_payload("policy-available@example.com")
    )
    assert duplicate.status_code == fresh.status_code == 200
    assert duplicate.json() == fresh.json() == {"status": "ok"}
    assert policy.await_count == 2

    policy.side_effect = ValueError("Password policy rejected request")
    occupied_error = await async_client.post("/auth/register", json=existing)
    available_error = await async_client.post(
        "/auth/register", json=_payload("policy-rejected@example.com")
    )
    assert occupied_error.status_code == available_error.status_code == 400
    assert occupied_error.json() == available_error.json()


async def test_driver_cause_and_pgcode_identify_postgres_email_constraint(
    async_client, monkeypatch
) -> None:
    class DriverError(Exception):
        pass

    original = DriverError("synthetic driver cause")
    original.pgcode = "23505"
    original.constraint_name = "ix_users_email_lower"
    wrapped = DriverError("synthetic adapter error")
    wrapped.__cause__ = original
    error = IntegrityError("INSERT", {}, wrapped)
    monkeypatch.setattr(
        UserRepository, "create_with_invite", AsyncMock(side_effect=error)
    )
    response = await async_client.post(
        "/auth/register", json=_payload("adapter-cause@example.com")
    )
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.parametrize(
    ("message", "errorcode", "expected_status"),
    [
        (
            "UNIQUE constraint failed: users.email",
            sqlite3.SQLITE_CONSTRAINT_UNIQUE,
            200,
        ),
        (
            "UNIQUE constraint failed: index 'ux_users_lower_email'",
            sqlite3.SQLITE_CONSTRAINT_UNIQUE,
            200,
        ),
        ("UNIQUE constraint failed: users.id", sqlite3.SQLITE_CONSTRAINT_UNIQUE, 400),
        ("UNIQUE constraint failed: users.email", sqlite3.SQLITE_CONSTRAINT_CHECK, 400),
    ],
)
async def test_only_sqlite_email_unique_failure_is_private_success(
    async_client, monkeypatch, message, errorcode, expected_status
) -> None:
    driver = sqlite3.IntegrityError(message)
    driver.sqlite_errorcode = errorcode
    error = IntegrityError("INSERT", {}, driver)
    monkeypatch.setattr(
        UserRepository, "create_with_invite", AsyncMock(side_effect=error)
    )
    response = await async_client.post(
        "/auth/register", json=_payload("sqlite-error@example.com")
    )
    assert response.status_code == expected_status


@pytest.mark.parametrize(
    ("entity", "identifier"),
    [("Other", "unrelated"), ("User", "other@example.com")],
)
async def test_unrelated_domain_conflict_is_not_reported_as_success(
    async_client, monkeypatch, entity, identifier
) -> None:
    monkeypatch.setattr(
        compliance_service.UserComplianceService,
        "register_user",
        AsyncMock(side_effect=EntityAlreadyExists(entity, identifier)),
    )
    response = await async_client.post(
        "/auth/register", json=_payload("domain-error@example.com")
    )
    assert response.status_code == 400


async def test_invite_lock_failure_is_not_reported_as_private_success(
    async_client, monkeypatch
) -> None:
    class DriverError(Exception):
        sqlstate = "55P03"

    failure = OperationalError("SELECT", {}, DriverError("lock unavailable"))
    monkeypatch.setattr(
        UserRepository, "get_invite_code", AsyncMock(side_effect=failure)
    )
    response = await async_client.post(
        "/auth/register",
        json=_payload("invite-lock@example.com", role="teacher", invite_code="TEST"),
    )
    assert response.status_code == 400


async def test_invite_lookup_waits_for_the_other_transaction() -> None:
    db = MagicMock()
    db.execute = AsyncMock(return_value=MagicMock())
    repo = UserRepository(db)
    await repo.get_invite_code("AUD444-LOCK")
    statement = db.execute.await_args.args[0]
    sql = str(statement.compile(dialect=postgresql.dialect()))
    assert "FOR UPDATE" in sql
    assert "NOWAIT" not in sql
    assert "SKIP LOCKED" not in sql

    await repo.get_invite_code("AUD444-READ", with_for_update=False)
    read_sql = str(db.execute.await_args.args[0].compile(dialect=postgresql.dialect()))
    assert "FOR UPDATE" not in read_sql
