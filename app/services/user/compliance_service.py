import logging
import uuid
from typing import Any

from fastapi import Request
from sqlalchemy.exc import IntegrityError

from app.auth.security import _validate_password_hibp, get_password_hash
from app.core.config import settings
from app.core.exceptions.domain import (
    BusinessRuleViolation,
    EntityAlreadyExists,
    EntityNotFound,
    PermissionDenied,
)
from app.models.enums import UserRole
from app.repositories.user_repository import UserRepository
from app.schemas import schemas
from app.schemas.dtos import UserDTO
from app.services.audit_service import AuditService, SecurityEvent, auditable
from app.services.data_access import log_data_access
from app.services.user.logic import anonymize_user_data

logger = logging.getLogger(__name__)


class UserComplianceService:
    def __init__(self, user_repo: UserRepository, audit: AuditService) -> None:
        self.repo = user_repo
        self.audit = audit

    @auditable(SecurityEvent.ADMIN_USER_DELETE, user_id_param="user_id")
    async def admin_delete_user(
        self,
        user_id: uuid.UUID | str,
        request: Request,
        current_user: UserDTO,
    ) -> dict[str, Any]:
        if current_user.role != "admin":
            raise PermissionDenied()

        # Fetch ORM user
        db_user = await self.repo._get_orm(user_id)
        if db_user is None:
            raise EntityNotFound("User", user_id)

        if db_user.id == current_user.id:
            raise BusinessRuleViolation("errors.users.cannot_delete_self")

        # Perform anonymization
        await anonymize_user_data(db_user)
        await self.repo.delete_sensitive_data(db_user.id)

        await self.repo.commit()
        return {"deleted": True, "user_id": user_id}

    @auditable("users.data_export", user_id_param="user")
    async def export_user_data(
        self, user: UserDTO, request: Request
    ) -> schemas.DataExportOut:
        db_user = await self.repo.get(user.id)
        if not db_user:
            raise EntityNotFound("User", user.id)

        # db_user is already a DTO and has mfa_challenges/totp_enrollments
        profile = db_user.model_dump()

        import asyncio

        # PERF-010 (audit 2026-03-04): Gather independent I/O fetches concurrently
        sessions_list, notifications_list, access_logs = await asyncio.gather(
            self.repo.get_user_sessions(user.id),
            self.repo.get_user_notifications(user.id),
            self.repo.get_user_access_logs(user.id, limit=2000),
        )

        sessions = [
            {
                "id": s.id,
                "created_at": s.created_at,
                "expires_at": s.expires_at,
                "revoked_at": s.revoked_at,
                "ip_address": s.ip_address,
                "user_agent": s.user_agent,
                "last_seen_at": s.last_seen_at,
                "mfa_completed_at": s.mfa_completed_at,
            }
            for s in sessions_list
        ]

        notifications = [
            {
                "id": n.id,
                "title": n.title,
                "body": n.body,
                "type": n.type,
                "created_at": n.created_at,
                "read_at": n.read_at,
            }
            for n in notifications_list
        ]

        challenges = [
            {
                "id": c.id,
                "type": c.challenge_type,
                "expires_at": c.expires_at,
                "consumed_at": c.consumed_at,
                "created_at": c.created_at,
            }
            for c in getattr(db_user, "mfa_challenges", [])
        ]

        enrollments = [
            {
                "id": e.id,
                "label": e.label,
                "is_active": e.is_active,
                "confirmed_at": e.confirmed_at,
                "revoked_at": e.revoked_at,
                "created_at": e.created_at,
            }
            for e in getattr(db_user, "totp_enrollments", [])
        ]

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

    @auditable(SecurityEvent.USER_DELETE, user_id_param="user")
    async def delete_user_data(
        self,
        user: UserDTO,
        request: Request,
        *,
        confirm: bool,
    ) -> schemas.DataDeletionOut:
        if not confirm:
            raise BusinessRuleViolation("errors.users.confirmation_required")

        # Fetch ORM user
        db_user = await self.repo._get_orm(user.id)
        if not db_user:
            raise EntityNotFound("User", user.id)

        await anonymize_user_data(db_user)
        await self.repo.delete_sensitive_data(db_user.id)

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
        # Refresh to get anonymized email
        updated_user = await self.repo.get(user.id)
        assert updated_user is not None  # nosec B101
        return schemas.DataDeletionOut(
            deleted=True, anonymized_email=updated_user.email
        )

    async def register_user(self, user_in: schemas.UserCreate) -> UserDTO:
        raw_role = getattr(user_in, "role", None)
        requested_role = UserRole(raw_role) if raw_role else UserRole.STUDENT
        normalized_email = user_in.email.strip().lower()

        if await self.repo.check_email_exists(normalized_email):
            raise EntityAlreadyExists("User", normalized_email)

        code = None
        if hasattr(user_in, "invite_code") and requested_role in (
            UserRole.TEACHER,
            UserRole.ADMIN,
        ):
            code_obj = await self.repo.get_invite_code(str(user_in.invite_code))
            if (
                not code_obj
                or code_obj.role != requested_role.value
                or not code_obj.is_active
                or code_obj.is_used
            ):
                raise BusinessRuleViolation("errors.users.invalid_invite")
            code = code_obj

        if settings.password_hibp_check_enabled:
            await _validate_password_hibp(user_in.password)
        hashed_password = await get_password_hash(user_in.password)

        user_data = user_in.model_dump(
            exclude={"invite_code", "password", "spotify_connected"}
        )
        user_data.update(
            {
                "hashed_password": hashed_password,
                "role": requested_role.value,
                "email": normalized_email,
                "mfa_required": settings.mfa_enabled,
                "mfa_default_method": settings.mfa_default_method,
            }
        )
        try:
            db_user = await self.repo.create_with_invite(user_data, code)
            await self.repo.commit()
            # create_with_invite now returns DTO
            return db_user
        except Exception as exc:
            import traceback

            traceback.print_exc()
            await self.repo.rollback()
            raise BusinessRuleViolation("errors.users.create_failed") from exc

    @auditable(SecurityEvent.ADMIN_USER_CREATE)
    async def create_user(
        self,
        data: schemas.UserCreate,
        request: Request,
        current_user: UserDTO,
    ) -> UserDTO:
        if current_user.role != "admin":
            raise PermissionDenied()

        if data.invite_code:
            code_obj = await self.repo.get_invite_code(data.invite_code)
            if not code_obj:
                raise BusinessRuleViolation("errors.users.invalid_invite_code")
        elif data.role in ["teacher"]:
            raise BusinessRuleViolation("errors.users.invite_code_required")

        if settings.password_hibp_check_enabled:
            await _validate_password_hibp(data.password)
        hashed = await get_password_hash(data.password)

        user_data = data.model_dump(
            exclude={"invite_code", "password", "spotify_connected"}
        )
        user_data["hashed_password"] = hashed

        try:
            user = await self.repo.create(user_data)
            await self.repo.commit()
            return user
        except IntegrityError as exc:
            await self.repo.rollback()
            error_str = str(exc.orig).lower() if exc.orig else str(exc).lower()
            if "email" in error_str or "users_email_key" in error_str:
                raise EntityAlreadyExists("User", data.email) from exc
            raise BusinessRuleViolation("errors.users.create_failed") from exc
