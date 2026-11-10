"""Shared health fixtures must not reuse another test's probe results."""

import pytest

from app.api import health
from tests.conftest import mock_health_checks


@pytest.mark.parametrize("boundary", ["setup", "teardown"])
def test_mock_health_checks_clears_cached_probe_results(monkeypatch, boundary):
    fixture = mock_health_checks.__wrapped__(monkeypatch)
    if boundary == "teardown":
        next(fixture)

    monkeypatch.setitem(health._health_cache, "expires_at", float("inf"))
    monkeypatch.setitem(health._health_cache, "payload", {"status": "error"})
    monkeypatch.setitem(health._health_cache, "status_code", 503)
    monkeypatch.setitem(health._storage_probe_cache, "expires_at", float("inf"))
    monkeypatch.setitem(health._storage_probe_cache, "status", "error")
    monkeypatch.setattr(health, "_storage_probe_generation", 7)
    monkeypatch.setattr(health, "_storage_probe_last_result", (7, "error", 1.0))

    try:
        if boundary == "setup":
            next(fixture)
        else:
            with pytest.raises(StopIteration):
                next(fixture)

        assert health._health_cache == {
            "expires_at": 0.0,
            "payload": {},
            "status_code": 200,
        }
        assert health._storage_probe_cache == {
            "expires_at": 0.0,
            "status": "unknown",
            "latency": 0.0,
        }
        assert health._storage_probe_generation == 0
        assert health._storage_probe_last_result is None
    finally:
        fixture.close()
