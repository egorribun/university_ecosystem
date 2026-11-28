from datetime import UTC, datetime
from unittest.mock import patch
from uuid import uuid4

from app.api import notifications


def test_notification_validation_warning_omits_record_data() -> None:
    notification_id = uuid4()
    stored_body = {"unexpected": "private notification text"}
    row = {
        "id": notification_id,
        "title": "Notification",
        "body": "Plain text",
        "body_en": stored_body,
        "created_at": datetime(2026, 1, 1, tzinfo=UTC),
    }

    with patch.object(notifications.logger, "warning") as warning:
        result = notifications._serialize_notification(row, locale="ru")

    assert result.id == notification_id
    assert result.__dict__["body_en"] is stored_body
    warning.assert_called_once_with(
        "Failed to validate notification payload",
        error_type="ValidationError",
        error_count=1,
    )
