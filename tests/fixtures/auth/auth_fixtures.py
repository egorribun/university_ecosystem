import uuid
from collections.abc import Awaitable, Callable

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

import app.models as models
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

        # Default profile mapping
        profile_data = {"full_name": "Test User"}
        pref_data = {}

        profile_keys = {
            "full_name",
            "avatar_url",
            "cover_url",
            "about",
            "telegram",
            "profile_status",
            "status",
            "achievements",
            "position",
            "department",
        }
        pref_keys = {"timezone", "dnd_enabled", "dnd_start", "dnd_end"}

        for k, v in list(kwargs.items()):
            if k in profile_keys:
                if k == "profile_status":
                    profile_data["status"] = kwargs.pop(k)
                elif k == "profile_department":
                    profile_data["department"] = kwargs.pop(k)
                else:
                    profile_data[k] = kwargs.pop(k)
            elif k in pref_keys:
                pref_data[k] = kwargs.pop(k)

        defaults.update(kwargs)
        defaults["_allow_system_managed_assignment"] = True
        user = models.User(**defaults)

        user.profile = models.UserProfile(**profile_data)
        if pref_data:
            user.preferences = models.UserPreferences(**pref_data)
        db_session.add(user)
        if not user.spotify:
            user.spotify = models.SpotifyIntegration()
        await db_session.commit()
        from app.models.user_loaders import USER_AUTH_LOAD_OPTIONS

        fetched_user = await db_session.get(
            models.User, user.id, options=USER_AUTH_LOAD_OPTIONS, populate_existing=True
        )
        assert fetched_user is not None
        user = fetched_user
        await ensure_mfa_relationships_loaded(db_session, user)
        await db_session.commit()
        return user

    return _factory


@pytest_asyncio.fixture
async def test_user(user_factory: Callable[..., Awaitable[models.User]]) -> models.User:
    return await user_factory(role="student")


@pytest_asyncio.fixture
async def admin_user(
    user_factory: Callable[..., Awaitable[models.User]],
) -> models.User:
    return await user_factory(role="admin")


@pytest.fixture
def auth_headers():
    def _headers(token: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {token}"}

    return _headers


async def create_access_token(
    sub: str, db: AsyncSession, expires_delta_minutes: int = 30
) -> tuple[str, models.ActiveSession]:
    """
    Test helper to create a full session and JWT.
    Used by tests that need a valid session in DB to pass get_current_user.
    """
    from datetime import UTC, datetime, timedelta
    from uuid import uuid4

    from app.auth.security import _mint_pure_jwt

    user_id = sub
    now = datetime.now(UTC)
    expires_at = now + timedelta(minutes=expires_delta_minutes)
    jti = str(uuid4())

    session = models.ActiveSession(
        user_id=uuid.UUID(user_id),
        jti=jti,
        expires_at=expires_at,
        created_at=now,
        last_seen_at=now,
        ip_address="127.0.0.1",
        user_agent="pytest",
        mfa_verified_at=now,  # assume verified for tests
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)

    token = _mint_pure_jwt(
        subject=user_id,
        expires_minutes=expires_delta_minutes,
        extra_claims={"jti": jti},
    )
    return token, session
