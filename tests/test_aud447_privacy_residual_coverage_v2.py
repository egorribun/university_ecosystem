from __future__ import annotations

import json
import secrets
from pathlib import Path
from urllib.parse import quote

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.dead_letter import DeadLetterJob
from app.workers.dead_letter_queue import (
    _QUARANTINED_AUTH_PAYLOAD,
    DeadLetterQueue,
    _auth_link_tokens,
    _scrub_error_text,
)

_AUTH_JOB_TYPE = "app.tasks.email.send_auth_email"


@pytest.mark.parametrize(
    "stored_arguments",
    [
        ["coverage-fixture@example.test", 17],
        ["coverage-fixture@example.test"],
    ],
    ids=("non-string-link", "valid-json-missing-link"),
)
def test_non_string_or_unreadable_stored_auth_link_fails_closed(
    stored_arguments: list[object],
) -> None:
    stored_payload = json.dumps({"args": stored_arguments, "kwargs": {}})

    tokens = _auth_link_tokens(_AUTH_JOB_TYPE, stored_payload)

    assert tokens == (None,)
    assert _scrub_error_text("generic worker diagnostic", tokens) == (
        _QUARANTINED_AUTH_PAYLOAD
    )


def test_scrubber_fails_closed_for_untrusted_nonconverging_token() -> None:
    token = "private-unit/token-value"
    for _ in range(10):
        token = quote(token, safe="")

    assert _scrub_error_text("generic worker diagnostic", (token,)) == (
        _QUARANTINED_AUTH_PAYLOAD
    )


def test_scrubber_keeps_error_without_a_matching_token() -> None:
    error = "generic worker diagnostic"
    token = "private-unit/token-value"

    assert _scrub_error_text(error, (token,)) == error


def test_scrubber_quarantines_error_with_a_matching_token() -> None:
    token = "private-unit/token-value"
    error = f"generic worker diagnostic {token}"

    assert _scrub_error_text(error, (token,)) == _QUARANTINED_AUTH_PAYLOAD


@pytest.mark.asyncio
async def test_quarantine_returns_false_for_missing_and_non_auth_sqlite_rows(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "private-quarantine-branches.sqlite3"
    engine = create_async_engine(f"sqlite+aiosqlite:///{database_path.as_posix()}")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(DeadLetterJob.__table__.create)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        missing_hash = secrets.token_hex(32)
        async with sessions() as session:
            assert (
                await DeadLetterQueue(session).quarantine_auth_payload(missing_hash)
                is False
            )

        other_hash = secrets.token_hex(32)
        async with sessions() as session:
            session.add(
                DeadLetterJob(
                    job_type="private-unit-non-auth-task",
                    job_hash=other_hash,
                    payload=json.dumps({"kind": "safe-unit-payload"}),
                    error_message="safe unit error",
                    status="pending",
                )
            )
            await session.commit()

        async with sessions() as session:
            assert (
                await DeadLetterQueue(session).quarantine_auth_payload(other_hash)
                is False
            )
            row = (
                await session.execute(
                    select(DeadLetterJob).where(DeadLetterJob.job_hash == other_hash)
                )
            ).scalar_one()
            assert row.payload == json.dumps({"kind": "safe-unit-payload"})
            assert row.error_message == "safe unit error"
    finally:
        await engine.dispose()
