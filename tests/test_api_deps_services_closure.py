from unittest.mock import MagicMock, patch

from app.api.deps.services import (
    get_chat_maintenance_service,
    get_chat_message_dispatcher,
)


def test_get_chat_message_dispatcher_builds_write_dependencies():
    session = MagicMock()
    uow = MagicMock()
    attachments = MagicMock()
    notifications = MagicMock()
    dispatcher = MagicMock()

    with (
        patch("app.repositories.unit_of_work.uow_from_session", return_value=uow),
        patch(
            "app.services.chat.attachment_service.ChatAttachmentService",
            return_value=attachments,
        ) as attachment_factory,
        patch(
            "app.services.chat.notification_service.ChatNotificationService",
            return_value=notifications,
        ) as notification_factory,
        patch(
            "app.services.chat.command_service.ChatMessageDispatcher",
            return_value=dispatcher,
        ) as dispatcher_factory,
    ):
        result = get_chat_message_dispatcher(session)

    assert result is dispatcher
    attachment_factory.assert_called_once_with()
    notification_factory.assert_called_once_with(session)
    dispatcher_factory.assert_called_once_with(uow, attachments, notifications)


def test_get_chat_maintenance_service_builds_write_dependencies():
    session = MagicMock()
    uow = MagicMock()
    attachments = MagicMock()
    maintenance = MagicMock()

    with (
        patch("app.repositories.unit_of_work.uow_from_session", return_value=uow),
        patch(
            "app.services.chat.attachment_service.ChatAttachmentService",
            return_value=attachments,
        ) as attachment_factory,
        patch(
            "app.services.chat.command_service.ChatMaintenanceService",
            return_value=maintenance,
        ) as maintenance_factory,
    ):
        result = get_chat_maintenance_service(session)

    assert result is maintenance
    attachment_factory.assert_called_once_with()
    maintenance_factory.assert_called_once_with(uow, attachments)
