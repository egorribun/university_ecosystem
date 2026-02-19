import json
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import Request, UploadFile

from app.api.utils import save_upload
from app.auth import mfa
from app.auth.security import _validate_password_hibp, get_password_hash
from app.core.config import settings
from app.core.exceptions.domain import (
    BusinessRuleViolation,
    EntityAlreadyExists,
    EntityNotFound,
    PermissionDenied,
)
from app.core.localization import resolve_locale, translate
from app.deps.cache import BaseCache
from app.models import models
from app.models.user_loaders import ensure_mfa_relationships_loaded
from app.repositories.user_repository import UserRepository
from app.repositories.user_stats_repository import UserStatsRepository
from app.schemas import schemas
from app.services import stats_cache
from app.services.audit_service import AuditService
from app.services.auth_service import attach_pending_email
from app.services.data_access import log_data_access
from app.services.notification_service import NotificationService
from app.services.user.logic import anonymize_user_data, update_user_attributes
from app.utils.files import delete_static_file

logger = logging.getLogger(__name__)


class UserService:
    def __init__(
        self,
        user_repo: UserRepository,
        stats_repo: UserStatsRepository,
        audit: AuditService,
        notifications: NotificationService,
    ) -> None:
        self.repo = user_repo
        self.stats_repo = stats_repo
        self.audit = audit
        self.notifications = notifications

    async def get_user_by_id(self, user_id: int) -> models.User | None:
        return await self.repo.get(user_id)

    async def get_user_by_email(self, email: str) -> models.User | None:
        return await self.repo.get_by_email(email)

    async def update_user_profile(
        self,
        user: models.User,
        data: schemas.UserProfileUpdate,
        request: Request,
    ) -> models.User:
        """Update current user profile (self-update)."""
        db_user = await self.repo.get(user.id)
        if not db_user:
            raise EntityNotFound("User", user.id)

        payload = data.model_dump(exclude_unset=True)

        if "email" in payload and payload["email"] is not None:
            from app.services.user.logic import validate_user_email

            payload["email"] = await validate_user_email(
                self.repo, payload["email"], exclude_user_id=user.id
            )

        if hasattr(db_user, "profile") and db_user.profile:
            # Manually update profile fields if they are in payload
            profile_fields = {
                "first_name",
                "last_name",
                "bio",
                "phone_number",
                "website",
                "location",
            }
            for field in profile_fields:
                if field in payload:
                    setattr(db_user.profile, field, payload.pop(field))

        # Update remaining user fields
        update_user_attributes(db_user, payload)

        await self.repo.commit()
        await self.repo.refresh(db_user)
        # Ensure relationships loaded for schema validation
        await ensure_mfa_relationships_loaded(self.repo.db, db_user)
        await attach_pending_email(self.repo.db, db_user)

        self.audit.log("users.update", request, user_id=user.id, reason="self_update")
        return db_user

    async def get_users(
        self,
        request: Request,
        current_user: models.User | None = None,
        filters: schemas.UserSearchFilter | None = None,
    ) -> list[models.User]:
        """Admin list users."""
        filters = filters or schemas.UserSearchFilter()

        # Check permissions if current_user provided (for admin endpoint)
        # If no current_user (internal call?), skip check or require it?
        # Based on test_get_users_non_admin_no_search, it expects permission check.

        if current_user and (
            current_user.role != "admin"
            and not filters.search
            and not filters.full_name
        ):
            raise PermissionDenied()

        # Clean name query
        name_query = filters.full_name
        if name_query:
            name_query = name_query.strip()
            if not name_query:
                name_query = None

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
        update_user_attributes(db_user, payload)

        reset_stats = None
        if reset_requested:
            reset_stats = await mfa.reset_user_mfa(self.repo.db, user=db_user)

        await self.repo.commit()
        await self.repo.refresh(db_user)
        await ensure_mfa_relationships_loaded(self.repo.db, db_user)

        updated_user = db_user

        self.audit.log(
            "users.admin_update",
            request,
            user_id=updated_user.id,
            reason="admin_update",
        )
        if reset_stats is not None and reset_stats.changed:
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

        await anonymize_user_data(db_user)

        self.audit.log(
            "users.admin_delete", request, user_id=user_id, reason="admin_delete"
        )

        await self.repo.commit()
        return {"deleted": True, "user_id": user_id}

    async def delete_avatar(
        self,
        user: models.User,
    ) -> models.User:
        db_user = await self.repo.get(user.id)
        if db_user.profile and db_user.profile.avatar_url:
            await delete_static_file(db_user.profile.avatar_url)
        if db_user.profile:
            db_user.profile.avatar_url = None
        await self.repo.commit()
        await self.repo.refresh(db_user)
        await ensure_mfa_relationships_loaded(self.repo.db, db_user)
        return db_user

    async def delete_cover(
        self,
        user: models.User,
    ) -> models.User:
        db_user = await self.repo.get(user.id)
        if db_user.profile and db_user.profile.cover_url:
            await delete_static_file(db_user.profile.cover_url)
        if db_user.profile:
            db_user.profile.cover_url = None
        await self.repo.commit()
        await self.repo.refresh(db_user)
        await ensure_mfa_relationships_loaded(self.repo.db, db_user)
        return db_user

    async def export_user_data(
        self, user: models.User, request: Request
    ) -> schemas.DataExportOut:
        db_user = await self.repo.get(user.id)
        if not db_user:
            raise EntityNotFound("User", user.id)
        await ensure_mfa_relationships_loaded(self.repo.db, db_user)
        await attach_pending_email(self.repo.db, db_user)

        profile = schemas.UserOut.model_validate(db_user).model_dump()

        # Sessions
        sessions_list = await self.repo.get_user_sessions(user.id)
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
            for session in sessions_list
        ]

        # Notifications
        notifications_list = await self.repo.get_user_notifications(user.id)
        notifications = [
            {
                "id": item.id,
                "title": item.title,
                "body": item.body,
                "type": item.type,
                "created_at": item.created_at,
                "read_at": item.read_at,
            }
            for item in notifications_list
        ]

        # MFA challenges directly from relationship
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

        access_logs = await self.repo.get_user_access_logs(user.id, limit=2000)
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
            self.repo.db,
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

        await anonymize_user_data(db_user)
        await self.repo.delete_sensitive_data(user.id)

        self.audit.log("users.data_delete", request, user_id=user.id)
        await log_data_access(
            self.repo.db,
            actor_user_id=user.id,
            subject_user_id=user.id,
            resource_type="profile",
            resource_id=str(user.id),
            action="delete",
            request=request,
        )

        await self.repo.commit()
        await self.repo.refresh(db_user)
        return schemas.DataDeletionOut(deleted=True, anonymized_email=db_user.email)

    async def register_user(
        self,
        user_in: schemas.UserCreate,
    ) -> models.User:
        """Register a new user (public signup)."""
        raw_role = getattr(user_in, "role", None)
        from app.models.enums import UserRole

        requested_role = UserRole(raw_role) if raw_role else UserRole.STUDENT
        normalized_email = user_in.email.strip().lower()

        code = None
        if hasattr(user_in, "invite_code") and requested_role in (
            UserRole.TEACHER,
            UserRole.ADMIN,
        ):
            code_obj = await self.repo.get_invite_code(user_in.invite_code)
            if not code_obj:
                raise BusinessRuleViolation("errors.users.invalid_invite")

            if (
                code_obj.role != requested_role.value
                or not code_obj.is_active
                or code_obj.is_used
            ):
                raise BusinessRuleViolation("errors.users.invalid_invite")
            code = code_obj

        if await self.repo.check_email_exists(normalized_email):
            raise EntityAlreadyExists("User", normalized_email)

        if settings.password_hibp_check_enabled:
            await _validate_password_hibp(user_in.password)
        hashed_password = await get_password_hash(user_in.password)

        user_data = user_in.model_dump(
            exclude={"invite_code", "password", "spotify_connected"}
        )
        user_data["hashed_password"] = hashed_password
        user_data["role"] = requested_role.value
        user_data["email"] = normalized_email
        if "id" in user_data:
            del user_data["id"]

        user_data["mfa_required"] = settings.mfa_enabled
        user_data["mfa_default_method"] = settings.mfa_default_method

        # Use repository for atomic creation and invite code update
        try:
            db_user = await self.repo.create_with_invite(user_data, code)
            await self.repo.commit()
            await self.repo.refresh(db_user)
        except Exception:
            await self.repo.rollback()
            raise BusinessRuleViolation("errors.users.create_failed")

        await ensure_mfa_relationships_loaded(self.repo.db, db_user)
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
            raise BusinessRuleViolation("errors.users.invite_code_required")

        if await self.repo.check_email_exists(data.email):
            raise EntityAlreadyExists("User", data.email)

        password = data.password
        if settings.password_hibp_check_enabled:
            await _validate_password_hibp(password)
        hashed = await get_password_hash(password)

        user_data = data.model_dump(
            exclude={"invite_code", "password", "spotify_connected"}
        )
        user_data["hashed_password"] = hashed

        user = await self.repo.create(user_data)

        self.audit.log("users.create", request, user_id=user.id, reason="admin_create")
        await ensure_mfa_relationships_loaded(self.repo.db, user)
        await attach_pending_email(self.repo.db, user)
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

        if db_user.profile and db_user.profile.avatar_url:
            await delete_static_file(db_user.profile.avatar_url)

        if db_user.profile:
            db_user.profile.avatar_url = file_url
        try:
            await self.repo.commit()
            await self.repo.refresh(db_user)
        except Exception:
            await self.repo.rollback()
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

        if db_user.profile and db_user.profile.cover_url:
            await delete_static_file(db_user.profile.cover_url)

        if db_user.profile:
            db_user.profile.cover_url = file_url
        try:
            await self.repo.commit()
            await self.repo.refresh(db_user)
        except Exception:
            await self.repo.rollback()
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

        # Use Repository for complex query
        rows = await self.stats_repo.get_attendance_stats_raw(
            user_id, window_start, previous_start, now
        )

        if rows:
            first_row = rows[0]
            # Access row fields safely - they are result objects
            total_events = int(getattr(first_row, "current_total", 0) or 0)
            attended_events = int(getattr(first_row, "current_attended", 0) or 0)
            previous_events = int(getattr(first_row, "previous_total", 0) or 0)
            previous_attended = int(getattr(first_row, "previous_attended", 0) or 0)
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
            date_source = getattr(row, "starts_at", None) or getattr(
                row, "registered_at", None
            )
            recent.append(
                {
                    "date": self._dt_to_iso(date_source),
                    "status": "present",
                    "course": getattr(row, "title", None) or None,
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

        # Use Repository
        current_rows = await self.stats_repo.get_grade_notifications(
            user_id, window_start, now
        )
        current_entries = []
        for notification in current_rows:
            entry = self._parse_grade_payload(
                notification.body,
                fallback_title=notification.title or "",
                fallback_date=notification.created_at,
            )
            if entry:
                current_entries.append(entry)

        previous_rows = await self.stats_repo.get_grade_notifications(
            user_id, previous_start, window_start
        )
        previous_entries = []
        for notification in previous_rows:
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
        start_date = now - timedelta(days=period_days)

        rows = await self.stats_repo.get_participation_stats_raw(
            user_id=user_id, window_start=start_date, now=now
        )

        events_count = len(rows)
        total_hours = 0.0
        unique_groups = set()
        recent_items = []

        for row in rows:
            duration = (row.ends_at - row.starts_at).total_seconds() / 3600
            total_hours += max(0.0, duration)
            if row.event_type:
                unique_groups.add(row.event_type)
            if len(recent_items) < 5:
                recent_items.append(
                    {"title": row.title, "date": row.starts_at.isoformat()}
                )

        # Mock trend for now as it requires previous period data
        result = {
            "events": events_count,
            "hours": round(total_hours, 2),
            "groups": len(unique_groups),
            "trend": 1 if events_count > 0 else 0,
            "period_key": cache_period_key,
            "recent": recent_items,
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
