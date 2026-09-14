"""Contracts for fail-closed browser assurance fixtures.

This check keeps the E2E harness from converting a missing mock response into a
green test.  An unhandled backend route must fail closed instead of fabricating
an apparently successful JSON response.
"""

from __future__ import annotations

from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
E2E_ROOT = REPOSITORY_ROOT / "frontend" / "tests" / "e2e"


def test_mock_api_does_not_return_success_for_unhandled_backend_routes() -> None:
    source = (E2E_ROOT / "utils" / "mockApi.ts").read_text(encoding="utf-8")

    assert "Generic 200 for unhandled path" not in source
    assert "Unhandled E2E API mock route" in source
    assert "status: 501" in source
