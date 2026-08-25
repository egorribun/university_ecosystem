from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from tests.quality_normalizer_v2_testkit import (
    CANONICAL_REPORT_ARGUMENTS,
    TOOL_VERSION_ARGUMENTS,
    write_complete_evidence,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
NORMALIZER_PATH = (
    REPOSITORY_ROOT / "scripts" / "quality" / "normalize_coverage_reports.py"
)
CONTRACT_PATH = REPOSITORY_ROOT / "quality" / "quality-contract.json"
SCHEMA_PATH = REPOSITORY_ROOT / "quality" / "coverage-manifest.schema.json"
GIT_EXECUTABLE = shutil.which("git")


@pytest.fixture
def evidence_repo(tmp_path: Path) -> Path:
    assert GIT_EXECUTABLE is not None
    subprocess.run(  # noqa: S603
        [GIT_EXECUTABLE, "init", "-q"], cwd=tmp_path, check=True
    )
    subprocess.run(  # noqa: S603
        [
            GIT_EXECUTABLE,
            "-c",
            "user.email=test@example.invalid",
            "-c",
            "user.name=Quality Test",
            "commit",
            "--allow-empty",
            "-qm",
            "fixture",
        ],
        cwd=tmp_path,
        check=True,
    )
    contract_target = tmp_path / "quality" / "quality-contract.json"
    contract_target.parent.mkdir(parents=True, exist_ok=True)
    contract_target.write_bytes(CONTRACT_PATH.read_bytes())
    (tmp_path / "quality" / "ownership-mapping.json").write_text(
        json.dumps({"tier0_rules": ["**/spicedb/**"]}),
        encoding="utf-8",
    )
    write_complete_evidence(tmp_path)
    return tmp_path


def _head(root: Path) -> str:
    assert GIT_EXECUTABLE is not None
    return subprocess.check_output(  # noqa: S603
        [GIT_EXECUTABLE, "rev-parse", "HEAD"], cwd=root, text=True
    ).strip()


def _full_arguments(root: Path) -> list[str]:
    return [
        "--repository-root",
        str(root),
        "--contract",
        str(root / "quality" / "quality-contract.json"),
        "--commit-sha",
        _head(root),
        "--generated-at",
        "2026-08-25T12:00:00Z",
        "--output",
        str(root / "artifacts" / "coverage" / "quality-manifest.json"),
        "--provenance-mode",
        "local",
        *TOOL_VERSION_ARGUMENTS,
        *CANONICAL_REPORT_ARGUMENTS,
    ]


def _run(root: Path, arguments: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603
        [sys.executable, str(NORMALIZER_PATH), *arguments],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )


def test_normalizer_v2_emits_current_complete_schema_valid_evidence(
    evidence_repo: Path,
) -> None:
    result = _run(evidence_repo, _full_arguments(evidence_repo))

    assert result.returncode == 0, result.stderr
    output = evidence_repo / "artifacts" / "coverage" / "quality-manifest.json"
    manifest = json.loads(output.read_text(encoding="utf-8"))
    Draft202012Validator(json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))).validate(
        manifest
    )
    assert manifest["schema_version"] == 2
    assert manifest["commit_sha"] == _head(evidence_repo)
    assert manifest["validation"] == {"valid": True, "errors": []}
    assert manifest["tier0"]["status"] == "ready"
    assert manifest["tier0"]["files"][0]["metrics"]["statements"]["percent"] == 100
    assert (
        manifest["tier0"]["files"][0]["metrics"]["branches"]["status"] == "unsupported"
    )
    assert len(manifest["reports"]) == 16
    python_json = next(
        report
        for report in manifest["reports"]
        if report["format"] == "coverage-py-json"
    )
    raw = (evidence_repo / python_json["path"]).read_bytes()
    assert python_json["size_bytes"] == len(raw)
    assert python_json["sha256"] == hashlib.sha256(raw).hexdigest()
    assert manifest["provenance"] == {
        "mode": "local",
        "workflow_run_id": "local",
        "workflow_run_attempt": "local",
        "workflow_event": "local",
        "workflow_repository": "local",
        "workflow_ref": "local",
        "workflow_job": "local",
    }


def test_normalizer_v2_rejects_sha_mismatch_before_writing(evidence_repo: Path) -> None:
    arguments = _full_arguments(evidence_repo)
    arguments[arguments.index("--commit-sha") + 1] = "0" * 40

    result = _run(evidence_repo, arguments)

    assert result.returncode == 2
    assert "current repository HEAD" in result.stderr
    assert not (evidence_repo / "artifacts/coverage/quality-manifest.json").exists()


@pytest.mark.parametrize("fault", ["missing", "empty", "symlink"])
def test_normalizer_v2_rejects_incomplete_or_unsafe_python_json(
    evidence_repo: Path,
    fault: str,
) -> None:
    report = evidence_repo / "artifacts/coverage/python/coverage.json"
    if fault == "missing":
        report.unlink()
    elif fault == "empty":
        report.write_bytes(b"")
    else:
        target = report.with_suffix(".target")
        target.write_bytes(report.read_bytes())
        report.unlink()
        try:
            report.symlink_to(target)
        except OSError:
            pytest.skip("symlink creation is unavailable on this platform")

    result = _run(evidence_repo, _full_arguments(evidence_repo))

    assert result.returncode != 0
    assert fault in result.stderr.lower()


def test_normalizer_v2_requires_every_declared_input_exactly_once(
    evidence_repo: Path,
) -> None:
    arguments = _full_arguments(evidence_repo)
    index = arguments.index("--python-json")
    del arguments[index : index + 2]

    result = _run(evidence_repo, arguments)

    assert result.returncode != 0
    manifest = json.loads(
        (evidence_repo / "artifacts/coverage/quality-manifest.json").read_text(
            encoding="utf-8"
        )
    )
    assert manifest["validation"]["valid"] is False
    assert manifest["missing_reports"] == [
        {
            "component": "python",
            "path": "artifacts/coverage/python/coverage.json",
            "reason_code": "expected_report_not_supplied",
        }
    ]


@pytest.mark.parametrize(
    "missing_field",
    ["executed_lines", "missing_lines", "executed_branches", "missing_branches"],
)
def test_normalizer_v2_rejects_partial_python_json_records(
    evidence_repo: Path,
    missing_field: str,
) -> None:
    report_path = evidence_repo / "artifacts/coverage/python/coverage.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    del report["files"]["app/example.py"][missing_field]
    report_path.write_text(json.dumps(report), encoding="utf-8")

    result = _run(evidence_repo, _full_arguments(evidence_repo))

    assert result.returncode == 2
    assert missing_field in result.stderr
    manifest = json.loads(
        (evidence_repo / "artifacts/coverage/quality-manifest.json").read_text(
            encoding="utf-8"
        )
    )
    assert manifest["validation"]["valid"] is False


def test_normalizer_v2_rejects_istanbul_counters_without_source_maps(
    evidence_repo: Path,
) -> None:
    report_path = evidence_repo / "frontend/coverage/coverage-final.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    del report["frontend/src/example.ts"]["statementMap"]
    report_path.write_text(json.dumps(report), encoding="utf-8")

    result = _run(evidence_repo, _full_arguments(evidence_repo))

    assert result.returncode == 2
    assert "statementMap" in result.stderr


def test_normalizer_v2_rejects_nightly_rust_source_inventory_extras(
    evidence_repo: Path,
) -> None:
    report_path = evidence_repo / "artifacts/coverage/rust/rust-native/branch-llvm.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    extra = json.loads(json.dumps(report["data"][0]["files"][0]))
    extra["filename"] = "native/rust_ext/src/extra.rs"
    report["data"][0]["files"].append(extra)
    extra_source = evidence_repo / "native/rust_ext/src/extra.rs"
    extra_source.write_text("pub fn extra() {}\n", encoding="utf-8")
    report_path.write_text(json.dumps(report), encoding="utf-8")

    result = _run(evidence_repo, _full_arguments(evidence_repo))

    assert result.returncode == 2
    assert "unexpected source native/rust_ext/src/extra.rs" in result.stderr


def test_normalizer_v2_rejects_duplicate_declared_input(evidence_repo: Path) -> None:
    arguments = _full_arguments(evidence_repo)
    arguments.extend(["--python-xml", "coverage.xml"])

    result = _run(evidence_repo, arguments)

    assert result.returncode == 1
    assert "exactly once" in result.stderr
    assert "Traceback" not in result.stderr


def test_normalizer_v2_requires_explicit_local_or_workflow_provenance(
    evidence_repo: Path,
) -> None:
    arguments = _full_arguments(evidence_repo)
    index = arguments.index("--provenance-mode")
    del arguments[index : index + 2]

    result = _run(evidence_repo, arguments)

    assert result.returncode == 2
    assert "provenance-mode" in result.stderr
