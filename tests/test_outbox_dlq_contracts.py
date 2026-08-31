"""Focused contracts for terminal outbox event handling."""

from __future__ import annotations

from datetime import UTC
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.workers import outbox


@pytest.mark.asyncio
async def test_dlq_records_utc_failure_time_for_non_mfa_events() -> None:
    """DLQ timestamps remain timezone-aware instead of silently becoming local."""

    event = SimpleNamespace(
        id=uuid4(),
        event_type="system.release",
        aggregate_type="Release",
        aggregate_id="release-1",
        payload={"version": "1.0.0"},
        error_count=5,
        processed_at=None,
    )
    db = MagicMock()

    await outbox.OutboxWorker(max_retries=5)._move_to_dlq(
        db, event, "RuntimeError: publication failed"
    )

    failed = db.add.call_args.args[0]
    assert failed.payload == {"version": "1.0.0"}
    assert failed.failed_at.tzinfo is UTC
    assert event.processed_at.tzinfo is UTC


@pytest.mark.asyncio
async def test_invalid_mfa_dlq_payload_logs_stable_event_id_field() -> None:
    """Malformed terminal MFA events are auditable without changing log keys."""

    event = SimpleNamespace(
        id=uuid4(),
        event_type="auth.mfa_email.requested",
        payload={"delivery_id": "not-a-uuid"},
        error_count=5,
        processed_at=None,
    )
    db = MagicMock()

    with patch.object(outbox.logger, "error") as log_error:
        with pytest.raises(RuntimeError, match="invalid MFA delivery id"):
            await outbox.OutboxWorker(max_retries=5)._move_to_dlq(
                db, event, "MfaDeliveryError: delivery failed"
            )

    log_error.assert_called_once_with(
        "OutboxWorker: terminal MFA event has invalid delivery id",
        extra={"event_id": str(event.id)},
    )


@pytest.mark.asyncio
async def test_terminal_mfa_dlq_clears_the_delivery_lease() -> None:
    delivery_id = uuid4()
    event = SimpleNamespace(
        id=uuid4(),
        event_type="auth.mfa_email.requested",
        aggregate_type="MfaChallenge",
        aggregate_id=str(uuid4()),
        payload={"delivery_id": str(delivery_id)},
        error_count=5,
        processed_at=None,
    )
    db = MagicMock()
    db.execute = AsyncMock()

    await outbox.OutboxWorker(max_retries=5)._move_to_dlq(
        db, event, "MfaDeliveryError: delivery failed"
    )

    statement = db.execute.await_args.args[0]
    params = statement.compile().params
    assert params["status"] == "cancelled"
    assert params["lease_token"] is None
    assert params["lease_expires_at"] is None
    status_sets = {
        tuple(value) for value in params.values() if isinstance(value, (list, tuple))
    }
    assert ("pending", "sending") in status_sets
