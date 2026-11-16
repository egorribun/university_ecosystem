"""Offline contracts for the opt-in, owned backup fixture runner."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/k8s/networkpolicy_runtime_proof.sh"
BASH = (
    Path("C:/Program Files/Git/bin/bash.exe") if os.name == "nt" else Path("/bin/bash")
)


def raw_function(name: str) -> str:
    text = SCRIPT.read_text(encoding="utf-8")
    start = text.index(f"{name}() {{")
    end_marker = "\nEOF\n}\n" if name == "backup_write_proxy_config" else "\n}\n"
    return text[start : text.index(end_marker, start) + len(end_marker)]


def function(name: str) -> str:
    dependencies = {
        "backup_preflight_networks": ("backup_bridge_cli", "backup_network_inventory"),
        "backup_preflight_routes": ("backup_bridge_cli",),
        "backup_inspect_container": ("backup_bridge_cli",),
        "backup_find_bridge": ("backup_bridge_cli", "backup_network_inventory"),
        "backup_find_container": ("backup_bridge_cli",),
        "backup_validate_bridge": ("backup_bridge_cli",),
        "backup_source_image": ("backup_bridge_cli",),
    }
    return "".join(
        raw_function(item) for item in dependencies.get(name, ())
    ) + raw_function(name)


def run_bash(program: str, **environment: str) -> subprocess.CompletedProcess[str]:
    assert BASH.is_file(), (
        "A native Bash executable is required for the offline runner tests"
    )
    return subprocess.run(  # noqa: S603 -- fixed native Bash runs local functions and command doubles
        [str(BASH), "-s"],
        input=program,
        text=True,
        capture_output=True,
        check=False,
        env={
            **os.environ,
            "TEST_PYTHON": sys.executable,
            "SCRIPT_DIR": (ROOT / "scripts" / "k8s").as_posix(),
            **environment,
        },
        timeout=20,
    )


@pytest.mark.parametrize(
    ("backup", "processor", "actions", "runner", "allowed"),
    [
        ("0", "0", "", "", True),
        ("1", "1", "true", "github-hosted", True),
        ("1", "0", "true", "github-hosted", False),
        ("1", "1", "false", "github-hosted", False),
        ("1", "1", "true", "self-hosted", False),
        ("1", "1", "TRUE", "github-hosted", False),
        ("yes", "1", "true", "github-hosted", False),
    ],
)
def test_backup_opt_in_requires_real_source_and_exact_hosted_runner(
    backup: str, processor: str, actions: str, runner: str, allowed: bool
) -> None:
    result = run_bash(
        'set -euo pipefail\nlog() { printf "%s\\n" "$*" >&2; }\n'
        + function("require_backup_opt_in")
        + "\nrequire_backup_opt_in\n",
        UE_NETPOL_REAL_BACKUP=backup,
        UE_NETPOL_REAL_FP=processor,
        GITHUB_ACTIONS=actions,
        RUNNER_ENVIRONMENT=runner,
    )
    assert (result.returncode == 0) is allowed


@pytest.mark.parametrize(
    ("override", "context", "endpoint", "allowed"),
    [
        ("", "default", "unix:///var/run/docker.sock", True),
        ("tcp://remote:2375", "default", "unix:///var/run/docker.sock", False),
        ("", "remote", "unix:///var/run/docker.sock", False),
        ("", "default", "tcp://remote:2375", False),
    ],
)
def test_backup_requires_the_default_local_docker_daemon(
    override: str, context: str, endpoint: str, allowed: bool
) -> None:
    result = run_bash(
        r"""set -euo pipefail
docker() {
  case "$1 $2" in
    'context show') printf '%s' "$FAKE_CONTEXT" ;;
    'context inspect') printf '%s' "$FAKE_ENDPOINT" ;;
    *) return 70 ;;
  esac
}
log() { :; }
"""
        + function("require_backup_local_docker")
        + "\nrequire_backup_local_docker\n",
        UE_NETPOL_REAL_BACKUP="1",
        DOCKER_HOST=override,
        DOCKER_CONTEXT="",
        DOCKER_TLS_VERIFY="",
        DOCKER_CERT_PATH="",
        FAKE_CONTEXT=context,
        FAKE_ENDPOINT=endpoint,
    )
    assert (result.returncode == 0) is allowed


def network(name: str, subnet: str | None = None) -> dict[str, object]:
    return {
        "Name": name,
        "Driver": "bridge",
        "IPAM": {"Config": [] if subnet is None else [{"Subnet": subnet}]},
    }


@pytest.mark.parametrize(
    ("networks", "allowed"),
    [
        ([], True),
        ([network("bridge", "172.17.0.0/16"), network("kindly")], True),
        ([network("kind", "172.22.0.0/16")], False),
        ([network("occupied", "198.18.0.0/15")], False),
        ([network("occupied", "198.18.42.128/25")], False),
        ([network("ipv6", "fd00::/64")], True),
        ([{"Name": "host", "Driver": "host", "IPAM": {"Config": None}}], True),
        ([{"Name": "none", "Driver": "null", "IPAM": {"Config": None}}], True),
        ([{"Name": "custom", "Driver": "bridge", "IPAM": {"Config": None}}], False),
        ([{"Name": "host", "Driver": "bridge", "IPAM": {"Config": None}}], False),
        ([network("malformed", "not-a-network")], False),
        ([{"Name": "missing-ipam"}], False),
    ],
)
def test_backup_preflight_rejects_existing_kind_or_overlapping_subnets(
    networks: list[dict[str, object]], allowed: bool
) -> None:
    ids = [f"{i + 1:064x}" for i in range(len(networks))]
    snapshots = [
        {**item, "Id": identity} for item, identity in zip(networks, ids, strict=True)
    ]
    result = run_bash(
        r"""set -euo pipefail
log() { printf '%s\n' "$*" >&2; }
docker() {
  case "$1 $2" in
    'network ls') printf '%s' "$FAKE_NETWORK_IDS" ;;
    'network inspect') printf '%s' "$FAKE_NETWORKS" ;;
    *) printf 'unexpected Docker operation\n' >&2; return 70 ;;
  esac
}
uv() { "$TEST_PYTHON" "${@:4}"; }
"""
        + function("backup_preflight_networks")
        + "\nbackup_preflight_networks\n",
        FAKE_NETWORK_IDS="\n".join(ids),
        FAKE_NETWORKS=json.dumps(snapshots),
    )
    assert (result.returncode == 0) is allowed
    assert "unexpected Docker operation" not in result.stderr


@pytest.mark.parametrize(
    ("routes", "allowed"),
    [
        ([{"dst": "default"}, {"dst": "172.17.0.0/16"}], True),
        ([{"dst": "198.18.0.0/15"}], False),
        ([{"dst": "198.18.42.10"}], False),
        ([{"dst": "not-a-network"}], False),
    ],
)
def test_backup_preflight_rejects_host_route_overlap(routes, allowed) -> None:
    result = run_bash(
        r"""set -euo pipefail
ip() { printf '%s' "$FAKE_ROUTES"; }
uv() { "$TEST_PYTHON" "${@:4}"; }
"""
        + function("backup_preflight_routes")
        + "\nbackup_preflight_routes\n",
        FAKE_ROUTES=json.dumps(routes),
    )
    assert (result.returncode == 0) is allowed


NETWORK_ID = "a" * 64
SERVER_ID = "b" * 64
PROXY_ID = "d" * 64
OWNER = "123456abcdef"


def server_inspection() -> dict[str, object]:
    return {
        "Id": SERVER_ID,
        "Name": "/ue-netpol-backup-" + OWNER,
        "Config": {
            "Image": "fixture-image",
            "Labels": {"org.university-ecosystem.netpol-owner": OWNER},
        },
        "HostConfig": {
            "PortBindings": {},
            "PublishAllPorts": False,
            "NetworkMode": NETWORK_ID,
        },
        "State": {"Running": True},
        "NetworkSettings": {
            "Networks": {"kind": {"NetworkID": NETWORK_ID, "IPAddress": "198.18.42.11"}}
        },
    }


@pytest.mark.parametrize(
    ("mutate", "allowed"),
    [
        (lambda obj: None, True),
        (lambda obj: obj.update(Id="c" * 64), False),
        (lambda obj: obj.update(Name="/ambient"), False),
        (lambda obj: obj["Config"]["Labels"].clear(), False),
        (lambda obj: obj["HostConfig"].update(PublishAllPorts=True), False),
        (lambda obj: obj["HostConfig"].update(PortBindings={"443/tcp": [{}]}), False),
        (
            lambda obj: obj["NetworkSettings"]["Networks"]["kind"].update(
                NetworkID="d" * 64
            ),
            False,
        ),
        (
            lambda obj: obj["NetworkSettings"]["Networks"]["kind"].update(
                IPAddress="198.18.42.12"
            ),
            False,
        ),
        (lambda obj: obj["NetworkSettings"]["Networks"].update(ambient={}), False),
    ],
)
def test_backup_server_inspection_requires_its_full_identity_and_bridge(
    mutate, allowed
) -> None:
    inspected = server_inspection()
    mutate(inspected)
    result = run_bash(
        r"""set -euo pipefail
docker() { [[ "$1 $2" == 'container inspect' ]]; printf '%s' "$FAKE_INSPECT"; }
uv() { "$TEST_PYTHON" "${@:4}"; }
"""
        + function("backup_inspect_container")
        + '\nbackup_inspect_container server "$SERVER_ID" "$SERVER_NAME"\n',
        FAKE_INSPECT=json.dumps([inspected]),
        SERVER_ID=SERVER_ID,
        SERVER_NAME="ue-netpol-backup-" + OWNER,
        BACKUP_BRIDGE_ID=NETWORK_ID,
        BACKUP_IMAGE="fixture-image",
        RUN_SUFFIX=OWNER,
        CLUSTER_NAME="ue-netpol-" + OWNER,
    )
    assert (result.returncode == 0) is allowed
    if allowed:
        assert result.stdout.strip() == "198.18.42.11"


def test_backup_cleanup_preserves_ambient_endpoint_without_mutating_any_resource() -> (
    None
):
    result = run_bash(
        r"""set -u
BACKUP_BRIDGE_INTENT=1 BACKUP_SERVER_INTENT=1 BACKUP_PROXY_INTENT=1 BACKUP_NODE_INTENT=1
BACKUP_BRIDGE_ID=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
BACKUP_SERVER_ID=bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb
BACKUP_PROXY_ID=dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd
BACKUP_NODE_ID=cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc
BACKUP_SERVER_NAME=server BACKUP_PROXY_NAME=proxy CLUSTER_NAME=cluster RUN_SUFFIX=123456abcdef
backup_find_bridge() { printf '%s' "$BACKUP_BRIDGE_ID"; }
backup_find_container() { case "$1" in server) printf '%s' "$BACKUP_SERVER_ID";; proxy) printf '%s' "$BACKUP_PROXY_ID";; node) printf '%s' "$BACKUP_NODE_ID";; esac; }
backup_inspect_container() { case "$1" in server) printf '198.18.42.11';; proxy) printf '198.18.42.10';; node) printf '198.18.42.2';; esac; }
backup_validate_bridge() { return 1; }
docker() { printf 'UNEXPECTED MUTATION\n'; }
log() { :; }
"""
        + function("backup_cleanup_resources")
        + "\nbackup_cleanup_resources\n",
    )
    assert result.returncode != 0
    assert "UNEXPECTED MUTATION" not in result.stdout


@pytest.mark.parametrize("partial", [False, True])
def test_backup_cleanup_removes_only_recorded_ids_in_dependency_order(
    partial: bool,
) -> None:
    # Partial startup has an unstarted server with no bridge endpoint and no node.
    result = run_bash(
        r"""set -u
BACKUP_BRIDGE_INTENT=1 BACKUP_SERVER_INTENT=1 BACKUP_PROXY_INTENT="$NODE_INTENT" BACKUP_NODE_INTENT="$NODE_INTENT"
BACKUP_BRIDGE_ID=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
BACKUP_SERVER_ID=bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb
BACKUP_PROXY_ID=dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd
BACKUP_NODE_ID=cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc
BACKUP_SERVER_NAME=server BACKUP_PROXY_NAME=proxy CLUSTER_NAME=cluster RUN_SUFFIX=123456abcdef
trace=''
backup_find_bridge() { printf '%s' "$BACKUP_BRIDGE_ID"; }
backup_find_container() {
  case "$1" in server) printf '%s' "$BACKUP_SERVER_ID";; proxy) printf '%s' "$BACKUP_PROXY_ID";; node) printf '%s' "$BACKUP_NODE_ID";; esac
}
backup_inspect_container() {
  case "$1" in node) printf '198.18.42.2';; proxy) printf '198.18.42.10';; server) if [[ "$NODE_INTENT" == 0 ]]; then printf '-'; else printf '198.18.42.11'; fi;; esac
}
backup_validate_bridge() { :; }
docker() { trace+="$*"$'\n'; }
log() { :; }
"""
        + function("backup_cleanup_resources")
        + "\nbackup_cleanup_resources\nprintf '%s' \"$trace\"\n",
        NODE_INTENT="0" if partial else "1",
    )
    assert result.returncode == 0, result.stderr
    commands = result.stdout.splitlines()
    if not partial:
        assert commands.pop(0) == "container rm --force --volumes " + "c" * 64
        assert commands.pop(0) == "container rm --force --volumes " + "d" * 64
    assert commands == [
        "container rm --force --volumes " + "b" * 64,
        "network rm " + "a" * 64,
    ]


def test_proxy_cleanup_failure_does_not_remove_bridge() -> None:
    result = run_bash(
        r"""set -u
BACKUP_BRIDGE_INTENT=1 BACKUP_SERVER_INTENT=1 BACKUP_PROXY_INTENT=1 BACKUP_NODE_INTENT=1
BACKUP_BRIDGE_ID="$NETWORK_ID" BACKUP_SERVER_ID="$SERVER_ID" BACKUP_PROXY_ID="$PROXY_ID" BACKUP_NODE_ID="$NODE_ID"
BACKUP_SERVER_NAME=server BACKUP_PROXY_NAME=proxy CLUSTER_NAME=cluster
trace=''
backup_find_bridge() { printf '%s' "$BACKUP_BRIDGE_ID"; }
backup_find_container() { case "$1" in server) printf '%s' "$SERVER_ID";; proxy) printf '%s' "$PROXY_ID";; node) printf '%s' "$NODE_ID";; esac; }
backup_inspect_container() { case "$1" in server) printf '198.18.42.11';; proxy) printf '198.18.42.10';; node) printf '198.18.42.2';; esac; }
backup_validate_bridge() { :; }
docker() {
  trace+="$*"$'\n'
  [[ "$1 $2 $5" != "container rm $PROXY_ID" ]]
}
"""
        + function("backup_cleanup_resources")
        + r"""
if backup_cleanup_resources; then status=0; else status=1; fi
printf 'status=%s\n%s' "$status" "$trace"
""",
        NETWORK_ID=NETWORK_ID,
        SERVER_ID=SERVER_ID,
        PROXY_ID=PROXY_ID,
        NODE_ID="c" * 64,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == [
        "status=1",
        "container rm --force --volumes " + "c" * 64,
        "container rm --force --volumes " + PROXY_ID,
        "container rm --force --volumes " + SERVER_ID,
    ]


@pytest.mark.parametrize(
    "stage,extra_endpoint",
    [
        ("full", False),
        ("proxy-created", False),
        ("server-created", False),
        ("full", True),
    ],
)
def test_cleanup_integrates_recorded_identities_and_exact_bridge_members(
    stage: str, extra_endpoint: bool
) -> None:
    node_id = "c" * 64
    server_name = "ue-netpol-backup-" + OWNER
    proxy_name = "ue-netpol-backup-proxy-" + OWNER
    cluster_name = "ue-netpol-" + OWNER
    server = server_inspection()
    proxy = {
        "Id": PROXY_ID,
        "Name": "/" + proxy_name,
        "Config": {
            "Image": "proxy-image",
            "Labels": {"org.university-ecosystem.netpol-owner": OWNER},
        },
        "HostConfig": {
            "NetworkMode": NETWORK_ID,
            "PortBindings": {},
            "PublishAllPorts": False,
        },
        "State": {"Running": stage == "full"},
        "NetworkSettings": {
            "Networks": (
                {"kind": {"NetworkID": NETWORK_ID, "IPAddress": "198.18.42.10"}}
                if stage == "full"
                else {}
            )
        },
    }
    node = {
        "Id": node_id,
        "Name": "/" + cluster_name + "-control-plane",
        "Config": {
            "Image": "node-image",
            "Labels": {
                "io.x-k8s.kind.cluster": cluster_name,
                "io.x-k8s.kind.role": "control-plane",
            },
        },
        "HostConfig": {"NetworkMode": "kind"},
        "State": {"Running": True},
        "NetworkSettings": {
            "Networks": {"kind": {"NetworkID": NETWORK_ID, "IPAddress": "198.18.42.2"}}
        },
    }
    if stage == "server-created":
        server["State"]["Running"] = False
        server["NetworkSettings"]["Networks"] = {}

    def bridge(node_running: bool, proxy_running: bool, server_running: bool) -> str:
        members = {}
        if node_running:
            members[node_id] = {"IPv4Address": "198.18.42.2/24", "IPv6Address": ""}
        if proxy_running:
            members[PROXY_ID] = {"IPv4Address": "198.18.42.10/24", "IPv6Address": ""}
        if server_running:
            members[SERVER_ID] = {"IPv4Address": "198.18.42.11/24", "IPv6Address": ""}
        if extra_endpoint:
            members["e" * 64] = {"IPv4Address": "198.18.42.3/24", "IPv6Address": ""}
        return json.dumps(
            [
                {
                    "Id": NETWORK_ID,
                    "Name": "kind",
                    "Driver": "bridge",
                    "Scope": "local",
                    "Internal": False,
                    "EnableIPv6": False,
                    "Labels": {"org.university-ecosystem.netpol-owner": OWNER},
                    "IPAM": {
                        "Driver": "default",
                        "Config": [
                            {"Subnet": "198.18.42.0/24", "Gateway": "198.18.42.1"}
                        ],
                    },
                    "Containers": members,
                }
            ]
        )

    result = run_bash(
        r"""set -u
BACKUP_BRIDGE_INTENT=1 BACKUP_SERVER_INTENT=1 BACKUP_PROXY_INTENT=1 BACKUP_NODE_INTENT=1
BACKUP_BRIDGE_ID="$NETWORK_ID" BACKUP_SERVER_ID="$SERVER_ID" BACKUP_PROXY_ID="$PROXY_ID" BACKUP_NODE_ID="$NODE_ID"
BACKUP_SERVER_NAME="$SERVER_NAME" BACKUP_PROXY_NAME="$PROXY_NAME" CLUSTER_NAME="$CLUSTER_NAME" RUN_SUFFIX="$OWNER"
BACKUP_IMAGE=fixture-image BACKUP_PROXY_IMAGE=proxy-image NODE_IMAGE=node-image
SERVER_EXISTS=1 PROXY_EXISTS="$PROXY_EXISTS_INITIAL" NODE_EXISTS="$NODE_EXISTS_INITIAL"
SERVER_RUNNING="$SERVER_RUNNING_INITIAL" PROXY_RUNNING="$PROXY_RUNNING_INITIAL"
trace=''
docker() {
  case "$1 $2" in
    'network ls') printf '%s\n' "$NETWORK_ID" ;;
    'network inspect')
      case "$NODE_EXISTS$PROXY_RUNNING$SERVER_RUNNING" in
        111) printf '%s' "$BRIDGE_ALL" ;;
        011) printf '%s' "$BRIDGE_SERVER_PROXY" ;;
        001) printf '%s' "$BRIDGE_SERVER" ;;
        000) printf '%s' "$BRIDGE_EMPTY" ;;
        *) return 70 ;;
      esac ;;
    'container ls')
      [[ "$SERVER_EXISTS" == 0 ]] || printf '%s %s\n' "$SERVER_ID" "$SERVER_NAME"
      [[ "$PROXY_EXISTS" == 0 ]] || printf '%s %s\n' "$PROXY_ID" "$PROXY_NAME"
      [[ "$NODE_EXISTS" == 0 ]] || printf '%s %s\n' "$NODE_ID" "$CLUSTER_NAME-control-plane" ;;
    'container inspect')
      case "$3" in "$SERVER_ID") printf '%s' "$SERVER_INSPECT";; "$PROXY_ID") printf '%s' "$PROXY_INSPECT";; "$NODE_ID") printf '%s' "$NODE_INSPECT";; *) return 70;; esac ;;
    'container rm')
      trace+="$5"$'\n'
      case "$5" in "$NODE_ID") NODE_EXISTS=0;; "$PROXY_ID") PROXY_EXISTS=0; PROXY_RUNNING=0;; "$SERVER_ID") SERVER_EXISTS=0; SERVER_RUNNING=0;; *) return 70;; esac ;;
    'network rm') trace+="$3"$'\n' ;;
    *) return 70 ;;
  esac
}
uv() { "$TEST_PYTHON" "${@:4}"; }
log() { :; }
"""
        + function("backup_bridge_cli")
        + function("backup_network_inventory")
        + raw_function("backup_find_bridge")
        + raw_function("backup_find_container")
        + raw_function("backup_inspect_container")
        + raw_function("backup_validate_bridge")
        + function("backup_cleanup_resources")
        + r"""
if backup_cleanup_resources; then status=0; else status=1; fi
printf 'status=%s\n%s' "$status" "$trace"
""",
        NETWORK_ID=NETWORK_ID,
        SERVER_ID=SERVER_ID,
        PROXY_ID=PROXY_ID,
        NODE_ID=node_id,
        SERVER_NAME=server_name,
        PROXY_NAME=proxy_name,
        CLUSTER_NAME=cluster_name,
        OWNER=OWNER,
        PROXY_EXISTS_INITIAL="0" if stage == "server-created" else "1",
        NODE_EXISTS_INITIAL="1" if stage == "full" else "0",
        SERVER_RUNNING_INITIAL="0" if stage == "server-created" else "1",
        PROXY_RUNNING_INITIAL="1" if stage == "full" else "0",
        SERVER_INSPECT=json.dumps([server]),
        PROXY_INSPECT=json.dumps([proxy]),
        NODE_INSPECT=json.dumps([node]),
        BRIDGE_ALL=bridge(True, True, True),
        BRIDGE_SERVER_PROXY=bridge(False, True, True),
        BRIDGE_SERVER=bridge(False, False, True),
        BRIDGE_EMPTY=bridge(False, False, False),
    )
    assert result.returncode == 0, result.stderr
    if extra_endpoint:
        assert result.stdout == "status=1\n"
    else:
        expected = [node_id] if stage == "full" else []
        expected += [] if stage == "server-created" else [PROXY_ID]
        expected += [SERVER_ID, NETWORK_ID]
        assert result.stdout.splitlines() == ["status=0", *expected]


@pytest.mark.parametrize("pinned", [False, True])
def test_backup_image_is_loaded_from_the_archived_compose_service(
    tmp_path: Path, pinned: bool
) -> None:
    image = "ghcr.io/chrislusf/seaweedfs:4.48"
    if pinned:
        image += "@sha256:" + "d" * 64
    compose = tmp_path / "docker-compose.yml"
    compose.write_text(f"services:\n  minio:\n    image: {image}\n", encoding="utf-8")
    result = run_bash(
        'set -euo pipefail\nuv() { "$TEST_PYTHON" "${@:4}"; }\n'
        + function("backup_source_image")
        + '\nbackup_source_image "$TEST_COMPOSE"\n',
        TEST_COMPOSE=compose.as_posix(),
    )
    assert (result.returncode == 0) is pinned
    if pinned:
        assert result.stdout.strip() == image


def test_backup_credentials_are_private_and_not_printed(tmp_path: Path) -> None:
    work = tmp_path.as_posix()
    if os.name == "nt":
        work = "/" + work[0].lower() + work[2:]
    result = run_bash(
        "set -euo pipefail\numask 077\n"
        + function("backup_write_credentials")
        + "\nbackup_write_credentials\n",
        WORK_DIR=work,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == ""
    credentials = (tmp_path / "backup-credentials.env").read_text(encoding="ascii")
    import re

    assert re.fullmatch(
        r"AWS_ACCESS_KEY_ID=[0-9a-f]{16,128}\nAWS_SECRET_ACCESS_KEY=[0-9a-f]{16,128}\n",
        credentials,
    )
    if os.name != "nt":
        assert (tmp_path / "backup-credentials.env").stat().st_mode & 0o077 == 0


@pytest.mark.parametrize("start_fails", [False, True])
def test_backup_server_uses_private_backend_and_retains_identity_on_failure(
    tmp_path: Path, start_fails: bool
) -> None:
    work = tmp_path.as_posix()
    if os.name == "nt":
        work = "/" + work[0].lower() + work[2:]
    result = run_bash(
        r"""set -u
BACKUP_SERVER_INTENT=0 BACKUP_SERVER_ID=''
BACKUP_SERVER_NAME="ue-netpol-backup-$RUN_SUFFIX"
BACKUP_TLS_DIR="$WORK_DIR/tls"
mkdir() { command mkdir "$3"; }
docker() {
  case "$1 $2" in
    'container create') printf '%s\n' "$@" > "$WORK_DIR/create-args"; printf '%s' "$SERVER_ID" ;;
    'container start') [[ "$START_FAILS" == 0 ]] ;;
    *) return 71 ;;
  esac
}
backup_inspect_container() { printf '198.18.42.11'; }
backup_validate_bridge() { :; }
backup_wait_bucket() { :; }
"""
        + function("backup_create_server")
        + r"""
if backup_create_server; then result=0; else result=1; fi
printf 'result=%s intent=%s id=%s\n' "$result" "$BACKUP_SERVER_INTENT" "$BACKUP_SERVER_ID"
""",
        WORK_DIR=work,
        BACKUP_BRIDGE_ID=NETWORK_ID,
        BACKUP_IMAGE="fixture-image",
        BACKUP_BUCKET="backups",
        SERVER_ID=SERVER_ID,
        RUN_SUFFIX=OWNER,
        CLUSTER_NAME="ue-netpol-" + OWNER,
        START_FAILS="1" if start_fails else "0",
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == (
        f"result={int(start_fails)} intent=1 id={SERVER_ID}"
    ), result.stderr
    arguments = (tmp_path / "create-args").read_text().splitlines()
    assert arguments[:2] == ["container", "create"]
    assert arguments[arguments.index("--network") + 1] == NETWORK_ID
    assert arguments[arguments.index("--ip") + 1] == "198.18.42.11"
    assert arguments[arguments.index("--env-file") + 1].endswith(
        "/backup-credentials.env"
    )
    assert "--publish" not in arguments and "-p" not in arguments
    assert arguments[arguments.index("--env") + 1] == "S3_BUCKET=backups"
    assert "-master.telemetry=false" in arguments
    assert "-s3.port=9000" in arguments
    assert not any("s3.cert" in arg or "s3.key" in arg for arg in arguments)


def test_proxy_config_terminates_supplied_tls_and_preserves_host(
    tmp_path: Path,
) -> None:
    work = tmp_path.as_posix()
    if os.name == "nt":
        work = "/" + work[0].lower() + work[2:]
    result = run_bash(
        "set -euo pipefail\n"
        + function("backup_write_proxy_config")
        + "\nbackup_write_proxy_config\n",
        WORK_DIR=work,
    )
    assert result.returncode == 0, result.stderr
    assert (tmp_path / "backup.Caddyfile").read_bytes() == (
        b"{\n"
        b"\tadmin off\n"
        b"\tauto_https off\n"
        b"}\n\n"
        b"https://198.18.42.10:443 {\n"
        b"\ttls /run/ue-backup/server.crt /run/ue-backup/server.key\n"
        b"\treverse_proxy http://198.18.42.11:9000\n"
        b"}\n"
    )


@pytest.mark.parametrize("start_fails", [False, True])
def test_proxy_uses_owned_identity_and_private_tls_without_published_ports(
    tmp_path: Path, start_fails: bool
) -> None:
    work = tmp_path.as_posix()
    if os.name == "nt":
        work = "/" + work[0].lower() + work[2:]
    result = run_bash(
        r"""set -u
BACKUP_PROXY_INTENT=0 BACKUP_PROXY_ID=''
BACKUP_PROXY_NAME="ue-netpol-backup-proxy-$RUN_SUFFIX" BACKUP_TLS_DIR="$WORK_DIR/tls"
docker() {
  case "$1 $2" in
    'container create') printf '%s\n' "$@" > "$WORK_DIR/proxy-args"; printf '%s' "$PROXY_ID" ;;
    'container start') [[ "$START_FAILS" == 0 ]] ;;
    *) return 71 ;;
  esac
}
backup_inspect_container() { [[ "$1" == proxy ]] && printf '198.18.42.10'; }
backup_validate_bridge() { [[ "$*" == "$SERVER_ID 198.18.42.11 $PROXY_ID 198.18.42.10" ]]; }
backup_wait_https() { :; }
id() { case "$1" in -u) printf '1001';; -g) printf '1002';; *) return 71;; esac; }
"""
        + function("backup_create_proxy")
        + r"""
if backup_create_proxy; then result=0; else result=1; fi
printf 'result=%s intent=%s id=%s\n' "$result" "$BACKUP_PROXY_INTENT" "$BACKUP_PROXY_ID"
""",
        WORK_DIR=work,
        BACKUP_BRIDGE_ID=NETWORK_ID,
        BACKUP_SERVER_ID=SERVER_ID,
        BACKUP_PROXY_IMAGE="pinned-caddy-image",
        PROXY_ID=PROXY_ID,
        SERVER_ID=SERVER_ID,
        RUN_SUFFIX=OWNER,
        START_FAILS="1" if start_fails else "0",
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == f"result={int(start_fails)} intent=1 id={PROXY_ID}"
    args = (tmp_path / "proxy-args").read_text().splitlines()
    assert args[args.index("--ip") + 1] == "198.18.42.10"
    assert args[args.index("--network") + 1] == NETWORK_ID
    assert args[args.index("--user") + 1] == "1001:1002"
    assert args[args.index("--cap-drop") + 1] == "ALL"
    assert args[args.index("--cap-add") + 1] == "NET_BIND_SERVICE"
    assert "--publish" not in args and "-p" not in args
    assert args[args.index("--entrypoint") + 1] == "/usr/bin/caddy"
    assert "pinned-caddy-image" in args
    assert any("/run/ue-backup,readonly" in arg for arg in args)
    assert any("/etc/caddy/Caddyfile,readonly" in arg for arg in args)
    assert "XDG_CONFIG_HOME=/tmp/caddy-config" in args
    assert "XDG_DATA_HOME=/tmp/caddy-data" in args


@pytest.mark.parametrize("bucket_fails", [False, True])
def test_fixture_uses_archived_proxy_and_chart_bucket_before_creating_resources(
    tmp_path: Path, bucket_fails: bool
) -> None:
    tls_dir = tmp_path / "tls"
    tls_dir.mkdir()
    for name in ("ca.crt", "server.crt", "server.key"):
        (tls_dir / name).write_text("fixture", encoding="ascii")
    work = tmp_path.as_posix()
    if os.name == "nt":
        work = "/" + work[0].lower() + work[2:]
    result = run_bash(
        r"""set -u
BACKUP_SERVER_NAME=server BACKUP_PROXY_NAME=proxy CLUSTER_NAME=cluster
backup_preflight_networks() { :; }
backup_preflight_routes() { :; }
backup_find_container() { :; }
backup_source_image() { [[ "$1" == "$WORK_DIR/source/docker-compose.yml" ]] && printf 'storage-pin'; }
backup_bridge_cli() {
  case "$1" in
    caddy-image) [[ "$2" == "$WORK_DIR/source/services/caddy/Dockerfile" ]] && printf 'caddy-pin' ;;
    backup-bucket) [[ "$2" == "$WORK_DIR/source/charts/university-ecosystem/values.yaml" && "$BUCKET_FAILS" == 0 ]] && printf 'chart-bucket' ;;
    certificate) printf '%s/tls' "$WORK_DIR" ;;
    *) return 71 ;;
  esac
}
backup_write_credentials() { :; }
backup_write_proxy_config() { :; }
backup_create_bridge() { printf 'bridge\n'; }
backup_create_server() { printf 'server=%s bucket=%s\n' "$BACKUP_IMAGE" "$BACKUP_BUCKET"; }
backup_create_proxy() { printf 'proxy=%s\n' "$BACKUP_PROXY_IMAGE"; }
"""
        + function("backup_prepare_fixture")
        + r"""
if backup_prepare_fixture; then status=0; else status=1; fi
printf 'status=%s\n' "$status"
""",
        WORK_DIR=work,
        BUCKET_FAILS="1" if bucket_fails else "0",
    )
    assert result.returncode == 0, result.stderr
    if bucket_fails:
        assert result.stdout == "status=1\n"
    else:
        assert result.stdout.splitlines() == [
            "bridge",
            "server=storage-pin bucket=chart-bucket",
            "proxy=caddy-pin",
            "status=0",
        ]


def test_kind_node_validation_checks_both_owned_fixture_endpoints() -> None:
    result = run_bash(
        r"""set -u
BACKUP_NODE_ID='' BACKUP_SERVER_ID="$SERVER_ID" BACKUP_PROXY_ID="$PROXY_ID"
BACKUP_SERVER_NAME=server BACKUP_PROXY_NAME=proxy CLUSTER_NAME=cluster
backup_find_container() { printf '%s' "$NODE_ID"; }
backup_inspect_container() { case "$1" in server) printf '198.18.42.11';; proxy) printf '198.18.42.10';; node) printf '198.18.42.2';; esac; }
backup_validate_bridge() { [[ "$*" == "$SERVER_ID 198.18.42.11 $PROXY_ID 198.18.42.10 $NODE_ID 198.18.42.2" ]]; }
"""
        + function("backup_verify_kind_node")
        + "\nbackup_verify_kind_node\n",
        SERVER_ID=SERVER_ID,
        PROXY_ID=PROXY_ID,
        NODE_ID="c" * 64,
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("ready_at", [2, 0])
def test_storage_readiness_requires_the_exact_bucket_marker_without_logging_raw_output(
    tmp_path: Path, ready_at: int
) -> None:
    work = tmp_path.as_posix()
    if os.name == "nt":
        work = "/" + work[0].lower() + work[2:]
    result = run_bash(
        r"""set -u
BACKUP_SERVER_ID="$SERVER_ID" BACKUP_BUCKET=backups
sleeps=0 TIMED=0
timeout() {
  [[ "$1 $2" == '--kill-after=2s 10s' ]] || return 71
  TIMED=1
  shift 2
  "$@"
}
docker() {
  [[ "$TIMED" == 1 ]] || return 71
  [[ "$1 $2 $3" == "container logs $SERVER_ID" ]] || return 71
  printf 'x\n' >> "$WORK_DIR/log-attempts"
  count="$(wc -l < "$WORK_DIR/log-attempts")"
  printf 'private startup detail\n'
  printf 'timestamp uncreated bucket backups\n'
  if [[ "$count" == "$READY_AT" ]]; then
    printf 'timestamp created bucket backups\n'
  else
    printf 'timestamp created bucket backups-extra\n'
  fi
}
sleep() { sleeps=$((sleeps + 1)); }
log() { printf '%s\n' "$*" >&2; }
"""
        + function("backup_wait_bucket")
        + r"""
if backup_wait_bucket; then status=0; else status=1; fi
printf 'status=%s sleeps=%s\n' "$status" "$sleeps"
""",
        WORK_DIR=work,
        SERVER_ID=SERVER_ID,
        READY_AT=str(ready_at),
    )
    assert result.returncode == 0
    if ready_at:
        assert result.stdout == "status=0 sleeps=1\n"
        assert result.stderr == ""
        assert len((tmp_path / "log-attempts").read_text().splitlines()) == 2
    else:
        assert result.stdout == "status=1 sleeps=29\n"
        assert result.stderr == "backup storage startup failed: bucket\n"
        assert len((tmp_path / "log-attempts").read_text().splitlines()) == 30


def test_storage_readiness_sanitizes_log_collection_failures() -> None:
    result = run_bash(
        r"""set -u
BACKUP_SERVER_ID="$SERVER_ID" BACKUP_BUCKET=backups
TIMED=0
timeout() {
  [[ "$1 $2" == '--kill-after=2s 10s' ]] || return 71
  TIMED=1
  shift 2
  "$@"
}
docker() { [[ "$TIMED" == 1 ]] || return 72; printf 'private daemon error\n' >&2; return 71; }
log() { printf '%s\n' "$*" >&2; }
"""
        + function("backup_wait_bucket")
        + "\nbackup_wait_bucket\n",
        SERVER_ID=SERVER_ID,
    )
    assert result.returncode != 0
    assert result.stdout == ""
    assert result.stderr == "backup storage startup failed: logs\n"


@pytest.mark.parametrize(
    ("final_status", "label"),
    [
        (5, "dns"),
        (6, "dns"),
        (7, "connect"),
        (28, "timeout"),
        (51, "tls-verification"),
        (60, "tls-verification"),
        (77, "tls-verification"),
        (35, "tls-handshake"),
        (1, "other"),
    ],
)
def test_backup_readiness_reports_only_final_sanitized_failure(
    tmp_path: Path, final_status: int, label: str
) -> None:
    work = tmp_path.as_posix()
    if os.name == "nt":
        work = "/" + work[0].lower() + work[2:]
    result = run_bash(
        r"""set -u
BACKUP_SERVER_INTENT=0 BACKUP_SERVER_ID=''
BACKUP_SERVER_NAME="ue-netpol-backup-$RUN_SUFFIX" BACKUP_TLS_DIR="$WORK_DIR/tls"
attempts=0 sleeps=0
mkdir() { :; }
docker() { [[ "$1 $2" != 'container create' ]] || printf '%s' "$SERVER_ID"; }
backup_inspect_container() { printf '198.18.42.10'; }
backup_validate_bridge() { :; }
curl() {
  attempts=$((attempts + 1))
  printf 'private response data'
  printf 'private curl diagnostics' >&2
  if [[ "$attempts" == 30 ]]; then return "$FINAL_STATUS"; fi
  return 7
}
sleep() { sleeps=$((sleeps + 1)); }
log() { printf '%s\n' "$*" >&2; }
"""
        + function("backup_wait_https")
        + r"""
if backup_wait_https; then status=0; else status=1; fi
printf 'status=%s attempts=%s sleeps=%s\n' "$status" "$attempts" "$sleeps"
""",
        WORK_DIR=work,
        BACKUP_BRIDGE_ID=NETWORK_ID,
        BACKUP_IMAGE="fixture-image",
        SERVER_ID=SERVER_ID,
        RUN_SUFFIX=OWNER,
        CLUSTER_NAME="ue-netpol-" + OWNER,
        FINAL_STATUS=str(final_status),
    )
    assert result.returncode == 0
    assert result.stdout == "status=1 attempts=30 sleeps=29\n"
    assert result.stderr == f"backup HTTPS readiness failed: {label}\n"


@pytest.mark.parametrize("success_at", [1, 3])
def test_backup_readiness_requires_verified_200_without_exposing_response(
    tmp_path: Path,
    success_at: int,
) -> None:
    work = tmp_path.as_posix()
    if os.name == "nt":
        work = "/" + work[0].lower() + work[2:]
    result = run_bash(
        r"""set -u
BACKUP_SERVER_INTENT=0 BACKUP_SERVER_ID=''
BACKUP_SERVER_NAME="ue-netpol-backup-$RUN_SUFFIX" BACKUP_TLS_DIR="$WORK_DIR/tls"
attempts=0 sleeps=0
mkdir() { :; }
docker() { [[ "$1 $2" != 'container create' ]] || printf '%s' "$SERVER_ID"; }
backup_inspect_container() { printf '198.18.42.10'; }
backup_validate_bridge() { :; }
curl() {
  local expected=(--silent --output /dev/null --write-out '%{http_code}' --connect-timeout 2 --max-time 5 --noproxy '*' --cacert "$BACKUP_TLS_DIR/ca.crt" https://198.18.42.10:443/status)
  [[ "$#" == "${#expected[@]}" && "$*" == "${expected[*]}" ]] || return 99
  attempts=$((attempts + 1))
  if [[ "$attempts" == "$SUCCESS_AT" ]]; then printf '200'; return 0; fi
  printf 'private response data'
  return 7
}
sleep() { sleeps=$((sleeps + 1)); }
log() { printf '%s\n' "$*" >&2; }
"""
        + function("backup_wait_https")
        + r"""
if backup_wait_https; then status=0; else status=1; fi
printf 'status=%s attempts=%s sleeps=%s\n' "$status" "$attempts" "$sleeps"
""",
        WORK_DIR=work,
        BACKUP_BRIDGE_ID=NETWORK_ID,
        BACKUP_IMAGE="fixture-image",
        SERVER_ID=SERVER_ID,
        RUN_SUFFIX=OWNER,
        CLUSTER_NAME="ue-netpol-" + OWNER,
        SUCCESS_AT=str(success_at),
    )
    assert result.returncode == 0
    assert result.stdout == f"status=0 attempts={success_at} sleeps={success_at - 1}\n"
    assert result.stderr == ""


@pytest.mark.parametrize("http_status", [403, 502])
def test_backup_readiness_retries_non_200_without_exposing_status(
    tmp_path: Path, http_status: int
) -> None:
    work = tmp_path.as_posix()
    if os.name == "nt":
        work = "/" + work[0].lower() + work[2:]
    result = run_bash(
        r"""set -u
BACKUP_TLS_DIR="$WORK_DIR/tls"
attempts=0 sleeps=0
curl() { attempts=$((attempts + 1)); printf '%s' "$HTTP_STATUS"; }
sleep() { sleeps=$((sleeps + 1)); }
log() { printf '%s\n' "$*" >&2; }
"""
        + function("backup_wait_https")
        + r"""
if backup_wait_https; then status=0; else status=1; fi
printf 'status=%s attempts=%s sleeps=%s\n' "$status" "$attempts" "$sleeps"
""",
        WORK_DIR=work,
        HTTP_STATUS=str(http_status),
    )
    assert result.returncode == 0
    assert result.stdout == "status=1 attempts=30 sleeps=29\n"
    assert result.stderr == "backup HTTPS readiness failed: http-status\n"


@pytest.mark.parametrize("enabled", [False, True])
def test_main_hands_only_private_paths_and_endpoint_to_probe(enabled: bool) -> None:
    result = run_bash(
        r"""set -euo pipefail
require_backup_opt_in() { :; }
require_backup_local_docker() { :; }
require_platform() { :; }
install_tools() { :; }
write_kind_config() { :; }
build_real_processor_images() { FP_IMAGE=processor; DIAGNOSTIC_IMAGE=diagnostic; SOURCE_SHA=source; }
backup_prepare_fixture() { BACKUP_TLS_DIR=/private/certs; printf 'PREPARE\n'; }
backup_verify_kind_node() { printf 'VERIFY\n'; }
kind() { printf 'KIND %s\n' "$*"; }
add_link_local_address() { :; }
load_real_processor_images() { :; }
download_pinned() { :; }
kubectl() { :; }
mkdir() { :; }
uv() { printf 'ARG=%s\n' "$@"; }
"""
        + function("main")
        + "\nmain\n",
        UE_NETPOL_REAL_BACKUP="1" if enabled else "0",
        UE_NETPOL_REAL_FP="1",
        UE_NETPOL_REAL_WS="0",
        CLUSTER_NAME="fixture",
        NODE_IMAGE="node",
        KUBERNETES_VERSION="1",
        CALICO_URL="url",
        CALICO_SHA256="checksum",
        WORK_DIR="/private",
        DIAG_DIR="/private/diagnostics",
        ROOT_DIR="/",
    )
    assert result.returncode == 0, result.stderr
    if enabled:
        assert result.stdout.index("PREPARE") < result.stdout.index("KIND create")
        assert result.stdout.index("KIND create") < result.stdout.index("VERIFY")
        assert "ARG=--backup-endpoint\nARG=https://198.18.42.10:443\n" in result.stdout
        assert "ARG=--backup-ca-file\nARG=/private/certs/ca.crt\n" in result.stdout
        assert (
            "ARG=--backup-credentials-file\nARG=/private/backup-credentials.env\n"
            in result.stdout
        )
    else:
        assert "PREPARE" not in result.stdout
        assert "--backup-" not in result.stdout


@pytest.mark.parametrize(
    ("original", "cleanup_fails"), [(0, False), (0, True), (17, True)]
)
def test_cleanup_failure_is_reported_without_kind_delete(
    original: int, cleanup_fails: bool
) -> None:
    result = run_bash(
        r"""set -u
UE_NETPOL_REAL_BACKUP=1 CLUSTER_CREATED=1 WS_IMAGE_CREATED=0 WORK_DIR=/private
collect_diagnostics() { :; }
backup_cleanup_resources() { [[ "$FAIL_CLEANUP" == 0 ]]; }
kind() { printf 'UNEXPECTED KIND DELETION\n'; }
rm() { :; }
log() { :; }
"""
        + function("cleanup")
        + f"\ntrap cleanup EXIT\nexit {original}\n",
        FAIL_CLEANUP="1" if cleanup_fails else "0",
    )
    assert result.returncode == (original or int(cleanup_fails))
    assert "UNEXPECTED KIND DELETION" not in result.stdout


def test_failed_bridge_creation_keeps_recovery_eligible_without_trusting_output() -> (
    None
):
    result = run_bash(
        r"""set -u
BACKUP_BRIDGE_INTENT=0 BACKUP_BRIDGE_ID=''
RUN_SUFFIX=123456abcdef
docker() { printf 'untrusted-partial-output'; return 1; }
backup_validate_bridge() { :; }
"""
        + function("backup_create_bridge")
        + r"""
if backup_create_bridge; then exit 99; fi
printf 'intent=%s id=%s\n' "$BACKUP_BRIDGE_INTENT" "$BACKUP_BRIDGE_ID"
"""
    )
    assert result.returncode == 0
    assert result.stdout == "intent=1 id=\n"


def test_failed_node_reinspection_preserves_original_id_for_cleanup() -> None:
    result = run_bash(
        r"""set -u
BACKUP_NODE_ID=cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc
CLUSTER_NAME=fixture
backup_find_container() { return 1; }
"""
        + function("backup_verify_kind_node")
        + r"""
if backup_verify_kind_node; then exit 99; fi
printf '%s\n' "$BACKUP_NODE_ID"
"""
    )
    assert result.returncode == 0
    assert result.stdout.strip() == "c" * 64


@pytest.mark.parametrize(("signal", "status"), [("INT", 130), ("TERM", 143)])
def test_runner_signals_enter_cleanup(signal: str, status: int) -> None:
    lines = SCRIPT.read_text(encoding="utf-8").splitlines()
    traps = [line for line in lines if line.startswith("trap ")]
    result = run_bash(
        "cleanup() { printf 'cleanup\\n'; }\n"
        + "\n".join(traps)
        + f"\nkill -{signal} $$\nprintf 'not-stopped\\n'\n"
    )
    assert result.returncode == status
    assert result.stdout == "cleanup\n"
