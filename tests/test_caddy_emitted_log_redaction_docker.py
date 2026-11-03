"""Emitted-log redaction proof for the real Caddy edge configurations (AUD-449).

Each configuration runs in its own container from an already built edge image,
receives credential-shaped requests, and must emit access-log lines that carry
the redaction markers without any raw credential value. The proof is local: it
runs only with RUN_DOCKER_PROOFS=1 and CADDY_PROOF_IMAGE naming a built Caddy
edge image. The ordinary backend suite does not run Docker proofs.
"""

from __future__ import annotations

import http.client
import os
import secrets
import shutil
import ssl
import subprocess
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


def _docker(*arguments: str, timeout: float = 120) -> str:
    completed = subprocess.run(  # noqa: S603 - resolved docker CLI with fixed argv, no shell
        [_docker_executable(), *arguments],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
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
    name = f"ue-l3-caddy-{secrets.token_hex(4)}"
    # Create first: only a returned, validated ID authorizes start and cleanup.
    # A name collision must never remove somebody else's existing container.
    container = _docker(
        "create",
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
    ).strip()
    assert len(container) == 64 and all(
        character in "0123456789abcdef" for character in container
    ), "Docker did not acknowledge a valid owned container ID"
    try:
        _docker("start", container)
        published = _docker("port", container, f"{container_port}/tcp").splitlines()
        yield container, int(published[0].rsplit(":", 1)[1])
    finally:
        _docker("rm", "-f", "-v", container)


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


def _wait_until_serving(scheme: str, container: str) -> None:
    # Use the image's curl to poll the real handler, not a fixed Python sleep.
    # Curl bounds each transfer to 5s and starts retries for at most 80s. The
    # outer 90s subprocess timeout kills and reaps the Docker CLI on expiry;
    # _edge_container's finally removes the owned container and its curl child.
    # This bounds the readiness command, not container setup/cleanup or the
    # subsequent host-published requests that prove actual emitted-log redaction.
    status = _docker(
        "exec",
        container,
        "curl",
        "--insecure",
        "--fail",
        "--silent",
        "--show-error",
        "--output",
        "/dev/null",
        "--write-out",
        "%{http_code}",
        "--retry",
        "90",
        "--retry-all-errors",
        "--retry-delay",
        "1",
        "--retry-max-time",
        "80",
        "--connect-timeout",
        "3",
        "--max-time",
        "5",
        f"{scheme}://localhost/healthz",
        timeout=90,
    )
    assert status.strip() == "200", "the Caddy edge did not serve /healthz"


def _marker(label: str) -> str:
    return f"{label}-{secrets.token_hex(12)}"


def _spotify_shaped(label: str) -> str:
    # Spotify authorization codes are long URL-safe base64 strings with an "AQ"
    # prefix. The probe uses that shape so the negative receipt matches the
    # production credential class, not only a generic marker.
    return f"AQ{label}{secrets.token_urlsafe(96)}"


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
    spotify_code = _spotify_shaped("AUDSPOTIFY")
    spotify_state = _marker("AUDSPOTIFYSTATE")
    secrets_seen = (
        code,
        state,
        password,
        token,
        ticket,
        reset_token,
        bearer,
        cookie,
        spotify_code,
        spotify_state,
    )

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
    # The Spotify OAuth callback is the production path that carries the code.
    _request(
        scheme,
        port,
        "/api/v1/integrations/spotify/callback"
        f"?code={spotify_code}&state={spotify_state}&scope=user-read-email",
    )

    logs = _container_logs(container)
    for value in secrets_seen:
        assert value not in logs, "a raw credential value reached the edge log"
    for marker in _REDACTION_MARKERS:
        assert marker in logs, f"the edge log is missing the {marker!r} marker"
    assert "/login?" in logs, "the probe request was not logged at all"
    assert (
        "/api/v1/integrations/spotify/callback?code=REDACTED&state=REDACTED" in logs
    ), "the Spotify callback row was not logged with its redacted URI"
    return logs


@pytest.mark.parametrize("acme_email", [None, "", "ops@example.invalid"])
def test_tls_edge_production_config_redacts_emitted_access_logs(
    acme_email: str | None,
) -> None:
    image = os.environ["CADDY_PROOF_IMAGE"]
    environment = ["--env", "PUBLIC_HOSTNAME=localhost"]
    if acme_email is not None:
        environment.extend(["--env", f"ACME_EMAIL={acme_email}"])
    with _edge_container(image, TLS_EDGE_CADDYFILE, 443, environment) as (
        container,
        port,
    ):
        _wait_until_serving("https", container)
        _probe_edge("https", port, container)


def test_plain_edge_development_config_redacts_emitted_access_logs() -> None:
    image = os.environ["CADDY_PROOF_IMAGE"]
    with _edge_container(image, PLAIN_EDGE_CADDYFILE, 80, []) as (container, port):
        _wait_until_serving("http", container)
        _probe_edge("http", port, container)
