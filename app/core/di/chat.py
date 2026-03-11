from __future__ import annotations

from dishka import Provider, Scope, provide

from app.core.protocols import AsyncDatabaseSession
from app.repositories.chat_repository import ChatRepository
from app.repositories.unit_of_work import UnitOfWork
from app.services.chat.attachment_service import ChatAttachmentService
from app.services.chat.command_service import ChatCommandService
from app.services.chat.notification_service import (
    ChatNotificationService as ChatWSNotificationService,
)
from app.services.chat.query_service import ChatQueryService
from app.services.chat_service import ChatService


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
    def chat_command_service(
        self,
        uow: UnitOfWork,
        attachments: ChatAttachmentService,
        notifications: ChatWSNotificationService,
    ) -> ChatCommandService:
        return ChatCommandService(
            uow=uow,
            attachment_service=attachments,
            notification_service=notifications,
        )

    @provide(scope=Scope.REQUEST)
    def chat_service(
        self,
        db: AsyncDatabaseSession,
        attachments: ChatAttachmentService,
        notifications: ChatWSNotificationService,
        queries: ChatQueryService,
        commands: ChatCommandService,
    ) -> ChatService:
        return ChatService(
            session=db,
            attachments=attachments,
            notifications=notifications,
            queries=queries,
            commands=commands,
        )
