"""Exercise the Go inventory and stdlib gate shell blocks with offline inputs."""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/sbom.yml"
pytest_plugins = ("pytester",)
SCAN_STEPS = (
    ("sbom-go", "Scan Go modules for vulnerabilities + generate SBOM"),
    ("vuln-gate-pr", "Scan Go modules for vulnerabilities (pull request inventory)"),
)
STDLIB_STEP = "Gate the pinned Go builder standard library"
BUILDERS = ("caddy", "gateway", "ws-hub", "file-processor")
MANIFESTS = ("services/gateway/go.mod", "services/pkg/logging/go.mod")
PREFIX = r"""
git() {
  if [[ "$1" != ls-files ]]; then return 90; fi
  case "$AUD_MODE" in
    git-error) return 2 ;;
    git-partial) printf 'services/gateway/go.mod\0'; return 2 ;;
    no-manifests) return 0 ;;
    duplicate-manifest) printf 'services/gateway/go.mod\0services/gateway/go.mod\0' ;;
    *) printf 'services/gateway/go.mod\0services/pkg/logging/go.mod\0' ;;
  esac
}
go() {
  if [[ "$1" != env || "$2" != GOVERSION || "${GOTOOLCHAIN:-}" != local ]]; then return 91; fi
  if [[ "$AUD_MODE" == go-error ]]; then return 2; fi
  printf 'go%s\n' "${AUD_GO_VERSION:-1.26.10}"
}
python3() { "$AUD_PYTHON" "$@"; }
"""
FAKE_SCANNER = r"""#!/usr/bin/env bash
set -euo pipefail
printf '%s\n' "$@" > "$AUD_SCAN_LOG"
printf '%s\n' "${GOWORK-unset}" > "$AUD_GOWORK_LOG"
output=''
manifest=''
config=''
stdlib=false
while (($#)); do
  case "$1" in
    --output|--output-file) output="$2"; shift 2 ;;
    --lockfile) manifest="$2"; shift 2 ;;
    --config) config="$2"; shift 2 ;;
    --all-packages) stdlib=true; shift ;;
    *) shift ;;
  esac
done
if [[ "$AUD_MODE" == config-suppression ]]; then
  if [[ -z "$config" ]]; then
    # Model the pinned scanner loading the adjacent suppression and exiting clean.
    grep -Fq 'id = "GO-2099-9999"' services/gateway/osv-scanner.toml || exit 94
    exit 0
  fi
  # A configuration override must not itself contain an ignore or override.
  [[ -f "$config" && ! -s "$config" ]] || exit 95
  exit 1
fi
case "$AUD_MODE" in
  scanner-error) exit 17 ;;
  finding) exit 1 ;;
  analysis-error)
    printf '%s\n' "Failed to run code analysis (govulncheck) on 'services/caddy/go.mod'" >&2
    exit 1 ;;
  analysis-skipped)
    printf '%s\n' 'Skipping call analysis on Go code since Go is not installed.' >&2
    exit 1 ;;
  missing-report) exit 0 ;;
  malformed-report) printf '{' > "$output"; exit 0 ;;
esac
if [[ "$stdlib" == true ]]; then
  [[ -n "$config" ]] || exit 91
  [[ "$(cat "$config")" == 'ScanGoModVersion = true' ]] || exit 92
  grep -Fqx 'go 1.26.10' "$manifest" || exit 93
  version=1.26.10
  if [[ "$AUD_MODE" == wrong-version ]]; then version=1.26.4; fi
  if [[ "$AUD_MODE" == empty-inventory ]]; then printf '{"results":[]}' > "$output"; exit 0; fi
  if [[ "$AUD_MODE" == wrong-source ]]; then manifest=other/go.mod; fi
  if [[ "$AUD_MODE" == hidden-finding ]]; then
    printf '{"results":[{"source":{"path":"%s","type":"lockfile"},"packages":[{"package":{"name":"stdlib","version":"%s","ecosystem":"Go"},"vulnerabilities":[{"id":"GO-2099-0001"}]}]}]}' "$manifest" "$version" > "$output"
    exit 0
  fi
  printf '{"results":[{"source":{"path":"%s","type":"lockfile"},"packages":[{"package":{"name":"stdlib","version":"%s","ecosystem":"Go"}}]}]}' "$manifest" "$version" > "$output"
fi
exit 0
"""


def _bash() -> str:
    if os.name == "nt":
        candidate = (
            Path(os.environ.get("ProgramFiles", "C:/Program Files"))
            / "Git/bin/bash.exe"
        )
        if candidate.is_file():
            return str(candidate)
    result = shutil.which("bash")
    if result is None:
        pytest.fail(
            "Bash is required for the GitHub Actions shell controls", pytrace=False
        )
    return result


def _step(job: str, name: str) -> dict[str, Any]:
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    return next(
        step for step in workflow["jobs"][job]["steps"] if step.get("name") == name
    )


def _fixture(pytester: pytest.Pytester, mode: str) -> dict[str, str]:
    for manifest in (*MANIFESTS, "go.mod", "gen/go/go.mod"):
        path = pytester.path / manifest
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("module fixture.test/example\n\ngo 1.26.4\n", encoding="utf-8")
    for service in BUILDERS:
        path = pytester.path / "services" / service / "Dockerfile"
        path.parent.mkdir(parents=True, exist_ok=True)
        version = (
            "1.26.9"
            if mode == "builder-mismatch" and service == "gateway"
            else "1.26.10"
        )
        path.write_text(
            f"FROM golang:{version}-alpine3.24@sha256:{'a' * 64} AS builder\n",
            encoding="utf-8",
        )
    if mode == "toolchain-directive":
        with (pytester.path / MANIFESTS[0]).open("a", encoding="utf-8") as file:
            file.write("toolchain go1.27.0\n")
    if mode == "minimum-newer":
        (pytester.path / MANIFESTS[0]).write_text(
            "module fixture.test/example\ngo 1.27.0\n", encoding="utf-8"
        )
    if mode == "missing-manifest":
        (pytester.path / MANIFESTS[0]).unlink()
    if mode == "missing-builder":
        (pytester.path / "services/gateway/Dockerfile").write_text(
            "FROM scratch\n", encoding="utf-8"
        )
    if mode == "config-suppression":
        (pytester.path / "services/gateway/osv-scanner.toml").write_text(
            '[[IgnoredVulns]]\nid = "GO-2099-9999"\n', encoding="utf-8"
        )
    scanner = pytester.path / "fake-osv-scanner"
    scanner.write_text(FAKE_SCANNER, encoding="utf-8")
    scanner.chmod(0o755)
    runner_temp = pytester.path / "runner-temp"
    runner_temp.mkdir()
    env = {
        "AUD_MODE": mode,
        "AUD_PYTHON": Path(sys.executable).as_posix(),
        "AUD_SCAN_LOG": (pytester.path / "scan-log").as_posix(),
        "AUD_GOWORK_LOG": (pytester.path / "gowork-log").as_posix(),
        "OSV_SCANNER_BIN": scanner.as_posix(),
        "RUNNER_TEMP": runner_temp.as_posix(),
        "GITHUB_OUTPUT": (pytester.path / "github-output").as_posix(),
    }
    if mode == "invalid-go-version":
        env["AUD_GO_VERSION"] = "1.26"
    return env


def _run(
    pytester: pytest.Pytester,
    monkeypatch: pytest.MonkeyPatch,
    job: str,
    name: str,
    mode: str,
) -> pytest.RunResult:
    step = _step(job, name)
    assert step.get("continue-on-error") is not True
    for key, value in _fixture(pytester, mode).items():
        monkeypatch.setenv(key, value)
    return pytester.run(
        _bash(),
        "--noprofile",
        "--norc",
        "-e",
        "-o",
        "pipefail",
        "-c",
        PREFIX + "\n" + step["run"],
        timeout=20,
    )


@pytest.mark.parametrize(("job", "name"), SCAN_STEPS)
def test_recursive_scan_names_each_tracked_manifest(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch, job: str, name: str
) -> None:
    result = _run(pytester, monkeypatch, job, name, "ok")
    assert result.ret == 0, result.stderr.str()
    args = (pytester.path / "scan-log").read_text(encoding="utf-8").splitlines()
    assert "--recursive" in args and "./services/" in args
    assert [
        args[index + 1] for index, arg in enumerate(args) if arg == "--lockfile"
    ] == list(MANIFESTS)
    assert (pytester.path / "github-output").read_text(
        encoding="utf-8"
    ).strip() == "scanner_status=0"


@pytest.mark.parametrize(("job", "name"), SCAN_STEPS)
@pytest.mark.parametrize(
    "mode",
    [
        "git-error",
        "git-partial",
        "no-manifests",
        "duplicate-manifest",
        "missing-manifest",
    ],
)
def test_incomplete_manifest_discovery_blocks_the_scan(
    pytester: pytest.Pytester,
    monkeypatch: pytest.MonkeyPatch,
    job: str,
    name: str,
    mode: str,
) -> None:
    result = _run(pytester, monkeypatch, job, name, mode)
    assert result.ret != 0
    assert not (pytester.path / "scan-log").exists()


@pytest.mark.parametrize(("job", "name"), SCAN_STEPS)
@pytest.mark.parametrize(("mode", "status"), [("finding", 1), ("scanner-error", 17)])
def test_module_scan_preserves_the_scanner_status(
    pytester: pytest.Pytester,
    monkeypatch: pytest.MonkeyPatch,
    job: str,
    name: str,
    mode: str,
    status: int,
) -> None:
    result = _run(pytester, monkeypatch, job, name, mode)
    assert result.ret == 0, result.stderr.str()
    assert (pytester.path / "github-output").read_text(encoding="utf-8").strip() == (
        f"scanner_status={status}"
    )


@pytest.mark.parametrize(("job", "name"), SCAN_STEPS)
def test_module_scan_cannot_hide_findings_with_adjacent_config(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch, job: str, name: str
) -> None:
    result = _run(pytester, monkeypatch, job, name, "config-suppression")
    assert result.ret == 0, result.stderr.str()
    assert (pytester.path / "github-output").read_text(encoding="utf-8").strip() == (
        "scanner_status=1"
    )


@pytest.mark.parametrize(("job", "name"), SCAN_STEPS)
def test_module_inventory_scans_each_module_outside_the_root_workspace(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch, job: str, name: str
) -> None:
    result = _run(pytester, monkeypatch, job, name, "ok")
    assert result.ret == 0, result.stderr.str()
    assert (pytester.path / "gowork-log").read_text(encoding="utf-8").strip() == "off"
    assert (
        "--all-vulns"
        in (pytester.path / "scan-log").read_text(encoding="utf-8").splitlines()
    )


@pytest.mark.parametrize(("job", "name"), SCAN_STEPS)
@pytest.mark.parametrize("mode", ["analysis-error", "analysis-skipped"])
def test_module_inventory_rejects_a_call_analysis_error_even_with_findings(
    pytester: pytest.Pytester,
    monkeypatch: pytest.MonkeyPatch,
    job: str,
    name: str,
    mode: str,
) -> None:
    result = _run(pytester, monkeypatch, job, name, mode)
    assert result.ret == 0, result.stderr.str()
    assert (pytester.path / "github-output").read_text(encoding="utf-8").strip() == (
        "scanner_status=2"
    )


@pytest.mark.parametrize("job", ["sbom-go", "vuln-gate-pr"])
def test_stdlib_gate_scans_the_pinned_builder_inventory(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch, job: str
) -> None:
    result = _run(pytester, monkeypatch, job, STDLIB_STEP, "ok")
    assert result.ret == 0, result.stderr.str()
    args = (pytester.path / "scan-log").read_text(encoding="utf-8").splitlines()
    assert "--all-packages" in args and "--all-vulns" in args
    assert "--no-call-analysis=go" in args
    assert "--lockfile" in args and "--config" in args


@pytest.mark.parametrize("job", ["sbom-go", "vuln-gate-pr"])
@pytest.mark.parametrize(
    "mode",
    [
        "git-error",
        "git-partial",
        "no-manifests",
        "duplicate-manifest",
        "missing-manifest",
        "go-error",
        "invalid-go-version",
        "builder-mismatch",
        "missing-builder",
        "toolchain-directive",
        "minimum-newer",
        "scanner-error",
        "finding",
        "missing-report",
        "malformed-report",
        "wrong-version",
        "empty-inventory",
        "wrong-source",
        "hidden-finding",
    ],
)
def test_stdlib_gate_rejects_incomplete_or_vulnerable_evidence(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch, job: str, mode: str
) -> None:
    result = _run(pytester, monkeypatch, job, STDLIB_STEP, mode)
    assert result.ret != 0, (mode, result.stdout.str(), result.stderr.str())
