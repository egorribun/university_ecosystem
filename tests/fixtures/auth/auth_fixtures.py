import uuid
from collections.abc import Awaitable, Callable

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import models
from app.models.user_loaders import ensure_mfa_relationships_loaded


@pytest_asyncio.fixture
async def user_factory(
    db_session: AsyncSession,
) -> Callable[..., Awaitable[models.User]]:
    async def _factory(**kwargs) -> models.User:
        defaults = {
            "email": f"user-{uuid.uuid4().hex[:8]}@example.com",
            "hashed_password": "hashed-password",
            "role": "student",
            "is_active": True,
        }
        defaults.update(kwargs)
        user = models.User(**defaults)
        db_session.add(user)
        if not user.spotify:
            user.spotify = models.SpotifyIntegration()
        await db_session.commit()
        from app.models.user_loaders import USER_AUTH_LOAD_OPTIONS

        user = await db_session.get(
            models.User, user.id, options=USER_AUTH_LOAD_OPTIONS, populate_existing=True
        )
        await ensure_mfa_relationships_loaded(db_session, user)
        return user

    return _factory


@pytest_asyncio.fixture
async def test_user(user_factory) -> models.User:
    return await user_factory(role="student")


@pytest_asyncio.fixture
async def admin_user(user_factory) -> models.User:
    return await user_factory(role="admin")


@pytest.fixture
def auth_headers():
    def _headers(token: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {token}"}

    return _headers
