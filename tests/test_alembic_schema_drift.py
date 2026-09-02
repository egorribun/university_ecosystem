"""Regression tests for the narrowly scoped Alembic nullability adapter."""

from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any

from alembic.operations import ops

from scripts.quality import alembic_schema_drift


@dataclass
class _Result:
    row: tuple[bool, str] | None

    def first(self) -> tuple[bool, str] | None:
        return self.row


class _Dialect:
    name = "postgresql"


class _Connection:
    dialect = _Dialect()

    def __init__(self, checks: dict[str, tuple[bool, str] | None]) -> None:
        self._checks = checks

    def execute(self, _statement: Any, parameters: dict[str, str]) -> _Result:
        return _Result(self._checks.get(parameters["constraint_name"]))


class _PartitionConnection:
    class dialect:
        name = "postgresql"

    def __init__(self, names: tuple[str, ...]) -> None:
        self._names = names
        self.query_count = 0
        self.statements: list[str] = []

    def execute(self, _statement: Any) -> list[tuple[str]]:
        self.query_count += 1
        self.statements.append(str(_statement))
        return [(name,) for name in self._names]


class _MigrationContext:
    def __init__(self, connection: Any) -> None:
        self.connection = connection


def _valid_checks() -> dict[str, tuple[bool, str]]:
    return {
        constraint: (True, f"CHECK (({column.upper()} IS NOT NULL))")
        for _table, column, constraint in alembic_schema_drift._CHECK_BACKED_COLUMNS
    }


def test_validated_check_filters_only_nullable_change() -> None:
    nullable_only = ops.AlterColumnOp(
        "mfa_challenges",
        "flow",
        existing_nullable=True,
        modify_nullable=False,
    )
    type_change = ops.AlterColumnOp(
        "mfa_challenges",
        "method",
        existing_nullable=True,
        modify_nullable=False,
        modify_type="different",
    )
    unrelated = ops.AlterColumnOp(
        "users",
        "email",
        existing_nullable=True,
        modify_nullable=False,
    )
    table_ops = ops.ModifyTableOps(
        "mfa_challenges", [nullable_only, type_change, unrelated]
    )
    directive = type(
        "Directive",
        (),
        {"upgrade_ops_list": [ops.UpgradeOps([table_ops])]},
    )()

    alembic_schema_drift.filter_check_backed_nullable_diffs(
        _MigrationContext(_Connection(_valid_checks())),
        None,
        [directive],
    )

    assert table_ops.ops == [type_change, unrelated]
    assert type_change.modify_nullable is False
    assert unrelated.modify_nullable is False


def test_unvalidated_or_mismatched_check_does_not_filter() -> None:
    checks = _valid_checks()
    checks["ck_mfa_challenges_flow_not_null"] = (
        False,
        "CHECK ((FLOW IS NOT NULL))",
    )
    checks["ck_mfa_challenges_method_not_null"] = (
        True,
        "CHECK ((METHOD IS NULL))",
    )
    flow = ops.AlterColumnOp(
        "mfa_challenges",
        "flow",
        existing_nullable=True,
        modify_nullable=False,
    )
    method = ops.AlterColumnOp(
        "mfa_challenges",
        "method",
        existing_nullable=True,
        modify_nullable=False,
    )
    table_ops = ops.ModifyTableOps("mfa_challenges", [flow, method])
    directive = type(
        "Directive",
        (),
        {"upgrade_ops_list": [ops.UpgradeOps([table_ops])]},
    )()

    alembic_schema_drift.filter_check_backed_nullable_diffs(
        _MigrationContext(_Connection(checks)),
        None,
        [directive],
    )

    assert table_ops.ops == [flow, method]


def test_non_postgresql_connection_never_filters_contract_diffs() -> None:
    class _SQLiteConnection:
        class dialect:
            name = "sqlite"

    operation = ops.AlterColumnOp(
        "mfa_challenges",
        "flow",
        existing_nullable=True,
        modify_nullable=False,
    )
    table_ops = ops.ModifyTableOps("mfa_challenges", [operation])
    directive = type(
        "Directive",
        (),
        {"upgrade_ops_list": [ops.UpgradeOps([table_ops])]},
    )()

    alembic_schema_drift.filter_check_backed_nullable_diffs(
        _MigrationContext(_SQLiteConnection()),
        None,
        [directive],
    )

    assert table_ops.ops == [operation]


def test_partition_discovery_excludes_only_reflected_partition_objects() -> None:
    connection = _PartitionConnection(("notifications_2026_08",))
    callback = alembic_schema_drift.build_partition_aware_include_object(connection)

    # Building the callback must not execute a metadata query.  In the async
    # Alembic CLI, an eager query would autobegin the SQLAlchemy connection
    # before ``context.configure`` and make migrations using
    # ``autocommit_block`` fail with no Alembic transaction handle.
    assert connection.query_count == 0

    reflected_partition = SimpleNamespace(name="notifications_2026_08")
    reflected_index = SimpleNamespace(
        table=SimpleNamespace(name="notifications_2026_08")
    )
    reflected_partition_fk = SimpleNamespace(
        elements=(SimpleNamespace(target_fullname="notifications_2026_08.id"),),
        table=SimpleNamespace(name="notification_deliveries"),
    )
    reflected_parent = SimpleNamespace(name="notifications")

    assert (
        callback(reflected_partition, "notifications_2026_08", "table", True, None)
        is False
    )
    assert connection.query_count == 1
    assert "parent.relkind = 'p'" in connection.statements[0]
    assert "child.relispartition" in connection.statements[0]
    assert callback(reflected_index, "partition_idx", "index", True, None) is False
    assert (
        callback(
            reflected_partition_fk,
            "partition_fk",
            "foreign_key_constraint",
            True,
            None,
        )
        is False
    )
    assert callback(reflected_parent, "notifications", "table", True, None) is True
    assert connection.query_count == 1
    assert (
        callback(reflected_partition, "notifications_2026_08", "table", False, None)
        is True
    )


def test_partition_discovery_is_noop_for_non_postgresql_connections() -> None:
    class _SQLiteConnection:
        class dialect:
            name = "sqlite"

        def execute(self, _statement: Any) -> None:
            raise AssertionError("SQLite must not query pg_inherits")

    callback = alembic_schema_drift.build_partition_aware_include_object(
        _SQLiteConnection()
    )
    assert (
        callback(SimpleNamespace(name="events"), "events", "table", True, None) is True
    )
