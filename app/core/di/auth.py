from __future__ import annotations

from dishka import Provider, Scope, provide

from app.core.protocols import AsyncDatabaseSession
from app.repositories.auth_repository import AuthRepository
from app.repositories.unit_of_work import UnitOfWork
from app.repositories.user_repository import UserRepository
from app.services.audit_service import AuditService
from app.services.auth.credential_validator import CredentialValidator
from app.services.auth.lockout import LockoutService
from app.services.auth.login_service import LoginService
from app.services.auth.login_session_manager import LoginSessionManager
from app.services.auth.mfa_coordinator import MfaCoordinator
from app.services.auth.redis_session import RedisSessionService
from app.services.auth_service import AuthService
from app.services.geolocation import GeolocationService
from app.services.session_service import SessionService
from app.services.user.profile_service import UserProfileService


class AuthProvider(Provider):
    @provide(scope=Scope.REQUEST)
    def auth_repository(self, db: AsyncDatabaseSession) -> AuthRepository:
        return AuthRepository(db)

    @provide(scope=Scope.REQUEST)
    def auth_service(
        self,
        audit: AuditService,
        uow: UnitOfWork,
    ) -> AuthService:
        return AuthService(
            audit=audit,
            auth_repo=uow.auth,
            user_repo=uow.users,
            session_repo=uow.sessions,
            uow=uow,
        )

    @provide(scope=Scope.REQUEST)
    def lockout_service(self, db: AsyncDatabaseSession) -> LockoutService:
        return LockoutService(db=db)

    @provide(scope=Scope.REQUEST)
    def login_session_manager(
        self,
        session_service: SessionService,
        redis_session: RedisSessionService,
        geolocation_service: GeolocationService,
        audit: AuditService,
    ) -> LoginSessionManager:
        from app.services.auth.login_session_manager import (
            LoginSessionManager as _LSM,
        )

        return _LSM(
            session_service=session_service,
            redis_session_service=redis_session,
            geolocation_service=geolocation_service,
            audit=audit,
        )

    @provide(scope=Scope.REQUEST)
    def credential_validator(
        self,
        uow: UnitOfWork,
        user_repo: UserRepository,
        profile_service: UserProfileService,
        lockout_service: LockoutService,
        audit: AuditService,
        session_manager: LoginSessionManager,
    ) -> CredentialValidator:
        from app.services.auth.credential_validator import (
            CredentialValidator as _CV,
        )

        return _CV(
            uow=uow,
            user_repo=user_repo,
            profile_service=profile_service,
            lockout_service=lockout_service,
            audit=audit,
            session_manager=session_manager,
        )

    @provide(scope=Scope.REQUEST)
    def mfa_coordinator(
        self,
        uow: UnitOfWork,
        auth_repo: AuthRepository,
    ) -> MfaCoordinator:
        from app.services.auth.mfa_coordinator import MfaCoordinator as _MC

        return _MC(
            uow=uow,
            auth_repo=auth_repo,
        )

    @provide(scope=Scope.REQUEST)
    def login_service(
        self,
        db: AsyncDatabaseSession,
        validator: CredentialValidator,
        mfa_coord: MfaCoordinator,
        session_manager: LoginSessionManager,
    ) -> LoginService:
        return LoginService(
            validator=validator,
            mfa_coord=mfa_coord,
            session_manager=session_manager,
            db_session=db,
        )
