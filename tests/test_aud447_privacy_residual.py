"""Private AUD-447 SQLite regressions for the current residual candidate."""

from __future__ import annotations

import json
import secrets
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from urllib.parse import quote

import pytest
import pytest_asyncio
from sqlalchemy import Select, Update, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import app.core.database as database_module
import app.core.nats_broker as nats_broker_module
import app.models.dead_letter as dead_letter_model
import app.services.auth_service as auth_module
import app.tasks.email as email_tasks
import app.workers.dead_letter_queue as dlq_module
from app.models.dead_letter import DeadLetterJob
from app.workers.dead_letter_queue import (
    _QUARANTINED_AUTH_PAYLOAD,
    DeadLetterQuarantineContentionError,
    DeadLetterQueue,
    compute_job_hash,
)

_AUTH_TASK = "app.tasks.email.send_auth_email"
_OTHER_TASK = "app.tasks.other"
_TABLE = DeadLetterJob.__table__
_CONTENTION_MESSAGE = "Auth payload quarantine did not converge after bounded retries"


class _CaptureLogger:
    def __init__(self) -> None:
        self.events: list[tuple[str, tuple[Any, ...]]] = []

    def debug(self, event: str, *args: Any, **_kwargs: Any) -> None:
        self.events.append((event, args))

    def info(self, event: str, *args: Any, **_kwargs: Any) -> None:
        self.events.append((event, args))

    def warning(self, event: str, *args: Any, **_kwargs: Any) -> None:
        self.events.append((event, args))

    def error(self, event: str, *args: Any, **_kwargs: Any) -> None:
        self.events.append((event, args))


def _deeply_encoded_link(marker: str) -> str:
    value = f"https://portal.example.test/reset-password#token={marker}"
    for _ in range(9):
        value = quote(value, safe="")
    return value


@pytest_asyncio.fixture
async def sessions(tmp_path: Path) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    database_path = tmp_path / f"dlq-{secrets.token_hex(8)}.sqlite"
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{database_path.as_posix()}", hide_parameters=True
    )
    try:
        async with engine.begin() as connection:
            await connection.run_sync(_TABLE.create)
        yield async_sessionmaker(engine, expire_on_commit=False)
    finally:
        await engine.dispose()


def test_aud447_worker_source_binding_positive_control() -> None:
    project = Path(__file__).resolve().parents[1]
    expected = project / "app" / "workers" / "dead_letter_queue.py"
    expected_nats = project / "app" / "core" / "nats_broker.py"
    assert Path(dlq_module.__file__).resolve() == expected
    assert Path(nats_broker_module.__file__).resolve() == expected_nats
    assert Path(dead_letter_model.__file__).resolve() == (
        project / "app" / "models" / "dead_letter.py"
    )
    assert Path(auth_module.__file__).resolve() == (
        project / "app" / "services" / "auth_service.py"
    )
    assert (
        Path(email_tasks.__file__).resolve() == project / "app" / "tasks" / "email.py"
    )


async def _stored(sessions: async_sessionmaker[AsyncSession]) -> dict[str, Any]:
    async with sessions() as session:
        rows = (await session.execute(select(_TABLE))).mappings().all()
    assert len(rows) == 1
    return dict(rows[0])


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "encoded_link",
    [
        "https://portal.example.test/reset-password&num;token&equals;{marker}",
        "https://portal.example.test/reset-password&quest;token&#x3d;{marker}",
        "https://portal.example.test/reset-password%2523token%253D{marker}",
        r"https://portal.example.test/reset-password\u0023token\u003d{marker}",
    ],
    ids=["html-named", "mixed-html", "double-percent", "json-unicode"],
)
async def test_aud447_escaped_marker_is_redacted_after_persist(
    sessions: async_sessionmaker[AsyncSession], encoded_link: str
) -> None:
    marker = secrets.token_urlsafe(40)
    error = "delivery provider rejected " + encoded_link.format(marker=marker)
    async with sessions() as session:
        job = await DeadLetterQueue(session).add_failed_job(
            job_type=_OTHER_TASK,
            payload={"args": []},
            error_message=error,
        )
        assert job is not None
        await session.commit()

    stored = await _stored(sessions)
    assert stored["error_message"] == _QUARANTINED_AUTH_PAYLOAD
    assert marker not in repr(stored)


@pytest.mark.asyncio
async def test_aud447_decode_budget_exhaustion_quarantines_persisted_non_auth_link(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    marker = secrets.token_urlsafe(40)
    nested_link = _deeply_encoded_link(marker)
    async with sessions() as session:
        job = await DeadLetterQueue(session).add_failed_job(
            job_type=_OTHER_TASK,
            payload={"args": [nested_link]},
            error_message=f"provider detail {nested_link}",
        )
        assert job is not None
        await session.commit()

    stored = await _stored(sessions)
    assert stored["payload"] == _QUARANTINED_AUTH_PAYLOAD
    assert stored["error_message"] == _QUARANTINED_AUTH_PAYLOAD
    assert marker not in repr(stored)


@pytest.mark.asyncio
async def test_aud447_auth_link_key_mismatch_quarantines_error_token(
    monkeypatch: pytest.MonkeyPatch,
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    prepared_secret = secrets.token_hex(32)
    rotated_secret = secrets.token_hex(32)
    secret_calls = 0

    def rotating_secret() -> str:
        nonlocal secret_calls
        secret_calls += 1
        return prepared_secret if secret_calls == 1 else rotated_secret

    monkeypatch.setattr(auth_module, "_token_hmac_secret", rotating_secret)
    marker = secrets.token_urlsafe(40)
    payload = {
        "args": ["student@example.test", _deeply_encoded_link(marker)],
        "kwargs": {},
    }
    async with sessions() as session:
        job = await DeadLetterQueue(session).add_failed_job(
            job_type=_AUTH_TASK,
            payload=payload,
            error_message=f"provider echoed token {marker}",
        )
        assert job is not None
        await session.commit()

    stored = await _stored(sessions)
    assert stored["error_message"] == _QUARANTINED_AUTH_PAYLOAD
    assert marker not in repr(stored)


@pytest.mark.asyncio
async def test_aud447_decode_budget_exhaustion_scrubs_auth_error_token(
    monkeypatch: pytest.MonkeyPatch,
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    runtime_secret = secrets.token_hex(32)
    monkeypatch.setattr(auth_module, "_token_hmac_secret", lambda: runtime_secret)
    marker = secrets.token_urlsafe(40)
    nested_link = _deeply_encoded_link(marker)
    assert dlq_module._decode_token_link_text(nested_link) is None
    payload = {
        "args": ["student@example.test", nested_link],
        "kwargs": {},
    }
    async with sessions() as session:
        job = await DeadLetterQueue(session).add_failed_job(
            job_type=_AUTH_TASK,
            payload=payload,
            error_message=f"provider echoed token {marker}",
        )
        assert job is not None
        await session.commit()

    stored = await _stored(sessions)
    assert stored["error_message"] == _QUARANTINED_AUTH_PAYLOAD
    assert marker not in repr(stored)


@pytest.mark.asyncio
async def test_aud447_forged_encrypted_marker_cannot_create_a_dlq_row(
    monkeypatch: pytest.MonkeyPatch,
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    from app.tasks.email import AuthEmailPayloadError

    monkeypatch.setattr(
        auth_module, "_token_hmac_secret", lambda: secrets.token_hex(32)
    )
    marker = secrets.token_urlsafe(40)
    payload = {
        "args": [
            "student@example.test",
            f"https://portal.example.test/reset-password#token={marker}",
        ],
        "kwargs": {"encrypted_link": True},
    }
    async with sessions() as session:
        with pytest.raises(AuthEmailPayloadError):
            await DeadLetterQueue(session).add_failed_job(
                job_type=_AUTH_TASK,
                payload=payload,
                error_message="invalid retained envelope",
            )
        await session.rollback()

    async with sessions() as session:
        rows = (await session.execute(select(_TABLE))).mappings().all()
    assert rows == []


@pytest.mark.asyncio
async def test_aud447_non_link_token_diagnostics_remain_readable(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    error = "token expired; refresh_token=abc is not a reset link"
    async with sessions() as session:
        job = await DeadLetterQueue(session).add_failed_job(
            job_type=_OTHER_TASK,
            payload={"args": []},
            error_message=error,
        )
        assert job is not None
        await session.commit()

    stored = await _stored(sessions)
    assert stored["error_message"] == error


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "bad_shape", ["malformed", "duplicate_key", "forged_marker", "hash_mismatch"]
)
async def test_aud447_quarantine_tombstones_historical_error_with_invalid_auth_bytes(
    monkeypatch: pytest.MonkeyPatch,
    sessions: async_sessionmaker[AsyncSession],
    bad_shape: str,
) -> None:
    marker = secrets.token_urlsafe(40)
    secret = secrets.token_hex(32)
    monkeypatch.setattr(auth_module, "_token_hmac_secret", lambda: secret)
    link = f"https://portal.example.test/reset-password#token={marker}"
    plain = {"args": ["student@example.test", link], "kwargs": {}}
    if bad_shape == "malformed":
        stored_payload = json.dumps(plain)[:-1]
    elif bad_shape == "duplicate_key":
        stored_payload = (
            '{"args": '
            + json.dumps(plain["args"])
            + ', "args": ["student@example.test", "shadowed"], "kwargs": {}}'
        )
    elif bad_shape == "forged_marker":
        stored_payload = json.dumps(
            {"args": plain["args"], "kwargs": {"encrypted_link": True}}
        )
    else:
        stored_payload = json.dumps(plain)

    job_hash = secrets.token_hex(32)
    historical_error = f"historical provider detail {marker}"
    old_schedule = datetime.now(UTC) + timedelta(hours=1)
    async with sessions() as session:
        row = DeadLetterJob(
            job_type=_AUTH_TASK,
            job_hash=job_hash,
            payload=stored_payload,
            error_message=historical_error,
            status="pending",
            retry_count=2,
            max_retries=4,
            next_retry_at=old_schedule,
        )
        session.add(row)
        await session.commit()
        row_id = row.id

    async with sessions() as session:
        assert await DeadLetterQueue(session).quarantine_auth_payload(job_hash) is True
        await session.commit()

    stored = await _stored(sessions)
    assert stored["payload"] == _QUARANTINED_AUTH_PAYLOAD
    assert stored["error_message"] == _QUARANTINED_AUTH_PAYLOAD
    assert marker not in repr(stored)
    assert (stored["id"], stored["job_hash"], stored["status"]) == (
        row_id,
        job_hash,
        "pending",
    )
    assert (stored["retry_count"], stored["max_retries"]) == (2, 4)
    assert stored["next_retry_at"] == old_schedule.replace(tzinfo=None)


@pytest.mark.asyncio
async def test_aud447_quarantine_retries_after_invalid_payload_changes_at_cas(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    marker = secrets.token_urlsafe(40)
    job_hash = secrets.token_hex(32)
    observed_payload = '{"args": ["malformed-before-read"'
    current_payload = '{"args": ["malformed-after-read"'
    current_error = f"historical provider detail {marker}"
    async with sessions() as session:
        row = DeadLetterJob(
            job_type=_AUTH_TASK,
            job_hash=job_hash,
            payload=observed_payload,
            error_message="safe before concurrent write",
            status="pending",
            retry_count=2,
            max_retries=4,
        )
        session.add(row)
        await session.commit()

    async with sessions() as session:
        original_execute = session.execute
        interleaved = False

        async def write_between_read_and_cas(
            statement: Any, *args: Any, **kwargs: Any
        ) -> Any:
            nonlocal interleaved
            result = await original_execute(statement, *args, **kwargs)
            if not interleaved and isinstance(statement, Select):
                interleaved = True
                # End SQLite's read transaction, then commit a distinct writer
                # before the stale compare-and-set is issued.
                await session.commit()
                async with sessions() as concurrent:
                    await concurrent.execute(
                        update(_TABLE)
                        .where(_TABLE.c.job_hash == job_hash)
                        .values(payload=current_payload, error_message=current_error)
                    )
                    await concurrent.commit()
            return result

        session.execute = write_between_read_and_cas  # type: ignore[method-assign]
        replaced = await DeadLetterQueue(session).quarantine_auth_payload(job_hash)
        await session.commit()

    assert interleaved is True
    assert replaced is True
    stored = await _stored(sessions)
    assert stored["payload"] == _QUARANTINED_AUTH_PAYLOAD
    assert stored["error_message"] == _QUARANTINED_AUTH_PAYLOAD
    assert marker not in repr(stored)


@pytest.mark.asyncio
async def test_aud447_quarantine_does_not_overwrite_concurrently_repaired_payload(
    monkeypatch: pytest.MonkeyPatch,
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    secret = secrets.token_hex(32)
    monkeypatch.setattr(auth_module, "_token_hmac_secret", lambda: secret)
    marker = secrets.token_urlsafe(40)
    logical = {
        "args": [
            "student@example.test",
            f"https://portal.example.test/reset-password#token={marker}",
        ],
        "kwargs": {},
    }
    protected, logical_payload = email_tasks.prepare_auth_email_payload(logical)
    job_hash = compute_job_hash(_AUTH_TASK, logical_payload)
    observed_payload = json.dumps(logical)[:-1]
    repaired_payload = json.dumps(protected)
    async with sessions() as session:
        session.add(
            DeadLetterJob(
                job_type=_AUTH_TASK,
                job_hash=job_hash,
                payload=observed_payload,
                error_message="safe repair-race detail",
                status="pending",
                retry_count=1,
                max_retries=4,
            )
        )
        await session.commit()

    async with sessions() as session:
        original_execute = session.execute
        interleaved = False

        async def repair_between_read_and_cas(
            statement: Any, *args: Any, **kwargs: Any
        ) -> Any:
            nonlocal interleaved
            result = await original_execute(statement, *args, **kwargs)
            if not interleaved and isinstance(statement, Select):
                interleaved = True
                await session.commit()
                async with sessions() as concurrent:
                    await concurrent.execute(
                        update(_TABLE)
                        .where(_TABLE.c.job_hash == job_hash)
                        .values(payload=repaired_payload)
                    )
                    await concurrent.commit()
            return result

        session.execute = repair_between_read_and_cas  # type: ignore[method-assign]
        replaced = await DeadLetterQueue(session).quarantine_auth_payload(job_hash)
        await session.commit()

    assert interleaved is True
    assert replaced is False
    stored = await _stored(sessions)
    assert stored["payload"] == repaired_payload
    assert stored["error_message"] == "safe repair-race detail"
    assert marker not in repr(stored)


@pytest.mark.asyncio
async def test_aud447_quarantine_reports_bounded_persistent_invalid_row_contention(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    marker = secrets.token_urlsafe(40)
    job_hash = secrets.token_hex(32)
    initial_payload = '{"args": ["invalid-initial"'
    changed_payloads = [
        '{"args": ["invalid-race-one"',
        '{"args": ["invalid-race-two"',
        '{"args": ["invalid-race-three"',
    ]
    final_error = f"concurrent historical detail {marker}"
    async with sessions() as session:
        session.add(
            DeadLetterJob(
                job_type=_AUTH_TASK,
                job_hash=job_hash,
                payload=initial_payload,
                error_message="safe before concurrent writers",
                status="pending",
                retry_count=1,
                max_retries=4,
            )
        )
        await session.commit()

    async with sessions() as session:
        original_execute = session.execute
        writes = 0
        cas_calls = 0

        async def write_before_each_cas(
            statement: Any, *args: Any, **kwargs: Any
        ) -> Any:
            nonlocal writes, cas_calls
            if isinstance(statement, Update):
                cas_calls += 1
            result = await original_execute(statement, *args, **kwargs)
            if isinstance(statement, Select) and writes < len(changed_payloads):
                await session.commit()
                async with sessions() as concurrent:
                    error = (
                        final_error
                        if writes == len(changed_payloads) - 1
                        else f"interleaved detail {writes} {marker}"
                    )
                    await concurrent.execute(
                        update(_TABLE)
                        .where(_TABLE.c.job_hash == job_hash)
                        .values(payload=changed_payloads[writes], error_message=error)
                    )
                    await concurrent.commit()
                writes += 1
            return result

        session.execute = write_before_each_cas  # type: ignore[method-assign]
        with pytest.raises(DeadLetterQuarantineContentionError) as failure:
            await DeadLetterQueue(session).quarantine_auth_payload(job_hash)
        await session.rollback()

    assert writes == 3
    assert cas_calls == 3
    assert marker not in str(failure.value)
    assert str(failure.value) == _CONTENTION_MESSAGE
    stored = await _stored(sessions)
    assert stored["payload"] == changed_payloads[-1]
    assert stored["error_message"] == final_error


@pytest.mark.asyncio
async def test_aud447_auto_replay_logs_contention_without_raw_row_material(
    monkeypatch: pytest.MonkeyPatch,
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    marker = secrets.token_urlsafe(40)
    job_hash = secrets.token_hex(32)
    raw_payload = (
        '{"args": ["student@example.test", '
        f'"https://portal.example.test/reset-password#token={marker}"'
    )
    async with sessions() as session:
        session.add(
            DeadLetterJob(
                job_type=_AUTH_TASK,
                job_hash=job_hash,
                payload=raw_payload,
                error_message=f"historical detail {marker}",
                status="pending",
                retry_count=0,
                max_retries=3,
                next_retry_at=datetime.now(UTC) - timedelta(seconds=1),
            )
        )
        await session.commit()

    def protect_fails(_job: DeadLetterJob) -> None:
        raise email_tasks.AuthEmailPayloadError() from None

    async def quarantine_contended(_queue: DeadLetterQueue, _job_hash: str) -> bool:
        raise DeadLetterQuarantineContentionError() from None

    captured = _CaptureLogger()
    monkeypatch.setattr(dlq_module, "_protect_retained_auth_payload", protect_fails)
    monkeypatch.setattr(
        DeadLetterQueue, "quarantine_auth_payload", quarantine_contended
    )
    monkeypatch.setattr(dlq_module, "logger", captured)
    async with sessions() as session:
        result = await DeadLetterQueue(session).auto_replay_jobs(
            force=True, rate_limit_delay=0
        )
        await session.commit()

    stored = await _stored(sessions)
    safe_logs = repr(captured.events)
    assert result == (0, 1)
    assert "DB DLQ auth payload quarantine contended" in safe_logs
    assert marker not in safe_logs
    assert "#token=" not in safe_logs
    assert stored["payload"] == raw_payload
    assert stored["error_message"] == _CONTENTION_MESSAGE
    assert stored["status"] == "pending"


@pytest.mark.asyncio
async def test_aud447_nats_quarantine_logs_generic_contention_only(
    monkeypatch: pytest.MonkeyPatch,
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    monkeypatch.setattr(
        auth_module, "_token_hmac_secret", lambda: secrets.token_hex(32)
    )
    marker = secrets.token_urlsafe(40)
    captured = _CaptureLogger()

    @asynccontextmanager
    async def session_context() -> AsyncIterator[AsyncSession]:
        async with sessions() as session:
            yield session

    async def quarantine_contended(_queue: DeadLetterQueue, _job_hash: str) -> bool:
        raise DeadLetterQuarantineContentionError() from None

    monkeypatch.setattr(database_module, "async_session", session_context)
    monkeypatch.setattr(
        DeadLetterQueue, "quarantine_auth_payload", quarantine_contended
    )
    monkeypatch.setattr(nats_broker_module, "_logger", captured)
    payload = SimpleNamespace(
        name=_AUTH_TASK,
        id="private-nats-job-id",
        args=[
            "student@example.test",
            f"https://portal.example.test/reset-password#token={marker}",
        ],
        kwargs={},
    )

    await nats_broker_module.NatsTaskBroker()._quarantine_auth_payload(payload)

    assert captured.events == [("nats_auth_payload_quarantine_contended", ())]
    assert marker not in repr(captured.events)
