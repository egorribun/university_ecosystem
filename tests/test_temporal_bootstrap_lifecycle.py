"""No-Docker execution contract for the private proposed launcher block.

Extracts the actual block through PowerShell AST, exercises the current real
private lease/mint helpers with a generated RSA key, and fakes only Compose and
model validators. It does not prove Compose, Docker bind or final integration.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

ROOT = Path(__file__).resolve().parents[1]
PROPOSED = ROOT / "start-docker.ps1"
HELPER = ROOT / "scripts" / "temporal" / "bootstrap-functions.ps1"

RUNNER = r"""
param([string]$Launcher, [string]$Helper, [string]$State, [string]$Scenario, [string]$Receipt)
$ErrorActionPreference = 'Stop'
$tokens = $null; $errors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile($Launcher, [ref]$tokens, [ref]$errors)
if ($errors.Count) { throw 'candidate launcher failed to parse' }
foreach ($name in @('ConvertTo-Base64Url', 'Assert-EnvironmentFileLeafPath', 'Get-TemporalDiagnosticSummary', 'Write-TemporalStartupDiagnostic')) {
    $node = $ast.Find({param($v) $v -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $v.Name -eq $name}, $true)
    if ($null -eq $node) { throw 'candidate helper not found' }
    Invoke-Expression $node.Extent.Text
}
. $Helper
$script:realEnter = (Get-Item function:Enter-TemporalBootstrapLease).ScriptBlock
$script:realExit = (Get-Item function:Exit-TemporalBootstrapLease).ScriptBlock
$script:realMint = (Get-Item function:New-TemporalBootstrapProfile).ScriptBlock
$script:realIdentity = (Get-Item function:Assert-TemporalBootstrapIdentity).ScriptBlock
$script:events = [System.Collections.Generic.List[object]]::new()
$script:diagnostics = [System.Collections.Generic.List[string]]::new()
$script:privateMarker = 'PRIVATE-MARKER-DO-NOT-EMIT'
$script:StateRoot = $State
$script:ProjectRoot = $State
$script:ComposeArgs = @('-p', 'synthetic-owner', '-f', 'synthetic-compose.yml')
$script:EnvFile = 'synthetic.env'
$script:LiveStandOwner = [PSCustomObject]@{ version = 11; stack = 'full'; source_sha = ('a' * 40) }
$script:LiveStateMode = $Scenario -notin @('ordinary_full', 'disabled') -and -not $Scenario.StartsWith('prepare_')
$script:TemporalBootstrapRequested = $false
$LiveStandStateRoot = if ($script:LiveStateMode) { Join-Path $State 'owned-state' } else { '' }
$script:LiveAcceptanceCore = ($Scenario -eq 'core_bypass')
$Core = ($Scenario -eq 'core_bypass')
$Down = ($Scenario -eq 'down_bypass')
$Logs = ($Scenario -eq 'logs_bypass')
$RefreshTrustedProxyPeers = ($Scenario -eq 'refresh_bypass')
$PrepareOnly = ($Scenario -eq 'disabled') -or $Scenario.StartsWith('prepare_')
$ExtraCompose = @('docker-compose.live.yml')
$script:sourceCount = 0
$script:modelCount = 0
$script:identityCount = 0
$script:legacyFileProcessorRunning = ($Scenario -eq 'legacy_fp')
$script:withinHelper = $false
$script:failure = $false
$script:failure_reason = ''
function Add-Event {
    param([string]$Name, [string[]]$Arguments = @())
    $path = Join-Path $State '.temporal-bootstrap/profile.toml'
    $length = if (Test-Path -LiteralPath $path -PathType Leaf) { (Get-Item -LiteralPath $path).Length } else { -1 }
    $digest = ''
    if ($length -gt 0) {
        $reader = [System.IO.FileStream]::new($path, [System.IO.FileMode]::Open, [System.IO.FileAccess]::Read, [System.IO.FileShare]::ReadWrite)
        $sha = [System.Security.Cryptography.SHA256]::Create()
        try { $digest = [Convert]::ToHexString($sha.ComputeHash($reader)) }
        finally { $sha.Dispose(); $reader.Dispose() }
    }
    [void]$script:events.Add([PSCustomObject]@{ name = $Name; arguments = @($Arguments); length = $length; digest = $digest })
}
function Write-Status { param([string]$Message) }
function Resolve-StatePath { param([string]$Path) Join-Path $State $Path }
function Resolve-OwnedLiveStandStateRoot { param([string]$Path) return $State }
function Get-VerifiedLiveAcceptanceOwner { return $script:LiveStandOwner }
function Assert-InPlaceTemporalBootstrapSource {
    param([string]$SourceSha, [string]$Repository)
    $script:sourceCount++
    Add-Event 'source'
    if ($Scenario -eq 'source_fail' -or ($Scenario -eq 'source_recheck_fail' -and $script:sourceCount -eq 3) -or ($Scenario -eq 'source_final_fail' -and $script:sourceCount -eq 4)) { throw 'synthetic source rejection' }
}
function Assert-ComposeConfiguration { Add-Event 'resolve'; return [PSCustomObject]@{} }
function Assert-LiveAcceptanceSelection { param($ComposeModel) Add-Event 'selection'; return $true }
function Assert-InPlaceTemporalBootstrapModel {
    param($ComposeModel, $StateRoot, $ProjectRoot)
    $script:modelCount++
    Add-Event 'model'
    if ($Scenario -eq 'model_fail' -or ($Scenario -eq 'model_recheck_fail' -and $script:modelCount -eq 2)) { throw 'synthetic model rejection' }
}
function Assert-InPlaceTemporalBootstrapVolumeSafety {
    param($ComposeModel)
    Add-Event 'volume_safety'
    if ($Scenario -eq 'volume_fail') { throw 'synthetic volume inspection rejection' }
}
function Enter-TemporalBootstrapLease {
    param([string]$StateRoot)
    Add-Event 'enter'
    $script:withinHelper = $true
    try { $lease = & $script:realEnter -StateRoot $StateRoot } finally { $script:withinHelper = $false }
    Add-Event 'entered'
    return $lease
}
function Exit-TemporalBootstrapLease {
    param($Lease)
    Add-Event 'exit'
    $script:withinHelper = $true
    try { & $script:realExit -Lease $Lease } finally { $script:withinHelper = $false }
    Add-Event 'exited'
}
function New-TemporalBootstrapProfile {
    param([string]$PrivateKeyPath, $Lease)
    Add-Event 'mint'
    $script:withinHelper = $true
    try { & $script:realMint -PrivateKeyPath $PrivateKeyPath -Lease $Lease } finally { $script:withinHelper = $false }
    Add-Event 'minted'
}
function Assert-TemporalBootstrapIdentity {
    param($Lease, [switch]$RequirePath, [switch]$RequireSingleLink)
    if (-not $script:withinHelper) {
        $script:identityCount++
        Add-Event 'identity'
        if ($Scenario -eq 'identity_fail' -or ($Scenario -eq 'identity_final_fail' -and $script:identityCount -eq 2)) { throw 'synthetic identity rejection' }
    }
    & $script:realIdentity -Lease $Lease -RequirePath:$RequirePath -RequireSingleLink:$RequireSingleLink
}
function Assert-InPlaceTemporalBootstrapRuntime {
    param($ComposeModel, $StateRoot, $ProjectRoot)
    Add-Event 'runtime'
    if ($script:legacyFileProcessorRunning) { throw 'legacy file processor remained running before peer inspection' }
    if ($Scenario -eq 'runtime_fail') { throw 'synthetic runtime rejection' }
    return ('b' * 64)
}
function Invoke-TemporalBootstrapDockerBounded {
    param([string[]]$Arguments, [int]$TimeoutSeconds)
    Add-Event ('bounded_' + $Arguments[0]) (@($Arguments) + @([string]$TimeoutSeconds))
    if ($Arguments[0] -eq 'start') {
        if ($Scenario -eq 'start_fail') { throw 'synthetic start failure' }
        if ($Scenario -eq 'start_mismatch') { return ('c' * 64) }
        return $Arguments[1]
    }
    if ($Arguments[0] -eq 'wait') {
        if ($Scenario -eq 'wait_timeout') { throw 'synthetic wait timeout' }
        if ($Scenario -eq 'wait_nonzero') { return '1' }
        return '0'
    }
    if ($Arguments[0] -eq 'kill') { return $Arguments[1] }
    throw 'unexpected bounded Docker invocation'
}
function docker {
    $arguments = @($args | ForEach-Object { [string]$_ })
    if ($arguments[0] -eq 'inspect') {
        Add-Event 'docker_diagnostic_inspect' $arguments
        $global:LASTEXITCODE = if ($Scenario -eq 'dependency_inspect_fail') { 11 } else { 0 }
        if ($Scenario -in @('dependency_inspect_fail', 'dependency_bad_state')) { return "exited|false|2|false|3|none|0|$script:privateMarker" }
        return 'exited|false|2|false|3|none|0'
    } elseif ($arguments -contains 'ps') {
        Add-Event 'docker_diagnostic_ps' $arguments
        if ($Scenario -eq 'dependency_diagnostic_exception') { throw "private exception $script:privateMarker" }
        $global:LASTEXITCODE = 0
        if ($Scenario -eq 'dependency_invalid_id') { return "invalid-$script:privateMarker" }
        return ('a' * 64)
    } elseif ($arguments -contains 'logs') {
        Add-Event 'docker_diagnostic_logs' $arguments
        $global:LASTEXITCODE = if ($Scenario -eq 'dependency_logs_fail') { 12 } else { 0 }
        return "password authentication failed $script:privateMarker"
    } elseif ($arguments[-2] -eq 'stop' -and $arguments[-1] -eq 'file-processor') {
        Add-Event 'docker_stop_file_processor' $arguments
        if ($Scenario -eq 'stop_fail') {
            $global:LASTEXITCODE = 13
        } else {
            $script:legacyFileProcessorRunning = $false
            $global:LASTEXITCODE = 0
        }
    } elseif ($arguments[-1] -eq 'temporal') {
        Add-Event 'docker_dependency' $arguments
        $global:LASTEXITCODE = if ($Scenario -like 'dependency_*') { 8 } else { 0 }
    } elseif ($arguments[-1] -eq 'temporal-namespace-init') {
        Add-Event 'docker_create' $arguments
        $global:LASTEXITCODE = if ($Scenario -eq 'create_fail') { 9 } else { 0 }
    } else { throw 'unexpected synthetic Docker invocation' }
}
$lines = [System.IO.File]::ReadAllLines($Launcher)
$marker = -1
for ($i = 0; $i -lt $lines.Length; $i++) { if ($lines[$i] -match '^# -- Start services') { $marker = $i + 1; break } }
if ($marker -lt 0) { throw 'start-services marker missing' }
$bootstrapAssignment = $ast.Find({param($n) $n -is [System.Management.Automation.Language.AssignmentStatementAst] -and $n.Extent.Text.StartsWith('$fullTemporalBootstrap =')}, $true)
if ($null -eq $bootstrapAssignment) { throw 'shared bootstrap selection missing' }
$blocks = @($ast.FindAll({
    param($n)
    $n -is [System.Management.Automation.Language.IfStatementAst] -and
    $n.Extent.StartLineNumber -gt $marker -and
    $n.Extent.Text.StartsWith('if ($fullTemporalBootstrap)')
}, $true))
if ($blocks.Count -ne 1) { throw 'expected one shared full bootstrap block' }
try {
    if ($Scenario.StartsWith('prepare_')) {
        $script:LiveStateMode = $false
        $script:TemporalBootstrapRequested = $false
        $script:LiveStandOwner.version = if ($Scenario -eq 'prepare_v7') { 7 } else { 11 }
        $script:LiveStandOwner.stack = if ($Scenario -eq 'prepare_full') { 'full' } else { 'core' }
        if ($Scenario -eq 'prepare_ordinary') {
            Remove-Item -LiteralPath (Join-Path $State '.secrets/live-stand.json') -Force -ErrorAction SilentlyContinue
        } else {
            [System.IO.File]::WriteAllText((Join-Path $State '.secrets/live-stand.json'), '{}')
        }
        function Get-VerifiedLiveAcceptanceOwner { return $script:LiveStandOwner }
        $projectScripts = Join-Path $State 'scripts/temporal'
        New-Item -ItemType Directory -Path $projectScripts -Force | Out-Null
        Copy-Item -LiteralPath $Helper -Destination (Join-Path $projectScripts 'bootstrap-functions.ps1')
        $script:ProjectRoot = $State
        $ProjectRoot = $State
        $selection = $ast.Find({
            param($n)
            $n -is [System.Management.Automation.Language.IfStatementAst] -and
            $n.Extent.Text.StartsWith('if ($LiveStateMode)') -and
            $n.Extent.Text.Contains('$prepareManagedFull')
        }, $true)
        $prepareLease = $ast.Find({
            param($n)
            $n -is [System.Management.Automation.Language.IfStatementAst] -and
            $n.Extent.Text.StartsWith('if ($script:TemporalBootstrapRequested)')
        }, $true)
        if ($null -eq $selection -or $null -eq $prepareLease) { throw 'managed prepare selection or lease guard missing' }
        Invoke-Expression $selection.Extent.Text
        Invoke-Expression $bootstrapAssignment.Extent.Text
        function Enter-TemporalBootstrapLease {
            param([string]$StateRoot)
            Add-Event 'enter'
            $script:withinHelper = $true
            try { $lease = & $script:realEnter -StateRoot $StateRoot } finally { $script:withinHelper = $false }
            Add-Event 'entered'
            return $lease
        }
        function Exit-TemporalBootstrapLease {
            param($Lease)
            Add-Event 'exit'
            $script:withinHelper = $true
            try { & $script:realExit -Lease $Lease } finally { $script:withinHelper = $false }
            Add-Event 'exited'
        }
        Invoke-Expression $prepareLease.Extent.Text
    } else {
        if ($Scenario -eq 'disabled') {
            Remove-Item -LiteralPath (Join-Path $State '.secrets/live-stand.json') -Force -ErrorAction SilentlyContinue
        }
        $selection = $ast.Find({
            param($n)
            $n -is [System.Management.Automation.Language.IfStatementAst] -and
            $n.Extent.Text.StartsWith('if ($LiveStateMode)') -and
            $n.Extent.Text.Contains('$prepareManagedFull')
        }, $true)
        if ($null -eq $selection) { throw 'shared Temporal bootstrap selection condition missing' }
        $selectionPath = Join-Path $State 'scripts/temporal/bootstrap-functions.ps1'
        New-Item -ItemType Directory -Path (Split-Path -Parent $selectionPath) -Force | Out-Null
        [System.IO.File]::WriteAllText($selectionPath, '# selection-only placeholder')
        Invoke-Expression $selection.Extent.Text
        Invoke-Expression $bootstrapAssignment.Extent.Text
        Invoke-Expression $blocks[0].Extent.Text | ForEach-Object { [void]$script:diagnostics.Add([string]$_) }
    }
} catch { $script:failure = $true; $script:failure_reason = $_.Exception.Message }
$payload = [PSCustomObject]@{ failed = $script:failure; reason = $script:failure_reason; bootstrap_requested = $script:TemporalBootstrapRequested; full_bootstrap = [bool]$fullTemporalBootstrap; events = @($script:events); diagnostics = @($script:diagnostics) } | ConvertTo-Json -Depth 6 -Compress
[System.IO.File]::WriteAllText($Receipt, $payload, [System.Text.UTF8Encoding]::new($false))
"""


async def run_powershell(arguments: list[str]) -> tuple[int, str, str]:
    process = await asyncio.create_subprocess_exec(
        *arguments,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=30)
    except TimeoutError:
        if process.returncode is None:
            process.kill()
        await process.wait()
        raise
    return process.returncode, stdout.decode("utf-8"), stderr.decode("utf-8")


class LauncherLifecycle(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.pwsh = shutil.which("pwsh")
        if not cls.pwsh:
            raise RuntimeError("PowerShell is required")
        cls.pwsh = str(Path(cls.pwsh).resolve(strict=True))
        cls.launcher_hash = hashlib.sha256(PROPOSED.read_bytes()).hexdigest()
        cls.helper_hash = hashlib.sha256(HELPER.read_bytes()).hexdigest()
        cls.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        cls.key_bytes = cls.key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(prefix="ue-temporal-launch-order-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / ".secrets").mkdir()
        (self.root / ".secrets" / "jwt_rs256.pem").write_bytes(self.key_bytes)
        self.runner = self.root / "runner.ps1"
        self.runner.write_text(RUNNER, encoding="utf-8")
        self.receipt = self.root / "receipt.json"
        self.profile = self.root / ".temporal-bootstrap" / "profile.toml"

    def run_block(self, scenario: str):
        code, stdout, stderr = asyncio.run(
            run_powershell(
                [
                    self.pwsh,
                    "-NoProfile",
                    "-NonInteractive",
                    "-File",
                    str(self.runner),
                    str(PROPOSED),
                    str(HELPER),
                    str(self.root),
                    scenario,
                    str(self.receipt),
                ],
            )
        )
        self.assertEqual(code, 0, stderr)
        self.assertEqual(stdout, "")
        data = json.loads(self.receipt.read_text(encoding="utf-8"))
        self.assertEqual(
            hashlib.sha256(PROPOSED.read_bytes()).hexdigest(), self.launcher_hash
        )
        self.assertEqual(
            hashlib.sha256(HELPER.read_bytes()).hexdigest(), self.helper_hash
        )
        return data

    def assert_scrubbed(self):
        self.assertTrue(self.profile.is_file())
        self.assertEqual(self.profile.read_bytes(), b"")

    def test_normal_full_up_runs_after_shared_temporal_bootstrap(self):
        script = PROPOSED.read_text(encoding="utf-8")
        start = script.index("# -- Start services")
        bootstrap = script.index("if ($fullTemporalBootstrap)", start)
        core_selection = script.index("if ($script:LiveAcceptanceCore)", bootstrap)
        full_start = script.index(
            'Write-Status "Starting containers..."', core_selection
        )
        full_up = script.index(
            "docker compose @ComposeArgs --env-file $EnvFile up -d\n", full_start
        )
        health_loop = script.index("# -- Health check loop", full_up)
        self.assertLess(bootstrap, core_selection)
        self.assertLess(core_selection, full_start)
        self.assertLess(full_start, full_up)
        self.assertLess(full_up, health_loop)

    def test_success_orders_creation_inspection_mint_start_and_wait(self):
        data = self.run_block("success")
        self.assertFalse(data["failed"], data)
        self.assertTrue(data["bootstrap_requested"])
        self.assertTrue(data["full_bootstrap"])
        self.assertEqual(data["diagnostics"], [])
        events = data["events"]
        names = [event["name"] for event in events]
        self.assertEqual(
            names,
            [
                "source",
                "source",
                "docker_stop_file_processor",
                "docker_dependency",
                "enter",
                "entered",
                "resolve",
                "selection",
                "model",
                "docker_create",
                "source",
                "resolve",
                "selection",
                "model",
                "volume_safety",
                "identity",
                "source",
                "identity",
                "runtime",
                "mint",
                "minted",
                "bounded_start",
                "bounded_wait",
                "exit",
                "exited",
            ],
        )
        self.assertEqual(events[names.index("docker_create")]["length"], 0)
        self.assertEqual(events[names.index("mint")]["length"], 0)
        self.assertGreater(events[names.index("bounded_start")]["length"], 0)
        self.assert_scrubbed()
        first = events[names.index("docker_dependency")]["arguments"]
        self.assertEqual(
            first[-5:], ["up", "--wait", "--wait-timeout", "300", "temporal"]
        )
        stop = events[names.index("docker_stop_file_processor")]["arguments"]
        self.assertEqual(stop[-2:], ["stop", "file-processor"])
        self.assertLess(
            names.index("docker_stop_file_processor"), names.index("runtime")
        )
        second = events[names.index("docker_create")]["arguments"]
        self.assertEqual(
            second[-8:],
            [
                "up",
                "--no-start",
                "--no-deps",
                "--no-build",
                "--pull",
                "never",
                "--force-recreate",
                "temporal-namespace-init",
            ],
        )
        self.assertEqual(
            events[names.index("bounded_start")]["arguments"], ["start", "b" * 64, "15"]
        )
        self.assertEqual(
            events[names.index("bounded_wait")]["arguments"], ["wait", "b" * 64, "240"]
        )
        self.assertNotIn("build", second)
        self.assertFalse(any("eyJ" in arg for arg in first + second))

    def test_ordinary_full_uses_the_same_authenticated_sequence_without_live_owner(
        self,
    ):
        data = self.run_block("ordinary_full")
        self.assertFalse(data["failed"], data)
        self.assertTrue(data["bootstrap_requested"])
        self.assertTrue(data["full_bootstrap"])
        names = [event["name"] for event in data["events"]]
        self.assertNotIn("source", names)
        self.assertIn("docker_stop_file_processor", names)
        self.assertIn("docker_dependency", names)
        self.assertIn("mint", names)
        self.assertIn("bounded_start", names)
        self.assertIn("bounded_wait", names)
        self.assert_scrubbed()

    def test_explicit_lifecycle_and_core_modes_skip_bootstrap(self):
        for scenario in (
            "disabled",
            "core_bypass",
            "down_bypass",
            "logs_bypass",
            "refresh_bypass",
        ):
            with self.subTest(scenario=scenario):
                data = self.run_block(scenario)
                self.assertFalse(data["failed"], data)
                self.assertFalse(data["bootstrap_requested"])
                self.assertFalse(data["full_bootstrap"])
                self.assertEqual(data["events"], [])
                self.assertFalse(self.profile.exists())

    def test_early_failures_issue_no_credential(self):
        for scenario in ("source_fail", "dependency_fail"):
            with self.subTest(scenario=scenario):
                data = self.run_block(scenario)
                self.assertTrue(data["failed"])
                self.assertNotIn("enter", [e["name"] for e in data["events"]])
                self.assertFalse(self.profile.exists())

    def test_legacy_file_processor_is_stopped_before_bootstrap_peer_inspection(self):
        data = self.run_block("legacy_fp")
        self.assertFalse(data["failed"], data)
        names = [event["name"] for event in data["events"]]
        self.assertLess(
            names.index("docker_stop_file_processor"), names.index("runtime")
        )
        self.assertIn("bounded_start", names)
        self.assert_scrubbed()

    def test_file_processor_stop_failure_fails_closed_before_credential_mint(self):
        data = self.run_block("stop_fail")
        self.assertTrue(data["failed"])
        self.assertEqual(
            data["reason"],
            "Existing file processor could not be stopped; namespace bootstrap was not issued.",
        )
        names = [event["name"] for event in data["events"]]
        self.assertIn("docker_stop_file_processor", names)
        self.assertNotIn("docker_dependency", names)
        self.assertNotIn("enter", names)
        self.assertFalse(self.profile.exists())

    def test_dependency_failure_reports_only_scoped_safe_diagnostic(self):
        data = self.run_block("dependency_fail")
        self.assertTrue(data["failed"])
        self.assertEqual(
            data["reason"],
            "Temporal dependency startup failed; namespace bootstrap was not issued.",
        )
        names = [event["name"] for event in data["events"]]
        self.assertEqual(
            names,
            [
                "source",
                "source",
                "docker_stop_file_processor",
                "docker_dependency",
                "docker_diagnostic_ps",
                "docker_diagnostic_inspect",
                "docker_diagnostic_logs",
            ],
        )
        self.assertEqual(
            data["diagnostics"],
            [
                "temporal_state=exited|false|2|false|3|none|0",
                "temporal_signature=database_auth",
            ],
        )
        expected_prefix = [
            "compose",
            "-p",
            "synthetic-owner",
            "-f",
            "synthetic-compose.yml",
            "--env-file",
            "synthetic.env",
        ]
        self.assertEqual(
            data["events"][names.index("docker_diagnostic_ps")]["arguments"],
            [*expected_prefix, "ps", "--all", "-q", "temporal"],
        )
        self.assertEqual(
            data["events"][names.index("docker_diagnostic_logs")]["arguments"],
            [*expected_prefix, "logs", "--no-color", "--tail=50", "temporal"],
        )
        self.assertNotIn("PRIVATE-MARKER", json.dumps(data))
        self.assertFalse(self.profile.exists())

    def test_dependency_diagnostic_failures_preserve_original_failure_and_privacy(self):
        cases = {
            "dependency_invalid_id": ["temporal_diagnostic=container_unavailable"],
            "dependency_diagnostic_exception": ["temporal_diagnostic=unavailable"],
            "dependency_inspect_fail": [
                "temporal_state=unavailable",
                "temporal_signature=database_auth",
            ],
            "dependency_bad_state": [
                "temporal_state=unavailable",
                "temporal_signature=database_auth",
            ],
            "dependency_logs_fail": [
                "temporal_state=exited|false|2|false|3|none|0",
                "temporal_logs=unavailable",
            ],
        }
        for scenario, expected in cases.items():
            with self.subTest(scenario=scenario):
                data = self.run_block(scenario)
                self.assertTrue(data["failed"])
                self.assertEqual(
                    data["reason"],
                    "Temporal dependency startup failed; namespace bootstrap was not issued.",
                )
                self.assertEqual(data["diagnostics"], expected)
                self.assertNotIn("PRIVATE-MARKER", json.dumps(data))
                self.assertNotIn("enter", [event["name"] for event in data["events"]])
                self.assertFalse(self.profile.exists())

    def test_pre_mint_failures_scrub_and_do_not_start(self):
        for scenario in (
            "model_fail",
            "create_fail",
            "source_recheck_fail",
            "model_recheck_fail",
            "volume_fail",
            "identity_fail",
            "runtime_fail",
            "source_final_fail",
            "identity_final_fail",
        ):
            with self.subTest(scenario=scenario):
                data = self.run_block(scenario)
                self.assertTrue(data["failed"])
                names = [e["name"] for e in data["events"]]
                self.assertEqual(names[-2:], ["exit", "exited"])
                self.assertNotIn("mint", names)
                self.assertNotIn("bounded_start", names)
                self.assert_scrubbed()

    def test_mint_failure_scrubs_and_does_not_start_initializer(self):
        (self.root / ".secrets" / "jwt_rs256.pem").unlink()
        data = self.run_block("success")
        self.assertTrue(data["failed"])
        names = [e["name"] for e in data["events"]]
        self.assertIn("mint", names)
        self.assertNotIn("minted", names)
        self.assertNotIn("bounded_start", names)
        self.assertEqual(names[-2:], ["exit", "exited"])
        self.assert_scrubbed()

    def test_start_and_wait_failures_scrub_and_kill_unconfirmed_execution(self):
        for scenario in (
            "start_fail",
            "start_mismatch",
            "wait_timeout",
            "wait_nonzero",
        ):
            with self.subTest(scenario=scenario):
                data = self.run_block(scenario)
                self.assertTrue(data["failed"])
                names = [e["name"] for e in data["events"]]
                self.assertGreater(
                    data["events"][names.index("bounded_start")]["length"], 0
                )
                self.assertEqual("bounded_kill" in names, scenario != "wait_nonzero")
                if "bounded_kill" in names:
                    self.assertEqual(
                        data["events"][names.index("bounded_kill")]["arguments"],
                        ["kill", "b" * 64, "10"],
                    )
                self.assertEqual(names[-2:], ["exit", "exited"])
                self.assert_scrubbed()

    def test_repeated_launch_reuses_inode_but_mints_fresh_credential(self):
        first = self.run_block("success")
        self.assertFalse(first["failed"])
        inode = self.profile.stat().st_ino
        first_digest = next(
            e["digest"] for e in first["events"] if e["name"] == "bounded_start"
        )
        self.assert_scrubbed()
        second = self.run_block("success")
        self.assertFalse(second["failed"])
        self.assertEqual(self.profile.stat().st_ino, inode)
        second_digest = next(
            e["digest"] for e in second["events"] if e["name"] == "bounded_start"
        )
        self.assertNotEqual(first_digest, second_digest)
        self.assert_scrubbed()

    def test_signed_core_prepare_does_not_create_profile(self):
        data = self.run_block("prepare_core")
        self.assertFalse(data["failed"], data)
        self.assertEqual(data["events"], [])
        self.assertFalse(self.profile.exists())

    def test_full_and_legacy_prepare_create_only_empty_profile(self):
        for scenario in ("prepare_full", "prepare_v7"):
            with self.subTest(scenario=scenario):
                data = self.run_block(scenario)
                self.assertFalse(data["failed"], data)
                self.assertEqual(
                    [e["name"] for e in data["events"]],
                    ["enter", "entered", "exit", "exited"],
                )
                self.assert_scrubbed()

    def test_prepare_without_a_managed_full_owner_skips_bootstrap_lease(self):
        data = self.run_block("prepare_ordinary")
        self.assertFalse(data["failed"], data)
        self.assertEqual(data["events"], [])
        self.assertFalse(self.profile.exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
