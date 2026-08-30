from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import shutil
import subprocess
from pathlib import Path
from types import ModuleType

import pytest

from tests.symlink_support import DIRECTORY_SYMLINKS_SUPPORTED

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
VALIDATOR_PATH = (
    REPOSITORY_ROOT / "scripts" / "quality" / "validate_quality_contract.py"
)
SCHEMA_PATH = REPOSITORY_ROOT / "quality" / "coverage-manifest.schema.json"
CONTRACT_PATH = REPOSITORY_ROOT / "quality" / "quality-contract.json"
METRICS = ("lines", "statements", "branches", "functions")
GIT_EXECUTABLE = shutil.which("git")


def _load_validator() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "quality_validator_v2", VALIDATOR_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _head(repo_root: Path = REPOSITORY_ROOT) -> str:
    assert GIT_EXECUTABLE is not None
    return subprocess.check_output(  # noqa: S603
        [GIT_EXECUTABLE, "rev-parse", "HEAD"],
        cwd=repo_root,
        text=True,
    ).strip()


def _native() -> dict[str, object]:
    return {"status": "native", "covered": 1, "total": 1, "percent": 100.0}


def _derived() -> dict[str, object]:
    return {
        "status": "derived",
        "covered": 1,
        "total": 1,
        "percent": 100.0,
        "derivation": "unique source lines in coverprofile blocks; covered when any overlapping block has count greater than zero",
    }


def _unsupported(reason: str = "toolchain_metric_unavailable") -> dict[str, object]:
    return {
        "status": "unsupported",
        "covered": None,
        "total": None,
        "percent": None,
        "reason_code": reason,
    }


def _missing() -> dict[str, object]:
    return {"status": "missing", "covered": None, "total": None, "percent": None}


def _valid_manifest_fixture(
    tmp_path: Path,
) -> tuple[dict[str, object], dict[str, object], Path]:
    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    assert contract["version"] == 2
    tier0_source = tmp_path / "services" / "pkg" / "spicedb" / "client.go"
    tier0_source.parent.mkdir(parents=True, exist_ok=True)
    tier0_source.write_text("package spicedb\n", encoding="utf-8")
    # Tier0 inventory is intentionally Git-backed.  Keep the fixture source
    # in the index so the manifest exercises the same tracked HEAD contract as
    # the production validator (coverage artifacts remain untracked evidence).
    assert GIT_EXECUTABLE is not None
    subprocess.run(  # noqa: S603
        [GIT_EXECUTABLE, "add", "services/pkg/spicedb/client.go"],
        cwd=tmp_path,
        check=True,
    )
    subprocess.run(  # noqa: S603
        [
            GIT_EXECUTABLE,
            "-c",
            "user.email=test@example.invalid",
            "-c",
            "user.name=Quality Test",
            "commit",
            "-qm",
            "track Tier0 source",
        ],
        cwd=tmp_path,
        check=True,
    )
    reports: list[dict[str, object]] = []
    for index, declaration in enumerate(contract["coverage_reports"]):
        path = tmp_path / declaration["path"]
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = f"report-{index}\n".encode()
        path.write_bytes(payload)
        reports.append(
            {
                "component": declaration["component"],
                "format": declaration["format"],
                "path": declaration["path"],
                "sha256": hashlib.sha256(payload).hexdigest(),
                "size_bytes": len(payload),
            }
        )

    components: dict[str, object] = {}
    for component, config in contract["components"].items():
        floors = config["coverage"]
        metrics = {
            metric: (_native() if floor == 100 else _unsupported())
            for metric, floor in floors.items()
        }
        has_report = any(report["component"] == component for report in reports)
        components[component] = {
            "status": "passed" if has_report else "not_applicable",
            "metrics": metrics,
            "errors": [],
        }

    tier0_metrics = {
        "lines": _derived(),
        "statements": _native(),
        "branches": _unsupported("go_coverprofile_has_no_branch_counter"),
        "functions": _unsupported("go_coverprofile_has_no_function_counter"),
    }
    manifest: dict[str, object] = {
        "schema_version": 2,
        "commit_sha": _head(tmp_path),
        "generated_at": "2026-08-25T12:00:00Z",
        "manifest_path": contract["manifest_path"],
        "source_roots": contract["source_roots"],
        "coverage_scope": contract["coverage_scope"],
        "tool_versions": {
            "coverage.py": "7.10.0",
            "cargo-llvm-cov": "0.6.19",
            "go": "1.26.0",
            "node": "24.7.0",
            "python": "3.14.0",
            "quality-normalizer": "2.0.0",
            "rustc": "1.90.0",
            "rustc-nightly": "1.92.0-nightly",
            "vitest": "4.0.0",
        },
        "provenance": {
            "mode": "local",
            "workflow_run_id": "local",
            "workflow_run_attempt": "local",
            "workflow_event": "local",
            "workflow_repository": "local",
            "workflow_ref": "local",
            "workflow_job": "local",
        },
        "generation": {
            "command": "scripts/quality/normalize_coverage_reports.py",
            "normalizer_version": "2.0.0",
        },
        "reports": reports,
        "components": components,
        "tier0": {
            "status": "ready",
            "rules": ["**/spicedb/**"],
            "coverage": tier0_metrics,
            "metric_summary": {
                "lines": {"applicable_files": 1, "not_applicable_files": 0},
                "statements": {"applicable_files": 1, "not_applicable_files": 0},
                "branches": {"applicable_files": 0, "not_applicable_files": 1},
                "functions": {"applicable_files": 0, "not_applicable_files": 1},
            },
            "files": [
                {
                    "path": "services/pkg/spicedb/client.go",
                    "component": "go-shared",
                    "metrics": tier0_metrics,
                }
            ],
            "errors": [],
        },
        "missing_reports": [],
        "validation": {"valid": True, "errors": []},
    }
    manifest_path = tmp_path / contract["manifest_path"]
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    return contract, manifest, manifest_path


@pytest.fixture
def git_evidence_root(tmp_path: Path) -> Path:
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
    quality_root = tmp_path / "quality"
    quality_root.mkdir(parents=True, exist_ok=True)
    (quality_root / "ownership-mapping.json").write_text(
        json.dumps({"tier0_rules": ["**/spicedb/**"]}),
        encoding="utf-8",
    )
    return tmp_path


def _validate(
    validator: ModuleType,
    manifest: dict[str, object],
    contract: dict[str, object],
    manifest_path: Path,
    repo_root: Path,
) -> list[str]:
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    return validator.validate_manifest_evidence(
        manifest,
        contract=contract,
        manifest_path=manifest_path,
        repository_root=repo_root,
        schema_path=SCHEMA_PATH,
    )


def test_v2_manifest_accepts_go_tier0_na_only_for_zero_floor(
    git_evidence_root: Path,
) -> None:
    validator = _load_validator()
    contract, manifest, manifest_path = _valid_manifest_fixture(git_evidence_root)

    assert (
        _validate(validator, manifest, contract, manifest_path, git_evidence_root) == []
    )


def test_v2_manifest_rejects_coverage_scope_drift(
    git_evidence_root: Path,
) -> None:
    validator = _load_validator()
    contract, manifest, manifest_path = _valid_manifest_fixture(git_evidence_root)
    manifest["coverage_scope"] = copy.deepcopy(contract["coverage_scope"])
    manifest["coverage_scope"]["python"] = ["app/subtree"]

    errors = _validate(validator, manifest, contract, manifest_path, git_evidence_root)

    assert any("coverage_scope" in error for error in errors)


def test_v2_manifest_rejects_tier0_source_outside_coverage_scope(
    git_evidence_root: Path,
) -> None:
    validator = _load_validator()
    contract, manifest, manifest_path = _valid_manifest_fixture(git_evidence_root)
    migration_path = git_evidence_root / "alembic/versions/20260825_example.py"
    migration_path.parent.mkdir(parents=True, exist_ok=True)
    migration_path.write_text("revision = '20260825'\n", encoding="utf-8")
    forged = copy.deepcopy(manifest["tier0"]["files"][0])
    forged["path"] = "alembic/versions/20260825_example.py"
    forged["component"] = "python"
    manifest["tier0"]["files"] = [forged]

    errors = _validate(validator, manifest, contract, manifest_path, git_evidence_root)

    assert any("outside coverage_scope.python" in error for error in errors)


@pytest.mark.parametrize("commit_sha", ["a1b2c3d", "A" * 40, "0" * 39, "g" * 40])
def test_v2_manifest_rejects_invalid_or_noncanonical_sha(
    git_evidence_root: Path,
    commit_sha: str,
) -> None:
    validator = _load_validator()
    contract, manifest, manifest_path = _valid_manifest_fixture(git_evidence_root)
    manifest["commit_sha"] = commit_sha

    errors = _validate(validator, manifest, contract, manifest_path, git_evidence_root)

    assert any("commit_sha" in error for error in errors)


def test_v2_manifest_rejects_sha_different_from_repository_head(
    git_evidence_root: Path,
) -> None:
    validator = _load_validator()
    contract, manifest, manifest_path = _valid_manifest_fixture(git_evidence_root)
    manifest["commit_sha"] = "0" * 40

    errors = _validate(validator, manifest, contract, manifest_path, git_evidence_root)

    assert any("current repository HEAD" in error for error in errors)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda manifest: manifest.update({"unexpected": True}), "schema"),
        (
            lambda manifest: manifest["validation"].update({"valid": False}),
            "validation.valid",
        ),
        (
            lambda manifest: manifest["validation"]["errors"].append("stale"),
            "validation.errors",
        ),
        (
            lambda manifest: manifest["components"]["python"].update(
                {"status": "failed"}
            ),
            "components.python.status",
        ),
        (
            lambda manifest: manifest["tier0"].update({"status": "failed"}),
            "tier0.status",
        ),
    ],
)
def test_v2_manifest_rejects_schema_and_declared_failure_states(
    git_evidence_root: Path,
    mutation: object,
    message: str,
) -> None:
    validator = _load_validator()
    contract, manifest, manifest_path = _valid_manifest_fixture(git_evidence_root)
    mutation(manifest)

    errors = _validate(validator, manifest, contract, manifest_path, git_evidence_root)

    assert any(message in error for error in errors)


@pytest.mark.parametrize("fault", ["hash", "size", "empty", "missing"])
def test_v2_manifest_recomputes_report_integrity(
    git_evidence_root: Path,
    fault: str,
) -> None:
    validator = _load_validator()
    contract, manifest, manifest_path = _valid_manifest_fixture(git_evidence_root)
    report = manifest["reports"][0]
    report_path = git_evidence_root / report["path"]
    if fault == "hash":
        report["sha256"] = "0" * 64
    elif fault == "size":
        report["size_bytes"] += 1
    elif fault == "empty":
        report_path.write_bytes(b"")
    else:
        report_path.unlink()

    errors = _validate(validator, manifest, contract, manifest_path, git_evidence_root)

    assert any(report["path"] in error for error in errors)


@pytest.mark.parametrize("fault", ["extra", "duplicate", "escape", "absolute"])
def test_v2_manifest_rejects_noncanonical_report_registry(
    git_evidence_root: Path,
    fault: str,
) -> None:
    validator = _load_validator()
    contract, manifest, manifest_path = _valid_manifest_fixture(git_evidence_root)
    if fault == "extra":
        extra = copy.deepcopy(manifest["reports"][0])
        extra["path"] = "artifacts/coverage/extra.json"
        manifest["reports"].append(extra)
    elif fault == "duplicate":
        manifest["reports"].append(copy.deepcopy(manifest["reports"][0]))
    elif fault == "escape":
        manifest["reports"][0]["path"] = "../outside.xml"
    else:
        manifest["reports"][0]["path"] = str(
            (git_evidence_root / "absolute.xml").resolve()
        )

    errors = _validate(validator, manifest, contract, manifest_path, git_evidence_root)

    assert any("report" in error.lower() for error in errors)


@pytest.mark.skipif(
    not DIRECTORY_SYMLINKS_SUPPORTED,
    reason="symlink creation is unavailable on this platform",
)
def test_v2_manifest_rejects_symlinked_report(git_evidence_root: Path) -> None:
    validator = _load_validator()
    contract, manifest, manifest_path = _valid_manifest_fixture(git_evidence_root)
    report = manifest["reports"][0]
    report_path = git_evidence_root / report["path"]
    target = report_path.with_suffix(".target")
    target.write_bytes(report_path.read_bytes())
    report_path.unlink()
    report_path.symlink_to(target)

    errors = _validate(validator, manifest, contract, manifest_path, git_evidence_root)

    assert any("symlink" in error.lower() for error in errors)


def test_v2_manifest_rejects_unsupported_tier0_metric_when_floor_is_100(
    git_evidence_root: Path,
) -> None:
    validator = _load_validator()
    contract, manifest, manifest_path = _valid_manifest_fixture(git_evidence_root)
    manifest["tier0"]["files"][0]["metrics"]["statements"] = _unsupported()

    errors = _validate(validator, manifest, contract, manifest_path, git_evidence_root)

    assert any("statements" in error and "floor" in error for error in errors)


@pytest.mark.parametrize("status", ["missing", "experimental"])
def test_v2_manifest_rejects_missing_or_experimental_even_with_zero_floor(
    git_evidence_root: Path,
    status: str,
) -> None:
    validator = _load_validator()
    contract, manifest, manifest_path = _valid_manifest_fixture(git_evidence_root)
    metric = _missing()
    if status == "experimental":
        metric = _unsupported("experimental_toolchain")
        metric["status"] = "experimental"
    manifest["tier0"]["files"][0]["metrics"]["branches"] = metric

    errors = _validate(validator, manifest, contract, manifest_path, git_evidence_root)

    assert any("branches" in error and status in error for error in errors)


def test_v2_manifest_rejects_measured_tier0_statements_below_100(
    git_evidence_root: Path,
) -> None:
    validator = _load_validator()
    contract, manifest, manifest_path = _valid_manifest_fixture(git_evidence_root)
    manifest["tier0"]["files"][0]["metrics"]["statements"] = {
        "status": "native",
        "covered": 9,
        "total": 10,
        "percent": 90.0,
    }

    errors = _validate(validator, manifest, contract, manifest_path, git_evidence_root)

    assert any("statements" in error and "100" in error for error in errors)


def test_v2_manifest_na_does_not_enter_aggregate_denominator(
    git_evidence_root: Path,
) -> None:
    validator = _load_validator()
    contract, manifest, manifest_path = _valid_manifest_fixture(git_evidence_root)
    manifest["tier0"]["metric_summary"]["branches"] = {
        "applicable_files": 1,
        "not_applicable_files": 0,
    }

    errors = _validate(validator, manifest, contract, manifest_path, git_evidence_root)

    assert any("metric_summary.branches" in error for error in errors)


def test_v2_manifest_rejects_manifest_authored_tier0_rules(
    git_evidence_root: Path,
) -> None:
    validator = _load_validator()
    contract, manifest, manifest_path = _valid_manifest_fixture(git_evidence_root)
    manifest["tier0"]["rules"] = ["**/nothing-security-critical/**"]

    errors = _validate(validator, manifest, contract, manifest_path, git_evidence_root)

    assert any("canonical ownership-mapping" in error for error in errors)


def test_v2_manifest_rejects_measured_undercoverage_even_when_floor_is_zero(
    git_evidence_root: Path,
) -> None:
    validator = _load_validator()
    contract, manifest, manifest_path = _valid_manifest_fixture(git_evidence_root)
    undercovered = {"status": "native", "covered": 0, "total": 1, "percent": 0.0}
    manifest["tier0"]["files"][0]["metrics"]["branches"] = undercovered
    manifest["tier0"]["coverage"]["branches"] = undercovered
    manifest["tier0"]["metric_summary"]["branches"] = {
        "applicable_files": 1,
        "not_applicable_files": 0,
    }

    errors = _validate(validator, manifest, contract, manifest_path, git_evidence_root)

    assert any("branches" in error and "100" in error for error in errors)


def test_v2_manifest_recomputes_percent_from_native_counters(
    git_evidence_root: Path,
) -> None:
    validator = _load_validator()
    contract, manifest, manifest_path = _valid_manifest_fixture(git_evidence_root)
    forged = {"status": "native", "covered": 0, "total": 10, "percent": 100.0}
    manifest["tier0"]["files"][0]["metrics"]["branches"] = forged
    manifest["tier0"]["coverage"]["branches"] = forged
    manifest["tier0"]["metric_summary"]["branches"] = {
        "applicable_files": 1,
        "not_applicable_files": 0,
    }

    errors = _validate(validator, manifest, contract, manifest_path, git_evidence_root)

    assert any("covered/total counters" in error for error in errors)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda manifest: manifest["tool_versions"].pop("go"), "tool_versions"),
        (
            lambda manifest: manifest["tool_versions"].update({"go": "latest"}),
            "tool_versions.go",
        ),
        (
            lambda manifest: manifest["tool_versions"].update({"unrelated": "1.0.0"}),
            "unexpected tools",
        ),
        (
            lambda manifest: manifest["generation"].update(
                {"command": "python arbitrary.py"}
            ),
            "generation.command",
        ),
    ],
)
def test_v2_manifest_requires_exact_tool_and_generator_provenance(
    git_evidence_root: Path,
    mutation: object,
    message: str,
) -> None:
    validator = _load_validator()
    contract, manifest, manifest_path = _valid_manifest_fixture(git_evidence_root)
    mutation(manifest)

    errors = _validate(validator, manifest, contract, manifest_path, git_evidence_root)

    assert any(message in error for error in errors)


def test_contract_v2_removes_manifest_self_hash_and_declares_all_native_evidence() -> (
    None
):
    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))

    assert contract["version"] == 2
    assert contract["manifest_path"] == "artifacts/coverage/quality-manifest.json"
    paths = [report["path"] for report in contract["coverage_reports"]]
    assert contract["manifest_path"] not in paths
    assert len(paths) == len(set(paths)) == 16
    assert "artifacts/coverage/python/coverage.json" in paths
    assert "frontend/coverage/coverage-final.json" in paths
    assert (
        sum(
            report["format"] == "llvm-cov-branch-json"
            for report in contract["coverage_reports"]
        )
        == 4
    )


def test_schema_v2_models_provenance_integrity_and_rust_branch_format() -> None:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))

    assert schema["properties"]["schema_version"]["const"] == 2
    assert "coverage_scope" in schema["required"]
    assert schema["properties"]["coverage_scope"]["$ref"] == "#/$defs/coverageScope"
    assert {"manifest_path", "tool_versions", "provenance", "generation"}.issubset(
        schema["required"]
    )
    assert (
        "llvm-cov-branch-json"
        in schema["$defs"]["report"]["properties"]["format"]["enum"]
    )
    assert "size_bytes" in schema["$defs"]["report"]["required"]
    assert schema["$defs"]["provenance"]["additionalProperties"] is False


def test_validator_cli_uses_explicit_schema_and_artifact_root(
    git_evidence_root: Path,
) -> None:
    validator = _load_validator()
    _, manifest, manifest_path = _valid_manifest_fixture(git_evidence_root)

    exit_code = validator.main(
        [
            "--contract",
            str(CONTRACT_PATH),
            "--manifest",
            str(manifest_path),
            "--schema",
            str(SCHEMA_PATH),
            "--artifact-root",
            str(git_evidence_root),
            "--expected-commit-sha",
            str(manifest["commit_sha"]),
        ]
    )

    assert exit_code == 0


def test_branch_reports_require_exact_nightly_rustc_tool_mapping(
    git_evidence_root: Path,
) -> None:
    validator = _load_validator()
    assert validator.REPORT_FORMAT_TO_TOOLS["llvm-cov-branch-json"] == frozenset(
        {"cargo-llvm-cov", "rustc-nightly"}
    )
    contract, manifest, manifest_path = _valid_manifest_fixture(git_evidence_root)
    del manifest["tool_versions"]["rustc-nightly"]

    errors = _validate(validator, manifest, contract, manifest_path, git_evidence_root)

    assert any("missing required tools: rustc-nightly" in error for error in errors)
