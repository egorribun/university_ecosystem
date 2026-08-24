# API versioning and compatibility

## Current contract

The FastAPI application publishes semantic API version `1.0.0`. Its REST
surface is mounted under `/api/v1`; health, WebSocket, GraphQL and well-known
discovery endpoints intentionally use infrastructure-specific root paths.
Interactive documentation and `/api/openapi.json` are available only in
development-like environments.

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
