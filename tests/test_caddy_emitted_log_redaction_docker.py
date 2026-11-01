"""Emitted-log redaction proof for the real Caddy edge configurations (AUD-449).

Each configuration runs in its own container from an already built edge image,
receives credential-shaped requests, and must emit access-log lines that carry
the redaction markers without any raw credential value. The proof is local: it
runs only with RUN_DOCKER_PROOFS=1 and CADDY_PROOF_IMAGE naming a built Caddy
edge image, because CI does not provide Docker to this suite.
"""

from __future__ import annotations

import http.client
import os
import secrets
import shutil
import ssl
import subprocess
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TLS_EDGE_CADDYFILE = ROOT / "services" / "caddy" / "Caddyfile"
PLAIN_EDGE_CADDYFILE = ROOT / "infrastructure" / "Caddyfile"

pytestmark = [
    pytest.mark.skipif(
        os.environ.get("RUN_DOCKER_PROOFS") != "1",
        reason="Set RUN_DOCKER_PROOFS=1 and CADDY_PROOF_IMAGE to run the Caddy proof",
    ),
]

_REDACTION_MARKERS = (
    "code=REDACTED",
    "state=REDACTED",
    "password=REDACTED",
    "token=REDACTED",
    "ticket=REDACTED",
    "[REDACTED]",
)


def _docker_executable() -> str:
    executable = shutil.which("docker")
    if executable is None:
        pytest.fail("the docker CLI must be on PATH for the Caddy proof")
    return executable


def _docker(*arguments: str) -> str:
    completed = subprocess.run(  # noqa: S603 - resolved docker CLI with fixed argv, no shell
        [_docker_executable(), *arguments],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
    )
    return completed.stdout


def _container_logs(container: str) -> str:
    # Caddy writes its access log to stderr, which `docker logs` relays on the
    # client's stderr; both streams are part of the emitted log.
    completed = subprocess.run(  # noqa: S603 - resolved docker CLI with fixed argv, no shell
        [_docker_executable(), "logs", container],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
    )
    return completed.stdout + completed.stderr


@contextmanager
def _edge_container(
    image: str, caddyfile: Path, container_port: int, environment: list[str]
) -> Iterator[tuple[str, int]]:
    name = f"ue-agent-deploy3-caddy-{secrets.token_hex(4)}"
    try:
        _docker(
            "run",
            "--detach",
            "--name",
            name,
            "--cap-add",
            "NET_BIND_SERVICE",
            "--publish",
            f"127.0.0.1::{container_port}",
            "--volume",
            f"{caddyfile}:/etc/caddy/Caddyfile:ro",
            *environment,
            image,
        )
        published = _docker("port", name, f"{container_port}/tcp").splitlines()
        yield name, int(published[0].rsplit(":", 1)[1])
    finally:
        subprocess.run(  # noqa: S603 - resolved docker CLI with fixed argv, no shell
            [_docker_executable(), "rm", "-f", "-v", name],
            check=False,
            capture_output=True,
            timeout=120,
        )


def _request(
    scheme: str, port: int, path: str, headers: dict[str, str] | None = None
) -> int:
    if scheme == "https":
        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        connection: http.client.HTTPConnection = http.client.HTTPSConnection(
            "localhost", port, context=context, timeout=15
        )
    else:
        connection = http.client.HTTPConnection("localhost", port, timeout=15)
    try:
        connection.request("GET", path, headers=headers or {})
        response = connection.getresponse()
        response.read()
        return response.status
    finally:
        connection.close()


def _wait_until_serving(scheme: str, port: int) -> None:
    deadline = time.monotonic() + 90
    while True:
        try:
            if _request(scheme, port, "/healthz") == 200:
                return
        except OSError:
            pass
        if time.monotonic() > deadline:
            raise AssertionError("the Caddy edge did not serve /healthz in time")
        time.sleep(0.5)


def _marker(label: str) -> str:
    return f"{label}-{secrets.token_hex(12)}"


def _probe_edge(
    scheme: str,
    port: int,
    container: str,
) -> str:
    code = _marker("AUDCODE")
    state = _marker("AUDSTATE")
    password = _marker("AUDPASSWORD")
    token = _marker("AUDTOKEN")
    ticket = _marker("AUDTICKET")
    reset_token = _marker("AUDRESET")
    bearer = _marker("AUDBEARER")
    cookie = _marker("AUDCOOKIE")
    secrets_seen = (code, state, password, token, ticket, reset_token, bearer, cookie)

    _request(
        scheme,
        port,
        f"/login?code={code}&state={state}&password={password}"
        f"&token={token}&ticket={ticket}",
        headers={
            "Referer": f"https://localhost/landing?token={token}&code={code}",
            "Authorization": f"Bearer {bearer}",
            "Cookie": f"session={cookie}",
        },
    )
    _request(scheme, port, f"/reset-password/{reset_token}")
    _request(scheme, port, f"/ws/ticket?ticket={ticket}")
    _request(scheme, port, f"/ws/chat?ticket={ticket}")

    logs = _container_logs(container)
    for value in secrets_seen:
        assert value not in logs, "a raw credential value reached the edge log"
    for marker in _REDACTION_MARKERS:
        assert marker in logs, f"the edge log is missing the {marker!r} marker"
    assert "/login?" in logs, "the probe request was not logged at all"
    return logs


def test_tls_edge_production_config_redacts_emitted_access_logs() -> None:
    image = os.environ["CADDY_PROOF_IMAGE"]
    environment = [
        "--env",
        "PUBLIC_HOSTNAME=localhost",
        "--env",
        "ACME_EMAIL=ops@example.invalid",
    ]
    with _edge_container(image, TLS_EDGE_CADDYFILE, 443, environment) as (
        container,
        port,
    ):
        _wait_until_serving("https", port)
        _probe_edge("https", port, container)


def test_plain_edge_development_config_redacts_emitted_access_logs() -> None:
    image = os.environ["CADDY_PROOF_IMAGE"]
    with _edge_container(image, PLAIN_EDGE_CADDYFILE, 80, []) as (container, port):
        _wait_until_serving("http", port)
        _probe_edge("http", port, container)
