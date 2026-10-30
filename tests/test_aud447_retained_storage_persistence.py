from __future__ import annotations

import asyncio
import hashlib
import json
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import app.core.database as database_module
import app.core.nats_broker as nats_module
import app.services.auth_service as auth_module
import app.tasks.email as email_tasks
from app.models.dead_letter import DeadLetterJob
from app.workers.dead_letter_queue import DeadLetterQueue

_AUTH_TASK = "app.tasks.email.send_auth_email"


@pytest_asyncio.fixture
async def retained_auth_sessions() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", hide_parameters=True)
    try:
        async with engine.begin() as connection:
            await connection.run_sync(DeadLetterJob.__table__.create)
        yield async_sessionmaker(engine, expire_on_commit=False)
    finally:
        await engine.dispose()


async def _stored_row(sessions: async_sessionmaker[AsyncSession]) -> dict[str, Any]:
    # Use a new session and Core columns, not the writer's identity-map object.
    async with sessions() as session:
        rows = (await session.execute(select(DeadLetterJob.__table__))).mappings().all()
    assert len(rows) == 1
    return dict(rows[0])


def _message() -> SimpleNamespace:
    return SimpleNamespace(
        metadata=SimpleNamespace(num_delivered=nats_module._MAX_DELIVERIES),
        term=AsyncMock(),
        ack=AsyncMock(),
        nak=AsyncMock(),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("boundary", ["dedup", "replay"])
@pytest.mark.parametrize(
    "bad_case", ["malformed_json", "duplicate_keys", "hash_mismatch"]
)
async def test_aud447_invalid_retained_auth_rows_do_not_keep_plaintext_after_uow(
    monkeypatch: pytest.MonkeyPatch,
    retained_auth_sessions: async_sessionmaker[AsyncSession],
    boundary: str,
    bad_case: str,
) -> None:
    marker = "synthetic-" + uuid.uuid4().hex
    other_marker = "synthetic-" + uuid.uuid4().hex
    link = f"https://portal.example.test/reset-password#token={marker}"
    secret = uuid.uuid4().hex
    monkeypatch.setattr(auth_module, "_token_hmac_secret", lambda: secret)
    monkeypatch.setattr(database_module, "async_session", retained_auth_sessions)
    monkeypatch.setattr(DeadLetterQueue, "_replay_lock", asyncio.Lock())

    incoming = {"args": ["student@example.test", link], "kwargs": {}}
    input_before = json.dumps(incoming, sort_keys=True)
    expected_hash = hashlib.sha256(
        json.dumps({"type": _AUTH_TASK, "payload": incoming}, sort_keys=True).encode()
    ).hexdigest()
    task = nats_module._NatsTaskPayload.model_validate(
        {"id": str(uuid.uuid4()), "name": _AUTH_TASK, **json.loads(input_before)}
    )
    task_before = json.dumps(task.model_dump(), sort_keys=True)
    due_at = datetime.now(UTC) - timedelta(minutes=1)
    created_at = datetime(2026, 1, 1, tzinfo=UTC)
    async with retained_auth_sessions() as session:
        session.add(
            DeadLetterJob(
                job_type=_AUTH_TASK,
                job_hash=expected_hash,
                payload=json.dumps(incoming),
                error_message="Historical delivery failure",
                status="pending",
                retry_count=1,
                max_retries=4,
                next_retry_at=due_at,
                created_at=created_at,
                updated_at=created_at,
            )
        )
        await session.commit()
    original = await _stored_row(retained_auth_sessions)
    seeded_plaintext = marker in original["payload"]
    assert seeded_plaintext

    broker = nats_module.NatsTaskBroker()
    transport = AsyncMock()
    monkeypatch.setattr(broker, "_js", transport)
    monkeypatch.setattr(
        broker,
        "connect",
        AsyncMock(side_effect=AssertionError("unexpected broker connection")),
    )
    delivered: list[bool] = []

    async def capture_delivery(**kwargs: Any) -> None:
        delivered.append(
            kwargs["to_email"] == "student@example.test"
            and kwargs["fallback_fields"]["link"] == link
        )

    monkeypatch.setattr(email_tasks, "_deliver_email_message", capture_delivery)

    async def apply_boundary(message: SimpleNamespace) -> tuple[int, int] | None:
        if boundary == "dedup":
            # The real broker opens its own session and owns commit/rollback.
            await broker._retry_or_dead_letter(
                message, task, "Authentication email delivery failed"
            )
            return None
        async with retained_auth_sessions() as session:
            result = await DeadLetterQueue(session).auto_replay_jobs(
                broker.replay_dead_letter,
                batch_size=1,
                max_batches=1,
                rate_limit_delay=0,
                base_backoff_seconds=1,
                max_backoff_seconds=8,
                jitter=0,
            )
            # The caller, not DeadLetterQueue, owns this transaction boundary.
            await session.commit()
        return result

    # First prove the same real boundary can persist protection of a valid
    # legacy row and still deliver its exact link through replay and the handler.
    healthy_message = _message()
    healthy_result = await apply_boundary(healthy_message)
    protected_row = await _stored_row(retained_auth_sessions)
    protected_storage = marker not in protected_row["payload"]
    assert protected_storage, "the valid legacy control did not protect storage"
    stable_identity = (
        protected_row["id"] == original["id"]
        and protected_row["job_type"] == _AUTH_TASK
        and protected_row["job_hash"] == expected_hash
        and protected_row["max_retries"] == 4
        and protected_row["created_at"] == original["created_at"]
        and protected_row["next_retry_at"] == original["next_retry_at"]
    )
    assert stable_identity, "the valid legacy control changed job identity"
    if boundary == "dedup":
        assert healthy_result is None
        healthy_message.term.assert_awaited_once_with()
        healthy_message.ack.assert_not_awaited()
        healthy_message.nak.assert_not_awaited()
        assert protected_row["status"] == "pending"
        assert protected_row["retry_count"] == 1
        transport.publish.assert_not_awaited()
        await broker.replay_dead_letter(
            _AUTH_TASK, json.loads(protected_row["payload"])
        )
    else:
        assert healthy_result == (1, 0)
        assert protected_row["status"] == "completed"
        assert protected_row["retry_count"] == 2
    transport.publish.assert_awaited_once()
    wire = transport.publish.await_args.args[1]
    safe_wire = marker not in wire.decode()
    assert safe_wire, "the valid legacy control published plaintext"
    replayed = nats_module._NatsTaskPayload.model_validate(json.loads(wire))
    await email_tasks.broker._tasks[_AUTH_TASK](*replayed.args, **replayed.kwargs)
    assert delivered == [True]

    protected_payload = json.loads(protected_row["payload"])
    if bad_case == "malformed_json":
        bad_bytes = json.dumps(incoming)[:-1]
        malformed = False
        try:
            json.loads(bad_bytes)
        except json.JSONDecodeError:
            malformed = True
        assert malformed
    elif bad_case == "duplicate_keys":
        bad_bytes = (
            '{"args": '
            + json.dumps(incoming["args"])
            + ', "args": '
            + json.dumps(protected_payload["args"])
            + ', "kwargs": '
            + json.dumps(protected_payload["kwargs"])
            + "}"
        )
        last_key_control = json.loads(bad_bytes) == protected_payload
        assert last_key_control, "the duplicate-key fixture lost its shadowed field"
    else:
        other_payload = json.loads(input_before)
        other_payload["args"][1] = (
            f"https://portal.example.test/reset-password#token={other_marker}"
        )
        different_hash = hashlib.sha256(
            json.dumps(
                {"type": _AUTH_TASK, "payload": other_payload}, sort_keys=True
            ).encode()
        ).hexdigest()
        assert different_hash != expected_hash
        bad_bytes = json.dumps(other_payload)

    # Seed historical corruption directly; new enqueue already protects links.
    # Reset the row only after the positive boundary and delivery controls pass.
    async with retained_auth_sessions() as session:
        await session.execute(
            update(DeadLetterJob)
            .where(DeadLetterJob.id == original["id"])
            .values(
                payload=bad_bytes,
                error_message="Historical delivery failure",
                status="pending",
                retry_count=1,
                max_retries=4,
                next_retry_at=due_at,
                updated_at=created_at,
            )
        )
        await session.commit()
    before = await _stored_row(retained_auth_sessions)
    seeded_invalid_bytes = before["payload"] == bad_bytes
    has_plaintext = any(value in before["payload"] for value in (marker, other_marker))
    assert seeded_invalid_bytes and has_plaintext

    transport.reset_mock()
    delivered.clear()
    rejected_message = _message()
    outcome = await apply_boundary(rejected_message)

    transport.publish.assert_not_awaited()
    rejected_message.term.assert_not_awaited()
    rejected_message.ack.assert_not_awaited()
    assert delivered == []
    after = await _stored_row(retained_auth_sessions)
    preserved = all(
        after[field] == before[field]
        for field in ("id", "job_type", "job_hash", "max_retries", "created_at")
    )
    assert preserved, "rejection changed persisted job identity or retry budget"
    assert after["status"] == "pending"
    if boundary == "dedup":
        assert outcome is None
        rejected_message.nak.assert_awaited_once()
        expected_delay = min(
            nats_module._RETRY_BASE_DELAY_S * 2 ** (nats_module._MAX_DELIVERIES - 1),
            nats_module._RETRY_MAX_DELAY_S,
        )
        rejected_message.nak.assert_awaited_once_with(delay=expected_delay)
        assert after["retry_count"] == before["retry_count"] == 1
        assert after["next_retry_at"] == before["next_retry_at"]
    else:
        assert outcome == (0, 1)
        rejected_message.nak.assert_not_awaited()
        assert after["retry_count"] == 2
        assert after["next_retry_at"] > before["next_retry_at"]
    input_unchanged = (
        json.dumps(incoming, sort_keys=True) == input_before
        and json.dumps(task.model_dump(), sort_keys=True) == task_before
    )
    assert input_unchanged, "retention handling changed the incoming task"
    safe_error = all(
        value not in str(after["error_message"]) for value in (marker, other_marker)
    )
    assert safe_error, "rejection persisted a synthetic marker in error details"

    # This final assertion is the expected semantic RED on current source.
    # Opaque errors, no publication and an in-memory repair are not storage proof.
    persisted_private = all(
        value not in after["payload"] for value in (marker, other_marker)
    )
    assert persisted_private, "committed auth DLQ storage retained plaintext"
