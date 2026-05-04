from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.core.versioning import API_V1_PREFIX, API_VERSION, assert_semver
from tests.contracts.utils import (
    SNAPSHOT_FILE,
    assert_openapi_superset,
    load_current_openapi,
    normalize_openapi,
)


@pytest.fixture(scope="session")
def openapi_schema() -> dict:
    return normalize_openapi(load_current_openapi())


def test_api_version_matches_semver(openapi_schema: dict):
    assert_semver(API_VERSION)
    assert openapi_schema["info"]["version"] == API_VERSION


@pytest.mark.parametrize(
    "required_path_prefix",
    [
        f"{API_V1_PREFIX}/auth",
        f"{API_V1_PREFIX}/users",
        f"{API_V1_PREFIX}/news",
        f"{API_V1_PREFIX}/events",
        f"{API_V1_PREFIX}/schedule",
        f"{API_V1_PREFIX}/notifications",
    ],
)
def test_core_routes_present(openapi_schema: dict, required_path_prefix: str):
    matching_paths = [
        p for p in openapi_schema["paths"] if p.startswith(required_path_prefix)
    ]
    assert matching_paths, f"Expected routes for prefix {required_path_prefix} to exist"


def test_openapi_contract_snapshot(openapi_schema: dict):
    assert SNAPSHOT_FILE.exists(), f"Snapshot file {SNAPSHOT_FILE} is missing"

    expected_schema = json.loads(Path(SNAPSHOT_FILE).read_text(encoding="utf-8"))
    assert_openapi_superset(expected_schema, openapi_schema)
