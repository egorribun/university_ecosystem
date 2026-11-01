from __future__ import annotations

import hashlib
import json
import logging
import uuid
from datetime import UTC, datetime, timedelta
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
_LINK_MARKER = "synthetic-" + uuid.uuid4().hex


class _Result:
    """Minimal result for both the row lookup and the compare-and-set write."""

    def __init__(self, row: DeadLetterJob | None, rowcount: int) -> None:
        self._row = row
        self.rowcount = rowcount

    def one_or_none(self) -> DeadLetterJob | None:
        return self._row

    def scalar_one_or_none(self) -> DeadLetterJob | None:
        return self._row


class _RecordingSession:
    """Record the statements a quarantine would send, without touching a database."""

    def __init__(
        self,
        *,
        fail_writes: bool = False,
        update_rowcount: int = 1,
        accept_adds: bool = False,
    ) -> None:
        self.statements: list[Any] = []
        self.fail_writes = fail_writes
        self.update_rowcount = update_rowcount
        self.accept_adds = accept_adds
        self.added: list[Any] = []
        self.row: DeadLetterJob | None = None

    async def __aenter__(self) -> _RecordingSession:
        return self

    async def __aexit__(self, *_args: object) -> None:
        return None

    async def execute(self, statement: Any) -> _Result:
        self.statements.append(statement)
        if isinstance(statement, Update):
            if self.fail_writes:
                raise OSError("synthetic storage outage")
            return _Result(None, self.update_rowcount)
        # The row lookup (quarantine read or dedup lookup) returns the stored row.
        return _Result(self.row, 0)

    def add(self, job: Any) -> None:
        if not self.accept_adds:
            raise AssertionError("a retained duplicate must not insert a second row")
        self.added.append(job)

    async def flush(self) -> None:
        return None

    async def commit(self) -> None:
        return None


def _retained_row(
    payload: str, *, job_hash: str = "f" * 64, **extra: Any
) -> DeadLetterJob:
    return DeadLetterJob(
        id=extra.pop("id", 450),
        job_type=extra.pop("job_type", _AUTH_TASK),
        job_hash=job_hash,
        payload=payload,
        status="pending",
        retry_count=1,
        max_retries=4,
        **extra,
    )


def _update_params(session: _RecordingSession) -> dict[str, Any]:
    (statement,) = [s for s in session.statements if isinstance(s, Update)]
    return dict(statement.compile().params)


@pytest.mark.asyncio
async def test_aud447_quarantine_replaces_only_the_bytes_it_judged_unprotectable() -> (
    None
):
    malformed = json.dumps({"args": ["x@example.test", "#token=" + _LINK_MARKER]})[:-1]
    session = _RecordingSession()
    session.row = _retained_row(malformed)

    assert await DeadLetterQueue(session).quarantine_auth_payload("f" * 64) is True

    params = _update_params(session)
    assert params["payload"] == _QUARANTINED_AUTH_PAYLOAD
    assert params["job_hash_1"] == "f" * 64
    # Compare-and-set: only the exact bytes that were read are replaced.
    assert params["payload_1"] == malformed
    # Identity, status and retry budget are not part of the replacement; the
    # model's onupdate timestamp is the only other column the statement sets.
    assert set(params) == {"payload", "updated_at", "job_hash_1", "payload_1"}


@pytest.mark.asyncio
async def test_aud447_quarantine_declines_when_the_row_is_absent_or_not_auth() -> None:
    session = _RecordingSession()
    assert await DeadLetterQueue(session).quarantine_auth_payload("e" * 64) is False

    session.row = _retained_row("not json", job_type="app.tasks.other")
    assert await DeadLetterQueue(session).quarantine_auth_payload("f" * 64) is False
    assert not [s for s in session.statements if isinstance(s, Update)]


@pytest.mark.asyncio
async def test_aud447_quarantine_declines_a_row_that_is_protectable_now(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(auth_module, "_token_hmac_secret", lambda: uuid.uuid4().hex)
    incoming = {
        "args": [
            "student@example.test",
            f"https://portal.example.test/x#token={_LINK_MARKER}",
        ],
        "kwargs": {},
    }
    job_hash = hashlib.sha256(
        json.dumps({"type": _AUTH_TASK, "payload": incoming}, sort_keys=True).encode()
    ).hexdigest()
    session = _RecordingSession()
    # A repair committed by someone else: valid, plaintext, protectable bytes.
    session.row = _retained_row(json.dumps(incoming), job_hash=job_hash)

    assert await DeadLetterQueue(session).quarantine_auth_payload(job_hash) is False

    assert not [s for s in session.statements if isinstance(s, Update)]


@pytest.mark.asyncio
async def test_aud447_quarantine_reports_a_lost_compare_and_set() -> None:
    malformed = json.dumps({"args": ["x"]})[:-1]
    session = _RecordingSession(update_rowcount=0)
    session.row = _retained_row(malformed)

    assert await DeadLetterQueue(session).quarantine_auth_payload("f" * 64) is False


@pytest.mark.asyncio
async def test_aud447_quarantine_scrubs_the_error_field_in_the_same_statement() -> None:
    malformed = json.dumps({"args": ["x"]})[:-1]
    session = _RecordingSession()
    session.row = _retained_row(
        malformed,
        error_message=f"smtp refused https://portal.example.test/x#token={_LINK_MARKER}",
    )

    assert await DeadLetterQueue(session).quarantine_auth_payload("f" * 64) is True

    params = _update_params(session)
    assert params["error_message"] == _QUARANTINED_AUTH_PAYLOAD
    assert _LINK_MARKER not in json.dumps(params, default=str)


@pytest.mark.asyncio
async def test_aud447_quarantine_keeps_an_error_field_without_a_link() -> None:
    malformed = json.dumps({"args": ["x"]})[:-1]
    session = _RecordingSession()
    session.row = _retained_row(malformed, error_message="SMTP timeout after 30s")

    assert await DeadLetterQueue(session).quarantine_auth_payload("f" * 64) is True

    assert "error_message" not in _update_params(session)


@pytest.mark.asyncio
async def test_aud447_add_failed_job_stores_scrubbed_error_text() -> None:
    session = _RecordingSession(accept_adds=True)

    job = await DeadLetterQueue(session).add_failed_job(
        job_type="app.tasks.other",
        payload={"args": []},
        error_message=f"upstream echoed https://portal.example.test/x#token={_LINK_MARKER}",
    )

    assert job is not None
    assert job.error_message == _QUARANTINED_AUTH_PAYLOAD
    assert _LINK_MARKER not in repr(job.__dict__)


@pytest.mark.asyncio
async def test_aud447_add_failed_job_keeps_ordinary_error_text() -> None:
    session = _RecordingSession(accept_adds=True)

    job = await DeadLetterQueue(session).add_failed_job(
        job_type="app.tasks.other",
        payload={"args": []},
        error_message="SMTP timeout after 30s",
    )

    assert job is not None
    assert job.error_message == "SMTP timeout after 30s"


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


def test_aud447_protection_helper_refuses_other_job_types_and_non_object_payloads() -> (
    None
):
    from app.workers.dead_letter_queue import _protected_auth_payload_bytes

    assert _protected_auth_payload_bytes("app.tasks.other", "h" * 64, "{}") is None
    assert _protected_auth_payload_bytes(_AUTH_TASK, "h" * 64, "[]") is None


def test_aud447_protecting_bytes_that_are_already_protected_leaves_the_row_unchanged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app.workers.dead_letter_queue as dlq_module

    already_protected = json.dumps({"args": ["x"], "kwargs": {"encrypted_link": True}})
    monkeypatch.setattr(
        dlq_module,
        "_protected_auth_payload_bytes",
        lambda _job_type, _job_hash, stored: stored,
    )
    job = _retained_row(already_protected)

    _protect_retained_auth_payload(job)

    assert job.payload == already_protected
