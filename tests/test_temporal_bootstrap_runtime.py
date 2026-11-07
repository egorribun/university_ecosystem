"""Independent fake-daemon checks for the private Temporal runtime guard.

Executes the real candidate PowerShell guard against synthetic inspect output;
no Docker executable, daemon, container, or real credential is used. Model and
helper bytes are hash-checked over each run. This is not a runtime stand proof.
"""

from __future__ import annotations

import asyncio
import copy
import hashlib
import ipaddress
import json
import os
import secrets
import shutil
import tempfile
import unittest
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "scripts" / "temporal" / "bootstrap-functions.ps1"
PROJECT = "ue-live-0123456789abcdef"
SERVER_ID = "a" * 64
INIT_ID = "b" * 64
SERVER_IMAGE_ID = "sha256:" + "1" * 64
INIT_IMAGE_ID = "sha256:" + "2" * 64
SERVER_REF = "temporalio/server:1.30.7@sha256:dc8dc6fffa29de3bad7f5c39cb406db3104053fbb0c2494e7c76016211bc99b0"
INIT_REF = "temporalio/admin-tools:1.30.7@sha256:bbdf5fe91b288c17442efbbfb42daa3668d09cfa8ebeb078d6fd475a97f66b81"
HEALTH = [
    "CMD-SHELL",
    "wget -q --spider --timeout=3 http://127.0.0.1:8000/metrics || exit 1",
]
PATH_ENTRY = "PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
CONTAINER_TEMP = str(PurePosixPath("/", "tmp"))

RUNNER = r"""
param([string]$Helper, [string]$Fixture, [string]$State, [string]$Repo)
$ErrorActionPreference = 'Stop'
. $Helper
$script:f = Get-Content -LiteralPath $Fixture -Raw | ConvertFrom-Json
$script:ComposeArgs = @('-p', [string]$f.model.name, '-f', 'synthetic.yml')
$script:EnvFile = 'synthetic.env'
$script:fixtureError = $false
function Fail-Fixture { $script:fixtureError = $true; throw 'synthetic fixture contract error' }
function docker {
    $a = @($args | ForEach-Object { [string]$_ })
    if ($f.dockerFailure -eq $true) { Write-Error 'synthetic docker command detail' -ErrorAction Continue; $global:LASTEXITCODE = 5; return }
    if ($f.dockerOutputShapeFailure -eq $true) { $global:LASTEXITCODE = 0; return @('synthetic stdout one', 'synthetic stdout two') }
    $global:LASTEXITCODE = 0
    if ($a[0] -ceq 'image' -and $a[1] -ceq 'inspect') {
        if ($a[2] -cne '--format' -or $a[3] -cne '{"Id":{{json .Id}},"Config":{"User":{{json .Config.User}},"Env":{{json .Config.Env}}}}') { Fail-Fixture }
        if ($a[-1] -ceq $f.model.services.temporal.image) { return ($f.serverImage | ConvertTo-Json -Depth 30 -Compress) }
        if ($a[-1] -ceq $f.model.services.'temporal-namespace-init'.image) { return ($f.initImage | ConvertTo-Json -Depth 30 -Compress) }
    } elseif ($a[0] -ceq 'compose' -and $a -ccontains 'ps' -and $a -ccontains '--no-trunc') {
        if ($a[-1] -ceq 'temporal') { return $f.serverIds }
        if ($a[-1] -ceq 'temporal-namespace-init') { return $f.initIds }
    } elseif ($a[0] -ceq 'ps') {
        if (($a -join '|') -cne 'ps|--no-trunc|--quiet') { Fail-Fixture }
        return $f.runningIds
    } elseif ($a[0] -ceq 'volume' -and $a[1] -ceq 'inspect') {
        if ($a[2] -cne '--format' -or $a[3] -cne '{{.Name}}|{{.Driver}}|{{.Scope}}|{{json .Options}}') { Fail-Fixture }
        $entry = $f.volumeInfo.PSObject.Properties[$a[-1]]
        if ($null -eq $entry) { Fail-Fixture }
        return [string]$entry.Value
    } elseif ($a[0] -ceq 'container' -and $a[1] -ceq 'inspect') {
        if ($a[2] -cne '--format' -or $a.Count -ne 5) { Fail-Fixture }
        if ([string]$f.peerFailure -ceq $a[-1]) { $global:LASTEXITCODE = 5; return }
        if ($a[3] -ceq '{{json .HostConfig.NetworkMode}}') {
            $entry = $f.peerModes.PSObject.Properties[$a[-1]]
            if ($null -eq $entry) { Fail-Fixture }
            return (ConvertTo-Json -InputObject ([string]$entry.Value) -Compress)
        }
        if ($a[3] -ceq '{{json .HostConfig.PidMode}}') {
            $entry = $f.peerPidModes.PSObject.Properties[$a[-1]]
            if ($null -eq $entry) { Fail-Fixture }
            return (ConvertTo-Json -InputObject ([string]$entry.Value) -Compress)
        }
        if ($a[3] -ceq '{"Labels":{{json .Config.Labels}},"Mounts":{{json .Mounts}}}') {
            $label = $f.peerLabels.PSObject.Properties[$a[-1]]
            $entry = $f.peerMounts.PSObject.Properties[$a[-1]]
            if ($null -eq $label -or $null -eq $entry) { Fail-Fixture }
            if ($entry.Value -is [string] -and $entry.Value -ceq 'null') {
                $mounts = $null
            } elseif ($entry.Value -is [string] -and $entry.Value -ceq '[]') {
                $mounts = @()
            } elseif ($entry.Value -is [string]) {
                $mounts = [string]$entry.Value
            } else {
                $mounts = @($entry.Value)
            }
            return (ConvertTo-Json -InputObject @{ Labels=$label.Value; Mounts=$mounts } -Depth 30 -Compress)
        }
        if ($a[3] -ceq '{{json .Mounts}}') {
            $entry = $f.peerMounts.PSObject.Properties[$a[-1]]
            if ($null -eq $entry) { Fail-Fixture }
            if ($entry.Value -is [string]) { return [string]$entry.Value }
            return (ConvertTo-Json -InputObject @($entry.Value) -Depth 30 -Compress)
        }
        if ($a[3] -ceq '{{json .Id}}') {
            $entry = $f.peerTargets.PSObject.Properties[$a[-1]]
            if ($null -eq $entry) { $global:LASTEXITCODE = 1; return }
            return (ConvertTo-Json -InputObject ([string]$entry.Value) -Compress)
        }
        $allowed = @('.Id','.Image','.Config.User','.Config.Env','.Config.Labels','.Config.Entrypoint','.Config.Cmd',
            '(index .Config "Healthcheck")','.State.Status','.State.Running','.State.Health.Status','.HostConfig.NetworkMode',
            '.HostConfig.ReadonlyRootfs','.HostConfig.Privileged','.HostConfig.CapDrop','.HostConfig.CapAdd',
            '.HostConfig.SecurityOpt','.HostConfig.PidMode','.HostConfig.UsernsMode','.HostConfig.Devices',
            '.HostConfig.DeviceCgroupRules','(index .HostConfig "Tmpfs")','.Mounts') | Sort-Object -CaseSensitive
        $matches = @([regex]::Matches($a[3], '{{json ([^}]+)}}') | ForEach-Object { $_.Groups[1].Value } | Sort-Object -CaseSensitive)
        $remaining = [regex]::Replace($a[3], '{{json [^}]+}}|{{if index \.State "Health"}}|{{else}}|{{end}}', '')
        if (($matches -join '|') -cne ($allowed -join '|') -or $remaining.Contains('{{')) { Fail-Fixture }
        if ($a[-1] -ceq $f.serverIds[0]) { return ($f.server | ConvertTo-Json -Depth 30 -Compress) }
        if ($a[-1] -ceq $f.initIds[0]) { return ($f.init | ConvertTo-Json -Depth 30 -Compress) }
    }
    Fail-Fixture
}
try {
    $id = Assert-InPlaceTemporalBootstrapRuntime -ComposeModel $f.model -StateRoot $State -ProjectRoot $Repo
    if ([string]$id -cne [string]$f.initIds[0]) { throw 'unexpected returned container id' }
    Write-Output 'ACCEPTED'
} catch {
    if ($script:fixtureError) { Write-Output 'FIXTURE_ERROR'; exit 3 }
    if ($f.dockerFailure -eq $true -or $f.dockerOutputShapeFailure -eq $true) { [Console]::Error.WriteLine("THROWN_EXCEPTION=$($_.Exception.Message)") }
    Write-Output 'REJECTED'
    exit 2
}
"""


def fixture(state: Path, repo: Path) -> tuple[dict, str]:
    secret = secrets.token_hex(16)
    model_env = {
        "BIND_ON_IP": str(ipaddress.IPv4Address(0)),
        "POSTGRES_USER": "ue_temporal",
        "POSTGRES_PWD": secret,
        "TEMPORAL_JWKS_URL": "https://caddy:8443/.well-known/jwks.json",
        "TEMPORAL_SERVICES": "frontend,history,matching,worker,internal-frontend",
    }

    def labels(name):
        return {
            "com.docker.compose.project": PROJECT,
            "com.docker.compose.service": name,
        }

    def bind(source, target):
        return {
            "Type": "bind",
            "Source": str(source),
            "Destination": target,
            "RW": False,
        }

    def image(image_id):
        return {"Id": image_id, "Config": {"User": "temporal", "Env": [PATH_ENTRY]}}

    server = {
        "Id": SERVER_ID,
        "Image": SERVER_IMAGE_ID,
        "Config": {
            "User": "temporal",
            "Labels": labels("temporal"),
            "Entrypoint": ["/bin/sh", "/etc/temporal/wave144-entrypoint.sh"],
            "Cmd": None,
            "Healthcheck": {"Test": HEALTH},
            "Env": [
                PATH_ENTRY,
                *[f"{key}={value}" for key, value in model_env.items()],
            ],
        },
        "State": {"Running": True, "Health": {"Status": "healthy"}},
        "HostConfig": {
            "Privileged": False,
            "CapAdd": None,
            "NetworkMode": PROJECT + "_internal",
            "PidMode": "",
            "UsernsMode": "",
        },
        "Mounts": [
            bind(
                repo / "services/temporal/config.yaml",
                "/etc/temporal/config/docker.yaml",
            ),
            bind(
                repo / "services/temporal/entrypoint.sh",
                "/etc/temporal/wave144-entrypoint.sh",
            ),
            {
                "Type": "volume",
                "Name": PROJECT + "_temporal-jwks-ca",
                "Destination": "/etc/temporal/jwks-ca",
                "RW": False,
            },
        ],
    }
    init = {
        "Id": INIT_ID,
        "Image": INIT_IMAGE_ID,
        "Config": {
            "User": "1000:1000",
            "Labels": labels("temporal-namespace-init"),
            "Entrypoint": ["/bin/sh", "/etc/temporal/namespace-init.sh"],
            "Cmd": None,
            "Healthcheck": None,
            "Env": [PATH_ENTRY],
        },
        "State": {"Status": "created", "Running": False},
        "HostConfig": {
            "NetworkMode": "container:" + SERVER_ID,
            "ReadonlyRootfs": True,
            "Privileged": False,
            "CapDrop": ["ALL"],
            "CapAdd": None,
            "SecurityOpt": ["no-new-privileges:true"],
            "PidMode": "",
            "UsernsMode": "",
            "Tmpfs": {
                name: "uid=1000,gid=1000,mode=0700,noexec,nosuid,nodev"
                for name in (CONTAINER_TEMP, "/run/temporal-bootstrap-runtime")
            },
        },
        "Mounts": [
            bind(
                repo / "scripts/temporal/namespace-init.sh",
                "/etc/temporal/namespace-init.sh",
            ),
            bind(
                state / ".temporal-bootstrap/profile.toml",
                "/run/temporal-bootstrap/profile.toml",
            ),
            bind(state / ".secrets/temporal_api_key", "/run/temporal-worker/token"),
        ],
    }
    peer_id = "c" * 64
    safe_bind = state.parent / "safe-data" / "sample.txt"
    return {
        "model": {
            "name": PROJECT,
            "services": {
                "temporal": {"image": SERVER_REF, "environment": model_env},
                "temporal-namespace-init": {"image": INIT_REF},
            },
        },
        "serverImage": image(SERVER_IMAGE_ID),
        "initImage": image(INIT_IMAGE_ID),
        "serverIds": [SERVER_ID],
        "initIds": [INIT_ID],
        "server": server,
        "init": init,
        "runningIds": [SERVER_ID, peer_id],
        "peerLabels": {
            SERVER_ID: labels("temporal"),
            peer_id: labels("file-processor"),
        },
        "peerModes": {SERVER_ID: PROJECT + "_internal", peer_id: "bridge"},
        "peerPidModes": {SERVER_ID: "", peer_id: ""},
        "peerMounts": {
            SERVER_ID: copy.deepcopy(server["Mounts"]),
            peer_id: [
                bind(safe_bind, "/data/sample.txt"),
                {"Type": "volume", "Name": "foreign-safe"},
                {"Type": "tmpfs"},
            ],
        },
        "peerTargets": {SERVER_ID: SERVER_ID, INIT_ID: INIT_ID},
        "volumeInfo": {
            PROJECT + "_temporal-jwks-ca": PROJECT
            + "_temporal-jwks-ca|local|local|null",
            "foreign-safe": "foreign-safe|local|local|{}",
        },
    }, secret


async def run_powershell(arguments: list[str]) -> tuple[int, str, str]:
    process = await asyncio.create_subprocess_exec(
        *arguments,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=25)
    except TimeoutError:
        process.kill()
        await process.wait()
        raise
    return process.returncode, stdout.decode("utf-8"), stderr.decode("utf-8")


class RuntimeGuard(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pwsh = shutil.which("pwsh")
        if not cls.pwsh:
            raise RuntimeError("PowerShell is required")
        cls.pwsh = str(Path(cls.pwsh).resolve(strict=True))
        cls.helper_hash = hashlib.sha256(HELPER.read_bytes()).hexdigest()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="ue-temporal-runtime-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.state = self.root / "state"
        self.state.mkdir()
        self.repo = self.root / "repo"
        self.repo.mkdir()
        for path in (
            self.state / ".temporal-bootstrap/profile.toml",
            self.state / ".secrets/temporal_api_key",
            self.repo / "services/temporal/config.yaml",
            self.repo / "services/temporal/entrypoint.sh",
            self.repo / "scripts/temporal/namespace-init.sh",
            self.root / "safe-data/sample.txt",
        ):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("synthetic", encoding="utf-8")
        (self.root / "profile-alias").symlink_to(
            self.state / ".temporal-bootstrap", target_is_directory=True
        )
        self.runner = self.root / "runner.ps1"
        self.runner.write_text(RUNNER, encoding="utf-8")
        self.json_path = self.root / "fixture.json"
        self.good, self.secret = fixture(self.state, self.repo)

    def check(self, value: dict, accepted: bool):
        self.json_path.write_text(json.dumps(value), encoding="utf-8")
        code, stdout, stderr = asyncio.run(
            run_powershell(
                [
                    self.pwsh,
                    "-NoProfile",
                    "-NonInteractive",
                    "-File",
                    str(self.runner),
                    str(HELPER),
                    str(self.json_path),
                    str(self.state),
                    str(self.repo),
                ]
            )
        )
        self.assertEqual(
            hashlib.sha256(HELPER.read_bytes()).hexdigest(), self.helper_hash
        )
        self.assertNotIn(self.secret, stdout + stderr)
        self.assertEqual(code, 0 if accepted else 2, stdout + stderr)
        self.assertEqual(stdout.strip(), "ACCEPTED" if accepted else "REJECTED")

    def test_baseline(self):
        self.check(self.good, True)

    def test_omitted_optional_fields_preserve_fail_closed_semantics(self):
        omitted_optional = copy.deepcopy(self.good)
        del omitted_optional["init"]["Config"]["Healthcheck"]
        omitted_optional["init"]["State"].pop("Health", None)
        self.check(omitted_optional, True)

        missing_server_health = copy.deepcopy(self.good)
        del missing_server_health["server"]["State"]["Health"]
        self.check(missing_server_health, False)

        missing_init_tmpfs = copy.deepcopy(self.good)
        del missing_init_tmpfs["init"]["HostConfig"]["Tmpfs"]
        self.check(missing_init_tmpfs, False)

        for label, mutate in (
            (
                "missing required init tmpfs target",
                lambda value: value["init"]["HostConfig"]["Tmpfs"].pop(
                    "/run/temporal-bootstrap-runtime"
                ),
            ),
            (
                "unexpected init tmpfs target",
                lambda value: value["init"]["HostConfig"]["Tmpfs"].__setitem__(
                    "/unexpected", "uid=1000,gid=1000,mode=0700,noexec,nosuid,nodev"
                ),
            ),
            (
                "unsafe init tmpfs options",
                lambda value: value["init"]["HostConfig"]["Tmpfs"].__setitem__(
                    "/run/temporal-bootstrap-runtime", "mode=0777"
                ),
            ),
        ):
            with self.subTest(label=label):
                value = copy.deepcopy(self.good)
                mutate(value)
                self.check(value, False)

    def test_inspection_failure_emits_only_allowlisted_phase_and_preserves_throw(self):
        for field, result in (
            ("dockerFailure", "command-failed"),
            ("dockerOutputShapeFailure", "invalid-output-shape"),
        ):
            with self.subTest(result=result):
                value = copy.deepcopy(self.good)
                value[field] = True
                self.json_path.write_text(json.dumps(value), encoding="utf-8")
                code, stdout, stderr = asyncio.run(
                    run_powershell(
                        [
                            self.pwsh,
                            "-NoProfile",
                            "-NonInteractive",
                            "-File",
                            str(self.runner),
                            str(HELPER),
                            str(self.json_path),
                            str(self.state),
                            str(self.repo),
                        ]
                    )
                )
                self.assertEqual(code, 2, stdout + stderr)
                self.assertEqual(stdout.strip(), "REJECTED")
                self.assertIn(
                    f"TEMPORAL_BOOTSTRAP_RUNTIME_INSPECT phase=temporal-server-image result={result}",
                    stderr,
                )
                self.assertIn(
                    "THROWN_EXCEPTION=Cannot inspect Temporal bootstrap runtime identity.",
                    stderr,
                )
                for forbidden in (
                    "synthetic docker command detail",
                    "synthetic stdout one",
                    "synthetic stdout two",
                    SERVER_ID,
                    INIT_ID,
                    SERVER_REF,
                    INIT_REF,
                    self.secret,
                ):
                    self.assertNotIn(forbidden, stdout + stderr)

    def test_image_and_ownership_negatives(self):
        changes = []
        for label, fn in (
            ("server-image", lambda x: x["server"].__setitem__("Image", INIT_IMAGE_ID)),
            ("init-image", lambda x: x["init"].__setitem__("Image", SERVER_IMAGE_ID)),
            (
                "bad-image-id",
                lambda x: x["initImage"].__setitem__("Id", "sha256:short"),
            ),
            (
                "server-image-user",
                lambda x: x["serverImage"]["Config"].__setitem__("User", "root"),
            ),
            ("server-id", lambda x: x["server"].__setitem__("Id", "c" * 64)),
            (
                "server-owner",
                lambda x: x["server"]["Config"]["Labels"].__setitem__(
                    "com.docker.compose.project", "other"
                ),
            ),
            (
                "init-service",
                lambda x: x["init"]["Config"]["Labels"].__setitem__(
                    "com.docker.compose.service", "other"
                ),
            ),
            (
                "multiple-server-ids",
                lambda x: x.__setitem__("serverIds", [SERVER_ID, "c" * 64]),
            ),
            ("short-init-id", lambda x: x.__setitem__("initIds", ["short"])),
            ("docker-error", lambda x: x.__setitem__("dockerFailure", True)),
        ):
            item = copy.deepcopy(self.good)
            fn(item)
            changes.append((label, item))
        for label, value in changes:
            with self.subTest(label=label):
                self.check(value, False)

    def test_server_and_initializer_isolation_negatives(self):
        changes = []
        for label, fn in (
            (
                "server-unhealthy",
                lambda x: x["server"]["State"]["Health"].__setitem__(
                    "Status", "unhealthy"
                ),
            ),
            (
                "server-stopped",
                lambda x: x["server"]["State"].__setitem__("Running", False),
            ),
            (
                "server-root",
                lambda x: x["server"]["Config"].__setitem__("User", "root"),
            ),
            (
                "server-privileged",
                lambda x: x["server"]["HostConfig"].__setitem__("Privileged", True),
            ),
            (
                "server-capability",
                lambda x: x["server"]["HostConfig"].__setitem__(
                    "CapAdd", ["SYS_ADMIN"]
                ),
            ),
            (
                "server-device",
                lambda x: x["server"]["HostConfig"].__setitem__(
                    "Devices", [{"PathOnHost": "/dev/example"}]
                ),
            ),
            (
                "server-host-network",
                lambda x: x["server"]["HostConfig"].__setitem__("NetworkMode", "host"),
            ),
            (
                "server-entrypoint",
                lambda x: x["server"]["Config"].__setitem__("Entrypoint", ["/bin/sh"]),
            ),
            (
                "server-health-probe",
                lambda x: x["server"]["Config"]["Healthcheck"].__setitem__(
                    "Test", ["NONE"]
                ),
            ),
            (
                "init-not-created",
                lambda x: x["init"]["State"].__setitem__("Status", "running"),
            ),
            ("init-running", lambda x: x["init"]["State"].__setitem__("Running", True)),
            (
                "wrong-network-namespace",
                lambda x: x["init"]["HostConfig"].__setitem__(
                    "NetworkMode", "container:" + "c" * 64
                ),
            ),
            ("init-root", lambda x: x["init"]["Config"].__setitem__("User", "0:0")),
            (
                "init-writable-root",
                lambda x: x["init"]["HostConfig"].__setitem__("ReadonlyRootfs", False),
            ),
            (
                "init-added-cap",
                lambda x: x["init"]["HostConfig"].__setitem__("CapAdd", ["SYS_ADMIN"]),
            ),
            (
                "init-device-rule",
                lambda x: x["init"]["HostConfig"].__setitem__(
                    "DeviceCgroupRules", ["c 1:1 rwm"]
                ),
            ),
            (
                "init-no-no-new-privileges",
                lambda x: x["init"]["HostConfig"].__setitem__("SecurityOpt", []),
            ),
            (
                "init-health-hook",
                lambda x: x["init"]["Config"].__setitem__(
                    "Healthcheck", {"Test": ["CMD", "id"]}
                ),
            ),
            (
                "init-tmpfs-mode",
                lambda x: x["init"]["HostConfig"]["Tmpfs"].__setitem__(
                    CONTAINER_TEMP, "mode=0777"
                ),
            ),
            (
                "stale-shared-peer",
                lambda x: x["peerModes"].__setitem__(
                    "c" * 64, "container:" + SERVER_ID
                ),
            ),
            (
                "server-absent-from-inventory",
                lambda x: x.__setitem__("runningIds", ["c" * 64]),
            ),
            (
                "malformed-peer-id",
                lambda x: x.__setitem__("runningIds", [SERVER_ID, "short"]),
            ),
        ):
            item = copy.deepcopy(self.good)
            fn(item)
            changes.append((label, item))
        for label, value in changes:
            with self.subTest(label=label):
                self.check(value, False)

    def test_running_foreign_bind_mounts_are_verified(self):
        peer = "c" * 64
        profile = self.state / ".temporal-bootstrap/profile.toml"
        sources = {
            "exact profile": profile,
            "state ancestor": self.state,
            "profile directory": profile.parent,
            "symbolic file alias": self.root / "profile-alias/profile.toml",
            "symbolic directory alias": self.root / "profile-alias",
            "unverifiable missing path": self.root / "missing-source",
        }
        if os.name == "nt":
            sources["network share"] = r"\\example.invalid\share\secret"
        for label, source in sources.items():
            with self.subTest(label=label):
                value = copy.deepcopy(self.good)
                value["peerMounts"][peer] = [
                    {"Type": "bind", "Source": str(source), "Destination": "/data"}
                ]
                self.check(value, False)

    def test_hardlinked_profile_is_rejected_and_unlinked_profile_passes(self):
        alias = self.root / "safe-data/profile-hardlink"
        os.link(self.state / ".temporal-bootstrap/profile.toml", alias)
        try:
            value = copy.deepcopy(self.good)
            value["peerMounts"]["c" * 64] = [
                {"Type": "bind", "Source": str(alias), "Destination": "/data"}
            ]
            self.check(value, False)
        finally:
            alias.unlink()
        self.check(self.good, True)

    def test_foreign_mount_metadata_fails_closed(self):
        peer = "c" * 64
        for label, mounts in (
            ("malformed null element", "[null]"),
            ("object instead of list", '{"Type":"tmpfs"}'),
            ("malformed json", "not-json"),
            ("unknown mount type", [{"Type": "image"}]),
        ):
            with self.subTest(label=label):
                value = copy.deepcopy(self.good)
                value["peerMounts"][peer] = mounts
                self.check(value, False)
        for mounts in ("null", []):
            with self.subTest(empty_mounts=mounts):
                value = copy.deepcopy(self.good)
                value["peerMounts"][peer] = mounts
                self.check(value, True)

    def test_foreign_volume_driver_and_backing_are_verified(self):
        for label, metadata in (
            ("driver options", 'foreign-safe|local|local|{"type":"none","o":"bind"}'),
            ("different driver", "foreign-safe|nfs|local|null"),
            ("nonlocal scope", "foreign-safe|local|global|null"),
            ("malformed options array", "foreign-safe|local|local|[]"),
            ("malformed options boolean", "foreign-safe|local|local|false"),
            ("invalid response", "foreign-safe|local|local"),
        ):
            with self.subTest(label=label):
                value = copy.deepcopy(self.good)
                value["volumeInfo"]["foreign-safe"] = metadata
                self.check(value, False)

    def test_foreign_network_namespace_chains_and_inspection_failures(self):
        peer = "c" * 64
        other = "d" * 64
        for label, mode in (
            ("server by id", "container:" + SERVER_ID),
            ("missing reference", "container:missing"),
            ("invalid reference", "container:bad/reference"),
        ):
            with self.subTest(label=label):
                value = copy.deepcopy(self.good)
                value["peerModes"][peer] = mode
                self.check(value, False)
        value = copy.deepcopy(self.good)
        value["peerModes"][peer] = "container:middle"
        value["peerModes"][other] = "container:server-alias"
        value["peerTargets"].update({"middle": other, "server-alias": SERVER_ID})
        self.check(value, False)
        value["peerModes"][other] = "container:middle"
        self.check(value, False)
        value = copy.deepcopy(self.good)
        value["peerFailure"] = peer
        self.check(value, False)

    def test_foreign_process_namespace_chains_are_verified(self):
        peer = "c" * 64
        other = "d" * 64
        for label, mode in (
            ("host pid namespace", "host"),
            ("server pid namespace", "container:" + SERVER_ID),
            ("initializer pid namespace", "container:" + INIT_ID),
            ("unknown pid mode", "unexpected"),
            ("missing pid reference", "container:missing"),
            ("invalid pid reference", "container:bad/reference"),
        ):
            with self.subTest(label=label):
                value = copy.deepcopy(self.good)
                value["peerPidModes"][peer] = mode
                self.check(value, False)
        value = copy.deepcopy(self.good)
        value["peerPidModes"][peer] = "container:middle"
        value["peerPidModes"][other] = ""
        value["peerTargets"]["middle"] = other
        self.check(value, True)
        for target in (SERVER_ID, INIT_ID):
            with self.subTest(transitive_target=target):
                value["peerPidModes"][other] = "container:" + target
                self.check(value, False)
        value["peerPidModes"][other] = "host"
        self.check(value, False)
        value["peerPidModes"][other] = "container:middle"
        self.check(value, False)

    def test_environment_and_mount_negatives(self):
        changes = []
        for label, fn in (
            (
                "server-env-extra",
                lambda x: x["server"]["Config"]["Env"].append("LD_PRELOAD=/evil"),
            ),
            (
                "server-env-changed",
                lambda x: x["server"]["Config"]["Env"].__setitem__(
                    1, "BIND_ON_IP=127.0.0.1"
                ),
            ),
            (
                "server-service-list-changed",
                lambda x: x["server"]["Config"]["Env"].__setitem__(
                    5, "TEMPORAL_SERVICES=frontend,history,matching,worker"
                ),
            ),
            (
                "model-service-list-changed",
                lambda x: x["model"]["services"]["temporal"]["environment"].__setitem__(
                    "TEMPORAL_SERVICES", "frontend,history,matching,worker"
                ),
            ),
            (
                "model-env-extra",
                lambda x: x["model"]["services"]["temporal"]["environment"].__setitem__(
                    "UNREVIEWED_TEMPORAL_SETTING", "enabled"
                ),
            ),
            (
                "init-env-extra",
                lambda x: x["init"]["Config"]["Env"].append("TEMPORAL_API_KEY=bad"),
            ),
            (
                "duplicate-image-env",
                lambda x: x["serverImage"]["Config"]["Env"].append(PATH_ENTRY),
            ),
            (
                "server-ca-writable",
                lambda x: x["server"]["Mounts"][2].__setitem__("RW", True),
            ),
            (
                "server-wrong-ca",
                lambda x: x["server"]["Mounts"][2].__setitem__("Name", "other_ca"),
            ),
            (
                "server-entrypoint-source",
                lambda x: x["server"]["Mounts"][1].__setitem__(
                    "Source", str(self.repo / "evil")
                ),
            ),
            ("server-mount-omitted", lambda x: x["server"]["Mounts"].pop()),
            (
                "server-extra-mount",
                lambda x: x["server"]["Mounts"].append(
                    copy.deepcopy(x["server"]["Mounts"][0])
                ),
            ),
            (
                "server-config-source",
                lambda x: x["server"]["Mounts"][0].__setitem__(
                    "Source", str(self.repo / "evil-config.yaml")
                ),
            ),
            (
                "init-admin-writable",
                lambda x: x["init"]["Mounts"][1].__setitem__("RW", True),
            ),
            (
                "init-admin-source",
                lambda x: x["init"]["Mounts"][1].__setitem__(
                    "Source", str(self.state / "other")
                ),
            ),
            ("init-mount-omitted", lambda x: x["init"]["Mounts"].pop()),
            (
                "init-extra-mount",
                lambda x: x["init"]["Mounts"].append(
                    copy.deepcopy(x["init"]["Mounts"][0])
                ),
            ),
        ):
            item = copy.deepcopy(self.good)
            fn(item)
            changes.append((label, item))
        for label, value in changes:
            with self.subTest(label=label):
                self.check(value, False)


if __name__ == "__main__":
    unittest.main(verbosity=2)
