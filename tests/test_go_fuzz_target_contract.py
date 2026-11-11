from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
import sys
from pathlib import Path
from shutil import which

import pytest
import yaml

pytest_plugins = ("pytester",)

ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "scripts" / "ci" / "run-go-fuzz.sh"


@pytest.mark.parametrize(
    ("workflow_name", "job_name", "expected"),
    [
        (
            "ci.yml",
            "go-fuzz",
            {
                ("services/ws-hub", "./pkg/hub", "FuzzParseMessage"),
                ("services/ws-hub", "./pkg/hub", "FuzzParseResumeToken"),
            },
        ),
        (
            "go-fuzz.yml",
            "fuzz",
            {
                (
                    "services/file-processor",
                    "./internal/middleware",
                    "FuzzEstimateQueryDepth",
                ),
                ("services/gateway", "./middleware", "FuzzJWTValidation"),
                ("services/ws-hub", "./pkg/hub", "FuzzParseMessage"),
                ("services/ws-hub", "./pkg/hub", "FuzzParseResumeToken"),
            },
        ),
    ],
)
def test_workflow_fuzz_targets_exist_and_use_fail_closed_runner(
    workflow_name: str, job_name: str, expected: set[tuple[str, str, str]]
) -> None:
    workflow = yaml.safe_load(
        (ROOT / ".github" / "workflows" / workflow_name).read_text()
    )
    selected = []
    for step in workflow["jobs"][job_name]["steps"]:
        directory = "."
        for line in step.get("run", "").splitlines():
            args = shlex.split(line, comments=True)
            if not args:
                continue
            if args[0] == "cd":
                directory = args[1]
            assert not (
                args[:2] == ["go", "test"] and any("-fuzz=" in arg for arg in args)
            )
            if "run-go-fuzz.sh" not in line:
                continue
            assert args[:2] == ["bash", "../../scripts/ci/run-go-fuzz.sh"]
            package, target = args[2:4]
            selected.append((directory, package, target))
            sources = (ROOT / directory / package).glob("*_test.go")
            declaration = rf"(?m)^func {re.escape(target)}\(\w+ \*testing\.F\)"
            assert any(
                re.search(declaration, source.read_text()) for source in sources
            ), target
    assert len(selected) == len(expected)
    assert set(selected) == expected


@pytest.fixture
def fake_go(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    executable = tmp_path / "go"
    executable.write_text(
        f"#!{sys.executable}\n"
        "import json, os, sys\n"
        "with open(os.environ['GO_CALLS'], 'a') as calls:\n"
        "    calls.write(json.dumps(sys.argv[1:]) + '\\n')\n"
        "if any(arg.startswith('-list=') for arg in sys.argv):\n"
        "    print(os.environ.get('GO_TARGETS', 'FuzzParser'))\n"
        "    sys.exit(int(os.environ.get('GO_LIST_EXIT', '0')))\n"
        "sys.exit(int(os.environ.get('GO_FUZZ_EXIT', '0')))\n"
    )
    executable.chmod(0o755)
    calls = tmp_path / "calls.jsonl"
    monkeypatch.setenv("PATH", f"{tmp_path}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("GO_CALLS", str(calls))
    return calls


def run_fuzz(pytester: pytest.Pytester, *args: str) -> pytest.RunResult:
    assert RUNNER.exists(), "missing fail-closed fuzz runner"
    bash = which("bash")
    assert bash is not None, "the workflow's Bash shell is required"
    return pytester.run(bash, str(RUNNER), *args, timeout=10)


@pytest.mark.parametrize(
    "listing",
    [
        "",
        "testing: warning: no fuzz tests to fuzz",
        "FuzzParserExtra",
        "FuzzParser/seed#0",
        "TestFuzzParser",
    ],
)
def test_runner_rejects_missing_or_inexact_target(
    fake_go: Path,
    monkeypatch: pytest.MonkeyPatch,
    listing: str,
    pytester: pytest.Pytester,
) -> None:
    monkeypatch.setenv("GO_TARGETS", listing)
    result = run_fuzz(
        pytester, "./pkg/hub", "FuzzParser", "-fuzztime=20s", "-parallel=1"
    )
    assert result.ret == 1
    assert "Missing fuzz target FuzzParser in ./pkg/hub" in result.stderr.str()
    assert len(fake_go.read_text().splitlines()) == 1


def test_runner_preserves_listing_failure(
    fake_go: Path, monkeypatch: pytest.MonkeyPatch, pytester: pytest.Pytester
) -> None:
    monkeypatch.setenv("GO_LIST_EXIT", "7")
    result = run_fuzz(pytester, "./pkg/hub", "FuzzParser")
    assert result.ret == 7
    assert len(fake_go.read_text().splitlines()) == 1


@pytest.mark.parametrize("fuzz_exit", [0, 9])
def test_runner_preserves_flags_exact_target_and_fuzz_result(
    fake_go: Path,
    monkeypatch: pytest.MonkeyPatch,
    fuzz_exit: int,
    pytester: pytest.Pytester,
) -> None:
    monkeypatch.setenv("GO_FUZZ_EXIT", str(fuzz_exit))
    monkeypatch.setenv("GO_TARGETS", "FuzzParser\nok  example/hub 0.001s")
    flags = ["-v", "-fuzztime=20s", "-parallel=1", "-timeout=3m"]
    result = run_fuzz(pytester, "./pkg/hub", "FuzzParser", *flags)
    assert result.ret == fuzz_exit
    assert [json.loads(line) for line in fake_go.read_text().splitlines()] == [
        ["test", "./pkg/hub", "-list=^FuzzParser$"],
        ["test", "./pkg/hub", "-fuzz=^FuzzParser$", *flags],
    ]


@pytest.mark.parametrize(
    "args", [[], ["./pkg/hub"], ["./pkg/hub", "Fuzz.*"], ["./pkg/hub", "TestParser"]]
)
def test_runner_rejects_invalid_invocation(
    fake_go: Path, args: list[str], pytester: pytest.Pytester
) -> None:
    result = run_fuzz(pytester, *args)
    assert result.ret == 2
    assert not fake_go.exists()


@pytest.mark.parametrize(
    "flag", ["-fuzz=Missing", "-list=Fuzz", "-skip=Fuzz", "-args", "./other-package"]
)
def test_runner_rejects_flags_that_can_bypass_target_selection(
    fake_go: Path, pytester: pytest.Pytester, flag: str
) -> None:
    result = run_fuzz(pytester, "./pkg/hub", "FuzzParser", flag)
    assert result.ret == 2
    assert "Unsupported fuzz flag" in result.stderr.str()
    assert not fake_go.exists()


def test_ci_fuzz_uploads_package_crash_corpus() -> None:
    workflow = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text())
    upload = next(
        step
        for step in workflow["jobs"]["go-fuzz"]["steps"]
        if step.get("name") == "Upload fuzz corpus on failure"
    )
    assert upload["if"] == "failure()"
    assert upload["with"]["path"] == "services/ws-hub/pkg/hub/testdata/fuzz/"


def test_fuzz_workflow_contract_preserves_reviewed_companion_binding() -> None:
    ledger = json.loads((ROOT / "quality/semgrep-dispositions.json").read_text())
    path = "tests/test_quality_workflow_contract.py"
    companions = [
        companion
        for disposition in ledger["dispositions"]
        for companion in disposition["companions"]
        if companion["path"] == path
    ]
    assert len(companions) == 1
    assert (
        companions[0]["sha256"]
        == hashlib.sha256((ROOT / path).read_bytes()).hexdigest()
    )
