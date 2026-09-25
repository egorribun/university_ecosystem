"""Offline contracts for the read-only BE-02 catalog preflight command."""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

import pytest

import scripts.be02_catalog_preflight as preflight


def test_loads_the_reviewed_migration_specs() -> None:
    migration = preflight.load_migration()

    assert migration.revision == "202609250001"
    assert len(migration.DEFAULT_SPECS) == 12


def test_rejects_a_missing_migration_file(tmp_path) -> None:
    with pytest.raises(FileNotFoundError):
        preflight.load_migration(tmp_path / "missing.py")


def test_uses_the_synchronous_driver_for_async_urls() -> None:
    assert (
        preflight.sync_url("postgresql+asyncpg://u@h/db")
        == "postgresql+psycopg://u@h/db"
    )
    assert preflight.sync_url("postgresql+psycopg://u@h/db") == (
        "postgresql+psycopg://u@h/db"
    )


def _fake_migration(states: dict[str, Any]) -> SimpleNamespace:
    specs = [
        SimpleNamespace(table="t", column=name, expression=f"expr-{name}")
        for name in states
    ]

    def catalog_state(_connection: object, spec: Any, schema: str) -> Any:
        assert schema == "app"
        state = states[spec.column]
        if isinstance(state, Exception):
            raise state
        return state

    def validate_state(spec: Any, state: Any) -> None:
        if state.default_sql == "bad":
            raise RuntimeError(f"conflicting server default on t.{spec.column}")

    return SimpleNamespace(
        DEFAULT_SPECS=specs,
        _target_schema=lambda _connection: "app",
        _catalog_state=catalog_state,
        _validate_state=validate_state,
    )


def test_classifies_pending_converged_and_blocked_columns() -> None:
    migration = _fake_migration(
        {
            "fresh": SimpleNamespace(default_sql=None),
            "done": SimpleNamespace(default_sql="now()"),
            "drift": SimpleNamespace(default_sql="bad"),
            "gone": RuntimeError("BE-02 phase four requires t.gone"),
        }
    )

    results = preflight.inspect_catalog(object(), migration)

    assert results == [
        preflight.ColumnResult("app.t.fresh", "pending", "expr-fresh"),
        preflight.ColumnResult("app.t.done", "converged", "now()"),
        preflight.ColumnResult(
            "app.t.drift", "blocked", "conflicting server default on t.drift"
        ),
        preflight.ColumnResult(
            "app.t.gone", "blocked", "BE-02 phase four requires t.gone"
        ),
    ]


def test_main_requires_a_database_url(monkeypatch, capsys) -> None:
    monkeypatch.delenv("BE02_TARGET_URL", raising=False)

    assert preflight.main(["--database-url-env", "BE02_TARGET_URL"]) == 2
    assert "BE02_TARGET_URL is not set" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("statuses", "exit_code"),
    [(["pending", "converged"], 0), (["pending", "blocked"], 1)],
)
def test_main_reports_json_and_fails_closed_on_drift(
    monkeypatch, capsys, statuses: list[str], exit_code: int
) -> None:
    results = [
        preflight.ColumnResult(f"app.t.c{index}", status, "detail")
        for index, status in enumerate(statuses)
    ]
    seen: list[str] = []

    def fake_run(url: str, migration: object) -> list[preflight.ColumnResult]:
        seen.append(url)
        return results

    monkeypatch.setenv("DATABASE_URL", " postgresql+asyncpg://u@h/db ")
    monkeypatch.setattr(preflight, "run", fake_run)
    monkeypatch.setattr(preflight, "load_migration", lambda: object())

    assert preflight.main([]) == exit_code
    assert seen == ["postgresql+asyncpg://u@h/db"]
    report = json.loads(capsys.readouterr().out)
    assert [row["status"] for row in report] == statuses
