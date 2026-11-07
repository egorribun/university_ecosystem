from __future__ import annotations

import os
from types import ModuleType, SimpleNamespace
from typing import Any, cast

import pytest
import sqlalchemy as sa

import scripts.be02_catalog_preflight as preflight


@pytest.mark.parametrize("phase", [1, 3, 4])
def test_retired_phases_refuse_before_import_or_database_access(
    monkeypatch: pytest.MonkeyPatch, phase: int
) -> None:
    def forbidden(*_args: object, **_kwargs: object) -> None:
        pytest.fail("retired phase attempted import or database access")

    monkeypatch.setattr("importlib.util.spec_from_file_location", forbidden)
    monkeypatch.setattr(sa, "create_engine", forbidden)
    with pytest.raises(RuntimeError) as failure:
        preflight.load_migration(phase)
    message = str(failure.value)
    assert "retired by ADR-051" in message
    assert "baseline 202611020000 has no pre-squash upgrade path" in message
    assert "scripts/quality/audit_model_defaults.py" in message
    assert "not deployed-catalog proof" in message
    assert "BE-02 remains open" in message


def test_phase_two_is_not_a_selectable_preflight_phase(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(
        ValueError,
        match="phase 2 is Python-only and has no catalog DDL",
    ):
        preflight.load_migration(2)

    with pytest.raises(SystemExit) as error:
        preflight.main(["--phase", "2"])

    assert error.value.code == 2
    assert "invalid choice" in capsys.readouterr().err


def test_help_explains_retirement_without_database_configuration_or_access(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def forbidden(*_args: object, **_kwargs: object) -> None:
        pytest.fail("retired help attempted migration loading or database access")

    environment_get = type(os.environ).__getitem__

    def guarded_environment_get(environment: object, key: str) -> str:
        if key in {"DATABASE_URL", "BE02_TARGET_URL"}:
            pytest.fail("retired help read database configuration")
        return environment_get(environment, key)

    monkeypatch.setattr(type(os.environ), "__getitem__", guarded_environment_get)
    monkeypatch.setattr(preflight, "load_migration", forbidden)
    monkeypatch.setattr(preflight, "run", forbidden)
    monkeypatch.setattr(sa, "create_engine", forbidden)
    with pytest.raises(SystemExit) as error:
        preflight.main(["--database-url-env", "BE02_TARGET_URL", "--help"])

    captured = capsys.readouterr()
    output = " ".join(captured.out.split())
    assert error.value.code == 0
    assert captured.err == ""
    assert "--phase {1,3,4}" in output
    assert "--database-url-env" in output
    assert "retired historical phase option retained for compatibility only" in output
    assert "no phase is executed" in output
    assert "variable is not read and no database URL is used" in output
    assert "default: 4" in output
    assert "phase 2 is Python-only and has no catalog DDL" in output


@pytest.mark.parametrize("phase", [1, 3, 4])
def test_run_starts_read_only_transaction_before_inspection_and_disposes(
    monkeypatch: pytest.MonkeyPatch, phase: int
) -> None:
    events: list[str] = []
    results = [preflight.ColumnResult("app.sample.enabled", "pending", "true", phase)]

    class _Transaction:
        def __enter__(self) -> _Transaction:
            events.append("transaction-enter")
            return self

        def __exit__(self, *_exc: object) -> None:
            events.append("transaction-exit")

    class _Connection:
        def __enter__(self) -> _Connection:
            events.append("connection-enter")
            return self

        def __exit__(self, *_exc: object) -> None:
            events.append("connection-exit")

        def begin(self) -> _Transaction:
            return _Transaction()

        def execute(self, statement: sa.sql.elements.TextClause) -> None:
            events.append(str(statement))

    class _Engine:
        def connect(self) -> _Connection:
            return _Connection()

        def dispose(self) -> None:
            events.append("dispose")

    migration = cast(ModuleType, SimpleNamespace(BE02_PHASE=phase))
    monkeypatch.setattr(sa, "create_engine", lambda _url: _Engine())

    def inspect(_connection: object, _selected: object) -> list[preflight.ColumnResult]:
        events.append("inspect")
        return results

    monkeypatch.setattr(preflight, "inspect_catalog", inspect)

    assert (
        preflight.run("postgresql+asyncpg://localhost/synthetic", migration) == results
    )
    read_only_index = events.index("SET TRANSACTION READ ONLY")
    assert read_only_index < events.index("inspect")
    assert events[-1] == "dispose"


@pytest.mark.parametrize("phase", [1, 3])
@pytest.mark.parametrize("relation_kind", ["r", "p"])
def test_inspects_legacy_phase_catalog_without_writing(
    phase: int, relation_kind: str
) -> None:
    spec = SimpleNamespace(table="sample", column="enabled", server_default="true")
    state = SimpleNamespace(default_sql=None, not_null=False)
    calls: list[str] = []

    def catalog_state(_connection: object, _spec: object) -> Any:
        calls.append("catalog")
        return state

    def validate_default(_spec: object, _state: object) -> None:
        calls.append("default")

    def null_count(_connection: object, _spec: object) -> int:
        calls.append("null-count")
        return 2

    def matching_check(_connection: object, _spec: object) -> tuple[str, bool, bool]:
        calls.append("check")
        return "ck_sample_enabled", False, False

    migration = SimpleNamespace(
        BE02_PHASE=phase,
        DEFAULT_SPECS=(spec,),
        _catalog_state=catalog_state,
        _validate_existing_default=validate_default,
        _null_count=null_count,
        _matching_check=matching_check,
    )
    connection = _CurrentSchemaConnection(relation_kind=relation_kind)

    results = preflight.inspect_catalog(connection, cast(ModuleType, migration))

    assert results == [
        preflight.ColumnResult(
            "app.sample.enabled",
            "pending",
            "server default true; backfill 2 NULL row(s); "
            "NOT NULL contract; validate check ck_sample_enabled",
            phase,
        )
    ]
    assert calls == ["catalog", "default", "null-count", "check"]
    assert connection.statements[0] == "SELECT current_schema()"
    assert len(connection.statements) == 2
    assert "pg_catalog.pg_class" in connection.statements[1]


@pytest.mark.parametrize("phase", [1, 3])
def test_marks_legacy_phase_column_converged_only_after_all_contracts(
    phase: int,
) -> None:
    spec = SimpleNamespace(table="sample", column="enabled", server_default="true")
    state = SimpleNamespace(default_sql="true", not_null=True)
    migration = SimpleNamespace(
        BE02_PHASE=phase,
        DEFAULT_SPECS=(spec,),
        _catalog_state=lambda _connection, _spec: state,
        _validate_existing_default=lambda _spec, _state: None,
        _null_count=lambda _connection, _spec: 0,
        _matching_check=lambda _connection, _spec: (None, False, True),
    )

    results = preflight.inspect_catalog(
        _CurrentSchemaConnection(), cast(ModuleType, migration)
    )

    assert results == [
        preflight.ColumnResult("app.sample.enabled", "converged", "true", phase)
    ]


@pytest.mark.parametrize("phase", [1, 3])
@pytest.mark.parametrize("relation_kind", ["v", "m", "f", None])
def test_blocks_non_table_targets_before_inspecting_columns(
    phase: int, relation_kind: str | None
) -> None:
    catalog_calls: list[str] = []
    spec = SimpleNamespace(table="sample", column="enabled", server_default="true")

    def catalog_state(*_args: Any) -> SimpleNamespace:
        catalog_calls.append("catalog")
        return SimpleNamespace(default_sql=None, not_null=False)

    def null_count(*_args: Any) -> int:
        catalog_calls.append("null-count")
        return 0

    def matching_check(*_args: Any) -> tuple[None, bool, bool]:
        catalog_calls.append("check")
        return None, False, True

    migration = SimpleNamespace(
        BE02_PHASE=phase,
        DEFAULT_SPECS=(spec,),
        _catalog_state=catalog_state,
        _validate_existing_default=lambda *_args: catalog_calls.append("default"),
        _null_count=null_count,
        _matching_check=matching_check,
    )
    connection = _CurrentSchemaConnection(relation_kind=relation_kind)

    results = preflight.inspect_catalog(connection, cast(ModuleType, migration))

    assert len(results) == 1
    assert results[0].status == "blocked"
    assert "ordinary or partitioned table" in results[0].detail
    assert catalog_calls == []


@pytest.mark.parametrize(
    "arguments", [[], ["--phase", "1"], ["--phase", "3"], ["--phase", "4"]]
)
def test_cli_refuses_retired_phases_before_loading_or_connecting(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    arguments: list[str],
) -> None:
    def forbidden(*_args: object, **_kwargs: object) -> None:
        pytest.fail("retired CLI attempted migration loading or database access")

    monkeypatch.setattr(preflight, "load_migration", forbidden)
    monkeypatch.setattr(preflight, "run", forbidden)
    monkeypatch.setattr(sa, "create_engine", forbidden)
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://localhost/synthetic")

    assert preflight.main(arguments) == 2
    output = capsys.readouterr()
    assert output.out == ""
    assert "retired by ADR-051" in output.err
    assert "not deployed-catalog proof" in output.err


class _CurrentSchemaResult:
    def __init__(self, value: str | None) -> None:
        self.value = value

    def scalar_one_or_none(self) -> str | None:
        return self.value


class _CurrentSchemaConnection:
    def __init__(self, relation_kind: str | None = "r") -> None:
        self.statements: list[str] = []
        self.relation_kind = relation_kind

    def execute(
        self,
        statement: sa.sql.elements.TextClause,
        _parameters: dict[str, Any] | None = None,
    ) -> _CurrentSchemaResult:
        sql = str(statement)
        self.statements.append(sql)
        if "pg_catalog.pg_class" in sql:
            return _CurrentSchemaResult(self.relation_kind)
        return _CurrentSchemaResult("app")
