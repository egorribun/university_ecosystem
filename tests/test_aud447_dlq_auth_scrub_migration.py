"""AUD-447 follow-up: scrub plaintext auth links from dead_letter_jobs.

These tests drive revision 202610310001 with an in-memory keyset-paginated fake
of the dead_letter_jobs table. The PostgreSQL behaviour is covered separately by
tests/integration/test_aud447_dlq_auth_scrub_postgres.py.
"""

from __future__ import annotations

import importlib.util
import json
import re
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest

from app.workers.dead_letter_queue import _QUARANTINED_AUTH_PAYLOAD
from tests.integration import test_aud447_dlq_auth_scrub_postgres as postgres_fixture

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


_OWNED_AUD447_URL = "postgresql+psycopg://test:test@127.0.0.1:5432/test"


def _aud447_owned_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RUN_INTEGRATION_TESTS", "1")
    monkeypatch.setenv("ENVIRONMENT", "testing")
    monkeypatch.setenv("UNIVERSITY_ECOSYSTEM_PYTEST_ALLOW_DATABASE_RESET", "1")
    monkeypatch.setenv("AUD447_POSTGRES_DATABASE_URL", _OWNED_AUD447_URL)


def _aud447_deny_engine_creation(*_args: Any, **_kwargs: Any) -> None:
    pytest.fail("Invalid AUD-447 allocation reached engine creation")


def test_owned_postgres_target_accepts_only_the_explicit_synchronous_allocation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _aud447_owned_environment(monkeypatch)

    url = postgres_fixture._owned_postgres_url()

    assert (
        url.drivername,
        url.host,
        url.port,
        url.database,
        url.username,
        url.password,
        dict(url.query),
    ) == ("postgresql+psycopg", "127.0.0.1", 5432, "test", "test", "test", {})


@pytest.mark.parametrize(
    "target",
    [
        pytest.param("", id="missing"),
        pytest.param("not-a-url", id="malformed"),
        pytest.param(
            "postgresql+asyncpg://test:test@127.0.0.1:5432/test",
            id="async-driver",
        ),
        pytest.param("sqlite:///:memory:", id="sqlite"),
        pytest.param("postgresql+psycopg://test:test@192.0.2.1:5432/test", id="remote"),
        pytest.param(
            "postgresql+psycopg://test:test@localhost:5432/test",
            id="dns-name",
        ),
        pytest.param(
            "postgresql+psycopg://test:test@127.0.0.1:5433/test",
            id="wrong-port",
        ),
        pytest.param(
            "postgresql+psycopg://test:test@127.0.0.1/test",
            id="missing-port",
        ),
        pytest.param(
            "postgresql+psycopg://other:test@127.0.0.1:5432/test",
            id="wrong-user",
        ),
        pytest.param(
            "postgresql+psycopg://test:other@127.0.0.1:5432/test",
            id="wrong-password",
        ),
        pytest.param(
            "postgresql+psycopg://test:test@127.0.0.1:5432/other",
            id="wrong-database",
        ),
        pytest.param(_OWNED_AUD447_URL + "?hostaddr=192.0.2.1", id="host-override"),
        pytest.param(
            _OWNED_AUD447_URL + "?options=-csearch_path=public",
            id="options-override",
        ),
    ],
)
def test_owned_postgres_target_rejects_unsafe_allocation_before_connect(
    monkeypatch: pytest.MonkeyPatch, target: str
) -> None:
    _aud447_owned_environment(monkeypatch)
    monkeypatch.setenv("AUD447_POSTGRES_DATABASE_URL", target)
    monkeypatch.setenv("DATABASE_URL", _OWNED_AUD447_URL)
    monkeypatch.setattr(
        postgres_fixture.sa, "create_engine", _aud447_deny_engine_creation
    )

    with pytest.raises(ValueError) as failure:
        next(postgres_fixture.connection.__wrapped__())

    assert str(failure.value) == postgres_fixture._OWNED_TARGET_ERROR


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("RUN_INTEGRATION_TESTS", None),
        ("RUN_INTEGRATION_TESTS", "0"),
        ("ENVIRONMENT", None),
        ("ENVIRONMENT", "production"),
        ("UNIVERSITY_ECOSYSTEM_PYTEST_ALLOW_DATABASE_RESET", None),
        ("UNIVERSITY_ECOSYSTEM_PYTEST_ALLOW_DATABASE_RESET", "0"),
    ],
)
def test_owned_postgres_target_requires_explicit_integration_acknowledgments(
    monkeypatch: pytest.MonkeyPatch, name: str, value: str | None
) -> None:
    _aud447_owned_environment(monkeypatch)
    if value is None:
        monkeypatch.delenv(name)
    else:
        monkeypatch.setenv(name, value)
    monkeypatch.setattr(
        postgres_fixture.sa, "create_engine", _aud447_deny_engine_creation
    )

    with pytest.raises(ValueError) as failure:
        next(postgres_fixture.connection.__wrapped__())

    assert str(failure.value) == postgres_fixture._OWNED_TARGET_ERROR


@pytest.mark.parametrize(
    ("relation", "active", "owns_transaction", "dialect", "missing_transaction"),
    [
        (None, True, True, "postgresql", False),
        (("p", True), True, True, "postgresql", False),
        (("t", False), True, True, "postgresql", False),
        (("t", None), True, True, "postgresql", False),
        (("t", True), False, True, "postgresql", False),
        (("t", True), True, False, "postgresql", False),
        (("t", True), True, True, "sqlite", False),
        (("t", True), True, True, "postgresql", True),
    ],
    ids=[
        "missing-relation",
        "persistent-relation",
        "foreign-namespace",
        "unknown-namespace",
        "inactive-transaction",
        "different-transaction",
        "wrong-dialect",
        "missing-transaction",
    ],
)
def test_owned_postgres_guard_rejects_non_owned_table_or_transaction(
    relation: tuple[str, bool | None] | None,
    active: bool,
    owns_transaction: bool,
    dialect: str,
    missing_transaction: bool,
) -> None:
    transaction = None if missing_transaction else SimpleNamespace(is_active=active)
    connection = SimpleNamespace(
        dialect=SimpleNamespace(name=dialect),
        get_transaction=lambda: transaction if owns_transaction else object(),
        execute=lambda _statement: SimpleNamespace(one_or_none=lambda: relation),
    )

    with pytest.raises(RuntimeError) as failure:
        postgres_fixture._assert_owned_temp_table(connection, transaction)

    assert str(failure.value) == postgres_fixture._OWNED_TEMP_ERROR


@pytest.mark.parametrize("body_fails", [False, True], ids=["normal", "exception"])
def test_owned_postgres_fixture_pins_connection_and_rolls_back_its_transaction(
    monkeypatch: pytest.MonkeyPatch, body_fails: bool
) -> None:
    _aud447_owned_environment(monkeypatch)
    events: list[str] = []
    statements: list[str] = []
    transaction = SimpleNamespace(is_active=True)

    def rollback() -> None:
        events.append("rollback")
        transaction.is_active = False

    transaction.rollback = rollback

    def execute(statement: Any) -> Any:
        statements.append(str(statement))
        return SimpleNamespace(one_or_none=lambda: ("t", True))

    connection = SimpleNamespace(
        dialect=SimpleNamespace(name="postgresql"),
        begin=lambda: transaction,
        get_transaction=lambda: transaction,
        execute=execute,
    )

    @contextmanager
    def connect() -> Iterator[Any]:
        yield connection

    engine = SimpleNamespace(connect=connect, dispose=lambda: events.append("dispose"))

    def create_engine(url: Any, *, connect_args: dict[str, object]) -> Any:
        assert url == postgres_fixture.sa.engine.make_url(_OWNED_AUD447_URL)
        assert connect_args == {"hostaddr": "127.0.0.1", "connect_timeout": 5}
        return engine

    monkeypatch.setattr(postgres_fixture.sa, "create_engine", create_engine)
    fixture = postgres_fixture.connection.__wrapped__()
    assert next(fixture) is connection
    assert statements[0].startswith("CREATE TEMP TABLE dead_letter_jobs")
    assert "ON COMMIT DROP" in statements[0]
    assert "pg_catalog.pg_my_temp_schema()" in statements[1]
    assert "pg_catalog.to_regclass('dead_letter_jobs')" in statements[1]
    assert transaction.is_active is True

    if body_fails:
        with pytest.raises(RuntimeError, match=r"^synthetic body failure$"):
            fixture.throw(RuntimeError("synthetic body failure"))
    else:
        with pytest.raises(StopIteration):
            next(fixture)

    assert events == ["rollback", "dispose"]
    assert transaction.is_active is False
