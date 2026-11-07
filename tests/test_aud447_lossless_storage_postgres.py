"""PostgreSQL byte scan for the lossless dead-letter storage invariant (AUD-447).

Opt-in: set AUD447_DLQ_DISPOSABLE=1 and AUD447_DLQ_DISPOSABLE_PG_URL to a
postgresql+asyncpg URL for a disposable database and a non-superuser,
non-BYPASSRLS role. The test creates and drops its own schema. It inserts a real
auth row, replays it, and scans the stored bytes of every column for the token
after each step.

Tokens, secrets and links are generated at runtime.
"""

from __future__ import annotations

import asyncio
import os
import secrets
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from inspect import signature
from typing import Any
from urllib.parse import quote

import pytest
import pytest_asyncio
from sqlalchemy import text, update
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

import app.services.auth_service as auth_module
import app.tasks.email as email_tasks
from app.models.dead_letter import DeadLetterJob
from app.workers.dead_letter_queue import DeadLetterQueue

_URL = os.getenv("AUD447_DLQ_DISPOSABLE_PG_URL", "")
_OPTED_IN = os.getenv("AUD447_DLQ_DISPOSABLE") == "1"
pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not (_OPTED_IN and _URL.startswith("postgresql+asyncpg://")),
        reason="Set AUD447_DLQ_DISPOSABLE=1 and a dedicated non-superuser AUD447_DLQ_DISPOSABLE_PG_URL",
    ),
]

_AUTH_TASK = "app.tasks.email.send_auth_email"
_TABLE = DeadLetterJob.__table__


@pytest_asyncio.fixture
async def dlq_engine() -> AsyncIterator[AsyncEngine]:
    schema = "aud447_lossless_" + uuid.uuid4().hex
    bootstrap = create_async_engine(_URL, poolclass=NullPool)
    engine: AsyncEngine | None = None
    try:
        async with bootstrap.begin() as connection:
            role = (
                await connection.execute(
                    text(
                        "SELECT rolsuper, rolbypassrls FROM pg_roles "
                        "WHERE rolname = current_user"
                    )
                )
            ).one()
            assert tuple(role) == (False, False)
            await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        engine = create_async_engine(
            _URL,
            poolclass=NullPool,
            connect_args={"server_settings": {"search_path": schema}},
        )
        async with engine.begin() as connection:
            await connection.run_sync(_TABLE.create)
        yield engine
    finally:
        if engine is not None:
            await engine.dispose()
        async with bootstrap.begin() as connection:
            await connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        await bootstrap.dispose()


@pytest.fixture
def secret(monkeypatch: pytest.MonkeyPatch) -> str:
    value = secrets.token_hex(32)
    monkeypatch.setattr(auth_module, "_token_hmac_secret", lambda: value)
    return value


def _link_for(token: str) -> str:
    return f"https://portal.example.test/reset-password#token={quote(token, safe='')}"


def _sealed_payload(link: str, secret: str) -> dict[str, Any]:
    sealed = email_tasks.seal_auth_email_link(
        link, datetime.now(UTC) + timedelta(minutes=15), secret
    )
    return {
        "args": ["student@example.test", sealed, "Student", "en"],
        "kwargs": {"encrypted_link": True},
    }


async def _stored_row_bytes(engine: AsyncEngine) -> list[bytes]:
    """Return each stored row as the UTF-8 bytes of its full text form."""
    async with engine.connect() as connection:
        rows = await connection.execute(
            text(
                "SELECT encode(convert_to(t::text, 'UTF8'), 'hex') "
                "FROM dead_letter_jobs AS t ORDER BY id"
            )
        )
        return [bytes.fromhex(row[0]) for row in rows]


def _assert_no_token_bytes(rows: list[bytes], token: str) -> None:
    assert rows, "expected at least one stored dead-letter row"
    for row_bytes in rows:
        for needle in (token, quote(token, safe="")):
            assert needle.encode("utf-8") not in row_bytes


@pytest.mark.asyncio
async def test_aud447_postgres_insert_and_replay_store_no_token_bytes(
    monkeypatch: pytest.MonkeyPatch,
    dlq_engine: AsyncEngine,
    secret: str,
) -> None:
    sessions: async_sessionmaker[AsyncSession] = async_sessionmaker(
        dlq_engine, expire_on_commit=False
    )
    token = secrets.token_urlsafe(48)
    link = _link_for(token)

    async with sessions() as session:
        job = await DeadLetterQueue(session).add_failed_job(
            job_type=_AUTH_TASK,
            payload=_sealed_payload(link, secret),
            error_message=f"smtp rejected upstream token {token}",
        )
        await session.commit()
    assert job is not None
    _assert_no_token_bytes(await _stored_row_bytes(dlq_engine), token)

    async with sessions() as session:
        await session.execute(
            update(_TABLE).values(
                next_retry_at=datetime.now(UTC) - timedelta(minutes=1)
            )
        )
        await session.commit()

    delivered: list[str] = []

    async def capture(**kwargs: Any) -> None:
        delivered.append(kwargs["fallback_fields"]["link"])

    monkeypatch.setattr(email_tasks, "_deliver_email_message", capture)
    monkeypatch.setattr(DeadLetterQueue, "_replay_lock", asyncio.Lock())

    async def handler(job_type: str, payload: dict[str, Any]) -> None:
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

    async with sessions() as session:
        result = await DeadLetterQueue(session).auto_replay_jobs(
            handler, batch_size=1, max_batches=1, rate_limit_delay=0, jitter=0
        )
        await session.commit()

    assert result == (1, 0)
    assert delivered == [link]
    _assert_no_token_bytes(await _stored_row_bytes(dlq_engine), token)
