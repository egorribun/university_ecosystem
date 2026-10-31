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

_TRUSTED_PROXY_POWERSHELL_RUNNER = r"""
param(
    [Parameter(Mandatory=$true)][string]$SourcePath,
    [Parameter(Mandatory=$true)][string]$EnvPath
)
$tokens = $null
$parseErrors = $null
$sourceAst = [System.Management.Automation.Language.Parser]::ParseFile(
    $SourcePath, [ref]$tokens, [ref]$parseErrors
)
if ($parseErrors.Count -gt 0) { throw "trusted_proxy_source_parse_failed" }
function Get-UniqueFunctionText([string]$Name) {
    $matches = @($sourceAst.FindAll({
        param($node)
        $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and
            $node.Name -ceq $Name
    }, $true))
    if ($matches.Count -ne 1) { throw "trusted_proxy_function_binding_failed" }
    return $matches[0].Extent.Text
}
function Resolve-StatePath {
    param([Parameter(Mandatory=$true)][string]$Path)
    if ([System.IO.Path]::IsPathRooted($Path)) {
        return [System.IO.Path]::GetFullPath($Path)
    }
    return [System.IO.Path]::GetFullPath((Join-Path $StateRoot $Path))
}
function Write-Utf8NoBom {
    param([string]$Path, [string]$Content)
    $absolutePath = Resolve-StatePath -Path $Path
    [System.IO.File]::WriteAllText(
        $absolutePath,
        $Content,
        [System.Text.UTF8Encoding]::new($false)
    )
}
Invoke-Expression (Get-UniqueFunctionText "Set-EnvEntry")
Invoke-Expression (Get-UniqueFunctionText "Set-LiveTrustedProxyEnvironment")
Invoke-Expression (Get-UniqueFunctionText "ConvertFrom-TrustedProxyPeers")
Invoke-Expression (Get-UniqueFunctionText "Resolve-TrustedProxyRefreshServices")
$StateRoot = [System.IO.Path]::GetDirectoryName([System.IO.Path]::GetFullPath($EnvPath))
$EnvFile = ".env.docker"
$bootstrap = ConvertFrom-TrustedProxyPeers -Stage bootstrap -Json '{"GATEWAY_TRUSTED_PROXIES":[],"TRUSTED_PROXIES":[],"WS_HUB_TRUSTED_PROXIES":[]}'
Set-LiveTrustedProxyEnvironment -Settings $bootstrap
$writtenProxyLines = @(Get-Content -LiteralPath $EnvPath | Where-Object {
    $_ -match '^(TRUSTED_PROXIES|GATEWAY_TRUSTED_PROXIES|WS_HUB_TRUSTED_PROXIES)='
})
$rejectedProxyWithoutFlag = $false
try {
    Set-EnvEntry -Path $EnvFile -Key "TRUSTED_PROXIES" -Value ""
} catch { $rejectedProxyWithoutFlag = $true }
$rejectedUnrelatedEmpty = $false
try {
    Set-EnvEntry -Path $EnvFile -Key "UNRELATED_SETTING" -Value "" -AllowEmptyTrustedProxyValue
} catch { $rejectedUnrelatedEmpty = $true }
$unrelatedLine = @(Get-Content -LiteralPath $EnvPath | Where-Object {
    $_.StartsWith("UNRELATED_SETTING=", [StringComparison]::Ordinal)
})
$edgeJson = '{"GATEWAY_TRUSTED_PROXIES":["172.28.0.2"],"TRUSTED_PROXIES":[],"WS_HUB_TRUSTED_PROXIES":["172.28.0.2"]}'
$edge = ConvertFrom-TrustedProxyPeers -Stage edge -Json $edgeJson
$ipv6Json = '{"GATEWAY_TRUSTED_PROXIES":["fd00::2"],"TRUSTED_PROXIES":[],"WS_HUB_TRUSTED_PROXIES":["fd00::2"]}'
$ipv6 = ConvertFrom-TrustedProxyPeers -Stage edge -Json $ipv6Json
$rejectedIPv6Any = $false
try {
    ConvertFrom-TrustedProxyPeers -Stage edge -Json '{"GATEWAY_TRUSTED_PROXIES":["::"],"TRUSTED_PROXIES":[],"WS_HUB_TRUSTED_PROXIES":["::"]}' | Out-Null
} catch { $rejectedIPv6Any = $true }
$rejectedIPv6Loopback = $false
try {
    ConvertFrom-TrustedProxyPeers -Stage edge -Json '{"GATEWAY_TRUSTED_PROXIES":["::1"],"TRUSTED_PROXIES":[],"WS_HUB_TRUSTED_PROXIES":["::1"]}' | Out-Null
} catch { $rejectedIPv6Loopback = $true }
$backendJson = '{"GATEWAY_TRUSTED_PROXIES":["172.28.0.2"],"TRUSTED_PROXIES":["172.28.0.2","172.29.0.4"],"WS_HUB_TRUSTED_PROXIES":["172.28.0.2"]}'
$backend = ConvertFrom-TrustedProxyPeers -Stage backend -Json $backendJson
$rejectedCidr = $false
try {
    ConvertFrom-TrustedProxyPeers -Stage edge -Json '{"GATEWAY_TRUSTED_PROXIES":["172.28.0.0/24"],"TRUSTED_PROXIES":[],"WS_HUB_TRUSTED_PROXIES":["172.28.0.0/24"]}' | Out-Null
} catch { $rejectedCidr = $true }
$rejectedPublic = $false
try {
    ConvertFrom-TrustedProxyPeers -Stage edge -Json '{"GATEWAY_TRUSTED_PROXIES":["8.8.8.8"],"TRUSTED_PROXIES":[],"WS_HUB_TRUSTED_PROXIES":["8.8.8.8"]}' | Out-Null
} catch { $rejectedPublic = $true }
$rejectedExtraKey = $false
try {
    ConvertFrom-TrustedProxyPeers -Stage edge -Json '{"GATEWAY_TRUSTED_PROXIES":["172.28.0.2"],"TRUSTED_PROXIES":[],"WS_HUB_TRUSTED_PROXIES":["172.28.0.2"],"unexpected":[]}' | Out-Null
} catch { $rejectedExtraKey = $true }
$rejectedEmptyBackend = $false
try {
    ConvertFrom-TrustedProxyPeers -Stage backend -Json $edgeJson | Out-Null
} catch { $rejectedEmptyBackend = $true }
$selected = [string[]]@("backend", "caddy", "gateway", "ws-hub", "postgres")
$edgeServices = Resolve-TrustedProxyRefreshServices -Stage edge -SelectedServices $selected
$backendServices = Resolve-TrustedProxyRefreshServices -Stage backend -SelectedServices $selected
$rejectedMissingPeer = $false
try {
    Resolve-TrustedProxyRefreshServices -Stage edge -SelectedServices @("backend", "gateway", "ws-hub") | Out-Null
} catch { $rejectedMissingPeer = $true }
$result = [pscustomobject]@{
    bootstrapEmpty = @($bootstrap.Values | Where-Object { $_.Length -gt 0 }).Count -eq 0
    emptyProxyLinesWritten = $writtenProxyLines.Count -eq 3 -and @($writtenProxyLines | Where-Object { $_ -notmatch "=$" }).Count -eq 0
    proxyEmptyRequiresOptIn = $rejectedProxyWithoutFlag
    unrelatedEmptyRejected = $rejectedUnrelatedEmpty
    unrelatedValuePreserved = $unrelatedLine.Count -eq 1 -and $unrelatedLine[0] -ceq "UNRELATED_SETTING=preserved"
    edgeGateway = [string]$edge["GATEWAY_TRUSTED_PROXIES"]
    ipv6Gateway = [string]$ipv6["GATEWAY_TRUSTED_PROXIES"]
    rejectedIPv6Any = $rejectedIPv6Any
    rejectedIPv6Loopback = $rejectedIPv6Loopback
    edgeBackendEmpty = [string]$edge["TRUSTED_PROXIES"] -ceq ""
    backendPeers = [string]$backend["TRUSTED_PROXIES"]
    edgeServices = @($edgeServices)
    backendServices = @($backendServices)
    rejectedCidr = $rejectedCidr
    rejectedPublic = $rejectedPublic
    rejectedExtraKey = $rejectedExtraKey
    rejectedEmptyBackend = $rejectedEmptyBackend
    rejectedMissingPeer = $rejectedMissingPeer
}
ConvertTo-Json -InputObject $result -Depth 4 -Compress
"""


_READINESS_STAGE_PREFIX = "CONTRACT_STAGE:"
_READINESS_TIMEOUT_SCAN_LIMIT = 4096
_READINESS_TIMEOUT_PHASES = frozenset(
    {
        "source-parse",
        "function-search",
        "source-function-loading",
        "core-exclusions",
        "waiting-anchor",
        "readiness-binding",
        "core-guard",
        "core-inventory",
        "core-loop",
        "full-loop",
        "legacy-core-loop",
        "build-start-binding",
        "selection-guard",
        "serialize-result",
    }
)


def _last_readiness_timeout_phase(stderr: bytes | bytearray | str | None) -> str:
    if isinstance(stderr, (bytes, bytearray)):
        tail = bytes(stderr[-_READINESS_TIMEOUT_SCAN_LIMIT:]).decode(
            "ascii", errors="replace"
        )
    elif isinstance(stderr, str):
        tail = stderr[-_READINESS_TIMEOUT_SCAN_LIMIT:]
    else:
        return "unknown"

    for line in reversed(tail.splitlines()):
        if not line.startswith(_READINESS_STAGE_PREFIX):
            continue
        phase = line[len(_READINESS_STAGE_PREFIX) :]
        if phase in _READINESS_TIMEOUT_PHASES:
            return phase
    return "unknown"


_POWERSHELL_RUNNER = r"""
param(
    [Parameter(Mandatory=$true)][string]$SourcePath,
    [Parameter(Mandatory=$true)][string]$ExpectedRootsJson,
    [Parameter(Mandatory=$true)][string]$ExpectedCoreJson
)

[Console]::Error.WriteLine("CONTRACT_STAGE:source-parse")
$tokens = $null
$parseErrors = $null
$sourceAst = [System.Management.Automation.Language.Parser]::ParseFile(
    $SourcePath, [ref]$tokens, [ref]$parseErrors
)
if ($parseErrors.Count -gt 0) { throw "readiness_source_parse_failed" }

function Get-UniqueFunctionText([string]$Name) {
    [Console]::Error.WriteLine("CONTRACT_STAGE:function-search")
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

$localServiceUrlText = Get-UniqueFunctionText "Get-LocalServiceUrl"
[Console]::Error.WriteLine("CONTRACT_STAGE:source-function-loading")
Invoke-Expression $localServiceUrlText
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
    $functionText = Get-UniqueFunctionText $functionName
    [Console]::Error.WriteLine("CONTRACT_STAGE:source-function-loading")
    Invoke-Expression $functionText
}

[Console]::Error.WriteLine("CONTRACT_STAGE:core-exclusions")
$sourceAssignments = $sourceAst.FindAll({
    param($node)
    $node -is [System.Management.Automation.Language.AssignmentStatementAst] -and
        $node.Left -is [System.Management.Automation.Language.VariableExpressionAst] -and
        $node.Left.VariablePath.UserPath -ceq "CoreExcludedHealthServices"
}, $true)
if (@($sourceAssignments).Count -ne 1) { throw "legacy_core_exclusions_binding_failed" }
Invoke-Expression $sourceAssignments[0].Extent.Text

[Console]::Error.WriteLine("CONTRACT_STAGE:waiting-anchor")
$waiting = $sourceAst.FindAll({
    param($node)
    $node -is [System.Management.Automation.Language.CommandAst] -and
        $node.GetCommandName() -ceq "Write-Status" -and
        $node.Extent.Text.Contains("Waiting for services")
}, $true) | Select-Object -First 1
if ($null -eq $waiting) { throw "health_loop_anchor_missing" }

[Console]::Error.WriteLine("CONTRACT_STAGE:readiness-binding")
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

[Console]::Error.WriteLine("CONTRACT_STAGE:core-guard")
$coreGuard = $sourceAst.FindAll({
    param($node)
    $node -is [System.Management.Automation.Language.IfStatementAst] -and
        $node.Extent.Text.Contains("Live Core readiness inventory does not cover its signed service closure.")
}, $true) | Sort-Object { $_.Extent.Text.Length } -Descending | Select-Object -First 1
if ($null -eq $coreGuard) { throw "core_readiness_guard_missing" }

[Console]::Error.WriteLine("CONTRACT_STAGE:core-inventory")
$coreReadiness = Get-LiveAcceptanceCoreReadinessInventory
$mailpitUrl = [string]$coreReadiness.mailpit.url
Invoke-Expression $coreGuard.Extent.Text
Invoke-Expression $fullAssignment.Extent.Text
[Console]::Error.WriteLine("CONTRACT_STAGE:core-loop")
$script:LiveAcceptanceCore = $true
$Core = $false
Invoke-Expression $coreLoopAssignment.Extent.Text
$coreSummary = Get-MapSummary $services

Invoke-Expression $fullAssignment.Extent.Text
[Console]::Error.WriteLine("CONTRACT_STAGE:full-loop")
$script:LiveAcceptanceCore = $false
$Core = $false
Invoke-Expression $legacyLoopAssignment.Extent.Text
$fullSummary = Get-MapSummary $services

Invoke-Expression $fullAssignment.Extent.Text
[Console]::Error.WriteLine("CONTRACT_STAGE:legacy-core-loop")
$Core = $true
Invoke-Expression $legacyLoopAssignment.Extent.Text
$legacyCoreSummary = Get-MapSummary $services

[Console]::Error.WriteLine("CONTRACT_STAGE:build-start-binding")
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
[Console]::Error.WriteLine("CONTRACT_STAGE:selection-guard")
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

[Console]::Error.WriteLine("CONTRACT_STAGE:serialize-result")
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


def _run_trusted_proxy_powershell_contract(tmp_path: Path) -> dict[str, object]:
    assert POWERSHELL is not None
    runner = tmp_path / "trusted-proxy-contract.ps1"
    runner.write_text(_TRUSTED_PROXY_POWERSHELL_RUNNER, encoding="utf-8")
    env_path = tmp_path / ".env.docker"
    env_path.write_text(
        "UNRELATED_SETTING=preserved\n"
        "TRUSTED_PROXIES=172.28.0.9\n"
        "GATEWAY_TRUSTED_PROXIES=172.28.0.9\n"
        "WS_HUB_TRUSTED_PROXIES=172.28.0.9\n",
        encoding="utf-8",
    )
    result = subprocess.run(  # noqa: S603 - fixed pwsh executable and test-owned runner
        [
            POWERSHELL,
            "-NoProfile",
            "-NonInteractive",
            "-File",
            str(runner),
            "-SourcePath",
            str(LAUNCHER),
            "-EnvPath",
            str(env_path),
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=20,
    )
    assert result.returncode == 0, "powershell_trusted_proxy_contract_failed"
    return json.loads(result.stdout)


@pytest.mark.skipif(POWERSHELL is None, reason="PowerShell 7 (pwsh) is unavailable")
def test_trusted_proxy_refresh_parser_is_closed_and_services_are_exact(
    tmp_path: Path,
) -> None:
    result = _run_trusted_proxy_powershell_contract(tmp_path)

    assert result["bootstrapEmpty"] is True
    assert result["emptyProxyLinesWritten"] is True
    assert result["proxyEmptyRequiresOptIn"] is True
    assert result["unrelatedEmptyRejected"] is True
    assert result["unrelatedValuePreserved"] is True
    assert result["edgeGateway"] == "172.28.0.2"
    assert result["ipv6Gateway"] == "fd00::2"
    assert result["rejectedIPv6Any"] is True
    assert result["rejectedIPv6Loopback"] is True
    assert result["edgeBackendEmpty"] is True
    assert result["backendPeers"] == "172.28.0.2,172.29.0.4"
    assert result["edgeServices"] == ["gateway", "ws-hub"]
    assert result["backendServices"] == ["backend"]
    assert result["rejectedCidr"] is True
    assert result["rejectedPublic"] is True
    assert result["rejectedExtraKey"] is True
    assert result["rejectedEmptyBackend"] is True
    assert result["rejectedMissingPeer"] is True


def _run_powershell_readiness_contract(tmp_path: Path) -> dict[str, object]:
    assert POWERSHELL is not None
    runner = tmp_path / "readiness-contract.ps1"
    runner.write_text(_POWERSHELL_RUNNER, encoding="utf-8")
    try:
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
    except subprocess.TimeoutExpired as error:
        phase = _last_readiness_timeout_phase(error.stderr)
        pytest.fail(
            f"powershell_live_readiness_contract_timed_out: phase={phase}",
            pytrace=False,
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
    assert result["mailpitUrl"] == "http://127.0.0.1:43123/api/v1/info"

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


def test_trusted_proxy_refresh_wait_is_bounded() -> None:
    source = LAUNCHER.read_text(encoding="utf-8")
    refresh_command = (
        "docker compose @ComposeArgs --env-file $EnvFile "
        "up --wait --wait-timeout 120 -d --no-deps @refreshServices"
    )

    assert source.count(refresh_command) == 1
    assert "up -d --no-deps @refreshServices" not in source


@pytest.mark.parametrize(
    ("stderr", "expected_phase"),
    [
        pytest.param(
            (
                b"CONTRACT_STAGE:core-inventory\n"
                b"private-path private-field=private-value\n"
                b"CONTRACT_STAGE:../untrusted-phase\n"
            ),
            "core-inventory",
            id="last-allowlisted-phase-only",
        ),
        pytest.param(
            "CONTRACT_STAGE:../../private-path\nprivate-field=private-value",
            "unknown",
            id="unrecognized-phase-is-unknown",
        ),
        pytest.param(
            b"CONTRACT_STAGE:core-\xffloop",
            "unknown",
            id="malformed-encoded-phase-is-unknown",
        ),
    ],
)
def test_readiness_timeout_diagnostic_only_exposes_finite_phase(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    stderr: bytes | str,
    expected_phase: str,
) -> None:
    monkeypatch.setitem(globals(), "POWERSHELL", "private-pwsh-marker")

    def timeout_run(
        command: list[str], **kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        assert kwargs["timeout"] == 20
        assert command[0] == "private-pwsh-marker"
        assert command[command.index("-ExpectedRootsJson") + 1] == json.dumps(
            CORE_ROOTS
        )
        assert command[command.index("-ExpectedCoreJson") + 1] == json.dumps(
            CORE_SERVICES
        )
        raise subprocess.TimeoutExpired(
            cmd=["private-command-path", "private-command-value"],
            timeout=20,
            output=b"CONTRACT_STAGE:selection-guard\nstdout-private-value",
            stderr=stderr,
        )

    monkeypatch.setattr(subprocess, "run", timeout_run)
    with pytest.raises(pytest.fail.Exception) as failure:
        _run_powershell_readiness_contract(tmp_path)

    assert str(failure.value) == (
        f"powershell_live_readiness_contract_timed_out: phase={expected_phase}"
    )
    assert "private-path" not in str(failure.value)
    assert "private-value" not in str(failure.value)
    assert "stdout-private-value" not in str(failure.value)
    assert "private-command" not in str(failure.value)
