from __future__ import annotations

from dishka import Provider, Scope, provide

from app.core.protocols import AsyncDatabaseSession
from app.repositories.active_session_repository import ActiveSessionRepository
from app.repositories.unit_of_work import UnitOfWork
from app.repositories.user_repository import UserRepository
from app.services.audit_service import AuditService
from app.services.notification_service import NotificationService
from app.services.session_service import SessionService
from app.services.user.compliance_service import UserComplianceService
from app.services.user.media_service import UserMediaService
from app.services.user.profile_service import UserProfileService
from app.services.user_service import UserService


class UserProvider(Provider):
    # TD-33-08: NotificationService provider removed — now provided by
    # ContentProvider only.  Dishka injects the same instance into both
    # UserService and content services, eliminating the duplicate registration.

    @provide(scope=Scope.REQUEST)
    def user_service(
        self,
        uow: UnitOfWork,
        audit: AuditService,
        notifications: NotificationService,
    ) -> UserService:
        return UserService(
            uow=uow,
            audit=audit,
            notifications=notifications,
        )

    @provide(scope=Scope.REQUEST)
    def user_profile_service(
        self,
        uow: UnitOfWork,
        audit: AuditService,
        notifications: NotificationService,
    ) -> UserProfileService:
        return UserProfileService(
            uow=uow,
            audit=audit,
            notifications=notifications,
        )

    @provide(scope=Scope.REQUEST)
    def user_compliance_service(
        self,
        uow: UnitOfWork,
        audit: AuditService,
    ) -> UserComplianceService:
        return UserComplianceService(uow=uow, audit=audit)

    @provide(scope=Scope.REQUEST)
    def user_media_service(self, uow: UnitOfWork) -> UserMediaService:
        return UserMediaService(uow=uow)

    @provide(scope=Scope.REQUEST)
    def unit_of_work(self, db: AsyncDatabaseSession) -> UnitOfWork:
        from app.repositories.unit_of_work import uow_from_session

        return uow_from_session(db)

    @provide(scope=Scope.REQUEST)
    def user_repository(self, db: AsyncDatabaseSession) -> UserRepository:
        return UserRepository(db)

    @provide(scope=Scope.REQUEST)
    def active_session_repository(
        self, db: AsyncDatabaseSession
    ) -> ActiveSessionRepository:
        return ActiveSessionRepository(db)

    @provide(scope=Scope.REQUEST)
    def session_service(self, uow: UnitOfWork) -> SessionService:
        return SessionService(uow=uow)
