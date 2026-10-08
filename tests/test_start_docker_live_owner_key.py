"""PowerShell contracts for live-stand owner-key lookup."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import uuid
from pathlib import Path

import pytest

from scripts import live_stand

ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = ROOT / "start-docker.ps1"
POWERSHELL = shutil.which("pwsh")
GIT = shutil.which("git")

_POWERSHELL_RUNNER = r"""
param(
    [Parameter(Mandatory=$true)][string]$SourcePath,
    [Parameter(Mandatory=$true)][string]$ProjectRoot,
    [Parameter(Mandatory=$true)][string]$ProjectName,
    [Parameter(Mandatory=$true)][string]$GitExecutable,
    [Parameter(Mandatory=$true)][ValidateSet("inplace", "worktree")][string]$Mode,
    [string]$StateRoot = "",
    [string]$SourceSha = ""
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
$tokens = $null
$parseErrors = $null
$sourceAst = [System.Management.Automation.Language.Parser]::ParseFile(
    $SourcePath, [ref]$tokens, [ref]$parseErrors
)
if ($parseErrors.Count -gt 0) { throw "owner_source_parse_failed" }

function Get-UniqueFunctionText([string]$Name) {
    $matches = @($sourceAst.FindAll({
        param($node)
        $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and
            $node.Name -ceq $Name
    }, $true))
    if ($matches.Count -ne 1) { throw "owner_function_binding_failed" }
    return $matches[0].Extent.Text
}

$functionNames = @(
    "ConvertTo-CanonicalLiveOwnerJson",
    "Test-CanonicalLiveServiceList",
    "Get-CommonGitOwnerKeyPath",
    "Get-VerifiedLiveAcceptanceOwner"
)
if ($Mode -ceq "inplace") {
    $functionNames += @("Assert-LiveStandPrivatePath", "Resolve-OwnedLiveStandStateRoot")
}
foreach ($name in $functionNames) {
    Invoke-Expression (Get-UniqueFunctionText $name)
}

$ProjectRoot = [System.IO.Path]::GetFullPath($ProjectRoot)
$StateRoot = if ($Mode -ceq "inplace") {
    [System.IO.Path]::GetFullPath($StateRoot)
} else {
    $ProjectRoot
}
$LiveStateMode = $Mode -ceq "inplace"
$LiveStandStateRoot = $StateRoot
$script:LiveStandOwner = $null
$env:COMPOSE_PROJECT_NAME = $ProjectName
$env:LIVE_STAND_SOURCE_SHA = $SourceSha
$script:gitLookupCount = 0
$script:GitExecutable = $GitExecutable
function git {
    $script:gitLookupCount += 1
    if ($Mode -ceq "inplace") {
        $global:LASTEXITCODE = 1
        throw "unexpected_git_lookup"
    }
    $gitOutput = @(& $script:GitExecutable @args 2>$null)
    $gitExitCode = $LASTEXITCODE
    $global:LASTEXITCODE = $gitExitCode
    return $gitOutput
}

$result = $null
$stage = "start"
try {
    if ($Mode -ceq "inplace") {
        $stage = "resolve_in_place_owner"
        $resolvedRoot = Resolve-OwnedLiveStandStateRoot -Path $StateRoot
        $stage = "cached_owner_verification"
        $owner = Get-VerifiedLiveAcceptanceOwner
        $stage = "result_projection"
        $result = [pscustomobject]@{
            accepted = $true
            version = [int]$owner.version
            sameResolvedOwner = [object]::ReferenceEquals($owner, $script:LiveStandOwner)
            resolvedPathMatches = [System.StringComparer]::OrdinalIgnoreCase.Equals(
                [System.IO.Path]::GetFullPath($resolvedRoot),
                [System.IO.Path]::GetFullPath($StateRoot)
            )
            gitLookups = $script:gitLookupCount
            failure = ""
            stage = "complete"
            errorType = ""
        }
    } else {
        $stage = "worktree_owner_verification"
        $owner = Get-VerifiedLiveAcceptanceOwner
        $result = [pscustomobject]@{
            accepted = $true
            version = [int]$owner.version
            sameResolvedOwner = $false
            resolvedPathMatches = $false
            gitLookups = $script:gitLookupCount
            failure = ""
            stage = "complete"
            errorType = ""
        }
    }
} catch {
    $message = [string]$_.Exception.Message
    $failure = "unexpected"
    if ($message -ceq "Live acceptance Git metadata cannot be validated.") {
        $failure = "git_metadata_invalid"
    } elseif ($message -ceq "Live acceptance Git metadata path is missing or unsafe.") {
        $failure = "git_metadata_path_unsafe"
    } elseif ($message -ceq "Live acceptance requires a signed owner marker and key.") {
        $failure = "signed_owner_material_missing"
    } elseif ($message -ceq "Live acceptance owner signature is invalid.") {
        $failure = "signature_invalid"
    } elseif ($message -ceq "Live stand owner does not match this source checkout and run root.") {
        $failure = "in_place_owner_mismatch"
    } elseif ($message -like "Live stand state ACL *") {
        $failure = "in_place_acl_rejected"
    } elseif ($message -like "Live stand state *permissions*") {
        $failure = "in_place_permissions_rejected"
    } elseif ($message -like "Live stand state root *") {
        $failure = "in_place_state_root_rejected"
    } elseif ($message -like "Live stand owner *") {
        $failure = "in_place_owner_rejected"
    }
    $result = [pscustomobject]@{
        accepted = $false
        version = 0
        sameResolvedOwner = $false
        resolvedPathMatches = $false
        gitLookups = $script:gitLookupCount
        failure = $failure
        stage = $stage
        errorType = $_.Exception.GetType().Name
        sourceLine = [int]$_.InvocationInfo.ScriptLineNumber
    }
}
ConvertTo-Json -InputObject $result -Compress
"""


def _run_powershell_owner_check(
    tmp_path: Path,
    *,
    mode: str,
    project_root: Path,
    project_name: str,
    state_root: Path | None = None,
    source_sha: str = "",
) -> dict[str, object]:
    assert POWERSHELL is not None
    runner = tmp_path / "owner-key-contract.ps1"
    runner.write_text(_POWERSHELL_RUNNER, encoding="utf-8")
    environment = os.environ.copy()
    environment["XDG_CACHE_HOME"] = str(tmp_path / "powershell-cache")
    arguments = [
        POWERSHELL,
        "-NoProfile",
        "-NonInteractive",
        "-File",
        str(runner),
        "-SourcePath",
        str(LAUNCHER),
        "-ProjectRoot",
        str(project_root.resolve()),
        "-ProjectName",
        project_name,
        "-GitExecutable",
        GIT or "git",
        "-Mode",
        mode,
        "-StateRoot",
        str((state_root or project_root).resolve()),
        "-SourceSha",
        source_sha,
    ]
    result = subprocess.run(  # noqa: S603 - fixed PowerShell host and test-created runner
        arguments,
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    assert result.returncode == 0, "PowerShell owner-key contract runner failed"
    output_lines = [line for line in result.stdout.splitlines() if line.strip()]
    assert len(output_lines) == 1, "PowerShell owner-key contract output was not closed"
    parsed = json.loads(output_lines[0])
    assert isinstance(parsed, dict)
    return parsed


def _git(*arguments: str, cwd: Path) -> str:
    assert GIT is not None
    result = subprocess.run(  # noqa: S603 - fixed Git executable and pytest-owned fixture paths
        [GIT, *arguments],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
        timeout=20,
    )
    assert result.returncode == 0, "temporary Git fixture setup failed"
    return result.stdout.strip()


def _non_in_place_fixture(
    tmp_path: Path,
    *,
    common_key: bytes | None = None,
    tamper_signature: bool = False,
) -> tuple[Path, Path, str]:
    assert GIT is not None
    repository = tmp_path / "source repository"
    repository.mkdir()
    _git("init", "--quiet", cwd=repository)
    _git("config", "user.name", "Contract Fixture", cwd=repository)
    _git("config", "user.email", "contract-fixture@example.invalid", cwd=repository)
    (repository / "anchor.txt").write_text("fixture\n", encoding="utf-8")
    _git("add", "anchor.txt", cwd=repository)
    _git("commit", "--quiet", "-m", "fixture", cwd=repository)

    worktree = tmp_path / "linked worktree"
    _git(
        "worktree",
        "add",
        "--quiet",
        "--detach",
        str(worktree),
        "HEAD",
        cwd=repository,
    )
    reported_common = _git("rev-parse", "--git-common-dir", cwd=worktree)
    reported_path = Path(reported_common)
    common_directory = (
        reported_path if reported_path.is_absolute() else worktree / reported_path
    ).resolve()

    key = common_key if common_key is not None else b"k" * 32
    (common_directory / "live-stand-owner.key").write_bytes(key)
    secrets_root = worktree / ".secrets"
    secrets_root.mkdir()
    # A decoy ensures the supported non-in-place path cannot silently fall
    # back to the historical worktree-local key location.
    (secrets_root / "live-stand-owner.key").write_bytes(b"d" * 32)

    project_name = f"ue-live-{uuid.uuid4().hex[:16]}"
    ports = {
        name: 32000 + index
        for index, (name, _service, _container_port) in enumerate(
            live_stand.LIVE_PORT_SPECS
        )
    }
    payload: dict[str, object] = {
        "version": live_stand.OWNER_SCHEMA_VERSION,
        "repository": str(repository.resolve()),
        "worktree": str(worktree.resolve()),
        "project_name": project_name,
        "published_ports": ports,
        "daemon_fingerprint": "d" * 64,
        "compose_resource_fingerprint": "f" * 64,
        "resume_compose_resource_fingerprint": None,
        "resume_compose_resource_schema_version": None,
        "stack": live_stand.LIVE_STACK_CORE,
        "service_roots": list(live_stand.LIVE_CORE_SERVICE_ROOTS),
        "selected_services": list(live_stand.LIVE_CORE_EXPECTED_SERVICES),
    }
    signature = live_stand._owner_signature(payload, key)
    if tamper_signature:
        payload["daemon_fingerprint"] = "e" * 64
    marker = {**payload, "signature": signature}
    (secrets_root / "live-stand.json").write_text(
        json.dumps(marker, indent=2) + "\n", encoding="utf-8"
    )
    return repository, worktree, project_name


def _in_place_fixture(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[Path, str, str]:
    temporary_root = tmp_path / "temp"
    state_parent = temporary_root / "ue-live-acceptance"
    state_parent.mkdir(parents=True)
    state_root = state_parent / f"run-{uuid.uuid4().hex}"
    source_sha = "a" * 40

    monkeypatch.setenv("TEMP", str(temporary_root))
    monkeypatch.setenv("TMP", str(temporary_root))
    if os.name != "nt":
        monkeypatch.setenv("TMPDIR", str(temporary_root))
    monkeypatch.setattr(live_stand, "REPO_ROOT", ROOT.resolve())
    monkeypatch.setattr(live_stand, "WORKTREE", state_root)
    monkeypatch.setattr(live_stand, "IN_PLACE_MODE", True)
    monkeypatch.setattr(live_stand, "SOURCE_SHA", source_sha)
    monkeypatch.setattr(live_stand, "docker_daemon_fingerprint", lambda: "d" * 64)

    live_stand._ensure_private_state_directory(state_root, protect_new_windows=True)
    published_ports = {
        name: 32000 + index
        for index, (name, _service, _container_port) in enumerate(
            live_stand.LIVE_PORT_SPECS
        )
    }
    owner = live_stand.create_stand_owner(
        state_root,
        published_ports=published_ports,
        stack=live_stand.LIVE_STACK_FULL,
    )
    compose_override = state_root / live_stand.IN_PLACE_OVERLAY
    compose_override.write_text("services: {}\n", encoding="utf-8")
    if os.name == "nt":
        live_stand._restrict_in_place_windows_state_file(compose_override)
    else:
        compose_override.chmod(0o600)
    assert owner.schema_version == live_stand.IN_PLACE_OWNER_SCHEMA_VERSION
    return state_root, owner.project_name, source_sha


@pytest.mark.skipif(
    POWERSHELL is None or GIT is None,
    reason="PowerShell 7 and Git are required for owner verification contracts",
)
def test_worktree_owner_uses_common_git_key_and_ignores_worktree_decoy(
    tmp_path: Path,
) -> None:
    _repository, worktree, project_name = _non_in_place_fixture(tmp_path)

    result = _run_powershell_owner_check(
        tmp_path,
        mode="worktree",
        project_root=worktree,
        project_name=project_name,
    )

    assert result == {
        "accepted": True,
        "version": live_stand.OWNER_SCHEMA_VERSION,
        "sameResolvedOwner": False,
        "resolvedPathMatches": False,
        "gitLookups": 1,
        "failure": "",
        "stage": "complete",
        "errorType": "",
    }


@pytest.mark.skipif(
    POWERSHELL is None or GIT is None,
    reason="PowerShell 7 and Git are required for owner verification contracts",
)
def test_worktree_owner_fails_closed_when_shared_key_is_missing_even_with_decoy(
    tmp_path: Path,
) -> None:
    repository, worktree, project_name = _non_in_place_fixture(tmp_path)
    reported_common = _git("rev-parse", "--git-common-dir", cwd=worktree)
    reported_path = Path(reported_common)
    common_directory = (
        reported_path if reported_path.is_absolute() else worktree / reported_path
    ).resolve()
    (common_directory / "live-stand-owner.key").unlink()

    result = _run_powershell_owner_check(
        tmp_path,
        mode="worktree",
        project_root=worktree,
        project_name=project_name,
    )

    assert result["accepted"] is False
    assert result["failure"] == "signed_owner_material_missing"
    assert result["gitLookups"] == 1
    assert (worktree / ".secrets" / "live-stand-owner.key").is_file()
    assert repository.is_dir()


@pytest.mark.skipif(
    POWERSHELL is None or GIT is None,
    reason="PowerShell 7 and Git are required for owner verification contracts",
)
def test_worktree_owner_rejects_signature_tampering(
    tmp_path: Path,
) -> None:
    _repository, worktree, project_name = _non_in_place_fixture(
        tmp_path, tamper_signature=True
    )

    result = _run_powershell_owner_check(
        tmp_path,
        mode="worktree",
        project_root=worktree,
        project_name=project_name,
    )

    assert result["accepted"] is False
    assert result["failure"] == "signature_invalid"
    assert result["stage"] == "worktree_owner_verification"
    assert result["gitLookups"] == 1


@pytest.mark.skipif(
    POWERSHELL is None,
    reason="PowerShell 7 is required for Git metadata failure contracts",
)
def test_worktree_owner_rejects_missing_git_common_metadata(
    tmp_path: Path,
) -> None:
    project_root = tmp_path / "not-a-git-checkout"
    project_root.mkdir()
    project_name = "ue-live-0123456789abcdef"
    result = _run_powershell_owner_check(
        tmp_path,
        mode="worktree",
        project_root=project_root,
        project_name=project_name,
    )

    assert result["accepted"] is False
    assert result["failure"] == "git_metadata_invalid"
    assert result["gitLookups"] == 1


@pytest.mark.skipif(
    POWERSHELL is None,
    reason="PowerShell 7 is required for in-place owner cache contracts",
)
def test_in_place_resolver_caches_valid_v9_owner_without_git_lookup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state_root, project_name, source_sha = _in_place_fixture(tmp_path, monkeypatch)

    result = _run_powershell_owner_check(
        tmp_path,
        mode="inplace",
        project_root=ROOT,
        project_name=project_name,
        state_root=state_root,
        source_sha=source_sha,
    )

    assert result == {
        "accepted": True,
        "version": live_stand.IN_PLACE_OWNER_SCHEMA_VERSION,
        "sameResolvedOwner": True,
        "resolvedPathMatches": True,
        "gitLookups": 0,
        "failure": "",
        "stage": "complete",
        "errorType": "",
    }, f"sanitized owner-resolution result: {result}"
