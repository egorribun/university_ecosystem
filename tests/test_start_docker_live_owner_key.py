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
    [string]$SourceSha = "",
    [ValidateSet("0", "1")][string]$AllowUnbound = "0",
    [ValidateSet("0", "1")][string]$CheckTenant = "0"
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
    "Test-ExactLiveOwnerFields",
    "Test-CanonicalLivePublishedPorts",
    "Get-CommonGitOwnerKeyPath",
    "Get-VerifiedLiveAcceptanceOwner"
)
if ($Mode -ceq "inplace") {
    $functionNames += @("Assert-LiveStandPrivatePath", "Resolve-OwnedLiveStandStateRoot")
}
if ($CheckTenant -ceq "1") {
    $functionNames += "Ensure-OwnedLiveTenantEnvironment"
}
foreach ($name in $functionNames) {
    Invoke-Expression (Get-UniqueFunctionText $name)
}
foreach ($name in @('$script:LiveAcceptanceCoreRoots', '$script:LiveAcceptanceCoreClosure')) {
    $assignments = @($sourceAst.FindAll({
        param($node)
        $node -is [System.Management.Automation.Language.AssignmentStatementAst] -and
            $node.Left.Extent.Text -ceq $name
    }, $true))
    if ($assignments.Count -ne 1) { throw "owner_constant_binding_failed" }
    Invoke-Expression $assignments[0].Extent.Text
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
    if ($CheckTenant -ceq "1") {
        $stage = "tenant_owner_verification"
        $ExtraCompose = @("docker-compose.live.yml")
        $PrepareOnly = $AllowUnbound -ceq "1"
        $EnvFile = Join-Path $ProjectRoot ".env.docker"
        $EnvCompose = Join-Path $ProjectRoot ".env"
        [System.IO.File]::WriteAllText($EnvFile, "")
        [System.IO.File]::WriteAllText($EnvCompose, "")
        $env:MVP_TENANT_ID = "fixture-tenant"
        function Get-OwnedSeedTenantId { return "fixture-tenant" }
        function Resolve-StatePath([string]$Path) { return $Path }
        function Get-EnvEntry([string]$Path, [string]$Key) { return $null }
        function Set-EnvEntry([string]$Path, [string]$Key, [string]$Value) {
            Add-Content -LiteralPath $Path -Value "$Key=$Value"
        }
        Ensure-OwnedLiveTenantEnvironment
        $result = [pscustomobject]@{
            accepted = $true
            version = 0
            sameResolvedOwner = $null -ne $script:LiveStandOwner
            resolvedPathMatches = $false
            gitLookups = $script:gitLookupCount
            failure = ""
            stage = "complete"
            errorType = ""
        }
    } elseif ($Mode -ceq "inplace") {
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
        $owner = if ($AllowUnbound -ceq "1") {
            Get-VerifiedLiveAcceptanceOwner -AllowUnboundResources
        } else {
            Get-VerifiedLiveAcceptanceOwner
        }
        $result = [pscustomobject]@{
            accepted = $true
            version = [int]$owner.version
            # With the PrepareOnly switch this reports whether the owner was cached.
            sameResolvedOwner = ($AllowUnbound -ceq "1") -and
                [object]::ReferenceEquals($owner, $script:LiveStandOwner)
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
    } elseif ($message -ceq "Live acceptance owner does not match this worktree and Compose project.") {
        $failure = "worktree_owner_mismatch"
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
    allow_unbound: bool = False,
    check_tenant: bool = False,
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
        "-AllowUnbound",
        "1" if allow_unbound else "0",
        "-CheckTenant",
        "1" if check_tenant else "0",
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
    schema_version: int = live_stand.OWNER_SCHEMA_VERSION,
    compose_resource_fingerprint: str | None = "f" * 64,
    stack: str = live_stand.LIVE_STACK_CORE,
    owner_overrides: dict[str, object] | None = None,
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
    if schema_version == live_stand.PRE_MINIO_OWNER_SCHEMA_VERSION:
        ports.pop("MINIO")
    payload: dict[str, object] = {
        "version": schema_version,
        "repository": str(repository.resolve()),
        "worktree": str(worktree.resolve()),
        "project_name": project_name,
        "published_ports": ports,
        "daemon_fingerprint": "d" * 64,
        "compose_resource_fingerprint": compose_resource_fingerprint,
        "resume_compose_resource_fingerprint": None,
        "resume_compose_resource_schema_version": None,
        "stack": stack,
        "service_roots": (
            list(live_stand.LIVE_CORE_SERVICE_ROOTS)
            if stack == live_stand.LIVE_STACK_CORE
            else (["backend"] if compose_resource_fingerprint is not None else [])
        ),
        "selected_services": (
            (
                list(live_stand.LIVE_CORE_EXPECTED_SERVICES)
                if stack == live_stand.LIVE_STACK_CORE
                else ["backend"]
            )
            if compose_resource_fingerprint is not None
            else []
        ),
    }
    if owner_overrides is not None:
        payload.update(owner_overrides)
    signature = live_stand._owner_signature(payload, key)
    if tamper_signature:
        payload["daemon_fingerprint"] = "e" * 64
    marker = {**payload, "signature": signature}
    (secrets_root / "live-stand.json").write_text(
        json.dumps(marker, indent=2) + "\n", encoding="utf-8"
    )
    return repository, worktree, project_name


def _in_place_fixture(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    schema_version: int = live_stand.IN_PLACE_OWNER_SCHEMA_VERSION,
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
    if schema_version == live_stand.PRE_MINIO_IN_PLACE_OWNER_SCHEMA_VERSION:
        marker_path = state_root / live_stand.STAND_FILE
        marker = json.loads(marker_path.read_text(encoding="utf-8"))
        marker["version"] = schema_version
        marker["published_ports"].pop("MINIO")
        payload = {name: value for name, value in marker.items() if name != "signature"}
        key = (state_root / ".secrets" / "live-stand-owner.key").read_bytes()
        marker["signature"] = live_stand._owner_signature(payload, key)
        marker_path.write_text(json.dumps(marker, indent=2) + "\n", encoding="utf-8")
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
def test_worktree_owner_rejects_signed_pre_minio_v8_owner(
    tmp_path: Path,
) -> None:
    _repository, worktree, project_name = _non_in_place_fixture(
        tmp_path, schema_version=live_stand.PRE_MINIO_OWNER_SCHEMA_VERSION
    )

    result = _run_powershell_owner_check(
        tmp_path,
        mode="worktree",
        project_root=worktree,
        project_name=project_name,
    )

    assert result["accepted"] is False
    assert result["stage"] == "worktree_owner_verification"
    assert result["gitLookups"] == 1


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
def test_in_place_resolver_caches_valid_v11_owner_without_git_lookup(
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


@pytest.mark.skipif(
    POWERSHELL is None,
    reason="PowerShell 7 is required for in-place owner cache contracts",
)
def test_in_place_resolver_rejects_signed_pre_minio_v9_owner(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state_root, project_name, source_sha = _in_place_fixture(
        tmp_path,
        monkeypatch,
        schema_version=live_stand.PRE_MINIO_IN_PLACE_OWNER_SCHEMA_VERSION,
    )

    result = _run_powershell_owner_check(
        tmp_path,
        mode="inplace",
        project_root=ROOT,
        project_name=project_name,
        state_root=state_root,
        source_sha=source_sha,
    )

    assert result["accepted"] is False
    assert result["failure"] == "in_place_owner_mismatch"
    assert result["stage"] == "resolve_in_place_owner"
    assert result["gitLookups"] == 0


_OWNER_CONTRACT_SKIP = pytest.mark.skipif(
    POWERSHELL is None or GIT is None,
    reason="PowerShell 7 and Git are required for owner verification contracts",
)


@_OWNER_CONTRACT_SKIP
@pytest.mark.parametrize(
    "stack", [live_stand.LIVE_STACK_CORE, live_stand.LIVE_STACK_FULL]
)
@pytest.mark.parametrize("resume", [False, True])
def test_prepare_only_accepts_a_signed_owner_before_resource_binding(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    stack: str,
    resume: bool,
) -> None:
    """live_stand.py binds the Compose resource fingerprint after PrepareOnly."""
    overrides = (
        {
            "resume_compose_resource_fingerprint": "a" * 64,
            "resume_compose_resource_schema_version": live_stand.OWNER_SCHEMA_VERSION,
        }
        if resume
        else None
    )
    repository, worktree, project_name = _non_in_place_fixture(
        tmp_path,
        compose_resource_fingerprint=None,
        stack=stack,
        owner_overrides=overrides,
    )
    monkeypatch.setattr(live_stand, "REPO_ROOT", repository)
    monkeypatch.setattr(live_stand, "WORKTREE", worktree)
    monkeypatch.setattr(live_stand, "IN_PLACE_MODE", False)
    owner = live_stand.load_stand_owner(worktree)
    assert owner.compose_resource_fingerprint is None
    assert owner.selected_services == ()

    result = _run_powershell_owner_check(
        tmp_path,
        mode="worktree",
        project_root=worktree,
        project_name=project_name,
        allow_unbound=True,
    )

    assert result["accepted"] is True
    assert result["version"] == live_stand.OWNER_SCHEMA_VERSION
    # An unbound owner is never cached for the later, binding-required callers.
    assert result["sameResolvedOwner"] is False


@_OWNER_CONTRACT_SKIP
@pytest.mark.parametrize(
    ("stack", "overrides"),
    [
        ("core", {"service_roots": ["backend"]}),
        ("core", {"selected_services": ["backend"]}),
        ("full", {"service_roots": ["backend"]}),
        ("full", {"selected_services": ["backend"]}),
        ("core", {"resume_compose_resource_fingerprint": "a" * 64}),
        ("core", {"resume_compose_resource_schema_version": 10}),
        (
            "core",
            {
                "resume_compose_resource_fingerprint": "a" * 64,
                "resume_compose_resource_schema_version": 99,
            },
        ),
    ],
)
def test_prepare_only_rejects_inconsistent_signed_reservations(
    tmp_path: Path, stack: str, overrides: dict[str, object]
) -> None:
    _repository, worktree, project_name = _non_in_place_fixture(
        tmp_path,
        compose_resource_fingerprint=None,
        stack=stack,
        owner_overrides=overrides,
    )

    result = _run_powershell_owner_check(
        tmp_path,
        mode="worktree",
        project_root=worktree,
        project_name=project_name,
        allow_unbound=True,
    )

    assert result["accepted"] is False


@_OWNER_CONTRACT_SKIP
@pytest.mark.parametrize(
    ("stack", "overrides"),
    [
        ("core", {"version": 10.0}),
        ("core", {"daemon_fingerprint": "invalid"}),
        ("core", {"service_roots": ["backend"]}),
        ("core", {"selected_services": ["backend"]}),
        ("full", {"selected_services": ["caddy"]}),
        (
            "core",
            {
                "resume_compose_resource_fingerprint": "a" * 64,
                "resume_compose_resource_schema_version": 10,
            },
        ),
    ],
)
def test_bound_owner_rejects_inconsistent_signed_metadata(
    tmp_path: Path, stack: str, overrides: dict[str, object]
) -> None:
    _repository, worktree, project_name = _non_in_place_fixture(
        tmp_path, stack=stack, owner_overrides=overrides
    )

    result = _run_powershell_owner_check(
        tmp_path,
        mode="worktree",
        project_root=worktree,
        project_name=project_name,
    )

    assert result["accepted"] is False
    assert result["failure"] == "worktree_owner_mismatch"


@_OWNER_CONTRACT_SKIP
def test_unbound_owner_is_rejected_outside_prepare_only(tmp_path: Path) -> None:
    _repository, worktree, project_name = _non_in_place_fixture(
        tmp_path, compose_resource_fingerprint=None
    )

    result = _run_powershell_owner_check(
        tmp_path,
        mode="worktree",
        project_root=worktree,
        project_name=project_name,
    )

    assert result["accepted"] is False
    assert result["failure"] == "worktree_owner_mismatch"


@_OWNER_CONTRACT_SKIP
def test_prepare_only_switch_still_caches_a_bound_owner(tmp_path: Path) -> None:
    _repository, worktree, project_name = _non_in_place_fixture(tmp_path)

    result = _run_powershell_owner_check(
        tmp_path,
        mode="worktree",
        project_root=worktree,
        project_name=project_name,
        allow_unbound=True,
    )

    assert result["accepted"] is True
    assert result["sameResolvedOwner"] is True


@_OWNER_CONTRACT_SKIP
@pytest.mark.parametrize("fingerprint", ["", "F" * 64, "f" * 63])
def test_prepare_only_switch_still_rejects_a_malformed_fingerprint(
    tmp_path: Path, fingerprint: str
) -> None:
    _repository, worktree, project_name = _non_in_place_fixture(
        tmp_path, compose_resource_fingerprint=fingerprint
    )

    result = _run_powershell_owner_check(
        tmp_path,
        mode="worktree",
        project_root=worktree,
        project_name=project_name,
        allow_unbound=True,
    )

    assert result["accepted"] is False
    assert result["failure"] == "worktree_owner_mismatch"


@_OWNER_CONTRACT_SKIP
def test_prepare_only_switch_still_verifies_the_signature(tmp_path: Path) -> None:
    _repository, worktree, project_name = _non_in_place_fixture(
        tmp_path, compose_resource_fingerprint=None, tamper_signature=True
    )

    result = _run_powershell_owner_check(
        tmp_path,
        mode="worktree",
        project_root=worktree,
        project_name=project_name,
        allow_unbound=True,
    )

    assert result["accepted"] is False
    assert result["failure"] == "signature_invalid"


@_OWNER_CONTRACT_SKIP
@pytest.mark.parametrize(
    ("fingerprint", "prepare", "accepted", "cached"),
    [
        (None, True, True, False),
        (None, False, False, False),
        ("f" * 64, False, True, True),
    ],
)
def test_tenant_initialization_verifies_the_owner_for_the_current_phase(
    tmp_path: Path,
    fingerprint: str | None,
    prepare: bool,
    accepted: bool,
    cached: bool,
) -> None:
    _repository, worktree, project_name = _non_in_place_fixture(
        tmp_path, compose_resource_fingerprint=fingerprint
    )

    result = _run_powershell_owner_check(
        tmp_path,
        mode="worktree",
        project_root=worktree,
        project_name=project_name,
        allow_unbound=prepare,
        check_tenant=True,
    )

    assert result["accepted"] is accepted
    assert result["sameResolvedOwner"] is cached


@_OWNER_CONTRACT_SKIP
@pytest.mark.parametrize(
    "stack", [live_stand.LIVE_STACK_CORE, live_stand.LIVE_STACK_FULL]
)
def test_worktree_prepare_only_accepts_python_created_reservation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stack: str
) -> None:
    """Exercise the full launcher with Python's real incomplete owner marker."""
    from tests.test_start_docker_live_stand_state_root import _fixture_project

    fixture_dir = tmp_path / "launcher-fixture"
    fixture_dir.mkdir()
    source, _ = _fixture_project(fixture_dir)
    repository, worktree, _ = _non_in_place_fixture(tmp_path)
    shutil.copytree(source, worktree, dirs_exist_ok=True)
    for relative in (
        "scripts/temporal/bootstrap-functions.ps1",
        "scripts/temporal/namespace-init.sh",
    ):
        target = worktree / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / relative, target)

    (worktree / ".secrets" / "live-stand.json").unlink()
    monkeypatch.setattr(live_stand, "REPO_ROOT", repository)
    monkeypatch.setattr(live_stand, "WORKTREE", worktree)
    monkeypatch.setattr(live_stand, "IN_PLACE_MODE", False)
    monkeypatch.setattr(live_stand, "docker_daemon_fingerprint", lambda: "d" * 64)
    monkeypatch.delenv("MVP_TENANT_ID", raising=False)
    ports = {
        name: 32000 + index
        for index, (name, _service, _container_port) in enumerate(
            live_stand.LIVE_PORT_SPECS
        )
    }
    owner = live_stand.create_stand_owner(worktree, published_ports=ports, stack=stack)
    vapid = live_stand.load_or_create_vapid(worktree)
    environment = live_stand.stand_environment(vapid, owner.project_name, ports)
    environment["XDG_CACHE_HOME"] = str(tmp_path / "powershell-cache")

    # PrepareOnly must never invoke Docker; put a sentinel ahead of the host CLI.
    shim_dir = tmp_path / "docker-shim"
    shim_dir.mkdir()
    sentinel = shim_dir / "unexpected-call"
    if os.name == "nt":
        shim = shim_dir / "docker.cmd"
        shim.write_text(
            '@echo off\r\necho called > "%DOCKER_SENTINEL%"\r\nexit /b 91\r\n'
        )
    else:
        shim = shim_dir / "docker"
        shim.write_text('#!/bin/sh\necho called > "$DOCKER_SENTINEL"\nexit 91\n')
        shim.chmod(0o755)
    environment["DOCKER_SENTINEL"] = str(sentinel)
    environment["PATH"] = str(shim_dir) + os.pathsep + environment.get("PATH", "")
    assert POWERSHELL is not None
    result = subprocess.run(  # noqa: S603 - fixed launcher in a pytest-owned worktree
        [
            POWERSHELL,
            "-NoProfile",
            "-NonInteractive",
            "-File",
            str(worktree / "start-docker.ps1"),
            "-PrepareOnly",
            "-InitializeTrustedProxyBootstrap",
            "-ExtraCompose",
            "docker-compose.live.yml",
        ],
        cwd=worktree,
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
        timeout=40,
    )

    assert result.returncode == 0, f"PrepareOnly exited with status {result.returncode}"
    assert not sentinel.exists()
    assert (worktree / ".env").is_file()
    assert (worktree / ".env.docker").is_file()
    assert (worktree / ".env.docker.workers").is_file()
