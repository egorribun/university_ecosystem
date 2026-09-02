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

    Authorization checks intentionally revalidate ``lazy="noload"``
    relationships on every call.  The historical ``_mfa_loaded`` shortcut can
    become stale when factors are enrolled or revoked while the ORM identity
    remains alive.
    """

    if user is None:
        return None

    try:
        state = inspect(user)
    except Exception:  # RZ-22-01-JUSTIFIED: optional dependency — inspect() fails for non-ORM objects (reviewed TD-27-04)
        # Not a SQLAlchemy model (e.g. DTO), just return as-is
        return user

    if state is None:
        return user

    mapper = getattr(state, "mapper", None)
    relationships = getattr(mapper, "relationships", None)

    def _uses_noload(name: str) -> bool:
        if relationships is None:
            return False
        relationship = relationships.get(name)
        return relationship is not None and relationship.lazy == "noload"

    # SQLAlchemy's ``noload`` strategy materializes an empty collection and does
    # not keep the attribute in ``state.unloaded``.  Sensitive MFA checks must
    # therefore refresh noload relationships explicitly; otherwise a confirmed
    # factor is indistinguishable from no factor and step-up authorization can
    # be bypassed.  Do not trust the historical ``_mfa_loaded`` marker here:
    # factor enrollment/revocation can mutate the database while the same ORM
    # identity remains alive, making that marker stale at the authorization
    # boundary.
    to_refresh = [
        name
        for name in USER_MFA_RELATIONSHIP_NAMES
        if name in state.unloaded or _uses_noload(name)
    ]
    if to_refresh:
        await db.refresh(user, attribute_names=to_refresh)

    # Preserve the marker for compatibility with callers that expose diagnostic
    # state.  It is deliberately not trusted as an authorization cache.
    try:
        object.__setattr__(user, "_mfa_loaded", True)
    except (TypeError, AttributeError):  # RZ-28-01
        pass  # DTO with frozen config — skip silently, overhead is minimal

    return user
