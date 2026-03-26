import datetime

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
