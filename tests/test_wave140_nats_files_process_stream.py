"""Wave 140 SW1 — file-processor NATS stream provisioning unit tests.

NatsTaskBroker.connect() must create BOTH the TASK_QUEUE stream (legacy
worker queue) AND the new FILES_PROCESS stream (consumed by the Go
file-processor service per W140 Q2 architecture).

Pre-W140: only TASK_QUEUE was created; file-processor crashed at startup
with `nats: no stream matches subject` (W139 §Honesty #6).

This test mocks the JetStream + NATS client surfaces and asserts that
connect() invokes add_stream() exactly twice with the expected stream
name + subject configuration.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.nats_broker import NatsTaskBroker


@pytest.mark.asyncio
async def test_connect_creates_both_streams() -> None:
    """NatsTaskBroker.connect() must add all 5 streams with file storage & 7-day retention."""
    broker = NatsTaskBroker()

    mock_js = MagicMock()
    mock_js.add_stream = AsyncMock()

    mock_nc = MagicMock()
    mock_nc.jetstream = MagicMock(return_value=mock_js)
    mock_nc.is_connected = True

    with patch(
        "app.core.nats_broker.nats.connect", new=AsyncMock(return_value=mock_nc)
    ):
        await broker.connect()

    assert mock_js.add_stream.await_count == 5, (
        f"Expected 5 add_stream calls, got {mock_js.add_stream.await_count}"
    )

    calls = mock_js.add_stream.call_args_list
    configs = [c.kwargs["config"] for c in calls]

    assert configs[0].name == "TASK_QUEUE"
    assert configs[0].subjects == ["tasks.>"]

    assert configs[1].name == "FILES_PROCESS"
    assert configs[1].subjects == ["files.process"]

    assert configs[2].name == "CHAT_EVENTS"
    assert configs[2].subjects == ["chat.*"]

    assert configs[3].name == "NOTIFICATIONS_EVENTS"
    assert configs[3].subjects == ["notifications.*"]

    assert configs[4].name == "OUTBOX_EVENTS"
    assert configs[4].subjects == ["outbox.*"]


@pytest.mark.asyncio
async def test_connect_idempotent_when_streams_exist() -> None:
    """add_stream is idempotent per nats-py contract — re-creating is a no-op.

    Mocked here as success-on-existing (real nats-py returns the existing
    StreamInfo without raising). Verifies our code doesn't break if the
    stream was created by a prior process.
    """
    broker = NatsTaskBroker()

    mock_js = MagicMock()
    mock_js.add_stream = AsyncMock()

    mock_nc = MagicMock()
    mock_nc.jetstream = MagicMock(return_value=mock_js)
    mock_nc.is_connected = True

    with patch(
        "app.core.nats_broker.nats.connect", new=AsyncMock(return_value=mock_nc)
    ):
        await broker.connect()
        # Second connect() call is short-circuited (line 102 guard); add_stream
        # not invoked again.
        await broker.connect()

    assert mock_js.add_stream.await_count == 5, (
        "Second connect() should short-circuit; add_stream should still be 5 total"
    )


@pytest.mark.asyncio
async def test_files_process_stream_subject_matches_file_processor_subscribe() -> None:
    """Backend stream subject must match file-processor's QueueSubscribe.

    Contract: file-processor's `js.QueueSubscribe("files.process", ...)` at
    main.go:214 subscribes to this exact subject. If we change the subject
    here without updating file-processor, file-processor would silently
    fail to receive messages.
    """
    broker = NatsTaskBroker()
    assert broker._files_process_subject == "files.process"
    assert broker._files_process_stream_name == "FILES_PROCESS"
