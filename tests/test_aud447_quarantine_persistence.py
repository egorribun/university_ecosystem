from __future__ import annotations

import hashlib
import json
import logging
import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any

import pytest
from sqlalchemy import Update

import app.core.database as database_module
import app.core.nats_broker as nats_module
import app.services.auth_service as auth_module
import app.tasks.email as email_tasks
from app.models.dead_letter import DeadLetterJob
from app.workers.dead_letter_queue import (
    _QUARANTINED_AUTH_PAYLOAD,
    DeadLetterQueue,
    _protect_retained_auth_payload,
)

_AUTH_TASK = "app.tasks.email.send_auth_email"


class _RecordingSession:
    """Record the statements a quarantine would send, without touching a database."""

    def __init__(self, *, fail_writes: bool = False) -> None:
        self.statements: list[Any] = []
        self.fail_writes = fail_writes
        self.row: DeadLetterJob | None = None

    async def __aenter__(self) -> _RecordingSession:
        return self

    async def __aexit__(self, *_args: object) -> None:
        return None

    async def execute(self, statement: Any) -> SimpleNamespace:
        self.statements.append(statement)
        if isinstance(statement, Update) and self.fail_writes:
            raise OSError("synthetic storage outage")
        # Return the malformed retained row for the dedup lookup SELECT only.
        return SimpleNamespace(scalar_one_or_none=lambda: self.row)

    def add(self, job: Any) -> None:
        raise AssertionError("a retained duplicate must not insert a second row")

    async def flush(self) -> None:
        return None

    async def commit(self) -> None:
        return None


@pytest.mark.asyncio
async def test_aud447_quarantine_statement_replaces_only_the_stored_bytes() -> None:
    session = _RecordingSession()

    await DeadLetterQueue(session).quarantine_auth_payload("f" * 64)

    (statement,) = session.statements
    assert isinstance(statement, Update)
    params = statement.compile().params
    assert params["payload"] == _QUARANTINED_AUTH_PAYLOAD
    assert params["job_hash_1"] == "f" * 64
    # Identity, status and retry budget are not part of the replacement; the
    # model's onupdate timestamp is the only other column the statement sets.
    assert set(params) == {"payload", "updated_at", "job_hash_1"}


def test_aud447_quarantined_payload_fails_closed_as_auth_work(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(auth_module, "_token_hmac_secret", lambda: uuid.uuid4().hex)
    job = DeadLetterJob(
        id=452,
        job_type=_AUTH_TASK,
        job_hash="0" * 64,
        payload=_QUARANTINED_AUTH_PAYLOAD,
        status="pending",
        retry_count=1,
        max_retries=4,
    )

    with pytest.raises(email_tasks.AuthEmailPayloadError):
        _protect_retained_auth_payload(job)


@pytest.mark.asyncio
async def test_aud447_failed_quarantine_write_is_logged_and_naks_without_raising(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    marker = "synthetic-" + uuid.uuid4().hex
    link = f"https://portal.example.test/reset-password#token={marker}"
    secret = uuid.uuid4().hex
    monkeypatch.setattr(auth_module, "_token_hmac_secret", lambda: secret)
    incoming = {"args": ["student@example.test", link], "kwargs": {}}
    job_hash = hashlib.sha256(
        json.dumps({"type": _AUTH_TASK, "payload": incoming}, sort_keys=True).encode()
    ).hexdigest()
    retained = DeadLetterJob(
        id=451,
        job_type=_AUTH_TASK,
        job_hash=job_hash,
        # Malformed on purpose: the retained bytes hold the plaintext link.
        payload=json.dumps(incoming)[:-1],
        error_message="Historical delivery failure",
        status="pending",
        retry_count=1,
        max_retries=4,
        next_retry_at=datetime.now(UTC) - timedelta(minutes=1),
    )
    session = _RecordingSession(fail_writes=True)
    session.row = retained
    monkeypatch.setattr(database_module, "async_session", lambda: session)
    task = nats_module._NatsTaskPayload.model_validate(
        {"id": str(uuid.uuid4()), "name": _AUTH_TASK, **incoming}
    )
    broker = nats_module.NatsTaskBroker()

    with caplog.at_level(logging.ERROR, logger="app.core.nats_broker"):
        saved = await broker._dead_letter(
            task, "Authentication email delivery failed", 5
        )

    # The quarantine failure must not escape the worker loop; the message NAKs.
    assert saved is False
    (statement,) = [s for s in session.statements if isinstance(s, Update)]
    assert statement.compile().params["job_hash_1"] == job_hash
    failure_logs = [
        record
        for record in caplog.records
        if record.name == "app.core.nats_broker" and record.levelno >= logging.ERROR
    ]
    assert any(
        "nats_auth_payload_quarantine_failed" in record.getMessage()
        for record in failure_logs
    )
    logs_safe = all(marker not in repr(record.__dict__) for record in failure_logs)
    assert logs_safe, "quarantine failure logs contained the synthetic marker"
    assert retained.payload == json.dumps(incoming)[:-1]
