from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.cqrs.queries import GetScheduleHandler, GetStatsHandler
from app.deps.cache import BaseCache, get_cache
from app.services.audit_service import (
    AuditService,
    SecureAuditService,
    get_secure_audit_service,
)
from app.services.auth_service import AuthService
from app.services.user_service import UserService


def get_audit_service() -> AuditService:
    return AuditService()


def get_secure_audit_service_dep() -> SecureAuditService:
    return get_secure_audit_service()


def get_user_service(
    db: AsyncSession = Depends(get_db),
    audit: AuditService = Depends(get_audit_service),
) -> UserService:
    return UserService(db=db, audit=audit)


def get_auth_service(
    db: AsyncSession = Depends(get_db),
    audit: AuditService = Depends(get_audit_service),
) -> AuthService:
    return AuthService(db=db, audit=audit)


def get_schedule_handler(
    db: AsyncSession = Depends(get_db), cache: BaseCache = Depends(get_cache)
) -> GetScheduleHandler:
    return GetScheduleHandler(db=db, cache=cache)


def get_stats_handler(
    db: AsyncSession = Depends(get_db), cache: BaseCache = Depends(get_cache)
) -> GetStatsHandler:
    return GetStatsHandler(db=db, cache=cache)
