# API versioning and compatibility

## Current contract

The FastAPI application publishes semantic API version `1.0.0`. Its REST
surface is mounted under `/api/v1`; health, WebSocket, and well-known
discovery endpoints intentionally use infrastructure-specific root paths. The
backend GraphQL endpoint is excluded from the MVP and is not a FastAPI route;
see [ADR-046](adr/ADR-046-codebase-consolidation-audit.md). The Go
file-processor GraphQL runtime is a separate service. Interactive documentation
and `/api/openapi.json` are available only in development-like environments.

The implementation lives in
[`app/main.py`](../app/main.py), while the version and prefix constants are
defined in [`app/core/versioning.py`](../app/core/versioning.py).

## Compatibility policy

- Breaking request, response, or route changes require a new major API version
  and a separately mounted router such as `/api/v2`.
- Backward-compatible endpoints and optional fields increment the minor
  version. Compatible fixes increment the patch version.
- `/api/v1` remains mounted throughout any announced migration window.
- Infrastructure endpoints must keep stable paths unless every in-repository
  and deployed consumer is migrated together.

## One-time v1 security exception: directory search (2026-10-17)

For AUD-201, the owner approved a narrow restriction in the existing v1 API:
authenticated non-admin `GET /api/v1/users` requests must use an effective
name query of at least two Unicode code points after trimming. Existing
normalization is preserved: a non-empty `full_name` takes precedence and legacy
`search` is its fallback. The authorization check runs before repository
access, including requests with `after_id`.

Administrator behavior and service-internal calls with `current_user=None`
remain unchanged. The restriction matches the existing two-character
add-member UI. It intentionally rejects formerly accepted one-character
non-admin requests without changing the OpenAPI schema or API version.
This owner-approved security exception is specific to AUD-201, not a general
permission to make incompatible v1 changes.

This does not establish prevention of bulk harvesting: longer substring
queries and repeated cursor pages can still retrieve matching public
profiles. Broader directory scoping or dedicated anti-abuse limits require
a separate policy decision.

## Enforcement

The canonical OpenAPI snapshot is
[`tests/contracts/snapshots/api_openapi_v1.json`](../tests/contracts/snapshots/api_openapi_v1.json).
[`tests/contracts/test_openapi_contract.py`](../tests/contracts/test_openapi_contract.py)
checks semantic versioning, required route groups, operation completeness and
backward compatibility. The comparison accepts additive changes but rejects
removed or changed snapshot fields.

## Release checklist

1. Classify the OpenAPI diff as patch, additive minor, or breaking major.
2. Update `API_VERSION` for an intentional contract release.
3. Regenerate the snapshot only after reviewing the normalized schema diff.
4. For a breaking release, add a new versioned router and migration guidance;
   do not silently rewrite the v1 contract.
