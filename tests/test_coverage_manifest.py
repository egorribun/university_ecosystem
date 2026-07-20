from __future__ import annotations

import hashlib
import json
import os
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

if not QUALITY_CONTRACT_PATH.exists():
    pytest.skip("Quality contract file not found", allow_module_level=True)
QUALITY_MANIFEST_SCHEMA_PATH = (
    REPOSITORY_ROOT / "quality" / "coverage-manifest.schema.json"
)
COMMIT_SHA = "a1b2c3d"
GENERATED_AT = "2026-07-17T00:00:00Z"
MAX_COVERAGE_COUNTER = (1 << 63) - 1
DEEP_JSON_DEPTH = 15_000


def _write_test_contract(path: Path) -> None:
    contract = {
        "version": 1,
        "policy": {
            "patch_coverage": 100,
            "viable_mutant_score": 100,
            "required_pr_matrix": True,
        },
        "coverage_minimums": {
            "lines": 91,
            "statements": 91,
            "branches": 82,
            "functions": 82,
            "tier0": 100,
        },
        "components": {
            "python": {
                "coverage": {
                    "lines": 99,
                    "statements": 99,
                    "branches": 98,
                    "functions": 98,
                }
            },
            "frontend": {
                "coverage": {
                    "lines": 91,
                    "statements": 91,
                    "branches": 82,
                    "functions": 82,
                }
            },
            "go-gateway": {
                "coverage": {
                    "lines": 99,
                    "statements": 99,
                    "branches": 98,
                    "functions": 98,
                }
            },
            "go-ws-hub": {
                "coverage": {
                    "lines": 99,
                    "statements": 99,
                    "branches": 98,
                    "functions": 98,
                }
            },
            "go-file-processor": {
                "coverage": {
                    "lines": 99,
                    "statements": 99,
                    "branches": 98,
                    "functions": 98,
                }
            },
            "rust-native": {
                "coverage": {
                    "lines": 99,
                    "statements": 99,
                    "branches": 98,
                    "functions": 98,
                }
            },
            "rust-pyo3-sanitizer": {
                "coverage": {
                    "lines": 99,
                    "statements": 99,
                    "branches": 98,
                    "functions": 98,
                }
            },
            "rust-wasm-sanitizer": {
                "coverage": {
                    "lines": 99,
                    "statements": 99,
                    "branches": 98,
                    "functions": 98,
                }
            },
            "infrastructure": {
                "coverage": {
                    "lines": 99,
                    "statements": 99,
                    "branches": 98,
                    "functions": 98,
                }
            },
            "workflows": {
                "coverage": {
                    "lines": 99,
                    "statements": 99,
                    "branches": 98,
                    "functions": 98,
                }
            },
            "scripts": {
                "coverage": {
                    "lines": 99,
                    "statements": 99,
                    "branches": 98,
                    "functions": 98,
                }
            },
        },
        "tier0": {
            "coverage": {
                "lines": 100,
                "statements": 100,
                "branches": 100,
                "functions": 100,
            }
        },
        "required_artifacts": [
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
        ],
        "exclusions": [],
        "quarantines": [],
    }
    path.write_text(json.dumps(contract), encoding="utf-8")


def _run_normalizer(
    output: Path,
    *arguments: str,
    cwd: Path | None = None,
    commit_sha: str = COMMIT_SHA,
    generated_at: str = GENERATED_AT,
) -> subprocess.CompletedProcess[str]:
    extra_args = []
    if "--contract" not in arguments:
        contract_path = output.parent / "quality-contract.json"
        _write_test_contract(contract_path)
        extra_args = ["--contract", str(contract_path)]

    command = [
        sys.executable,
        str(NORMALIZER_PATH),
        "--commit-sha",
        commit_sha,
        "--generated-at",
        generated_at,
        "--output",
        str(output),
        *extra_args,
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


def _normalizer_module() -> object:
    """Load the CLI module directly for bounded parser-helper tests."""
    module_directory = str(NORMALIZER_PATH.parent)
    sys.path.insert(0, module_directory)
    try:
        import normalize_coverage_reports as normalizer
    finally:
        sys.path.remove(module_directory)
    return normalizer


def _deeply_nested_json_object(depth: int = DEEP_JSON_DEPTH) -> str:
    return ('{"nested":' * depth) + "0" + ("}" * depth)


def _full_report_arguments() -> list[str]:
    rust_report = FIXTURES / "rust-valid.json"
    return [
        "--python-xml",
        str(FIXTURES / "python-valid.xml"),
        "--frontend-lcov",
        str(FIXTURES / "frontend-valid.lcov"),
        "--go-report",
        f"go-gateway={FIXTURES / 'go-valid.coverprofile'}",
        "--go-report",
        f"go-ws-hub={FIXTURES / 'go-ws-hub-valid.coverprofile'}",
        "--go-report",
        f"go-file-processor={FIXTURES / 'go-file-processor-valid.coverprofile'}",
        "--rust-report",
        f"rust-native={rust_report}",
        "--rust-report",
        f"rust-pyo3-sanitizer={rust_report}",
        "--rust-report",
        f"rust-wasm-sanitizer={rust_report}",
    ]


def _assert_structural_source_evidence_failure(
    tmp_path: Path,
    component: str,
    report_path: Path,
    *arguments: str,
) -> dict[str, object]:
    output = tmp_path / "quality-manifest.json"

    result = _run_normalizer(output, *arguments)

    assert result.returncode == 2
    assert "Traceback" not in result.stderr
    assert all(line.startswith("ERROR:") for line in result.stderr.splitlines())
    manifest = json.loads(output.read_text(encoding="utf-8"))
    schema = json.loads(QUALITY_MANIFEST_SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator(schema).validate(manifest)
    assert manifest["validation"]["valid"] is False
    assert manifest["components"][component]["status"] == "failed"
    assert (
        next(
            report for report in manifest["reports"] if report["component"] == component
        )["sha256"]
        == hashlib.sha256(report_path.read_bytes()).hexdigest()
    )
    return manifest


def _write_python_source_fixture(
    tmp_path: Path,
    filename: str,
    source_path: str,
) -> Path:
    report_path = tmp_path / filename
    report_path.write_text(
        (FIXTURES / "python-valid.xml")
        .read_text(encoding="utf-8")
        .replace('filename="app/example.py"', f'filename="{source_path}"'),
        encoding="utf-8",
    )
    return report_path


def _write_lcov_source_fixture(
    tmp_path: Path,
    filename: str,
    source_path: str,
) -> Path:
    report_path = tmp_path / filename
    report_path.write_text(
        "\n".join(
            (
                f"SF:{source_path}",
                "DA:1,1",
                "LF:1",
                "LH:1",
                "end_of_record",
                "",
            )
        ),
        encoding="utf-8",
    )
    return report_path


def _write_go_source_fixture(
    tmp_path: Path,
    filename: str,
    source_path: str,
) -> Path:
    report_path = tmp_path / filename
    report_path.write_text(
        "\n".join(
            (
                "mode: count",
                f"{source_path}:1.1,1.10 1 1",
                "",
            )
        ),
        encoding="utf-8",
    )
    return report_path


def _rust_totals() -> dict[str, object]:
    return {
        "functions": {"count": 2, "covered": 1},
        "lines": {"count": 4, "covered": 3},
    }


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
    if not QUALITY_CONTRACT_PATH.exists():
        pytest.skip("Quality contract file does not exist (e.g., under mutmut)")
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


def test_source_identity_accepts_in_root_relative_backslash_and_absolute_paths(
    tmp_path: Path,
) -> None:
    python_report = _write_python_source_fixture(
        tmp_path,
        "python-backslash.xml",
        r".\app\example.py",
    )
    frontend_report = _write_lcov_source_fixture(
        tmp_path,
        "frontend-absolute.lcov",
        (REPOSITORY_ROOT / "frontend" / "src" / "one.ts").as_posix(),
    )
    go_report = _write_go_source_fixture(
        tmp_path,
        "gateway-backslash.coverprofile",
        r".\services\gateway\main.go",
    )
    rust_report = tmp_path / "rust-absolute-files.json"
    rust_report.write_text(
        json.dumps(
            {
                "totals": _rust_totals(),
                "files": [
                    {"path": str(REPOSITORY_ROOT / "native" / "rust_ext" / "lib.rs")}
                ],
            }
        ),
        encoding="utf-8",
    )
    output = tmp_path / "quality-manifest.json"

    result = _run_normalizer(
        output,
        "--python-xml",
        str(python_report),
        "--frontend-lcov",
        str(frontend_report),
        "--go-report",
        f"go-gateway={go_report}",
        "--rust-report",
        f"rust-native={rust_report}",
    )

    assert result.returncode == 1
    assert all("source identity" not in error for error in result.stderr.splitlines())


@pytest.mark.parametrize(
    ("component", "source_root"),
    (
        ("python", "app"),
        ("frontend", "frontend/src"),
        ("go-gateway", "services/gateway"),
        ("go-ws-hub", "services/ws-hub"),
        ("go-file-processor", "services/file-processor"),
        ("rust-native", "native/rust_ext"),
        ("rust-pyo3-sanitizer", "crates/pyo3-sanitizer"),
        ("rust-wasm-sanitizer", "frontend/wasm-sanitizer"),
        ("infrastructure", "infra"),
        ("infrastructure", "infrastructure"),
        ("infrastructure", "k8s"),
        ("infrastructure", "charts"),
        ("workflows", ".github/workflows"),
        ("scripts", "scripts"),
    ),
)
def test_canonical_source_identity_rejects_every_root_directory_itself(
    component: str,
    source_root: str,
) -> None:
    normalizer = _normalizer_module()
    root_only_variants = (
        source_root,
        f"./{source_root}",
        f"{source_root}/.",
        f"{source_root}/child/..",
        (REPOSITORY_ROOT / source_root).as_posix(),
    )

    for source_path in root_only_variants:
        with pytest.raises(
            normalizer._InputError,
            match="must identify a file below configured roots",
        ):
            normalizer._canonical_source_identity(component, source_path)

    assert (
        normalizer._canonical_source_identity(
            component, f"{source_root}/fictitious-source.ext"
        )
        == f"{source_root}/fictitious-source.ext"
    )


def test_xml_root_only_source_path_is_a_structural_evidence_error(
    tmp_path: Path,
) -> None:
    report_path = _write_python_source_fixture(tmp_path, "python-root-only.xml", "app")

    _assert_structural_source_evidence_failure(
        tmp_path,
        "python",
        report_path,
        "--python-xml",
        str(report_path),
    )


def test_lcov_root_only_source_path_is_a_structural_evidence_error(
    tmp_path: Path,
) -> None:
    report_path = _write_lcov_source_fixture(
        tmp_path, "frontend-root-only.lcov", "frontend/src"
    )

    _assert_structural_source_evidence_failure(
        tmp_path,
        "frontend",
        report_path,
        "--frontend-lcov",
        str(report_path),
    )


def test_go_root_only_source_path_is_a_structural_evidence_error(
    tmp_path: Path,
) -> None:
    report_path = _write_go_source_fixture(
        tmp_path, "gateway-root-only.coverprofile", "services/gateway"
    )

    _assert_structural_source_evidence_failure(
        tmp_path,
        "go-gateway",
        report_path,
        "--go-report",
        f"go-gateway={report_path}",
    )


def test_rust_root_only_source_path_is_a_structural_evidence_error(
    tmp_path: Path,
) -> None:
    report_path = tmp_path / "rust-root-only.json"
    report_path.write_text(
        json.dumps(
            {
                "totals": _rust_totals(),
                "files": [{"path": "native/rust_ext"}],
            }
        ),
        encoding="utf-8",
    )

    _assert_structural_source_evidence_failure(
        tmp_path,
        "rust-native",
        report_path,
        "--rust-report",
        f"rust-native={report_path}",
    )


@pytest.mark.parametrize(
    "source_path",
    (
        "frontend/src/example.ts",
        "../outside.py",
        "app/../../outside.py",
        "C:app/example.py",
        "D:/foreign/example.py",
        r"\\server\share\example.py",
    ),
)
def test_python_source_identity_rejects_unsafe_or_outside_paths(
    tmp_path: Path,
    source_path: str,
) -> None:
    report_path = _write_python_source_fixture(
        tmp_path,
        "python-unsafe.xml",
        source_path,
    )

    _assert_structural_source_evidence_failure(
        tmp_path,
        "python",
        report_path,
        "--python-xml",
        str(report_path),
    )


def test_frontend_source_identity_rejects_component_root_mismatch(
    tmp_path: Path,
) -> None:
    report_path = _write_lcov_source_fixture(
        tmp_path,
        "frontend-wrong-root.lcov",
        "app/example.py",
    )

    _assert_structural_source_evidence_failure(
        tmp_path,
        "frontend",
        report_path,
        "--frontend-lcov",
        str(report_path),
    )


def test_frontend_source_identity_rejects_control_characters(
    tmp_path: Path,
) -> None:
    report_path = _write_lcov_source_fixture(
        tmp_path,
        "frontend-control-character.lcov",
        "frontend/src/unsafe\tname.ts",
    )

    _assert_structural_source_evidence_failure(
        tmp_path,
        "frontend",
        report_path,
        "--frontend-lcov",
        str(report_path),
    )


@pytest.mark.parametrize(
    ("component", "source_path"),
    (
        ("go-gateway", "services/ws-hub/main.go"),
        ("go-ws-hub", "services/gateway/main.go"),
        ("go-file-processor", "services/gateway/main.go"),
    ),
)
def test_go_source_identity_rejects_selected_component_root_mismatch(
    tmp_path: Path,
    component: str,
    source_path: str,
) -> None:
    report_path = _write_go_source_fixture(
        tmp_path,
        f"{component}-wrong-root.coverprofile",
        source_path,
    )

    _assert_structural_source_evidence_failure(
        tmp_path,
        component,
        report_path,
        "--go-report",
        f"{component}={report_path}",
    )


def test_xml_alias_source_lines_are_duplicate_evidence(tmp_path: Path) -> None:
    report_path = tmp_path / "python-alias-lines.xml"
    report_path.write_text(
        """<coverage lines-covered=\"2\" lines-valid=\"2\">
  <packages><package><classes>
    <class filename=\"app/example.py\"><lines><line number=\"1\" hits=\"1\" /></lines></class>
    <class filename=\".\\app\\example.py\"><lines><line number=\"1\" hits=\"1\" /></lines></class>
  </classes></package></packages>
</coverage>
""",
        encoding="utf-8",
    )

    _assert_structural_source_evidence_failure(
        tmp_path,
        "python",
        report_path,
        "--python-xml",
        str(report_path),
    )


def test_xml_alias_source_spellings_conflict_across_distinct_lines(
    tmp_path: Path,
) -> None:
    report_path = tmp_path / "python-alias-distinct-lines.xml"
    report_path.write_text(
        """<coverage lines-covered=\"2\" lines-valid=\"2\">
  <packages><package><classes>
    <class filename=\"app/example.py\"><lines><line number=\"1\" hits=\"1\" /></lines></class>
    <class filename=\".\\app\\example.py\"><lines><line number=\"2\" hits=\"1\" /></lines></class>
  </classes></package></packages>
</coverage>
""",
        encoding="utf-8",
    )

    _assert_structural_source_evidence_failure(
        tmp_path,
        "python",
        report_path,
        "--python-xml",
        str(report_path),
    )


@pytest.mark.skipif(os.name != "nt", reason="Windows source paths are case-insensitive")
def test_xml_case_only_alias_source_spellings_conflict(
    tmp_path: Path,
) -> None:
    report_path = tmp_path / "python-case-alias-lines.xml"
    report_path.write_text(
        """<coverage lines-covered=\"2\" lines-valid=\"2\">
  <packages><package><classes>
    <class filename=\"app/Example.py\"><lines><line number=\"1\" hits=\"1\" /></lines></class>
    <class filename=\"APP/example.py\"><lines><line number=\"2\" hits=\"1\" /></lines></class>
  </classes></package></packages>
</coverage>
""",
        encoding="utf-8",
    )

    _assert_structural_source_evidence_failure(
        tmp_path,
        "python",
        report_path,
        "--python-xml",
        str(report_path),
    )


def test_lcov_alias_source_records_are_duplicate_evidence(tmp_path: Path) -> None:
    report_path = tmp_path / "frontend-alias-records.lcov"
    report_path.write_text(
        """SF:frontend/src/example.ts
DA:1,1
LF:1
LH:1
end_of_record
SF:.\\frontend\\src\\example.ts
DA:1,1
LF:1
LH:1
end_of_record
""",
        encoding="utf-8",
    )

    _assert_structural_source_evidence_failure(
        tmp_path,
        "frontend",
        report_path,
        "--frontend-lcov",
        str(report_path),
    )


def test_go_alias_source_blocks_are_duplicate_evidence(tmp_path: Path) -> None:
    report_path = tmp_path / "gateway-alias-blocks.coverprofile"
    report_path.write_text(
        """mode: count
services/gateway/main.go:1.1,1.10 1 1
.\\services\\gateway\\main.go:1.1,1.10 1 1
""",
        encoding="utf-8",
    )

    _assert_structural_source_evidence_failure(
        tmp_path,
        "go-gateway",
        report_path,
        "--go-report",
        f"go-gateway={report_path}",
    )


def test_go_alias_source_spellings_conflict_across_distinct_blocks(
    tmp_path: Path,
) -> None:
    report_path = tmp_path / "gateway-alias-distinct-blocks.coverprofile"
    report_path.write_text(
        """mode: count
services/gateway/main.go:1.1,1.10 1 1
.\\services\\gateway\\main.go:2.1,2.10 1 1
""",
        encoding="utf-8",
    )

    _assert_structural_source_evidence_failure(
        tmp_path,
        "go-gateway",
        report_path,
        "--go-report",
        f"go-gateway={report_path}",
    )


@pytest.mark.skipif(os.name != "nt", reason="Windows root-relative path semantics")
def test_python_source_identity_rejects_root_relative_windows_path(
    tmp_path: Path,
) -> None:
    assert REPOSITORY_ROOT.drive
    source_path = str(REPOSITORY_ROOT / "app" / "example.py")[2:]
    assert source_path.startswith("\\")
    report_path = _write_python_source_fixture(
        tmp_path,
        "python-root-relative.xml",
        source_path,
    )

    _assert_structural_source_evidence_failure(
        tmp_path,
        "python",
        report_path,
        "--python-xml",
        str(report_path),
    )


@pytest.mark.skipif(os.name != "nt", reason="Windows Win32 path alias semantics")
@pytest.mark.parametrize(
    "source_path",
    (
        "app/example.py.",
        "app/example.py ",
        "app/example:stream.py",
    ),
)
def test_python_source_identity_rejects_windows_alias_segments(
    tmp_path: Path,
    source_path: str,
) -> None:
    report_path = _write_python_source_fixture(
        tmp_path,
        "python-windows-alias.xml",
        source_path,
    )

    _assert_structural_source_evidence_failure(
        tmp_path,
        "python",
        report_path,
        "--python-xml",
        str(report_path),
    )


@pytest.mark.parametrize(
    "document",
    (
        {
            "data": [{"totals": _rust_totals()}],
            "totals": _rust_totals(),
        },
        {
            "totals": _rust_totals(),
            "files": [{}],
        },
        {
            "totals": _rust_totals(),
            "files": [{"filename": "app/foreign.py"}],
        },
        {
            "data": [
                {
                    "files": [{"filename": "app/foreign.py"}],
                    "totals": _rust_totals(),
                }
            ],
        },
        {
            "data": [
                {
                    "files": [{"filename": "native/rust_ext/lib.rs"}],
                    "totals": _rust_totals(),
                }
            ],
            "files": [{"path": r".\native\rust_ext\lib.rs"}],
        },
        {
            "totals": _rust_totals(),
            "files": [
                {"filename": "native/rust_ext/lib.rs"},
                {"path": r".\native\rust_ext\lib.rs"},
            ],
        },
        {
            "totals": _rust_totals(),
            "files": [
                {
                    "filename": "native/rust_ext/lib.rs",
                    "path": r".\native\rust_ext\lib.rs",
                }
            ],
        },
    ),
)
def test_rust_source_identity_rejects_ambiguous_or_invalid_report_paths(
    tmp_path: Path,
    document: dict[str, object],
) -> None:
    report_path = tmp_path / "rust-invalid-source-identity.json"
    report_path.write_text(json.dumps(document), encoding="utf-8")

    _assert_structural_source_evidence_failure(
        tmp_path,
        "rust-native",
        report_path,
        "--rust-report",
        f"rust-native={report_path}",
    )


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


@pytest.mark.parametrize(
    "counter",
    (
        "9" * (sys.get_int_max_str_digits() + 1),
        "\N{ARABIC-INDIC DIGIT ONE}",
    ),
)
def test_parser_hardening_rejects_non_ascii_or_unrenderable_decimal_counters(
    tmp_path: Path,
    counter: str,
) -> None:
    report_path = tmp_path / "invalid-decimal.xml"
    report_path.write_text(
        (FIXTURES / "python-valid.xml")
        .read_text(encoding="utf-8")
        .replace('lines-covered="1"', f'lines-covered="{counter}"'),
        encoding="utf-8",
    )

    _assert_structural_source_evidence_failure(
        tmp_path,
        "python",
        report_path,
        "--python-xml",
        str(report_path),
    )


def test_parser_hardening_rejects_counter_above_the_documented_maximum(
    tmp_path: Path,
) -> None:
    report_path = tmp_path / "counter-above-maximum.coverprofile"
    report_path.write_text(
        "\n".join(
            (
                "mode: count",
                f"services/gateway/main.go:1.1,1.10 {MAX_COVERAGE_COUNTER + 1} 0",
                "",
            )
        ),
        encoding="utf-8",
    )

    _assert_structural_source_evidence_failure(
        tmp_path,
        "go-gateway",
        report_path,
        "--go-report",
        f"go-gateway={report_path}",
    )


def test_parser_hardening_rejects_aggregation_above_the_documented_maximum(
    tmp_path: Path,
) -> None:
    report_path = tmp_path / "aggregate-above-maximum.coverprofile"
    report_path.write_text(
        "\n".join(
            (
                "mode: count",
                f"services/gateway/main.go:1.1,1.10 {MAX_COVERAGE_COUNTER} 1",
                f"services/gateway/main.go:2.1,2.10 {MAX_COVERAGE_COUNTER} 1",
                "",
            )
        ),
        encoding="utf-8",
    )

    _assert_structural_source_evidence_failure(
        tmp_path,
        "go-gateway",
        report_path,
        "--go-report",
        f"go-gateway={report_path}",
    )


@pytest.mark.parametrize(
    "record",
    (
        "services/gateway/main.go:1.1,1.10\t1 1",
        "services/gateway/main.go:\N{ARABIC-INDIC DIGIT ONE}.1,1.10 1 1",
    ),
)
def test_parser_hardening_rejects_noncanonical_go_numeric_grammar(
    tmp_path: Path,
    record: str,
) -> None:
    report_path = tmp_path / "noncanonical-go.coverprofile"
    report_path.write_text(
        "\n".join(("mode: count", record, "")),
        encoding="utf-8",
    )

    _assert_structural_source_evidence_failure(
        tmp_path,
        "go-gateway",
        report_path,
        "--go-report",
        f"go-gateway={report_path}",
    )


@pytest.mark.parametrize(
    "record",
    (
        "services/gateway/main.go:0.0,0.0 1 1",
        "services/gateway/main.go:3.9,3.0 1 1",
    ),
)
def test_parser_hardening_preserves_go_nonnegative_profile_positions(
    tmp_path: Path,
    record: str,
) -> None:
    report_path = tmp_path / "nonnegative-go-positions.coverprofile"
    report_path.write_text(
        "\n".join(("mode: count", record, "")),
        encoding="utf-8",
    )
    output = tmp_path / "quality-manifest.json"

    result = _run_normalizer(
        output,
        "--go-report",
        f"go-gateway={report_path}",
    )

    assert result.returncode == 1
    assert "Traceback" not in result.stderr
    assert (
        json.loads(output.read_text(encoding="utf-8"))["components"]["go-gateway"][
            "status"
        ]
        == "failed"
    )


def test_parser_hardening_rejects_go_line_range_ending_before_it_starts(
    tmp_path: Path,
) -> None:
    report_path = tmp_path / "reversed-go-lines.coverprofile"
    report_path.write_text(
        "mode: count\nservices/gateway/main.go:3.0,1.0 1 1\n",
        encoding="utf-8",
    )

    _assert_structural_source_evidence_failure(
        tmp_path,
        "go-gateway",
        report_path,
        "--go-report",
        f"go-gateway={report_path}",
    )


def test_parser_hardening_go_interval_helper_handles_a_huge_span_compactly() -> None:
    normalizer = _normalizer_module()

    assert normalizer._go_line_coverage_counts(
        {
            "services/gateway/main.go": [
                (1, 3_000_000_000, False),
                (2_000_000_000, 4_000_000_000, True),
            ]
        }
    ) == (2_000_000_001, 4_000_000_000)


def test_parser_hardening_go_interval_helper_rejects_a_reversed_line_span() -> None:
    normalizer = _normalizer_module()

    with pytest.raises(normalizer._InputError, match="ends before it starts"):
        normalizer._go_line_coverage_counts(
            {"services/gateway/main.go": [(3, 1, True)]}
        )


def test_parser_hardening_rejects_non_ascii_condition_coverage_decoration(
    tmp_path: Path,
) -> None:
    report_path = tmp_path / "non-ascii-condition-coverage.xml"
    report_path.write_text(
        (FIXTURES / "python-valid.xml")
        .read_text(encoding="utf-8")
        .replace('condition-coverage="50% (1/2)"', 'condition-coverage="١% (1/2)"'),
        encoding="utf-8",
    )

    _assert_structural_source_evidence_failure(
        tmp_path,
        "python",
        report_path,
        "--python-xml",
        str(report_path),
    )


@pytest.mark.parametrize("has_xml_declaration", (False, True))
def test_parser_hardening_accepts_utf8_xml_without_a_declared_encoding(
    tmp_path: Path,
    has_xml_declaration: bool,
) -> None:
    report_path = tmp_path / "xml-without-declared-encoding.xml"
    fixture_bytes = (FIXTURES / "python-valid.xml").read_bytes()
    body = fixture_bytes.split(b"?>", maxsplit=1)[1]
    report_path.write_bytes(fixture_bytes if has_xml_declaration else body)
    output = tmp_path / "quality-manifest.json"

    result = _run_normalizer(output, "--python-xml", str(report_path))

    assert result.returncode == 1
    assert "Traceback" not in result.stderr
    assert (
        json.loads(output.read_text(encoding="utf-8"))["components"]["python"]["status"]
        == "failed"
    )


@pytest.mark.parametrize("encoding", ("utf-16", "utf-32"))
def test_parser_hardening_rejects_encoded_xml_dtd_payloads(
    tmp_path: Path,
    encoding: str,
) -> None:
    report_path = tmp_path / f"encoded-dtd-{encoding}.xml"
    report_path.write_bytes(
        (
            f'<?xml version="1.0" encoding="{encoding.upper()}"?>'
            '<!DOCTYPE coverage [<!ENTITY unsafe "payload">]>'
            '<coverage lines-covered="0" lines-valid="0" />'
        ).encode(encoding)
    )

    _assert_structural_source_evidence_failure(
        tmp_path,
        "python",
        report_path,
        "--python-xml",
        str(report_path),
    )


def test_parser_hardening_rejects_unknown_xml_encoding_with_manifest_evidence(
    tmp_path: Path,
) -> None:
    report_path = tmp_path / "unknown-encoding.xml"
    body = (FIXTURES / "python-valid.xml").read_bytes().split(b"?>", maxsplit=1)[1]
    report_path.write_bytes(
        b'<?xml version="1.0" encoding="not-a-real-encoding"?>' + body
    )

    _assert_structural_source_evidence_failure(
        tmp_path,
        "python",
        report_path,
        "--python-xml",
        str(report_path),
    )


def test_parser_hardening_accepts_utf8_bom_coverage_xml(tmp_path: Path) -> None:
    report_path = tmp_path / "utf8-bom.xml"
    body = (FIXTURES / "python-valid.xml").read_bytes().split(b"?>", maxsplit=1)[1]
    report_path.write_bytes(
        b'\xef\xbb\xbf<?xml version="1.0" encoding="UTF-8"?>' + body
    )
    output = tmp_path / "quality-manifest.json"

    result = _run_normalizer(output, "--python-xml", str(report_path))

    assert result.returncode == 1
    assert "Traceback" not in result.stderr
    assert (
        json.loads(output.read_text(encoding="utf-8"))["components"]["python"]["status"]
        == "failed"
    )


def test_parser_hardening_deeply_nested_rust_json_writes_failed_manifest(
    tmp_path: Path,
) -> None:
    report_path = tmp_path / "deep-rust.json"
    report_path.write_text(_deeply_nested_json_object(), encoding="utf-8")

    _assert_structural_source_evidence_failure(
        tmp_path,
        "rust-native",
        report_path,
        "--rust-report",
        f"rust-native={report_path}",
    )


def test_parser_hardening_deeply_nested_contract_leaves_output_untouched(
    tmp_path: Path,
) -> None:
    contract_path = tmp_path / "deep-contract.json"
    contract_path.write_text(_deeply_nested_json_object(), encoding="utf-8")
    output = tmp_path / "quality-manifest.json"
    stale_output = b'{"stale": true}\n'
    output.write_bytes(stale_output)

    result = _run_normalizer(output, "--contract", str(contract_path))

    assert result.returncode == 2
    assert "Traceback" not in result.stderr
    assert output.read_bytes() == stale_output


def test_parser_hardening_rejects_a_mocked_junction_ancestor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    normalizer = _normalizer_module()

    def _is_junction(path: Path) -> bool:
        return path == REPOSITORY_ROOT / "app"

    monkeypatch.setattr(normalizer.Path, "is_junction", _is_junction)

    with pytest.raises(normalizer._InputError, match="symbolic link or junction"):
        normalizer._parse_python_xml(
            (FIXTURES / "python-valid.xml").read_bytes(),
            "python",
        )
