"""Fail-closed contract checks for Rust fuzzing and TSan evidence."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import yaml

ROOT = Path(__file__).parents[1]
FUZZ_WORKFLOW = ROOT / ".github" / "workflows" / "rust-fuzz.yml"
OSS_BUILD = ROOT / "infra" / "oss-fuzz" / "build.sh"
OSS_PROJECT = ROOT / "infra" / "oss-fuzz" / "project.yaml"
TSAN_RUNNER = ROOT / "scripts" / "run_tsan_tests.sh"
TSAN_SUPPRESSIONS = ROOT / "tests" / "tsan_suppressions.txt"


def _native_targets() -> set[str]:
    manifest = tomllib.loads(
        (ROOT / "native" / "rust_ext" / "fuzz" / "Cargo.toml").read_text(
            encoding="utf-8"
        )
    )
    bins = manifest["bin"]
    return {entry["name"] for entry in bins}


def test_native_fuzz_job_executes_every_declared_target_and_caches_its_workspace() -> (
    None
):
    workflow = yaml.safe_load(FUZZ_WORKFLOW.read_text(encoding="utf-8"))
    fuzz_job = workflow["jobs"]["fuzz"]
    run_step = next(
        step for step in fuzz_job["steps"] if step.get("name") == "Run fuzz targets"
    )
    run_text = run_step["run"]
    declared = set(
        re.findall(r"^\s+(fuzz_[A-Za-z0-9_]+)$", run_text, flags=re.MULTILINE)
    )

    assert declared == _native_targets()
    assert "cargo +nightly fuzz list" in run_text
    assert "inventory drifted" in run_text
    assert 'cargo +nightly fuzz run "$target"' in run_text

    cache = next(
        step
        for step in fuzz_job["steps"]
        if step.get("uses", "").startswith("actions/cache")
    )
    assert "native/rust_ext/fuzz/target/" in str(cache["with"]["path"])
    cache_key = str(cache["with"]["key"])
    assert "native/rust_ext/fuzz/Cargo.toml" in cache_key
    assert "native/rust_ext/fuzz/Cargo.lock" in cache_key


def test_native_fuzz_inventory_uses_null_safe_array_population() -> None:
    """The actionlint/shellcheck gate must not flag command substitution splitting."""

    workflow = yaml.safe_load(FUZZ_WORKFLOW.read_text(encoding="utf-8"))
    run_step = next(
        step
        for step in workflow["jobs"]["fuzz"]["steps"]
        if step.get("name") == "Run fuzz targets"
    )
    run_text = str(run_step["run"])

    assert (
        "mapfile -t expected < <(printf '%s\\n' \"${targets[@]}\" | sort)" in run_text
    )
    assert "expected=($(" not in run_text


def test_native_fuzz_uses_stable_pyo3_abi_for_standalone_binaries() -> None:
    """Fuzz binaries must not link private symbols from a runner libpython."""

    manifest = tomllib.loads(
        (ROOT / "native" / "rust_ext" / "Cargo.toml").read_text(encoding="utf-8")
    )
    pyo3 = manifest["dependencies"]["pyo3"]
    assert "abi3-py311" in pyo3["features"]

    fuzz_manifest = tomllib.loads(
        (ROOT / "native" / "rust_ext" / "fuzz" / "Cargo.toml").read_text(
            encoding="utf-8"
        )
    )
    assert fuzz_manifest["dependencies"]["rust_ext"]["default-features"] is False


def test_additional_fuzz_matrix_matches_all_checked_in_targets() -> None:
    workflow = yaml.safe_load(FUZZ_WORKFLOW.read_text(encoding="utf-8"))
    entries = workflow["jobs"]["fuzz-additional-rust-crates"]["strategy"]["matrix"][
        "include"
    ]
    expected = {
        "crates/pyo3-sanitizer/fuzz": {
            path.name.removesuffix(".rs")
            for path in (
                ROOT / "crates" / "pyo3-sanitizer" / "fuzz" / "fuzz_targets"
            ).glob("*.rs")
        },
        "frontend/wasm-sanitizer/fuzz": {
            path.name.removesuffix(".rs")
            for path in (
                ROOT / "frontend" / "wasm-sanitizer" / "fuzz" / "fuzz_targets"
            ).glob("*.rs")
        },
        "frontend/rust-crypto/fuzz": {
            path.name.removesuffix(".rs")
            for path in (
                ROOT / "frontend" / "rust-crypto" / "fuzz" / "fuzz_targets"
            ).glob("*.rs")
        },
    }
    actual = {entry["directory"]: set(entry["targets"].split()) for entry in entries}
    assert actual == expected


def test_oss_fuzz_builder_is_fail_closed_and_advertises_only_libfuzzer() -> None:
    script = OSS_BUILD.read_text(encoding="utf-8")
    assert "set -euo pipefail" in script
    assert "cargo fuzz build --release" in script
    assert "cargo fuzz list" in script
    assert "cargo fuzz build --release 2>/dev/null || true" not in script
    assert "cp target/" not in script
    assert "if (( ${#fuzzers[@]} == 0 )); then" in script
    assert "did not produce executable" in script
    assert 'find "${OUT}"' in script

    project = yaml.safe_load(OSS_PROJECT.read_text(encoding="utf-8"))
    assert project["fuzzing_engines"] == ["libfuzzer"]


def test_tsan_runner_proves_detection_and_rejects_unsuppressed_reports() -> None:
    script = TSAN_RUNNER.read_text(encoding="utf-8")
    assert "tests/tsan_race_canary.c" in script
    assert "-fsanitize=thread" in script
    assert "TSAN_CANARY_EXIT=$?" in script
    assert "unexpectedly exited successfully" in script
    assert "TSAN_UNSUPPRESSED=0" in script
    assert "ThreadSanitizer: data race" in script
    assert "unsuppressed race or memory error" in script

    suppressions = TSAN_SUPPRESSIONS.read_text(encoding="utf-8")
    assert "called_from_lib:uvloop" in suppressions
    assert "race:__pyfunction_batch_detect_conflicts_py" in suppressions
    assert "race:__pyfunction_verify_audit_signature" in suppressions
    for broad_rule in (
        "called_from_lib:libuv.so",
        "called_from_lib:libpython3",
        "race:memcpy",
    ):
        assert broad_rule not in suppressions
