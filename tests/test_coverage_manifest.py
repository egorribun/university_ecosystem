from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, ValidationError

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


def _assert_metric_schema_shape(metric: dict[str, object]) -> None:
    assert set(metric) >= {"status", "covered", "total", "percent"}
    status = metric["status"]
    if status in {"native", "derived"}:
        assert isinstance(metric["covered"], int)
        assert isinstance(metric["total"], int)
        assert isinstance(metric["percent"], float | int)
        if status == "derived":
            assert isinstance(metric["derivation"], str)
        return

    assert status in {"experimental", "unsupported", "missing"}
    assert metric["covered"] is None
    assert metric["total"] is None
    assert metric["percent"] is None
    if status in {"experimental", "unsupported"}:
        assert isinstance(metric["reason_code"], str)


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
        "scripts": ["scripts"],
        "workflows": [".github/workflows"],
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
        "percent": 66.666667,
        "status": "native",
        "total": 3,
    }
    assert _metric(manifest, "frontend", "branches") == {
        "covered": 2,
        "percent": 66.666667,
        "status": "native",
        "total": 3,
    }
    assert _metric(manifest, "frontend", "functions") == {
        "covered": 2,
        "percent": 66.666667,
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
        "percent": 33.333333,
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
    ("component", "argument", "value"),
    [
        ("python", "--python-xml", str(FIXTURES / "python-malformed.xml")),
        ("python", "--python-xml", str(FIXTURES / "python-doctype.xml")),
        ("python", "--python-xml", str(FIXTURES / "python-duplicate-line.xml")),
        (
            "python",
            "--python-xml",
            str(FIXTURES / "python-impossible-condition.xml"),
        ),
        (
            "python",
            "--python-xml",
            str(FIXTURES / "python-conflicting-root.xml"),
        ),
        ("frontend", "--frontend-lcov", str(FIXTURES / "frontend-malformed.lcov")),
        (
            "frontend",
            "--frontend-lcov",
            str(FIXTURES / "frontend-summary-only.lcov"),
        ),
        (
            "frontend",
            "--frontend-lcov",
            str(FIXTURES / "frontend-conflicting-summary.lcov"),
        ),
        (
            "frontend",
            "--frontend-lcov",
            str(FIXTURES / "frontend-conflicting-branch-summary.lcov"),
        ),
        (
            "frontend",
            "--frontend-lcov",
            str(FIXTURES / "frontend-conflicting-function-summary.lcov"),
        ),
        (
            "frontend",
            "--frontend-lcov",
            str(FIXTURES / "frontend-duplicate-source.lcov"),
        ),
        (
            "frontend",
            "--frontend-lcov",
            str(FIXTURES / "frontend-duplicate-da.lcov"),
        ),
        (
            "frontend",
            "--frontend-lcov",
            str(FIXTURES / "frontend-duplicate-brda.lcov"),
        ),
        (
            "frontend",
            "--frontend-lcov",
            str(FIXTURES / "frontend-duplicate-fn.lcov"),
        ),
        (
            "frontend",
            "--frontend-lcov",
            str(FIXTURES / "frontend-duplicate-fnda.lcov"),
        ),
        (
            "frontend",
            "--frontend-lcov",
            str(FIXTURES / "frontend-malformed-detail.lcov"),
        ),
        (
            "go-gateway",
            "--go-report",
            f"go-gateway={FIXTURES / 'go-malformed.coverprofile'}",
        ),
        (
            "go-gateway",
            "--go-report",
            f"go-gateway={FIXTURES / 'go-duplicate-block.coverprofile'}",
        ),
        (
            "rust-native",
            "--rust-report",
            f"rust-native={FIXTURES / 'rust-malformed.json'}",
        ),
        (
            "rust-native",
            "--rust-report",
            f"rust-native={FIXTURES / 'rust-multiple-data.json'}",
        ),
    ],
)
def test_malformed_native_report_returns_two_without_traceback(
    tmp_path: Path,
    component: str,
    argument: str,
    value: str,
) -> None:
    output = tmp_path / "quality-manifest.json"
    result = _run_normalizer(output, argument, value)

    assert result.returncode == 2
    assert "Traceback" not in result.stderr
    assert result.stderr.startswith("ERROR:")
    assert output.is_file()
    manifest = json.loads(output.read_text(encoding="utf-8"))
    assert manifest["validation"]["valid"] is False
    assert manifest["validation"]["errors"]
    assert manifest["components"][component]["status"] == "failed"
    assert manifest["components"][component]["errors"]
    assert any(report["component"] == component for report in manifest["reports"])
    for metric in manifest["components"][component]["metrics"].values():
        assert isinstance(metric, dict)
        _assert_metric_schema_shape(metric)


def test_python_same_line_in_distinct_source_files_is_not_a_duplicate(
    tmp_path: Path,
) -> None:
    output = tmp_path / "quality-manifest.json"

    result = _run_normalizer(
        output,
        "--python-xml",
        str(FIXTURES / "python-same-line-different-sources.xml"),
    )

    assert result.returncode == 1
    manifest = json.loads(output.read_text(encoding="utf-8"))
    assert manifest["components"]["python"]["status"] == "failed"
    assert all(
        "duplicate coverage XML source line" not in error
        for error in manifest["validation"]["errors"]
    )


def test_percent_display_rounds_half_up_to_six_decimal_places(tmp_path: Path) -> None:
    output = tmp_path / "quality-manifest.json"

    result = _run_normalizer(
        output,
        "--go-report",
        f"go-gateway={FIXTURES / 'go-rounding.coverprofile'}",
    )

    assert result.returncode == 1
    manifest = json.loads(output.read_text(encoding="utf-8"))
    assert _metric(manifest, "go-gateway", "statements")["percent"] == 0.000001


def test_lcov_branch_expression_may_contain_commas(tmp_path: Path) -> None:
    output = tmp_path / "quality-manifest.json"

    result = _run_normalizer(
        output,
        "--frontend-lcov",
        str(FIXTURES / "frontend-branch-expression.lcov"),
    )

    assert result.returncode == 1
    manifest = json.loads(output.read_text(encoding="utf-8"))
    assert _metric(manifest, "frontend", "branches") == {
        "covered": 1,
        "percent": 100.0,
        "status": "native",
        "total": 1,
    }


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


def test_unreadable_report_replaces_writable_output_with_failed_manifest(
    tmp_path: Path,
) -> None:
    output = tmp_path / "quality-manifest.json"
    stale_output = b'{"stale": true}\n'
    output.write_bytes(stale_output)

    result = _run_normalizer(
        output,
        "--python-xml",
        str(tmp_path / "does-not-exist.xml"),
    )

    assert result.returncode == 2
    assert "Traceback" not in result.stderr
    assert all(line.startswith("ERROR:") for line in result.stderr.splitlines())
    assert output.read_bytes() != stale_output
    manifest = json.loads(output.read_text(encoding="utf-8"))
    schema = json.loads(QUALITY_MANIFEST_SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator(schema).validate(manifest)
    assert manifest["validation"]["valid"] is False
    assert any(
        "unable to read report" in error for error in manifest["validation"]["errors"]
    )
    assert manifest["components"]["python"]["status"] == "failed"
    assert manifest["reports"] == []
    for metric in manifest["components"]["python"]["metrics"].values():
        assert isinstance(metric, dict)
        _assert_metric_schema_shape(metric)


@pytest.mark.parametrize(
    (
        "case_name",
        "expected_returncode",
        "expected_component",
        "expected_status",
        "expected_report_count",
        "materializes_manifest",
    ),
    [
        ("unreadable", 2, "python", "failed", 0, True),
        ("readable-malformed", 2, "python", "failed", 1, True),
        ("mixed-unreadable-readable", 2, "python", "failed", 1, True),
        ("invalid-contract", 2, None, None, 0, False),
        ("invalid-arguments", 2, None, None, 0, False),
        ("output-alias", 2, None, None, 0, False),
        ("missing-evidence", 1, "python", "missing", 0, True),
        ("duplicate-component", 1, "go-gateway", "failed", 2, True),
    ],
)
def test_coverage_evidence_lifecycle_is_fail_closed(
    tmp_path: Path,
    case_name: str,
    expected_returncode: int,
    expected_component: str | None,
    expected_status: str | None,
    expected_report_count: int,
    materializes_manifest: bool,
) -> None:
    output = tmp_path / "quality-manifest.json"
    stale_output = b'{"stale": true}\n'
    output.write_bytes(stale_output)
    arguments: list[str] = []

    if case_name == "unreadable":
        arguments = ["--python-xml", str(tmp_path / "does-not-exist.xml")]
    elif case_name == "readable-malformed":
        arguments = ["--python-xml", str(FIXTURES / "python-malformed.xml")]
    elif case_name == "mixed-unreadable-readable":
        arguments = [
            "--python-xml",
            str(tmp_path / "does-not-exist.xml"),
            "--frontend-lcov",
            str(FIXTURES / "frontend-valid.lcov"),
        ]
    elif case_name == "invalid-contract":
        contract = tmp_path / "bad-contract.json"
        contract.write_text("{not valid JSON", encoding="utf-8")
        arguments = ["--contract", str(contract)]
    elif case_name == "invalid-arguments":
        arguments = []
    elif case_name == "output-alias":
        output = FIXTURES / "python-valid.xml"
        stale_output = output.read_bytes()
        arguments = ["--python-xml", str(output)]
    elif case_name == "duplicate-component":
        profile = FIXTURES / "go-valid.coverprofile"
        arguments = [
            "--go-report",
            f"go-gateway={profile}",
            "--go-report",
            f"go-gateway={profile}",
        ]

    result = _run_normalizer(
        output,
        *arguments,
        commit_sha="invalid-sha" if case_name == "invalid-arguments" else COMMIT_SHA,
    )

    assert result.returncode == expected_returncode
    assert "Traceback" not in result.stderr
    assert all(line.startswith("ERROR:") for line in result.stderr.splitlines())
    if not materializes_manifest:
        assert output.read_bytes() == stale_output
        return

    assert output.read_bytes() != stale_output
    assert not list(output.parent.glob(f".{output.name}.*.tmp"))
    manifest = json.loads(output.read_text(encoding="utf-8"))
    schema = json.loads(QUALITY_MANIFEST_SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator(schema).validate(manifest)
    assert manifest["validation"]["valid"] is False
    assert len(manifest["reports"]) == expected_report_count
    assert expected_component is not None
    assert expected_status is not None
    assert manifest["components"][expected_component]["status"] == expected_status

    if case_name == "readable-malformed":
        assert manifest["reports"] == [
            {
                "component": "python",
                "format": "cobertura-xml",
                "path": "tests/fixtures/quality/python-malformed.xml",
                "sha256": hashlib.sha256(
                    (FIXTURES / "python-malformed.xml").read_bytes()
                ).hexdigest(),
            }
        ]
    if case_name == "mixed-unreadable-readable":
        assert manifest["reports"] == [
            {
                "component": "frontend",
                "format": "lcov",
                "path": "tests/fixtures/quality/frontend-valid.lcov",
                "sha256": hashlib.sha256(
                    (FIXTURES / "frontend-valid.lcov").read_bytes()
                ).hexdigest(),
            }
        ]
    if case_name == "duplicate-component":
        for metric in manifest["components"]["go-gateway"]["metrics"].values():
            assert isinstance(metric, dict)
            assert metric["status"] == "missing"


def test_malformed_contract_returns_two(tmp_path: Path) -> None:
    malformed_contract = tmp_path / "bad-contract.json"
    malformed_contract.write_text("{not valid JSON", encoding="utf-8")

    invalid_contract = _run_normalizer(
        tmp_path / "invalid-contract.json",
        "--contract",
        str(malformed_contract),
    )

    assert invalid_contract.returncode == 2
    assert "Traceback" not in invalid_contract.stderr
    assert invalid_contract.stderr.startswith("ERROR:")


def test_print_error_escapes_control_characters_to_one_prefixed_line() -> None:
    result = subprocess.run(  # noqa: S603
        [
            sys.executable,
            "-c",
            (
                "import sys; "
                "sys.path.insert(0, sys.argv[1]); "
                "import normalize_coverage_reports as normalizer; "
                "normalizer._print_error(sys.stdin.buffer.read().decode('utf-8'))"
            ),
            str(NORMALIZER_PATH.parent),
        ],
        capture_output=True,
        check=False,
        input=b"unsafe-path\r\nforged-diagnostic",
    )

    assert result.returncode == 0
    assert result.stderr.decode("utf-8").splitlines() == [
        r"ERROR: unsafe-path\x0d\x0aforged-diagnostic"
    ]


def test_coverage_manifest_schema_is_closed_and_versioned() -> None:
    schema = json.loads(QUALITY_MANIFEST_SCHEMA_PATH.read_text(encoding="utf-8"))

    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert schema["properties"]["schema_version"]["const"] == 1
    assert schema["additionalProperties"] is False
    metric_schema = schema["$defs"]["metric"]
    assert metric_schema["additionalProperties"] is False
    variants = metric_schema["oneOf"]
    assert len(variants) == 4
    statuses = {
        variant["properties"]["status"].get("const")
        or tuple(variant["properties"]["status"]["enum"])
        for variant in variants
    }
    assert statuses == {
        "native",
        "derived",
        ("experimental", "unsupported"),
        "missing",
    }
    native = next(
        variant
        for variant in variants
        if variant["properties"]["status"].get("const") == "native"
    )
    assert native["properties"]["covered"] == {"type": "integer", "minimum": 0}
    assert native["properties"]["total"] == {"type": "integer", "minimum": 0}
    assert native["properties"]["percent"]["type"] == "number"
    derived = next(
        variant
        for variant in variants
        if variant["properties"]["status"].get("const") == "derived"
    )
    assert "derivation" in derived["required"]
    assert derived["properties"]["covered"]["type"] == "integer"
    unmeasured = next(
        variant
        for variant in variants
        if variant["properties"]["status"].get("enum")
        == ["experimental", "unsupported"]
    )
    assert "reason_code" in unmeasured["required"]
    assert {
        field: unmeasured["properties"][field]["type"]
        for field in ("covered", "total", "percent")
    } == {"covered": "null", "total": "null", "percent": "null"}
    missing = next(
        variant
        for variant in variants
        if variant["properties"]["status"].get("const") == "missing"
    )
    assert {
        field: missing["properties"][field]["type"]
        for field in ("covered", "total", "percent")
    } == {"covered": "null", "total": "null", "percent": "null"}


@pytest.mark.parametrize(
    "metric",
    [
        {
            "status": "native",
            "covered": 1,
            "total": 1,
            "percent": 100.0,
            "reason_code": "must_not_be_present",
        },
        {
            "status": "native",
            "covered": 1,
            "total": 1,
            "percent": 100.0,
            "derivation": "must_not_be_present",
        },
        {
            "status": "derived",
            "covered": 1,
            "total": 1,
            "percent": 100.0,
            "derivation": "valid derived provenance",
            "reason_code": "must_not_be_present",
        },
        {
            "status": "unsupported",
            "covered": None,
            "total": None,
            "percent": None,
            "reason_code": "valid unsupported reason",
            "derivation": "must_not_be_present",
        },
        {
            "status": "missing",
            "covered": None,
            "total": None,
            "percent": None,
            "reason_code": "must_not_be_present",
        },
        {
            "status": "missing",
            "covered": None,
            "total": None,
            "percent": None,
            "derivation": "must_not_be_present",
        },
    ],
)
def test_metric_schema_rejects_incompatible_status_metadata(
    metric: dict[str, object],
) -> None:
    schema = json.loads(QUALITY_MANIFEST_SCHEMA_PATH.read_text(encoding="utf-8"))
    metric_schema = schema["$defs"]["metric"]
    assert isinstance(metric_schema, dict)

    with pytest.raises(ValidationError):
        Draft202012Validator(metric_schema).validate(metric)


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
