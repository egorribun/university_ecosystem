from __future__ import annotations

from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload

from .models import User

USER_MFA_RELATIONSHIP_NAMES: tuple[str, ...] = (
    "totp_enrollments",
    "mfa_challenges",
    "webauthn_credentials",
    "preferences",
    "spotify",
    "email_change_tokens",
    "profile_detail",
    "education_path",
)

USER_MFA_LOAD_OPTIONS: tuple = (
    selectinload(User.totp_enrollments),
    selectinload(User.mfa_challenges),
    selectinload(User.webauthn_credentials),
    selectinload(User.email_change_tokens),
    joinedload(User.preferences),
    joinedload(User.spotify),
    joinedload(User.profile_detail),
    joinedload(User.education_path),
)


async def ensure_mfa_relationships_loaded(
    db: AsyncSession, user: User | None
) -> User | None:
    """Ensure MFA-related relationships are loaded on the given user instance."""

    if user is None:
        return None

    state = inspect(user)
    if state is None:
        return user

    to_refresh = [
        name for name in USER_MFA_RELATIONSHIP_NAMES if name in state.unloaded
    ]
    if to_refresh:
        await db.refresh(user, attribute_names=to_refresh)
    return user
