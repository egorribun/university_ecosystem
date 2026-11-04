"""AUD-346 behavioural contract for the nightly chaos dry-run gate.

A dry-run must never pass the recovery assertion. It applies no fault, sends no
target traffic, reports recovery as NOT EVALUATED, and still fails on bad
configuration or manifests. A live run keeps the recovery thresholds unchanged.
"""

from __future__ import annotations

import asyncio
import http.server
import logging
import socket
import subprocess
import sys
import threading
from collections.abc import Iterator
from pathlib import Path

import pytest

from scripts.chaos import run_chaos_loadtest as chaos

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "chaos" / "run_chaos_loadtest.py"
MANIFESTS = sorted((ROOT / "k8s" / "chaos").glob("*.yaml"))
NOT_EVALUATED = "NOT EVALUATED (dry-run)"


class _HitCounter:
    def __init__(self) -> None:
        self.hits = 0
        self._lock = threading.Lock()

    def increment(self) -> None:
        with self._lock:
            self.hits += 1


@pytest.fixture
def live_target() -> Iterator[tuple[str, _HitCounter]]:
    """A healthy local server that counts every request it receives."""
    counter = _HitCounter()

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            counter.increment()
            self.send_response(200)
            self.end_headers()

        def log_message(self, *_args: object) -> None:
            return

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address[:2]
        yield f"http://{host}:{port}/health", counter
    finally:
        server.shutdown()
        server.server_close()


def _unreachable_url() -> str:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    return f"http://127.0.0.1:{port}/health"


def _run_dry_run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603  # fixed argv: this interpreter runs the repo script
        [sys.executable, str(SCRIPT), "--dry-run", *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )


@pytest.mark.parametrize("manifest", MANIFESTS, ids=lambda path: path.name)
def test_dry_run_passes_configuration_checks_and_reports_recovery_not_evaluated(
    manifest: Path, live_target: tuple[str, _HitCounter]
) -> None:
    url, counter = live_target

    result = _run_dry_run(
        "--manifest", str(manifest), "--duration", "5", "--target-url", url
    )

    output = result.stdout + result.stderr
    assert result.returncode == 0, output
    assert NOT_EVALUATED in output
    assert "Recovery availability assertion passed" not in output
    assert counter.hits == 0, "dry-run must never probe the target"


@pytest.mark.parametrize(
    ("extra_args", "reason"),
    [
        (["--manifest", "missing-manifest.yaml"], "manifest not found"),
        (["--manifest", "{bad_kind}", "--duration", "5"], "unsupported kind"),
        (["--manifest", "{bad_yaml}", "--duration", "5"], "unreadable yaml"),
        (["--manifest", "{dup}", "--duration", "5"], "duplicate identity"),
        (["--manifest", "{empty}", "--duration", "5"], "empty manifest"),
        (["--manifest", "{valid}", "--duration", "0"], "non-positive duration"),
        (
            [
                "--manifest",
                "{valid}",
                "--duration",
                "5",
                "--target-url",
                "file:///etc/passwd",
            ],
            "unsupported scheme",
        ),
        (
            [
                "--manifest",
                "{valid}",
                "--duration",
                "5",
                "--target-url",
                "http://u:p@127.0.0.1/health",
            ],
            "credentials",
        ),
    ],
)
def test_dry_run_fails_on_bad_configuration_or_manifest(
    tmp_path: Path,
    live_target: tuple[str, _HitCounter],
    extra_args: list[str],
    reason: str,
) -> None:
    url, counter = live_target
    bodies = {
        "{bad_kind}": "apiVersion: chaos-mesh.org/v1alpha1\nkind: Deployment\nmetadata:\n  name: x\n",
        "{bad_yaml}": "apiVersion: [unclosed\n",
        "{dup}": (
            "apiVersion: chaos-mesh.org/v1alpha1\nkind: PodChaos\nmetadata:\n  name: same\n"
            "---\napiVersion: chaos-mesh.org/v1alpha1\nkind: PodChaos\nmetadata:\n  name: same\n"
        ),
        "{empty}": "# nothing here\n",
        "{valid}": (
            "apiVersion: chaos-mesh.org/v1alpha1\nkind: PodChaos\nmetadata:\n  name: ok\n"
        ),
    }
    args: list[str] = []
    for item in extra_args:
        if item in bodies:
            path = tmp_path / f"{item.strip('{}')}.yaml"
            path.write_text(bodies[item], encoding="utf-8")
            args.append(str(path))
        else:
            args.append(item)
    if "--target-url" not in args:
        args += ["--target-url", url]

    result = _run_dry_run(*args)

    assert result.returncode == 1, f"{reason}: {result.stdout}{result.stderr}"
    assert counter.hits == 0


def test_dry_run_recovery_is_not_counted_as_pass_in_process(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    def forbidden_probe(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("dry-run must not probe the target")

    monkeypatch.setattr(
        chaos.ChaosLoadTestOrchestrator, "_send_http_request", forbidden_probe
    )
    orchestrator = chaos.ChaosLoadTestOrchestrator(
        str(MANIFESTS[0]), 5, "http://127.0.0.1:1/health", dry_run=True
    )
    caplog.set_level(logging.INFO, logger="chaos_loadtest")

    assert asyncio.run(orchestrator.execute()) == 0
    assert NOT_EVALUATED in caplog.text
    assert "Recovery availability assertion passed" not in caplog.text
    assert "ASSERTION FAILED" not in caplog.text


def test_live_run_with_unreachable_target_fails_recovery(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    # Fault creation and removal are stubbed so only the recovery path is
    # exercised. The target is unreachable, so the recovery threshold must fail.
    monkeypatch.setattr(chaos, "_RECOVERY_POLL_BUDGET_SEC", 0.0)
    orchestrator = chaos.ChaosLoadTestOrchestrator(
        str(MANIFESTS[0]), 1, _unreachable_url(), dry_run=False
    )
    monkeypatch.setattr(orchestrator, "phase1_preflight", lambda: True)
    monkeypatch.setattr(orchestrator, "phase3_apply_fault", lambda: True)
    monkeypatch.setattr(orchestrator, "phase5_remove_fault", lambda: True)
    caplog.set_level(logging.INFO, logger="chaos_loadtest")

    assert asyncio.run(orchestrator.execute()) == 1
    assert "ASSERTION FAILED: Post-recovery success rate below threshold" in caplog.text
    assert NOT_EVALUATED not in caplog.text
