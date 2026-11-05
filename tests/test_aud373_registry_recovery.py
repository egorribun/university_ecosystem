"""Isolated behavior tests for the private AUD-373 registry candidate."""

from __future__ import annotations

import pytest

from tests.test_internal_mtls_kind_contract import _bash_command as bash
from tests.test_internal_mtls_kind_contract import _shell_function as function


def test_registry_uses_ipv4_listener_and_waits_for_owned_endpoint() -> None:
    command = f"""set -euo pipefail
{function("start_local_registry")}
{function("wait_local_registry")}
{function("verify_registry_paths")}
LOCAL_REGISTRY_NAME=owned-registry
REGISTRY_IMAGE=fixture
CLUSTER_NAME=owned-cluster
IMAGE_TAG=proof
REGISTRY_CREATED=0
attempts=0
docker() {{
  case "$1" in
    inspect) if [[ "$*" == *--format* ]]; then printf '%064d\\n' 1; else return 1; fi ;;
    port) printf '127.0.0.1:32768\\n' ;;
    run) printf 'docker %s\\n' "$*" >&2; printf '%064d\\n' 1 ;;
    exec)
      if [[ "$*" == *' curl '* ]]; then printf 'node %s\\n' "$*" >&2
      elif [[ "$*" == *--interactive* ]]; then cat >/dev/null; fi ;;
  esac
}}
kind() {{ printf 'kind-node\\n'; }}
curl() {{
  printf 'curl %s\\n' "$*" >&2
  attempts=$((attempts + 1))
  (( attempts >= 3 ))
}}
sleep() {{ :; }}
log() {{ printf '%s\\n' "$*" >&2; }}
start_local_registry
printf 'attempts=%s registry_created=%s address=%s\\n' "$attempts" "$REGISTRY_CREATED" "$LOCAL_REGISTRY_ADDRESS"
"""
    result = bash(command)
    assert result.returncode == 0, result.stderr
    assert b"REGISTRY_HTTP_ADDR=0.0.0.0:5000" in result.stderr
    assert b"--network kind" in result.stderr
    assert b"network connect" not in result.stderr
    assert b"--publish 127.0.0.1::5000" in result.stderr
    assert b"--noproxy * http://127.0.0.1:32768/v2/" in result.stderr
    assert b"http://owned-registry:5000/v2/" in result.stderr
    assert b"attempts=3 registry_created=1 address=127.0.0.1:32768" in result.stdout


def test_failed_readiness_stops_push_after_bounded_attempts() -> None:
    command = f"""set -euo pipefail
{function("wait_local_registry")}
{function("verify_registry_paths")}
{function("push_images")}
LOCAL_REGISTRY_ADDRESS=127.0.0.1:32768
LOCAL_BACKEND_IMAGE=local-backend:proof
LOCAL_GATEWAY_IMAGE=local-gateway:proof
BACKEND_IMAGE=127.0.0.1:32768/backend:proof
GATEWAY_IMAGE=127.0.0.1:32768/gateway:proof
attempts=0
curl() {{ attempts=$((attempts + 1)); return 1; }}
sleep() {{ :; }}
docker() {{ printf 'unexpected docker %s\\n' "$*" >&2; return 1; }}
log() {{ printf '%s\\n' "$*" >&2; }}
if push_images; then exit 1; fi
printf 'attempts=%s\\n' "$attempts"
"""
    result = bash(command)
    assert result.returncode == 0, result.stderr
    assert b"unexpected docker" not in result.stderr
    assert b"attempts=30" in result.stdout


def test_node_registry_path_failure_prevents_push() -> None:
    command = f"""set -euo pipefail
{function("wait_local_registry")}
{function("verify_registry_paths")}
{function("push_images")}
LOCAL_REGISTRY_ADDRESS=127.0.0.1:32768
LOCAL_REGISTRY_NAME=owned-registry
CLUSTER_NAME=owned-cluster
LOCAL_BACKEND_IMAGE=local-backend:proof
LOCAL_GATEWAY_IMAGE=local-gateway:proof
BACKEND_IMAGE=127.0.0.1:32768/backend:proof
GATEWAY_IMAGE=127.0.0.1:32768/gateway:proof
curl() {{ :; }}
sleep() {{ :; }}
kind() {{ printf 'kind-node\\n'; }}
docker() {{
  if [[ "$1" == exec ]]; then return 1; fi
  printf 'unexpected docker %s\\n' "$*" >&2
  return 1
}}
log() {{ printf '%s\\n' "$*" >&2; }}
if push_images; then exit 1; fi
"""
    result = bash(command)
    assert result.returncode == 0, result.stderr
    assert b"unexpected docker" not in result.stderr
    assert b"kind-node" in result.stderr


def test_registry_name_must_still_resolve_to_the_container_created_here() -> None:
    command = f"""set -euo pipefail
{function("start_local_registry")}
LOCAL_REGISTRY_NAME=owned-registry
REGISTRY_IMAGE=fixture
REGISTRY_CREATED=0
docker() {{
  case "$1" in
    inspect) if [[ "$*" == *--format* ]]; then printf '%064d\\n' 2; else return 1; fi ;;
    run) printf '%064d\\n' 1 ;;
    *) printf 'unexpected docker %s\\n' "$*" >&2; return 1 ;;
  esac
}}
log() {{ :; }}
if start_local_registry; then exit 1; fi
test "$REGISTRY_CREATED" = 1
"""
    result = bash(command)
    assert result.returncode == 0, result.stderr
    assert b"unexpected docker" not in result.stderr


def test_registry_is_verified_before_build_and_again_before_push() -> None:
    command = f"""set -euo pipefail
{function("main")}
cleanup() {{ :; }}
require_platform() {{ :; }}
install_tools() {{ :; }}
create_cluster() {{ :; }}
build_images() {{ printf '%s\\n' build; }}
start_local_registry() {{ printf '%s\\n' registry; }}
push_images() {{ printf '%s\\n' push; }}
install_spire() {{ :; }}
deploy_stack() {{ :; }}
run_proofs() {{ :; }}
FAILURES=0
main
"""
    result = bash(command)
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == [
        b"registry",
        b"build",
        b"push",
        b"RESULT=PASS",
    ]


@pytest.mark.parametrize(
    "endpoint", ["tcp://198.51.100.1:2375", "ssh://remote.example"]
)
def test_remote_docker_daemon_cannot_make_host_loopback_look_valid(
    endpoint: str,
) -> None:
    command = f"""set -euo pipefail
{function("require_local_docker_daemon")}
DOCKER_HOST={endpoint}
DOCKER_CONTEXT=
log() {{ :; }}
if require_local_docker_daemon; then exit 1; fi
"""
    result = bash(command)
    assert result.returncode == 0, result.stderr


def test_explicit_docker_context_takes_precedence_over_docker_host() -> None:
    command = f"""set -euo pipefail
{function("require_local_docker_daemon")}
DOCKER_CONTEXT=local-proof
DOCKER_HOST=tcp://198.51.100.1:2375
docker() {{
  [[ "$*" == *'context inspect'* && "$*" == *local-proof* ]] || return 1
  printf '%s\\n' 'unix:///var/run/docker.sock'
}}
log() {{ :; }}
require_local_docker_daemon
test "$DOCKER_DAEMON_ENDPOINT" = 'unix:///var/run/docker.sock'
"""
    result = bash(command)
    assert result.returncode == 0, result.stderr
