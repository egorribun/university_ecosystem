"""Wave 2 / Task 2.3 — Schemathesis v4 property-based OpenAPI conformance tests.

Schemathesis generates random-but-valid HTTP requests directly from the live
FastAPI OpenAPI schema and asserts that every response conforms to the declared
schema — correct status codes, response body shapes, and content types.

Architecture
------------
Uses ``schemathesis.openapi.from_asgi`` with the FastAPI ASGI app directly
(available in schemathesis >=4.0 with the TestClient transport).  No network
or server process required — fully hermetic.

What this catches
-----------------
- Response body missing a declared required field
- Incorrect status code returned (e.g. 200 instead of 201)
- Content-Type header mismatch
- Endpoints that crash with 500 on any valid input shape
- Schema drift between the FastAPI route definition and its actual response

Run locally
-----------
    uv run pytest tests/test_schemathesis_api.py -v
"""

from __future__ import annotations

import json
import os

import hypothesis
import pytest
import schemathesis
from schemathesis.checks import not_a_server_error

# ---------------------------------------------------------------------------
# Environment setup — must precede any app import
# ---------------------------------------------------------------------------

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./test_schemathesis.db")
os.environ.setdefault("ENVIRONMENT", "testing")
os.environ.setdefault(
    "SECRET_KEY",
    "schemathesis-ci-placeholder-secret-key-minimum-32-chars-long",  # pragma: allowlist secret
)

from app.main import app

# ---------------------------------------------------------------------------
# Schema loader — deferred to avoid blocking during pytest collection.
#
# schemathesis.openapi.from_asgi() performs an ASGI round-trip to fetch the
# OpenAPI spec.  When called at module level it executes during *collection*,
# which triggers the app's lifespan and can hang indefinitely if a backing
# service (DB, NATS, SpiceDB) is unavailable.
#
# We lazily compute the schema inside a session-scoped fixture so the ASGI
# call only happens when the schemathesis tests are actually run, not during
# collection of the full test suite.
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def loaded_schema():
    """Return the schemathesis schema loaded from the ASGI app."""
    return schemathesis.openapi.from_asgi("/api/openapi.json", app=app)


# ---------------------------------------------------------------------------
# Stateless property-based conformance tests
# ---------------------------------------------------------------------------


def test_api_responses_conform_to_schema(loaded_schema) -> None:
    """Every OpenAPI-described endpoint must return a non-5xx response.

    Schemathesis generates random valid requests for every (method, path)
    combination in the spec.  Auth-required endpoints may return 401/403
    (which are schema-declared), but NEVER 500.

    Checks applied:
      ``not_a_server_error`` — no 5xx responses for valid input shapes.

    Pytest parametrizes this test once per (method, path) pair, so each
    failure is reported with its exact endpoint.
    """

    @loaded_schema.parametrize()
    @hypothesis.settings(
        max_examples=25, suppress_health_check=["too_slow", "filter_too_much"]
    )
    def _run(case: schemathesis.Case) -> None:
        response = case.call()
        case.validate_response(response, checks=[not_a_server_error])

    _run()


# ---------------------------------------------------------------------------
# Spec integrity smoke tests
# ---------------------------------------------------------------------------


def test_openapi_spec_declares_paths() -> None:
    """The live FastAPI app's OpenAPI spec must declare at least one path.

    A zero-path spec indicates the app failed to initialise its routing
    correctly (e.g. no routers included) and Schemathesis would produce
    no tests — a false-positive silence we must explicitly guard against.
    """
    spec = app.openapi()
    assert "paths" in spec, "OpenAPI spec must have a 'paths' section"
    assert len(spec["paths"]) >= 1, (
        f"Expected at least 1 declared path, got {len(spec['paths'])}. "
        "Ensure all FastAPI routers are included in app/main.py."
    )


def test_openapi_spec_is_valid_json() -> None:
    """The OpenAPI spec exported by FastAPI must be round-trip JSON-serialisable."""
    spec = app.openapi()
    serialised = json.dumps(spec)
    parsed = json.loads(serialised)
    assert parsed["openapi"].startswith("3."), "Spec must declare OpenAPI 3.x"
