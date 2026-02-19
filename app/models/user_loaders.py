from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import inspect
from sqlalchemy.orm import joinedload, selectinload

from .models import User

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

USER_MFA_RELATIONSHIP_NAMES: tuple[str, ...] = (
    "totp_enrollments",
    "mfa_challenges",
    "webauthn_credentials",
    "preferences",
    "spotify",
    "email_change_tokens",
    "profile",
    "education_path",
    "recovery_codes",
)

USER_MFA_LOAD_OPTIONS: tuple = (
    selectinload(User.totp_enrollments),
    selectinload(User.mfa_challenges),
    selectinload(User.webauthn_credentials),
    selectinload(User.email_change_tokens),
    selectinload(User.recovery_codes),
    joinedload(User.preferences),
    joinedload(User.spotify),
    joinedload(User.profile),
    joinedload(User.education_path),
)

# [NEW] Lightweight options for EVERY request (Auth only)
# We use joinedload for 1-to-1 relationships to avoid N+1 'selectin' queries
# caused by model-level defaults.
# We intentionally DO NOT load MFA collections (totp, challenges, etc.) here.
USER_AUTH_LOAD_OPTIONS: tuple = (
    joinedload(User.preferences),
    joinedload(User.spotify),
    joinedload(User.profile),
    joinedload(User.education_path),
)

# [NEW] Minimal options for list views (Admin Dashboard, Search)
# We only load the profile (for full_name) and potentially the group.
# Preferences, Education Path, Spotify, and all MFA data are omitted.
USER_LIST_LOAD_OPTIONS: tuple = (joinedload(User.profile),)


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
