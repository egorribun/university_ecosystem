"""AUD-447 follow-up: scrub plaintext auth links from dead_letter_jobs.

These tests drive revision 202610310001 with an in-memory keyset-paginated fake
of the dead_letter_jobs table. The PostgreSQL behaviour is covered separately by
tests/integration/test_aud447_dlq_auth_scrub_postgres.py.
"""

from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest

from app.workers.dead_letter_queue import _QUARANTINED_AUTH_PAYLOAD

MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "202610310001_scrub_plaintext_auth_tokens_from_dlq.py"
)
AUTH_JOB = "app.tasks.email.send_auth_email"
PLAINTEXT_RESET = json.dumps(
    {
        "args": [
            "user@example.test",
            "https://app.example.test/reset-password#token=abc123",
        ],
        "kwargs": {},
    }
)
SEALED_RESET = json.dumps(
    {
        "args": ["user@example.test", "gAAAA-sealed-envelope"],
        "kwargs": {"encrypted_link": True},
    }
)


def _load_migration() -> ModuleType:
    spec = importlib.util.spec_from_file_location("aud447_scrub", MIGRATION)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _Table:
    """Keyset SELECT and executemany UPDATE over an in-memory dead_letter_jobs."""

    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = {row["id"]: dict(row) for row in rows}
        self.selects = 0
        self.update_batches: list[list[dict[str, Any]]] = []

    def execute(self, statement: Any, params: Any = None) -> Any:
        sql = " ".join(str(statement).split())
        if sql.startswith("SELECT id"):
            self.selects += 1
            assert params is not None
            chosen = [
                SimpleNamespace(**row)
                for row_id, row in sorted(self.rows.items())
                if row_id > params["last_id"]
            ][: params["batch_size"]]
            return SimpleNamespace(fetchall=lambda: chosen)
        assert sql.startswith("UPDATE dead_letter_jobs SET payload")
        assert isinstance(params, list)
        self.update_batches.append(params)
        for change in params:
            self.rows[change["id"]].update(
                payload=change["payload"], error_message=change["error_message"]
            )
        return SimpleNamespace()


def _row(row_id: int, payload: str, error: str | None = None, job_type: str = AUTH_JOB):
    return {
        "id": row_id,
        "job_type": job_type,
        "payload": payload,
        "error_message": error,
    }


def _run_upgrade(
    monkeypatch: pytest.MonkeyPatch, table: _Table, batch_size: int = 500
) -> ModuleType:
    migration = _load_migration()
    monkeypatch.setattr(migration, "_BATCH_SIZE", batch_size)
    monkeypatch.setattr(migration, "op", SimpleNamespace(get_bind=lambda: table))
    migration.upgrade()
    return migration


def test_tombstone_is_the_application_quarantine_constant() -> None:
    migration = _load_migration()
    assert migration.QUARANTINED_AUTH_PAYLOAD == _QUARANTINED_AUTH_PAYLOAD
    assert json.loads(migration.QUARANTINED_AUTH_PAYLOAD) == {
        "kind": "auth-email-quarantined-v1"
    }


def test_plaintext_reset_link_payload_is_replaced_by_tombstone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    table = _Table([_row(1, PLAINTEXT_RESET)])

    _run_upgrade(monkeypatch, table)

    assert table.rows[1]["payload"] == _QUARANTINED_AUTH_PAYLOAD
    assert "abc123" not in table.rows[1]["payload"]


def test_plaintext_confirm_link_in_query_string_is_replaced(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = json.dumps(
        {
            "args": [
                "user@example.test",
                "https://app.example.test/settings/email-confirm?token=xyz",
            ],
            "kwargs": {},
        }
    )
    table = _Table([_row(1, payload)])

    _run_upgrade(monkeypatch, table)

    assert table.rows[1]["payload"] == _QUARANTINED_AUTH_PAYLOAD


def test_sealed_auth_payload_is_kept_byte_for_byte(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    table = _Table([_row(1, SEALED_RESET)])

    _run_upgrade(monkeypatch, table)

    assert table.rows[1]["payload"] == SEALED_RESET
    assert table.update_batches == []


@pytest.mark.parametrize(
    "payload",
    [
        "not json at all",
        json.dumps(["list", "not", "a", "task"]),
        json.dumps({"args": [], "kwargs": ["not", "a", "dict"]}),
        json.dumps({"args": [], "kwargs": {"encrypted_link": "yes"}}),
    ],
    ids=["unreadable", "non-object", "kwargs-not-object", "non-boolean-flag"],
)
def test_auth_payload_that_cannot_be_proven_sealed_is_scrubbed(
    monkeypatch: pytest.MonkeyPatch, payload: str
) -> None:
    table = _Table([_row(1, payload)])

    _run_upgrade(monkeypatch, table)

    assert table.rows[1]["payload"] == _QUARANTINED_AUTH_PAYLOAD


def test_non_auth_payload_without_token_is_kept(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = json.dumps({"args": ["unrelated"], "kwargs": {}})
    table = _Table([_row(1, payload, job_type="app.tasks.reports.build")])

    _run_upgrade(monkeypatch, table)

    assert table.rows[1]["payload"] == payload


def test_non_auth_payload_echoing_a_token_is_scrubbed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = json.dumps({"args": ["https://x.example.test/?token=leak"], "kwargs": {}})
    table = _Table([_row(1, payload, job_type="app.tasks.reports.build")])

    _run_upgrade(monkeypatch, table)

    assert table.rows[1]["payload"] == _QUARANTINED_AUTH_PAYLOAD


def test_error_text_echoing_a_plaintext_token_is_replaced(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    table = _Table(
        [
            _row(
                1,
                SEALED_RESET,
                error="SMTP refused https://app.example.test/reset-password#token=abc",
            )
        ]
    )

    _run_upgrade(monkeypatch, table)

    assert table.rows[1]["error_message"] == _QUARANTINED_AUTH_PAYLOAD
    assert table.rows[1]["payload"] == SEALED_RESET


def test_error_text_without_token_and_missing_error_are_kept(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    table = _Table(
        [
            _row(1, SEALED_RESET, error="timeout after 30s"),
            _row(2, SEALED_RESET, error=None),
        ]
    )

    _run_upgrade(monkeypatch, table)

    assert table.rows[1]["error_message"] == "timeout after 30s"
    assert table.rows[2]["error_message"] is None
    assert table.update_batches == []


def test_already_scrubbed_rows_are_not_rewritten_on_rerun(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    table = _Table(
        [
            _row(1, PLAINTEXT_RESET, error="boom https://x.test/?token=q"),
            _row(2, PLAINTEXT_RESET),
        ]
    )

    _run_upgrade(monkeypatch, table)
    first_batches = len(table.update_batches)
    _run_upgrade(monkeypatch, table)

    assert first_batches == 1
    assert len(table.update_batches) == first_batches
    assert table.rows[1]["payload"] == _QUARANTINED_AUTH_PAYLOAD


def test_scan_is_keyset_batched_and_covers_every_row(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rows = [_row(i, PLAINTEXT_RESET if i % 2 else SEALED_RESET) for i in range(1, 8)]
    table = _Table(rows)

    _run_upgrade(monkeypatch, table, batch_size=3)

    # Three data batches plus the empty page that ends the scan.
    assert table.selects == 4
    assert sum(len(batch) for batch in table.update_batches) == 4
    assert all(
        table.rows[i]["payload"] == _QUARANTINED_AUTH_PAYLOAD for i in (1, 3, 5, 7)
    )
    assert all(table.rows[i]["payload"] == SEALED_RESET for i in (2, 4, 6))


def test_empty_table_performs_one_select_and_no_update(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    table = _Table([])

    _run_upgrade(monkeypatch, table)

    assert table.selects == 1
    assert table.update_batches == []


def test_downgrade_is_an_explicit_noop() -> None:
    migration = _load_migration()
    assert migration.downgrade() is None
    assert migration.revision == "202610310001"
    assert migration.down_revision == "202610250001"


def test_migration_source_does_not_import_application_code() -> None:
    source = MIGRATION.read_text(encoding="utf-8")
    assert re.search(r"^\s*(?:from|import)\s+app", source, re.MULTILINE) is None
