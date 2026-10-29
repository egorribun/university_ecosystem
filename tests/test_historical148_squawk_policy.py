"""Tests-first contract for an inactive historical Squawk inventory matcher.

The captured SQL/JSON came from the hosted 15eaaa job, not this validator. These
tests establish no empty-database, all-migration, operational or deployment proof.
"""

from __future__ import annotations

import ast
import copy
import hashlib
import inspect
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from scripts.quality import validate_historical148_squawk as validator

ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "quality/historical148-squawk-policy.json"
CAPTURE = ROOT / "tests/fixtures/historical148-squawk-capture-15eaaa.json"
VERDICT = "matched-diagnostic-inventory"
POLICY_LIMIT = 32768
CAPTURE_LIMIT = 131072


def _wire(value: object) -> bytes:
    rendered = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return (rendered + "\n").encode()


def _load() -> tuple[dict[str, Any], dict[str, Any]]:
    return (
        json.loads(POLICY.read_bytes()),
        json.loads(CAPTURE.read_bytes()),
    )


@pytest.fixture(autouse=True)
def clock(monkeypatch: pytest.MonkeyPatch) -> list[datetime]:
    current = [datetime(2026, 10, 29, tzinfo=UTC)]

    class FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz: Any = None) -> datetime:
            return current[0].astimezone(tz) if tz else current[0].replace(tzinfo=None)

    monkeypatch.setattr(validator, "datetime", FrozenDateTime)
    return current


def _valid_control(policy: dict[str, Any], capture: dict[str, Any]) -> None:
    matched = validator.match_inventory(_wire(policy), _wire(capture)) == VERDICT
    assert matched, "historical diagnostic inventory did not match"


def _rows(capture: dict[str, Any], scenario: int) -> list[dict[str, Any]]:
    return json.loads(capture["report"]["captures"][scenario]["stdout"])


def _put_rows(
    capture: dict[str, Any], scenario: int, rows: list[dict[str, Any]]
) -> None:
    capture["report"]["captures"][scenario]["stdout"] = json.dumps(rows) + "\n"


def test_exact_historical_capture_matches_only_the_diagnostic_inventory() -> None:
    policy, capture = _load()
    assert policy["status"] == "prepared-inactive"
    assert policy["execution_scope"] == "new-empty-mvp-only"
    assert [len(_rows(capture, index)) for index in range(2)] == [13, 24]
    statements = {
        finding["sql_statement"]
        for scenario in policy["scenarios"]
        for finding in scenario["findings"]
    }
    assert len(statements) == 20
    sql_inputs = (capture["ordinary"]["sql"], capture["expanded"]["sql"])
    for index, sql in enumerate(sql_inputs):
        expected = policy["scenarios"][index]
        assert len(sql.encode()) == expected["sql_bytes"]
        assert hashlib.sha256(sql.encode()).hexdigest() == expected["sql_sha256"]
    _valid_control(policy, capture)


def test_raw_warning_failure_is_retained_without_mutating_the_capture() -> None:
    policy, capture = _load()
    before = copy.deepcopy(capture)
    _valid_control(policy, capture)
    assert capture == before
    assert capture["report"]["raw_ordinary_exit"] == 1
    assert capture["report"]["raw_expanded_exit"] == 1
    assert capture["report"]["original_squawk_outcome"] == "failure"
    assert all(row["exit_code"] == 1 for row in capture["report"]["captures"])


@pytest.mark.parametrize("scenario", [0, 1])
def test_warning_order_does_not_change_the_exact_multiset(scenario: int) -> None:
    policy, capture = _load()
    _valid_control(policy, capture)
    rows = _rows(capture, scenario)
    _put_rows(capture, scenario, list(reversed(rows)))
    assert validator.match_inventory(_wire(policy), _wire(capture)) == VERDICT


@pytest.mark.parametrize(
    ("scenario", "index"),
    [
        (scenario, index)
        for scenario, count in enumerate((13, 24))
        for index in range(count)
    ],
)
@pytest.mark.parametrize("mutation", ["missing", "duplicate", "changed_rule"])
def test_each_known_occurrence_is_exact_and_required(
    scenario: int, index: int, mutation: str
) -> None:
    policy, capture = _load()
    _valid_control(policy, capture)
    rows = _rows(capture, scenario)
    if mutation == "missing":
        rows.pop(index)
    elif mutation == "duplicate":
        rows.append(copy.deepcopy(rows[index]))
    else:
        rows[index]["rule_name"] += "-changed"
    _put_rows(capture, scenario, rows)
    assert validator.match_inventory(_wire(policy), _wire(capture)) is None


@pytest.mark.parametrize("scenario", [0, 1])
@pytest.mark.parametrize(
    "mutation",
    [
        "line",
        "column",
        "line_end",
        "column_end",
        "level",
        "message",
        "help",
        "file",
        "unknown_field",
        "bool_line",
        "negative_column",
        "sql_digest",
        "sql_length",
        "sql_path",
        "sql_identity",
        "scenario",
        "stderr",
        "scanner_crash",
        "scanner_timeout",
        "scanner_success",
        "malformed_stdout",
        "duplicate_json_key",
        "unknown_capture_field",
    ],
)
def test_span_source_and_raw_scanner_near_misses_fail_closed(
    scenario: int, mutation: str
) -> None:
    policy, capture = _load()
    _valid_control(policy, capture)
    selected = capture["report"]["captures"][scenario]
    rows = _rows(capture, scenario)
    if mutation in {"line", "column", "line_end", "column_end"}:
        rows[0][mutation] += 1
    elif mutation in {"level", "message", "help", "file"}:
        rows[0][mutation] = "changed"
    elif mutation == "unknown_field":
        rows[0]["approved"] = True
    elif mutation == "bool_line":
        rows[0]["line"] = True
    elif mutation == "negative_column":
        rows[0]["column"] = -1
    elif mutation == "sql_digest":
        selected["sql_sha256"] = "0" * 64
    elif mutation == "sql_length":
        selected["sql_bytes"] += 1
    elif mutation == "sql_path":
        selected["sql_path"] += ".other"
    elif mutation == "sql_identity":
        selected["sql_identity"] = "0:0"
    elif mutation == "scenario":
        selected["scenario"] = "unrelated-migration"
    elif mutation == "stderr":
        selected["stderr"] = "unexpected scanner warning\n"
    elif mutation in {"scanner_crash", "scanner_timeout", "scanner_success"}:
        selected["exit_code"] = {
            "scanner_crash": 2,
            "scanner_timeout": -9,
            "scanner_success": 0,
        }[mutation]
    elif mutation == "unknown_capture_field":
        selected["approved"] = True
    elif mutation == "malformed_stdout":
        selected["stdout"] = "["
        assert validator.match_inventory(_wire(policy), _wire(capture)) is None
        return
    else:
        encoded = json.dumps(rows)
        duplicate = '{"line":' + str(rows[0]["line"]) + ","
        selected["stdout"] = encoded.replace("{", duplicate, 1) + "\n"
        assert validator.match_inventory(_wire(policy), _wire(capture)) is None
        return
    _put_rows(capture, scenario, rows)
    assert validator.match_inventory(_wire(policy), _wire(capture)) is None


@pytest.mark.parametrize(
    "mutation",
    [
        "pr_head",
        "checkout",
        "workflow_sha",
        "run",
        "attempt",
        "job",
        "raw_ordinary",
        "raw_expanded",
        "outcome",
        "version",
        "binary",
        "arguments",
        "status",
        "unknown_approval",
        "swapped_scenarios",
        "missing_scenario",
        "extra_scenario",
        "ordinary_sql",
        "expanded_sql",
        "ordinary_revision",
        "ordinary_parent",
        "ordinary_migration_path",
        "ordinary_source",
        "expanded_source",
        "expanded_nested_ddl",
        "expanded_postgres",
        "provenance",
        "unknown_root",
    ],
)
def test_capture_provenance_and_complete_inputs_are_required(mutation: str) -> None:
    policy, capture = _load()
    _valid_control(policy, capture)
    report = capture["report"]
    changes = {
        "pr_head": ("pr_head_sha", "0" * 40),
        "checkout": ("checkout_sha", "0" * 40),
        "workflow_sha": ("workflow_sha", "0" * 40),
        "run": ("workflow_run_id", "1"),
        "attempt": ("workflow_run_attempt", "2"),
        "job": ("producer_job", "other"),
        "raw_ordinary": ("raw_ordinary_exit", 0),
        "raw_expanded": ("raw_expanded_exit", 0),
        "outcome": ("original_squawk_outcome", "success"),
        "version": ("squawk_version", "squawk 2.67.1"),
        "binary": ("squawk_binary_sha256", "0" * 64),
        "status": ("status", "approved"),
    }
    if mutation in changes:
        key, value = changes[mutation]
        report[key] = value
    elif mutation == "arguments":
        report["squawk_args"] = report["squawk_args"][:-2]
    elif mutation == "unknown_approval":
        report["approved"] = True
    elif mutation == "swapped_scenarios":
        report["captures"].reverse()
    elif mutation == "missing_scenario":
        report["captures"].pop()
    elif mutation == "extra_scenario":
        report["captures"].append(copy.deepcopy(report["captures"][0]))
    elif mutation in {"ordinary_sql", "expanded_sql"}:
        target = (
            capture["ordinary"] if mutation == "ordinary_sql" else capture["expanded"]
        )
        target["sql"] = target["sql"].replace("ALTER TABLE", "ALTER  TABLE", 1)
    elif mutation.startswith("ordinary_"):
        key = mutation.removeprefix("ordinary_")
        key = {"parent": "down_revision", "source": "source_blobs"}.get(key, key)
        capture["ordinary"][key] = {} if key == "source_blobs" else "changed"
    elif mutation == "expanded_source":
        capture["expanded"]["metadata"]["helper_sha256"] = "0" * 64
    elif mutation == "expanded_nested_ddl":
        capture["expanded"]["metadata"]["nested_ddl"].pop()
    elif mutation == "expanded_postgres":
        capture["expanded"]["metadata"]["postgres_version"] = "unknown"
    elif mutation == "provenance":
        capture["provenance"]["job_id"] = "1"
    else:
        capture["approval"] = True
    assert validator.match_inventory(_wire(policy), _wire(capture)) is None


@pytest.mark.parametrize(
    "mutation",
    [
        "owner",
        "scope",
        "status",
        "approval_date",
        "expiry_extension",
        "expiry_ambiguous",
        "normalization",
        "scanner",
        "source",
        "findings",
        "unknown_approval",
        "unknown_root",
        "missing_schema",
    ],
)
def test_policy_is_not_an_arbitrary_exception_document(mutation: str) -> None:
    policy, capture = _load()
    _valid_control(policy, capture)
    values = {
        "owner": ("owner", "other"),
        "scope": ("execution_scope", "populated-database"),
        "status": ("status", "active"),
        "approval_date": ("preparation_approved_on", "2026-10-29"),
        "expiry_extension": ("expires_at", "2026-11-14T00:00:00Z"),
        "expiry_ambiguous": ("expires_at", "2026-11-13"),
        "normalization": ("normalization", "collapse-whitespace"),
    }
    if mutation in values:
        key, value = values[mutation]
        policy[key] = value
    elif mutation == "scanner":
        policy["scanner"]["binary_sha256"] = "0" * 64
    elif mutation == "source":
        policy["source_blobs"][".squawk.toml"] = "0" * 40
    elif mutation == "findings":
        policy["scenarios"][0]["findings"].pop()
    elif mutation == "missing_schema":
        del policy["schema"]
    else:
        policy["approved" if mutation == "unknown_approval" else "extra"] = True
    assert validator.match_inventory(_wire(policy), _wire(capture)) is None


@pytest.mark.parametrize("target", ["policy", "capture"])
@pytest.mark.parametrize(
    "defect",
    [
        "empty",
        "invalid_utf8",
        "truncated",
        "duplicate_key",
        "nan",
        "deep",
        "oversized",
    ],
)
def test_bounded_json_is_strict(target: str, defect: str) -> None:
    policy, capture = _load()
    _valid_control(policy, capture)
    policy_wire, capture_wire = _wire(policy), _wire(capture)
    limit = POLICY_LIMIT if target == "policy" else CAPTURE_LIMIT
    original = policy_wire if target == "policy" else capture_wire
    schema = policy["schema"] if target == "policy" else capture["schema"]
    duplicate = b'{"schema":' + json.dumps(schema).encode() + b","
    bad = {
        "empty": b"",
        "invalid_utf8": b"\xff",
        "truncated": original[:-4],
        "duplicate_key": original.replace(b"{", duplicate, 1),
        "nan": b'{"schema":NaN}',
        "deep": b"[" * 1000 + b"0" + b"]" * 1000,
        "oversized": b" " * (limit + 1),
    }[defect]
    if target == "policy":
        policy_wire = bad
    else:
        capture_wire = bad
    assert validator.match_inventory(policy_wire, capture_wire) is None


@pytest.mark.parametrize("offset_us", [-1, 0, 1])
def test_real_utc_expiry_boundary_has_no_caller_override(
    clock: list[datetime], monkeypatch: pytest.MonkeyPatch, offset_us: int
) -> None:
    policy, capture = _load()
    _valid_control(policy, capture)
    clock[0] = datetime(2026, 11, 13, tzinfo=UTC) + timedelta(microseconds=offset_us)
    monkeypatch.setenv("HISTORICAL148_NOW", "2026-10-29T00:00:00Z")
    expected = VERDICT if offset_us < 0 else None
    assert validator.match_inventory(_wire(policy), _wire(capture)) == expected
    assert tuple(inspect.signature(validator.match_inventory).parameters) == (
        "policy_bytes",
        "capture_bytes",
    )


@pytest.mark.parametrize("field", ["raw_ordinary_exit", "raw_expanded_exit"])
def test_boolean_is_not_an_integer_scanner_exit(field: str) -> None:
    policy, capture = _load()
    _valid_control(policy, capture)
    capture["report"][field] = True
    assert validator.match_inventory(_wire(policy), _wire(capture)) is None


@pytest.mark.parametrize("scenario", [0, 1])
def test_boolean_is_not_a_capture_exit(scenario: int) -> None:
    policy, capture = _load()
    _valid_control(policy, capture)
    capture["report"]["captures"][scenario]["exit_code"] = True
    assert validator.match_inventory(_wire(policy), _wire(capture)) is None


@pytest.mark.parametrize(
    "location",
    [
        "provenance",
        "ordinary",
        "expanded",
        "expanded_metadata",
        "nested_ddl",
        "report",
        "policy_scanner",
        "policy_provenance",
        "policy_scenario",
        "policy_finding",
    ],
)
def test_unknown_nested_fields_cannot_claim_approval(location: str) -> None:
    policy, capture = _load()
    _valid_control(policy, capture)
    targets = {
        "provenance": capture["provenance"],
        "ordinary": capture["ordinary"],
        "expanded": capture["expanded"],
        "expanded_metadata": capture["expanded"]["metadata"],
        "nested_ddl": capture["expanded"]["metadata"]["nested_ddl"][0],
        "report": capture["report"],
        "policy_scanner": policy["scanner"],
        "policy_provenance": policy["provenance"],
        "policy_scenario": policy["scenarios"][0],
        "policy_finding": policy["scenarios"][0]["findings"][0],
    }
    targets[location]["approved"] = True
    assert validator.match_inventory(_wire(policy), _wire(capture)) is None


def test_capture_source_pins_match_the_unchanged_reviewed_inputs() -> None:
    policy, capture = _load()
    # The workflow receipt is historical, not the current workflow's Git blob.
    # Other inputs remain byte-pinned; a changed input requires a new review.
    for path, expected in policy["source_blobs"].items():
        if path == ".github/workflows/ci.yml":
            assert capture["ordinary"]["source_blobs"][path] == expected
            continue
        data = (ROOT / path).read_bytes()
        framing = b"blob " + str(len(data)).encode("ascii") + b"\0"
        actual = hashlib.sha1(framing + data, usedforsecurity=False).hexdigest()
        assert actual == expected, path
    for key, path in (
        ("helper_sha256", "tests/helpers/migration_148642dd1207_trace.py"),
        ("fixture_sha256", "tests/integration/test_migration_148642dd1207.py"),
    ):
        actual = hashlib.sha256((ROOT / path).read_bytes()).hexdigest()
        assert capture["expanded"]["metadata"][key] == actual
        assert policy["expanded_contract"][key] == actual


@pytest.mark.parametrize(
    "path",
    [
        ".github/workflows/ci.yml",
        ".squawk.toml",
        "alembic.ini",
        "alembic/env.py",
        "alembic/versions/148642dd1207_fix_missing_tables.py",
        "pyproject.toml",
        "scripts/quality/read_alembic_revision.py",
        "scripts/quality/render_live_alembic_sql.py",
        "uv.lock",
        "tests/helpers/migration_148642dd1207_trace.py",
        "tests/integration/test_migration_148642dd1207.py",
    ],
    ids=[
        "workflow",
        "scanner-config",
        "alembic-config",
        "env",
        "migration",
        "project",
        "revision-reader",
        "renderer",
        "lock",
        "trace",
        "fixture",
    ],
)
def test_every_source_pin_remains_exact(path: str) -> None:
    policy, capture = _load()
    _valid_control(policy, capture)
    policy["source_blobs"][path] = "0" * 40
    assert validator.match_inventory(_wire(policy), _wire(capture)) is None


@pytest.mark.parametrize("target", ["policy", "capture"])
@pytest.mark.parametrize("bad", [None, 0, True, "", [], {}])
def test_only_bytes_are_accepted(target: str, bad: Any) -> None:
    policy, capture = _load()
    _valid_control(policy, capture)
    policy_wire = bad if target == "policy" else _wire(policy)
    capture_wire = bad if target == "capture" else _wire(capture)
    assert validator.match_inventory(policy_wire, capture_wire) is None


def test_clock_before_the_preparation_decision_cannot_match(
    clock: list[datetime],
) -> None:
    policy, capture = _load()
    _valid_control(policy, capture)
    clock[0] = datetime(2026, 10, 27, 23, 59, 59, tzinfo=UTC)
    assert validator.match_inventory(_wire(policy), _wire(capture)) is None


def test_correlated_policy_and_capture_changes_cannot_self_authorize() -> None:
    policy, capture = _load()
    _valid_control(policy, capture)
    rows = _rows(capture, 0)
    # Use another already-known rule, not an unknown name an allowlist rejects.
    replacement = rows[1]["rule_name"]
    assert replacement != rows[0]["rule_name"]
    policy["scenarios"][0]["findings"][0]["rule_name"] = replacement
    rows[0]["rule_name"] = replacement
    _put_rows(capture, 0, rows)
    assert validator.match_inventory(_wire(policy), _wire(capture)) is None


def test_matcher_has_no_execution_or_admission_adapter() -> None:
    source = inspect.getsource(validator)
    module = ast.parse(source)
    imports: set[str] = set()
    for node in ast.walk(module):
        if isinstance(node, ast.Import):
            imports.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module.split(".")[0])
    prohibited = {"os", "subprocess", "socket", "requests", "pathlib"}
    assert not imports.intersection(prohibited)
    assert '__name__ == "__main__"' not in source
    assert "policy_bytes" in inspect.signature(validator.match_inventory).parameters
