import json
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import Request, UploadFile
from sqlalchemy import and_, case, func, literal, select, true
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.api.utils import save_upload
from app.auth.security import get_password_hash
from app.core.exceptions.domain import (
    BusinessRuleViolation,
    EntityAlreadyExists,
    EntityNotFound,
    PermissionDenied,
)
from app.core.localization import resolve_locale, translate
from app.deps.cache import BaseCache
from app.models import models
from app.models.user_loaders import (
    ensure_mfa_relationships_loaded,
)
from app.repositories.user_repository import UserRepository
from app.schemas import schemas
from app.services import stats_cache
from app.services.audit_service import AuditService
from app.services.auth_service import attach_pending_email
from app.services.data_access import export_access_logs, log_data_access
from app.services.notification_service import NotificationService
from app.utils.files import delete_static_file

logger = logging.getLogger(__name__)


class UserService:
    def __init__(
        self,
        db: AsyncSession,
        repo: UserRepository,
        audit: AuditService,
        notifications: NotificationService,
    ) -> None:
        self.db = db
        self.repo = repo
        self.audit = audit
        self.notifications = notifications

    async def update_user_profile(
        self,
        user: models.User,
        data: schemas.UserProfileUpdate,
        request: Request,
    ) -> models.User:
        db_user = await self.repo.get(user.id)
        if not db_user:
            raise EntityNotFound("User", user.id)

        update_fields = data.model_dump(exclude_unset=True)

        if "email" in update_fields and update_fields["email"] is not None:
            validated_email = str(update_fields["email"]).strip().lower()
            if await self.repo.check_email_exists(
                validated_email, exclude_user_id=user.id
            ):
                raise EntityAlreadyExists("User", validated_email)
            update_fields["email"] = validated_email

        # ... (keeping complex mapping logic in service for now as it's business-heavy)
        preferences_fields = {"dnd_enabled", "dnd_start", "dnd_end", "timezone"}
        profile_fields = {
            "about",
            "telegram",
            "status",
            "achievements",
            "position",
            "department",
        }
        education_fields = {
            "institute",
            "course",
            "education_level",
            "track",
            "program",
            "record_book_number",
        }

        for field, value in update_fields.items():
            if field in preferences_fields:
                if not db_user.preferences:
                    db_user.preferences = models.UserPreferences(user_id=db_user.id)
                setattr(db_user.preferences, field, value)
            elif field in profile_fields:
                if not db_user.profile_detail:
                    db_user.profile_detail = models.UserProfileDetail(
                        user_id=db_user.id
                    )
                setattr(db_user.profile_detail, field, value)
            elif field in education_fields:
                if not db_user.education_path:
                    db_user.education_path = models.EducationPath(user_id=db_user.id)
                setattr(db_user.education_path, field, value)
            else:
                setattr(db_user, field, value)

        await self.db.commit()
        await self.db.refresh(db_user)
        await ensure_mfa_relationships_loaded(self.db, db_user)
        await attach_pending_email(self.db, db_user)
        return db_user

    async def get_users(
        self,
        request: Request,
        current_user: models.User,
        filters: schemas.UserSearchFilter | None = None,
    ) -> list[models.User]:
        filters = filters or schemas.UserSearchFilter()
        if (
            current_user.role != "admin"
            and not filters.search
            and not filters.full_name
        ):
            raise PermissionDenied()

        name_query = filters.search if filters.search else filters.full_name
        # We update filters with the name query for repository call
        filters.full_name = name_query
        return await self.repo.list_users(filters=filters)

    async def admin_update_user(
        self,
        user_id: int,
        data: schemas.UserAdminUpdate,
        request: Request,
        current_user: models.User,
    ) -> models.User:
        if current_user.role != "admin":
            raise PermissionDenied()

        db_user = await self.repo.get(user_id)
        if not db_user:
            raise EntityNotFound("User", user_id)

        payload = data.model_dump(exclude_unset=True)
        reset_requested = bool(payload.pop("reset_mfa", False))

        if "email" in payload and payload["email"] is not None:
            payload["email"] = str(payload["email"]).strip().lower()

        # Update fields logic matching crud
        preferences_fields = {"dnd_enabled", "dnd_start", "dnd_end", "timezone"}

        for field, value in payload.items():
            if field in preferences_fields:
                if not db_user.preferences:
                    db_user.preferences = models.UserPreferences(user_id=db_user.id)
                setattr(db_user.preferences, field, value)
            else:
                setattr(db_user, field, value)

        reset_stats = None
        if reset_requested:
            from app.auth import mfa

            reset_stats = await mfa.reset_user_mfa(self.db, user=db_user)

        await self.db.commit()
        await self.db.refresh(db_user)
        await ensure_mfa_relationships_loaded(self.db, db_user)

        updated_user = db_user

        self.audit.log(
            "users.admin_update",
            request,
            user_id=updated_user.id,
            reason="admin_update",
        )
        if reset_stats is not None:
            if reset_stats.changed:
                # Log MFA reset audit event
                self.audit.log(
                    "users.mfa.reset",
                    request,
                    user_id=updated_user.id,
                    reason="admin_reset",
                )
                target_locale = resolve_locale(request=request, user=updated_user)
                title = translate("notifications.mfa.reset.title", locale=target_locale)
                body = translate("notifications.mfa.reset.body", locale=target_locale)
                await self.notifications.send_security_notification(
                    user_ids=[updated_user.id],
                    title=title,
                    body=body,
                )
        return updated_user

    async def admin_delete_user(
        self,
        user_id: int,
        request: Request,
        current_user: models.User,
    ) -> dict:
        """Delete a user by admin (anonymize user data)."""

        if current_user.role != "admin":
            raise PermissionDenied()

        db_user = await self.repo.get(user_id)
        if db_user is None:
            raise EntityNotFound("User", user_id)

        # Prevent admin from deleting themselves
        if db_user.id == current_user.id:
            raise BusinessRuleViolation("errors.users.cannot_delete_self")

        anonymized_email = f"deleted+{db_user.id}@deleted.example.com"

        await delete_static_file(db_user.avatar_url) if db_user.avatar_url else None
        await delete_static_file(db_user.cover_url) if db_user.cover_url else None

        db_user.full_name = None
        db_user.email = anonymized_email
        db_user.avatar_url = None
        db_user.cover_url = None
        db_user.about = None
        db_user.telegram = None
        db_user.achievements = None
        db_user.record_book_number = None
        db_user.hashed_password = "deleted"
        db_user.is_active = False
        db_user.status = "deleted"
        db_user.mfa_required = False
        db_user.mfa_default_method = None
        db_user.mfa_last_verified_at = None

        await self.repo.delete_sensitive_data(user_id)

        db_user.preferences = None
        db_user.spotify = None

        self.audit.log(
            "users.admin_delete", request, user_id=user_id, reason="admin_delete"
        )

        await self.db.commit()
        return {"deleted": True, "user_id": user_id}

    async def delete_avatar(
        self,
        user: models.User,
    ) -> models.User:
        db_user = await self.repo.get(user.id)
        if db_user.avatar_url:
            await delete_static_file(db_user.avatar_url)
        db_user.avatar_url = None
        await self.db.commit()
        await self.db.refresh(db_user)
        await ensure_mfa_relationships_loaded(self.db, db_user)
        return db_user

    async def delete_cover(
        self,
        user: models.User,
    ) -> models.User:
        db_user = await self.repo.get(user.id)
        if db_user.cover_url:
            await delete_static_file(db_user.cover_url)
        db_user.cover_url = None
        await self.db.commit()
        await self.db.refresh(db_user)
        await ensure_mfa_relationships_loaded(self.db, db_user)
        return db_user

    async def export_user_data(
        self, user: models.User, request: Request
    ) -> schemas.DataExportOut:
        db_user = await self.repo.get(user.id)
        if not db_user:
            raise EntityNotFound("User", user.id)
        await ensure_mfa_relationships_loaded(self.db, db_user)
        await attach_pending_email(self.db, db_user)

        profile = schemas.UserOut.from_orm(db_user).model_dump()

        sessions_result = await self.db.execute(
            select(models.ActiveSession).where(models.ActiveSession.user_id == user.id)
        )
        sessions = [
            {
                "id": session.id,
                "created_at": session.created_at,
                "expires_at": session.expires_at,
                "revoked_at": session.revoked_at,
                "ip_address": session.ip_address,
                "user_agent": session.user_agent,
                "last_seen_at": session.last_seen_at,
                "mfa_completed_at": session.mfa_completed_at,
            }
            for session in sessions_result.scalars()
        ]

        notifications_result = await self.db.execute(
            select(models.Notification).where(models.Notification.user_id == user.id)
        )
        notifications = [
            {
                "id": item.id,
                "title": item.title,
                "body": item.body,
                "type": item.type,
                "created_at": item.created_at,
                "read_at": item.read_at,
            }
            for item in notifications_result.scalars()
        ]

        challenges = [
            {
                "id": challenge.id,
                "type": challenge.challenge_type,
                "expires_at": challenge.expires_at,
                "consumed_at": challenge.consumed_at,
                "created_at": challenge.created_at,
            }
            for challenge in db_user.mfa_challenges
        ]

        enrollments = [
            {
                "id": enrollment.id,
                "label": enrollment.label,
                "is_active": enrollment.is_active,
                "confirmed_at": enrollment.confirmed_at,
                "revoked_at": enrollment.revoked_at,
                "created_at": enrollment.created_at,
            }
            for enrollment in db_user.totp_enrollments
        ]

        access_logs = await export_access_logs(
            self.db,
            actor_user_id=user.id,
            subject_user_id=user.id,
            limit=2000,
        )
        access_log_payload = [
            {
                "resource_type": log.resource_type,
                "resource_id": log.resource_id,
                "action": log.action,
                "created_at": log.created_at,
                "ip_address": log.ip_address,
                "user_agent": log.user_agent,
                "context": log.context,
            }
            for log in access_logs
        ]

        self.audit.log("users.data_export", request, user_id=user.id)
        await log_data_access(
            self.db,
            actor_user_id=user.id,
            subject_user_id=user.id,
            resource_type="profile",
            resource_id=str(user.id),
            action="export",
            request=request,
        )

        return schemas.DataExportOut(
            profile=profile,
            sessions=sessions,
            notifications=notifications,
            mfa_challenges=challenges,
            mfa_enrollments=enrollments,
            access_logs=access_log_payload,
        )

    async def delete_user_data(
        self,
        user: models.User,
        request: Request,
        *,
        confirm: bool,
    ) -> schemas.DataDeletionOut:
        if not confirm:
            raise BusinessRuleViolation("errors.users.confirmation_required")

        db_user = await self.repo.get(user.id)
        if not db_user:
            raise EntityNotFound("User", user.id)
        anonymized_email = f"deleted+{user.id}@deleted.example.com"

        await delete_static_file(db_user.avatar_url) if db_user.avatar_url else None
        await delete_static_file(db_user.cover_url) if db_user.cover_url else None

        db_user.full_name = None
        db_user.email = anonymized_email
        db_user.avatar_url = None
        db_user.cover_url = None
        db_user.about = None
        db_user.telegram = None
        db_user.achievements = None
        db_user.record_book_number = None
        db_user.hashed_password = "deleted"
        db_user.is_active = False
        db_user.status = "deleted"
        db_user.mfa_required = False
        db_user.mfa_default_method = None
        db_user.mfa_last_verified_at = None

        await self.repo.delete_sensitive_data(user.id)

        db_user.preferences = None
        db_user.spotify = None

        self.audit.log("users.data_delete", request, user_id=user.id)
        await log_data_access(
            self.db,
            actor_user_id=user.id,
            subject_user_id=user.id,
            resource_type="profile",
            resource_id=str(user.id),
            action="delete",
            request=request,
        )

        await self.db.commit()
        await self.db.refresh(db_user)
        return schemas.DataDeletionOut(deleted=True, anonymized_email=anonymized_email)

    async def register_user(
        self,
        user_in: schemas.UserCreate,
    ) -> models.User:
        """Register a new user (public signup)."""
        raw_role = getattr(user_in, "role", None)
        # Import UserRole if not present or use string
        from app.core.config import settings
        from app.models.enums import UserRole

        requested_role = UserRole(raw_role) if raw_role else UserRole.STUDENT
        normalized_email = user_in.email.strip().lower()

        code = None
        if hasattr(user_in, "invite_code") and requested_role in (
            UserRole.TEACHER,
            UserRole.ADMIN,
        ):
            # We fetch the code and validate it manually to keep repo simple
            # or we could make a specific repo method `get_valid_invite_code`.
            # Let's use get_invite_code and validate.
            code_obj = await self.repo.get_invite_code(user_in.invite_code)
            if not code_obj:
                raise BusinessRuleViolation("errors.users.invalid_invite")

            # Validation logic from crud
            if (
                code_obj.role != requested_role.value
                or not code_obj.is_active
                or code_obj.is_used
            ):
                raise BusinessRuleViolation("errors.users.invalid_invite")
            code = code_obj

        if await self.repo.check_email_exists(normalized_email):
            raise EntityAlreadyExists("User", normalized_email)

        hashed_password = get_password_hash(user_in.password)

        # Mapping logic
        user_data = user_in.model_dump(
            exclude={"invite_code", "password", "spotify_connected"}
        )
        user_data["hashed_password"] = hashed_password
        user_data["role"] = requested_role.value
        user_data["email"] = normalized_email
        if "id" in user_data:
            del user_data["id"]

        # Default fields from crud
        user_data["mfa_required"] = settings.mfa_enabled
        user_data["mfa_default_method"] = settings.mfa_default_method

        # Handle nested fields if schema has them flat?
        # Crud used manual mapping.
        # Let's use repo.create for simplicity but we might need to handle
        # specific fields if schemas.UserCreate is flat but model is not.
        # schemas.UserCreate seems flat.
        # But crud logic (lines 80-102) maps many fields explicitly.
        # Most match, but some are nested in model (preferences, profile_detail)?
        # No, User model has these fields directly (department, position, etc.)
        # except where they were moved to mixins or separate tables?
        # Crud lines 86-99 seem to map attributes directly to User model.
        # So repo.create(**user_data) should work if user_data keys match User columns.

        # However, crud explicitly sets `mfa_required`.
        # And creates User object directly.
        # Let's use repo.create to be consistent with Repository pattern.
        # But we need to update the invite code transactionally.

        # We can do:
        # user = await self.repo.create(user_data) -> does commit
        # Then update code -> does commit
        # But ideally all in one transaction.
        # Repo.create does commit/refresh.

        # If we use repo.create, we can't wrap it easily in a larger tx
        # unless we modify repo to accept commit=False.
        # Or we use a Unit of Work.
        # For now, let's accept slight risk or modify repo to not auto-commit?
        # BaseRepository `create` calls `db.commit()`.

        # Let's assume we can live with separate commits for now
        # (User created, then Code marked used).
        # Worst case: User created, code not marked. User is valid, code reusable.
        # Risk: Code reusable.
        # Mitigation: Update code first? No, need user_id.

        # Solution: Use `self.db` directly here for transactionality?
        # Or use `repo.db`.

        # Let's do manuals:
        db_user = models.User(**user_data)
        self.db.add(db_user)
        try:
            await self.db.flush()  # to get ID
            if code:
                code.is_used = True
                code.is_active = False
                code.used_by_user_id = db_user.id
                self.db.add(code)

            await self.db.commit()
            await self.db.refresh(db_user)
        except Exception:
            await self.db.rollback()
            raise BusinessRuleViolation("errors.users.create_failed")

        await ensure_mfa_relationships_loaded(self.db, db_user)
        return db_user

    async def create_user(
        self,
        data: schemas.UserCreate,
        request: Request,
        current_user: models.User,
    ) -> models.User:
        """Admin create user."""
        if current_user.role != "admin":
            raise PermissionDenied()

        if data.invite_code:
            code_obj = await self.repo.get_invite_code(data.invite_code)
            if not code_obj:
                raise BusinessRuleViolation("errors.users.invalid_invite_code")
        elif data.role in ["teacher"]:
            # Logic from before
            raise BusinessRuleViolation("errors.users.invite_code_required")

        if await self.repo.check_email_exists(data.email):
            raise EntityAlreadyExists("User", data.email)

        password = data.password
        hashed = get_password_hash(password)

        user_data = data.model_dump(
            exclude={"invite_code", "password", "spotify_connected"}
        )
        user_data["hashed_password"] = hashed

        # Use repo.create
        user = await self.repo.create(user_data)

        self.audit.log("users.create", request, user_id=user.id, reason="admin_create")
        await ensure_mfa_relationships_loaded(self.db, user)
        await attach_pending_email(self.db, user)
        return user

    async def upload_avatar(
        self,
        user: models.User,
        file: UploadFile,
    ) -> models.User:
        db_user = await self.repo.get(user.id)
        if not db_user:
            raise EntityNotFound("User", user.id)

        file_url = await save_upload(file, "avatars", f"user_{user.id}_avatar")

        if db_user.avatar_url:
            await delete_static_file(db_user.avatar_url)

        db_user.avatar_url = file_url
        try:
            await self.db.commit()
            await self.db.refresh(db_user)
        except Exception:
            await self.db.rollback()
            await delete_static_file(file_url)
            raise
        return db_user

    async def upload_cover(
        self,
        user: models.User,
        file: UploadFile,
    ) -> models.User:
        db_user = await self.repo.get(user.id)
        if not db_user:
            raise EntityNotFound("User", user.id)

        file_url = await save_upload(file, "covers", f"user_{user.id}_cover")

        if db_user.cover_url:
            await delete_static_file(db_user.cover_url)

        db_user.cover_url = file_url
        try:
            await self.db.commit()
            await self.db.refresh(db_user)
        except Exception:
            await self.db.rollback()
            await delete_static_file(file_url)
            raise
        return db_user

    def _dt_to_iso(self, value: datetime | None) -> str:
        if value is None:
            return ""
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.astimezone(UTC).isoformat()

    async def get_attendance_stats(
        self,
        *,
        user_id: int,
        period_days: int,
        period_key: str | None = None,
        cache: BaseCache | None = None,
        skip_cache: bool = False,
    ) -> dict[str, Any]:
        cache_period_key = stats_cache.resolve_period_key(period_key, period_days)
        cached = await stats_cache.get_cached_stats(
            cache=cache,
            kind="attendance",
            user_id=user_id,
            period_key=cache_period_key,
            skip_cache=skip_cache,
        )
        if cached is not None:
            return cached.payload

        now = datetime.now(UTC)
        window_start = now - timedelta(days=period_days)
        previous_start = window_start - timedelta(days=period_days)

        attendance_alias = aliased(models.EventAttendance)
        filtered_events = (
            select(
                models.Event.id.label("event_id"),
                case(
                    (models.Event.starts_at >= window_start, literal("current")),
                    else_=literal("previous"),
                ).label("period"),
            )
            .where(
                models.Event.is_active.is_(True),
                models.Event.starts_at >= previous_start,
                models.Event.starts_at < now,
            )
            .cte("filtered_events")
        )

        attendance_join = filtered_events.outerjoin(
            attendance_alias,
            and_(
                attendance_alias.event_id == filtered_events.c.event_id,
                attendance_alias.user_id == user_id,
            ),
        )

        stats_subquery = (
            select(
                func.coalesce(
                    func.sum(case((filtered_events.c.period == "current", 1), else_=0)),
                    0,
                ).label("current_total"),
                func.coalesce(
                    func.sum(
                        case((filtered_events.c.period == "previous", 1), else_=0)
                    ),
                    0,
                ).label("previous_total"),
                func.coalesce(
                    func.sum(
                        case(
                            (
                                and_(
                                    filtered_events.c.period == "current",
                                    attendance_alias.id.isnot(None),
                                ),
                                1,
                            ),
                            else_=0,
                        )
                    ),
                    0,
                ).label("current_attended"),
                func.coalesce(
                    func.sum(
                        case(
                            (
                                and_(
                                    filtered_events.c.period == "previous",
                                    attendance_alias.id.isnot(None),
                                ),
                                1,
                            ),
                            else_=0,
                        )
                    ),
                    0,
                ).label("previous_attended"),
            ).select_from(attendance_join)
        ).subquery()

        recent_attendance_base = (
            select(
                models.EventAttendance.registered_at.label("registered_at"),
                models.Event.starts_at.label("starts_at"),
                models.Event.title.label("title"),
                func.row_number()
                .over(order_by=models.EventAttendance.registered_at.desc())
                .label("rn"),
            )
            .join(models.Event, models.Event.id == models.EventAttendance.event_id)
            .where(
                models.EventAttendance.user_id == user_id,
                models.Event.is_active.is_(True),
                models.Event.starts_at >= window_start,
                models.Event.starts_at < now,
            )
        ).subquery()

        top_recent = (
            select(
                recent_attendance_base.c.registered_at,
                recent_attendance_base.c.starts_at,
                recent_attendance_base.c.title,
                recent_attendance_base.c.rn,
            ).where(recent_attendance_base.c.rn <= 5)
        ).subquery()

        stats_rows = await self.db.execute(
            select(
                stats_subquery.c.current_total,
                stats_subquery.c.previous_total,
                stats_subquery.c.current_attended,
                stats_subquery.c.previous_attended,
                top_recent.c.registered_at,
                top_recent.c.starts_at,
                top_recent.c.title,
                top_recent.c.rn,
            )
            .select_from(stats_subquery.outerjoin(top_recent, true()))
            .order_by(top_recent.c.rn)
        )

        rows = stats_rows.all()

        if rows:
            first_row = rows[0]
            total_events = int(first_row.current_total or 0)
            attended_events = int(first_row.current_attended or 0)
            previous_events = int(first_row.previous_total or 0)
            previous_attended = int(first_row.previous_attended or 0)
        else:
            total_events = attended_events = previous_events = previous_attended = 0

        percent = (attended_events / total_events * 100) if total_events else 0.0
        previous_percent = (
            previous_attended / previous_events * 100 if previous_events else 0.0
        )

        recent: list[dict[str, Any]] = []
        for row in rows:
            if getattr(row, "rn", None) is None:
                continue
            date_source = row.starts_at or row.registered_at
            recent.append(
                {
                    "date": self._dt_to_iso(date_source),
                    "status": "present",
                    "course": row.title or None,
                }
            )

        result = {
            "percent": round(percent, 2),
            "present": attended_events,
            "total": total_events,
            "trend": round(percent - previous_percent, 2),
            "period_key": cache_period_key,
            "recent": recent,
        }
        await stats_cache.set_cached_stats(
            cache=cache,
            kind="attendance",
            user_id=user_id,
            period_key=cache_period_key,
            payload=result,
            skip_cache=skip_cache,
        )
        return result

    def _parse_grade_payload(
        self, body: str | None, *, fallback_title: str, fallback_date: datetime | None
    ) -> dict[str, Any] | None:
        if not body:
            return None
        try:
            payload = json.loads(body)
        except (TypeError, ValueError):
            return None
        if not isinstance(payload, dict):
            return None
        score = payload.get("score")
        try:
            score_value = float(score)
        except (TypeError, ValueError):
            return None
        max_score = payload.get("max")
        max_value = None
        if max_score is not None:
            try:
                max_value = float(max_score)
            except (TypeError, ValueError):
                max_value = None
        course = payload.get("course")
        if not isinstance(course, str) or not course.strip():
            course = fallback_title
        date_raw = payload.get("date")
        if isinstance(date_raw, str):
            try:
                parsed = datetime.fromisoformat(date_raw)
            except ValueError:
                parsed = None
        else:
            parsed = None
        date_value = parsed or fallback_date
        return {
            "course": course,
            "score": score_value,
            "max": max_value,
            "date": self._dt_to_iso(date_value),
        }

    async def get_grade_stats(
        self,
        *,
        user_id: int,
        period_days: int,
        period_key: str | None = None,
        cache: BaseCache | None = None,
        skip_cache: bool = False,
    ) -> dict[str, Any]:
        cache_period_key = stats_cache.resolve_period_key(period_key, period_days)
        cached = await stats_cache.get_cached_stats(
            cache=cache,
            kind="grades",
            user_id=user_id,
            period_key=cache_period_key,
            skip_cache=skip_cache,
        )
        if cached is not None:
            return cached.payload

        now = datetime.now(UTC)
        window_start = now - timedelta(days=period_days)
        previous_start = window_start - timedelta(days=period_days)

        current_rows = await self.db.execute(
            select(models.Notification)
            .where(
                models.Notification.user_id == user_id,
                models.Notification.type == "grade",
                models.Notification.created_at >= window_start,
                models.Notification.created_at < now,
            )
            .order_by(models.Notification.created_at.desc())
        )
        current_entries = []
        for notification in current_rows.scalars():
            entry = self._parse_grade_payload(
                notification.body,
                fallback_title=notification.title or "",
                fallback_date=notification.created_at,
            )
            if entry:
                current_entries.append(entry)

        previous_rows = await self.db.execute(
            select(models.Notification).where(
                models.Notification.user_id == user_id,
                models.Notification.type == "grade",
                models.Notification.created_at >= previous_start,
                models.Notification.created_at < window_start,
            )
        )
        previous_entries = []
        for notification in previous_rows.scalars():
            entry = self._parse_grade_payload(
                notification.body,
                fallback_title=notification.title or "",
                fallback_date=notification.created_at,
            )
            if entry:
                previous_entries.append(entry)

        def _average(items: list[dict[str, Any]]) -> float:
            if not items:
                return 0.0
            return sum(item["score"] for item in items) / len(items)

        average = _average(current_entries)
        previous_average = _average(previous_entries)

        max_values = [item["max"] for item in current_entries if item.get("max")]
        scale = "5"
        if any(value and value > 5 for value in max_values):
            scale = "100"

        recent = current_entries[:5]

        result = {
            "average": round(average, 2) if current_entries else 0.0,
            "scale": scale,
            "trend": round(average - previous_average, 2),
            "recent": recent,
            "period_key": cache_period_key,
        }
        await stats_cache.set_cached_stats(
            cache=cache,
            kind="grades",
            user_id=user_id,
            period_key=cache_period_key,
            payload=result,
            skip_cache=skip_cache,
        )
        return result

    async def get_participation_stats(
        self,
        *,
        user_id: int,
        period_days: int,
        period_key: str | None = None,
        cache: BaseCache | None = None,
        skip_cache: bool = False,
    ) -> dict[str, Any]:
        cache_period_key = stats_cache.resolve_period_key(period_key, period_days)
        cached = await stats_cache.get_cached_stats(
            cache=cache,
            kind="participation",
            user_id=user_id,
            period_key=cache_period_key,
            skip_cache=skip_cache,
        )
        if cached is not None:
            return cached.payload

        now = datetime.now(UTC)
        window_start = now - timedelta(days=period_days)
        previous_start = window_start - timedelta(days=period_days)

        # Helper inner function for reuse
        def _ensure_utc_local(value: datetime) -> datetime:
            if value.tzinfo is None:
                return value.replace(tzinfo=UTC)
            return value.astimezone(UTC)

        def _attendance_query(start: datetime, end: datetime):
            return (
                select(
                    models.EventAttendance.event_id,
                    models.EventAttendance.registered_at,
                    models.Event.starts_at,
                    models.Event.ends_at,
                    models.Event.title,
                    models.Event.event_type,
                )
                .join(models.Event, models.Event.id == models.EventAttendance.event_id)
                .where(
                    models.EventAttendance.user_id == user_id,
                    models.Event.starts_at >= start,
                    models.Event.starts_at < end,
                    models.Event.is_active.is_(True),
                )
            )

        current_rows = await self.db.execute(
            _attendance_query(window_start, now).order_by(models.Event.starts_at.desc())
        )
        current_entries = current_rows.all()
        previous_rows = await self.db.execute(
            _attendance_query(previous_start, window_start)
        )
        previous_entries = previous_rows.all()

        unique_events = {}
        total_hours = 0.0
        event_types = set()
        recent = []
        for (
            event_id,
            registered_at,
            starts_at,
            ends_at,
            title,
            event_type,
        ) in current_entries:
            if event_id not in unique_events:
                unique_events[event_id] = (starts_at, ends_at)
                if starts_at and ends_at:
                    start_dt = _ensure_utc_local(starts_at)
                    end_dt = _ensure_utc_local(ends_at)
                    if end_dt > start_dt:
                        total_hours += (end_dt - start_dt).total_seconds() / 3600
            if event_type:
                event_types.add(event_type)
            recent.append(
                {
                    "title": title or "",
                    "date": self._dt_to_iso(starts_at or registered_at),
                    "role": event_type or None,
                }
            )

        recent.sort(key=lambda item: item["date"], reverse=True)
        recent = recent[:5]

        previous_event_ids = {row[0] for row in previous_entries}

        result = {
            "events": len(unique_events),
            "hours": round(total_hours, 2) if total_hours else 0.0,
            "groups": len(event_types),
            "trend": len(unique_events) - len(previous_event_ids),
            "recent": recent,
            "period_key": cache_period_key,
        }
        await stats_cache.set_cached_stats(
            cache=cache,
            kind="participation",
            user_id=user_id,
            period_key=cache_period_key,
            payload=result,
            skip_cache=skip_cache,
        )
        return result
