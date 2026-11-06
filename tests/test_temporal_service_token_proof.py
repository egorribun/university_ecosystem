"""Exercise the launcher's Temporal token functions with ephemeral keys."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

ROOT = Path(__file__).resolve().parents[1]

HARNESS = r"""
param([string]$SourcePath, [string]$KeyPath, [string]$TokenPath, [string]$Action)
$ErrorActionPreference = 'Stop'
$tokens = $null
$parseErrors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile($SourcePath, [ref]$tokens, [ref]$parseErrors)
if ($parseErrors.Count) { throw 'Launcher did not parse' }
$definitions = @{}
foreach ($definition in $ast.FindAll({ param($node) $node -is [System.Management.Automation.Language.FunctionDefinitionAst] }, $true)) {
    $definitions[$definition.Name] = $definition
}
foreach ($name in @('ConvertTo-Base64Url', 'ConvertFrom-Base64Url', 'Test-TemporalServiceToken', 'New-TemporalServiceToken')) {
    if (-not $definitions.ContainsKey($name)) { throw "Missing launcher function: $name" }
    Invoke-Expression $definitions[$name].Extent.Text
}
function Resolve-StatePath { param([string]$Path) return $Path }
function Set-LiveStandPrivateFileMode { param([string]$Path) }
function Write-Status { param([string]$Message) }
function Write-Ok { param([string]$Message) }
function Write-Warn { param([string]$Message) }
if ($Action -eq 'mint') {
    New-TemporalServiceToken -PrivateKeyPath $KeyPath -OutputPath $TokenPath -NoDockerFallback
} elseif ($Action -eq 'verify') {
    $candidate = [System.IO.File]::ReadAllText($TokenPath)
    if (Test-TemporalServiceToken -Token $candidate -PrivateKeyPath $KeyPath -Subject 'file-processor-service' -Audience 'temporal') {
        'accepted'
    } else {
        'rejected'
    }
} else {
    throw 'Unknown test action'
}
"""


def test_launcher_mints_and_reuses_only_the_scoped_temporal_token(
    tmp_path: Path,
) -> None:
    pwsh = shutil.which("pwsh")
    assert pwsh, "PowerShell 7 is required for the Temporal launcher proof"
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    key_path = tmp_path / "ephemeral-signing-key.pem"
    key_path.write_bytes(
        private_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    token_path = tmp_path / "temporal-token"
    harness_path = tmp_path / "temporal-token-proof.ps1"
    harness_path.write_text(HARNESS, encoding="utf-8")

    def run(action: str) -> str:
        result = subprocess.run(  # noqa: S603 - fixed PowerShell harness and temporary paths
            [
                pwsh,
                "-NoProfile",
                "-NonInteractive",
                "-File",
                str(harness_path),
                str(ROOT / "start-docker.ps1"),
                str(key_path),
                str(token_path),
                action,
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
            timeout=30,
            env=os.environ.copy(),
        )
        assert result.returncode == 0, result.stderr
        return result.stdout.strip()

    run("mint")
    minted = token_path.read_text(encoding="utf-8")
    claims = jwt.decode(
        minted, private_key.public_key(), algorithms=["RS256"], audience="temporal"
    )
    assert claims["permissions"] == ["default:write"]
    assert run("verify") == "accepted"
    run("mint")
    assert token_path.read_text(encoding="utf-8") == minted

    for permissions in (
        [],
        "default:write",
        ["default:WRITE"],
        ["system:reader", "default:writer"],
        ["default:write", "temporal-system:admin"],
        ["default:write", "default:write"],
    ):
        candidate = jwt.encode(
            {**claims, "permissions": permissions},
            private_key,
            algorithm="RS256",
            headers={"kid": "primary"},
        )
        token_path.write_text(candidate, encoding="utf-8")
        assert run("verify") == "rejected"

    legacy = jwt.encode(
        {**claims, "permissions": ["system:reader", "default:writer"]},
        private_key,
        algorithm="RS256",
        headers={"kid": "primary"},
    )
    token_path.write_text(legacy, encoding="utf-8")
    run("mint")
    replaced = token_path.read_text(encoding="utf-8")
    assert replaced != legacy
    assert jwt.decode(
        replaced, private_key.public_key(), algorithms=["RS256"], audience="temporal"
    )["permissions"] == ["default:write"]
