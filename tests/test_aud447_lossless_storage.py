"""Lossless storage invariant for auth links in dead_letter_jobs (AUD-447).

A reset or verification link, or its token, may exist in a dead-letter row only
inside the authenticated Fernet envelope. Every write path must keep the token
out of every column. Replay must still deliver the exact original link.

Tokens, secrets and links are generated at runtime. No literal credential
values appear in this file.
"""

from __future__ import annotations

import asyncio
import json
import secrets
from collections.abc import AsyncIterator, Callable
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import quote

import pytest
import pytest_asyncio
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import app.core.database as database_module
import app.core.nats_broker as nats_module
import app.services.auth_service as auth_module
import app.tasks.email as email_tasks
from app.models.dead_letter import DeadLetterJob
from app.workers.dead_letter_queue import _QUARANTINED_AUTH_PAYLOAD, DeadLetterQueue

_AUTH_TASK = "app.tasks.email.send_auth_email"
_NOTIFICATION_TASK = "app.tasks.example.send_verification_link"
_TABLE = DeadLetterJob.__table__
_MODES = ("sealed", "legacy_plaintext")


@pytest_asyncio.fixture
async def sessions() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", hide_parameters=True)
    try:
        async with engine.begin() as connection:
            await connection.run_sync(_TABLE.create)
        yield async_sessionmaker(engine, expire_on_commit=False)
    finally:
        await engine.dispose()


@pytest.fixture
def secret(monkeypatch: pytest.MonkeyPatch) -> str:
    value = secrets.token_hex(32)
    monkeypatch.setattr(auth_module, "_token_hmac_secret", lambda: value)
    return value


def _link_for(token: str) -> str:
    return f"https://portal.example.test/reset-password#token={quote(token, safe='')}"


def _auth_payload(mode: str, link: str, secret: str) -> dict[str, Any]:
    if mode == "sealed":
        sealed = email_tasks.seal_auth_email_link(
            link, datetime.now(UTC) + timedelta(minutes=15), secret
        )
        return {
            "args": ["student@example.test", sealed, "Student", "en"],
            "kwargs": {"encrypted_link": True},
        }
    return {
        "args": ["student@example.test", link, "Student", "en"],
        "kwargs": {},
    }


@pytest.mark.asyncio
async def test_aud447_forged_plaintext_marked_encrypted_fails_closed_and_stores_nothing(
    sessions: async_sessionmaker[AsyncSession],
    secret: str,
) -> None:
    from app.tasks.email import AuthEmailPayloadError

    token = secrets.token_urlsafe(48)
    payload = {
        "args": ["student@example.test", _link_for(token), "Student", "en"],
        "kwargs": {"encrypted_link": True},
    }
    async with sessions() as session:
        with pytest.raises(AuthEmailPayloadError):
            await DeadLetterQueue(session).add_failed_job(
                job_type=_AUTH_TASK,
                payload=payload,
                error_message="smtp timeout",
            )
        await session.rollback()

    assert await _rows(sessions) == []


async def _rows(sessions: async_sessionmaker[AsyncSession]) -> list[dict[str, Any]]:
    async with sessions() as session:
        rows = (await session.execute(select(_TABLE))).mappings().all()
    return [dict(row) for row in rows]


def _assert_no_token(row: dict[str, Any], token: str) -> None:
    needles = {token, quote(token, safe="")}
    for column, value in row.items():
        text = "" if value is None else str(value)
        for needle in needles:
            assert needle not in text, f"token leaked into column {column!r}"


def _deliver_capture(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[list[str], list[bool]]:
    links: list[str] = []
    sent: list[bool] = []

    async def capture(**kwargs: Any) -> None:
        sent.append(True)
        links.append(kwargs["fallback_fields"]["link"])

    monkeypatch.setattr(email_tasks, "_deliver_email_message", capture)
    return links, sent


def _replay_handler() -> Callable[[str, dict[str, Any]], Any]:
    from inspect import signature

    async def handler(job_type: str, payload: dict[str, Any]) -> None:
        assert job_type == _AUTH_TASK
        bound = signature(email_tasks.send_auth_email).bind(
            *payload["args"], **payload["kwargs"]
        )
        await email_tasks._deliver_auth_email(
            bound.arguments["to_email"],
            bound.arguments["link"],
            bound.arguments.get("full_name", ""),
            bound.arguments.get("locale"),
            bound.arguments.get("encrypted_link", False),
        )

    return handler


async def _make_replayable(sessions: async_sessionmaker[AsyncSession]) -> None:
    async with sessions() as session:
        await session.execute(
            update(_TABLE).values(
                next_retry_at=datetime.now(UTC) - timedelta(minutes=1)
            )
        )
        await session.commit()


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", _MODES)
@pytest.mark.parametrize("error_shape", ["link_form", "raw_token"])
async def test_aud447_insert_path_stores_no_token_in_any_column(
    sessions: async_sessionmaker[AsyncSession],
    secret: str,
    mode: str,
    error_shape: str,
) -> None:
    token = secrets.token_urlsafe(48)
    link = _link_for(token)
    error = (
        f"smtp rejected {link}" if error_shape == "link_form" else f"upstream {token}"
    )
    async with sessions() as session:
        job = await DeadLetterQueue(session).add_failed_job(
            job_type=_AUTH_TASK,
            payload=_auth_payload(mode, link, secret),
            error_message=error,
        )
        await session.commit()
    assert job is not None

    rows = await _rows(sessions)
    assert len(rows) == 1
    _assert_no_token(rows[0], token)


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", _MODES)
async def test_aud447_reopened_finished_row_stores_no_token_in_any_column(
    sessions: async_sessionmaker[AsyncSession],
    secret: str,
    mode: str,
) -> None:
    token = secrets.token_urlsafe(48)
    link = _link_for(token)
    payload = _auth_payload(mode, link, secret)
    async with sessions() as session:
        await DeadLetterQueue(session).add_failed_job(
            job_type=_AUTH_TASK, payload=payload, error_message="first failure"
        )
        await session.commit()
    async with sessions() as session:
        await session.execute(update(_TABLE).values(status="completed"))
        await session.commit()
    async with sessions() as session:
        reopened = await DeadLetterQueue(session).add_failed_job(
            job_type=_AUTH_TASK,
            payload=payload,
            error_message=f"retry echoed {token}",
        )
        await session.commit()
    assert reopened is not None

    rows = await _rows(sessions)
    assert len(rows) == 1
    _assert_no_token(rows[0], token)


@pytest.mark.asyncio
async def test_aud447_non_auth_link_payload_is_quarantined_and_never_replayed(
    monkeypatch: pytest.MonkeyPatch,
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    token = secrets.token_urlsafe(48)
    payload = {"args": [_link_for(token)], "kwargs": {}}
    async with sessions() as session:
        job = await DeadLetterQueue(session).add_failed_job(
            job_type=_NOTIFICATION_TASK,
            payload=payload,
            error_message="delivery failed",
        )
        await session.commit()
    assert job is not None

    rows = await _rows(sessions)
    assert len(rows) == 1
    _assert_no_token(rows[0], token)
    assert rows[0]["status"] == "failed"
    assert rows[0]["payload"] == _QUARANTINED_AUTH_PAYLOAD
    assert rows[0]["next_retry_at"] is None
    assert rows[0]["error_message"] == "delivery failed"

    await _make_replayable(sessions)
    monkeypatch.setattr(DeadLetterQueue, "_replay_lock", asyncio.Lock())
    handled: list[str] = []

    async def handler(job_type: str, payload: dict[str, Any]) -> None:
        handled.append(job_type)

    async with sessions() as session:
        result = await DeadLetterQueue(session).auto_replay_jobs(
            handler, batch_size=5, max_batches=2, rate_limit_delay=0, jitter=0
        )
        await session.commit()
    assert result == (0, 0)
    assert handled == []
    assert len(await _rows(sessions)) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", _MODES)
async def test_aud447_replay_delivers_the_identical_original_link(
    monkeypatch: pytest.MonkeyPatch,
    sessions: async_sessionmaker[AsyncSession],
    secret: str,
    mode: str,
) -> None:
    token = secrets.token_urlsafe(48)
    link = _link_for(token)
    async with sessions() as session:
        await DeadLetterQueue(session).add_failed_job(
            job_type=_AUTH_TASK,
            payload=_auth_payload(mode, link, secret),
            error_message="smtp timeout",
        )
        await session.commit()
    await _make_replayable(sessions)
    links, sent = _deliver_capture(monkeypatch)
    monkeypatch.setattr(DeadLetterQueue, "_replay_lock", asyncio.Lock())

    async with sessions() as session:
        result = await DeadLetterQueue(session).auto_replay_jobs(
            _replay_handler(),
            batch_size=1,
            max_batches=1,
            rate_limit_delay=0,
            jitter=0,
        )
        await session.commit()

    assert result == (1, 0)
    assert sent == [True]
    assert links == [link]
    _assert_no_token(_only(await _rows(sessions)), token)


@pytest.mark.asyncio
async def test_aud447_tampered_envelope_is_quarantined_and_never_sent(
    monkeypatch: pytest.MonkeyPatch,
    sessions: async_sessionmaker[AsyncSession],
    secret: str,
) -> None:
    token = secrets.token_urlsafe(48)
    async with sessions() as session:
        await DeadLetterQueue(session).add_failed_job(
            job_type=_AUTH_TASK,
            payload=_auth_payload("sealed", _link_for(token), secret),
            error_message="smtp timeout",
        )
        await session.commit()
    row = _only(await _rows(sessions))
    stored = json.loads(row["payload"])
    envelope = stored["args"][1]
    flipped = "B" if envelope[len(envelope) // 2] != "B" else "C"
    stored["args"][1] = (
        envelope[: len(envelope) // 2] + flipped + envelope[len(envelope) // 2 + 1 :]
    )
    async with sessions() as session:
        await session.execute(
            update(_TABLE)
            .where(_TABLE.c.id == row["id"])
            .values(
                payload=json.dumps(stored),
                next_retry_at=datetime.now(UTC) - timedelta(minutes=1),
            )
        )
        await session.commit()

    links, sent = _deliver_capture(monkeypatch)
    monkeypatch.setattr(DeadLetterQueue, "_replay_lock", asyncio.Lock())
    handled: list[str] = []

    async def handler(job_type: str, payload: dict[str, Any]) -> None:
        handled.append(job_type)

    async with sessions() as session:
        await DeadLetterQueue(session).auto_replay_jobs(
            handler,
            batch_size=1,
            max_batches=1,
            rate_limit_delay=0,
            jitter=0,
        )
        await session.commit()

    assert handled == []
    assert sent == []
    assert links == []
    stored_row = _only(await _rows(sessions))
    assert stored_row["payload"] == _QUARANTINED_AUTH_PAYLOAD
    _assert_no_token(stored_row, token)


@pytest.mark.asyncio
async def test_aud447_nats_dead_letter_writer_quarantines_non_auth_link_payload(
    monkeypatch: pytest.MonkeyPatch,
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    token = secrets.token_urlsafe(48)
    monkeypatch.setattr(database_module, "async_session", sessions)
    task = nats_module._NatsTaskPayload.model_validate(
        {
            "id": secrets.token_hex(16),
            "name": _NOTIFICATION_TASK,
            "args": [_link_for(token)],
            "kwargs": {},
        }
    )
    broker = nats_module.NatsTaskBroker()

    assert await broker._dead_letter(task, "delivery failed", 1) is True
    assert await broker._dead_letter(task, "delivery failed", 2) is True

    rows = await _rows(sessions)
    assert len(rows) == 1
    _assert_no_token(rows[0], token)
    assert rows[0]["status"] == "failed"


@pytest.mark.asyncio
async def test_aud447_replay_error_echoing_a_raw_token_is_scrubbed(
    monkeypatch: pytest.MonkeyPatch,
    sessions: async_sessionmaker[AsyncSession],
    secret: str,
) -> None:
    token = secrets.token_urlsafe(48)
    async with sessions() as session:
        await DeadLetterQueue(session).add_failed_job(
            job_type=_AUTH_TASK,
            payload=_auth_payload("sealed", _link_for(token), secret),
            error_message="smtp timeout",
        )
        await session.commit()
    await _make_replayable(sessions)
    monkeypatch.setattr(DeadLetterQueue, "_replay_lock", asyncio.Lock())

    async def failing_handler(job_type: str, payload: dict[str, Any]) -> None:
        raise RuntimeError(f"broker rejected {token}")

    async with sessions() as session:
        result = await DeadLetterQueue(session).auto_replay_jobs(
            failing_handler,
            batch_size=1,
            max_batches=1,
            rate_limit_delay=0,
            jitter=0,
        )
        await session.commit()

    assert result == (0, 1)
    _assert_no_token(_only(await _rows(sessions)), token)


@pytest.mark.asyncio
async def test_aud447_duplicate_failure_scrubs_a_retained_raw_token_error(
    sessions: async_sessionmaker[AsyncSession],
    secret: str,
) -> None:
    token = secrets.token_urlsafe(48)
    payload = _sealed_payload_for(_link_for(token), secret)
    async with sessions() as session:
        await DeadLetterQueue(session).add_failed_job(
            job_type=_AUTH_TASK, payload=payload, error_message="smtp timeout"
        )
        await session.commit()
    async with sessions() as session:
        await session.execute(
            update(_TABLE).values(error_message=f"retained upstream {token}")
        )
        await session.commit()

    async with sessions() as session:
        duplicate = await DeadLetterQueue(session).add_failed_job(
            job_type=_AUTH_TASK, payload=payload, error_message="smtp timeout"
        )
        await session.commit()

    assert duplicate is None
    _assert_no_token(_only(await _rows(sessions)), token)


def _sealed_payload_for(link: str, secret: str) -> dict[str, Any]:
    return _auth_payload("sealed", link, secret)


def test_aud447_link_token_extraction_reads_only_authenticated_links(
    secret: str,
) -> None:
    from app.workers.dead_letter_queue import _auth_link_tokens, _scrub_error_text

    token = secrets.token_urlsafe(48)
    sealed = _auth_payload("sealed", _link_for(token), secret)
    plain = _auth_payload("legacy_plaintext", _link_for(token), secret)

    assert _auth_link_tokens(_AUTH_TASK, json.dumps(sealed)) == (token,)
    assert _auth_link_tokens(_AUTH_TASK, json.dumps(plain)) == (token,)
    assert _auth_link_tokens(_NOTIFICATION_TASK, json.dumps(plain)) == ()
    unreadable = _auth_link_tokens(_AUTH_TASK, "not json")
    assert unreadable == (None,)
    assert _scrub_error_text("smtp timeout", unreadable) == _QUARANTINED_AUTH_PAYLOAD
    assert _auth_link_tokens(
        _AUTH_TASK, json.dumps({"args": ["a", 5], "kwargs": {}})
    ) == (None,)
    tampered = json.loads(json.dumps(sealed))
    tampered["args"][1] = "gAAAAA" + secrets.token_urlsafe(40)
    assert _auth_link_tokens(_AUTH_TASK, json.dumps(tampered)) == (None,)


def _only(rows: list[dict[str, Any]]) -> dict[str, Any]:
    assert len(rows) == 1
    return rows[0]
