"""Security boundary tests for the operator-driven chaos load generator."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from scripts.chaos.run_chaos_loadtest import ChaosLoadTestOrchestrator


@pytest.fixture
def orchestrator(tmp_path: Path) -> ChaosLoadTestOrchestrator:
    return ChaosLoadTestOrchestrator(
        str(tmp_path / "manifest.yaml"), 1, "http://localhost"
    )


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "data:text/plain,secret",
        "http://user:password@localhost/",  # pragma: allowlist secret
        "//localhost/no-scheme",
    ],
)
def test_send_http_request_rejects_non_http_or_credentialed_urls(
    orchestrator: ChaosLoadTestOrchestrator, url: str
) -> None:
    status, latency, error = orchestrator._send_http_request(url)
    assert (status, latency) == (0, 0.0)
    assert error and error.startswith("Unsupported URL scheme")


def test_send_http_request_accepts_valid_operator_target(
    orchestrator: ChaosLoadTestOrchestrator,
) -> None:
    response = MagicMock(status=204)
    response.__enter__.return_value = response
    response.__exit__.return_value = False
    with patch("scripts.chaos.run_chaos_loadtest.urlopen", return_value=response):
        status, latency, error = orchestrator._send_http_request(
            "https://localhost:8443/health"
        )

    assert status == 204
    assert latency >= 0
    assert error is None
