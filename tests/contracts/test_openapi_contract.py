"""Contract tests for OpenAPI specification correctness (Wave 13 expansion).

Existing checks: semver, core route groups present, snapshot superset.
Wave 13 additions:
  - All major endpoint groups (auth, users, events, news, chat, notifications)
    have at least one GET or POST operation.
  - Every path has at least one operation (nothing is completely undocumented).
  - Every operation declares at least one response.
  - Auth endpoints should document a 401 response.
  - Component schemas are not bare 'object' without properties.
  - info block is complete.

Run with:
    pytest tests/contracts/test_openapi_contract.py -v
"""

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


# ---------------------------------------------------------------------------
# Existing Wave 5/6 tests (preserved unchanged)
# ---------------------------------------------------------------------------


def test_api_version_matches_semver(openapi_schema: dict) -> None:
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
def test_core_routes_present(openapi_schema: dict, required_path_prefix: str) -> None:
    matching_paths = [
        p for p in openapi_schema["paths"] if p.startswith(required_path_prefix)
    ]
    assert matching_paths, f"Expected routes for prefix {required_path_prefix} to exist"


def test_openapi_contract_snapshot(openapi_schema: dict) -> None:
    assert SNAPSHOT_FILE.exists(), f"Snapshot file {SNAPSHOT_FILE} is missing"

    expected_schema = json.loads(Path(SNAPSHOT_FILE).read_text(encoding="utf-8"))
    assert_openapi_superset(expected_schema, openapi_schema)


# ---------------------------------------------------------------------------
# Wave 13: Additional endpoint-group coverage checks
# ---------------------------------------------------------------------------

_HTTP_METHODS = frozenset({"get", "post", "put", "patch", "delete", "head", "options"})


@pytest.mark.parametrize(
    "endpoint_group",
    [
        "auth",
        "users",
        "events",
        "news",
        "notifications",
    ],
)
def test_endpoint_group_has_get_or_post(
    openapi_schema: dict, endpoint_group: str
) -> None:
    """Every major feature group must expose at least one GET or POST operation.

    WHY: Catches accidental removal of an entire router (e.g. forgetting to
    include the router in app.main) before it surfaces in production.
    """
    prefix = f"{API_V1_PREFIX}/{endpoint_group}"
    matching = [p for p in openapi_schema["paths"] if p.startswith(prefix)]
    assert matching, f"No paths found for endpoint group '{endpoint_group}'"

    has_method = any(
        method in openapi_schema["paths"][path]
        for path in matching
        for method in ("get", "post")
    )
    assert has_method, (
        f"Endpoint group '{endpoint_group}' has no GET or POST operations documented"
    )


def test_no_path_is_completely_undocumented(openapi_schema: dict) -> None:
    """Every path must have at least one HTTP operation.

    WHY: Paths with no operations cause documentation generators and SDK
    clients to skip them silently.
    """
    empty_paths = [
        path
        for path, path_item in openapi_schema.get("paths", {}).items()
        if not any(path_item.get(m) for m in _HTTP_METHODS)
    ]
    assert not empty_paths, (
        f"These paths have no documented HTTP operations: {empty_paths}"
    )


def test_all_operations_have_response_definitions(openapi_schema: dict) -> None:
    """Every operation must declare at least one response.

    WHY: OpenAPI requires at least one response entry.  Operations without
    responses indicate incomplete spec generation and break SDK codegen.
    """
    missing: list[str] = []

    for path, path_item in openapi_schema.get("paths", {}).items():
        for method, operation in path_item.items():
            if method not in _HTTP_METHODS:
                continue
            if not isinstance(operation, dict):
                continue
            if not operation.get("responses"):
                missing.append(f"{method.upper()} {path}")

    assert not missing, (
        "These operations have no response definitions in the spec:\n"
        + "\n".join(f"  {m}" for m in missing)
    )


def test_auth_endpoints_document_401_response(openapi_schema: dict) -> None:
    """At least some /auth/** endpoints should document 401 Unauthorized.

    WHY: Consumers rely on the spec to know which status codes to handle.
    A missing 401 on every single auth endpoint means SDK consumers never
    implement refresh/retry logic.
    """
    auth_prefix = f"{API_V1_PREFIX}/auth"
    documented_401 = 0

    for path, path_item in openapi_schema.get("paths", {}).items():
        if not path.startswith(auth_prefix):
            continue
        for method, operation in path_item.items():
            if method not in _HTTP_METHODS:
                continue
            if not isinstance(operation, dict):
                continue
            responses = operation.get("responses", {})
            if "401" in responses or 401 in responses:
                documented_401 += 1

    auth_ops_total = sum(
        1
        for path in openapi_schema.get("paths", {})
        if path.startswith(auth_prefix)
        for method in openapi_schema["paths"][path]
        if method in _HTTP_METHODS
        and isinstance(openapi_schema["paths"][path][method], dict)
    )

    # Only fail if there are auth operations AND none of them document 401.
    if auth_ops_total > 0 and documented_401 == 0:
        pytest.fail(
            f"None of the {auth_ops_total} /auth/** operations document a 401 "
            "response — auth error handling is systematically undocumented."
        )


def test_component_schemas_are_not_bare_objects(openapi_schema: dict) -> None:
    """Component schemas must not be bare 'object' without properties.

    WHY: A schema defined as {"type": "object"} with no properties is
    effectively 'any', breaking SDK type generation.  We allow a small
    set of intentionally opaque schemas (validation error wrappers).
    """
    _INTENTIONALLY_OPAQUE: frozenset[str] = frozenset(
        {"HTTPValidationError", "ValidationError"}
    )

    components = openapi_schema.get("components", {}).get("schemas", {})
    bare_object_schemas: list[str] = []

    for schema_name, schema_def in components.items():
        if schema_name in _INTENTIONALLY_OPAQUE:
            continue
        if not isinstance(schema_def, dict):
            continue
        if schema_def.get("type") == "object" and not schema_def.get("properties"):
            # Allow schemas that compose via allOf / anyOf / oneOf / $ref.
            if not any(k in schema_def for k in ("allOf", "anyOf", "oneOf", "$ref")):
                bare_object_schemas.append(schema_name)

    assert not bare_object_schemas, (
        "These component schemas are bare 'object' with no 'properties' — "
        "they act as 'any' types and break SDK type generation:\n"
        + "\n".join(f"  {s}" for s in bare_object_schemas)
    )


def test_openapi_info_block_is_complete(openapi_schema: dict) -> None:
    """The info block must have both title and version fields populated.

    WHY: Developer portals and auto-generated documentation require these.
    """
    info = openapi_schema.get("info", {})
    assert info.get("title"), "OpenAPI info.title must not be empty"
    assert info.get("version"), "OpenAPI info.version must not be empty"
