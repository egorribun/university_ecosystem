from __future__ import annotations

import hashlib
import json
import os
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
from tests.symlink_support import DIRECTORY_SYMLINKS_SUPPORTED

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
NORMALIZER_PATH = (
    REPOSITORY_ROOT / "scripts" / "quality" / "normalize_coverage_reports.py"
)
CONTRACT_PATH = REPOSITORY_ROOT / "quality" / "quality-contract.json"
SCHEMA_PATH = REPOSITORY_ROOT / "quality" / "coverage-manifest.schema.json"
SOURCE_POLICY_PATH = REPOSITORY_ROOT / "quality" / "coverage-source-policy.json"
GIT_EXECUTABLE = shutil.which("git")


@pytest.fixture
def evidence_repo(tmp_path: Path) -> Path:
    assert GIT_EXECUTABLE is not None
    subprocess.run(  # noqa: S603
        [GIT_EXECUTABLE, "init", "-q"], cwd=tmp_path, check=True
    )
    contract_target = tmp_path / "quality" / "quality-contract.json"
    contract_target.parent.mkdir(parents=True, exist_ok=True)
    contract_target.write_bytes(CONTRACT_PATH.read_bytes())
    (tmp_path / "quality" / "coverage-manifest.schema.json").write_bytes(
        SCHEMA_PATH.read_bytes()
    )
    (tmp_path / "quality" / "ownership-mapping.json").write_text(
        json.dumps({"tier0_rules": ["**/spicedb/**", "alembic/versions/**"]}),
        encoding="utf-8",
    )
    (tmp_path / "quality" / "coverage-source-policy.json").write_bytes(
        SOURCE_POLICY_PATH.read_bytes()
    )
    write_complete_evidence(tmp_path)
    _commit_all(tmp_path, "fixture")
    return tmp_path


def _commit_all(root: Path, message: str) -> None:
    assert GIT_EXECUTABLE is not None
    subprocess.run(  # noqa: S603
        [GIT_EXECUTABLE, "add", "--all"], cwd=root, check=True
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
            message,
        ],
        cwd=root,
        check=True,
    )


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
    assert manifest["schema_version"] == 3
    assert manifest["commit_sha"] == _head(evidence_repo)
    assert manifest["tested_commit_sha"] == _head(evidence_repo)
    assert manifest["source_head_sha"] == _head(evidence_repo)
    assert manifest["base_sha"] == _head(evidence_repo)
    assert manifest["base_ref"] == "local"
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


def test_normalizer_v2_rejects_coverage_scope_outside_source_roots(
    evidence_repo: Path,
) -> None:
    contract_path = evidence_repo / "quality/quality-contract.json"
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    contract["coverage_scope"]["python"] = ["services/gateway"]
    contract_path.write_text(json.dumps(contract), encoding="utf-8")

    result = _run(evidence_repo, _full_arguments(evidence_repo))

    assert result.returncode == 2
    assert "coverage_scope.python[0]" in result.stderr
    assert not (evidence_repo / "artifacts/coverage/quality-manifest.json").exists()


@pytest.mark.parametrize(
    "fault",
    [
        "missing",
        "empty",
        pytest.param(
            "symlink",
            marks=pytest.mark.skipif(
                not DIRECTORY_SYMLINKS_SUPPORTED,
                reason="symlink creation is unavailable on this platform",
            ),
        ),
    ],
)
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
        report.symlink_to(target)

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
    _commit_all(evidence_repo, "add tracked Rust source")
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


def test_normalizer_v2_preserves_alembic_source_identity_and_inventory(
    evidence_repo: Path,
) -> None:
    alembic_path = "alembic/versions/20260825_example.py"
    source = evidence_repo / alembic_path
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("revision = '20260825'\n", encoding="utf-8")
    _commit_all(evidence_repo, "add alembic migration")

    xml_path = evidence_repo / "coverage.xml"
    xml_path.write_text(
        f"""<?xml version="1.0" ?>
<coverage branches-covered="2" branches-valid="2" lines-covered="2" lines-valid="2" version="7.10">
  <packages><package name="python"><classes>
    <class filename="app/example.py" name="example"><methods /><lines><line branch="true" condition-coverage="100% (1/1)" hits="1" number="1" /></lines></class>
    <class filename="{alembic_path}" name="migration"><methods /><lines><line branch="true" condition-coverage="100% (1/1)" hits="1" number="1" /></lines></class>
  </classes></package></packages>
</coverage>
""",
        encoding="utf-8",
    )
    json_path = evidence_repo / "artifacts/coverage/python/coverage.json"
    report = json.loads(json_path.read_text(encoding="utf-8"))
    report["files"][alembic_path] = json.loads(
        json.dumps(report["files"]["app/example.py"])
    )
    report["totals"] = {
        "covered_lines": 2,
        "num_statements": 2,
        "covered_branches": 2,
        "num_branches": 2,
    }
    json_path.write_text(json.dumps(report), encoding="utf-8")

    result = _run(evidence_repo, _full_arguments(evidence_repo))

    assert result.returncode == 0, result.stderr
    manifest = json.loads(
        (evidence_repo / "artifacts/coverage/quality-manifest.json").read_text(
            encoding="utf-8"
        )
    )
    # Alembic revisions remain canonical report identities but are outside the
    # pytest-cov producer scope (``--cov=app``).  They are validated by the
    # dedicated PostgreSQL migration gate rather than fabricated as Tier0
    # Python coverage evidence.
    assert manifest["coverage_scope"]["python"] == ["app"]
    assert not any(item["path"] == alembic_path for item in manifest["tier0"]["files"])


def test_normalizer_v2_does_not_require_alembic_outside_python_coverage_scope(
    evidence_repo: Path,
) -> None:
    """Python coverage completeness follows coverage_scope, not source_roots."""
    alembic_path = "alembic/versions/20260825_unmeasured.py"
    source = evidence_repo / alembic_path
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("revision = '20260825_unmeasured'\n", encoding="utf-8")
    _commit_all(evidence_repo, "add migration outside pytest coverage scope")

    # The canonical pytest-cov producer runs with ``--cov=app`` and therefore
    # intentionally omits Alembic revisions.  A new migration must not create
    # a false missing-source failure in the aggregate coverage manifest.
    result = _run(evidence_repo, _full_arguments(evidence_repo))

    assert result.returncode == 0, result.stderr
    manifest = json.loads(
        (evidence_repo / "artifacts/coverage/quality-manifest.json").read_text(
            encoding="utf-8"
        )
    )
    assert manifest["validation"] == {"valid": True, "errors": []}


@pytest.mark.parametrize("mutation", ["modified", "deleted", "untracked"])
def test_normalizer_v2_rejects_dirty_authored_source_snapshot(
    evidence_repo: Path,
    mutation: str,
) -> None:
    source = evidence_repo / "app/example.py"
    if mutation == "modified":
        source.write_text("value = 2\n", encoding="utf-8")
    elif mutation == "deleted":
        source.unlink()
    else:
        (evidence_repo / "app/untracked.py").write_text("value = 2\n", encoding="utf-8")

    result = _run(evidence_repo, _full_arguments(evidence_repo))

    assert result.returncode == 2
    assert "clean tracked HEAD snapshot" in result.stderr
    assert not (evidence_repo / "artifacts/coverage/quality-manifest.json").exists()


def test_normalizer_v2_allows_generated_raw_coverage_artifact_changes(
    evidence_repo: Path,
) -> None:
    report_path = evidence_repo / "artifacts/coverage/python/coverage.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    result = _run(evidence_repo, _full_arguments(evidence_repo))

    assert result.returncode == 0, result.stderr


@pytest.mark.skipif(
    not DIRECTORY_SYMLINKS_SUPPORTED,
    reason="directory symlink creation is unavailable",
)
def test_normalizer_v2_rejects_output_parent_symlink_before_writing(
    evidence_repo: Path,
) -> None:
    contract_path = evidence_repo / "quality/quality-contract.json"
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    contract["manifest_path"] = "artifacts/manifests/quality-manifest.json"
    contract_path.write_text(json.dumps(contract), encoding="utf-8")
    _commit_all(evidence_repo, "move manifest path")

    outside = evidence_repo.parent / f"{evidence_repo.name}-outside"
    outside.mkdir()
    output_parent = evidence_repo / "artifacts/manifests"
    output_parent.symlink_to(outside, target_is_directory=True)

    arguments = _full_arguments(evidence_repo)
    arguments[arguments.index("--output") + 1] = str(
        output_parent / "quality-manifest.json"
    )
    result = _run(evidence_repo, arguments)

    assert result.returncode == 2
    assert "symlink or junction" in result.stderr
    assert not (outside / "quality-manifest.json").exists()


def test_normalizer_v2_rejects_reports_omitting_tracked_non_tier0_source(
    evidence_repo: Path,
) -> None:
    source = evidence_repo / "app/secondary.py"
    source.write_text("secondary = 1\n", encoding="utf-8")
    _commit_all(evidence_repo, "add authored source")

    result = _run(evidence_repo, _full_arguments(evidence_repo))

    assert result.returncode == 2
    assert "python coverage is missing tracked source app/secondary.py" in result.stderr


def test_normalizer_v2_frontend_inventory_matches_vitest_production_scope(
    evidence_repo: Path,
) -> None:
    excluded_sources = {
        "frontend/src/tests/helper.ts": "export const helper = 1\n",
        "frontend/src/example.test.ts": "export const tested = 1\n",
        "frontend/src/example.stories.tsx": "export const Story = () => null\n",
        "frontend/src/setupTests.ts": "export {}\n",
        "frontend/src/routeTree.gen.ts": "export {}\n",
        "frontend/src/api/generated/client.ts": "export const generated = 1\n",
        "frontend/src/types.d.ts": "export type Value = number\n",
        "frontend/src/test/setup.ts": "export {}\n",
        "frontend/src/nested/__tests__/helper.ts": "export const helper = 1\n",
    }
    for relative_path, contents in excluded_sources.items():
        source = evidence_repo / relative_path
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text(contents, encoding="utf-8")
    _commit_all(evidence_repo, "add non-production frontend sources")

    result = _run(evidence_repo, _full_arguments(evidence_repo))

    assert result.returncode == 0, result.stderr


def test_normalizer_v2_tier0_inventory_uses_tracked_sources_only(
    evidence_repo: Path,
) -> None:
    """Ignored Rust build output must not become a Tier0 source obligation."""
    ownership = evidence_repo / "quality/ownership-mapping.json"
    ownership.write_text(
        json.dumps({"tier0_rules": ["native/rust_ext/**"]}), encoding="utf-8"
    )
    _commit_all(evidence_repo, "cover Rust production sources as Tier0")

    exclude = evidence_repo / ".git" / "info" / "exclude"
    exclude.write_text(
        exclude.read_text(encoding="utf-8") + "\nnative/rust_ext/target/\n",
        encoding="utf-8",
    )
    generated = evidence_repo / "native/rust_ext/target/release/generated.rs"
    generated.parent.mkdir(parents=True, exist_ok=True)
    generated.write_text("pub fn generated() {}\n", encoding="utf-8")

    result = _run(evidence_repo, _full_arguments(evidence_repo))

    assert result.returncode == 0, result.stderr
    manifest = json.loads(
        (evidence_repo / "artifacts/coverage/quality-manifest.json").read_text(
            encoding="utf-8"
        )
    )
    tier0_paths = {
        item["path"] for item in manifest["tier0"]["files"] if isinstance(item, dict)
    }
    assert "native/rust_ext/src/lib.rs" in tier0_paths
    assert not any(path.startswith("native/rust_ext/target/") for path in tier0_paths)


def test_normalizer_v2_reads_frontend_inventory_from_shared_source_policy(
    evidence_repo: Path,
) -> None:
    policy = evidence_repo / "quality/coverage-source-policy.json"
    policy.write_text(
        json.dumps(
            {
                "frontend": {
                    "include": ["src/**/*.{ts,tsx}"],
                    "exclude": [
                        "src/tests/**/*",
                        "src/**/__tests__/**/*",
                        "src/**/*.test.{ts,tsx}",
                        "src/setupTests.ts",
                        "src/routeTree.gen.ts",
                        "src/api/generated/**/*",
                        "**/*.d.ts",
                        "src/test/**/*",
                    ],
                }
            }
        ),
        encoding="utf-8",
    )
    story = evidence_repo / "frontend/src/example.stories.tsx"
    story.write_text("export const Story = () => null\n", encoding="utf-8")
    _commit_all(evidence_repo, "make stories coverable in shared source policy")

    result = _run(evidence_repo, _full_arguments(evidence_repo))

    assert result.returncode == 2
    assert (
        "frontend coverage is missing tracked source frontend/src/example.stories.tsx"
        in result.stderr
    )


def test_normalizer_v2_rejects_frontend_report_omitting_authored_production_source(
    evidence_repo: Path,
) -> None:
    source = evidence_repo / "frontend/src/secondary.tsx"
    source.write_text("export const Secondary = () => null\n", encoding="utf-8")
    _commit_all(evidence_repo, "add authored frontend source")

    result = _run(evidence_repo, _full_arguments(evidence_repo))

    assert result.returncode == 2
    assert (
        "frontend coverage is missing tracked source frontend/src/secondary.tsx"
        in result.stderr
    )


@pytest.mark.skipif(os.name != "nt", reason="Windows report paths are case-insensitive")
def test_normalizer_v2_matches_frontend_report_case_to_tracked_identity(
    evidence_repo: Path,
) -> None:
    tracked_source = evidence_repo / "frontend/src/example.ts"
    mixed_case_source = evidence_repo / "frontend/src/App.tsx"
    tracked_source.rename(mixed_case_source)
    _commit_all(evidence_repo, "track mixed-case frontend source")

    lcov_path = evidence_repo / "frontend/coverage/lcov.info"
    lcov_path.write_text(
        lcov_path.read_text(encoding="utf-8").replace(
            "frontend/src/example.ts", "frontend/src/app.tsx"
        ),
        encoding="utf-8",
    )
    json_path = evidence_repo / "frontend/coverage/coverage-final.json"
    report = json.loads(json_path.read_text(encoding="utf-8"))
    record = report.pop("frontend/src/example.ts")
    record["path"] = "frontend/src/app.tsx"
    report["frontend/src/app.tsx"] = record
    json_path.write_text(json.dumps(report), encoding="utf-8")

    result = _run(evidence_repo, _full_arguments(evidence_repo))

    assert result.returncode == 0, result.stderr


@pytest.mark.skipif(os.name == "nt", reason="requires a case-sensitive checkout")
def test_normalizer_v2_keeps_case_distinct_frontend_sources_on_linux(
    evidence_repo: Path,
) -> None:
    source = evidence_repo / "frontend/src/EXAMPLE.ts"
    source.write_text("export const upper = 1\n", encoding="utf-8")
    _commit_all(evidence_repo, "add case-distinct frontend source")

    result = _run(evidence_repo, _full_arguments(evidence_repo))

    assert result.returncode == 2
    assert (
        "frontend coverage is missing tracked source frontend/src/EXAMPLE.ts"
        in result.stderr
    )


@pytest.mark.parametrize(
    "relative_path",
    [
        "tests/test_coverage_gate.py",
        "frontend/package-lock.json",
        "frontend/playwright.config.ts",
        "pyproject.toml",
        "go.work",
        "Makefile",
    ],
)
def test_normalizer_v2_rejects_dirty_coverage_control_inputs(
    evidence_repo: Path,
    relative_path: str,
) -> None:
    control = evidence_repo / relative_path
    control.parent.mkdir(parents=True, exist_ok=True)
    control.write_text("committed\n", encoding="utf-8")
    _commit_all(evidence_repo, f"add coverage control {relative_path}")
    control.write_text("dirty\n", encoding="utf-8")

    result = _run(evidence_repo, _full_arguments(evidence_repo))

    assert result.returncode == 2
    assert "clean tracked HEAD snapshot" in result.stderr
    assert relative_path in result.stderr


def test_normalizer_v2_allows_untracked_superpowers_documents(
    evidence_repo: Path,
) -> None:
    document = evidence_repo / "docs/superpowers/notes.md"
    document.parent.mkdir(parents=True, exist_ok=True)
    document.write_text("user plan\n", encoding="utf-8")

    result = _run(evidence_repo, _full_arguments(evidence_repo))

    assert result.returncode == 0, result.stderr


def test_normalizer_v2_zero_unit_tier0_derivation_validates_end_to_end(
    evidence_repo: Path,
) -> None:
    migration_path = "alembic/versions/20260825_empty.py"
    migration = evidence_repo / migration_path
    migration.parent.mkdir(parents=True, exist_ok=True)
    migration.write_text("revision = '20260825'\n", encoding="utf-8")
    ownership = evidence_repo / "quality/ownership-mapping.json"
    ownership.write_text(
        json.dumps({"tier0_rules": ["**/spicedb/**", "alembic/versions/**"]}),
        encoding="utf-8",
    )
    _commit_all(evidence_repo, "add zero-unit Tier0 source")

    xml_path = evidence_repo / "coverage.xml"
    xml = xml_path.read_text(encoding="utf-8")
    xml_path.write_text(
        xml.replace(
            "</classes>",
            f'<class filename="{migration_path}" name="migration"><methods />'
            '<lines><line hits="1" number="1" /></lines></class></classes>',
        ).replace(
            'lines-covered="1" lines-valid="1"', 'lines-covered="2" lines-valid="2"'
        ),
        encoding="utf-8",
    )
    json_path = evidence_repo / "artifacts/coverage/python/coverage.json"
    report = json.loads(json_path.read_text(encoding="utf-8"))
    report["files"][migration_path] = {
        "executed_lines": [1],
        "missing_lines": [],
        "executed_branches": [],
        "missing_branches": [],
        "summary": {
            "covered_lines": 1,
            "num_statements": 1,
            "covered_branches": 0,
            "num_branches": 0,
        },
    }
    report["totals"] = {
        "covered_lines": 2,
        "num_statements": 2,
        "covered_branches": 1,
        "num_branches": 1,
    }
    json_path.write_text(json.dumps(report), encoding="utf-8")

    result = _run(evidence_repo, _full_arguments(evidence_repo))

    assert result.returncode == 0, result.stderr
    manifest = json.loads(
        (evidence_repo / "artifacts/coverage/quality-manifest.json").read_text(
            encoding="utf-8"
        )
    )
    tier0_paths = {item["path"] for item in manifest["tier0"]["files"]}
    assert "services/pkg/spicedb/client.go" in tier0_paths
    assert migration_path not in tier0_paths
    assert manifest["validation"] == {"valid": True, "errors": []}
