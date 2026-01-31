import logging

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions.domain import (
    BusinessRuleViolation,
    EntityNotFound,
)
from app.models import models
from app.repositories.user_repository import UserRepository
from app.schemas import schemas
from app.services.audit_service import AuditService
from app.services.auth_service import attach_pending_email
from app.services.data_access import export_access_logs, log_data_access

logger = logging.getLogger(__name__)


class UserDataService:
    def __init__(
        self,
        db: AsyncSession,
        repo: UserRepository,
        audit: AuditService,
    ) -> None:
        self.db = db
        self.repo = repo
        self.audit = audit

    async def export_user_data(
        self, user: models.User, request: Request
    ) -> schemas.DataExportOut:
        db_user = await self.repo.get_full_user_data(user.id)
        if not db_user:
            raise EntityNotFound("User", user.id)
        await attach_pending_email(self.db, db_user)

        profile = schemas.UserOut.from_orm(db_user).model_dump()

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
            for session in db_user.sessions
        ]

        notifications = [
            {
                "id": item.id,
                "title": item.title,
                "body": item.body,
                "type": item.type,
                "created_at": item.created_at,
                "read_at": item.read_at,
            }
            for item in db_user.notifications
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

        from app.services.user.logic import anonymize_user_data

        anonymized_email = await anonymize_user_data(db_user)
        await self.repo.delete_sensitive_data(user.id)

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
