"""Fail-closed path contracts for the PowerShell owner-key resolver."""

from __future__ import annotations

import json
import os
import runpy
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = ROOT / "start-docker.ps1"
POWERSHELL = shutil.which("pwsh")
GIT = shutil.which("git")
_OWNER_KEY_HELPERS = runpy.run_path(
    str(ROOT / "tests" / "test_start_docker_live_owner_key.py")
)
_git = _OWNER_KEY_HELPERS["_git"]
_non_in_place_fixture = _OWNER_KEY_HELPERS["_non_in_place_fixture"]
_run_powershell_owner_check = _OWNER_KEY_HELPERS["_run_powershell_owner_check"]

_PATH_RUNNER = r"""
param(
    [Parameter(Mandatory=$true)][string]$SourcePath,
    [Parameter(Mandatory=$true)][string]$ProjectRoot,
    [Parameter(Mandatory=$true)][ValidateSet(
        "nonzero", "empty", "multiline", "whitespace", "nul",
        "missing", "nondirectory", "valid"
    )][string]$Scenario,
    [Parameter(Mandatory=$true)][string]$CommonPath
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
$tokens = $null
$parseErrors = $null
$sourceAst = [System.Management.Automation.Language.Parser]::ParseFile(
    $SourcePath, [ref]$tokens, [ref]$parseErrors
)
if ($parseErrors.Count -gt 0) { throw "owner_source_parse_failed" }
$matches = @($sourceAst.FindAll({
    param($node)
    $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and
        $node.Name -ceq "Get-CommonGitOwnerKeyPath"
}, $true))
if ($matches.Count -ne 1) { throw "owner_function_binding_failed" }
Invoke-Expression $matches[0].Extent.Text

$ProjectRoot = [System.IO.Path]::GetFullPath($ProjectRoot)
$script:scenario = $Scenario
$script:commonPath = $CommonPath
$script:gitCalls = 0
function git {
    $script:gitCalls += 1
    switch ($script:scenario) {
        "nonzero" { $global:LASTEXITCODE = 1; $script:commonPath; break }
        "empty" { $global:LASTEXITCODE = 0; break }
        "multiline" {
            $global:LASTEXITCODE = 0
            $script:commonPath
            $script:commonPath
            break
        }
        "whitespace" { $global:LASTEXITCODE = 0; " $($script:commonPath) "; break }
        "nul" { $global:LASTEXITCODE = 0; "$($script:commonPath)$([char]0)"; break }
        default { $global:LASTEXITCODE = 0; $script:commonPath; break }
    }
}

$ok = $false
$failure = ""
try {
    $null = Get-CommonGitOwnerKeyPath
    $ok = $true
} catch {
    $message = [string]$_.Exception.Message
    if ($message -ceq "Live acceptance Git metadata cannot be validated.") {
        $failure = "git_metadata_invalid"
    } elseif ($message -ceq "Live acceptance Git metadata path is missing or unsafe.") {
        $failure = "git_metadata_path_unsafe"
    } else {
        $failure = "unexpected"
    }
}
[pscustomobject]@{
    ok = $ok
    failure = $failure
    gitCalls = $script:gitCalls
} | ConvertTo-Json -Compress
"""


def _run_path_contract(
    tmp_path: Path, *, scenario: str, common_path: Path
) -> dict[str, object]:
    assert POWERSHELL is not None
    project_root = tmp_path / "project"
    project_root.mkdir(exist_ok=True)
    runner = tmp_path / "owner-key-path-contract.ps1"
    runner.write_text(_PATH_RUNNER, encoding="utf-8")
    environment = os.environ.copy()
    environment["XDG_CACHE_HOME"] = str(tmp_path / "powershell-cache")
    result = subprocess.run(  # noqa: S603 - fixed PowerShell host and test runner
        [
            POWERSHELL,
            "-NoProfile",
            "-NonInteractive",
            "-File",
            str(runner),
            "-SourcePath",
            str(LAUNCHER),
            "-ProjectRoot",
            str(project_root.resolve()),
            "-Scenario",
            scenario,
            "-CommonPath",
            str(common_path),
        ],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    assert result.returncode == 0, "PowerShell owner-key path runner failed"
    output_lines = [line for line in result.stdout.splitlines() if line.strip()]
    assert len(output_lines) == 1, "PowerShell path result was not closed"
    parsed = json.loads(output_lines[0])
    assert isinstance(parsed, dict)
    return parsed


@pytest.mark.skipif(POWERSHELL is None, reason="PowerShell 7 is required")
@pytest.mark.parametrize(
    ("scenario", "expected_failure"),
    [
        ("nonzero", "git_metadata_invalid"),
        ("empty", "git_metadata_invalid"),
        ("multiline", "git_metadata_invalid"),
        ("whitespace", "git_metadata_invalid"),
        ("nul", "git_metadata_invalid"),
        ("missing", "git_metadata_path_unsafe"),
        ("nondirectory", "git_metadata_path_unsafe"),
    ],
)
def test_common_git_metadata_rejects_invalid_output(
    tmp_path: Path, scenario: str, expected_failure: str
) -> None:
    common_path = tmp_path / "common metadata"
    if scenario == "nondirectory":
        common_path.write_text("not a directory\n", encoding="utf-8")

    result = _run_path_contract(
        tmp_path,
        scenario=scenario,
        common_path=common_path,
    )

    assert result == {
        "ok": False,
        "failure": expected_failure,
        "gitCalls": 1,
    }


@pytest.mark.skipif(POWERSHELL is None, reason="PowerShell 7 is required")
def test_common_git_metadata_rejects_reparse_directory_when_supported(
    tmp_path: Path,
) -> None:
    target = tmp_path / "real common metadata"
    target.mkdir()
    common_path = tmp_path / "linked common metadata"
    common_path.symlink_to(target, target_is_directory=True)

    result = _run_path_contract(
        tmp_path,
        scenario="valid",
        common_path=common_path,
    )

    assert result == {
        "ok": False,
        "failure": "git_metadata_path_unsafe",
        "gitCalls": 1,
    }


@pytest.mark.skipif(
    POWERSHELL is None or GIT is None,
    reason="PowerShell 7, Git, and the owner HMAC fixture are required",
)
def test_worktree_owner_rejects_reparse_common_key_when_supported(
    tmp_path: Path,
) -> None:
    _repository, worktree, project_name = _non_in_place_fixture(tmp_path)
    reported_common = _git("rev-parse", "--git-common-dir", cwd=worktree)
    reported_path = Path(reported_common)
    common_directory = (
        reported_path if reported_path.is_absolute() else worktree / reported_path
    ).resolve()
    key_path = common_directory / "live-stand-owner.key"
    outside_key = tmp_path / "outside valid owner key"
    valid_key = key_path.read_bytes()
    key_path.unlink()
    outside_key.write_bytes(valid_key)
    key_path.symlink_to(outside_key)

    result = _run_powershell_owner_check(
        tmp_path,
        mode="worktree",
        project_root=worktree,
        project_name=project_name,
    )

    assert result["accepted"] is False
    assert result["stage"] == "worktree_owner_verification"
    assert result["gitLookups"] == 1
