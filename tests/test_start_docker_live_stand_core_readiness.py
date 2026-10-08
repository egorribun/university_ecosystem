"""Behavioral contracts for the PowerShell live-stand readiness selection."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = ROOT / "start-docker.ps1"
POWERSHELL = shutil.which("pwsh")

CORE_ROOTS = (
    "caddy",
    "mailpit",
    "notifications-worker",
    "outbox-worker",
    "spicedb",
)
CORE_SERVICES = (
    "backend",
    "caddy",
    "flagd",
    "flagd-healthprobe",
    "frontend",
    "gateway",
    "imgproxy",
    "mailpit",
    "migrations",
    "minio",
    "minio-init",
    "nats",
    "notifications-worker",
    "outbox-worker",
    "postgres",
    "postgres-databases-init",
    "redis",
    "revocation-redis",
    "spicedb",
    "spicedb-migrate",
    "tempo",
    "tempo-healthprobe",
    "ws-hub",
)

FULL_READINESS_KEYS = (
    "alloy",
    "backend",
    "caddy",
    "elasticsearch",
    "fileprocessor",
    "flagd",
    "frontend",
    "gateway",
    "grafana",
    "imgproxy",
    "loki",
    "minio",
    "nats",
    "notifications",
    "outbox",
    "postgres",
    "prometheus",
    "pyroscope",
    "redis",
    "redisexporter",
    "site",
    "spicedb",
    "temporal",
    "tempo",
    "wshub",
)

FULL_READINESS_SERVICES = (
    "alloy",
    "backend",
    "caddy",
    "caddy",
    "elasticsearch",
    "file-processor",
    "flagd-healthprobe",
    "frontend",
    "gateway",
    "grafana",
    "imgproxy",
    "loki-healthprobe",
    "minio",
    "nats",
    "notifications-worker",
    "outbox-worker",
    "postgres",
    "prometheus",
    "pyroscope",
    "redis",
    "redis-exporter",
    "spicedb",
    "temporal",
    "tempo-healthprobe",
    "ws-hub",
)

LEGACY_CORE_KEYS = (
    "backend",
    "caddy",
    "flagd",
    "frontend",
    "gateway",
    "imgproxy",
    "minio",
    "nats",
    "notifications",
    "outbox",
    "postgres",
    "redis",
    "site",
    "spicedb",
    "wshub",
)

LEGACY_CORE_SERVICES = (
    "backend",
    "caddy",
    "caddy",
    "flagd-healthprobe",
    "frontend",
    "gateway",
    "imgproxy",
    "minio",
    "nats",
    "notifications-worker",
    "outbox-worker",
    "postgres",
    "redis",
    "spicedb",
    "ws-hub",
)

_POWERSHELL_RUNNER = r"""
param(
    [Parameter(Mandatory=$true)][string]$SourcePath,
    [Parameter(Mandatory=$true)][string]$ExpectedRootsJson,
    [Parameter(Mandatory=$true)][string]$ExpectedCoreJson
)

$tokens = $null
$parseErrors = $null
$sourceAst = [System.Management.Automation.Language.Parser]::ParseFile(
    $SourcePath, [ref]$tokens, [ref]$parseErrors
)
if ($parseErrors.Count -gt 0) { throw "readiness_source_parse_failed" }

function Get-UniqueFunctionText([string]$Name) {
    $matches = @($sourceAst.FindAll({
        param($node)
        $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and
            $node.Name -ceq $Name
    }, $true))
    if ($matches.Count -ne 1) { throw "readiness_function_binding_failed" }
    return $matches[0].Extent.Text
}

function Get-UniqueAssignment($Name, $AfterOffset = -1) {
    $matches = @($sourceAst.FindAll({
        param($node)
        $node -is [System.Management.Automation.Language.AssignmentStatementAst] -and
            $node.Left -is [System.Management.Automation.Language.VariableExpressionAst] -and
            $node.Left.VariablePath.UserPath -ceq $Name -and
            $node.Extent.StartOffset -gt $AfterOffset
    }, $true) | Sort-Object { $_.Extent.StartOffset })
    if ($matches.Count -ne 1) { throw "readiness_assignment_binding_failed" }
    return $matches[0]
}

function Get-OrderedAssignment($Name, $AfterOffset = -1) {
    $matches = @($sourceAst.FindAll({
        param($node)
        $node -is [System.Management.Automation.Language.AssignmentStatementAst] -and
            $node.Left -is [System.Management.Automation.Language.VariableExpressionAst] -and
            $node.Left.VariablePath.UserPath -ceq $Name -and
            $node.Extent.StartOffset -gt $AfterOffset
    }, $true) | Sort-Object { $_.Extent.StartOffset })
    if ($matches.Count -eq 0) { throw "readiness_assignment_missing" }
    return ,$matches
}

function Get-MapSummary([System.Collections.IDictionary]$Map) {
    $keys = [System.Collections.Generic.List[string]]::new()
    $services = [System.Collections.Generic.List[string]]::new()
    $jobs = [System.Collections.Generic.List[string]]::new()
    foreach ($key in $Map.Keys) {
        $entry = $Map[$key]
        $keys.Add([string]$key)
        $services.Add([string]$entry.service)
        if ([string]$entry.type -ceq "job") { $jobs.Add([string]$entry.service) }
    }
    return [pscustomobject]@{
        keys = @($keys.ToArray())
        services = @($services.ToArray())
        jobs = @($jobs.ToArray())
        probeCount = $keys.Count
    }
}

Invoke-Expression (Get-UniqueFunctionText "Get-LocalServiceUrl")
[Environment]::SetEnvironmentVariable("LIVE_MAILPIT_PORT", "43123", "Process")
[Environment]::SetEnvironmentVariable("LIVE_HOST_PORT_MAILPIT", $null, "Process")
function Write-Status([string]$Message) { }
function Write-Ok([string]$Message) { }
function Write-Err([string]$Message) { }

$expectedRoots = [string[]]@(ConvertFrom-Json -InputObject $ExpectedRootsJson)
$expectedCore = [string[]]@(ConvertFrom-Json -InputObject $ExpectedCoreJson)
$script:LiveAcceptanceCoreRoots = $expectedRoots
$script:LiveAcceptanceCoreClosure = $expectedCore
$script:LiveAcceptanceServices = $expectedCore
$script:LiveAcceptanceCore = $true
$Core = $false

foreach ($functionName in @(
    "Test-CanonicalLiveServiceList",
    "Resolve-LiveAcceptanceSelection",
    "Assert-LiveAcceptanceSelection",
    "Get-LiveAcceptanceCoreReadinessInventory",
    "Get-StartupReadinessInventory"
)) {
    Invoke-Expression (Get-UniqueFunctionText $functionName)
}

$sourceAssignments = $sourceAst.FindAll({
    param($node)
    $node -is [System.Management.Automation.Language.AssignmentStatementAst] -and
        $node.Left -is [System.Management.Automation.Language.VariableExpressionAst] -and
        $node.Left.VariablePath.UserPath -ceq "CoreExcludedHealthServices"
}, $true)
if (@($sourceAssignments).Count -ne 1) { throw "legacy_core_exclusions_binding_failed" }
Invoke-Expression $sourceAssignments[0].Extent.Text

$waiting = $sourceAst.FindAll({
    param($node)
    $node -is [System.Management.Automation.Language.CommandAst] -and
        $node.GetCommandName() -ceq "Write-Status" -and
        $node.Extent.Text.Contains("Waiting for services")
}, $true) | Select-Object -First 1
if ($null -eq $waiting) { throw "health_loop_anchor_missing" }

$fullAssignment = Get-UniqueAssignment "fullReadiness" $waiting.Extent.EndOffset
$serviceAssignments = Get-OrderedAssignment "services" $fullAssignment.Extent.EndOffset
$coreLoopAssignment = $serviceAssignments | Where-Object {
    $_.Extent.Text.Contains("-LiveAcceptanceCore")
} | Select-Object -First 1
$legacyLoopAssignment = $serviceAssignments | Where-Object {
    $_.Extent.Text.Contains("-Core:")
} | Select-Object -First 1
if ($null -eq $coreLoopAssignment -or $null -eq $legacyLoopAssignment) {
    throw "health_loop_assignment_binding_failed"
}

$coreGuard = $sourceAst.FindAll({
    param($node)
    $node -is [System.Management.Automation.Language.IfStatementAst] -and
        $node.Extent.Text.Contains("Live Core readiness inventory does not cover its signed service closure.")
}, $true) | Sort-Object { $_.Extent.Text.Length } -Descending | Select-Object -First 1
if ($null -eq $coreGuard) { throw "core_readiness_guard_missing" }

$coreReadiness = Get-LiveAcceptanceCoreReadinessInventory
$mailpitUrl = [string]$coreReadiness.mailpit.url
Invoke-Expression $coreGuard.Extent.Text
Invoke-Expression $fullAssignment.Extent.Text
$script:LiveAcceptanceCore = $true
$Core = $false
Invoke-Expression $coreLoopAssignment.Extent.Text
$coreSummary = Get-MapSummary $services

Invoke-Expression $fullAssignment.Extent.Text
$script:LiveAcceptanceCore = $false
$Core = $false
Invoke-Expression $legacyLoopAssignment.Extent.Text
$fullSummary = Get-MapSummary $services

Invoke-Expression $fullAssignment.Extent.Text
$Core = $true
Invoke-Expression $legacyLoopAssignment.Extent.Text
$legacyCoreSummary = Get-MapSummary $services

$buildBlock = $sourceAst.FindAll({
    param($node)
    $node -is [System.Management.Automation.Language.IfStatementAst] -and
        $node.Extent.Text.Contains("Building the owner-bound live Core service closure...")
}, $true) | Sort-Object { $_.Extent.Text.Length } -Descending | Select-Object -First 1
$startBlock = $sourceAst.FindAll({
    param($node)
    $node -is [System.Management.Automation.Language.IfStatementAst] -and
        $node.Extent.Text.Contains("Starting the signed live Core roots with normal Compose dependencies...")
}, $true) | Sort-Object { $_.Extent.Text.Length } -Descending | Select-Object -First 1
if ($null -eq $buildBlock -or $null -eq $startBlock) {
    throw "build_or_start_branch_binding_failed"
}

$serviceTable = [ordered]@{}
$nonRoots = @($expectedCore | Where-Object { $_ -cnotin $expectedRoots })
foreach ($service in $expectedCore) {
    $dependencies = if ($service -cin $expectedRoots) { $nonRoots } else { @() }
    $serviceTable[$service] = [pscustomobject]@{ depends_on = $dependencies }
}
$composeModel = [pscustomobject]@{ services = [pscustomobject]$serviceTable }
$wrongSelection = [string[]]@($expectedCore | Where-Object { $_ -cne "spicedb-migrate" })
$LiveStateMode = $false
$ExtraCompose = @("docker-compose.live.yml")
$LiveAcceptanceStack = "core"
$LiveAcceptanceServicesJson = ConvertTo-Json -InputObject $wrongSelection -Compress
$script:LiveAcceptanceCore = $true
$Core = $false
$Build = $true
$Rebuild = $false
$ComposeArgs = @("-f", "docker-compose.live.yml")
$EnvFile = ".env.docker"
$liveAcceptanceServiceArgs = $expectedCore
$liveAcceptanceRootArgs = $expectedRoots
$script:dockerCalls = [System.Collections.Generic.List[string]]::new()
function docker {
    [void]$script:dockerCalls.Add([string]::Join(" ", [string[]]$args))
    $global:LASTEXITCODE = 0
}
$selectionError = $null
try {
    Assert-LiveAcceptanceSelection -ComposeModel $composeModel | Out-Null
    Invoke-Expression $buildBlock.Extent.Text
    Invoke-Expression $startBlock.Extent.Text
} catch {
    $selectionError = [string]$_.Exception.Message
}

if ($selectionError -cne "Caller live service selection differs from resolved Compose closure.") {
    throw "selection_mismatch_contract_failed"
}
if ($script:dockerCalls.Count -ne 0) { throw "selection_mismatch_reached_build_or_up" }

$result = [pscustomobject]@{
    core = $coreSummary
    mailpitUrl = $mailpitUrl
    full = $fullSummary
    legacyCore = $legacyCoreSummary
    mismatchMessage = $selectionError
    dockerCalls = $script:dockerCalls.Count
}
ConvertTo-Json -InputObject $result -Depth 6 -Compress
"""


def _run_powershell_readiness_contract(tmp_path: Path) -> dict[str, object]:
    assert POWERSHELL is not None
    runner = tmp_path / "readiness-contract.ps1"
    runner.write_text(_POWERSHELL_RUNNER, encoding="utf-8")
    result = subprocess.run(  # noqa: S603 - fixed pwsh executable and test-owned files
        [
            POWERSHELL,
            "-NoProfile",
            "-NonInteractive",
            "-File",
            str(runner),
            "-SourcePath",
            str(LAUNCHER),
            "-ExpectedRootsJson",
            json.dumps(CORE_ROOTS),
            "-ExpectedCoreJson",
            json.dumps(CORE_SERVICES),
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=20,
    )
    assert result.returncode == 0, "powershell_live_readiness_contract_failed"
    return json.loads(result.stdout)


@pytest.mark.skipif(POWERSHELL is None, reason="PowerShell 7 (pwsh) is unavailable")
def test_live_readiness_loop_uses_core_and_preserves_full_inventories(
    tmp_path: Path,
) -> None:
    result = _run_powershell_readiness_contract(tmp_path)

    core = result["core"]
    assert isinstance(core, dict)
    assert sorted(set(core["services"])) == list(CORE_SERVICES)
    assert core["probeCount"] == 24
    assert core["services"].count("caddy") == 2
    assert sorted(core["jobs"]) == [
        "migrations",
        "minio-init",
        "postgres-databases-init",
        "spicedb-migrate",
    ]
    assert result["mailpitUrl"] == "http://localhost:43123/api/v1/info"

    full = result["full"]
    assert isinstance(full, dict)
    assert sorted(full["keys"]) == sorted(FULL_READINESS_KEYS)
    assert sorted(full["services"]) == sorted(FULL_READINESS_SERVICES)

    legacy_core = result["legacyCore"]
    assert isinstance(legacy_core, dict)
    assert sorted(legacy_core["keys"]) == sorted(LEGACY_CORE_KEYS)
    assert sorted(legacy_core["services"]) == sorted(LEGACY_CORE_SERVICES)


@pytest.mark.skipif(POWERSHELL is None, reason="PowerShell 7 (pwsh) is unavailable")
def test_live_selection_mismatch_fails_before_build_or_up(tmp_path: Path) -> None:
    result = _run_powershell_readiness_contract(tmp_path)

    assert result["mismatchMessage"] == (
        "Caller live service selection differs from resolved Compose closure."
    )
    assert result["dockerCalls"] == 0
