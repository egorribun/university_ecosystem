"""Unit contract for the squashed MVP baseline revision (Tier 0 migration)."""

from __future__ import annotations

import ast
import asyncio
import importlib.util
import sys
from copy import deepcopy
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest

from tests.integration import test_mvp_baseline_schema_equivalence as schema_proof

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BASELINE_PATH = PROJECT_ROOT / "alembic" / "versions" / "202611020000_mvp_baseline.py"


def _load_baseline() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "mvp_baseline_under_test", BASELINE_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _Result:
    def __init__(self, row: tuple[Any, ...] | None) -> None:
        self._row = row

    def fetchone(self) -> tuple[Any, ...] | None:
        return self._row


class _Bind:
    def __init__(self, dialect: str, pg_cron_available: bool) -> None:
        self.dialect = type("Dialect", (), {"name": dialect})()
        self._pg_cron_available = pg_cron_available
        self.queries: list[str] = []

    def execute(self, statement: Any) -> _Result:
        sql = str(statement)
        self.queries.append(sql)
        if "pg_available_extensions" in sql and self._pg_cron_available:
            return _Result((1,))
        return _Result(None)


class _Op:
    def __init__(self, bind: _Bind) -> None:
        self._bind = bind
        self.executed: list[str] = []

    def get_bind(self) -> _Bind:
        return self._bind

    def execute(self, statement: str) -> None:
        self.executed.append(statement)


def test_baseline_revision_is_the_root_of_the_squashed_chain() -> None:
    module = _load_baseline()

    assert module.revision == "202611020000"
    assert module.down_revision is None
    assert module.branch_labels is None
    assert module.depends_on is None


def test_downgrade_is_irreversible_and_refuses_before_changing_schema() -> None:
    module = _load_baseline()

    assert module.downgrade_policy == "irreversible"
    with pytest.raises(RuntimeError) as raised:
        module.downgrade()
    assert str(raised.value) == module.downgrade_reason
    assert "consistent backup" in module.downgrade_reason


def test_upgrade_requires_postgresql_and_executes_nothing_elsewhere(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_baseline()
    op = _Op(_Bind("sqlite", pg_cron_available=False))
    monkeypatch.setattr(module, "op", op)

    with pytest.raises(RuntimeError, match="requires PostgreSQL"):
        module.upgrade()
    assert op.executed == []


def test_upgrade_creates_the_restored_and_delivery_once_objects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_baseline()
    op = _Op(_Bind("postgresql", pg_cron_available=False))
    monkeypatch.setattr(module, "op", op)

    module.upgrade()

    executed = "\n".join(op.executed)
    assert "CREATE ROLE ue_rls_bypass NOLOGIN" in executed
    assert "CREATE TABLE public.notification_delivery_once" in executed
    assert "uq_notification_delivery_once_claim UNIQUE NULLS NOT DISTINCT" in executed
    for index_name in (
        "ux_users_lower_email",
        "ix_user_profiles_full_name_lower",
        "ix_user_profiles_full_name_trgm",
        "idx_notifications_user_unread_created",
        "idx_messages_chat_created",
        "ix_stored_events_pending",
        "idx_active_sessions_user_valid",
        "ix_active_sessions_user_active_created",
    ):
        assert index_name in executed, index_name
    partitions = [s for s in op.executed if "PARTITION OF" in s]
    assert len(partitions) == 4 * 26
    assert not any("cron.schedule" in s for s in op.executed)


def test_upgrade_schedules_pg_cron_jobs_only_when_the_extension_is_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_baseline()
    op = _Op(_Bind("postgresql", pg_cron_available=True))
    monkeypatch.setattr(module, "op", op)

    module.upgrade()

    assert op.executed[-4:] == list(module._PG_CRON_STATEMENTS)
    assert op.executed[-4] == "CREATE EXTENSION IF NOT EXISTS pg_cron"
    assert sum("cron.schedule" in s for s in op.executed) == 3


# These controls exercise the real proof functions with synthetic dump/catalog
# inputs. They do not start containers, execute DDL, or replace the comparator.
# The 63 approved additions are independently enumerated, not derived from the
# implementation's broad matching expression or the baseline revision constants.
_PROOF_RETAINED_STATEMENT = "CREATE TABLE public.retained_control (id integer)"
_PROOF_REMOVED_INDEX = (
    "CREATE UNIQUE INDEX ix_users_email_lower ON public.users USING btree "
    "(lower((email)::text))"
)
_PROOF_PARENT_INDEXES = (
    (
        "CREATE UNIQUE INDEX ux_users_lower_email ON public.users USING btree "
        "(lower((email)::text))"
    ),
    (
        "CREATE INDEX ix_user_profiles_full_name_lower ON public.user_profiles "
        "USING btree (lower((full_name)::text) text_pattern_ops) "
        "WHERE (full_name IS NOT NULL)"
    ),
    (
        "CREATE INDEX ix_user_profiles_full_name_trgm ON public.user_profiles "
        "USING gin (full_name public.gin_trgm_ops) WHERE (full_name IS NOT NULL)"
    ),
    (
        "CREATE INDEX idx_notifications_user_unread_created ON ONLY "
        "public.notifications USING btree (user_id, created_at DESC) "
        "WHERE (read = false)"
    ),
    (
        "CREATE INDEX idx_messages_chat_created ON public.messages USING btree "
        "(chat_id, created_at DESC)"
    ),
    (
        "CREATE INDEX ix_stored_events_pending ON public.stored_events "
        "USING btree (status, created_at)"
    ),
    (
        "CREATE INDEX idx_active_sessions_user_valid ON public.active_sessions "
        "USING btree (user_id, revoked_at) WHERE (revoked_at IS NULL)"
    ),
    (
        "CREATE INDEX ix_active_sessions_user_active_created "
        "ON public.active_sessions USING btree (user_id, created_at) "
        "WHERE (revoked_at IS NULL)"
    ),
)
_PROOF_CLAIM_STATEMENTS = (
    (
        "CREATE TABLE public.notification_delivery_once (\n"
        "    id uuid NOT NULL,\n"
        "    notification_id uuid NOT NULL,\n"
        "    subscription_id uuid,\n"
        "    channel character varying(50) NOT NULL,\n"
        "    created_at timestamp with time zone DEFAULT now() NOT NULL\n"
        ")"
    ),
    (
        "ALTER TABLE ONLY public.notification_delivery_once ADD CONSTRAINT "
        "notification_delivery_once_pkey PRIMARY KEY (id)"
    ),
    (
        "ALTER TABLE ONLY public.notification_delivery_once ADD CONSTRAINT "
        "uq_notification_delivery_once_claim UNIQUE NULLS NOT DISTINCT "
        "(notification_id, subscription_id, channel)"
    ),
)
_PROOF_PARTITION_SUFFIXES = (
    "2026_05",
    "2026_06",
    "2026_07",
    "2026_08",
    "2026_09",
    "2026_10",
    "2026_11",
    "2026_12",
    "2027_01",
    "2027_02",
    "2027_03",
    "2027_04",
    "2027_05",
    "2027_06",
    "2027_07",
    "2027_08",
    "2027_09",
    "2027_10",
    "2027_11",
    "2027_12",
    "2028_01",
    "2028_02",
    "2028_03",
    "2028_04",
    "2028_05",
    "default",
)


def _proof_statement_inputs() -> tuple[list[str], list[str]]:
    additions = [*_PROOF_CLAIM_STATEMENTS, *_PROOF_PARENT_INDEXES]
    for suffix in _PROOF_PARTITION_SUFFIXES:
        table = f"notifications_{suffix}"
        child = f"{table}_user_id_created_at_idx1"
        additions.extend(
            (
                (
                    f"CREATE INDEX {child} ON public.{table} USING btree "
                    "(user_id, created_at DESC) WHERE (read = false)"
                ),
                (
                    "ALTER INDEX public.idx_notifications_user_unread_created "
                    f"ATTACH PARTITION public.{child}"
                ),
            )
        )
    assert len(additions) == len(set(additions)) == 63
    before = [_PROOF_RETAINED_STATEMENT, _PROOF_REMOVED_INDEX]
    after = [_PROOF_RETAINED_STATEMENT, *additions]
    return before, after


def _run_statement_proof(
    monkeypatch: pytest.MonkeyPatch, before: list[str], after: list[str]
) -> None:
    pre = object()
    baseline = object()
    built = SimpleNamespace(pre_squash=pre, baseline=baseline)
    dumps = {pre: ";\n".join(before) + ";", baseline: ";\n".join(after) + ";"}
    monkeypatch.setattr(schema_proof, "_dump", dumps.__getitem__)
    schema_proof.test_statement_level_schema_differs_only_by_the_audited_additions(
        built
    )


def _replace_proof_statement(
    statements: list[str], before: str, after: str
) -> list[str]:
    assert before != after
    assert sum(statement.count(before) for statement in statements) == 1
    changed = [statement.replace(before, after) for statement in statements]
    assert len(changed) == len(statements)
    assert changed != statements
    return changed


def test_schema_statement_proof_accepts_the_exact_finite_positive(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    before, after = _proof_statement_inputs()
    _run_statement_proof(monkeypatch, before, after)


@pytest.mark.parametrize(
    ("defect", "side", "before", "after"),
    [
        (
            "replacement-not-unique",
            "after",
            "CREATE UNIQUE INDEX ux_users_lower_email",
            "CREATE INDEX ux_users_lower_email",
        ),
        (
            "replacement-wrong-key",
            "after",
            _PROOF_PARENT_INDEXES[0],
            _PROOF_PARENT_INDEXES[0].replace("lower((email)::text)", "email"),
        ),
        (
            "missing-pattern-opclass",
            "after",
            "lower((full_name)::text) text_pattern_ops",
            "lower((full_name)::text)",
        ),
        (
            "wrong-trigram-method",
            "after",
            "USING gin (full_name public.gin_trgm_ops)",
            "USING btree (full_name public.gin_trgm_ops)",
        ),
        (
            "missing-profile-predicate",
            "after",
            _PROOF_PARENT_INDEXES[1],
            _PROOF_PARENT_INDEXES[1].replace(" WHERE (full_name IS NOT NULL)", ""),
        ),
        (
            "wrong-notification-order",
            "after",
            _PROOF_PARENT_INDEXES[3],
            _PROOF_PARENT_INDEXES[3].replace("created_at DESC", "created_at"),
        ),
        (
            "wrong-notification-predicate",
            "after",
            _PROOF_PARENT_INDEXES[3],
            _PROOF_PARENT_INDEXES[3].replace("read = false", "read = true"),
        ),
        (
            "wrong-message-key",
            "after",
            "(chat_id, created_at DESC)",
            "(sender_id, created_at DESC)",
        ),
        (
            "wrong-pending-table",
            "after",
            _PROOF_PARENT_INDEXES[5],
            _PROOF_PARENT_INDEXES[5].replace(
                "ON public.stored_events", "ON public.users"
            ),
        ),
        (
            "wrong-session-predicate",
            "after",
            _PROOF_PARENT_INDEXES[6],
            _PROOF_PARENT_INDEXES[6].replace(
                "revoked_at IS NULL", "revoked_at IS NOT NULL"
            ),
        ),
        (
            "claim-subscription-not-null",
            "after",
            "    subscription_id uuid,",
            "    subscription_id uuid NOT NULL,",
        ),
        (
            "claim-channel-bound",
            "after",
            "    channel character varying(50) NOT NULL,",
            "    channel character varying(51) NOT NULL,",
        ),
        (
            "claim-nulls-distinct",
            "after",
            "UNIQUE NULLS NOT DISTINCT",
            "UNIQUE",
        ),
        (
            "wrong-partition-attachment",
            "after",
            (
                "ATTACH PARTITION "
                "public.notifications_2026_05_user_id_created_at_idx1"
            ),
            "ATTACH PARTITION public.unrelated_index",
        ),
        (
            "allowed-name-in-unrelated-comment",
            "after",
            _PROOF_CLAIM_STATEMENTS[0],
            (
                "COMMENT ON TABLE public.retained_control IS "
                "'notification_delivery_once'"
            ),
        ),
        (
            "wrong-removed-definition",
            "before",
            _PROOF_REMOVED_INDEX,
            _PROOF_REMOVED_INDEX.replace("lower((email)::text)", "email"),
        ),
    ],
    ids=[
        "replacement-not-unique",
        "replacement-wrong-key",
        "missing-pattern-opclass",
        "wrong-trigram-method",
        "missing-profile-predicate",
        "wrong-notification-order",
        "wrong-notification-predicate",
        "wrong-message-key",
        "wrong-pending-table",
        "wrong-session-predicate",
        "claim-subscription-not-null",
        "claim-channel-bound",
        "claim-nulls-distinct",
        "wrong-partition-attachment",
        "allowed-name-in-unrelated-comment",
        "wrong-removed-definition",
    ],
)
def test_schema_statement_proof_rejects_shape_drift_with_the_same_counts(
    monkeypatch: pytest.MonkeyPatch,
    defect: str,
    side: str,
    before: str,
    after: str,
) -> None:
    original, baseline = _proof_statement_inputs()
    _run_statement_proof(monkeypatch, original, baseline)
    changed = _replace_proof_statement(
        original if side == "before" else baseline, before, after
    )

    with pytest.raises(AssertionError):
        _run_statement_proof(
            monkeypatch,
            changed if side == "before" else original,
            changed if side == "after" else baseline,
        )


def _proof_catalog_inputs() -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    before: dict[str, list[str]] = {name: [] for name in schema_proof.CATALOG_PROBES}
    before["relations"] = [repr(("users", "r", True, True, False, "p", "d", ""))]
    after = deepcopy(before)
    after["relations"].append(
        repr(("notification_delivery_once", "r", False, False, False, "p", "d", ""))
    )
    fields = (
        ("id", None, "NO", "uuid", None),
        ("notification_id", None, "NO", "uuid", None),
        ("subscription_id", None, "YES", "uuid", None),
        ("channel", None, "NO", "character varying", 50),
        ("created_at", "now()", "NO", "timestamp with time zone", None),
    )
    after["columns"] = [
        repr(
            (
                "notification_delivery_once",
                name,
                default,
                nullable,
                data_type,
                length,
                None,
                None,
            )
        )
        for name, default, nullable, data_type, length in fields
    ]
    # Index inheritance is present in pg_inherits without a table partition bound.
    after["partition_bounds"] = [
        repr(
            (
                f"notifications_{suffix}_user_id_created_at_idx1",
                "idx_notifications_user_unread_created",
                None,
            )
        )
        for suffix in _PROOF_PARTITION_SUFFIXES
    ]
    assert len(after["partition_bounds"]) == 26
    assert len(set(after["partition_bounds"])) == 26
    for rows in after.values():
        rows.sort()
    return before, after


def _run_catalog_proof(
    monkeypatch: pytest.MonkeyPatch,
    before: dict[str, list[str]],
    after: dict[str, list[str]],
) -> None:
    pre = object()
    baseline = object()
    built = SimpleNamespace(pre_squash=pre, baseline=baseline)
    facts = {pre: before, baseline: after}
    monkeypatch.setattr(schema_proof, "_probe", facts.__getitem__)
    schema_proof.test_catalog_facts_outside_the_additions_are_identical(built)


def test_schema_catalog_proof_accepts_unchanged_facts_and_exact_claim_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    before, after = _proof_catalog_inputs()
    _run_catalog_proof(monkeypatch, before, after)


@pytest.mark.parametrize(
    ("group", "identity", "position", "replacement"),
    [
        ("relations", "notification_delivery_once", 1, "p"),
        ("relations", "notification_delivery_once", 2, True),
        ("relations", "notification_delivery_once", 7, "{fillfactor=70}"),
        ("columns", "id", 4, "text"),
        ("columns", "notification_id", 3, "YES"),
        ("columns", "subscription_id", 3, "NO"),
        ("columns", "channel", 5, 51),
        ("columns", "created_at", 2, None),
    ],
)
def test_schema_catalog_proof_rejects_drift_inside_an_approved_object(
    monkeypatch: pytest.MonkeyPatch,
    group: str,
    identity: str,
    position: int,
    replacement: object,
) -> None:
    before, after = _proof_catalog_inputs()
    _run_catalog_proof(monkeypatch, before, after)
    changed = deepcopy(after)
    matches = 0
    for index, rendered in enumerate(changed[group]):
        row = list(ast.literal_eval(rendered))
        key = row[0] if group == "relations" else row[1]
        if key == identity:
            assert row[position] != replacement
            row[position] = replacement
            changed[group][index] = repr(tuple(row))
            matches += 1
    assert matches == 1
    changed[group].sort()
    assert changed != after

    with pytest.raises(AssertionError):
        _run_catalog_proof(monkeypatch, before, changed)


def test_schema_statement_proof_still_rejects_unapproved_removed_objects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    before, after = _proof_statement_inputs()
    _run_statement_proof(monkeypatch, before, after)
    changed = [item for item in after if item != _PROOF_RETAINED_STATEMENT]
    assert len(changed) == len(after) - 1

    with pytest.raises(AssertionError):
        _run_statement_proof(monkeypatch, before, changed)


def test_schema_catalog_proof_still_rejects_unapproved_relation_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    before, after = _proof_catalog_inputs()
    _run_catalog_proof(monkeypatch, before, after)
    changed = deepcopy(after)
    changed["relations"].remove(before["relations"][0])
    changed["relations"].append(repr(("users", "v", True, True, False, "p", "d", "")))
    changed["relations"].sort()

    with pytest.raises(AssertionError):
        _run_catalog_proof(monkeypatch, before, changed)


@pytest.mark.parametrize(
    "inherited",
    ["DATABASE_URL_FILE", "database_url", "ENV_FILE_PATH"],
)
def test_schema_proof_child_keeps_the_owned_database_url_authoritative(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, inherited: str
) -> None:
    owned_url = "postgresql+asyncpg://127.0.0.1:5432/owned_schema_proof"
    value = (
        "postgresql+asyncpg://127.0.0.1:1/not_the_owned_database"
        if inherited == "database_url"
        else str(tmp_path / "must-not-be-read")
    )
    monkeypatch.setenv(inherited, value)
    captured: list[tuple[list[str], Path, dict[str, object]]] = []

    async def capture(
        argv: list[str], cwd: Path, env: dict[str, str] | None = None
    ) -> tuple[int, bytes, bytes]:
        assert env is not None
        captured.append(
            (
                argv,
                cwd,
                {
                    "owned_url": env.get("DATABASE_URL") == owned_url,
                    "url_names": tuple(
                        name for name in env if name.casefold() == "database_url"
                    ),
                    "file_present": any(
                        name.casefold() == "database_url_file" for name in env
                    ),
                    "dotenv_disabled": env.get("ENV_FILE_PATH") == "",
                },
            )
        )
        return 0, b"controlled-output", b""

    monkeypatch.setattr(schema_proof, "_run_fixed_argv", capture)

    completed = schema_proof._alembic(tmp_path, owned_url, "check")

    assert completed.returncode == 0
    assert completed.stdout == "controlled-output"
    assert completed.stderr == ""
    assert len(captured) == 1
    argv, cwd, observed = captured[0]
    assert argv == [sys.executable, "-m", "alembic", "check"]
    assert cwd == tmp_path
    assert observed == {
        "owned_url": True,
        "url_names": ("DATABASE_URL",),
        "file_present": False,
        "dotenv_disabled": True,
    }


@pytest.mark.parametrize("outcome", [0, 7, "timeout"])
def test_schema_proof_child_is_bounded_and_reaped_without_changing_its_result(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, outcome: int | str
) -> None:
    spawned: list[tuple[tuple[str, ...], dict[str, Any]]] = []
    deadlines: list[float] = []
    failure = TimeoutError("controlled schema-proof child deadline")

    class Process:
        def __init__(self) -> None:
            self.returncode: int | None = None
            self.killed = False
            self.reaped = False

        async def communicate(self) -> tuple[bytes, bytes]:
            if outcome == "timeout" and not self.killed:
                raise failure
            self.returncode = -9 if self.killed else int(outcome)
            self.reaped = True
            return b"controlled-stdout", b"controlled-stderr"

        def kill(self) -> None:
            self.killed = True
            self.returncode = -9

        async def wait(self) -> int:
            self.reaped = True
            assert self.returncode is not None
            return self.returncode

    process = Process()

    async def create(*argv: str, **kwargs: Any) -> Process:
        spawned.append((argv, kwargs))
        return process

    async def bounded(awaitable: Any, timeout: float | None) -> Any:
        assert not isinstance(timeout, bool)
        assert isinstance(timeout, (int, float))
        assert 0 < timeout <= 300
        deadlines.append(timeout)
        return await awaitable

    monkeypatch.setattr(schema_proof.asyncio, "create_subprocess_exec", create)
    monkeypatch.setattr(schema_proof.asyncio, "wait_for", bounded)
    argv = ["controlled-python", "-m", "alembic", "check"]
    operation = schema_proof._run_fixed_argv(argv, tmp_path, {"CONTROL": "1"})

    if outcome == "timeout":
        with pytest.raises(TimeoutError) as caught:
            asyncio.run(operation)
        assert caught.value is failure
        assert process.killed
        assert process.reaped
    else:
        result = asyncio.run(operation)
        assert result == (outcome, b"controlled-stdout", b"controlled-stderr")
        assert process.reaped
        assert not process.killed

    assert len(deadlines) == (2 if outcome == "timeout" else 1)
    assert spawned == [
        (
            tuple(argv),
            {
                "cwd": tmp_path,
                "env": {"CONTROL": "1"},
                "stdout": asyncio.subprocess.PIPE,
                "stderr": asyncio.subprocess.PIPE,
            },
        )
    ]
