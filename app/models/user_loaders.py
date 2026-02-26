from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import inspect
from sqlalchemy.orm import joinedload, selectinload

from .models import User

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.schemas.dtos import UserDTO

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
    db: AsyncSession, user: User | UserDTO | None
) -> User | UserDTO | None:
    """Ensure MFA-related relationships are loaded on the given user instance.

    PERF-4: Idempotent — sets ``_mfa_loaded = True`` after the first successful
    refresh so subsequent calls (e.g. from both deps.py and auth_service.py in
    the same request) bypass the SQLAlchemy inspect overhead entirely.
    """

    if user is None:
        return None

    # Short-circuit if we have already loaded relationships in this request.
    # User.__allow_unmapped__ = True permits the extra attribute on ORM instances;
    # for DTO objects (Pydantic) we also set it since model_config allows extras
    # or we use object.__setattr__ to avoid validation.
    if getattr(user, "_mfa_loaded", False):
        return user

    try:
        state = inspect(user)
    except Exception:
        # Not a SQLAlchemy model (e.g. DTO), just return as-is
        return user

    if state is None:
        return user

    to_refresh = [
        name for name in USER_MFA_RELATIONSHIP_NAMES if name in state.unloaded
    ]
    if to_refresh:
        await db.refresh(user, attribute_names=to_refresh)

    # Mark as loaded to avoid redundant inspect() calls on subsequent invocations.
    try:
        object.__setattr__(user, "_mfa_loaded", True)
    except (TypeError, AttributeError):
        pass  # DTO with frozen config — skip silently, overhead is minimal

    return user
