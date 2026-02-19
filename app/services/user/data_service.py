import logging

from fastapi import Request

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
        repo: UserRepository,
        audit: AuditService,
    ) -> None:
        self.repo = repo
        self.audit = audit

    async def export_user_data(
        self, user: models.User, request: Request
    ) -> schemas.DataExportOut:
        # 1. Fetch user profile (lightweight)
        db_user = await self.repo.get(user.id)
        if not db_user:
            raise EntityNotFound("User", user.id)

        # 2. Attach pending email
        await attach_pending_email(self.repo.db, db_user)

        # 3. Fetch related data in parallel (or sequential for now) with limits
        # We limit specific collections to prevent OOM on massive accounts
        sessions_list = await self.repo.get_user_sessions(user.id, limit=1000)
        notifications_list = await self.repo.get_user_notifications(user.id, limit=1000)
        challenges_list = await self.repo.get_user_mfa_challenges(user.id, limit=1000)
        enrollments_list = await self.repo.get_user_totp_enrollments(user.id)

        # 4. Consolidate and serialize data
        profile = schemas.UserOut.from_orm(db_user).model_dump()

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
            for c in challenges_list
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
            for e in enrollments_list
        ]

        # 5. Access logs (internal caching/limit handled by export_access_logs)
        access_logs = await export_access_logs(
            self.repo.db,
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

        # 6. Auditing & Access Logging (Asynchronous side-effects)
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

        from app.services.user.logic import execute_user_anonymization

        anonymized_email = await execute_user_anonymization(self.repo, db_user)

        self.audit.log("users.data_delete", request, user_id=user.id)
        await log_data_access(
            self.repo.db,
            actor_user_id=user.id,
            subject_user_id=user.id,
            resource_type="profile",
            resource_id=str(user.id),
            action="delete",
            request=request,
            commit=False,
        )

        await self.repo.commit()
        await self.repo.refresh(db_user)
        return schemas.DataDeletionOut(deleted=True, anonymized_email=anonymized_email)
