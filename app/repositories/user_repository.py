"""
User repository for user data access operations.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import delete, exists, func, or_, select
from sqlalchemy.orm import contains_eager, joinedload, selectinload

import app.models as models
from app.core.protocols import AsyncDatabaseSession
from app.models import User, UserProfile
from app.models.user_loaders import (
    USER_AUTH_WITH_MFA_OPTIONS,
    USER_MFA_COLLECTION_OPTIONS,
    USER_MFA_LOAD_OPTIONS,
    USER_MFA_RELATIONSHIP_NAMES,
)
from app.repositories.base import BaseRepository
from app.schemas import schemas
from app.schemas.dtos import UserAuthDTO, UserDTO

if TYPE_CHECKING:
    from app.core.protocols import AsyncDatabaseSession


class UserRepository(BaseRepository[User, UserDTO, schemas.UserCreate, dict[str, Any]]):
    """Repository for User model operations."""

    @property
    def model(self) -> type[User]:
        return User

    # Removed redundant __init__ override to use BaseRepository.db.

    @property
    def dto_class(self) -> type[UserDTO]:
        return UserDTO

    async def get(
        self, id: uuid.UUID | str, *, with_for_update: bool = False
    ) -> UserDTO | None:
        """Get user by ID, eagerly loading MFA collections in a single round-trip.

        PERF-W9-01: Replaced the 2-query pattern (base user + conditional
        db.refresh for MFA users) with USER_AUTH_WITH_MFA_OPTIONS which issues
        one selectinload query per MFA collection type.  For non-MFA users these
        queries return 0 rows immediately; for MFA users the collections arrive
        in the same database round-trip as the base user.
        """
        if isinstance(id, str):
            try:
                id = uuid.UUID(id)
            except ValueError:
                return None

        stmt = select(User).where(User.id == id).options(*USER_AUTH_WITH_MFA_OPTIONS)
        if with_for_update:
            stmt = stmt.with_for_update()

        result = await self.db.execute(stmt)
        obj = result.scalars().first()
        return self._to_dto(obj) if obj else None

    async def get_by_email(self, email: str) -> UserDTO | None:
        """Get user by email (case-insensitive), eagerly loading MFA collections.

        PERF-W9-01: See get() for rationale.
        """
        normalized = email.strip().lower()
        result = await self.db.execute(
            select(User)
            .where(func.lower(User.email) == normalized)
            .options(*USER_AUTH_WITH_MFA_OPTIONS)
        )
        obj = result.scalars().first()
        return self._to_dto(obj) if obj else None

    async def get_auth_by_email(self, email: str) -> UserAuthDTO | None:
        """Get user authentication data by email, eagerly loading MFA collections.

        PERF-W9-01: See get() for rationale.
        """
        normalized = email.strip().lower()
        result = await self.db.execute(
            select(User)
            .where(func.lower(User.email) == normalized)
            .options(*USER_AUTH_WITH_MFA_OPTIONS)
        )
        obj = result.scalars().first()
        return UserAuthDTO.model_validate(obj) if obj else None

    async def get_auth_by_id(self, id: uuid.UUID | str) -> UserAuthDTO | None:
        """Get user authentication data by ID, eagerly loading MFA collections.

        PERF-W9-01: See get() for rationale.
        """
        if isinstance(id, str):
            try:
                id = uuid.UUID(id)
            except ValueError:
                return None

        stmt = select(User).where(User.id == id).options(*USER_AUTH_WITH_MFA_OPTIONS)
        result = await self.db.execute(stmt)
        obj = result.scalars().first()
        return UserAuthDTO.model_validate(obj) if obj else None

    async def get_by_email_only(self, login: str) -> UserDTO | None:
        """Find user by email address (case-insensitive).

        TD-002 (audit 2026-03-10): Renamed from ``get_by_login`` and the dead
        ``or_()`` wrapper removed. The previous docstring claimed to search by
        "email or username/login" but the or_() had only one branch (email),
        making the promise a lie. Until a username field is added to the User
        model, this method correctly documents its single search key.
        """
        stmt = (
            select(User)
            .where(func.lower(User.email) == login.strip().lower())
            .options(*USER_MFA_LOAD_OPTIONS)
        )
        result = await self.db.execute(stmt)
        obj = result.scalar_one_or_none()
        return self._to_dto(obj) if obj else None

    async def get_by_email_or_raise(self, email: str) -> UserDTO:
        """Get user by email or raise ValueError.

        TD-010 (audit 2026-03-04): email address removed from the error message
        to prevent PII propagation into logs, error trackers, and API responses.
        """
        user = await self.get_by_email(email)
        if user is None:
            raise ValueError("User not found")
        return user

    async def get_with_full_profile(self, user_id: uuid.UUID | str) -> UserDTO | None:
        """Fetch a user with profile, preferences, and education_path in ONE query.

        Use this instead of :meth:`get` when all three delegated sub-objects are
        needed (e.g. /users/me, profile edit page).  A single LEFT OUTER JOIN
        replaces the three consecutive selectin round-trips that the lazy
        ``selectin`` relationship strategy would otherwise issue.
        """
        if isinstance(user_id, str):
            try:
                user_id = uuid.UUID(user_id)
            except ValueError:
                return None
        stmt = (
            select(User)
            .where(User.id == user_id)
            .options(
                joinedload(User.profile),
                joinedload(User.preferences),
                joinedload(User.education_path),
                *USER_MFA_LOAD_OPTIONS,
            )
        )
        result = await self.db.execute(stmt)
        obj = result.unique().scalars().first()
        return self._to_dto(obj) if obj else None

    async def list_users(
        self,
        filters: schemas.UserSearchFilter | None = None,
    ) -> list[UserDTO]:
        filters = filters or schemas.UserSearchFilter()

        # PERF-001 (audit 2026-03-10): Replaced User.profile.has(...) correlated
        # subquery with an explicit INNER JOIN. SQLAlchemy's .has() generates an
        # EXISTS (SELECT 1 FROM user_profile WHERE ...) subquery evaluated per-row —
        # effectively an N+1 query pattern. The JOIN + contains_eager resolves the
        # filter in a single pass and tells SQLAlchemy the relationship is already
        # loaded so it does not issue a second round-trip.
        #
        # RZ-14-02 (audit 2026-03-23): Changed INNER JOIN → LEFT OUTER JOIN.
        # The previous INNER JOIN silently excluded users whose UserProfile row has
        # not been created yet (e.g. newly registered accounts before the profile
        # creation event fires).  LEFT OUTER JOIN + NULL guard preserves the
        # "no deleted profiles" filter while including profile-less users.
        stmt = (
            select(User)
            .outerjoin(User.profile)
            .where(
                or_(
                    UserProfile.user_id.is_(None),  # no profile yet — still include
                    UserProfile.status != "deleted",
                )
            )
            .options(
                # PERF-001 (audit 2026-03-10): contains_eager() tells SQLAlchemy
                # that User.profile is already loaded via the explicit JOIN above.
                # USER_LIST_LOAD_OPTIONS is intentionally excluded — it contains
                # joinedload(User.profile) which conflicts with contains_eager on
                # the same ORM path (raises InvalidRequestError). The JOIN already
                # replaces the joinedload with zero extra round-trips.
                contains_eager(User.profile),
                selectinload(User.group),
            )
        )
        if filters.group_id:
            stmt = stmt.where(User.group_id == filters.group_id)
        if filters.full_name:
            # CRIT-01 (audit 2026-03-11): Escape wildcards before embedding in LIKE.
            # Unescaped % or _ turns this into a full-table scan (DoS) or allows
            # single-char brute-force enumeration of column values.
            # Profile is already joined above — filter directly on UserProfile column.
            safe_name = self._escape_like(filters.full_name)
            stmt = stmt.where(
                UserProfile.full_name.ilike(f"%{safe_name}%", escape="\\")
            )
        if filters.role:
            stmt = stmt.where(User.role == filters.role)

        # RZ-07 (audit 2026-03-04): Defense-in-depth cap — the schema already
        # validates limit ≤ 200, but internal callers may bypass schema validation.
        _MAX_PAGE_SIZE = 200
        capped_limit = min(filters.limit, _MAX_PAGE_SIZE)

        # Strictly enforce cursor-based pagination to prevent O(N) sequential scans
        after_id_val = filters.after_id or uuid.UUID(int=0)
        stmt = stmt.where(User.id > after_id_val).order_by(User.id).limit(capped_limit)

        result = await self.db.execute(stmt)
        # unique() is required after contains_eager to deduplicate rows produced
        # by the JOIN (a user with multiple profile associations would appear twice).
        objs = result.unique().scalars().all()
        return [self._to_dto(obj) for obj in objs]

    async def get_active_users(
        self, *, skip: int = 0, limit: int = 100
    ) -> list[UserDTO]:
        """Get only active users."""
        result = await self.db.execute(
            select(User)
            .where(User.is_active.is_(True))
            .offset(skip)
            .limit(limit)
            .options(*USER_MFA_LOAD_OPTIONS)
        )
        objs = result.scalars().all()
        return [self._to_dto(obj) for obj in objs]

    async def count_active(self) -> int:
        """Count active users."""
        result = await self.db.execute(
            select(func.count(User.id)).where(User.is_active.is_(True))
        )
        return result.scalar() or 0

    async def count_with_mfa(self) -> int:
        """Count users with MFA enabled."""
        result = await self.db.execute(
            select(func.count(User.id)).where(User.mfa_required.is_(True))
        )
        return result.scalar() or 0

    async def search_by_name(
        self, query: str, *, skip: int = 0, limit: int = 20
    ) -> list[UserDTO]:
        """Search users by name (case-insensitive)."""
        # CRIT-01 (audit 2026-03-11): Escape LIKE wildcards before embedding.
        safe_query = self._escape_like(query.strip().lower())
        pattern = f"%{safe_query}%"
        result = await self.db.execute(
            select(User)
            .join(User.profile)
            .where(func.lower(UserProfile.full_name).like(pattern, escape="\\"))
            .where(User.is_active.is_(True))
            .offset(skip)
            .limit(limit)
            .options(contains_eager(User.profile), *USER_MFA_COLLECTION_OPTIONS)
        )
        objs = result.unique().scalars().all()
        return [self._to_dto(obj) for obj in objs]

    async def get_user_sessions(
        self, user_id: uuid.UUID | str, limit: int = 50
    ) -> list[models.ActiveSession]:
        """Get user sessions with limit."""
        if isinstance(user_id, str):
            try:
                user_id = uuid.UUID(user_id)
            except ValueError:
                return []

        stmt = (
            select(models.ActiveSession)
            .where(models.ActiveSession.user_id == user_id)
            .where(
                models.ActiveSession.revoked_at.is_(None)
            )  # MED-W19: exclude revoked sessions
            .limit(limit)
            .order_by(models.ActiveSession.created_at.desc())
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    # RZ-12 (audit 2026-03-05): Hard-cap at 100. The old default of 1000 could
    # return multi-MB payloads bypassing the router-level MAX_PAGE_SIZE=200.
    _NOTIFICATIONS_MAX_LIMIT: int = 100

    async def get_user_notifications(
        self, user_id: uuid.UUID | str, limit: int = 100
    ) -> list[models.Notification]:
        """Get user notifications with limit."""
        if isinstance(user_id, str):
            try:
                user_id = uuid.UUID(user_id)
            except ValueError:
                return []

        capped = min(limit, self._NOTIFICATIONS_MAX_LIMIT)
        stmt = (
            select(models.Notification)
            .where(models.Notification.user_id == user_id)
            .limit(capped)
            .order_by(models.Notification.created_at.desc())
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    # RZ-12 (audit 2026-03-05): Hard-cap at 50 — MFA challenges are short-lived
    # objects; returning 1000 at once is never a valid business requirement.
    _MFA_CHALLENGES_MAX_LIMIT: int = 50

    async def get_user_mfa_challenges(
        self, user_id: uuid.UUID | str, limit: int = 50
    ) -> list[models.MfaChallenge]:
        """Get user MFA challenges."""
        if isinstance(user_id, str):
            try:
                user_id = uuid.UUID(user_id)
            except ValueError:
                return []

        capped = min(limit, self._MFA_CHALLENGES_MAX_LIMIT)
        stmt = (
            select(models.MfaChallenge)
            .where(models.MfaChallenge.user_id == user_id)
            .limit(capped)
            .order_by(models.MfaChallenge.created_at.desc())
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_user_totp_enrollments(
        self, user_id: uuid.UUID | str
    ) -> list[models.MfaTotpEnrollment]:
        """Get user TOTP enrollments."""
        if isinstance(user_id, str):
            try:
                user_id = uuid.UUID(user_id)
            except ValueError:
                return []

        stmt = (
            select(models.MfaTotpEnrollment)
            .where(models.MfaTotpEnrollment.user_id == user_id)
            .order_by(models.MfaTotpEnrollment.created_at.desc())
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def check_email_exists(
        self, email: str, exclude_user_id: uuid.UUID | str | None = None
    ) -> bool:
        # RZ-W19-13: build the EXISTS subquery with both conditions INSIDE the exists()
        # Previously, exclude_user_id filter was applied to the outer SELECT (silently dropped)
        conditions = [func.lower(User.email) == email.lower()]
        if exclude_user_id:
            if isinstance(exclude_user_id, str):
                try:
                    exclude_user_id = uuid.UUID(exclude_user_id)
                except ValueError:
                    return False
            conditions.append(User.id != exclude_user_id)
        stmt = select(exists().where(*conditions))
        result = await self.db.execute(stmt)
        return bool(result.scalar())

    async def get_invite_code(
        self, code: str, *, with_for_update: bool = True
    ) -> models.InviteCode | None:
        """Get invite code by value.

        AUDIT-BE-03 (audit 2026-03-15): Uses SELECT FOR UPDATE without skip_locked.
        SKIP LOCKED is correct for job-queue patterns where any worker can claim
        any item. For invite codes — a single-owner resource — it causes a TOCTOU
        race: a second concurrent transaction *skips* the locked row, receives None,
        and proceeds as if the code is absent, allowing duplicate registration.

        FOR UPDATE (without skip_locked) serialises concurrent registrations at the
        row level. The second caller blocks, then reads is_used=True and correctly
        fails. This mirrors the pattern in auth_repository.create_email_change_token.
        See PostgreSQL 17 §13.3.4 "Table-Level Locks".
        """
        stmt = select(models.InviteCode).where(models.InviteCode.code == code)
        if with_for_update:
            stmt = stmt.with_for_update(
                skip_locked=False, nowait=True
            )  # no skip_locked — serialize, not skip
        result = await self.db.execute(stmt)
        return result.scalars().first()

    # PERF-02 (audit 2026-03-11): Hoist field-set literals to class-level frozensets.
    # Recreating 3 plain sets on every _extract_cqrs_data() call (called for every
    # user update) allocates 3 objects needlessly @ high write throughput.
    _PROFILE_KEYS: frozenset[str] = frozenset(
        {
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
            "profile_department",
        }
    )
    _PREF_KEYS: frozenset[str] = frozenset(
        {"timezone", "dnd_enabled", "dnd_start", "dnd_end"}
    )
    _EDU_KEYS: frozenset[str] = frozenset(
        {
            "institute",
            "course",
            "education_level",
            "track",
            "program",
            "record_book_number",
        }
    )

    def _extract_cqrs_data(
        self, data: dict[str, Any]
    ) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
        """Extract profile, preferences, education_path, and core user data from a flat dictionary."""
        profile_keys = self._PROFILE_KEYS
        pref_keys = self._PREF_KEYS
        edu_keys = self._EDU_KEYS
        profile_data = {}
        pref_data = {}
        edu_data = {}
        core_data = {}

        for k, v in data.items():
            if k in profile_keys:
                if k == "profile_status":
                    profile_data["status"] = v
                elif k == "profile_department":
                    profile_data["department"] = v
                else:
                    profile_data[k] = v
            elif k in pref_keys:
                pref_data[k] = v
            elif k in edu_keys:
                edu_data[k] = v
            else:
                core_data[k] = v

        return core_data, profile_data, pref_data, edu_data

    def _build_user_aggregate(
        self,
        core_data: dict[str, Any],
        profile_data: dict[str, Any],
        pref_data: dict[str, Any],
        edu_data: dict[str, Any],
    ) -> models.User:
        """Construct a User ORM aggregate with all nested sub-objects.

        TD-004 (audit 2026-03-10): Extracted from the duplicate 14-line
        construction block that appeared verbatim in both ``create()`` and
        ``create_with_invite()``. A single change point for the aggregate
        structure ensures both code paths stay consistent.

        Always populates profile / preferences / education_path — even when
        no data is provided — so downstream code can safely access
        ``user.profile`` without a None-guard.
        """
        user = models.User(**core_data)
        user.profile = (
            models.UserProfile(**profile_data) if profile_data else models.UserProfile()
        )
        user.preferences = (
            models.UserPreferences(**pref_data)
            if pref_data
            else models.UserPreferences()
        )
        user.education_path = (
            models.EducationPath(**edu_data) if edu_data else models.EducationPath()
        )
        return user

    async def create(self, obj_in: schemas.UserCreate | dict[str, Any]) -> UserDTO:
        if hasattr(obj_in, "model_dump"):
            obj_data = obj_in.model_dump()
        else:
            obj_data = obj_in

        core_data, profile_data, pref_data, edu_data = self._extract_cqrs_data(obj_data)
        user = self._build_user_aggregate(core_data, profile_data, pref_data, edu_data)

        self.db.add(user)
        await self.db.flush()
        await self.db.refresh(user, attribute_names=USER_MFA_RELATIONSHIP_NAMES)
        return self._to_dto(user)

    async def update(
        self, id: uuid.UUID | str, obj_in: Any | dict[str, Any]
    ) -> UserDTO | None:
        db_obj = await self._get_orm(id)
        if db_obj is None:
            return None

        if hasattr(obj_in, "model_dump"):
            update_data = obj_in.model_dump(exclude_unset=True)
        else:
            update_data = obj_in

        core_data, profile_data, pref_data, edu_data = self._extract_cqrs_data(
            update_data
        )

        for field, value in core_data.items():
            setattr(db_obj, field, value)

        await self._upsert_child(db_obj, "profile", models.UserProfile, profile_data)
        await self._upsert_child(
            db_obj, "preferences", models.UserPreferences, pref_data
        )
        await self._upsert_child(
            db_obj, "education_path", models.EducationPath, edu_data
        )

        await self.db.flush()
        return self._to_dto(db_obj)

    async def _upsert_child(
        self,
        db_obj: User,
        rel_name: str,
        child_model: type[Any],
        data: dict[str, Any] | None,
    ) -> None:
        """INSERT-or-UPDATE a User child row (profile/preferences/education_path).

        The User -> child relationships are ``lazy="noload"`` (N+1 guard,
        MOD-30-01), so ``db_obj.<rel_name>`` reads ``None`` even when a row
        already exists. Trusting that attribute made ``update()`` always take
        the INSERT branch -> ``UNIQUE`` violation. We query the child table
        explicitly by ``user_id`` to decide INSERT-vs-UPDATE while keeping the
        read relationships ``noload``. Setting ``db_obj.<rel_name>`` on the
        update branch overrides the noload read so ``_to_dto`` sees the change.
        """
        if not data:
            return
        existing = (
            (
                await self.db.execute(
                    select(child_model).where(child_model.user_id == db_obj.id)
                )
            )
            .scalars()
            .first()
        )
        if existing is None:
            setattr(db_obj, rel_name, child_model(**data))
            return
        for field, value in data.items():
            setattr(existing, field, value)
        setattr(db_obj, rel_name, existing)

    async def create_with_invite(
        self, user_data: dict[str, Any], invite_code: models.InviteCode | None
    ) -> UserDTO:
        """Create a user and optionally mark an invite code as used."""
        core_data, profile_data, pref_data, edu_data = self._extract_cqrs_data(
            user_data
        )
        user = self._build_user_aggregate(core_data, profile_data, pref_data, edu_data)

        self.db.add(user)
        await self.db.flush()  # Get ID

        if invite_code:
            invite_code.is_used = True
            invite_code.is_active = False
            invite_code.used_by_user_id = user.id
            self.db.add(invite_code)

        await self.db.refresh(user, attribute_names=USER_MFA_RELATIONSHIP_NAMES)
        return self._to_dto(user)

    async def delete_sensitive_data(self, user_id: uuid.UUID | str) -> None:
        """Cleanup user-related transient records (sessions, challenges, etc)."""
        if isinstance(user_id, str):
            try:
                user_id = uuid.UUID(user_id)
            except ValueError:
                return

        await self.db.execute(
            delete(models.ActiveSession).where(models.ActiveSession.user_id == user_id)
        )
        await self.db.execute(
            delete(models.MfaChallenge).where(models.MfaChallenge.user_id == user_id)
        )
        await self.db.execute(
            delete(models.MfaTotpEnrollment).where(
                models.MfaTotpEnrollment.user_id == user_id
            )
        )
        await self.db.execute(
            delete(models.Notification).where(models.Notification.user_id == user_id)
        )
        await self.db.execute(
            delete(models.DataAccessLog).where(
                or_(
                    models.DataAccessLog.actor_user_id == user_id,
                    models.DataAccessLog.subject_user_id == user_id,
                )
            )
        )

    # RZ-12 (audit 2026-03-05): Hard-cap at 200. The old default of 2000 was an
    # OOM risk — a single GDPR export call could return multi-MB payloads.
    _ACCESS_LOGS_MAX_LIMIT: int = 200

    async def get_user_access_logs(
        self,
        user_id: uuid.UUID | str,
        limit: int = 200,
        before_dt: datetime | None = None,
        after_id: uuid.UUID | None = None,
    ) -> list[models.DataAccessLog]:
        """Get access logs where user is actor or subject."""
        if isinstance(user_id, str):
            try:
                user_id = uuid.UUID(user_id)
            except ValueError:
                return []

        condition = or_(
            models.DataAccessLog.actor_user_id == user_id,
            models.DataAccessLog.subject_user_id == user_id,
        )

        from sqlalchemy import and_

        if before_dt and after_id:
            condition = condition & or_(
                models.DataAccessLog.created_at < before_dt,
                and_(
                    models.DataAccessLog.created_at == before_dt,
                    models.DataAccessLog.id < after_id,
                ),
            )
        elif before_dt:
            condition = condition & (models.DataAccessLog.created_at < before_dt)

        capped = min(limit, self._ACCESS_LOGS_MAX_LIMIT)
        stmt = (
            select(models.DataAccessLog)
            .where(condition)
            .order_by(
                models.DataAccessLog.created_at.desc(), models.DataAccessLog.id.desc()
            )
            .limit(capped)
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())


def get_user_repository(db: AsyncDatabaseSession) -> UserRepository:
    """Factory function for dependency injection."""
    return UserRepository(db)


__all__ = ["UserRepository", "get_user_repository"]
