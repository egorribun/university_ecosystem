"""Fail-closed contracts for the bounded, diagnostic-only Alembic CI consumer."""

from __future__ import annotations

import hashlib
import json
import re
import runpy
import shlex
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

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
    assert "uv run pytest -q --tb=short" in diagnostic["run"]
    assert "tests/test_migration_148642dd1207_trace.py" in diagnostic["run"]
    assert "tests/test_migration_148642dd1207_diagnostic_ci.py" in diagnostic["run"]
    assert "tests/test_migration_148642dd1207_safety.py" in diagnostic["run"]
    for regression in (
        "test_existing_exact_shadow_check_is_reused_from_real_pg_catalog",
        "test_existing_shadow_check_rejects_wrong_real_pg_catalog_identity",
        "test_stale_shadow_value_aborts_before_fk_capture_with_exact_rollback",
        "test_shadow_cutover_omits_only_transient_validation_after_null_backfill",
        "test_groups_cutover_uses_only_the_exact_primary_key_index",
        "test_groups_index_cutover_failure_restores_exact_catalog_and_data",
        "test_groups_key_helper_round_trip_restores_legacy_index_and_foreign_keys",
        "test_groups_successors_do_not_require_the_duplicate_id_index",
    ):
        assert (
            f"tests/integration/test_migration_148642dd1207.py::{regression}"
            in diagnostic["run"]
        )
    # Keep passing setup logs captured; emitted artifacts are found on disk.
    assert "pytest -q -s" not in diagnostic["run"]
    assert "--capture=no" not in diagnostic["run"]
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


def test_consumer_creates_temp_parent_before_pytest() -> None:
    _, _, _, diagnostic = _steps()
    lines = diagnostic["run"].splitlines()
    root = lines.index('trace_root=".pytest_tmp/aud148-expanded"')
    prepare = lines.index('mkdir -p "$(dirname "$trace_root")"')
    invoke = lines.index("uv run pytest -q --tb=short \\")
    assert root < prepare < invoke


@pytest.fixture
def artifact_selection(monkeypatch):
    # Keep selector fixtures outside pytest's evidence root so they cannot
    # masquerade as the real PostgreSQL test's artifact pair.
    with TemporaryDirectory(prefix="aud148-selection-") as directory:
        base = Path(directory)
        root = base / "evidence with spaces"
        root.mkdir()
        _, _, _, diagnostic = _steps()
        body = diagnostic["run"].split("<<'SELECT_AUD148'\n", 1)[1]
        body = body.split("\nSELECT_AUD148\n", 1)[0]
        script = base / "selector.py"
        script.write_text(body, encoding="utf-8")
        manifest = base / "selected"
        monkeypatch.setattr(sys, "argv", [str(script), str(root), str(manifest)])
        yield script, root, manifest


def _artifact_pair(directory):
    directory.mkdir()
    paths = (
        directory / "148642dd1207.expanded.sql",
        directory / "148642dd1207.trace.json",
    )
    for path in paths:
        path.write_text("synthetic selector fixture\n", encoding="utf-8")
    return paths


@pytest.mark.parametrize("current_alias", [False, True])
def test_artifact_selection_accepts_one_physical_pair_despite_pytest_alias(
    artifact_selection, current_alias
) -> None:
    script, root, manifest = artifact_selection
    paths = _artifact_pair(root / "test_expanded_ddl_inventory_ma0")
    if current_alias:
        (root / "test_expanded_ddl_inventory_macurrent").symlink_to(
            paths[0].parent, target_is_directory=True
        )

    runpy.run_path(str(script), run_name="__main__")

    assert manifest.read_bytes().split(b"\0") == [
        str(paths[0]).encode(),
        str(paths[1]).encode(),
        b"",
    ]


@pytest.mark.parametrize(
    "case",
    [
        "missing_pair",
        "missing_sql",
        "missing_json",
        "two_real_pairs",
        "split_pair",
        "directory_symlink_only",
        "file_symlink",
    ],
)
def test_artifact_selection_rejects_missing_duplicate_or_aliased_evidence(
    artifact_selection, case
) -> None:
    script, root, manifest = artifact_selection
    if case != "missing_pair":
        paths = _artifact_pair(root / "real")
        if case == "missing_sql":
            paths[0].unlink()
        elif case == "missing_json":
            paths[1].unlink()
        elif case == "two_real_pairs":
            _artifact_pair(root / "second")
        elif case == "split_pair":
            second = root / "second"
            second.mkdir()
            paths[1].rename(second / paths[1].name)
        elif case == "directory_symlink_only":
            outside = root.parent / "outside"
            paths[0].parent.rename(outside)
            (root / "alias").symlink_to(outside, target_is_directory=True)
        else:
            outside = root.parent / "outside.sql"
            paths[0].rename(outside)
            paths[0].symlink_to(outside)

    with pytest.raises(SystemExit, match="AUD148"):
        runpy.run_path(str(script), run_name="__main__")
    assert not manifest.exists()


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


def test_tenant_context_diagnostic_is_separate_bounded_and_fail_closed() -> None:
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    job = workflow["jobs"]["alembic-migrations"]
    steps = job["steps"]
    tenant = next(step for step in steps if step.get("id") == "tenant-context-evidence")
    migration = next(
        step for step in steps if step.get("id") == "migration-ddl-evidence"
    )
    assert steps.index(migration) < steps.index(tenant)
    assert job["timeout-minutes"] == 15
    assert tenant["timeout-minutes"] == 3
    guard = tenant["if"]
    assert "!cancelled()" in guard
    assert "steps.migration-squawk.outcome == 'success'" in guard
    assert "steps.migration-squawk.outcome == 'failure'" in guard
    assert "always()" not in guard
    assert tenant["env"] == {
        "SECRET_KEY": "${{ env.SECRET_KEY }}",
        "ENVIRONMENT": "testing",
        "DATABASE_URL": "sqlite+aiosqlite:///:memory:",
        "RUN_INTEGRATION_TESTS": "1",
    }
    run = tenant["run"]
    assert "set -euo pipefail" in run
    assert 'probe_root="$(mktemp -d)"' in run
    assert 'trap \'rm -rf -- "$probe_root"\' EXIT' in run
    assert "uv run pytest -v --tb=short --no-cov --maxfail=0" in run
    selector = (
        "tests/integration/test_aud197_198_notification_outbox_postgres.py::"
        "test_content_outbox_restores_tenant_scope"
    )
    assert run.count(selector) == 1
    assert selector not in migration["run"]
    assert '--basetemp="$probe_root/basetemp"' in run
    assert '> "$test_log" 2>&1 || pytest_status=$?' in run
    assert 'head -c 131072 "$test_log"' in run
    assert 'if [ "$bytes" -gt 131072 ]; then' in run
    assert '[ "$pytest_status" -ne 0 ] || pytest_status=1' in run
    assert 'exit "$pytest_status"' in run
    assert "OWNED_TENANT_CONTEXT_TESTS_BEGIN" in run
    assert "OWNED_TENANT_CONTEXT_TESTS_END" in run
    assert "--capture=no" not in run
    assert "continue-on-error" not in tenant
