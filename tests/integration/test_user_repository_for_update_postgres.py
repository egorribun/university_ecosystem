"""PostgreSQL contract for locking a user with optional joined relationships."""

from __future__ import annotations

import pytest
from sqlalchemy import text, update
from sqlalchemy.exc import DBAPIError

import app.core.database as database
from app.models import UserProfile
from app.repositories.user_repository import UserRepository

pytestmark = pytest.mark.integration


def _require_postgres() -> None:
    if database.engine.dialect.name != "postgresql":
        pytest.skip("user row-lock regression requires PostgreSQL")


async def test_get_with_for_update_locks_user_and_loads_optional_relations(
    user_factory,
) -> None:
    _require_postgres()
    user = await user_factory()

    async with database.async_session() as session:
        locked_user = await UserRepository(session).get(user.id, with_for_update=True)
        assert locked_user is not None
        assert locked_user.id == user.id
        assert locked_user.full_name == "Test User"
        assert locked_user.preferences is None

        async with database.async_session() as competing_session:
            profile_update = await competing_session.execute(
                update(UserProfile)
                .where(UserProfile.user_id == user.id)
                .values(full_name="Updated while account is locked")
            )
            assert profile_update.rowcount == 1
            await competing_session.commit()

            await competing_session.execute(text("SET LOCAL lock_timeout = '250ms'"))
            with pytest.raises(DBAPIError) as blocked:
                await UserRepository(competing_session).get(
                    user.id, with_for_update=True
                )
            assert getattr(blocked.value.orig, "sqlstate", None) == "55P03"
