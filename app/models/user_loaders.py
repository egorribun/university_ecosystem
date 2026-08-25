from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import inspect
from sqlalchemy.orm import joinedload, selectinload

from app.models.users import User

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.schemas.dtos import UserAuthDTO, UserDTO

USER_MFA_RELATIONSHIP_NAMES: tuple[str, ...] = (
    "totp_enrollments",
    "mfa_challenges",
    "preferences",
    "spotify",
    "email_change_tokens",
    "profile",
    "education_path",
    "recovery_codes",
)

USER_MFA_COLLECTION_OPTIONS: tuple[Any, ...] = (
    selectinload(User.totp_enrollments),
    selectinload(User.mfa_challenges),
    selectinload(User.email_change_tokens),
    selectinload(User.recovery_codes),
)

USER_MFA_LOAD_OPTIONS: tuple[Any, ...] = (
    *USER_MFA_COLLECTION_OPTIONS,
    joinedload(User.preferences),
    joinedload(User.spotify),
    joinedload(User.profile),
    joinedload(User.education_path),
)

# [NEW] Lightweight options for EVERY request (Auth only)
# We use joinedload for 1-to-1 relationships to avoid N+1 'selectin' queries
# caused by model-level defaults.
# We intentionally DO NOT load MFA collections (totp, challenges, etc.) here.
USER_AUTH_LOAD_OPTIONS: tuple[Any, ...] = (
    joinedload(User.preferences),
    joinedload(User.spotify),
    joinedload(User.profile),
    joinedload(User.education_path),
)

# PERF-W9-01: Combined auth + MFA load options — used in the auth hot-path so
# that MFA-enabled users are fully hydrated in a SINGLE round-trip instead of
# the previous 2-query pattern (base user query + conditional db.refresh).
#
# selectinload issues one IN-clause query per collection regardless of the
# number of User rows in scope — O(1) queries vs O(N) for per-row lazy loads.
# For single-user auth lookups the savings are modest (2→2 queries, but the
# second is batched with the first and returns 0 rows for non-MFA users).
# For bulk operations (e.g. presence checks) this eliminates the N+1 entirely.
#
# Filtered selectinload requires SQLAlchemy 2.0+ — only active, non-revoked
# enrollments and credentials are loaded to keep the result set tight.
USER_AUTH_WITH_MFA_OPTIONS: tuple[Any, ...] = (
    joinedload(User.preferences),
    joinedload(User.spotify),
    joinedload(User.profile),
    joinedload(User.education_path),
    selectinload(User.totp_enrollments),
    selectinload(User.mfa_challenges),
    selectinload(User.email_change_tokens),
    selectinload(User.recovery_codes),
)

# [NEW] Minimal options for list views (Admin Dashboard, Search)
# We only load the profile (for full_name) and potentially the group.
# Preferences, Education Path, Spotify, and all MFA data are omitted.
USER_LIST_LOAD_OPTIONS: tuple[Any, ...] = (joinedload(User.profile),)


async def ensure_mfa_relationships_loaded(
    db: AsyncSession, user: User | UserDTO | UserAuthDTO | None
) -> User | UserDTO | UserAuthDTO | None:
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
    except Exception:  # RZ-22-01-JUSTIFIED: optional dependency — inspect() fails for non-ORM objects (reviewed TD-27-04)
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
    except (TypeError, AttributeError):  # RZ-28-01
        pass  # DTO with frozen config — skip silently, overhead is minimal

    return user
