from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from .models import User

USER_MFA_RELATIONSHIP_NAMES: tuple[str, ...] = (
    "totp_enrollments",
    "mfa_challenges",
)

USER_MFA_LOAD_OPTIONS: tuple = (
    selectinload(User.totp_enrollments),
    selectinload(User.mfa_challenges),
)


async def ensure_mfa_relationships_loaded(
    db: AsyncSession, user: User | None
) -> User | None:
    """Ensure MFA-related relationships are loaded on the given user instance."""

    if user is None:
        return None
    await db.refresh(user, attribute_names=list(USER_MFA_RELATIONSHIP_NAMES))
    return user
