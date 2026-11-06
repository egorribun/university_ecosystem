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
            "bind": {"create_host_path": False},
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
                    "TEMPORAL_SERVICES": "frontend,history,matching,worker,internal-frontend",
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
            "file-processor": {
                "volumes": [
                    bind(
                        state / ".secrets/temporal_api_key",
                        "/app/.secrets/temporal_api_key",
                    ),
                ],
            },
        },
    }


@pytest.mark.asyncio
async def test_exact_images_mounts_and_negative_controls(tmp_path: Path) -> None:
    state, repo = tmp_path / "state", tmp_path / "repo"
    state.mkdir()
    (state / ".secrets").mkdir()
    token_path = state / ".secrets/temporal_api_key"
    token_path.write_text("synthetic-worker-token", encoding="ascii")
    repo.mkdir()
    for relative in (
        "scripts/temporal/namespace-init.sh",
        "services/temporal/config.yaml",
        "services/temporal/entrypoint.sh",
    ):
        fixture = repo / relative
        fixture.parent.mkdir(parents=True, exist_ok=True)
        fixture.write_text("synthetic bind source\n", encoding="utf-8")
    runner = tmp_path / "validate.ps1"
    runner.write_text(
        "param($Helper,$Config,$State,$Repo)\n"
        "$ErrorActionPreference='Stop'\n. $Helper\n"
        "$m=Get-Content -Raw -LiteralPath $Config | ConvertFrom-Json\n"
        "Assert-InPlaceTemporalBootstrapModel -ComposeModel $m -StateRoot $State -ProjectRoot $Repo\n",
        encoding="utf-8",
    )
    config = tmp_path / "compose.json"

    async def validate(value: dict, *, expected: bool = False) -> bool:
        config.write_text(json.dumps(value), encoding="utf-8")
        status, output = await _run_powershell(
            runner, str(HELPER), str(config), str(state), str(repo)
        )
        if expected:
            assert status == 0, output
        return status == 0

    good = _model(state, repo)
    assert await validate(good, expected=True)
    canonical = copy.deepcopy(good)
    for service in canonical["services"].values():
        for mount in service.get("volumes", []):
            if mount.get("type") == "bind":
                mount["bind"] = {}
    assert await validate(canonical, expected=True)
    token_path.unlink()
    assert not await validate(good)
    token_path.write_text("synthetic-worker-token", encoding="ascii")
    bad_models = []
    for service_name, mount_index in (
        ("temporal-namespace-init", 0),
        ("temporal-namespace-init", 1),
        ("temporal-namespace-init", 2),
        ("file-processor", 0),
    ):
        for bind_value in (
            None,
            False,
            [],
            {"create_host_path": True},
            {"create_host_path": None},
            {"create_host_path": "false"},
            {"create_host_path": 0},
        ):
            altered = copy.deepcopy(canonical)
            altered["services"][service_name]["volumes"][mount_index]["bind"] = (
                bind_value
            )
            bad_models.append(altered)
        altered = copy.deepcopy(canonical)
        del altered["services"][service_name]["volumes"][mount_index]["bind"]
        bad_models.append(altered)
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
        ("TEMPORAL_SERVICES", "frontend,history,matching,worker"),
        (
            "TEMPORAL_SERVICES",
            "frontend,history,matching,worker,internal-frontend,admin",
        ),
    ):
        altered = copy.deepcopy(good)
        altered["services"]["temporal"]["environment"][target] = value
        bad_models.append(altered)
    server_environment = good["services"]["temporal"]["environment"]
    for value in (
        {
            key: item
            for key, item in server_environment.items()
            if key != "TEMPORAL_SERVICES"
        },
        {**server_environment, "UNREVIEWED_TEMPORAL_SETTING": "enabled"},
    ):
        altered = copy.deepcopy(good)
        altered["services"]["temporal"]["environment"] = value
        bad_models.append(altered)
    for scenario in ("missing-ca", "extra-server-mount", "writable-ca", "wrong-ca"):
        altered = copy.deepcopy(good)
        server_mounts = altered["services"]["temporal"]["volumes"]
        if scenario == "missing-ca":
            server_mounts.pop()
        elif scenario == "extra-server-mount":
            server_mounts.append(copy.deepcopy(server_mounts[0]))
        elif scenario == "writable-ca":
            server_mounts[2]["read_only"] = False
        else:
            server_mounts[2]["source"] = "unreviewed-ca-volume"
        bad_models.append(altered)
    altered = copy.deepcopy(good)
    altered["services"]["temporal-namespace-init"]["volumes"][1]["bind"][
        "create_host_path"
    ] = True
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
    exposed_token_mounts = (
        {
            "type": "bind",
            "source": str((state / ".secrets").resolve()),
            "target": "/leak",
            "read_only": True,
            "bind": {"create_host_path": False},
        },
        {
            "type": "bind",
            "source": str((state / ".secrets/temporal_api_key").resolve()),
            "target": "/wrong/target",
            "read_only": True,
            "bind": {"create_host_path": False},
        },
        {
            "type": "bind",
            "source": str((state / ".secrets/temporal_api_key").resolve()),
            "target": "/app/.secrets/temporal_api_key",
            "read_only": False,
            "bind": {"create_host_path": False},
        },
    )
    for service_name, mount in (
        ("backend", exposed_token_mounts[1]),
        ("file-processor", exposed_token_mounts[0]),
        ("file-processor", exposed_token_mounts[1]),
        ("file-processor", exposed_token_mounts[2]),
    ):
        altered = copy.deepcopy(good)
        altered["services"][service_name]["volumes"].append(copy.deepcopy(mount))
        bad_models.append(altered)
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
    for index, value in enumerate(bad_models):
        assert not await validate(value), f"unsafe model {index} was accepted"

    token_hardlink = state / ".secrets/temporal_api_key_alias"
    os.link(token_path, token_hardlink)
    linked_token = copy.deepcopy(good)
    linked_token["services"]["file-processor"]["volumes"].append(
        {
            "type": "bind",
            "source": str(token_hardlink.resolve()),
            "target": "/app/.secrets/temporal_api_key",
            "read_only": True,
            "bind": {"create_host_path": False},
        }
    )
    try:
        assert not await validate(linked_token)
    finally:
        token_hardlink.unlink()

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
$watch = [System.Diagnostics.Stopwatch]::StartNew()
try {
    Assert-InPlaceTemporalBootstrapVolumeSafety -ComposeModel $model
    $result = 'RESULT=ok'
} catch {
    $result = 'RESULT=ERROR: ' + $_.Exception.Message
} finally {
    $watch.Stop()
}
Write-Output $result
Write-Output ('ELAPSED=' + $watch.ElapsedMilliseconds)
""",
        encoding="utf-8",
    )
    code, output = await _run_powershell(runner, str(HELPER), "safe")
    assert code == 0, output
    assert "RESULT=ok" in output.splitlines(), output
    elapsed_line = next(
        line for line in output.splitlines() if line.startswith("ELAPSED=")
    )
    assert int(elapsed_line.removeprefix("ELAPSED=")) >= 0, output

    expected_errors = {
        "list-error": "Cannot inspect Temporal bootstrap volume inventory.",
        "inspect-error": "Cannot inspect an existing Temporal bootstrap volume.",
        "invalid-json": "An existing volume is not an unconfigured local volume.",
        "wrong-driver": "An existing volume is not an unconfigured local volume.",
        "wrong-name": "An existing volume is not an unconfigured local volume.",
        "wrong-scope": "An existing volume is not an unconfigured local volume.",
        "array-options": "An existing volume has unverified backing options.",
        "bind": "An existing volume has unverified backing options.",
    }
    for scenario, message in expected_errors.items():
        code, output = await _run_powershell(runner, str(HELPER), scenario)
        assert code == 0, output
        assert f"RESULT=ERROR: {message}" in output.splitlines(), output
        elapsed_line = next(
            line for line in output.splitlines() if line.startswith("ELAPSED=")
        )
        assert int(elapsed_line.removeprefix("ELAPSED=")) >= 0, output


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
$watch = [System.Diagnostics.Stopwatch]::StartNew()
try {
    $result = Invoke-TemporalBootstrapDockerBounded -Executable $executable -Arguments @('-NoProfile','-Command',$program) -TimeoutSeconds $limit
    if ($Scenario -ne 'success' -or $result -cne 'synthetic-result') { throw 'unexpected result' }
    $status = 'RESULT=ok'
} catch {
    $status = 'RESULT=ERROR: ' + $_.Exception.Message
} finally {
    $watch.Stop()
}
Write-Output $status
Write-Output ('ELAPSED=' + $watch.ElapsedMilliseconds)
""",
        encoding="utf-8",
    )
    code, output = await _run_powershell(runner, str(HELPER), scenario)
    assert code == 0, output
    result_line = next(
        line for line in output.splitlines() if line.startswith("RESULT=")
    )
    elapsed_line = next(
        line for line in output.splitlines() if line.startswith("ELAPSED=")
    )
    elapsed = int(elapsed_line.removeprefix("ELAPSED="))
    expected_result = {
        "success": "RESULT=ok",
        "failure": "RESULT=ERROR: Temporal bootstrap Docker command failed.",
        "timeout": "RESULT=ERROR: Temporal bootstrap Docker command timed out.",
    }[scenario]
    assert result_line == expected_result, output
    assert elapsed >= 0, output
    if scenario == "timeout":
        assert elapsed < 4000, output


_SIGNED_SOURCE_PATHS = (
    "start-docker.ps1",
    "docker-compose.full.yml",
    "docker-compose.live.yml",
    "infrastructure/Caddyfile",
    "services/temporal/config.yaml",
    "services/temporal/entrypoint.sh",
    "scripts/temporal/bootstrap-functions.ps1",
    "scripts/temporal/namespace-init.sh",
)


async def _synthetic_source_repo(
    root: Path, *, omit: str | None = None
) -> tuple[Path, dict[str, str]]:
    """Create real, disposable Git metadata; never access the project index."""
    repo = root / "source-repo"
    repo.mkdir()
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith("GIT_")}
    env.update(
        {
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_TERMINAL_PROMPT": "0",
            "GIT_AUTHOR_NAME": "Synthetic",
            "GIT_AUTHOR_EMAIL": "synthetic@example.invalid",
            "GIT_COMMITTER_NAME": "Synthetic",
            "GIT_COMMITTER_EMAIL": "synthetic@example.invalid",
        }
    )
    await _git(repo, env, "init", "--quiet")
    await _git(repo, env, "config", "core.autocrlf", "false")
    (repo / ".gitattributes").write_bytes(b"* text=auto eol=lf\n")
    for name in _SIGNED_SOURCE_PATHS:
        if name == omit:
            continue
        target = repo / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(("synthetic " + name + "\nsecond line\n").encode())
    await _git(repo, env, "add", "--", ".")
    await _git(repo, env, "commit", "--quiet", "-m", "synthetic source")
    return repo, env


async def _git(
    repo: Path, env: dict[str, str], *args: str, data: bytes | None = None
) -> bytes:
    executable = shutil.which("git")
    assert executable
    process = await asyncio.create_subprocess_exec(
        executable,
        "-C",
        str(repo),
        *args,
        stdin=asyncio.subprocess.PIPE
        if data is not None
        else asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
    )
    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(data), timeout=20)
    except BaseException:
        if process.returncode is None:
            process.kill()
            await process.wait()
        raise
    assert process.returncode == 0, stderr.decode("utf-8", errors="replace")
    return stdout


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("scenario", "expected"),
    [
        ("clean", "ACCEPTED"),
        ("crlf", "ACCEPTED"),
        ("dirty", "DIFFERS"),
        ("missing-worktree", "DIFFERS"),
        ("missing-commit", "MISSING"),
        ("invalid-sha", "INVALID"),
        ("replace", "DIFFERS"),
        ("assume-unchanged", "DIFFERS"),
        ("skip-worktree", "DIFFERS"),
        ("git-filter", "DIFFERS"),
        ("tree-symlink", "DIFFERS"),
        ("worktree-symlink-or-directory-if-unavailable", "DIFFERS"),
        ("fifo-or-directory-if-unavailable", "DIFFERS"),
        ("git-env", "ACCEPTED"),
    ],
)
async def test_signed_bootstrap_source_is_checked_without_git_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, scenario: str, expected: str
) -> None:
    omit = _SIGNED_SOURCE_PATHS[-1] if scenario == "missing-commit" else None
    repo, env = await _synthetic_source_repo(tmp_path, omit=omit)
    signed_sha = (await _git(repo, env, "rev-parse", "HEAD")).decode().strip()
    target_name = _SIGNED_SOURCE_PATHS[1]
    target = repo / target_name
    if scenario == "crlf":
        for name in _SIGNED_SOURCE_PATHS:
            source = repo / name
            source.write_bytes(source.read_bytes().replace(b"\n", b"\r\n"))
    elif scenario == "dirty":
        target.write_bytes(b"different content\n")
    elif scenario == "missing-worktree":
        target.unlink()
    elif scenario == "invalid-sha":
        signed_sha = "invalid"
    elif scenario == "replace":
        target.write_bytes(b"replacement content\n")
        await _git(repo, env, "add", "--", target_name)
        await _git(repo, env, "commit", "--quiet", "-m", "replacement source")
        replacement = (await _git(repo, env, "rev-parse", "HEAD")).decode().strip()
        await _git(repo, env, "replace", signed_sha, replacement)
    elif scenario == "assume-unchanged":
        await _git(repo, env, "update-index", "--assume-unchanged", "--", target_name)
        target.write_bytes(b"hidden change\n")
    elif scenario == "skip-worktree":
        await _git(repo, env, "update-index", "--skip-worktree", "--", target_name)
        target.write_bytes(b"hidden change\n")
    elif scenario == "git-filter":
        (repo / ".git/info/attributes").write_text(
            target_name + " filter=synthetic\n", encoding="utf-8"
        )
        await _git(
            repo,
            env,
            "config",
            "filter.synthetic.clean",
            "git show HEAD:" + target_name,
        )
        await _git(repo, env, "config", "filter.synthetic.required", "true")
        target.write_bytes(b"hidden by clean filter\n")
    elif scenario == "tree-symlink":
        await _git(repo, env, "config", "core.symlinks", "false")
        content = b"synthetic-link-target"
        blob = (
            (await _git(repo, env, "hash-object", "-w", "--stdin", data=content))
            .decode()
            .strip()
        )
        await _git(
            repo,
            env,
            "update-index",
            "--add",
            "--cacheinfo",
            "120000",
            blob,
            target_name,
        )
        await _git(repo, env, "commit", "--quiet", "-m", "synthetic symlink")
        signed_sha = (await _git(repo, env, "rev-parse", "HEAD")).decode().strip()
        target.write_bytes(content)
    elif scenario == "worktree-symlink-or-directory-if-unavailable":
        replacement = tmp_path / "regular-target"
        replacement.write_bytes(target.read_bytes())
        target.unlink()
        try:
            target.symlink_to(replacement)
        except (OSError, NotImplementedError):
            target.mkdir()
        assert target.is_symlink() or target.is_dir()
    elif scenario == "fifo-or-directory-if-unavailable":
        target.unlink()
        if hasattr(os, "mkfifo"):
            try:
                os.mkfifo(target)
            except (OSError, NotImplementedError):
                target.mkdir()
        else:
            target.mkdir()
        assert target.is_fifo() or target.is_dir()
    elif scenario == "git-env":
        other = tmp_path / "other-repo"
        other.mkdir()
        await _git(other, env, "init", "--quiet")
        monkeypatch.setenv("GIT_DIR", str(other / ".git"))
        monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
        monkeypatch.setenv("GIT_CONFIG_KEY_0", "core.bare")
        monkeypatch.setenv("GIT_CONFIG_VALUE_0", "true")

    runner = tmp_path / "source.ps1"
    runner.write_text(
        r"""
param($Launcher,$Root,$SourceSha)
$ErrorActionPreference='Stop'
$tokens=$null; $errors=$null
$ast=[System.Management.Automation.Language.Parser]::ParseFile($Launcher,[ref]$tokens,[ref]$errors)
if ($errors.Count) { throw 'invalid launcher' }
$node=$ast.Find({param($v) $v -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $v.Name -eq 'Assert-InPlaceTemporalBootstrapSource'},$true)
if ($null -eq $node) { throw 'source guard missing' }
Invoke-Expression $node.Extent.Text
try {
    Assert-InPlaceTemporalBootstrapSource -SourceSha $SourceSha -Repository $Root
    Write-Output 'ACCEPTED'
} catch {
    switch -Exact ($_.Exception.Message) {
        'Temporal bootstrap source differs from the signed commit.' { Write-Output 'DIFFERS' }
        'Temporal bootstrap source is missing from the signed commit.' { Write-Output 'MISSING' }
        'Temporal bootstrap source identity is invalid.' { Write-Output 'INVALID' }
        default { Write-Output 'UNEXPECTED'; exit 4 }
    }
}
""",
        encoding="utf-8",
    )
    code, output = await _run_powershell(
        runner, str(ROOT / "start-docker.ps1"), str(repo), signed_sha
    )
    assert code == 0, output
    assert output.strip() == expected


@pytest.mark.asyncio
async def test_all_running_peers_are_checked_without_environment_or_logs(
    tmp_path: Path,
) -> None:
    state = tmp_path / "state"
    bootstrap = state / ".temporal-bootstrap"
    bootstrap.mkdir(parents=True)
    profile = bootstrap / "profile.toml"
    profile.write_text("", encoding="utf-8")
    secrets_dir = state / ".secrets"
    secrets_dir.mkdir()
    worker_token = secrets_dir / "temporal_api_key"
    worker_token.write_text("synthetic-worker-token", encoding="ascii")
    unrelated = tmp_path / "unrelated"
    unrelated.mkdir()
    server, peer, intermediate, init = (character * 64 for character in "abcd")
    project = "ue-live-0123456789abcdef"
    runner = tmp_path / "running-peers.ps1"
    runner.write_text(
        r"""
param($Helper,$Fixture,$State,$Server,$Init,$ProjectName)
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
    } elseif ($format -ceq '{"Labels":{{json .Config.Labels}},"Mounts":{{json .Mounts}}}') {
        $labels=$f.labels.PSObject.Properties[$key]
        $mounts=$f.mounts.PSObject.Properties[$key]
        if ($null -eq $labels -or $null -eq $mounts) { $global:LASTEXITCODE=1; return }
        return (ConvertTo-Json -InputObject @{ Labels=$labels.Value; Mounts=@($mounts.Value) } -Depth 20 -Compress)
    } else { throw 'unexpected inspection fields' }
    if ($null -eq $entry) { $global:LASTEXITCODE=1; return }
    return (ConvertTo-Json -InputObject $entry.Value -Depth 20 -Compress)
}
try { Assert-TemporalBootstrapRunningPeers -ServerId $Server -InitId $Init -StateRoot $State -ExpectedProjectName $ProjectName; Write-Output 'ACCEPTED' }
catch { Write-Output 'REJECTED'; exit 2 }
""",
        encoding="utf-8",
    )
    fixture_path = tmp_path / "running.json"

    async def accepts(fixture: dict) -> bool:
        fixture_path.write_text(json.dumps(fixture), encoding="utf-8")
        code, output = await _run_powershell(
            runner, str(HELPER), str(fixture_path), str(state), server, init, project
        )
        assert output.strip() in {"ACCEPTED", "REJECTED"}
        return code == 0

    good = {
        "running": [server, peer],
        "ids": {server: server, intermediate: intermediate, "temporal-alias": server},
        "modes": {server: "project_internal", peer: "bridge", intermediate: "bridge"},
        "pids": {server: "", peer: "", intermediate: ""},
        "labels": {
            server: {
                "com.docker.compose.project": project,
                "com.docker.compose.service": "temporal",
            },
            peer: {
                "com.docker.compose.project": project,
                "com.docker.compose.service": "file-processor",
            },
        },
        "mounts": {
            server: [],
            peer: [
                {
                    "Type": "bind",
                    "Source": str(worker_token),
                    "Destination": "/app/.secrets/temporal_api_key",
                    "RW": False,
                }
            ],
        },
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

    modified = copy.deepcopy(good)
    modified["mounts"][peer] = [
        {
            "Type": "bind",
            "Source": str(secrets_dir),
            "Destination": "/app/.secrets",
            "RW": False,
        }
    ]
    assert not await accepts(modified)

    modified = copy.deepcopy(good)
    modified["labels"][peer]["com.docker.compose.service"] = "backend"
    assert not await accepts(modified)

    modified = copy.deepcopy(good)
    modified["labels"][peer]["com.docker.compose.project"] = "unowned-project"
    assert not await accepts(modified)

    modified = copy.deepcopy(good)
    modified["mounts"][peer][0]["RW"] = True
    assert not await accepts(modified)

    token_alias = tmp_path / "worker-token-alias"
    token_alias.symlink_to(worker_token)
    modified = copy.deepcopy(good)
    modified["mounts"][peer][0]["Source"] = str(token_alias)
    assert not await accepts(modified)

    safe = copy.deepcopy(good)
    safe["mounts"][peer].append(
        {
            "Type": "bind",
            "Source": str(unrelated),
            "Destination": "/unrelated",
            "RW": False,
        }
    )
    assert await accepts(safe)
    safe_alias = tmp_path / "unrelated-alias"
    if os.name == "nt":
        code, output = await _run_powershell(junction, str(safe_alias), str(unrelated))
        assert code == 0, output
    else:
        safe_alias.symlink_to(unrelated, target_is_directory=True)
    safe["mounts"][peer].append(
        {
            "Type": "bind",
            "Source": str(safe_alias),
            "Destination": "/safe-alias",
            "RW": False,
        }
    )
    assert await accepts(safe)
    if os.name == "nt":
        network = copy.deepcopy(good)
        network["mounts"][peer].append(
            {
                "Type": "bind",
                "Source": r"\\127.0.0.1\unverified\state",
                "Destination": "/network",
                "RW": False,
            }
        )
        assert not await accepts(network)
    inode_alias = copy.deepcopy(good)
    inode_alias["mounts"][peer].append(
        {
            "Type": "bind",
            "Source": str(unrelated),
            "Destination": "/inode-alias",
            "RW": False,
        }
    )
    inode_alias["identityAlias"] = {"source": str(unrelated), "target": str(bootstrap)}
    assert not await accepts(inode_alias)
    hardlink = tmp_path / "profile-hardlink"
    os.link(profile, hardlink)
    modified["mounts"][peer] = [
        {
            "Type": "bind",
            "Source": str(hardlink),
            "Destination": "/hardlink",
            "RW": False,
        }
    ]
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
