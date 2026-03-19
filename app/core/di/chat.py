"""Dishka DI providers for the chat domain.

TD-W9-01/05 (audit 2026-03-16):
- ChatCreationService registered as its own provider (extracted from ChatCommandService).
- ChatService wrapper removed — endpoints inject narrow services directly.
"""

from __future__ import annotations

from dishka import Provider, Scope, provide

from app.core.protocols import AsyncDatabaseSession
from app.deps.cache import BaseCache
from app.repositories.chat_repository import ChatRepository
from app.repositories.unit_of_work import UnitOfWork
from app.services.chat.attachment_service import ChatAttachmentService
from app.services.chat.command_service import (
    ChatMaintenanceService,
    ChatMessageDispatcher,
)
from app.services.chat.creation_service import ChatCreationService
from app.services.chat.notification_service import (
    ChatNotificationService as ChatWSNotificationService,
)
from app.services.chat.query_service import ChatQueryService


class ChatProvider(Provider):
    @provide(scope=Scope.REQUEST)
    def chat_repository(self, db: AsyncDatabaseSession) -> ChatRepository:
        return ChatRepository(db)

    @provide(scope=Scope.REQUEST)
    def chat_attachment_service(self) -> ChatAttachmentService:
        return ChatAttachmentService()

    @provide(scope=Scope.REQUEST)
    def chat_ws_notification_service(
        self, db: AsyncDatabaseSession
    ) -> ChatWSNotificationService:
        return ChatWSNotificationService(session=db)

    @provide(scope=Scope.REQUEST)
    def chat_query_service(self, uow: UnitOfWork) -> ChatQueryService:
        return ChatQueryService(session=uow.session, repository=uow.chats)

    @provide(scope=Scope.REQUEST)
    def chat_message_dispatcher(
        self,
        uow: UnitOfWork,
        attachments: ChatAttachmentService,
        notifications: ChatWSNotificationService,
    ) -> ChatMessageDispatcher:
        return ChatMessageDispatcher(
            uow=uow,
            attachment_service=attachments,
            notification_service=notifications,
        )

    @provide(scope=Scope.REQUEST)
    def chat_maintenance_service(
        self,
        uow: UnitOfWork,
        attachments: ChatAttachmentService,
    ) -> ChatMaintenanceService:
        return ChatMaintenanceService(
            uow=uow,
            attachment_service=attachments,
        )

    @provide(scope=Scope.REQUEST)
    def chat_creation_service(
        self,
        uow: UnitOfWork,
        db: AsyncDatabaseSession,
        cache: BaseCache,
    ) -> ChatCreationService:
        # TD-W9-01: ChatCreationService owns DM dedup + Redis lock + presence.
        # TD-W10-01: cache injected via DI (DIP compliance).
        return ChatCreationService(uow=uow, session=db, cache=cache)
