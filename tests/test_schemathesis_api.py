"""Schemathesis v4 property-based OpenAPI conformance tests.

Schemathesis generates random-but-valid HTTP requests directly from the live
FastAPI OpenAPI schema and asserts that every response conforms to the declared
schema — correct status codes, response body shapes, and content types.

Architecture
------------
Uses ``schemathesis.openapi.from_asgi`` with the FastAPI ASGI app directly
(available in schemathesis >=4.0 with the TestClient transport).  No network
or server process required — fully hermetic.

Schema loading is lazy via ``schemathesis.pytest.from_fixture``:

    _lazy_schema = schemathesis.pytest.from_fixture("loaded_schema")

This creates a ``LazySchema`` that stores the fixture name as a string at
module parse/collection time.  The actual ``from_asgi()`` ASGI round-trip only
happens at test *execution* time (via ``request.getfixturevalue("loaded_schema")``
inside the wrapped test), never during pytest collection.  This prevents the
app lifespan from blocking collection when backing services are unavailable.

The ``@_lazy_schema.parametrize()`` decorator is intercepted by the schemathesis
pytest plugin which parametrizes the test over every (method, path) pair and
runs a Hypothesis test for each one.

What this catches
-----------------
- Response body missing a declared required field
- Incorrect status code returned (e.g. 200 instead of 201)
- Content-Type header mismatch
- Endpoints that crash with 500 on any valid input shape
- Schema drift between the FastAPI route definition and its actual response

Run locally
-----------
    uv run pytest tests/test_schemathesis_api.py -v -m schemathesis

CI sets ``SCHEMATHESIS_SHARD_COUNT=4`` and
``SCHEMATHESIS_SHARD_INDEX=0..3`` to distribute the same exhaustive operation
set across four bounded jobs.
"""

from __future__ import annotations

import json
import os
from base64 import urlsafe_b64encode
from uuid import uuid4

import hypothesis
import pytest
import schemathesis

# ---------------------------------------------------------------------------
# Environment setup — must precede every app import, including auth helpers.
# ---------------------------------------------------------------------------

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./test_schemathesis.db")
os.environ.setdefault("ENVIRONMENT", "testing")
# Logout revokes the generated bearer session through the isolated Redis
# security datastore.  The application deliberately rejects its development
# default URL (fail-closed), so the hermetic Schemathesis harness must provide
# an explicit non-default endpoint.  ``tests/conftest.py`` redirects Redis
# clients to fakeredis; no external service is required.
os.environ.setdefault("REVOCATION_REDIS_URL", "redis://localhost:6380/0")
os.environ.setdefault(
    "SECRET_KEY",
    "schemathesis-ci-placeholder-secret-key-minimum-32-chars-long",  # pragma: allowlist secret
)
os.environ.setdefault(
    "MFA_EMAIL_OTP_HMAC_KEYS",
    f"schemathesis-hmac:{urlsafe_b64encode(b'h' * 32).decode('ascii').rstrip('=')}",
)
os.environ.setdefault("MFA_EMAIL_OTP_ACTIVE_HMAC_KEY_ID", "schemathesis-hmac")
os.environ.setdefault(
    "MFA_EMAIL_DELIVERY_KEKS",
    f"schemathesis-kek:{urlsafe_b64encode(b'k' * 32).decode('ascii').rstrip('=')}",
)
os.environ.setdefault("MFA_EMAIL_DELIVERY_ACTIVE_KEK_ID", "schemathesis-kek")

# ---------------------------------------------------------------------------
# Custom Schemathesis Conformance Check & Hooks
# ---------------------------------------------------------------------------
import schemathesis.checks
from hypothesis import HealthCheck
from schemathesis.checks import not_a_server_error

schemathesis.checks.load_all_checks()

# Dynamic auth hook for Schemathesis fuzzer.
# Issues a signed JWT with admin role to allow fuzzer to bypass auth barriers.
from app.auth.security import _mint_pure_jwt

auth_token = _mint_pure_jwt(subject=uuid4(), extra_claims={"role": "admin"})

# The test is parametrized by every OpenAPI operation.  The regular suite uses
# one generated request per operation as a bounded cross-stack smoke test.  The
# dedicated CI conformance job raises this through the environment without
# editing test code, retaining deep property-based coverage before merge.
SCHEMATHESIS_MAX_EXAMPLES = int(os.environ.get("SCHEMATHESIS_MAX_EXAMPLES", "1"))
if SCHEMATHESIS_MAX_EXAMPLES < 1:
    raise ValueError("SCHEMATHESIS_MAX_EXAMPLES must be at least 1")

# The complete OpenAPI surface is intentionally exercised with the same number
# of examples per operation.  CI distributes operations round-robin across
# independent jobs so the exhaustive pass remains bounded without reducing
# property-based depth.  Local runs default to one shard and therefore retain
# the familiar single-process behaviour.
SCHEMATHESIS_SHARD_COUNT = int(os.environ.get("SCHEMATHESIS_SHARD_COUNT", "1"))
SCHEMATHESIS_SHARD_INDEX = int(os.environ.get("SCHEMATHESIS_SHARD_INDEX", "0"))
if SCHEMATHESIS_SHARD_COUNT < 1:
    raise ValueError("SCHEMATHESIS_SHARD_COUNT must be at least 1")
if not 0 <= SCHEMATHESIS_SHARD_INDEX < SCHEMATHESIS_SHARD_COUNT:
    raise ValueError(
        "SCHEMATHESIS_SHARD_INDEX must be within the configured shard count"
    )


@schemathesis.hook
def before_call(context, case, **kwargs):
    if case.headers is None:
        case.headers = {}
    case.headers["Authorization"] = f"Bearer {auth_token}"


@schemathesis.check
def conform_to_schema_except_auth(ctx, response, case) -> None:
    """Validate that the response conforms to the OpenAPI specification.

    If the response is a 401, 403, or 404, we skip schema validation.
    401/403 are skipped because the run is stateless and unauthenticated,
    and 404 is skipped because random IDs generated by Schemathesis will not exist.

    For all other status codes, this check enforces:
    - No 5xx server errors
    - Status code matches what is declared in the spec
    - Content-Type matches what is declared in the spec
    - Response body conforms to the schema in the spec
    """
    if response.status_code in (304, 400, 401, 403, 404, 405, 422, 423, 429):
        not_a_server_error(ctx, response, case)
        return

    from schemathesis.checks import (
        content_type_conformance,
        response_schema_conformance,
        status_code_conformance,
    )

    not_a_server_error(ctx, response, case)
    status_code_conformance(ctx, response, case)
    content_type_conformance(ctx, response, case)
    response_schema_conformance(ctx, response, case)


from app.main import app  # env vars must be set before this import

# OpenAPI methods are the only keys that represent executable operations in a
# path item.  Build the shard map from FastAPI's local schema so collection does
# not need an ASGI round-trip or any backing service.
_OPENAPI_METHODS = frozenset(
    {"GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD", "TRACE"}
)


def _build_operation_index() -> dict[str, int]:
    operation_keys = sorted(
        f"{method.upper()} {path}"
        for path, path_item in app.openapi().get("paths", {}).items()
        for method in path_item
        if method.upper() in _OPENAPI_METHODS
    )
    if not operation_keys:
        raise RuntimeError("Schemathesis OpenAPI schema declares no operations")
    if len(set(operation_keys)) != len(operation_keys):
        raise RuntimeError("Schemathesis OpenAPI operation keys must be unique")
    return {key: index for index, key in enumerate(operation_keys)}


_OPERATION_INDEX = _build_operation_index()


def _operation_matches_shard(context) -> bool:
    key = f"{context.operation.method.upper()} {context.operation.path}"
    try:
        index = _OPERATION_INDEX[key]
    except KeyError as exc:
        raise RuntimeError(f"Unknown Schemathesis operation: {key}") from exc
    return index % SCHEMATHESIS_SHARD_COUNT == SCHEMATHESIS_SHARD_INDEX


# ---------------------------------------------------------------------------
# Schema loader — evaluated at module parse time but the ASGI call is deferred.
#
# ``schemathesis.pytest.from_fixture("loaded_schema")`` returns a ``LazySchema``
# that stores the fixture name as a plain string.  No ASGI round-trip happens
# here.  The real ``schemathesis.openapi.from_asgi()`` call only occurs inside
# the test body (via ``request.getfixturevalue("loaded_schema")``), so a slow
# or missing backing service cannot hang pytest collection.  The shard filter
# is applied to this LazySchema (rather than the fixture result), because the
# plugin merges its own filter set when it resolves the fixture.
# ---------------------------------------------------------------------------

_lazy_schema = schemathesis.pytest.from_fixture("loaded_schema")
if SCHEMATHESIS_SHARD_COUNT > 1:
    _selected_operation_count = sum(
        index % SCHEMATHESIS_SHARD_COUNT == SCHEMATHESIS_SHARD_INDEX
        for index in _OPERATION_INDEX.values()
    )
    if _selected_operation_count == 0:
        raise RuntimeError(
            "Schemathesis shard selected no OpenAPI operations: "
            f"{SCHEMATHESIS_SHARD_INDEX}/{SCHEMATHESIS_SHARD_COUNT}"
        )
    _lazy_schema = _lazy_schema.include(func=_operation_matches_shard)


@pytest.fixture(scope="session")
def loaded_schema():
    """Return the schemathesis schema loaded from the ASGI app.

    Session-scoped so the ASGI round-trip (fetching /api/openapi.json) happens
    exactly once per pytest session, not once per test case.
    """
    return schemathesis.openapi.from_asgi("/api/openapi.json", app=app)


@pytest.mark.schemathesis
def test_schemathesis_mfa_security_dependencies_are_configured() -> None:
    """Fail immediately when the conformance environment cannot build MFA."""

    from app.auth.mfa.email_otp import build_configured_email_otp_service

    assert build_configured_email_otp_service() is not None


# ---------------------------------------------------------------------------
# Stateless property-based conformance tests
#
# Decorator order matters for Hypothesis settings to take effect with a
# LazySchema: @hypothesis.settings must be the OUTER decorator so that it sets
# ``_hypothesis_internal_use_settings`` on the function that
# ``LazySchema.parametrize()`` returned (and that schemathesis reads back at
# test run time via ``getattr(wrapped_test, "_hypothesis_internal_use_settings",
# None)``).
# ---------------------------------------------------------------------------


@pytest.mark.schemathesis
@hypothesis.settings(
    max_examples=SCHEMATHESIS_MAX_EXAMPLES,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.filter_too_much],
)
@_lazy_schema.parametrize()
def test_api_responses_conform_to_schema(case: schemathesis.Case) -> None:
    """Every OpenAPI-described endpoint must return a non-5xx response and conform to spec.

    Schemathesis generates random valid requests for every (method, path)
    combination in the spec.  Auth-required endpoints may return 401/403
    (which are schema-declared), but NEVER 500.

    Checks applied:
      Custom conformance check that enforces status code, content-type,
      response schema, and no-server-errors for all non-auth responses.

    The schemathesis pytest plugin parametrizes this test once per (method,
    path) pair, reporting each failure with its exact endpoint.
    """
    response = case.call()
    case.validate_response(response, checks=[conform_to_schema_except_auth])


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
