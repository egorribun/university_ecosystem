"""Explicit POSIX Gunicorn emitted-log proof; not part of default collection.

Run with: uv run --frozen --no-sync pytest --noconftest
    tests/aud178_449_gunicorn_proof.py -q
"""

from __future__ import annotations

import http.client
import json
import os
import secrets
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
pytest_plugins = ("pytester",)


async def gunicorn_probe_app(scope: dict[str, Any], receive: Any, send: Any) -> None:
    """Minimal ASGI workload to exercise the production worker's HTTP logger."""
    if scope["type"] == "lifespan":
        while True:
            event = await receive()
            if event["type"] == "lifespan.startup":
                await send({"type": "lifespan.startup.complete"})
            elif event["type"] == "lifespan.shutdown":
                await send({"type": "lifespan.shutdown.complete"})
                return
    if scope["type"] == "http":
        import logging

        if scope["path"] != "/__aud178_ready":
            logging.getLogger("gunicorn.error").info("AUD178 synthetic request served")
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})


def _probe_targets(oauth: str, query: str, path: str) -> tuple[str, str, str]:
    return (
        f"/api/v1/spotify/callback?code={oauth}",
        f"/reset-password?token={query}",
        f"/reset-password/{path}",
    )


def _assert_real_gunicorn_worker_emitted_logs_exclude_reset_and_oauth_targets(
    tmp_path: Path, pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch
) -> None:
    if os.name != "posix":
        pytest.fail(
            "the Gunicorn proof requires an installed POSIX runtime", pytrace=False
        )
    try:
        from gunicorn.config import Config

        from app.server.spiffe_worker import BackendWorker
    except ImportError:
        pytest.fail(
            "the Gunicorn proof runtime dependencies are unavailable", pytrace=False
        )
    assert BackendWorker is not None and Config is not None
    # Run the image CMD with a minimal ASGI app and an already-bound local
    # socket. The positive control enables the access log that the image omits.
    dockerfile = (ROOT / "backend.Dockerfile").read_text(encoding="utf-8")
    command = json.loads(
        dockerfile[dockerfile.index('CMD ["gunicorn"') + 4 :].replace("\\\n", "")
    )
    assert command[:2] == ["gunicorn", "app.main:app"]
    assert (
        command[command.index("--worker-class") + 1]
        == "app.server.spiffe_worker.BackendWorker"
    )
    assert "--access-logfile" not in command
    oauth_marker = "oauthmarker" + secrets.token_hex(12)
    query_marker = "resetquerymarker" + secrets.token_hex(12)
    path_marker = "resetpathmarker" + secrets.token_hex(12)
    referer_marker = "referermarker" + secrets.token_hex(12)

    def run_worker(*, unsafe: bool) -> str:
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            listener.listen(128)
            port = listener.getsockname()[1]
            arguments = command[2:].copy()
            arguments[arguments.index("--bind") + 1] = f"fd://{listener.fileno()}"
            if unsafe:
                arguments.extend(["--access-logfile", "-"])
            monkeypatch.delenv("GUNICORN_CMD_ARGS", raising=False)
            # This independent local probe never connects to a workload agent.
            monkeypatch.setenv("INTERNAL_HTTP_MTLS_ENABLED", "false")
            # TemporaryFile is unlinked on POSIX, including while the unsafe
            # positive-control worker is running. Never persist its raw output.
            with tempfile.TemporaryFile(mode="w+b", dir=tmp_path) as output:
                # pytester launches the fixed interpreter and argv without a shell.
                process = pytester.popen(
                    [
                        sys.executable,
                        "-m",
                        "gunicorn",
                        "tests.aud178_449_gunicorn_proof:gunicorn_probe_app",
                        *arguments,
                    ],
                    cwd=ROOT,
                    stdout=output,
                    stderr=output,
                    pass_fds=(listener.fileno(),),
                )
                try:
                    deadline = time.monotonic() + 25
                    while True:
                        if process.poll() is not None or time.monotonic() >= deadline:
                            pytest.fail(
                                "the Gunicorn probe did not become ready", pytrace=False
                            )
                        connection = http.client.HTTPConnection(
                            "127.0.0.1", port, timeout=2
                        )
                        try:
                            connection.request("GET", "/__aud178_ready")
                            response = connection.getresponse()
                            assert response.status == 200 and response.read() == b"ok"
                            break
                        except (ConnectionError, OSError, TimeoutError):
                            time.sleep(0.05)
                        finally:
                            connection.close()
                    for target in _probe_targets(
                        oauth_marker, query_marker, path_marker
                    ):
                        connection = http.client.HTTPConnection(
                            "127.0.0.1", port, timeout=10
                        )
                        try:
                            connection.request(
                                "GET",
                                target,
                                headers={
                                    "Referer": f"https://portal.example.test/reset-password/{referer_marker}"
                                },
                            )
                            response = connection.getresponse()
                            assert response.status == 200 and response.read() == b"ok"
                        finally:
                            connection.close()
                finally:
                    process.terminate()
                    try:
                        process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=10)
                output.seek(0)
                return output.read().decode("utf-8", errors="replace")

    unsafe_log = run_worker(unsafe=True)
    assert unsafe_log.count("AUD178 synthetic request served") == 3
    assert all(
        marker in unsafe_log for marker in (oauth_marker, query_marker, path_marker)
    )
    assert referer_marker not in unsafe_log
    production_log = run_worker(unsafe=False)
    assert production_log.count("AUD178 synthetic request served") == 3
    assert all(
        marker not in production_log
        for marker in (oauth_marker, query_marker, path_marker, referer_marker)
    )


def test_real_gunicorn_worker_emitted_logs_exclude_reset_and_oauth_targets(
    tmp_path: Path, pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Assertion rewriting and unexpected exceptions can otherwise print the
    # positive-control markers or entire captured log, including under -l.
    failed = False
    try:
        _assert_real_gunicorn_worker_emitted_logs_exclude_reset_and_oauth_targets(
            tmp_path, pytester, monkeypatch
        )
    except Exception:
        failed = True
    # Report outside the except block so pytest cannot render an exception chain.
    if failed:
        pytest.fail("the Gunicorn emitted-log proof failed", pytrace=False)
