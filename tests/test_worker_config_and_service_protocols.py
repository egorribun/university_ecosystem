"""Coverage and fail-closed behavior for small service-layer contracts."""

from __future__ import annotations

import uuid

import pytest
from pydantic import ValidationError

from app.core.config.workers import OutboxWorkerSettings, outbox_worker_settings
from app.services.protocols import (
    IChatCommandService,
    IChatCreationService,
    IChatQueryService,
)


def test_outbox_worker_settings_defaults_and_explicit_values() -> None:
    assert outbox_worker_settings.outbox_batch_size == 50
    assert outbox_worker_settings.outbox_poll_interval == 1.0
    assert outbox_worker_settings.outbox_max_retries == 5
    assert outbox_worker_settings.outbox_retry_backoff_base == 2.0
    assert outbox_worker_settings.outbox_dead_letter_after == 10

    configured = OutboxWorkerSettings(
        outbox_batch_size=100,
        outbox_poll_interval=5.0,
        outbox_max_retries=8,
        outbox_retry_backoff_base=3.0,
        outbox_dead_letter_after=12,
    )
    assert configured.model_dump() == {
        "outbox_batch_size": 100,
        "outbox_poll_interval": 5.0,
        "outbox_max_retries": 8,
        "outbox_retry_backoff_base": 3.0,
        "outbox_dead_letter_after": 12,
    }


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("outbox_batch_size", 0),
        ("outbox_batch_size", 501),
        ("outbox_poll_interval", 0.09),
        ("outbox_poll_interval", 60.1),
        ("outbox_max_retries", 0),
        ("outbox_max_retries", 21),
        ("outbox_retry_backoff_base", 1.0),
        ("outbox_retry_backoff_base", 10.1),
        ("outbox_dead_letter_after", 0),
    ],
)
def test_outbox_worker_settings_rejects_out_of_range_values(
    field: str,
    value: int | float,
) -> None:
    with pytest.raises(ValidationError):
        OutboxWorkerSettings(**{field: value})


@pytest.mark.asyncio
async def test_service_protocol_methods_fail_closed_when_called_directly() -> None:
    owner = object()

    with pytest.raises(NotImplementedError, match="create_chat"):
        await IChatCreationService.create_chat(owner, owner, uuid.uuid4(), "en")

    with pytest.raises(NotImplementedError, match="get_chats"):
        await IChatQueryService.get_chats(owner, owner, None, 20)
    with pytest.raises(NotImplementedError, match="get_chat_details"):
        await IChatQueryService.get_chat_details(owner, uuid.uuid4(), owner, "en")
    with pytest.raises(NotImplementedError, match="get_messages"):
        await IChatQueryService.get_messages(owner, uuid.uuid4(), owner, None, 20, "en")

    with pytest.raises(NotImplementedError, match="send_message"):
        await IChatCommandService.send_message(
            owner,
            uuid.uuid4(),
            owner,
            "message",
            [],
            "en",
        )
    with pytest.raises(NotImplementedError, match="mark_read"):
        await IChatCommandService.mark_read(owner, uuid.uuid4(), owner, "en")
    with pytest.raises(NotImplementedError, match="clear_history"):
        await IChatCommandService.clear_history(owner, uuid.uuid4(), owner, "en")
    with pytest.raises(NotImplementedError, match="delete_chat"):
        await IChatCommandService.delete_chat(owner, uuid.uuid4(), owner, "en")
