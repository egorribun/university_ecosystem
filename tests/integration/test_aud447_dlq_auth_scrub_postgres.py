"""PostgreSQL behaviour of the AUD-447 dead_letter_jobs token scrub.

Set RUN_INTEGRATION_TESTS=1 and AUD447_POSTGRES_DATABASE_URL to a disposable
PostgreSQL server (postgresql+psycopg://...). The fixture builds a connection-local
temporary dead_letter_jobs table and rolls it back, so no durable state changes.
"""

from __future__ import annotations

import importlib.util
import json
import os
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

from app.workers.dead_letter_queue import _QUARANTINED_AUTH_PAYLOAD

MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "alembic"
    / "versions"
    / "202610310001_scrub_plaintext_auth_tokens_from_dlq.py"
)
AUTH_JOB = "app.tasks.email.send_auth_email"
_RUN = os.getenv("RUN_INTEGRATION_TESTS") == "1"

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not _RUN, reason="Set RUN_INTEGRATION_TESTS=1 to run"),
]

SEALED = json.dumps(
    {
        "args": ["sealed@example.test", "gAAAA-envelope"],
        "kwargs": {"encrypted_link": True},
    }
)
PLAIN_RESET = json.dumps(
    {
        "args": [
            "plain@example.test",
            "https://app.example.test/reset-password#token=PLAIN1",
        ],
        "kwargs": {},
    }
)
PLAIN_CONFIRM = json.dumps(
    {
        "args": [
            "c@example.test",
            "https://app.example.test/settings/email-confirm?token=PLAIN2",
        ],
        "kwargs": {},
    }
)


def _load_migration() -> ModuleType:
    spec = importlib.util.spec_from_file_location("aud447_scrub_pg", MIGRATION)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def connection() -> Iterator[sa.Connection]:
    engine = sa.create_engine(os.environ["AUD447_POSTGRES_DATABASE_URL"])
    try:
        with engine.connect() as conn:
            transaction = conn.begin()
            try:
                conn.execute(
                    sa.text(
                        "CREATE TEMP TABLE dead_letter_jobs ("
                        "id integer PRIMARY KEY, "
                        "job_type varchar(100) NOT NULL, "
                        "job_hash varchar(64) NOT NULL UNIQUE, "
                        "payload text NOT NULL, "
                        "error_message text, "
                        "status varchar(20) NOT NULL, "
                        "retry_count integer NOT NULL DEFAULT 0"
                        ") ON COMMIT DROP"
                    )
                )
                yield conn
            finally:
                if transaction.is_active:
                    transaction.rollback()
    finally:
        engine.dispose()


def _insert(conn: sa.Connection, rows: list[dict[str, Any]]) -> None:
    conn.execute(
        sa.text(
            "INSERT INTO dead_letter_jobs (id, job_type, job_hash, payload, "
            "error_message, status, retry_count) VALUES (:id, :job_type, :job_hash, "
            ":payload, :error_message, :status, :retry_count)"
        ),
        rows,
    )


def _snapshot(conn: sa.Connection) -> list[tuple[Any, ...]]:
    return [
        tuple(row)
        for row in conn.execute(
            sa.text(
                "SELECT id, job_type, job_hash, payload, error_message, status, "
                "retry_count FROM dead_letter_jobs ORDER BY id"
            )
        )
    ]


def _run(monkeypatch: pytest.MonkeyPatch, conn: sa.Connection, batch_size: int) -> None:
    migration = _load_migration()
    monkeypatch.setattr(migration, "_BATCH_SIZE", batch_size)
    monkeypatch.setattr(
        migration,
        "op",
        Operations(MigrationContext.configure(connection=conn)),
    )
    migration.upgrade()


def _job(row_id: int, payload: str, error: str | None = None, **extra: Any) -> dict:
    return {
        "id": row_id,
        "job_type": extra.get("job_type", AUTH_JOB),
        "job_hash": f"hash-{row_id:03d}",
        "payload": payload,
        "error_message": error,
        "status": extra.get("status", "pending"),
        "retry_count": extra.get("retry_count", row_id),
    }


def test_postgres_scrub_replaces_only_plaintext_auth_material(
    connection: sa.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    _insert(
        connection,
        [
            _job(1, PLAIN_RESET, status="failed", retry_count=2),
            _job(2, SEALED, error="SMTP timeout"),
            _job(3, PLAIN_CONFIRM),
            _job(4, "not json", job_type=AUTH_JOB),
            _job(
                5, json.dumps({"args": ["x"], "kwargs": {}}), job_type="app.tasks.other"
            ),
            _job(
                6,
                SEALED,
                error="refused https://app.example.test/reset-password#token=LEAK",
            ),
        ],
    )

    _run(monkeypatch, connection, batch_size=2)

    rows = {row[0]: row for row in _snapshot(connection)}
    assert rows[1][3] == _QUARANTINED_AUTH_PAYLOAD
    assert rows[3][3] == _QUARANTINED_AUTH_PAYLOAD
    assert rows[4][3] == _QUARANTINED_AUTH_PAYLOAD
    assert rows[2][3] == SEALED and rows[2][4] == "SMTP timeout"
    assert rows[5][3] == json.dumps({"args": ["x"], "kwargs": {}})
    assert rows[6][4] == _QUARANTINED_AUTH_PAYLOAD and rows[6][3] == SEALED
    # Identity, hash, status and retry state survive the scrub.
    assert rows[1][2] == "hash-001" and rows[1][5] == "failed" and rows[1][6] == 2
    assert all("PLAIN" not in (row[3] or "") for row in rows.values())
    assert all("LEAK" not in (row[4] or "") for row in rows.values())


def test_postgres_scrub_is_idempotent_across_batches(
    connection: sa.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    _insert(
        connection, [_job(i, PLAIN_RESET if i % 2 else SEALED) for i in range(1, 8)]
    )

    _run(monkeypatch, connection, batch_size=3)
    after_first = _snapshot(connection)
    _run(monkeypatch, connection, batch_size=3)

    assert _snapshot(connection) == after_first
    assert [row[3] for row in after_first if row[0] % 2] == [
        _QUARANTINED_AUTH_PAYLOAD
    ] * 4
