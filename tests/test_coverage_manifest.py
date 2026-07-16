from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
FIXTURES = REPOSITORY_ROOT / "tests" / "fixtures" / "quality"
NORMALIZER_PATH = (
    REPOSITORY_ROOT / "scripts" / "quality" / "normalize_coverage_reports.py"
)
QUALITY_CONTRACT_PATH = REPOSITORY_ROOT / "quality" / "quality-contract.json"
QUALITY_MANIFEST_SCHEMA_PATH = (
    REPOSITORY_ROOT / "quality" / "coverage-manifest.schema.json"
)
COMMIT_SHA = "a1b2c3d"
GENERATED_AT = "2026-07-17T00:00:00Z"


def _run_normalizer(
    output: Path,
    *arguments: str,
    cwd: Path | None = None,
    commit_sha: str = COMMIT_SHA,
    generated_at: str = GENERATED_AT,
) -> subprocess.CompletedProcess[str]:
    command = [
        sys.executable,
        str(NORMALIZER_PATH),
        "--commit-sha",
        commit_sha,
        "--generated-at",
        generated_at,
        "--output",
        str(output),
        *arguments,
    ]

    # The executable and normalizer path are test-controlled absolute paths.
    return subprocess.run(  # noqa: S603
        command,
        capture_output=True,
        check=False,
        cwd=cwd,
        encoding="utf-8",
        text=True,
    )


def _full_report_arguments() -> list[str]:
    go_profile = FIXTURES / "go-valid.coverprofile"
    rust_report = FIXTURES / "rust-valid.json"
    return [
        "--python-xml",
        str(FIXTURES / "python-valid.xml"),
        "--frontend-lcov",
        str(FIXTURES / "frontend-valid.lcov"),
        "--go-report",
        f"go-gateway={go_profile}",
        "--go-report",
        f"go-ws-hub={go_profile}",
        "--go-report",
        f"go-file-processor={go_profile}",
        "--rust-report",
        f"rust-native={rust_report}",
        "--rust-report",
        f"rust-pyo3-sanitizer={rust_report}",
        "--rust-report",
        f"rust-wasm-sanitizer={rust_report}",
    ]


def _metric(
    manifest: dict[str, object],
    component: str,
    metric: str,
) -> dict[str, object]:
    components = manifest["components"]
    assert isinstance(components, dict)
    component_entry = components[component]
    assert isinstance(component_entry, dict)
    metrics = component_entry["metrics"]
    assert isinstance(metrics, dict)
    metric_entry = metrics[metric]
    assert isinstance(metric_entry, dict)
    return metric_entry


def test_contract_declares_all_canonical_raw_coverage_artifacts() -> None:
    contract = json.loads(QUALITY_CONTRACT_PATH.read_text(encoding="utf-8"))

    assert {
        "coverage.xml",
        "artifacts/coverage/python/coverage.json",
        "frontend/coverage/lcov.info",
        "frontend/coverage/coverage-final.json",
        "artifacts/coverage/go/gateway/coverage.out",
        "artifacts/coverage/go/ws-hub/coverage.out",
        "artifacts/coverage/go/file-processor/coverage.out",
        "artifacts/coverage/rust/rust-native/llvm.json",
        "artifacts/coverage/rust/rust-pyo3-sanitizer/llvm.json",
        "artifacts/coverage/rust/rust-wasm-sanitizer/llvm.json",
        "artifacts/coverage/quality-manifest.json",
    }.issubset(contract["required_artifacts"])


def test_normalizes_native_reports_with_provenance_and_honest_metadata(
    tmp_path: Path,
) -> None:
    output = tmp_path / "quality-manifest.json"

    result = _run_normalizer(output, *_full_report_arguments(), cwd=tmp_path)

    assert result.returncode == 1
    assert all(line.startswith("ERROR:") for line in result.stderr.splitlines())
    manifest = json.loads(output.read_text(encoding="utf-8"))
    assert manifest["schema_version"] == 1
    assert manifest["commit_sha"] == COMMIT_SHA
    assert manifest["generated_at"] == GENERATED_AT
    assert manifest["source_roots"] == {
        "frontend": ["frontend/src"],
        "go-file-processor": ["services/file-processor"],
        "go-gateway": ["services/gateway"],
        "go-ws-hub": ["services/ws-hub"],
        "infrastructure": ["infra", "infrastructure", "k8s", "charts"],
        "python": ["app"],
        "rust-native": ["native/rust_ext"],
        "rust-pyo3-sanitizer": ["crates/pyo3-sanitizer"],
        "rust-wasm-sanitizer": ["frontend/wasm-sanitizer"],
        "scripts": [],
        "workflows": [],
    }

    python_lines = _metric(manifest, "python", "lines")
    assert python_lines == {
        "covered": 1,
        "percent": 50.0,
        "status": "native",
        "total": 2,
    }
    assert _metric(manifest, "python", "branches") == {
        "covered": 1,
        "percent": 50.0,
        "status": "native",
        "total": 2,
    }
    assert _metric(manifest, "python", "statements") == {
        "covered": None,
        "percent": None,
        "reason_code": "coverage_xml_has_no_statement_counter",
        "status": "unsupported",
        "total": None,
    }
    assert _metric(manifest, "python", "functions") == {
        "covered": None,
        "percent": None,
        "reason_code": "coverage_xml_has_no_function_counter",
        "status": "unsupported",
        "total": None,
    }

    assert _metric(manifest, "frontend", "lines") == {
        "covered": 2,
        "percent": 200 / 3,
        "status": "native",
        "total": 3,
    }
    assert _metric(manifest, "frontend", "branches") == {
        "covered": 2,
        "percent": 200 / 3,
        "status": "native",
        "total": 3,
    }
    assert _metric(manifest, "frontend", "functions") == {
        "covered": 2,
        "percent": 200 / 3,
        "status": "native",
        "total": 3,
    }
    assert _metric(manifest, "frontend", "statements")["status"] == "unsupported"

    go_statements = _metric(manifest, "go-gateway", "statements")
    assert go_statements == {
        "covered": 2,
        "percent": 40.0,
        "status": "native",
        "total": 5,
    }
    go_lines = _metric(manifest, "go-gateway", "lines")
    assert go_lines == {
        "covered": 1,
        "derivation": "unique source lines in coverprofile blocks; covered when any overlapping block has count greater than zero",
        "percent": 100 / 3,
        "status": "derived",
        "total": 3,
    }
    assert _metric(manifest, "go-gateway", "branches")["status"] == "unsupported"
    assert _metric(manifest, "go-gateway", "functions")["status"] == "unsupported"

    assert _metric(manifest, "rust-native", "lines") == {
        "covered": 3,
        "percent": 75.0,
        "status": "native",
        "total": 4,
    }
    assert _metric(manifest, "rust-native", "functions") == {
        "covered": 1,
        "percent": 50.0,
        "status": "native",
        "total": 2,
    }
    assert _metric(manifest, "rust-native", "branches") == {
        "covered": None,
        "percent": None,
        "reason_code": "llvm_branch_coverage_unstable",
        "status": "experimental",
        "total": None,
    }

    reports = manifest["reports"]
    assert isinstance(reports, list)
    python_report = next(
        report for report in reports if report["component"] == "python"
    )
    assert python_report == {
        "component": "python",
        "format": "cobertura-xml",
        "path": "tests/fixtures/quality/python-valid.xml",
        "sha256": hashlib.sha256(
            (FIXTURES / "python-valid.xml").read_bytes()
        ).hexdigest(),
    }
    assert manifest["components"]["python"]["status"] == "failed"
    assert manifest["components"]["infrastructure"]["status"] == "missing"
    assert manifest["validation"]["valid"] is False


def test_normalizer_output_is_byte_identical_for_fixed_inputs(tmp_path: Path) -> None:
    first_output = tmp_path / "first.json"
    second_output = tmp_path / "second.json"

    first = _run_normalizer(first_output, *_full_report_arguments())
    second = _run_normalizer(second_output, *_full_report_arguments())

    assert first.returncode == second.returncode == 1
    assert first_output.read_bytes() == second_output.read_bytes()


def test_rust_direct_totals_form_is_normalized(tmp_path: Path) -> None:
    output = tmp_path / "quality-manifest.json"

    result = _run_normalizer(
        output,
        "--rust-report",
        f"rust-native={FIXTURES / 'rust-direct-valid.json'}",
    )

    assert result.returncode == 1
    manifest = json.loads(output.read_text(encoding="utf-8"))
    assert _metric(manifest, "rust-native", "lines")["percent"] == 75.0
    assert _metric(manifest, "rust-native", "functions")["percent"] == 50.0


@pytest.mark.parametrize(
    ("argument", "value"),
    [
        ("--python-xml", str(FIXTURES / "python-malformed.xml")),
        ("--python-xml", str(FIXTURES / "python-doctype.xml")),
        ("--frontend-lcov", str(FIXTURES / "frontend-malformed.lcov")),
        ("--go-report", f"go-gateway={FIXTURES / 'go-malformed.coverprofile'}"),
        ("--rust-report", f"rust-native={FIXTURES / 'rust-malformed.json'}"),
    ],
)
def test_malformed_native_report_returns_two_without_traceback(
    tmp_path: Path,
    argument: str,
    value: str,
) -> None:
    result = _run_normalizer(tmp_path / "quality-manifest.json", argument, value)

    assert result.returncode == 2
    assert "Traceback" not in result.stderr
    assert result.stderr.startswith("ERROR:")


def test_missing_expected_report_writes_failed_manifest(tmp_path: Path) -> None:
    output = tmp_path / "quality-manifest.json"

    result = _run_normalizer(
        output,
        "--python-xml",
        str(FIXTURES / "python-valid.xml"),
    )

    assert result.returncode == 1
    manifest = json.loads(output.read_text(encoding="utf-8"))
    assert manifest["components"]["go-gateway"]["status"] == "missing"
    assert any(
        entry["component"] == "go-gateway"
        and entry["path"] == "artifacts/coverage/go/gateway/coverage.out"
        for entry in manifest["missing_reports"]
    )
    missing_paths = {
        entry["path"] for entry in manifest["missing_reports"] if "path" in entry
    }
    assert "frontend/coverage/coverage-final.json" not in missing_paths
    assert "artifacts/coverage/quality-manifest.json" not in missing_paths
    assert manifest["validation"]["valid"] is False


def test_unavailable_metrics_never_become_perfect_coverage(tmp_path: Path) -> None:
    output = tmp_path / "quality-manifest.json"

    result = _run_normalizer(
        output,
        "--python-xml",
        str(FIXTURES / "python-valid.xml"),
    )

    assert result.returncode == 1
    manifest = json.loads(output.read_text(encoding="utf-8"))
    for metric_name in ("statements", "functions"):
        metric = _metric(manifest, "python", metric_name)
        assert metric["covered"] is None
        assert metric["total"] is None
        assert metric["percent"] is None
        assert metric["percent"] != 100


def test_below_threshold_native_measurement_is_a_quality_failure(
    tmp_path: Path,
) -> None:
    output = tmp_path / "quality-manifest.json"

    result = _run_normalizer(
        output,
        "--python-xml",
        str(FIXTURES / "python-valid.xml"),
    )

    assert result.returncode == 1
    manifest = json.loads(output.read_text(encoding="utf-8"))
    validation = manifest["validation"]
    assert isinstance(validation, dict)
    assert "python.lines is below required coverage floor 99" in validation["errors"]


def test_derived_go_line_metric_cannot_satisfy_the_strict_v1_floor(
    tmp_path: Path,
) -> None:
    output = tmp_path / "quality-manifest.json"

    result = _run_normalizer(
        output,
        "--go-report",
        f"go-gateway={FIXTURES / 'go-valid.coverprofile'}",
    )

    assert result.returncode == 1
    manifest = json.loads(output.read_text(encoding="utf-8"))
    assert (
        "go-gateway.lines is derived and cannot satisfy strict coverage floor"
        in manifest["validation"]["errors"]
    )


def test_duplicate_component_input_is_an_honest_evidence_failure(
    tmp_path: Path,
) -> None:
    output = tmp_path / "quality-manifest.json"
    profile = FIXTURES / "go-valid.coverprofile"

    result = _run_normalizer(
        output,
        "--go-report",
        f"go-gateway={profile}",
        "--go-report",
        f"go-gateway={profile}",
    )

    assert result.returncode == 1
    manifest = json.loads(output.read_text(encoding="utf-8"))
    assert (
        "duplicate report input for component go-gateway"
        in manifest["validation"]["errors"]
    )


def test_invalid_component_and_malformed_arguments_return_two(tmp_path: Path) -> None:
    invalid_component = _run_normalizer(
        tmp_path / "component.json",
        "--go-report",
        f"python={FIXTURES / 'go-valid.coverprofile'}",
    )
    bad_sha = _run_normalizer(
        tmp_path / "sha.json",
        "--commit-sha",
        "not-a-sha",
    )
    bad_timestamp = _run_normalizer(
        tmp_path / "timestamp.json",
        "--generated-at",
        "2026-07-17T00:00:00+03:00",
    )

    for result in (invalid_component, bad_sha, bad_timestamp):
        assert result.returncode == 2
        assert "Traceback" not in result.stderr
        assert result.stderr.startswith("ERROR:")


def test_unreadable_report_and_malformed_contract_return_two(tmp_path: Path) -> None:
    malformed_contract = tmp_path / "bad-contract.json"
    malformed_contract.write_text("{not valid JSON", encoding="utf-8")

    missing_report = _run_normalizer(
        tmp_path / "missing-report.json",
        "--python-xml",
        str(tmp_path / "does-not-exist.xml"),
    )
    invalid_contract = _run_normalizer(
        tmp_path / "invalid-contract.json",
        "--contract",
        str(malformed_contract),
    )

    for result in (missing_report, invalid_contract):
        assert result.returncode == 2
        assert "Traceback" not in result.stderr
        assert result.stderr.startswith("ERROR:")


def test_coverage_manifest_schema_is_closed_and_versioned() -> None:
    schema = json.loads(QUALITY_MANIFEST_SCHEMA_PATH.read_text(encoding="utf-8"))

    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert schema["properties"]["schema_version"]["const"] == 1
    assert schema["additionalProperties"] is False
    assert schema["$defs"]["metric"]["additionalProperties"] is False


def test_relative_report_path_is_resolved_from_repository_root(tmp_path: Path) -> None:
    output = tmp_path / "quality-manifest.json"

    result = _run_normalizer(
        output,
        "--python-xml",
        "tests/fixtures/quality/python-valid.xml",
        cwd=tmp_path,
    )

    assert result.returncode == 1
    manifest = json.loads(output.read_text(encoding="utf-8"))
    report = next(
        entry for entry in manifest["reports"] if entry["component"] == "python"
    )
    assert report["path"] == "tests/fixtures/quality/python-valid.xml"


def test_output_cannot_alias_an_input_or_the_contract(tmp_path: Path) -> None:
    input_path = FIXTURES / "python-valid.xml"
    contract_bytes = QUALITY_CONTRACT_PATH.read_bytes()
    input_bytes = input_path.read_bytes()

    input_alias = _run_normalizer(
        input_path,
        "--python-xml",
        str(input_path),
    )
    contract_alias = _run_normalizer(QUALITY_CONTRACT_PATH)

    for result in (input_alias, contract_alias):
        assert result.returncode == 2
        assert "Traceback" not in result.stderr
        assert result.stderr.startswith("ERROR:")
    assert input_path.read_bytes() == input_bytes
    assert QUALITY_CONTRACT_PATH.read_bytes() == contract_bytes


def test_contract_expiry_uses_the_caller_supplied_generated_at_date(
    tmp_path: Path,
) -> None:
    contract = json.loads(QUALITY_CONTRACT_PATH.read_text(encoding="utf-8"))
    contract["exclusions"] = [
        {
            "created_on": "2026-07-01",
            "evidence": "quality test fixture",
            "expires_on": "2026-07-20",
            "id": "quality-test-expiry",
            "issue": "QUALITY-1",
            "owner": "quality",
            "path": "app/example.py",
            "reason": "deterministic contract-date test",
        }
    ]
    contract_path = tmp_path / "contract.json"
    contract_path.write_text(json.dumps(contract), encoding="utf-8")

    before_expiry = _run_normalizer(
        tmp_path / "before-expiry.json",
        "--contract",
        str(contract_path),
        generated_at="2026-07-17T00:00:00Z",
    )
    after_expiry = _run_normalizer(
        tmp_path / "after-expiry.json",
        "--contract",
        str(contract_path),
        generated_at="2026-07-21T00:00:00Z",
    )

    assert before_expiry.returncode == 1
    assert after_expiry.returncode == 2
    assert "expires_on must be after validation day" in after_expiry.stderr
