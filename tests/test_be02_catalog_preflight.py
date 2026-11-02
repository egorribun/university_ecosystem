"""Retirement contracts and retained read-only BE-02 helper behavior."""

from __future__ import annotations

import os
from types import SimpleNamespace
from typing import Any

import pytest

import scripts.be02_catalog_preflight as preflight


def test_default_phase_refuses_with_an_actionable_message() -> None:
    with pytest.raises(RuntimeError) as failure:
        preflight.load_migration()

    message = str(failure.value)
    assert "retired by ADR-051" in message
    assert "docs/adr/ADR-051-mvp-migration-baseline-squash.md" in message
    assert "scripts/quality/audit_model_defaults.py" in message
    assert "not deployed-catalog proof" in message
    assert "BE-02 remains open" in message


@pytest.mark.parametrize("phase", [True, False, 0, 2, 5])
def test_invalid_phase_remains_rejected(phase: int) -> None:
    with pytest.raises(ValueError, match="phase 2 is Python-only") as failure:
        preflight.load_migration(phase)
    assert "Historical BE-02 DDL phases were 1, 3, and 4 (now retired)" in str(
        failure.value
    )


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


@pytest.mark.parametrize("configured", [False, True])
def test_main_refuses_before_reading_database_environment(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    configured: bool,
) -> None:
    if configured:
        monkeypatch.setenv(
            "BE02_TARGET_URL", "postgresql+psycopg://localhost/synthetic"
        )
    else:
        monkeypatch.delenv("BE02_TARGET_URL", raising=False)

    def forbidden(*_args: object, **_kwargs: object) -> None:
        pytest.fail("retired CLI read database configuration or called a DB helper")

    environment_get = type(os.environ).__getitem__

    def guarded_environment_get(environment: object, key: str) -> str:
        if key in {"DATABASE_URL", "BE02_TARGET_URL"}:
            pytest.fail("retired CLI read database configuration")
        return environment_get(environment, key)

    monkeypatch.setattr(type(os.environ), "__getitem__", guarded_environment_get)
    monkeypatch.setattr(preflight, "run", forbidden)
    monkeypatch.setattr(preflight, "load_migration", forbidden)

    assert preflight.main(["--database-url-env", "BE02_TARGET_URL"]) == 2
    output = capsys.readouterr()
    assert output.out == ""
    assert "retired by ADR-051" in output.err
    assert "not deployed-catalog proof" in output.err
    assert "BE-02 remains open" in output.err
