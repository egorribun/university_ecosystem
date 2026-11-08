"""The single-container Temporal entrypoint renders loopback internal services.

The worker scanner's system client authenticates through `internal-frontend`
only when that service is defined. That service is unauthenticated, so it must
stay on 127.0.0.1 while the public frontend alone listens on all interfaces.
These tests run the real entrypoint and the real config.yaml, with only the
mount paths, the final temporal-server call and the JWKS trust anchor redirected
to temporary files.
"""

from __future__ import annotations

import ipaddress
import os
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
ENTRYPOINT = ROOT / "services" / "temporal" / "entrypoint.sh"
CONFIG = ROOT / "services" / "temporal" / "config.yaml"
SERVICES = "frontend,history,matching,worker,internal-frontend"
JWKS_URL = "https://caddy:8443/.well-known/jwks.json"
CONFIG_MOUNT = "/etc/temporal/config/docker.yaml"
SERVER_CALL = "exec temporal-server"
ENTRYPOINT_SOURCE = ENTRYPOINT.read_text(encoding="utf-8")


def _redirect_target(marker: str) -> str:
    return next(
        line.rsplit(">", 1)[1].strip()
        for line in ENTRYPOINT_SOURCE.splitlines()
        if marker in line and ">" in line
    )


RENDERED_FILE = _redirect_target("/etc/temporal/config/docker.yaml")
BUNDLE_FILE = _redirect_target("} >")


def _shell() -> str:
    shell = shutil.which("sh")
    if shell:
        return shell
    # Windows CI can use the same POSIX shell distributed with Git.
    git = shutil.which("git")
    assert git, "a POSIX shell is required"
    candidate = Path(git).resolve().parents[1] / "bin" / "sh.exe"
    assert candidate.is_file(), "a POSIX shell is required"
    return str(candidate)


def _run_entrypoint(
    tmp_path: Path,
    *,
    env_overrides: dict[str, str] | None = None,
) -> tuple[subprocess.CompletedProcess[bytes], dict]:
    rendered = tmp_path / "rendered.yaml"
    bundle = tmp_path / "bundle.pem"
    trust_anchor = tmp_path / "root.crt"
    trust_anchor.write_text(
        "-----BEGIN CERTIFICATE-----\nAAAA\n-----END CERTIFICATE-----\n",
        encoding="utf-8",
    )

    # The fake server reports the environment it was started with and prints
    # the config file that the real entrypoint rendered for it.
    fake_server = tmp_path / "fake-temporal-server.sh"
    fake_server.write_text(
        "#!/bin/sh\n"
        'printf "args=%s\\n" "$*"\n'
        'printf "services=%s\\n" "$TEMPORAL_SERVICES"\n'
        f'cat "{rendered.as_posix()}"\n',
        encoding="utf-8",
        newline="\n",
    )

    script = ENTRYPOINT_SOURCE
    script = script.replace(CONFIG_MOUNT, CONFIG.as_posix())
    script = script.replace(RENDERED_FILE, rendered.as_posix())
    script = script.replace(BUNDLE_FILE, bundle.as_posix())
    script = script.replace(
        SERVER_CALL,
        f'exec "{_shell()}" "{fake_server.as_posix()}"',
    )
    test_script = tmp_path / "entrypoint.sh"
    test_script.write_text(script, encoding="utf-8", newline="\n")

    env = {
        "PATH": os.environ.get("PATH", ""),
        "MSYS_NO_PATHCONV": "1",
        "POSTGRES_USER": "ue_temporal",
        "POSTGRES_PWD": f"pwd-{tmp_path.name}",
        "TEMPORAL_JWKS_URL": JWKS_URL,
        "TEMPORAL_JWKS_CA_FILE": trust_anchor.as_posix(),
        "TEMPORAL_SERVICES": SERVICES,
        "BIND_ON_IP": str(ipaddress.IPv4Address(0)),
    }
    env.update(env_overrides or {})
    result = subprocess.run(  # noqa: S603 - fixed shell running the repository entrypoint
        [_shell(), str(test_script)],
        capture_output=True,
        env=env,
        check=False,
        timeout=30,
    )
    rendered_config: dict = {}
    if result.returncode == 0:
        body = result.stdout.decode("utf-8").split("\n", 2)[2]
        rendered_config = yaml.safe_load(body)
    return result, rendered_config


def test_entrypoint_renders_internal_frontend_on_loopback(tmp_path: Path) -> None:
    result, rendered = _run_entrypoint(tmp_path)
    assert result.returncode == 0, result.stderr.decode("utf-8")
    stdout = result.stdout.decode("utf-8")
    assert f"services={SERVICES}\n" in stdout
    assert "args=--root /tmp --config . --env docker start" in stdout

    services = rendered["services"]
    assert set(services) == {
        "frontend",
        "internal-frontend",
        "matching",
        "history",
        "worker",
    }
    internal = services["internal-frontend"]["rpc"]
    assert internal["bindOnIP"] == "127.0.0.1"
    assert internal["bindOnLocalHost"] is False
    assert internal["grpcPort"] == 7236
    assert internal["membershipPort"] == 6936

    for name in ("matching", "history", "worker"):
        assert services[name]["rpc"]["bindOnIP"] == "127.0.0.1", name

    frontend = services["frontend"]["rpc"]
    assert frontend["bindOnIP"] == str(ipaddress.IPv4Address(0))
    assert frontend["grpcPort"] == 7233
    assert frontend["httpPort"] == 7243


def test_entrypoint_renders_loopback_membership_and_no_container_address(
    tmp_path: Path,
) -> None:
    result, rendered = _run_entrypoint(tmp_path)
    assert result.returncode == 0, result.stderr.decode("utf-8")

    assert rendered["global"]["membership"]["broadcastAddress"] == "127.0.0.1"
    ports = [
        spec["rpc"]["membershipPort"] for spec in rendered["services"].values()
    ] + [spec["rpc"]["grpcPort"] for spec in rendered["services"].values()]
    assert len(ports) == len(set(ports)), "service ports must not collide"


def test_entrypoint_renders_the_authorization_and_persistence_settings(
    tmp_path: Path,
) -> None:
    result, rendered = _run_entrypoint(tmp_path)
    assert result.returncode == 0, result.stderr.decode("utf-8")

    authorization = rendered["global"]["authorization"]
    assert authorization["jwtKeyProvider"]["keySourceURIs"] == [JWKS_URL]
    assert authorization["claimMapper"] == "default"
    assert authorization["authorizer"] == "default"
    assert "authorization" not in rendered["services"]["internal-frontend"]

    store = rendered["persistence"]["datastores"]["postgres-default"]["sql"]
    assert store["user"] == "ue_temporal"
    assert store["password"] == f"pwd-{tmp_path.name}"
    assert "${" not in result.stdout.decode("utf-8")


@pytest.mark.parametrize(
    "services",
    [
        "",
        "frontend,history,matching,worker",
        "frontend,history,matching,worker,internal-frontend,unexpected",
        "frontend,history,matching,worker,internal-frontend,internal-frontend",
    ],
)
def test_entrypoint_refuses_any_other_service_list(
    tmp_path: Path, services: str
) -> None:
    result, _ = _run_entrypoint(tmp_path, env_overrides={"TEMPORAL_SERVICES": services})
    assert result.returncode != 0
    assert b"args=" not in result.stdout
    assert b"services=" not in result.stdout


def test_entrypoint_refuses_to_start_without_the_service_variable(
    tmp_path: Path,
) -> None:
    script_copy = tmp_path / "entrypoint.sh"
    script_copy.write_text(
        ENTRYPOINT.read_text(encoding="utf-8").replace(CONFIG_MOUNT, CONFIG.as_posix()),
        encoding="utf-8",
        newline="\n",
    )
    env = {
        "PATH": os.environ.get("PATH", ""),
        "POSTGRES_USER": "ue_temporal",
        "POSTGRES_PWD": "unused",
        "TEMPORAL_JWKS_URL": JWKS_URL,
        # The guard runs before the trust-anchor wait, so this missing path must
        # not stall the test.
        "TEMPORAL_JWKS_CA_FILE": str(tmp_path / "missing.crt"),
    }
    result = subprocess.run(  # noqa: S603 - fixed shell running the repository entrypoint
        [_shell(), str(script_copy)],
        capture_output=True,
        env=env,
        check=False,
        timeout=30,
    )
    assert result.returncode != 0
    assert b"args=" not in result.stdout


@pytest.mark.parametrize("variable", ["POSTGRES_USER", "POSTGRES_PWD"])
@pytest.mark.parametrize("character", ["&", "|", "\\", "]", "[", '"', "'", " ", "\n"])
def test_entrypoint_refuses_sed_metacharacters_in_postgres_credentials(
    tmp_path: Path, variable: str, character: str
) -> None:
    secret = f"secret{character}value"
    result, _ = _run_entrypoint(tmp_path, env_overrides={variable: secret})
    assert result.returncode != 0
    assert b"args=" not in result.stdout
    stderr = result.stderr.decode("utf-8")
    assert (
        f"{variable} contains characters the config renderer does not accept" in stderr
    )
    assert "secret" not in stderr, "the rejected credential must never be echoed"


def test_entrypoint_renders_postgres_password_with_safe_punctuation(
    tmp_path: Path,
) -> None:
    safe_value = "p@ss:w#rd$%!+=~.(){}*"
    result, rendered = _run_entrypoint(
        tmp_path, env_overrides={"POSTGRES_PWD": safe_value}
    )
    assert result.returncode == 0, result.stderr.decode("utf-8")
    store = rendered["persistence"]["datastores"]["postgres-default"]["sql"]
    assert store["password"] == safe_value
    assert "${" not in result.stdout.decode("utf-8")
