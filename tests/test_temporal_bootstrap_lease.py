"""Verify private profile leases using synthetic keys and temporary files."""

from __future__ import annotations

import asyncio
import os
import shutil
import tomllib
from pathlib import Path

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "scripts/temporal/bootstrap-functions.ps1"
LAUNCHER = ROOT / "start-docker.ps1"

RUNNER = r"""
param([string]$Repo, [string]$Candidate, [string]$Root, [string]$Action, [string]$Key)
$ErrorActionPreference = 'Stop'
$tokens = $null; $errors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile($Repo, [ref]$tokens, [ref]$errors)
if ($errors.Count) { throw 'source parse failed' }
foreach ($name in @('ConvertTo-Base64Url', 'Assert-EnvironmentFileLeafPath')) {
    $node = $ast.Find({param($v) $v -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $v.Name -eq $name}, $true)
    if ($null -eq $node) { throw 'missing launcher helper' }
    Invoke-Expression $node.Extent.Text
}
. $Candidate
$lease = Enter-TemporalBootstrapLease -StateRoot $Root
try {
    if ($Action -eq 'mint') {
        New-TemporalBootstrapProfile -PrivateKeyPath $Key -Lease $lease
        [Console]::Out.WriteLine('ready')
        $null = [Console]::ReadLine()
    } elseif ($Action -ne 'init') { throw 'unexpected action' }
} finally { Exit-TemporalBootstrapLease -Lease $lease }
"""


async def _start(
    runner: Path, state: Path, action: str, key: Path
) -> asyncio.subprocess.Process:
    executable = shutil.which("pwsh")
    assert executable and Path(executable).is_file()
    return await asyncio.create_subprocess_exec(
        executable,
        "-NoProfile",
        "-NonInteractive",
        "-File",
        str(runner),
        str(LAUNCHER),
        str(HELPER),
        str(state),
        action,
        str(key),
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )


async def _finish(
    process: asyncio.subprocess.Process, data: bytes = b""
) -> tuple[int, bytes]:
    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(data), timeout=20)
    except BaseException:
        if process.returncode is None:
            process.kill()
            await process.wait()
        raise
    return process.returncode, stdout + stderr


@pytest.mark.asyncio
async def test_mints_and_scrubs_fresh_scoped_profiles(tmp_path: Path) -> None:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    key_path = tmp_path / "synthetic-key.pem"
    key_path.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    runner = tmp_path / "runner.ps1"
    runner.write_text(RUNNER, encoding="utf-8")
    profile = tmp_path / ".temporal-bootstrap/profile.toml"
    status, output = await _finish(await _start(runner, tmp_path, "init", key_path))
    assert status == 0, output
    inode = profile.stat().st_ino
    previous = None
    for _ in range(2):
        process = await _start(runner, tmp_path, "mint", key_path)
        try:
            assert process.stdout is not None
            ready = await asyncio.wait_for(process.stdout.readline(), timeout=20)
            assert ready.strip() == b"ready"
            assert profile.stat().st_ino == inode
            config = tomllib.loads(profile.read_text(encoding="utf-8"))["profile"][
                "default"
            ]
            assert config["address"] == "127.0.0.1:7233"
            assert config["namespace"] == "default"
            assert config["tls"] == {"disabled": True}
            token = config["api_key"]
            assert token != previous
            assert jwt.get_unverified_header(token)["kid"] == "primary"
            claims = jwt.decode(
                token, key.public_key(), algorithms=["RS256"], audience="temporal"
            )
            assert claims["sub"] == "temporal-namespace-bootstrap"
            assert claims["permissions"] == ["default:admin"]
            assert claims["exp"] - claims["iat"] == 300
            previous = token
            status, output = await _finish(process, b"done\n")
            assert status == 0, output
        finally:
            if process.returncode is None:
                process.kill()
                await process.wait()
        assert profile.stat().st_ino == inode
        assert profile.read_text(encoding="utf-8") == ""


@pytest.mark.asyncio
@pytest.mark.parametrize("replacement", ["hardlink", "single_link", "stale_lock"])
async def test_untrusted_profile_is_never_truncated(
    tmp_path: Path, replacement: str
) -> None:
    runner = tmp_path / "runner.ps1"
    runner.write_text(RUNNER, encoding="utf-8")
    placeholder_key = tmp_path / "unused-key"
    status, output = await _finish(
        await _start(runner, tmp_path, "init", placeholder_key)
    )
    assert status == 0, output
    profile = tmp_path / ".temporal-bootstrap/profile.toml"
    victim = tmp_path / "synthetic-victim.txt"
    original = b"synthetic victim remains unchanged"
    victim.write_bytes(original)
    if replacement == "stale_lock":
        (profile.parent / "profile.lock").write_bytes(b"unknown lock")
        observed = victim
    else:
        profile.unlink()
        if replacement == "hardlink":
            os.link(victim, profile)
            observed = victim
        else:
            victim.rename(profile)
            observed = profile
    status, _ = await _finish(await _start(runner, tmp_path, "init", placeholder_key))
    assert status != 0
    assert observed.read_bytes() == original
