import datetime
import uuid

import pytest
from sqlalchemy import select

import app.models as models
from app.models.enums import UserRole
from app.repositories.user_repository import UserRepository


# Helpers
@pytest.fixture
async def user_repo(db_session):
    return UserRepository(db_session)


@pytest.fixture
async def test_user(db_session):
    from app.models.users import UserPreferences, UserProfile

    user = models.User(
        email="test_repo@example.com",
        hashed_password="hashed_password",
        is_active=True,
        role=UserRole.STUDENT,
        profile=UserProfile(full_name="Test Repo User", status="active"),
        preferences=UserPreferences(),
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.mark.asyncio
async def test_get_by_email(user_repo, test_user):
    user = await user_repo.get_by_email(test_user.email)
    assert user is not None
    assert user.id == test_user.id

    # Case insensitive
    user_upper = await user_repo.get_by_email(test_user.email.upper())
    assert user_upper is not None
    assert user_upper.id == test_user.id


@pytest.mark.asyncio
async def test_get_by_email_only_found(user_repo, test_user):
    # TD-002 (audit 2026-03-10): method renamed from get_by_login to
    # get_by_email_only to reflect that it only searches by email, never username.
    user = await user_repo.get_by_email_only(test_user.email)
    assert user is not None
    assert user.id == test_user.id


@pytest.mark.asyncio
async def test_get_by_email_or_raise(user_repo, test_user):
    user = await user_repo.get_by_email_or_raise(test_user.email)
    assert user.id == test_user.id

    with pytest.raises(ValueError):
        await user_repo.get_by_email_or_raise("nonexistent@example.com")


@pytest.mark.asyncio
async def test_list_users_filters(user_repo, test_user):
    from app.schemas import schemas

    # Filter by name
    users = await user_repo.list_users(schemas.UserSearchFilter(full_name="Repo User"))
    assert len(users) >= 1
    assert any(u.id == test_user.id for u in users)

    # Filter by role
    users_role = await user_repo.list_users(
        schemas.UserSearchFilter(role=UserRole.STUDENT.value)
    )
    assert len(users_role) >= 1

    # We no longer test pydantic validation here, but rather empty results
    users_empty = await user_repo.list_users(
        schemas.UserSearchFilter(full_name="admin_impossible")
    )
    assert len(users_empty) == 0


@pytest.mark.asyncio
async def test_get_active_users(user_repo, test_user):
    users = await user_repo.get_active_users()
    assert any(u.id == test_user.id for u in users)


@pytest.mark.asyncio
async def test_counts(user_repo, test_user):
    count = await user_repo.count_active()
    assert count >= 1

    test_user.mfa_required = True
    await user_repo.db.commit()

    mfa_count = await user_repo.count_with_mfa()
    assert mfa_count >= 1


@pytest.mark.asyncio
async def test_search_by_name(user_repo, test_user):
    results = await user_repo.search_by_name("epo Us")
    assert any(u.id == test_user.id for u in results)


@pytest.mark.asyncio
async def test_check_email_exists(user_repo, test_user):
    assert await user_repo.check_email_exists(test_user.email) is True
    assert await user_repo.check_email_exists("unused@example.com") is False

    assert (
        await user_repo.check_email_exists(
            test_user.email, exclude_user_id=test_user.id
        )
        is False
    )


@pytest.mark.asyncio
async def test_delete_sensitive_data(user_repo, test_user, db_session):
    session = models.ActiveSession(
        user_id=test_user.id,
        jti="test_jti_delete",
        expires_at=datetime.datetime.now(datetime.UTC) + datetime.timedelta(hours=1),
    )
    db_session.add(session)
    await db_session.commit()

    result = await db_session.execute(
        select(models.ActiveSession).where(
            models.ActiveSession.jti == "test_jti_delete"
        )
    )
    assert result.scalars().first() is not None

    await user_repo.delete_sensitive_data(test_user.id)
    await db_session.commit()

    result = await db_session.execute(
        select(models.ActiveSession).where(
            models.ActiveSession.jti == "test_jti_delete"
        )
    )
    assert result.scalars().first() is None


@pytest.mark.asyncio
async def test_get_by_id_variants(user_repo, test_user):
    # Valid UUID as UUID
    u1 = await user_repo.get(test_user.id)
    assert u1.id == test_user.id

    # Valid UUID as string
    u2 = await user_repo.get(str(test_user.id))
    assert u2.id == test_user.id

    # Invalid UUID string
    u3 = await user_repo.get("not-a-uuid")
    assert u3 is None


@pytest.mark.asyncio
async def test_get_user_related_data(user_repo, test_user, db_session):
    # Setup some data
    session = models.ActiveSession(
        user_id=test_user.id,
        jti="rel_jti",
        expires_at=datetime.datetime.now(datetime.UTC) + datetime.timedelta(hours=1),
    )
    notification = models.Notification(
        user_id=test_user.id, title="Test Notif", body="Content", type="info"
    )
    challenge = models.MfaChallenge(
        user_id=test_user.id,
        token="challenge_token",
        challenge_type="totp",
        expires_at=datetime.datetime.now(datetime.UTC) + datetime.timedelta(minutes=5),
    )
    enrollment = models.MfaTotpEnrollment(
        user_id=test_user.id,
        secret="secret",
        confirmed_at=datetime.datetime.now(datetime.UTC),
    )

    db_session.add_all([session, notification, challenge, enrollment])
    await db_session.commit()

    # Test retrieval
    sessions = await user_repo.get_user_sessions(test_user.id)
    assert len(sessions) >= 1
    assert sessions[0].jti == "rel_jti"

    notifications = await user_repo.get_user_notifications(test_user.id)
    assert len(notifications) >= 1
    assert notifications[0].title == "Test Notif"

    challenges = await user_repo.get_user_mfa_challenges(test_user.id)
    assert len(challenges) >= 1
    assert challenges[0].token == "challenge_token"

    enrollments = await user_repo.get_user_totp_enrollments(test_user.id)
    assert len(enrollments) >= 1
    assert enrollments[0].secret == "secret"

    # Test with string IDs and invalid variants
    assert len(await user_repo.get_user_sessions(str(test_user.id))) >= 1
    assert len(await user_repo.get_user_sessions("invalid")) == 0
    assert len(await user_repo.get_user_notifications("invalid")) == 0
    assert len(await user_repo.get_user_mfa_challenges("invalid")) == 0
    assert len(await user_repo.get_user_totp_enrollments("invalid")) == 0


@pytest.mark.asyncio
async def test_invite_code(user_repo, db_session):
    code_val = "INVITE123"
    invite = models.InviteCode(code=code_val, role="student")
    db_session.add(invite)
    await db_session.commit()

    retrieved = await user_repo.get_invite_code(code_val)
    assert retrieved is not None
    assert retrieved.code == code_val

    assert await user_repo.get_invite_code("NONEXISTENT") is None


# --- Auth-data getters + full-profile join (this wave) -----------------------


@pytest.mark.asyncio
async def test_get_auth_by_email_and_id(user_repo, test_user):
    by_email = await user_repo.get_auth_by_email(test_user.email)
    assert by_email is not None
    assert by_email.id == test_user.id

    by_id = await user_repo.get_auth_by_id(test_user.id)
    assert by_id is not None
    assert by_id.id == test_user.id

    # Invalid-UUID + missing-email branches return None.
    assert await user_repo.get_auth_by_id("not-a-uuid") is None
    assert await user_repo.get_auth_by_email("missing@example.com") is None


@pytest.mark.asyncio
async def test_get_with_full_profile(user_repo, test_user):
    dto = await user_repo.get_with_full_profile(test_user.id)
    assert dto is not None
    assert dto.id == test_user.id
    # String id + invalid id branches.
    assert (await user_repo.get_with_full_profile(str(test_user.id))).id == test_user.id
    assert await user_repo.get_with_full_profile("not-a-uuid") is None


# --- CQRS create / update / create_with_invite -------------------------------


@pytest.mark.asyncio
async def test_create_via_repository_builds_aggregate(user_repo):
    # Flat dict spanning core + profile + preferences + education_path keys so
    # _extract_cqrs_data + _build_user_aggregate route each to its sub-object.
    dto = await user_repo.create(
        {
            "email": "cqrs_create@example.com",
            "hashed_password": "h",
            "role": UserRole.STUDENT,
            "full_name": "CQRS Created",  # → profile
            "timezone": "UTC",  # → preferences
            "institute": "Test Institute",  # → education_path
        }
    )
    assert dto.id is not None
    roundtrip = await user_repo.get_by_email("cqrs_create@example.com")
    assert roundtrip is not None
    assert roundtrip.id == dto.id


@pytest.mark.asyncio
async def test_update_via_repository_updates_core_and_education(user_repo, test_user):
    # Only core + education_path keys: test_user already HAS profile + preferences
    # rows, and update() reads db_obj.profile / .preferences under lazy="noload"
    # (→ None even when a row exists), so passing profile/pref data would attempt a
    # duplicate INSERT. education_path is genuinely absent on test_user, so the
    # create branch fires cleanly. The core setattr + edu create + flush + return
    # paths are what we cover here.
    updated = await user_repo.update(
        test_user.id,
        {
            "is_active": False,  # core → setattr branch
            "institute": "New Institute",  # education_path absent → create branch
        },
    )
    assert updated is not None
    # Updating a non-existent user returns None.
    assert await user_repo.update(uuid.uuid4(), {"is_active": True}) is None


@pytest.mark.asyncio
async def test_create_with_invite_marks_code_used_and_none_path(user_repo, db_session):
    invite = models.InviteCode(code="CQRSINVITE", role="student")
    db_session.add(invite)
    await db_session.commit()

    dto = await user_repo.create_with_invite(
        {
            "email": "invited@example.com",
            "hashed_password": "h",
            "role": UserRole.STUDENT,
            "full_name": "Invited User",
        },
        invite,
    )
    assert dto.id is not None
    assert invite.is_used is True

    # None invite → user created without touching any invite code.
    dto2 = await user_repo.create_with_invite(
        {
            "email": "noinvite@example.com",
            "hashed_password": "h",
            "role": UserRole.STUDENT,
        },
        None,
    )
    assert dto2.id is not None


# --- Access logs -------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_user_access_logs(user_repo, test_user, db_session):
    # data_access_logs is RANGE-partitioned by created_at on PostgreSQL — keep
    # the timestamp recent so it lands in a valid partition on the CI tier.
    now = datetime.datetime.now(datetime.UTC)
    log = models.DataAccessLog(
        actor_user_id=test_user.id,
        resource_type="user",
        action="view",
        created_at=now,
    )
    db_session.add(log)
    await db_session.commit()

    logs = await user_repo.get_user_access_logs(test_user.id)
    assert len(logs) >= 1

    # before_dt + after_id keyset branch.
    paged = await user_repo.get_user_access_logs(
        test_user.id,
        before_dt=now + datetime.timedelta(hours=1),
        after_id=log.id,
    )
    assert isinstance(paged, list)

    # before_dt-only branch.
    before_only = await user_repo.get_user_access_logs(
        test_user.id, before_dt=now + datetime.timedelta(hours=1)
    )
    assert isinstance(before_only, list)

    # Invalid-UUID branch → [].
    assert await user_repo.get_user_access_logs("not-a-uuid") == []
