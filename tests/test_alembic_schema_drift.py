"""Regression tests for the narrowly scoped Alembic nullability adapter."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any

import pytest
from alembic.operations import ops

from app.core.db import schema_drift as alembic_schema_drift


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


def test_table_that_loses_every_operation_is_dropped_from_the_diff() -> None:
    flow = ops.AlterColumnOp(
        "mfa_challenges",
        "flow",
        existing_nullable=True,
        modify_nullable=False,
    )
    emptied = ops.ModifyTableOps("mfa_challenges", [flow])
    unrelated = ops.AlterColumnOp(
        "users",
        "email",
        existing_nullable=True,
        modify_nullable=False,
    )
    kept = ops.ModifyTableOps("users", [unrelated])
    upgrade_ops = ops.UpgradeOps([emptied, kept])
    directive = type("Directive", (), {"upgrade_ops_list": [upgrade_ops]})()

    alembic_schema_drift.filter_check_backed_nullable_diffs(
        _MigrationContext(_Connection(_valid_checks())),
        None,
        [directive],
    )

    assert upgrade_ops.ops == [kept]
    assert kept.ops == [unrelated]


def test_container_without_an_operation_list_is_left_untouched() -> None:
    container = SimpleNamespace(ops=("not", "mutable"))

    alembic_schema_drift._filter_container(container, frozenset({("t", "c")}))

    assert container.ops == ("not", "mutable")


def test_foreign_key_is_kept_when_no_element_targets_a_partition() -> None:
    connection = _PartitionConnection(("notifications_2026_08",))
    callback = alembic_schema_drift.build_partition_aware_include_object(connection)
    foreign_key = SimpleNamespace(
        elements=(
            SimpleNamespace(target_fullname="public.users.id"),
            SimpleNamespace(target_fullname="groups.id"),
        ),
        table=SimpleNamespace(name="notification_deliveries"),
    )

    assert (
        callback(foreign_key, "deliveries_fk", "foreign_key_constraint", True, None)
        is True
    )


class _RecordingConnection:
    """PostgreSQL stand-in that records every check lookup it receives."""

    dialect = _Dialect()

    def __init__(self, checks: dict[str, tuple[bool, str] | None]) -> None:
        self._checks = checks
        self.statements: list[str] = []
        self.parameters: list[dict[str, str]] = []

    def execute(self, statement: Any, parameters: dict[str, str]) -> _Result:
        self.statements.append(str(statement))
        self.parameters.append(dict(parameters))
        return _Result(self._checks.get(parameters["constraint_name"]))


def test_validated_check_lookup_binds_table_and_constraint_names() -> None:
    connection = _RecordingConnection(_valid_checks())

    validated = alembic_schema_drift.validated_mfa_check_columns(connection)

    expected = alembic_schema_drift._CHECK_BACKED_COLUMNS
    assert validated == alembic_schema_drift._CHECK_BACKED_KEYS
    assert connection.parameters == [
        {"table_name": table, "constraint_name": constraint}
        for table, _column, constraint in expected
    ]
    for statement in connection.statements:
        assert "FROM pg_constraint AS c" in statement
        assert "c.conrelid = to_regclass(:table_name)" in statement
        assert "c.conname = :constraint_name" in statement
        assert "c.contype = 'c'" in statement
        assert "convalidated, pg_get_constraintdef(c.oid)" in statement


def test_dialect_without_a_name_is_treated_as_not_postgresql() -> None:
    class _NamelessDialect:
        pass

    class _NamelessConnection:
        dialect = _NamelessDialect()

        def execute(self, *_args: Any) -> None:
            raise AssertionError("an unknown dialect must not be queried")

    connection = _NamelessConnection()

    assert alembic_schema_drift.validated_mfa_check_columns(connection) == frozenset()
    assert alembic_schema_drift.postgres_partition_table_names(connection) == (
        frozenset()
    )


def test_filtered_nullable_diff_is_logged_with_table_and_column(
    caplog: pytest.LogCaptureFixture,
) -> None:
    flow = ops.AlterColumnOp(
        "mfa_challenges",
        "flow",
        existing_nullable=True,
        modify_nullable=False,
    )
    directive = SimpleNamespace(
        upgrade_ops_list=[
            ops.UpgradeOps([ops.ModifyTableOps("mfa_challenges", [flow])])
        ]
    )

    with caplog.at_level(logging.INFO, logger=alembic_schema_drift.logger.name):
        alembic_schema_drift.filter_check_backed_nullable_diffs(
            _MigrationContext(_Connection(_valid_checks())),
            None,
            [directive],
        )

    assert [record.getMessage() for record in caplog.records] == [
        "Treating validated MFA check as NOT NULL: mfa_challenges.flow"
    ]


def test_non_column_operations_survive_filtering() -> None:
    flow = ops.AlterColumnOp(
        "mfa_challenges",
        "flow",
        existing_nullable=True,
        modify_nullable=False,
    )
    drop_index = ops.DropIndexOp("ix_mfa_challenges_flow", "mfa_challenges")
    table_ops = ops.ModifyTableOps("mfa_challenges", [flow, drop_index])
    directive = SimpleNamespace(upgrade_ops_list=[ops.UpgradeOps([table_ops])])

    alembic_schema_drift.filter_check_backed_nullable_diffs(
        _MigrationContext(_Connection(_valid_checks())),
        None,
        [directive],
    )

    assert table_ops.ops == [drop_index]


def test_objects_without_the_optional_attributes_are_tolerated() -> None:
    # A container without ``ops`` and a directive without ``upgrade_ops_list``
    # are simply skipped; a migration context without a connection is a no-op.
    alembic_schema_drift._filter_container(SimpleNamespace(), frozenset({("t", "c")}))
    alembic_schema_drift.filter_check_backed_nullable_diffs(
        _MigrationContext(_Connection(_valid_checks())), None, [SimpleNamespace()]
    )
    alembic_schema_drift.filter_check_backed_nullable_diffs(
        SimpleNamespace(), None, [SimpleNamespace()]
    )


def test_foreign_key_to_schema_qualified_partition_is_excluded() -> None:
    connection = _PartitionConnection(("notifications_2026_08",))
    callback = alembic_schema_drift.build_partition_aware_include_object(connection)
    parent_table = SimpleNamespace(name="notification_deliveries")

    def _foreign_key(target: str) -> SimpleNamespace:
        return SimpleNamespace(
            elements=(SimpleNamespace(target_fullname=target),), table=parent_table
        )

    for target in (
        "notifications_2026_08.id",
        "public.notifications_2026_08.id",
        "catalog.public.notifications_2026_08.id",
    ):
        assert (
            callback(_foreign_key(target), "fk", "foreign_key_constraint", True, None)
            is False
        )
    for target in ("public.notifications.id", "notifications_2026_08_extra.id"):
        assert (
            callback(_foreign_key(target), "fk", "foreign_key_constraint", True, None)
            is True
        )


def test_foreign_key_without_elements_falls_back_to_its_owning_table() -> None:
    connection = _PartitionConnection(("notifications_2026_08",))
    callback = alembic_schema_drift.build_partition_aware_include_object(connection)

    bare = SimpleNamespace(table=SimpleNamespace(name="notification_deliveries"))
    on_partition = SimpleNamespace(table=SimpleNamespace(name="notifications_2026_08"))

    assert callback(bare, "fk", "foreign_key_constraint", True, None) is True
    assert callback(on_partition, "fk", "foreign_key_constraint", True, None) is False
