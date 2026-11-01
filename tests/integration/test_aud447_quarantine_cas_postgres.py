"""PostgreSQL interleavings for DLQ quarantine compare-and-set (AUD-447).

Opt-in: set AUD447_DLQ_DISPOSABLE=1 and AUD447_DLQ_DISPOSABLE_PG_URL to a
postgresql+asyncpg URL for a disposable database and a non-superuser,
non-BYPASSRLS role. The test creates and drops its own schema. A concurrent
writer commits between the quarantine's read and its write, so the replacement
decision is exercised against a real committed change.
"""

from __future__ import annotations

import json
import os
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Any, cast

import pytest
import pytest_asyncio
from sqlalchemy import Select, text, update
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from app.models.dead_letter import DeadLetterJob
from app.workers.dead_letter_queue import _QUARANTINED_AUTH_PAYLOAD, DeadLetterQueue

_URL = os.getenv("AUD447_DLQ_DISPOSABLE_PG_URL", "")
_OPTED_IN = os.getenv("AUD447_DLQ_DISPOSABLE") == "1"
pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not (_OPTED_IN and _URL.startswith("postgresql+asyncpg://")),
        reason="Set AUD447_DLQ_DISPOSABLE=1 and a dedicated non-superuser AUD447_DLQ_DISPOSABLE_PG_URL",
    ),
]

_AUTH_JOB = "app.tasks.email.send_auth_email"
_LINK_TOKEN = "pg-leak-" + uuid.uuid4().hex
_JOB_HASH = "c" * 64
_MALFORMED = json.dumps(
    {
        "args": [
            "student@example.test",
            f"https://portal.example.test/reset-password#token={_LINK_TOKEN}",
        ],
        "kwargs": {},
    }
)[:-1]
_REPAIRED = json.dumps(
    {
        "args": ["student@example.test", "gAAAA-envelope"],
        "kwargs": {"encrypted_link": True},
    }
)
_TABLE = DeadLetterJob.__table__


@pytest_asyncio.fixture
async def dlq_engine() -> AsyncIterator[AsyncEngine]:
    schema = "aud447_dlq_" + uuid.uuid4().hex
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
        try:
            async with bootstrap.begin() as connection:
                await connection.execute(
                    text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
                )
        finally:
            await bootstrap.dispose()


class _ConcurrentWriteAfterFirstRead:
    """Delegate to a real session, committing one other write after its first read."""

    def __init__(
        self,
        session: AsyncSession,
        concurrent_write: Callable[[], Awaitable[None]],
    ) -> None:
        self._session = session
        self._concurrent_write = concurrent_write
        self._fired = False

    async def execute(self, statement: Any) -> Any:
        result = await self._session.execute(statement)
        if not self._fired and isinstance(statement, Select):
            self._fired = True
            await self._concurrent_write()
        return result

    async def flush(self) -> None:
        await self._session.flush()


async def _insert(engine: AsyncEngine, **values: Any) -> None:
    async with engine.begin() as connection:
        await connection.execute(_TABLE.insert().values(**values))


async def _row(engine: AsyncEngine) -> Any:
    async with engine.connect() as connection:
        return (
            await connection.execute(
                _TABLE.select().where(_TABLE.c.job_hash == _JOB_HASH)
            )
        ).one()


def _sessions(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


@pytest.mark.asyncio
async def test_quarantine_never_overwrites_bytes_repaired_after_they_were_read(
    dlq_engine: AsyncEngine,
) -> None:
    await _insert(
        dlq_engine,
        job_type=_AUTH_JOB,
        job_hash=_JOB_HASH,
        payload=_MALFORMED,
        status="pending",
        retry_count=1,
        max_retries=4,
    )

    async def repair_committed_by_another_writer() -> None:
        async with dlq_engine.begin() as connection:
            await connection.execute(
                update(_TABLE)
                .where(_TABLE.c.job_hash == _JOB_HASH)
                .values(payload=_REPAIRED)
            )

    async with _sessions(dlq_engine)() as session:
        queue = DeadLetterQueue(
            cast(
                Any,
                _ConcurrentWriteAfterFirstRead(
                    session, repair_committed_by_another_writer
                ),
            )
        )
        assert await queue.quarantine_auth_payload(_JOB_HASH) is False
        await session.commit()

    assert (await _row(dlq_engine)).payload == _REPAIRED


@pytest.mark.asyncio
async def test_quarantine_replaces_observed_bytes_and_scrubs_link_in_error_field(
    dlq_engine: AsyncEngine,
) -> None:
    await _insert(
        dlq_engine,
        job_type=_AUTH_JOB,
        job_hash=_JOB_HASH,
        payload=_MALFORMED,
        error_message=f"smtp refused https://portal.example.test/x#token={_LINK_TOKEN}",
        status="pending",
        retry_count=1,
        max_retries=4,
    )
    before = await _row(dlq_engine)

    async with _sessions(dlq_engine)() as session:
        assert await DeadLetterQueue(session).quarantine_auth_payload(_JOB_HASH) is True
        await session.commit()

    after = await _row(dlq_engine)
    assert after.payload == _QUARANTINED_AUTH_PAYLOAD
    assert after.error_message == _QUARANTINED_AUTH_PAYLOAD
    assert _LINK_TOKEN not in repr(tuple(after))
    # Identity, hash, status and retry state survive the replacement.
    assert (after.id, after.job_hash, after.status, after.retry_count) == (
        before.id,
        before.job_hash,
        before.status,
        before.retry_count,
    )


@pytest.mark.asyncio
async def test_failed_replay_stores_scrubbed_error_text(
    dlq_engine: AsyncEngine,
) -> None:
    await _insert(
        dlq_engine,
        job_type="app.tasks.other",
        job_hash=_JOB_HASH,
        payload=json.dumps({"args": []}),
        status="pending",
        retry_count=0,
        max_retries=3,
        next_retry_at=datetime.now(UTC) - timedelta(minutes=1),
    )

    async def handler(_job_type: str, _payload: dict[str, Any]) -> None:
        raise RuntimeError(
            f"upstream echoed https://portal.example.test/x#token={_LINK_TOKEN}"
        )

    async with _sessions(dlq_engine)() as session:
        replayed = await DeadLetterQueue(session).auto_replay_jobs(
            handler, batch_size=5, max_batches=1, rate_limit_delay=0.001
        )
        assert replayed == (0, 1)
        await session.commit()

    after = await _row(dlq_engine)
    assert after.error_message == _QUARANTINED_AUTH_PAYLOAD
    assert after.retry_count == 1
    assert _LINK_TOKEN not in repr(tuple(after))
