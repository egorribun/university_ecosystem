import datetime

import pytest
from sqlalchemy import select

from app.models import models
from app.models.enums import UserRole
from app.repositories.user_repository import UserRepository


# Helpers
@pytest.fixture
async def user_repo(db_session):
    return UserRepository(db_session)


@pytest.fixture
async def test_user(db_session):
    user = models.User(
        email="test_repo@example.com",
        full_name="Test Repo User",
        hashed_password="hashed_password",
        is_active=True,
        role=UserRole.STUDENT,
        status="active",
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
async def test_get_by_login_found(user_repo, test_user):
    # Should work with email
    user = await user_repo.get_by_login(test_user.email)
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
    # Filter by name
    users = await user_repo.list_users(full_name="Repo User")
    assert len(users) >= 1
    assert any(u.id == test_user.id for u in users)

    # Filter by role
    users_role = await user_repo.list_users(role=UserRole.STUDENT.value)
    assert len(users_role) >= 1

    users_none = await user_repo.list_users(role="admin_impossible")
    assert not any(u.id == test_user.id for u in users_none)


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
        jti="test_jti",
        expires_at=datetime.datetime.now(datetime.UTC) + datetime.timedelta(hours=1),
    )
    db_session.add(session)
    await db_session.commit()

    result = await db_session.execute(
        select(models.ActiveSession).where(models.ActiveSession.user_id == test_user.id)
    )
    assert result.scalars().first() is not None

    await user_repo.delete_sensitive_data(test_user.id)

    result = await db_session.execute(
        select(models.ActiveSession).where(models.ActiveSession.user_id == test_user.id)
    )
    assert result.scalars().first() is None
