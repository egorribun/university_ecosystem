"""Exercise the in-place Temporal security checks without a Docker daemon."""

from __future__ import annotations

import asyncio
import copy
import ipaddress
import json
import os
import secrets
import shutil
from pathlib import Path, PurePosixPath

import pytest

ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "scripts/temporal/bootstrap-functions.ps1"
ADMIN_IMAGE = "temporalio/admin-tools:1.30.7@sha256:bbdf5fe91b288c17442efbbfb42daa3668d09cfa8ebeb078d6fd475a97f66b81"
SERVER_IMAGE = "temporalio/server:1.30.7@sha256:dc8dc6fffa29de3bad7f5c39cb406db3104053fbb0c2494e7c76016211bc99b0"


async def _run_powershell(script: Path, *arguments: str) -> tuple[int, str]:
    """Run a fixed test script with argument separation and a bounded lifetime."""
    executable = shutil.which("pwsh")
    assert executable and Path(executable).is_file()
    process = await asyncio.create_subprocess_exec(
        executable,
        "-NoProfile",
        "-NonInteractive",
        "-File",
        str(script),
        *arguments,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=20)
    except BaseException:
        if process.returncode is None:
            process.kill()
            await process.wait()
        raise
    return process.returncode, (stdout + stderr).decode("utf-8", errors="replace")


def _model(state: Path, repo: Path) -> dict:
    project = "ue-live-0123456789abcdef"

    def bind(source: Path, target: str) -> dict:
        return {
            "type": "bind",
            "source": str(source.resolve()),
            "target": target,
            "read_only": True,
        }

    return {
        "name": project,
        "volumes": {"temporal-jwks-ca": {"name": f"{project}_temporal-jwks-ca"}},
        "services": {
            "temporal-namespace-init": {
                "image": ADMIN_IMAGE,
                "network_mode": "service:temporal",
                "user": "1000:1000",
                "read_only": True,
                "cap_drop": ["ALL"],
                "security_opt": ["no-new-privileges:true"],
                "entrypoint": ["/bin/sh", "/etc/temporal/namespace-init.sh"],
                "command": [],
                "tmpfs": [
                    f"{PurePosixPath('/') / 'tmp'}:uid=1000,gid=1000,mode=0700,noexec,nosuid,nodev",
                    "/run/temporal-bootstrap-runtime:uid=1000,gid=1000,mode=0700,noexec,nosuid,nodev",
                ],
                "volumes": [
                    bind(
                        repo / "scripts/temporal/namespace-init.sh",
                        "/etc/temporal/namespace-init.sh",
                    ),
                    bind(
                        state / ".temporal-bootstrap/profile.toml",
                        "/run/temporal-bootstrap/profile.toml",
                    ),
                    bind(
                        state / ".secrets/temporal_api_key",
                        "/run/temporal-worker/token",
                    ),
                ],
            },
            "temporal": {
                "image": SERVER_IMAGE,
                "entrypoint": ["/bin/sh", "/etc/temporal/wave144-entrypoint.sh"],
                "environment": {
                    "POSTGRES_USER": "synthetic",
                    "POSTGRES_PWD": secrets.token_hex(16),
                    "BIND_ON_IP": str(ipaddress.IPv4Address(0)),
                    "TEMPORAL_JWKS_URL": "https://caddy:8443/.well-known/jwks.json",
                },
                "healthcheck": {
                    "test": [
                        "CMD-SHELL",
                        "wget -q --spider --timeout=3 http://127.0.0.1:8000/metrics || exit 1",
                    ]
                },
                "volumes": [
                    bind(
                        repo / "services/temporal/config.yaml",
                        "/etc/temporal/config/docker.yaml",
                    ),
                    bind(
                        repo / "services/temporal/entrypoint.sh",
                        "/etc/temporal/wave144-entrypoint.sh",
                    ),
                    {
                        "type": "volume",
                        "source": "temporal-jwks-ca",
                        "target": "/etc/temporal/jwks-ca",
                        "read_only": True,
                    },
                ],
            },
            "backend": {"volumes": []},
        },
    }


@pytest.mark.asyncio
async def test_exact_images_mounts_and_negative_controls(tmp_path: Path) -> None:
    state, repo = tmp_path / "state", tmp_path / "repo"
    state.mkdir()
    repo.mkdir()
    runner = tmp_path / "validate.ps1"
    runner.write_text(
        "param($Helper,$Config,$State,$Repo)\n"
        "$ErrorActionPreference='Stop'\n. $Helper\n"
        "$m=Get-Content -Raw -LiteralPath $Config | ConvertFrom-Json\n"
        "Assert-InPlaceTemporalBootstrapModel -ComposeModel $m -StateRoot $State -ProjectRoot $Repo\n",
        encoding="utf-8",
    )
    config = tmp_path / "compose.json"

    async def validate(value: dict) -> bool:
        config.write_text(json.dumps(value), encoding="utf-8")
        status, _ = await _run_powershell(
            runner, str(HELPER), str(config), str(state), str(repo)
        )
        return status == 0

    good = _model(state, repo)
    assert await validate(good)
    bad_models = []
    for service, field, value in (
        ("temporal-namespace-init", "image", "temporalio/admin-tools:1.30.7"),
        ("temporal-namespace-init", "image", ADMIN_IMAGE.replace("bbdf", "abcd")),
        (
            "temporal-namespace-init",
            "image",
            ADMIN_IMAGE.replace("temporalio", "other"),
        ),
        ("temporal-namespace-init", "build", {"context": str(repo)}),
        (
            "temporal-namespace-init",
            "healthcheck",
            {"test": ["CMD", "cat", "/run/temporal-bootstrap/profile.toml"]},
        ),
        (
            "temporal-namespace-init",
            "post_start",
            [{"command": "cat /run/temporal-bootstrap/profile.toml"}],
        ),
        (
            "temporal-namespace-init",
            "pre_stop",
            [{"command": "cat /run/temporal-bootstrap/profile.toml"}],
        ),
        ("temporal-namespace-init", "devices", ["/dev/null:/dev/null"]),
        ("temporal-namespace-init", "pid", "host"),
        ("temporal-namespace-init", "network_mode", "bridge"),
        ("temporal-namespace-init", "cap_add", ["SYS_ADMIN"]),
        ("temporal", "image", SERVER_IMAGE.replace("dc8d", "abcd")),
        (
            "temporal",
            "entrypoint",
            ["/bin/sh", "-c", "cat /run/temporal-bootstrap/profile.toml"],
        ),
        ("backend", "configs", ["unsafe"]),
        ("backend", "secrets", ["unsafe"]),
        ("backend", "volumes_from", ["unsafe"]),
        ("backend", "network_mode", "service:temporal"),
        ("backend", "pid", "host"),
        ("backend", "pid", "service:temporal"),
    ):
        altered = copy.deepcopy(good)
        altered["services"][service][field] = value
        bad_models.append(altered)
    for target, value in (
        ("BIND_ON_IP", "127.0.0.1"),
        ("TEMPORAL_JWKS_URL", "http://attacker/keys"),
    ):
        altered = copy.deepcopy(good)
        altered["services"]["temporal"]["environment"][target] = value
        bad_models.append(altered)
    for index, field, value in (
        (1, "read_only", False),
        (1, "source", str(state / "other.toml")),
    ):
        altered = copy.deepcopy(good)
        altered["services"]["temporal-namespace-init"]["volumes"][index][field] = value
        bad_models.append(altered)
    ancestor = copy.deepcopy(good)
    ancestor["services"]["backend"]["volumes"].append(
        {
            "type": "bind",
            "source": str(state.resolve()),
            "target": "/leak",
            "read_only": True,
        }
    )
    bad_models.append(ancestor)
    aliased_volume = copy.deepcopy(good)
    aliased_volume["volumes"]["trap"] = {
        "name": "project_trap",
        "driver": "local",
        "driver_opts": {
            "device": str(state / ".temporal-bootstrap"),
            "type": "none",
            "o": "bind",
        },
    }
    bad_models.append(aliased_volume)
    assert all([not await validate(value) for value in bad_models])

    private = state / ".temporal-bootstrap"
    private.mkdir()
    alias = state / "alias"
    if os.name == "nt":
        junction = tmp_path / "junction.ps1"
        junction.write_text(
            "param($Alias,$Target)\nNew-Item -ItemType Junction -Path $Alias -Target $Target | Out-Null\n",
            encoding="utf-8",
        )
        status, output = await _run_powershell(junction, str(alias), str(private))
        assert status == 0, output
    else:
        alias.symlink_to(private, target_is_directory=True)
    linked = copy.deepcopy(good)
    linked["services"]["backend"]["volumes"].append(
        {"type": "bind", "source": str(alias), "target": "/leak", "read_only": True}
    )
    assert not await validate(linked)


@pytest.mark.asyncio
async def test_existing_volume_inspection_fails_closed(tmp_path: Path) -> None:
    runner = tmp_path / "volume.ps1"
    runner.write_text(
        r"""
param([string]$Helper,[string]$Scenario)
$ErrorActionPreference = 'Stop'
. $Helper
function docker {
    if ($args[0] -ne 'volume') { throw 'unexpected Docker command' }
    if ($args[1] -eq 'ls') {
        if ($Scenario -eq 'list-error') { $global:LASTEXITCODE=1; return }
        $global:LASTEXITCODE=0
        return 'project_existing'
    }
    if ($args[1] -ne 'inspect') { throw 'unexpected volume operation' }
    if ($Scenario -eq 'inspect-error') { $global:LASTEXITCODE=1; return }
    $global:LASTEXITCODE=0
    if ($Scenario -eq 'invalid-json') { return 'invalid' }
    $driver = if ($Scenario -eq 'wrong-driver') { 'other' } else { 'local' }
    $name = if ($Scenario -eq 'wrong-name') { 'other' } else { 'project_existing' }
    $options = if ($Scenario -eq 'bind') { @{device='/synthetic/private';type='none';o='bind'} } else { $null }
    $scope = if ($Scenario -eq 'wrong-scope') { 'global' } else { 'local' }
    $encoded = if ($Scenario -eq 'array-options') { '[]' } else { ConvertTo-Json -InputObject $options -Compress }
    return "$name|$driver|$scope|$encoded"
}
$model = '{"volumes":{"existing":{"name":"project_existing"},"future":{"name":"project_future"}}}' | ConvertFrom-Json
Assert-InPlaceTemporalBootstrapVolumeSafety -ComposeModel $model
""",
        encoding="utf-8",
    )
    code, output = await _run_powershell(runner, str(HELPER), "safe")
    assert code == 0, output
    for scenario in (
        "list-error",
        "inspect-error",
        "invalid-json",
        "wrong-driver",
        "wrong-name",
        "wrong-scope",
        "array-options",
        "bind",
    ):
        code, _ = await _run_powershell(runner, str(HELPER), scenario)
        assert code != 0


@pytest.mark.asyncio
@pytest.mark.parametrize("scenario", ["success", "failure", "timeout"])
async def test_bounded_docker_process_handles_exit_and_timeout(
    tmp_path: Path, scenario: str
) -> None:
    runner = tmp_path / "bounded.ps1"
    runner.write_text(
        r"""
param($Helper,$Scenario)
$ErrorActionPreference='Stop'
. $Helper
$executable=(Get-Command pwsh -CommandType Application | Select-Object -First 1).Source
$program = switch ($Scenario) {
    'success' { "[Console]::Out.Write('synthetic-result')" }
    'failure' { '[Environment]::Exit(3)' }
    'timeout' { 'Start-Sleep -Seconds 5' }
    default { throw 'unknown scenario' }
}
$limit = if ($Scenario -eq 'timeout') { 1 } else { 5 }
$result=Invoke-TemporalBootstrapDockerBounded -Executable $executable -Arguments @('-NoProfile','-Command',$program) -TimeoutSeconds $limit
if ($Scenario -ne 'success' -or $result -cne 'synthetic-result') { throw 'unexpected result' }
""",
        encoding="utf-8",
    )
    code, _ = await _run_powershell(runner, str(HELPER), scenario)
    assert (code == 0) == (scenario == "success")


@pytest.mark.asyncio
@pytest.mark.parametrize("scenario", ["clean", "dirty", "missing", "invalid-sha"])
async def test_signed_bootstrap_source_is_checked_without_git_mutation(
    tmp_path: Path, scenario: str
) -> None:
    runner = tmp_path / "source.ps1"
    runner.write_text(
        r"""
param($Launcher,$Root,$Scenario)
$ErrorActionPreference='Stop'
$tokens=$null; $errors=$null
$ast=[System.Management.Automation.Language.Parser]::ParseFile($Launcher,[ref]$tokens,[ref]$errors)
if ($errors.Count) { throw 'invalid launcher' }
$node=$ast.Find({param($v) $v -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $v.Name -eq 'Assert-InPlaceTemporalBootstrapSource'},$true)
Invoke-Expression $node.Extent.Text
$script:calls=[System.Collections.Generic.List[string]]::new()
function Get-Command { [CmdletBinding()] param($Name,$CommandType) return [PSCustomObject]@{Source='fake-git'} }
function fake-git {
    $command = if ($args -ccontains 'cat-file') { 'cat-file' } elseif ($args -ccontains 'diff') { 'diff' } else { throw 'unexpected Git operation' }
    if ($args -cnotcontains '--no-optional-locks') { throw 'Git write-prevention option missing' }
    [void]$script:calls.Add($command)
    $global:LASTEXITCODE = if (($Scenario -eq 'dirty' -and $command -eq 'diff') -or
        ($Scenario -eq 'missing' -and $command -eq 'cat-file' -and $args[-1] -like '*:scripts/temporal/namespace-init.sh')) { 1 } else { 0 }
}
$sha = if ($Scenario -eq 'invalid-sha') { 'invalid' } else { 'a' * 40 }
$accepted=$true
try { Assert-InPlaceTemporalBootstrapSource -SourceSha $sha -Repository $Root } catch { $accepted=$false }
[PSCustomObject]@{accepted=$accepted;calls=@($script:calls)} | ConvertTo-Json -Compress
""",
        encoding="utf-8",
    )
    code, output = await _run_powershell(
        runner, str(ROOT / "start-docker.ps1"), str(tmp_path), scenario
    )
    assert code == 0, output
    receipt = json.loads(output)
    assert receipt["accepted"] == (scenario == "clean")
    if scenario == "invalid-sha":
        assert receipt["calls"] == []
    else:
        assert receipt["calls"].count("cat-file") == 8
        assert receipt["calls"].count("diff") == (scenario != "missing")


@pytest.mark.asyncio
async def test_all_running_peers_are_checked_without_environment_or_logs(
    tmp_path: Path,
) -> None:
    state = tmp_path / "state"
    bootstrap = state / ".temporal-bootstrap"
    bootstrap.mkdir(parents=True)
    profile = bootstrap / "profile.toml"
    profile.write_text("", encoding="utf-8")
    unrelated = tmp_path / "unrelated"
    unrelated.mkdir()
    server, peer, intermediate, init = (character * 64 for character in "abcd")
    runner = tmp_path / "running-peers.ps1"
    runner.write_text(
        r"""
param($Helper,$Fixture,$State,$Server,$Init)
$ErrorActionPreference='Stop'
. $Helper
$f=Get-Content -Raw -LiteralPath $Fixture | ConvertFrom-Json
$script:realPathIdentity=(Get-Item function:Get-TemporalBootstrapPathIdentity).ScriptBlock
function Get-TemporalBootstrapPathIdentity {
    param([string]$Path)
    if ($null -ne $f.identityAlias -and $Path -ceq [string]$f.identityAlias.source) {
        return (& $script:realPathIdentity -Path ([string]$f.identityAlias.target))
    }
    return (& $script:realPathIdentity -Path $Path)
}
function docker {
    $a=@($args | ForEach-Object { [string]$_ })
    $global:LASTEXITCODE=0
    if ($a[0] -ceq 'ps') {
        if ($a -ccontains '--filter' -or $a -cnotcontains '--no-trunc') { throw 'inventory was narrowed' }
        return $f.running
    }
    if ($a[0] -ceq 'volume' -and $a[1] -ceq 'inspect') {
        if ($a[3] -cne '{{.Name}}|{{.Driver}}|{{.Scope}}|{{json .Options}}') { throw 'unexpected volume fields' }
        $entry=$f.volumes.PSObject.Properties[$a[-1]]
        if ($null -eq $entry) { $global:LASTEXITCODE=1; return }
        $volume=$entry.Value
        return ([string]$a[-1] + '|' + [string]$volume.driver + '|' + [string]$volume.scope + '|' + (ConvertTo-Json -InputObject $volume.options -Compress))
    }
    if ($a[0] -cne 'container' -or $a[1] -cne 'inspect') { throw 'unexpected Docker operation' }
    $format=$a[3]; $key=$a[-1]
    if ($format -ceq '{{json .Id}}') {
        $entry=$f.ids.PSObject.Properties[$key]
    } elseif ($format -ceq '{{json .HostConfig.NetworkMode}}') {
        $entry=$f.modes.PSObject.Properties[$key]
    } elseif ($format -ceq '{{json .HostConfig.PidMode}}') {
        $entry=$f.pids.PSObject.Properties[$key]
    } elseif ($format -ceq '{{json .Mounts}}') {
        $entry=$f.mounts.PSObject.Properties[$key]
    } else { throw 'unexpected inspection fields' }
    if ($null -eq $entry) { $global:LASTEXITCODE=1; return }
    return (ConvertTo-Json -InputObject $entry.Value -Depth 20 -Compress)
}
try { Assert-TemporalBootstrapRunningPeers -ServerId $Server -InitId $Init -StateRoot $State; Write-Output 'ACCEPTED' }
catch { Write-Output 'REJECTED'; exit 2 }
""",
        encoding="utf-8",
    )
    fixture_path = tmp_path / "running.json"

    async def accepts(fixture: dict) -> bool:
        fixture_path.write_text(json.dumps(fixture), encoding="utf-8")
        code, output = await _run_powershell(
            runner, str(HELPER), str(fixture_path), str(state), server, init
        )
        assert output.strip() in {"ACCEPTED", "REJECTED"}
        return code == 0

    good = {
        "running": [server, peer],
        "ids": {server: server, intermediate: intermediate, "temporal-alias": server},
        "modes": {server: "project_internal", peer: "bridge", intermediate: "bridge"},
        "pids": {server: "", peer: "", intermediate: ""},
        "mounts": {server: [], peer: []},
        "volumes": {},
    }
    assert await accepts(good)
    for exposed in (profile, bootstrap, state):
        modified = copy.deepcopy(good)
        modified["mounts"][peer] = [{"Type": "bind", "Source": str(exposed)}]
        assert not await accepts(modified)

    alias = tmp_path / "profile-alias"
    if os.name == "nt":
        junction = tmp_path / "junction-peer.ps1"
        junction.write_text(
            "param($Alias,$Target)\nNew-Item -ItemType Junction -Path $Alias -Target $Target | Out-Null\n",
            encoding="utf-8",
        )
        code, output = await _run_powershell(junction, str(alias), str(bootstrap))
        assert code == 0, output
    else:
        alias.symlink_to(bootstrap, target_is_directory=True)
    modified = copy.deepcopy(good)
    modified["mounts"][peer] = [{"Type": "bind", "Source": str(alias)}]
    assert not await accepts(modified)

    safe = copy.deepcopy(good)
    safe["mounts"][peer] = [{"Type": "bind", "Source": str(unrelated)}]
    assert await accepts(safe)
    safe_alias = tmp_path / "unrelated-alias"
    if os.name == "nt":
        code, output = await _run_powershell(junction, str(safe_alias), str(unrelated))
        assert code == 0, output
    else:
        safe_alias.symlink_to(unrelated, target_is_directory=True)
    safe["mounts"][peer] = [{"Type": "bind", "Source": str(safe_alias)}]
    assert await accepts(safe)
    if os.name == "nt":
        network = copy.deepcopy(good)
        network["mounts"][peer] = [
            {"Type": "bind", "Source": r"\\127.0.0.1\unverified\state"}
        ]
        assert not await accepts(network)
    inode_alias = copy.deepcopy(good)
    inode_alias["mounts"][peer] = [{"Type": "bind", "Source": str(unrelated)}]
    inode_alias["identityAlias"] = {"source": str(unrelated), "target": str(bootstrap)}
    assert not await accepts(inode_alias)
    hardlink = tmp_path / "profile-hardlink"
    os.link(profile, hardlink)
    modified["mounts"][peer] = [{"Type": "bind", "Source": str(hardlink)}]
    assert not await accepts(modified)
    hardlink.unlink()
    volume = copy.deepcopy(good)
    volume["mounts"][peer] = [{"Type": "volume", "Name": "foreign_volume"}]
    volume["volumes"]["foreign_volume"] = {
        "driver": "local",
        "scope": "local",
        "options": None,
    }
    assert await accepts(volume)
    volume["volumes"]["foreign_volume"]["options"] = {
        "type": "none",
        "o": "bind",
        "device": str(state),
    }
    assert not await accepts(volume)
    direct = copy.deepcopy(good)
    direct["modes"][peer] = "container:temporal-alias"
    assert not await accepts(direct)
    chained = copy.deepcopy(good)
    chained["modes"][peer] = "container:" + intermediate
    chained["modes"][intermediate] = "container:" + server
    assert not await accepts(chained)
    for pid_mode in ("host", "unsupported", "container:" + server, "container:" + init):
        shared_pid = copy.deepcopy(good)
        shared_pid["ids"][init] = init
        shared_pid["pids"][peer] = pid_mode
        assert not await accepts(shared_pid)
    chained_pid = copy.deepcopy(good)
    chained_pid["pids"][peer] = "container:" + intermediate
    chained_pid["pids"][intermediate] = "container:" + server
    assert not await accepts(chained_pid)
    chained_pid["pids"][intermediate] = "host"
    assert not await accepts(chained_pid)
    missing_pid = copy.deepcopy(good)
    del missing_pid["pids"][peer]
    assert not await accepts(missing_pid)
    missing = copy.deepcopy(good)
    del missing["mounts"][peer]
    assert not await accepts(missing)
    malformed = copy.deepcopy(good)
    malformed["mounts"][peer] = [None]
    assert not await accepts(malformed)
    malformed["mounts"][peer] = {}
    assert not await accepts(malformed)
