"""Fail-closed contracts for the bounded, diagnostic-only Alembic CI consumer."""

from __future__ import annotations

import hashlib
import json
import re
import runpy
import shlex
import sys
from pathlib import Path

import pytest
import yaml

WORKFLOW = Path(__file__).resolve().parents[1] / ".github/workflows/ci.yml"


def _steps():
    job = yaml.safe_load(WORKFLOW.read_text())["jobs"]["alembic-migrations"]
    steps = job["steps"]
    original = next(s for s in steps if s.get("id") == "migration-squawk")
    diagnostic = next(s for s in steps if s.get("id") == "migration-ddl-evidence")
    return job, steps, original, diagnostic


def _squawk_args(script):
    match = re.search(r"squawk_args=\(\n(.*?)\n\)", script, re.DOTALL)
    assert match is not None
    return shlex.split(match.group(1))


def test_consumer_keeps_original_gate_context_budget_and_scanner_rules() -> None:
    job, steps, original, diagnostic = _steps()
    assert job["name"] == "Alembic Migrations"
    assert job["timeout-minutes"] == 15
    assert steps.index(diagnostic) == steps.index(original) + 1
    assert original["name"] == "Lint Postgres Migrations (Squawk)"
    assert 'squawk "${squawk_args[@]}" "$sql_file"' in original["run"]
    assert _squawk_args(diagnostic["run"]) == _squawk_args(original["run"])
    assert "continue-on-error" not in job
    assert "continue-on-error" not in original
    assert "continue-on-error" not in diagnostic
    guard = " ".join(diagnostic["if"].split())
    assert "!cancelled()" in guard
    assert "steps.migration-squawk.outcome == 'success'" in guard
    assert "steps.migration-squawk.outcome == 'failure'" in guard
    assert "always()" not in guard
    assert diagnostic["env"]["DATABASE_URL"] == "sqlite+aiosqlite:///:memory:"
    assert diagnostic["env"]["RUN_INTEGRATION_TESTS"] == "1"
    assert "uv run pytest -q -s --tb=short" in diagnostic["run"]
    assert "tests/test_migration_148642dd1207_trace.py" in diagnostic["run"]
    assert "tests/test_migration_148642dd1207_diagnostic_ci.py" in diagnostic["run"]
    assert (
        "::test_expanded_ddl_inventory_matches_unmodified_populated_control"
        in (diagnostic["run"])
    )
    assert (
        "::test_convertible_orphan_rolls_back_cutover_and_diagnostic_rows"
        in (diagnostic["run"])
    )
    assert 'exit "$pytest_status"' in diagnostic["run"]
    assert diagnostic["run"].rstrip().endswith('exit "$lint_status"')
    assert 'print_bounded "$test_log" 131072' in diagnostic["run"]
    assert 'print_bounded "$lint_log" 131072' in diagnostic["run"]
    assert "|| true" not in diagnostic["run"]


def _git_blob(data):
    header = b"blob " + str(len(data)).encode("ascii") + b"\0"
    return hashlib.sha1(header + data, usedforsecurity=False).hexdigest()


def _fixture(tmp_path, monkeypatch):
    _, _, _, diagnostic = _steps()
    body = diagnostic["run"].split("<<'PY'\n", 1)[1].split("\nPY\n", 1)[0]
    script = tmp_path / "consumer.py"
    script.write_text(body, encoding="utf-8")
    sources = {
        "alembic/versions/148642dd1207_fix_missing_tables.py": b"migration\n",
        "tests/helpers/migration_148642dd1207_trace.py": b"helper\n",
        "tests/integration/test_migration_148642dd1207.py": b"fixture\n",
        ".github/workflows/ci.yml": b"workflow\n",
        "scripts/quality/render_live_alembic_sql.py": b"renderer\n",
        ".squawk.toml": b"scanner configuration\n",
        "uv.lock": b"locked dependencies\n",
    }
    for name, content in sources.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    sql_path = tmp_path / "synthetic.expanded.sql"
    sql_path.write_text("-- DIAGNOSTIC ONLY: not a replay script.\nBEGIN;\nCOMMIT;\n")
    statement = "ALTER TABLE public.fixture ADD COLUMN marker integer"
    evidence = {
        "status": "diagnostic-only-not-an-exception",
        "migration_blob": _git_blob(sources[next(iter(sources))]),
        "helper_sha256": hashlib.sha256(b"helper\n").hexdigest(),
        "fixture_sha256": hashlib.sha256(b"fixture\n").hexdigest(),
        "workflow_sha": "synthetic-workflow-sha",
        "workflow_run_id": "synthetic-run-id",
        "postgres_version": "PostgreSQL 17 fixture",
        "expanded_sql_sha256": hashlib.sha256(sql_path.read_bytes()).hexdigest(),
        "nested_ddl": [
            {
                "outer_ordinal": 1,
                "site": "synthetic_site",
                "sql": statement,
                "sql_sha256": hashlib.sha256(statement.encode()).hexdigest(),
            }
        ],
        "equivalent_snapshot": {"private_rows": "never-print-row-data"},
        "original_cursor_events": [{"bound_value": "never-print-bound-values"}],
    }
    evidence_path = tmp_path / "synthetic.trace.json"
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("AUD148_CHECKOUT_SHA", "synthetic-checkout-sha")
    monkeypatch.setenv("AUD148_SQUAWK_VERSION", "squawk 2.67.0")
    monkeypatch.setenv("AUD148_SQUAWK_BINARY_SHA256", "synthetic-binary-digest")
    monkeypatch.setenv("ORIGINAL_SQUAWK_OUTCOME", "failure")
    monkeypatch.setenv("UNRELATED_PRIVATE_CONTEXT", "never-print-environment")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            str(script),
            str(sql_path),
            str(evidence_path),
            *_squawk_args(diagnostic["run"]),
        ],
    )
    return script, sql_path, evidence_path, evidence


def test_metadata_output_is_allowlisted_bounded_and_source_bound(
    tmp_path, monkeypatch, capsys
) -> None:
    script, _, evidence_path, evidence = _fixture(tmp_path, monkeypatch)
    evidence_path.write_text(json.dumps(evidence))
    runpy.run_path(str(script), run_name="__main__")
    output = capsys.readouterr().out
    assert len(output.encode()) < 131072
    assert "never-print-" not in output
    assert "AUD148_EXPANDED_SQL_BEGIN" in output
    assert not list(tmp_path.rglob("148642dd1207.expanded.sql"))
    assert not list(tmp_path.rglob("148642dd1207.trace.json"))
    metadata_text = output.split("AUD148_DIAGNOSTIC_METADATA_BEGIN\n", 1)[1]
    metadata_text = metadata_text.split("\nAUD148_DIAGNOSTIC_METADATA_END", 1)[0]
    metadata = json.loads(metadata_text)
    assert metadata["nested_ddl"] == evidence["nested_ddl"]
    assert metadata["original_squawk_outcome"] == "failure"
    assert metadata["workflow_blob"] == _git_blob(b"workflow\n")
    assert metadata["renderer_blob"] == _git_blob(b"renderer\n")
    assert "equivalent_snapshot" not in metadata
    assert "original_cursor_events" not in metadata


@pytest.mark.parametrize(
    "case",
    [
        "sql_input_cap",
        "json_input_cap",
        "status",
        "sql_label",
        "sql_digest",
        "migration",
        "diagnostic_source",
        "empty_nested",
        "wrong_nested_digest",
        "wrong_nested_operation",
        "wrong_version",
        "output_cap",
    ],
)
def test_invalid_or_oversized_evidence_fails_before_logging(
    case, tmp_path, monkeypatch, capsys
) -> None:
    script, sql_path, evidence_path, evidence = _fixture(tmp_path, monkeypatch)
    if case == "sql_input_cap":
        sql_path.write_bytes(b"x" * 65537)
    elif case == "json_input_cap":
        evidence["unprinted"] = "x" * 4194304
    elif case == "status":
        evidence["status"] = "not-approved"
    elif case == "sql_label":
        sql_path.write_text("SELECT 1;\n")
    elif case == "sql_digest":
        evidence["expanded_sql_sha256"] = "different"
    elif case == "migration":
        evidence["migration_blob"] = "different"
    elif case == "diagnostic_source":
        evidence["helper_sha256"] = "different"
    elif case == "empty_nested":
        evidence["nested_ddl"] = []
    elif case == "wrong_nested_digest":
        evidence["nested_ddl"][0]["sql_sha256"] = "different"
    elif case == "wrong_nested_operation":
        statement = "SELECT private_row"
        evidence["nested_ddl"][0]["sql"] = statement
        evidence["nested_ddl"][0]["sql_sha256"] = hashlib.sha256(
            statement.encode()
        ).hexdigest()
    elif case == "wrong_version":
        monkeypatch.setenv("AUD148_SQUAWK_VERSION", "squawk unknown")
    else:
        statement = "ALTER TABLE public.fixture " + "x" * 140000
        evidence["nested_ddl"][0]["sql"] = statement
        evidence["nested_ddl"][0]["sql_sha256"] = hashlib.sha256(
            statement.encode()
        ).hexdigest()
    evidence_path.write_text(json.dumps(evidence))
    with pytest.raises(SystemExit, match="AUD148"):
        runpy.run_path(str(script), run_name="__main__")
    assert capsys.readouterr().out == ""
