from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

from app.main import app

if TYPE_CHECKING:
    from collections.abc import Iterable


def load_current_openapi() -> dict[str, Any]:
    # FastAPI caches the OpenAPI schema, so this is safe to call multiple times.
    return app.openapi()


def normalize_openapi(schema: dict[str, Any]) -> dict[str, Any]:
    """Return a deterministically ordered OpenAPI payload."""
    normalized = json.loads(json.dumps(schema, sort_keys=True))
    return normalized


def _iterable_contains_superset(
    candidates: Iterable[Any], expected: Any, path: str
) -> bool:
    for candidate in candidates:
        try:
            assert_openapi_superset(expected, candidate, path=path)
        except AssertionError:
            continue
        return True
    return False


def assert_openapi_superset(expected: Any, actual: Any, *, path: str = "root") -> None:
    """Ensure ``actual`` contains everything from ``expected``.

    This subset matcher allows new fields/endpoints/components while ensuring the
    existing contract is not broken.
    """

    if isinstance(expected, dict):
        assert isinstance(actual, dict), f"{path}: expected dict, got {type(actual)}"
        for key, value in expected.items():
            assert key in actual, f"{path}: missing key '{key}'"
            assert_openapi_superset(value, actual[key], path=f"{path}.{key}")
        return

    if isinstance(expected, list):
        assert isinstance(actual, list), f"{path}: expected list, got {type(actual)}"
        if not expected:
            return
        if all(isinstance(item, str | int | float) for item in expected):
            missing = set(expected) - set(actual)
            assert not missing, f"{path}: missing values {sorted(missing)}"
            return
        for index, value in enumerate(expected):
            assert _iterable_contains_superset(actual, value, path=f"{path}[{index}]")
        return

    assert expected == actual, f"{path}: expected {expected!r}, got {actual!r}"


SNAPSHOT_DIR = Path(__file__).parent / "snapshots"
SNAPSHOT_FILE = SNAPSHOT_DIR / "api_openapi_v1.json"
