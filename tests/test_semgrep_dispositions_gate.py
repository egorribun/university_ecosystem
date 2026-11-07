"""Unit tests for the fail-closed Semgrep dispositions gate (AUD-380)."""

from __future__ import annotations

import hashlib
import json
import os
import runpy
import stat
import sys
from datetime import UTC, date, datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from scripts.quality import semgrep_dispositions_gate as gate

TODAY = date(2026, 11, 4)
CHECK = "python.lang.security.audit.example"
REACT_CHECK = (
    "typescript.react.security.audit.react-dangerouslysetinnerhtml."
    "react-dangerouslysetinnerhtml"
)
PATH = "app/example.py"
LINE = "    value = compute()  "
DIGEST = hashlib.sha256(LINE.encode("utf-8")).hexdigest()
CONTEXT_LINE = "context = reviewed()"
CONTEXT_DIGEST = hashlib.sha256(f"{LINE}\n{CONTEXT_LINE}".encode()).hexdigest()
REVIEWED_SEMGREP_IGNORE_PATTERNS = (
    "alembic/versions/",
    "tests/",
    "native/rust_ext/fuzz/",
    "**/*_test.go",
    "frontend/coverage-*/",
    "frontend/coverage/",
    "frontend/src/tests/mocks/generated/",
    "frontend/openapi.json",
    "frontend/src/routeTree.gen.ts",
    "app/static/quarantine/",
    "app/test-static/",
    ".agents/",
)


def _disposition(**overrides: Any) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "check_id": CHECK,
        "path": PATH,
        "line_sha256": DIGEST,
        "context": {"start_line": 1, "end_line": 2, "sha256": CONTEXT_DIGEST},
        "companions": [],
        "reason": "reviewed false positive for a fixed argv call",
        "owner": "egorribun",
        "approved": "2026-11-04",
        "expires": "2027-01-10",
    }
    entry.update(overrides)
    return entry


def _write(path: Path, value: object) -> Path:
    path.write_text(json.dumps(value), encoding="utf-8", newline="\n")
    return path


def _result(**overrides: Any) -> dict[str, Any]:
    result: dict[str, Any] = {
        "check_id": CHECK,
        "path": PATH,
        "start": {"line": 1, "col": 1},
        "end": {"line": 1, "col": 20},
    }
    result.update(overrides)
    return result


def _repo(tmp_path: Path, text: str = LINE + "\n" + CONTEXT_LINE + "\n") -> Path:
    target = tmp_path / "app" / "example.py"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8", newline="\n")
    (tmp_path / ".semgrepignore").write_text(
        "\n".join(REVIEWED_SEMGREP_IGNORE_PATTERNS) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return tmp_path


def _results(tmp_path: Path, results: object, errors: object = None) -> Path:
    payload: dict[str, Any] = {
        "results": results,
        "errors": [] if errors is None else errors,
        "skipped_rules": [],
        "paths": {"scanned": [PATH], "skipped": []},
        "time": {"fixpoint_timeouts": []},
    }
    return _write(tmp_path / "semgrep.json", payload)


def _skip_report(
    tmp_path: Path,
    skipped: object,
    *,
    scanned: list[str] | None = None,
    errors: object = None,
) -> Path:
    return _write(
        tmp_path / "semgrep-skips.json",
        {
            "results": [],
            "errors": [] if errors is None else errors,
            "skipped_rules": [],
            "paths": {
                "scanned": [PATH] if scanned is None else scanned,
                "skipped": skipped,
            },
            "time": {"fixpoint_timeouts": []},
        },
    )


def _dispositions(tmp_path: Path, entries: object) -> Path:
    return _write(tmp_path / "dispositions.json", {"dispositions": entries})


# normalize_path ----------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("app/a.py", "app/a.py"), ("./app/a.py", "app/a.py"), ("app\\a.py", "app/a.py")],
)
def test_normalize_path_accepts_canonical_relative_paths(
    raw: str, expected: str
) -> None:
    assert gate.normalize_path(raw) == expected


@pytest.mark.parametrize(
    "raw",
    ["", "   ", None, 3, "/abs/a.py", "app/../a.py", "C:/outside.py", "app/*.py"],
)
def test_normalize_path_rejects_unsafe_or_malformed_values(raw: object) -> None:
    with pytest.raises(gate.GateError):
        gate.normalize_path(raw)


# load_dispositions -------------------------------------------------------------


def test_load_dispositions_accepts_an_exact_unexpired_entry(tmp_path: Path) -> None:
    path = _dispositions(tmp_path, [_disposition()])
    assert set(gate.load_dispositions(path, TODAY)) == {(CHECK, PATH, DIGEST)}


def test_load_dispositions_accepts_the_empty_reviewed_list(tmp_path: Path) -> None:
    assert not gate.load_dispositions(_dispositions(tmp_path, []), TODAY)


@pytest.mark.parametrize(
    "document",
    [
        [],
        {"other": []},
        {"dispositions": {}},
        {"dispositions": [], "extra": 1},
    ],
)
def test_load_dispositions_rejects_a_malformed_document(
    tmp_path: Path, document: object
) -> None:
    path = _write(tmp_path / "d.json", document)
    with pytest.raises(gate.GateError):
        gate.load_dispositions(path, TODAY)


def test_load_dispositions_rejects_unreadable_json(tmp_path: Path) -> None:
    broken = tmp_path / "d.json"
    broken.write_text("{not json", encoding="utf-8")
    with pytest.raises(gate.GateError, match="cannot read JSON"):
        gate.load_dispositions(broken, TODAY)
    with pytest.raises(gate.GateError, match="cannot read JSON"):
        gate.load_dispositions(tmp_path / "missing.json", TODAY)
    binary = tmp_path / "binary.json"
    binary.write_bytes(b"\xff\xfe")
    with pytest.raises(gate.GateError, match="cannot read JSON"):
        gate.load_dispositions(binary, TODAY)


def test_load_dispositions_rejects_duplicate_json_keys(tmp_path: Path) -> None:
    duplicate = tmp_path / "d.json"
    duplicate.write_text('{"dispositions": [], "dispositions": []}', encoding="utf-8")
    with pytest.raises(gate.GateError, match="duplicate JSON key"):
        gate.load_dispositions(duplicate, TODAY)


@pytest.mark.parametrize(
    "entry",
    [
        "not-an-object",
        {k: v for k, v in _disposition().items() if k != "reason"},
        _disposition(extra="field"),
    ],
)
def test_load_dispositions_rejects_entries_without_exact_fields(
    tmp_path: Path, entry: object
) -> None:
    with pytest.raises(gate.GateError, match="exactly the required fields"):
        gate.load_dispositions(_dispositions(tmp_path, [entry]), TODAY)


@pytest.mark.parametrize(
    "override",
    [
        {"check_id": ""},
        {"check_id": 4},
        {"reason": "   "},
        {"owner": None},
        {"approved": "not-a-date"},
        {"expires": 20270110},
    ],
)
def test_load_dispositions_rejects_bad_text_and_dates(
    tmp_path: Path, override: dict[str, Any]
) -> None:
    with pytest.raises(gate.GateError):
        gate.load_dispositions(
            _dispositions(tmp_path, [_disposition(**override)]), TODAY
        )


def test_load_dispositions_rejects_approval_after_expiry(tmp_path: Path) -> None:
    entry = _disposition(approved="2027-01-11", expires="2027-01-10")
    with pytest.raises(gate.GateError, match="approved after it expires"):
        gate.load_dispositions(_dispositions(tmp_path, [entry]), TODAY)


def test_load_dispositions_rejects_future_approval(tmp_path: Path) -> None:
    entry = _disposition(approved="2026-11-05")
    with pytest.raises(gate.GateError, match="approval is in the future"):
        gate.load_dispositions(_dispositions(tmp_path, [entry]), TODAY)


def test_load_dispositions_rejects_wildcard_check_id(tmp_path: Path) -> None:
    with pytest.raises(gate.GateError, match="exact check_id"):
        gate.load_dispositions(
            _dispositions(tmp_path, [_disposition(check_id="python.*")]), TODAY
        )


@pytest.mark.parametrize("digest", ["ABC", "g" * 64, "A" * 64])
def test_load_dispositions_rejects_non_sha256_digests(
    tmp_path: Path, digest: str
) -> None:
    with pytest.raises(gate.GateError, match="64 lowercase hex"):
        gate.load_dispositions(
            _dispositions(tmp_path, [_disposition(line_sha256=digest)]), TODAY
        )


def test_load_dispositions_rejects_duplicate_dispositions(tmp_path: Path) -> None:
    with pytest.raises(gate.GateError, match="duplicate disposition"):
        gate.load_dispositions(
            _dispositions(tmp_path, [_disposition(), _disposition()]), TODAY
        )


@pytest.mark.parametrize("context", [None, {}, {"start_line": 1}])
def test_disposition_rejects_malformed_context(tmp_path: Path, context: object) -> None:
    with pytest.raises(gate.GateError, match="context must contain exactly"):
        gate.load_dispositions(
            _dispositions(tmp_path, [_disposition(context=context)]), TODAY
        )


@pytest.mark.parametrize(
    ("start", "end"), [(None, 2), (True, 2), (1, None), (1, True), (0, 2), (2, 2)]
)
def test_disposition_rejects_invalid_context_ranges(
    tmp_path: Path, start: object, end: object
) -> None:
    context = {"start_line": start, "end_line": end, "sha256": CONTEXT_DIGEST}
    with pytest.raises(gate.GateError, match="positive, multi-line range"):
        gate.load_dispositions(
            _dispositions(tmp_path, [_disposition(context=context)]), TODAY
        )


def test_disposition_rejects_invalid_span_and_context_digests(tmp_path: Path) -> None:
    entry = _disposition(span_sha256="not-a-digest")
    del entry["context"]
    with pytest.raises(gate.GateError, match="span_sha256 must be 64"):
        gate.load_dispositions(_dispositions(tmp_path, [entry]), TODAY)
    entry = _disposition(context={"start_line": 1, "end_line": 2, "sha256": "bad"})
    with pytest.raises(gate.GateError, match="sha256 must be 64"):
        gate.load_dispositions(_dispositions(tmp_path, [entry]), TODAY)


def test_disposition_requires_explicit_companion_evidence(tmp_path: Path) -> None:
    entry = _disposition()
    del entry["companions"]
    with pytest.raises(gate.GateError, match="required fields"):
        gate.load_dispositions(_dispositions(tmp_path, [entry]), TODAY)


def test_react_html_sink_rejects_empty_companions(tmp_path: Path) -> None:
    entry = _disposition(check_id=REACT_CHECK)
    with pytest.raises(gate.GateError, match="requires companion evidence"):
        gate.load_dispositions(_dispositions(tmp_path, [entry]), TODAY)


@pytest.mark.parametrize(
    "companions",
    [
        None,
        "not-a-list",
        ["not-an-object"],
        [{"path": "app/sanitizer.py"}],
        [{"path": "app/sanitizer.py", "sha256": "bad"}],
        [{"path": "../outside.py", "sha256": DIGEST}],
        [{"path": "app/*.py", "sha256": DIGEST}],
        [{"path": "./app/sanitizer.py", "sha256": DIGEST}],
        [{"path": PATH, "sha256": DIGEST}],
        [
            {"path": "app/sanitizer.py", "sha256": DIGEST},
            {"path": "app/sanitizer.py", "sha256": DIGEST},
        ],
    ],
)
def test_disposition_rejects_malformed_companions(
    tmp_path: Path, companions: object
) -> None:
    with pytest.raises(gate.GateError):
        gate.load_dispositions(
            _dispositions(tmp_path, [_disposition(companions=companions)]), TODAY
        )


def test_load_dispositions_rejects_expired_entries(tmp_path: Path) -> None:
    entry = _disposition(approved="2026-01-01", expires="2026-06-30")
    with pytest.raises(gate.GateError, match="expired dispositions"):
        gate.load_dispositions(_dispositions(tmp_path, [entry]), TODAY)


def test_load_dispositions_accepts_expiry_on_the_current_day(tmp_path: Path) -> None:
    entry = _disposition(approved="2026-10-01", expires="2026-11-04")
    assert gate.load_dispositions(_dispositions(tmp_path, [entry]), TODAY)


def test_load_dispositions_rejects_a_path_outside_the_repository(
    tmp_path: Path,
) -> None:
    with pytest.raises(gate.GateError, match="canonical repository path"):
        gate.load_dispositions(
            _dispositions(tmp_path, [_disposition(path="../outside.py")]), TODAY
        )


# load_findings -----------------------------------------------------------------


@pytest.mark.parametrize(
    "time_field",
    [
        None,
        3,
        [],
        "bad",
        {},
        {"fixpoint_timeouts": None},
        {"fixpoint_timeouts": {}},
        {"fixpoint_timeouts": "bad"},
    ],
)
def test_load_findings_rejects_malformed_fixpoint_timeout_metadata(
    tmp_path: Path, time_field: object
) -> None:
    report = {
        "results": [],
        "errors": [],
        "skipped_rules": [],
        "paths": {"scanned": [PATH], "skipped": []},
        "time": time_field,
    }
    with pytest.raises(gate.GateError, match="fixpoint timeout"):
        gate.load_findings(_write(tmp_path / "bad-time.json", report))


def test_load_findings_rejects_missing_fixpoint_timeout_metadata(
    tmp_path: Path,
) -> None:
    report = {
        "results": [],
        "errors": [],
        "skipped_rules": [],
        "paths": {"scanned": [PATH], "skipped": []},
    }
    with pytest.raises(gate.GateError, match="fixpoint timeout"):
        gate.load_findings(_write(tmp_path / "missing-time.json", report))


@pytest.mark.parametrize("entry", [None, {}, "unexpected"])
def test_load_findings_rejects_any_nonempty_fixpoint_timeout_list(
    tmp_path: Path, entry: object
) -> None:
    report = {
        "results": [],
        "errors": [],
        "skipped_rules": [],
        "paths": {"scanned": [PATH], "skipped": []},
        "time": {"fixpoint_timeouts": [entry]},
    }
    with pytest.raises(gate.GateError, match="fixpoint timeout"):
        gate.load_findings(_write(tmp_path / "nonempty-timeouts.json", report))


def test_load_findings_rejects_b33_shaped_fixpoint_warning(tmp_path: Path) -> None:
    position = {"line": 1, "col": 1, "offset": 0}
    report = {
        "results": [],
        "errors": [],
        "skipped_rules": [],
        "paths": {"scanned": [PATH], "skipped": []},
        "time": {
            "fixpoint_timeouts": [
                {
                    "error_type": "Fixpoint timeout",
                    "severity": "warn",
                    "message": "Fixpoint timeout while performing taint analysis",
                    "location": {"path": PATH, "start": position, "end": position},
                }
            ]
        },
    }
    with pytest.raises(gate.GateError, match="fixpoint timeout"):
        gate.load_findings(_write(tmp_path / "fixpoint-warning.json", report))


def test_load_findings_returns_results(tmp_path: Path) -> None:
    results = gate.load_findings(_results(tmp_path, [_result()], errors=[]))
    assert results == [_result()]


def test_load_findings_rejects_missing_errors_key(tmp_path: Path) -> None:
    with pytest.raises(gate.GateError, match="list results and errors"):
        gate.load_findings(_write(tmp_path / "incomplete.json", {"results": []}))


def test_load_findings_rejects_missing_skipped_rules_key(tmp_path: Path) -> None:
    report = {
        "results": [],
        "errors": [],
        "paths": {"scanned": [PATH]},
        "time": {"fixpoint_timeouts": []},
    }
    with pytest.raises(gate.GateError, match="skipped rules list"):
        gate.load_findings(_write(tmp_path / "missing-skipped-rules.json", report))


@pytest.mark.parametrize("skipped_rules", [None, {}, "bad"])
def test_load_findings_rejects_malformed_skipped_rules(
    tmp_path: Path, skipped_rules: object
) -> None:
    report = {
        "results": [],
        "errors": [],
        "skipped_rules": skipped_rules,
        "paths": {"scanned": [PATH], "skipped": []},
        "time": {"fixpoint_timeouts": []},
    }
    with pytest.raises(gate.GateError, match="skipped rules list"):
        gate.load_findings(_write(tmp_path / "malformed-skipped-rules.json", report))


@pytest.mark.parametrize("entry", [None, {}, "unexpected"])
def test_load_findings_rejects_any_skipped_rule(tmp_path: Path, entry: object) -> None:
    report = {
        "results": [],
        "errors": [],
        "skipped_rules": [entry],
        "paths": {"scanned": [PATH], "skipped": []},
        "time": {"fixpoint_timeouts": []},
    }
    with pytest.raises(gate.GateError, match="skipped 1 rule"):
        gate.load_findings(_write(tmp_path / "skipped-rule.json", report))


def test_load_findings_requires_verbose_skipped_target_metadata(
    tmp_path: Path,
) -> None:
    report = {
        "results": [],
        "errors": [],
        "skipped_rules": [],
        "paths": {"scanned": [PATH]},
        "time": {"fixpoint_timeouts": []},
    }
    with pytest.raises(gate.GateError, match="skipped targets list"):
        gate.load_findings(_write(tmp_path / "missing-skips.json", report))


@pytest.mark.parametrize("skipped", [None, {}, "bad"])
def test_load_findings_rejects_malformed_skipped_target_list(
    tmp_path: Path, skipped: object
) -> None:
    with pytest.raises(gate.GateError, match="skipped targets list"):
        gate.load_findings(_skip_report(tmp_path, skipped))


@pytest.mark.parametrize(
    "entry",
    [
        None,
        "not-an-object",
        {},
        {"path": "tests/ignored.py"},
        {"reason": "semgrepignore_patterns_match"},
        {"path": "tests/ignored.py", "reason": None},
        {
            "path": "tests/ignored.py",
            "reason": "semgrepignore_patterns_match",
            "rule_id": "some.rule",
        },
        {
            "path": "tests/ignored.py",
            "reason": "semgrepignore_patterns_match",
            "details": 3,
        },
    ],
)
def test_load_findings_rejects_malformed_skipped_target_entry(
    tmp_path: Path, entry: object
) -> None:
    repo = _repo(tmp_path)
    with pytest.raises(gate.GateError):
        gate.load_findings(_skip_report(tmp_path, [entry]), repository_root=repo)


def test_evaluate_accepts_only_a_valid_tracked_path_ignored_by_reviewed_policy(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path)
    ignored = repo / "tests" / "ignored.py"
    ignored.parent.mkdir(parents=True)
    ignored.write_text("eval('deliberate test fixture')\n", encoding="utf-8")
    # Unsupported text and binary assets are not scan targets or skip diagnostics.
    (repo / "app" / "notes.txt").write_text("documentation\n", encoding="utf-8")
    (repo / "app" / "image.bin").write_bytes(b"\x00\x01\xff")
    report = _skip_report(
        tmp_path,
        [{"path": "tests\\ignored.py", "reason": "semgrepignore_patterns_match"}],
    )
    assert gate.evaluate(report, _dispositions(tmp_path, []), repo, TODAY) == []


def test_evaluate_accepts_a_reviewed_ignored_directory_and_descendant_file(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path)
    ignored_directory = repo / ".agents" / "hooks"
    ignored_directory.mkdir(parents=True)
    ignored_file = ignored_directory / "hooks.json"
    ignored_file.write_text("{}\n", encoding="utf-8")
    report = _skip_report(
        tmp_path,
        [
            {"path": ".agents/hooks", "reason": "semgrepignore_patterns_match"},
            {
                "path": ".agents/hooks/hooks.json",
                "reason": "semgrepignore_patterns_match",
            },
        ],
    )
    assert gate.evaluate(report, _dispositions(tmp_path, []), repo, TODAY) == []


def test_load_findings_keeps_scanned_targets_file_only(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path)
    (repo / ".agents" / "hooks").mkdir(parents=True)
    report = _skip_report(tmp_path, [], scanned=[".agents/hooks"])
    with pytest.raises(gate.GateError, match="not a repository file"):
        gate.load_findings(report, repository_root=repo)


@pytest.mark.parametrize(
    "directory_alias",
    [".AGENTS/HOOKS", ".agents/hooks.", ".agents/hooks "],
)
def test_load_findings_uses_resolved_directory_aliases_for_conflicts(
    tmp_path: Path, directory_alias: str
) -> None:
    repo = _repo(tmp_path)
    ignored_file = repo / ".agents" / "hooks" / "probe.py"
    ignored_file.parent.mkdir(parents=True)
    ignored_file.write_text("pass\n", encoding="utf-8")
    alias_file = repo / Path(directory_alias) / "probe.py"
    aliases_ignored_file = alias_file.resolve() == ignored_file.resolve()
    if not aliases_ignored_file:
        alias_file.parent.mkdir(parents=True)
        alias_file.write_text("pass\n", encoding="utf-8")
    report = _skip_report(
        tmp_path,
        [{"path": ".agents/hooks", "reason": "semgrepignore_patterns_match"}],
        scanned=[(Path(directory_alias) / "probe.py").as_posix()],
    )
    if aliases_ignored_file:
        with pytest.raises(gate.GateError, match="beneath a skipped ignore directory"):
            gate.load_findings(report, repository_root=repo)
    else:
        assert gate.load_findings(report, repository_root=repo) == []


@pytest.mark.parametrize(
    "scanned_alias",
    ["TESTS/IGNORED.PY", "tests/ignored.py.", "tests/ignored.py "],
)
def test_load_findings_uses_resolved_file_aliases_for_conflicts(
    tmp_path: Path, scanned_alias: str
) -> None:
    repo = _repo(tmp_path)
    ignored_file = repo / "tests" / "ignored.py"
    ignored_file.parent.mkdir(parents=True)
    ignored_file.write_text("pass\n", encoding="utf-8")
    alias_file = repo / Path(scanned_alias)
    aliases_ignored_file = alias_file.resolve() == ignored_file.resolve()
    if not aliases_ignored_file:
        alias_file.parent.mkdir(parents=True, exist_ok=True)
        alias_file.write_text("pass\n", encoding="utf-8")
    report = _skip_report(
        tmp_path,
        [{"path": "tests/ignored.py", "reason": "semgrepignore_patterns_match"}],
        scanned=[Path(scanned_alias).as_posix()],
    )
    if aliases_ignored_file:
        with pytest.raises(gate.GateError, match="both scanned and skipped"):
            gate.load_findings(report, repository_root=repo)
    else:
        assert gate.load_findings(report, repository_root=repo) == []


@pytest.mark.parametrize(
    "scanned_alias", [PATH.upper(), "app/example.py.", "app/example.py "]
)
def test_load_findings_uses_resolved_file_aliases_for_duplicate_scanned_targets(
    tmp_path: Path, scanned_alias: str
) -> None:
    repo = _repo(tmp_path)
    source_file = repo / PATH
    alias_file = repo / Path(scanned_alias)
    aliases_source_file = alias_file.resolve() == source_file.resolve()
    if not aliases_source_file:
        alias_file.parent.mkdir(parents=True, exist_ok=True)
        alias_file.write_text("distinct\n", encoding="utf-8")
    report = _skip_report(
        tmp_path,
        [],
        scanned=[PATH, Path(scanned_alias).as_posix()],
    )
    if aliases_source_file:
        with pytest.raises(gate.GateError, match="duplicate scanned targets"):
            gate.load_findings(report, repository_root=repo)
    else:
        assert gate.load_findings(report, repository_root=repo) == []


def test_load_findings_rejects_scanning_beneath_a_skipped_ignore_directory(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path)
    ignored_file = repo / ".agents" / "hooks" / "probe.py"
    ignored_file.parent.mkdir(parents=True)
    ignored_file.write_text("pass\n", encoding="utf-8")
    report = _skip_report(
        tmp_path,
        [{"path": ".agents/hooks", "reason": "semgrepignore_patterns_match"}],
        scanned=[".agents/hooks/probe.py"],
    )
    with pytest.raises(gate.GateError, match="beneath a skipped ignore directory"):
        gate.load_findings(report, repository_root=repo)


def test_load_findings_rejects_a_missing_reviewed_ignore_directory(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path)
    report = _skip_report(
        tmp_path,
        [{"path": ".agents/missing", "reason": "semgrepignore_patterns_match"}],
    )
    with pytest.raises(
        gate.GateError, match="not a regular repository file or directory"
    ):
        gate.load_findings(report, repository_root=repo)


def test_load_findings_rejects_unreviewed_directory_skip_and_repository_root(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path)
    (repo / "app" / "child").mkdir()
    unreviewed = _skip_report(
        tmp_path,
        [{"path": "app/child", "reason": "semgrepignore_patterns_match"}],
    )
    with pytest.raises(gate.GateError, match="outside the reviewed policy"):
        gate.load_findings(unreviewed, repository_root=repo)

    repository_root_report = _skip_report(
        tmp_path,
        [{"path": ".", "reason": "semgrepignore_patterns_match"}],
    )
    with pytest.raises(gate.GateError):
        gate.load_findings(repository_root_report, repository_root=repo)


def test_load_findings_rejects_a_symlinked_reviewed_ignore_directory(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path)
    target = repo / "app" / "real-hooks"
    target.mkdir()
    ignored = repo / ".agents" / "hooks"
    ignored.parent.mkdir()
    ignored.symlink_to(target, target_is_directory=True)
    report = _skip_report(
        tmp_path,
        [{"path": ".agents/hooks", "reason": "semgrepignore_patterns_match"}],
    )
    with pytest.raises(gate.GateError, match="path contains a symlink"):
        gate.load_findings(report, repository_root=repo)


def test_load_findings_rejects_a_symlinked_ancestor_of_reviewed_ignore_directory(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path)
    target = repo / "app" / "real-agents"
    (target / "hooks").mkdir(parents=True)
    ignored = repo / ".agents"
    ignored.symlink_to(target, target_is_directory=True)
    report = _skip_report(
        tmp_path,
        [{"path": ".agents/hooks", "reason": "semgrepignore_patterns_match"}],
    )
    with pytest.raises(gate.GateError, match="path contains a symlink"):
        gate.load_findings(report, repository_root=repo)


def test_load_findings_rejects_a_junction_as_reviewed_ignore_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _repo(tmp_path)
    ignored = repo / ".agents" / "hooks"
    ignored.mkdir(parents=True)
    report = _skip_report(
        tmp_path,
        [{"path": ".agents/hooks", "reason": "semgrepignore_patterns_match"}],
    )
    original_is_junction = Path.is_junction

    def is_test_junction(path: Path) -> bool:
        return path == ignored or original_is_junction(path)

    monkeypatch.setattr(Path, "is_junction", is_test_junction)
    with pytest.raises(gate.GateError, match="path contains a symlink"):
        gate.load_findings(report, repository_root=repo)


def test_load_findings_rejects_oversized_target_even_with_approved_ignore_and_noncode(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path)
    ignored = repo / "tests" / "ignored.py"
    ignored.parent.mkdir(parents=True)
    ignored.write_text("pass\n", encoding="utf-8")
    (repo / "app" / "large.py").write_bytes(b"x" * 1_200_014)
    (repo / "app" / "notes.txt").write_text("documentation\n", encoding="utf-8")
    (repo / "app" / "image.bin").write_bytes(b"\x00\x01\xff")
    report = _skip_report(
        tmp_path,
        [
            {"path": "tests/ignored.py", "reason": "semgrepignore_patterns_match"},
            {"path": "app/large.py", "reason": "exceeded_size_limit"},
        ],
    )
    with pytest.raises(gate.GateError, match=r"app/large.py.*unapproved reason"):
        gate.load_findings(report, repository_root=repo)


@pytest.mark.parametrize(
    "repository_path",
    [
        "alembic/versions/ignored.py",
        "tests/ignored.py",
        "native/rust_ext/fuzz/ignored.rs",
        "services/gateway/worker_test.go",
        "frontend/coverage/report.json",
        "frontend/coverage-html/index.html",
        "frontend/src/tests/mocks/generated/client.ts",
        "frontend/openapi.json",
        "frontend/src/routeTree.gen.ts",
        "app/static/quarantine/fixture.js",
        "app/test-static/fixture.js",
        ".agents/skills/reference.md",
    ],
)
def test_reviewed_semgrepignore_matcher_accepts_only_the_exact_policy_paths(
    repository_path: str,
) -> None:
    assert gate._matches_reviewed_semgrep_ignore(repository_path)


@pytest.mark.parametrize(
    "repository_path",
    [
        "app/ignored.py",
        "frontend/coverageish/report.json",
        "services/gateway/worker.go",
        "frontend/src/mocks/handwritten.ts",
        "app/test-staticish/fixture.js",
    ],
)
def test_reviewed_semgrepignore_matcher_rejects_unreviewed_paths(
    repository_path: str,
) -> None:
    assert not gate._matches_reviewed_semgrep_ignore(repository_path)


@pytest.mark.parametrize(
    ("repository_path", "reason"),
    [
        ("app/large.py", "exceeded_size_limit"),
        ("app/binary.py", "analysis_failed_parser_or_internal_error"),
        ("app/unsupported.py", "wrong_language"),
        ("app/any.py", "mystery"),
    ],
)
def test_load_findings_rejects_non_ignore_skip_reasons(
    tmp_path: Path, repository_path: str, reason: str
) -> None:
    with pytest.raises(gate.GateError, match="unapproved reason"):
        gate.load_findings(
            _skip_report(tmp_path, [{"path": repository_path, "reason": reason}]),
            repository_root=_repo(tmp_path),
        )


def test_load_findings_rejects_an_ignore_reason_outside_reviewed_policy(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path)
    (repo / "app" / "not_ignored.py").write_text("pass\n", encoding="utf-8")
    report = _skip_report(
        tmp_path,
        [{"path": "app/not_ignored.py", "reason": "semgrepignore_patterns_match"}],
    )
    with pytest.raises(gate.GateError, match="outside the reviewed policy"):
        gate.load_findings(report, repository_root=repo)


def test_load_findings_rejects_duplicate_skipped_targets(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    ignored = repo / "tests" / "ignored.py"
    ignored.parent.mkdir(parents=True)
    ignored.write_text("pass\n", encoding="utf-8")
    skipped = [
        {"path": "tests/ignored.py", "reason": "semgrepignore_patterns_match"},
        {"path": "./tests/ignored.py", "reason": "semgrepignore_patterns_match"},
    ]
    with pytest.raises(gate.GateError, match="duplicate skipped targets"):
        gate.load_findings(_skip_report(tmp_path, skipped), repository_root=repo)


def test_load_findings_rejects_a_target_reported_as_scanned_and_skipped(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path)
    report = _skip_report(
        tmp_path,
        [{"path": PATH, "reason": "semgrepignore_patterns_match"}],
    )
    with pytest.raises(gate.GateError, match="both scanned and skipped"):
        gate.load_findings(report, repository_root=repo)


def test_load_findings_requires_repository_root_for_skipped_targets(
    tmp_path: Path,
) -> None:
    with pytest.raises(gate.GateError, match="repository root is required"):
        gate.load_findings(
            _skip_report(
                tmp_path,
                [
                    {
                        "path": "tests/ignored.py",
                        "reason": "semgrepignore_patterns_match",
                    }
                ],
            )
        )


def test_load_findings_rejects_an_ignore_skip_for_a_missing_snapshot_file(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path)
    report = _skip_report(
        tmp_path,
        [{"path": "tests/missing.py", "reason": "semgrepignore_patterns_match"}],
    )
    with pytest.raises(
        gate.GateError, match="not a regular repository file or directory"
    ):
        gate.load_findings(report, repository_root=repo)


def test_load_findings_rejects_a_symlinked_reviewed_ignore_skip(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path)
    ignored = repo / "tests" / "ignored.py"
    ignored.parent.mkdir(parents=True)
    ignored.symlink_to(repo / PATH)
    report = _skip_report(
        tmp_path,
        [{"path": "tests/ignored.py", "reason": "semgrepignore_patterns_match"}],
    )
    with pytest.raises(gate.GateError, match="skipped target path contains a symlink"):
        gate.load_findings(report, repository_root=repo)


@pytest.mark.parametrize("paths", [None, {}, {"scanned": []}, {"scanned": [3]}])
def test_load_findings_rejects_missing_or_empty_scan_targets(
    tmp_path: Path, paths: object
) -> None:
    report = {
        "results": [],
        "errors": [],
        "skipped_rules": [],
        "paths": paths,
        "time": {"fixpoint_timeouts": []},
    }
    with pytest.raises(gate.GateError, match="scanned target"):
        gate.load_findings(_write(tmp_path / "incomplete.json", report))


def test_load_findings_rejects_the_repository_root_as_a_scanned_target(
    tmp_path: Path,
) -> None:
    report = {
        "results": [],
        "errors": [],
        "skipped_rules": [],
        "paths": {"scanned": ["."], "skipped": []},
        "time": {"fixpoint_timeouts": []},
    }
    with pytest.raises(gate.GateError, match="must be a repository file path"):
        gate.load_findings(_write(tmp_path / "directory-target.json", report))


def test_load_findings_rejects_duplicate_scanned_targets(tmp_path: Path) -> None:
    report = {
        "results": [],
        "errors": [],
        "skipped_rules": [],
        "paths": {"scanned": [PATH, f"./{PATH}"], "skipped": []},
        "time": {"fixpoint_timeouts": []},
    }
    with pytest.raises(gate.GateError, match="duplicate scanned targets"):
        gate.load_findings(_write(tmp_path / "duplicate-targets.json", report))


def test_load_findings_rejects_a_result_not_in_the_scanned_targets(
    tmp_path: Path,
) -> None:
    report = {
        "results": [_result(path="app/other.py")],
        "errors": [],
        "skipped_rules": [],
        "paths": {"scanned": [PATH], "skipped": []},
        "time": {"fixpoint_timeouts": []},
    }
    with pytest.raises(gate.GateError, match="not in the scanned targets"):
        gate.load_findings(_write(tmp_path / "inconsistent.json", report))


def test_load_findings_rejects_root_pytest_temporary_targets(tmp_path: Path) -> None:
    report = {
        "results": [],
        "errors": [],
        "skipped_rules": [],
        "paths": {"scanned": ["./.pytest_tmp_trial/app/example.py"], "skipped": []},
        "time": {"fixpoint_timeouts": []},
    }
    with pytest.raises(gate.GateError, match="root pytest temporary target"):
        gate.load_findings(_write(tmp_path / "temporary-target.json", report))


@pytest.mark.parametrize(
    "patterns",
    [
        (*REVIEWED_SEMGREP_IGNORE_PATTERNS, "app/"),
        (
            REVIEWED_SEMGREP_IGNORE_PATTERNS[1],
            REVIEWED_SEMGREP_IGNORE_PATTERNS[0],
            *REVIEWED_SEMGREP_IGNORE_PATTERNS[2:],
        ),
    ],
)
def test_gate_requires_the_exact_reviewed_semgrepignore_pattern_set(
    tmp_path: Path, patterns: tuple[str, ...]
) -> None:
    repo = _repo(tmp_path)
    ignore_file = repo / ".semgrepignore"
    ignore_file.write_text(
        "\n".join(patterns) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    with pytest.raises(gate.GateError, match="reviewed exact pattern set"):
        gate.evaluate(
            _results(tmp_path, []),
            _dispositions(tmp_path, []),
            repo,
            TODAY,
        )


def test_gate_rejects_a_missing_semgrepignore_file(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    (repo / ".semgrepignore").unlink()
    with pytest.raises(gate.GateError, match="cannot read Semgrep ignore policy"):
        gate.evaluate(
            _results(tmp_path, []),
            _dispositions(tmp_path, []),
            repo,
            TODAY,
        )


def test_gate_rejects_a_symlinked_semgrepignore_file(tmp_path: Path) -> None:
    repo = _repo(tmp_path / "repo")
    external_ignore = tmp_path / "outside.semgrepignore"
    external_ignore.write_text(
        "\n".join(REVIEWED_SEMGREP_IGNORE_PATTERNS) + "\n", encoding="utf-8"
    )
    (repo / ".semgrepignore").unlink()
    (repo / ".semgrepignore").symlink_to(external_ignore)
    with pytest.raises(gate.GateError, match="must not be a symlink"):
        gate.validate_semgrep_ignore_policy(repo)


def test_live_repository_semgrepignore_matches_the_reviewed_pattern_set() -> None:
    assert (gate.validate_semgrep_ignore_policy(gate.REPOSITORY_ROOT)) is None


@pytest.mark.parametrize(
    ("results", "errors", "message"),
    [
        ({}, None, "list results and errors"),
        ([], "bad", "list results and errors"),
        (["not-object"], None, "must be an object"),
        ([], [{"message": "rule fetch failed"}], "results are not authoritative"),
    ],
)
def test_load_findings_fails_closed(
    tmp_path: Path, results: object, errors: object, message: str
) -> None:
    with pytest.raises(gate.GateError, match=message):
        gate.load_findings(_results(tmp_path, results, errors=errors))


# finding_keys and line digests -------------------------------------------------


def _reader(text: str) -> Any:
    return lambda _path: text.splitlines()


@pytest.mark.parametrize(
    "result",
    [
        _result(check_id=""),
        _result(check_id=5),
        _result(start="x"),
        _result(start={"line": "1"}),
        _result(start={"line": True}),
        _result(end="x"),
        _result(end={"line": "1"}),
        _result(end={"line": True}),
    ],
)
def test_finding_keys_rejects_malformed_findings(
    tmp_path: Path, result: dict[str, Any]
) -> None:
    with pytest.raises(gate.GateError):
        gate.finding_keys([result], tmp_path, _reader(LINE))


def test_finding_keys_rejects_a_line_outside_the_file(tmp_path: Path) -> None:
    _repo(tmp_path)
    with pytest.raises(gate.GateError, match="outside its file"):
        gate.finding_keys([_result(start={"line": 9})], tmp_path, _reader(LINE))
    with pytest.raises(gate.GateError, match="outside its file"):
        gate.finding_keys([_result(start={"line": 0})], tmp_path, _reader(LINE))


@pytest.mark.parametrize("end", [0, 2])
def test_finding_keys_rejects_an_invalid_reported_span(
    tmp_path: Path, end: int
) -> None:
    _repo(tmp_path)
    with pytest.raises(gate.GateError, match=r"source range.*outside its file"):
        gate.finding_keys([_result(end={"line": end})], tmp_path, _reader(LINE))


def test_finding_keys_rejects_a_symlink_outside_the_repository(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    target = tmp_path / "outside.py"
    target.write_text(LINE + "\n", encoding="utf-8")
    (repo / "app").mkdir(parents=True)
    (repo / PATH).symlink_to(target)
    with pytest.raises(gate.GateError, match="resolves outside the repository"):
        gate.finding_keys([_result()], repo, gate._read_source_lines)


@pytest.mark.parametrize("directory_link", [False, True])
def test_finding_keys_rejects_symlinks_inside_the_repository(
    tmp_path: Path, directory_link: bool
) -> None:
    repo = _repo(tmp_path)
    if directory_link:
        finding_path = "linked/example.py"
        (repo / "linked").symlink_to(repo / "app", target_is_directory=True)
    else:
        finding_path = "app/alias.py"
        (repo / finding_path).symlink_to(repo / PATH)
    with pytest.raises(gate.GateError, match="finding path contains a symlink"):
        gate.finding_keys([_result(path=finding_path)], repo, gate._read_source_lines)


def test_finding_keys_converts_a_symlink_loop_to_a_gate_error(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path)
    loop = repo / "app" / "loop.py"
    loop.symlink_to(loop)
    with pytest.raises(gate.GateError, match="finding path contains a symlink"):
        gate.finding_keys([_result(path="app/loop.py")], repo, gate._read_source_lines)


def test_finding_keys_rejects_ambiguous_identical_lines(
    tmp_path: Path,
) -> None:
    _repo(tmp_path)
    reads: list[Path] = []

    def reader(path: Path) -> list[str]:
        reads.append(path)
        return [LINE, LINE]

    with pytest.raises(gate.GateError, match="ambiguous finding identity"):
        gate.finding_keys(
            [
                _result(start={"line": 1}, end={"line": 1}),
                _result(start={"line": 2}, end={"line": 2}),
            ],
            tmp_path,
            reader,
        )
    assert reads == [tmp_path / PATH]


def test_read_source_lines_reports_missing_and_undecodable_files(
    tmp_path: Path,
) -> None:
    with pytest.raises(gate.GateError, match="cannot read finding source"):
        gate._read_source_lines(tmp_path / "missing.py")
    binary = tmp_path / "binary.py"
    binary.write_bytes(b"\xff\xfe\x00bad")
    with pytest.raises(gate.GateError, match="cannot read finding source"):
        gate._read_source_lines(binary)
    good = tmp_path / "good.py"
    good.write_text("one\ntwo\n", encoding="utf-8")
    assert gate._read_source_lines(good) == ["one", "two"]
    good.write_bytes("one\u2028two\r\nthree\n".encode())
    assert gate._read_source_lines(good) == ["one\u2028two", "three"]


# evaluate and main -------------------------------------------------------------


def test_evaluate_passes_when_every_finding_has_an_exact_disposition(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path)
    results = _results(tmp_path, [_result()])
    dispositions = _dispositions(tmp_path, [_disposition()])
    assert gate.evaluate(results, dispositions, repo, TODAY) == []


def test_evaluate_reports_an_unreviewed_finding(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    problems = gate.evaluate(
        _results(tmp_path, [_result()]), _dispositions(tmp_path, []), repo, TODAY
    )
    assert len(problems) == 1
    assert problems[0].startswith("unreviewed Semgrep finding")


def test_unreviewed_multiline_finding_reports_span_digest(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    problems = gate.evaluate(
        _results(tmp_path, [_result(end={"line": 2})]),
        _dispositions(tmp_path, []),
        repo,
        TODAY,
    )
    assert f"reported span 1-2 sha256 {CONTEXT_DIGEST}" in problems[0]


def test_evaluate_reports_a_stale_disposition(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    problems = gate.evaluate(
        _results(tmp_path, []), _dispositions(tmp_path, [_disposition()]), repo, TODAY
    )
    assert problems == [f"stale disposition matches no finding: {CHECK} {PATH}"]


def test_evaluate_rejects_scanned_targets_missing_from_the_repository(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path)
    report = _write(
        tmp_path / "missing-target.json",
        {
            "results": [],
            "errors": [],
            "skipped_rules": [],
            "paths": {"scanned": ["app/missing.py"], "skipped": []},
            "time": {"fixpoint_timeouts": []},
        },
    )
    with pytest.raises(gate.GateError, match="not a repository file"):
        gate.evaluate(report, _dispositions(tmp_path, []), repo, TODAY)


def test_evaluate_rejects_a_disposition_whose_line_changed(tmp_path: Path) -> None:
    repo = _repo(tmp_path, text="changed = line()\n")
    problems = gate.evaluate(
        _results(tmp_path, [_result()]),
        _dispositions(tmp_path, [_disposition()]),
        repo,
        TODAY,
    )
    assert any(p.startswith("unreviewed Semgrep finding") for p in problems)
    assert any(p.startswith("stale disposition") for p in problems)


def test_evaluate_rejects_changed_line_whitespace(tmp_path: Path) -> None:
    repo = _repo(tmp_path, text=LINE.strip() + "\n")
    problems = gate.evaluate(
        _results(tmp_path, [_result()]),
        _dispositions(tmp_path, [_disposition()]),
        repo,
        TODAY,
    )
    assert any(p.startswith("unreviewed Semgrep finding") for p in problems)
    assert any(p.startswith("stale disposition") for p in problems)


def test_multiline_disposition_binds_the_full_reported_span(tmp_path: Path) -> None:
    original = "value = (\n    safe()\n)\n"
    repo = _repo(tmp_path, original)
    entry = _disposition(
        line_sha256=hashlib.sha256(b"value = (").hexdigest(),
        span_sha256=hashlib.sha256(original.rstrip("\n").encode()).hexdigest(),
    )
    del entry["context"]
    results = _results(tmp_path, [_result(end={"line": 3})])
    dispositions = _dispositions(tmp_path, [entry])
    assert gate.evaluate(results, dispositions, repo, TODAY) == []

    (repo / PATH).write_text("value = (\n    dangerous()\n)\n", encoding="utf-8")
    assert gate.evaluate(results, dispositions, repo, TODAY), "changed span must block"


def test_single_line_disposition_binds_reviewed_context(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    results = _results(tmp_path, [_result()])
    dispositions = _dispositions(tmp_path, [_disposition()])
    assert gate.evaluate(results, dispositions, repo, TODAY) == []

    (repo / PATH).write_text(LINE + "\ncontext = changed()\n", encoding="utf-8")
    assert gate.evaluate(results, dispositions, repo, TODAY), (
        "changed context must block"
    )


def _companion(repo: Path, path: str, content: bytes) -> dict[str, str]:
    source = repo / path
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_bytes(content)
    return {"path": path, "sha256": hashlib.sha256(content).hexdigest()}


def test_react_finding_binds_complete_companion_bytes(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    companion = _companion(repo, "app/sanitizer.py", b"safe sanitizer\r\n")
    entry = _disposition(check_id=REACT_CHECK, companions=[companion])
    results = _results(tmp_path, [_result(check_id=REACT_CHECK)])
    dispositions = _dispositions(tmp_path, [entry])
    assert gate.evaluate(results, dispositions, repo, TODAY) == []

    (repo / companion["path"]).write_bytes(b"safe sanitizer\n")
    problems = gate.evaluate(results, dispositions, repo, TODAY)
    assert any("companion evidence changed" in problem for problem in problems)
    assert (repo / PATH).read_text(encoding="utf-8").splitlines()[0] == LINE


def test_every_declared_companion_is_required_to_match(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    first = _companion(repo, "app/sanitizer.py", b"sanitizer")
    second = _companion(repo, "app/policy.py", b"policy")
    entry = _disposition(check_id=REACT_CHECK, companions=[first, second])
    results = _results(tmp_path, [_result(check_id=REACT_CHECK)])
    dispositions = _dispositions(tmp_path, [entry])
    assert gate.evaluate(results, dispositions, repo, TODAY) == []

    (repo / second["path"]).write_bytes(b"modified policy")
    problems = gate.evaluate(results, dispositions, repo, TODAY)
    assert any(second["path"] in problem for problem in problems)


def test_disposition_rejects_missing_companion_file(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    entry = _disposition(companions=[{"path": "app/missing.py", "sha256": DIGEST}])
    with pytest.raises(gate.GateError, match="cannot read companion"):
        gate.evaluate(
            _results(tmp_path, [_result()]),
            _dispositions(tmp_path, [entry]),
            repo,
            TODAY,
        )


@pytest.mark.parametrize("directory_link", [False, True])
def test_disposition_rejects_companion_symlinks_even_inside_repo(
    tmp_path: Path, directory_link: bool
) -> None:
    repo = _repo(tmp_path)
    _companion(repo, "actual/sanitizer.py", b"safe")
    alias = repo / "linked"
    if directory_link:
        alias.symlink_to(repo / "actual", target_is_directory=True)
        path = "linked/sanitizer.py"
    else:
        alias.symlink_to(repo / "actual" / "sanitizer.py")
        path = "linked"
    entry = _disposition(companions=[{"path": path, "sha256": DIGEST}])
    with pytest.raises(gate.GateError, match=r"companion.*symlink"):
        gate.evaluate(
            _results(tmp_path, [_result()]),
            _dispositions(tmp_path, [entry]),
            repo,
            TODAY,
        )


def test_disposition_rejects_duplicate_physical_companions(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    one = _companion(repo, "app/one.py", b"safe")
    (repo / "app" / "two.py").hardlink_to(repo / one["path"])
    two = {"path": "app/two.py", "sha256": one["sha256"]}
    entry = _disposition(companions=[one, two])
    with pytest.raises(gate.GateError, match="duplicate companion"):
        gate.evaluate(
            _results(tmp_path, [_result()]),
            _dispositions(tmp_path, [entry]),
            repo,
            TODAY,
        )


def test_companion_cannot_be_hardlink_to_finding_source(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    (repo / "app" / "alias.py").hardlink_to(repo / PATH)
    entry = _disposition(companions=[{"path": "app/alias.py", "sha256": DIGEST}])
    with pytest.raises(gate.GateError, match="duplicate companion"):
        gate.evaluate(
            _results(tmp_path, [_result()]),
            _dispositions(tmp_path, [entry]),
            repo,
            TODAY,
        )


def test_companion_rejects_escape_even_if_link_check_is_evaded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _repo(tmp_path / "repo")
    outside = tmp_path / "outside.py"
    outside.write_bytes(b"safe")
    alias = repo / "linked.py"
    alias.symlink_to(outside)
    original = Path.is_symlink
    monkeypatch.setattr(
        Path, "is_symlink", lambda self: False if self == alias else original(self)
    )
    entry = _disposition(companions=[{"path": "linked.py", "sha256": DIGEST}])
    with pytest.raises(gate.GateError, match="companion resolves outside"):
        gate.evaluate(
            _results(tmp_path, [_result()]),
            _dispositions(tmp_path, [entry]),
            repo,
            TODAY,
        )


def test_companion_rejects_nonregular_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _repo(tmp_path)
    companion = _companion(repo, "app/sanitizer.py", b"safe")
    original = os.fstat

    def fake_fstat(fd: int) -> SimpleNamespace:
        actual = original(fd)
        return SimpleNamespace(
            st_mode=stat.S_IFIFO, st_dev=actual.st_dev, st_ino=actual.st_ino
        )

    monkeypatch.setattr(gate.os, "fstat", fake_fstat)
    entry = _disposition(companions=[companion])
    with pytest.raises(gate.GateError, match="regular file"):
        gate.evaluate(
            _results(tmp_path, [_result()]),
            _dispositions(tmp_path, [entry]),
            repo,
            TODAY,
        )


def test_companion_rejects_file_changed_during_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _repo(tmp_path)
    companion = _companion(repo, "app/sanitizer.py", b"safe")
    original = hashlib.file_digest

    def change_after_read(stream: Any, algorithm: str) -> Any:
        digest = original(stream, algorithm)
        (repo / companion["path"]).write_bytes(b"changed after digest")
        return digest

    monkeypatch.setattr(gate.hashlib, "file_digest", change_after_read)
    entry = _disposition(companions=[companion])
    with pytest.raises(gate.GateError, match="changed while being read"):
        gate.evaluate(
            _results(tmp_path, [_result()]),
            _dispositions(tmp_path, [entry]),
            repo,
            TODAY,
        )


def test_companion_rejects_disappeared_finding_source(tmp_path: Path) -> None:
    companion = gate.ReviewedCompanion("app/sanitizer.py", DIGEST)
    with pytest.raises(gate.GateError, match="cannot read finding source"):
        gate._companion_problems(tmp_path, PATH, (companion,))


def test_matching_disposition_without_span_evidence_blocks_multiline_finding(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path)
    results = _results(tmp_path, [_result(end={"line": 2})])
    assert gate.evaluate(
        results, _dispositions(tmp_path, [_disposition()]), repo, TODAY
    )


def test_single_line_finding_requires_containing_reviewed_context(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path, LINE + "\nsecond\nthird\n")
    entry = _disposition(context={"start_line": 2, "end_line": 3, "sha256": DIGEST})
    assert gate.evaluate(
        _results(tmp_path, [_result()]), _dispositions(tmp_path, [entry]), repo, TODAY
    )


def test_single_line_finding_rejects_context_outside_file(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    entry = _disposition(context={"start_line": 1, "end_line": 3, "sha256": DIGEST})
    with pytest.raises(gate.GateError, match=r"source range.*outside its file"):
        gate.evaluate(
            _results(tmp_path, [_result()]),
            _dispositions(tmp_path, [entry]),
            repo,
            TODAY,
        )


def test_single_line_finding_does_not_accept_only_span_digest(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    entry = _disposition(span_sha256=DIGEST)
    del entry["context"]
    assert gate.evaluate(
        _results(tmp_path, [_result()]), _dispositions(tmp_path, [entry]), repo, TODAY
    )


def test_evaluate_uses_the_default_reader_on_real_files(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    assert (
        gate.evaluate(
            _results(tmp_path, [_result()]),
            _dispositions(tmp_path, [_disposition()]),
            repo,
            TODAY,
        )
        == []
    )


def _main_args(tmp_path: Path, repo: Path, dispositions: Path) -> list[str]:
    return [
        str(_results(tmp_path, [_result()])),
        "--dispositions",
        str(dispositions),
        "--repository-root",
        str(repo),
    ]


def test_main_returns_zero_when_the_gate_passes(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _repo(tmp_path)
    args = _main_args(tmp_path, repo, _dispositions(tmp_path, [_disposition()]))
    assert gate.main(args) == 0
    assert "every finding matches" in capsys.readouterr().out


def test_main_returns_one_and_annotates_every_problem(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _repo(tmp_path)
    args = _main_args(tmp_path, repo, _dispositions(tmp_path, []))
    assert gate.main(args) == 1
    assert "::error::Semgrep dispositions gate: unreviewed" in capsys.readouterr().out


def test_main_returns_one_on_a_gate_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _repo(tmp_path)
    malformed = _write(tmp_path / "bad.json", [])
    args = _main_args(tmp_path, repo, malformed)
    assert gate.main(args) == 1
    assert "JSON root must be an object" in capsys.readouterr().out


def test_main_uses_utc_date_at_a_local_timezone_boundary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: dict[str, date] = {}
    fixed_utc = datetime(2026, 11, 4, 22, 30, tzinfo=UTC)

    class FixedClock:
        @staticmethod
        def now(tz: object) -> datetime:
            assert tz is UTC
            return fixed_utc

    def evaluate_at_date(
        _results_path: Path,
        _dispositions_path: Path,
        _repository_root: Path,
        today: date,
        check_id_prefix: str = "",
    ) -> list[str]:
        assert check_id_prefix == ""
        captured["today"] = today
        return []

    monkeypatch.setattr(gate, "datetime", FixedClock)
    monkeypatch.setattr(gate, "evaluate", evaluate_at_date)
    assert gate.main([str(tmp_path / "unused.json")]) == 0
    assert fixed_utc.astimezone(timezone(timedelta(hours=3))).date() == date(
        2026, 11, 5
    )
    assert captured["today"] == date(2026, 11, 4)


def test_main_does_not_allow_callers_to_backdate_expiry_checks(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path)
    args = _main_args(tmp_path, repo, _dispositions(tmp_path, []))
    with pytest.raises(SystemExit) as exit_info:
        gate.main([*args, "--today", "2020-01-01"])
    assert exit_info.value.code == 2


def test_main_defaults_to_the_repository_dispositions_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _repo(tmp_path)
    dispositions = _dispositions(tmp_path, [])
    monkeypatch.setattr(gate, "DEFAULT_DISPOSITIONS", dispositions)
    results = _results(tmp_path, [])
    assert gate.main([str(results), "--repository-root", str(repo)]) == 0


def test_script_entry_point_exits_with_the_gate_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _repo(tmp_path)
    args = _main_args(tmp_path, repo, _dispositions(tmp_path, [_disposition()]))
    monkeypatch.setattr(sys, "argv", ["semgrep_dispositions_gate.py", *args])
    with pytest.raises(SystemExit) as exit_info:
        runpy.run_path(str(gate.__file__), run_name="__main__")
    assert exit_info.value.code == 0


def test_load_findings_rejects_warn_level_parse_notes(tmp_path: Path) -> None:
    warnings = [{"level": "warn", "type": "Syntax error", "path": "x.tsx"}]
    with pytest.raises(gate.GateError, match="results are not authoritative"):
        gate.load_findings(_results(tmp_path, [_result()], errors=warnings))


@pytest.mark.parametrize(
    "error", [{"level": "error", "type": "Engine"}, "not-an-object"]
)
def test_load_findings_rejects_error_level_or_malformed_entries(
    tmp_path: Path, error: object
) -> None:
    with pytest.raises(gate.GateError, match="results are not authoritative"):
        gate.load_findings(_results(tmp_path, [], errors=[error]))


def test_check_id_prefix_is_stripped_from_every_finding(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    results = _results(tmp_path, [_result(check_id="out." + CHECK)])
    dispositions = _dispositions(tmp_path, [_disposition()])
    problems = gate.evaluate(results, dispositions, repo, TODAY, check_id_prefix="out.")
    assert problems == []


def test_finding_without_the_fixed_prefix_fails_closed(tmp_path: Path) -> None:
    with pytest.raises(gate.GateError, match="lacks the fixed prefix"):
        gate.finding_keys([_result()], tmp_path, _reader(LINE), "out.")


def test_prefix_that_leaves_an_empty_check_id_fails_closed(tmp_path: Path) -> None:
    with pytest.raises(gate.GateError, match="empty after prefix removal"):
        gate.finding_keys([_result(check_id="out.")], tmp_path, _reader(LINE), "out.")


def test_main_accepts_the_strip_prefix_option(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _repo(tmp_path)
    results = _write(
        tmp_path / "prefixed.json",
        {
            "results": [_result(check_id="out." + CHECK)],
            "errors": [],
            "skipped_rules": [],
            "paths": {"scanned": [PATH], "skipped": []},
            "time": {"fixpoint_timeouts": []},
        },
    )
    args = [
        str(results),
        "--dispositions",
        str(_dispositions(tmp_path, [_disposition()])),
        "--repository-root",
        str(repo),
        "--strip-check-prefix",
        "out.",
    ]
    assert gate.main(args) == 0


def test_fixpoint_diagnostics_include_only_bounded_source_coordinates() -> None:
    report = gate._fixpoint_timeout_details(
        [
            {
                "rule_id": "python.security.example",
                "message": "private scanner message",
                "source": "private source text",
                "location": {"path": "./app/example.py", "start": {"line": 12}},
            }
        ]
    )
    assert json.loads(report) == {
        "details": [
            {"rule_id": "python.security.example", "path": "app/example.py", "line": 12}
        ],
        "omitted": 0,
    }
    assert "private" not in report


@pytest.mark.parametrize(
    "path",
    ["../outside.py", "/absolute.py", "app/file\n::error::text", "a\x1bb", "x" * 241],
)
def test_fixpoint_diagnostics_omit_unsafe_paths(path: str) -> None:
    report = gate._fixpoint_timeout_details([{"location": {"path": path}}])
    assert json.loads(report) == {"details": [{}], "omitted": 0}


@pytest.mark.parametrize("rule_id", [None, 1, "bad\nrule", "a" * 201])
def test_fixpoint_diagnostics_omit_unsafe_rule_ids(rule_id: object) -> None:
    report = gate._fixpoint_timeout_details([{"rule_id": rule_id}])
    assert json.loads(report) == {"details": [{}], "omitted": 0}


@pytest.mark.parametrize("line", [None, True, 0, -1, "12", 1_000_000_001])
def test_fixpoint_diagnostics_omit_invalid_lines(line: object) -> None:
    report = gate._fixpoint_timeout_details([{"location": {"start": {"line": line}}}])
    assert json.loads(report) == {"details": [{}], "omitted": 0}


def test_fixpoint_diagnostics_bound_entries_and_tolerate_unknown_shapes() -> None:
    report = gate._fixpoint_timeout_details(
        [None, {}, "unknown", {"location": None}, {"location": {"start": None}}] * 20
    )
    assert json.loads(report) == {"details": [{}] * 8, "omitted": 92}


def test_fixpoint_failure_retains_count_and_source_without_becoming_a_pass(
    tmp_path: Path,
) -> None:
    report = {
        "results": [],
        "errors": [],
        "skipped_rules": [],
        "paths": {"scanned": [PATH], "skipped": []},
        "time": {
            "fixpoint_timeouts": [
                {"rule_id": CHECK, "location": {"path": PATH, "start": {"line": 7}}}
            ]
        },
    }
    with pytest.raises(gate.GateError) as caught:
        gate.load_findings(_write(tmp_path / "timed-out.json", report))
    message = str(caught.value)
    assert "1 fixpoint timeout(s); results are not authoritative" in message
    assert f'"rule_id":"{CHECK}"' in message
    assert f'"path":"{PATH}"' in message
    assert '"line":7' in message
