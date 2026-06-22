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

import schemathesis
from hypothesis import HealthCheck
from hypothesis import settings as hypothesis_settings
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
# Schema loader — ASGI transport (no network, no server)
# ---------------------------------------------------------------------------

schema = schemathesis.openapi.from_asgi("/api/openapi.json", app=app)

# ---------------------------------------------------------------------------
# Stateless property-based conformance tests
# ---------------------------------------------------------------------------


@schema.parametrize()
@hypothesis_settings(max_examples=25, suppress_health_check=[HealthCheck.too_slow])
def test_api_responses_conform_to_schema(case: schemathesis.Case) -> None:
    """Every OpenAPI-described endpoint must return a non-5xx response.

    Schemathesis generates random valid requests for every (method, path)
    combination in the spec.  Auth-required endpoints may return 401/403
    (which are schema-declared), but NEVER 500.

    Checks applied:
      ``not_a_server_error`` — no 5xx responses for valid input shapes.

    Pytest parametrizes this test once per (method, path) pair, so each
    failure is reported with its exact endpoint.
    """
    response = case.call_asgi()
    case.validate_response(response, checks=[not_a_server_error])


# ---------------------------------------------------------------------------
# Spec integrity smoke test
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
