# API versioning and compatibility strategy

## Current OpenAPI surface
- The FastAPI application exposes the OpenAPI document at `/api/openapi.json` with semantic version `1.0.0` and groups HTTP routes under the `/api/v1` prefix. WebSocket endpoints and legacy web push fallbacks remain at root-level paths for backward compatibility. 【F:root/app/main.py†L55-L120】【F:root/app/main.py†L229-L274】
- The captured schema documents the active surface for authentication, users, news, events, schedule, notifications, and supporting features such as Spotify integration and stats. These routes are preserved in the contract snapshot for compatibility checks. 【F:root/tests/contracts/snapshots/api_openapi_v1.json†L4611-L4878】

## Versioning approach
- **Semantic versioning (semver):** The published API version is pinned in code and validated against semver (`MAJOR.MINOR.PATCH`). Any breaking change that would drop or alter existing routes or response contracts requires a major version bump (e.g., `2.0.0`). Backward-compatible additions (new optional fields or new endpoints) should increment the minor version, while non-breaking fixes increment the patch version. 【F:root/app/core/versioning.py†L6-L24】
- **Versioned routing:** All REST endpoints live behind the `/api/v1` router. Future versions should introduce a dedicated router prefix (e.g., `/api/v2`) while keeping `/api/v1` mounted until the announced deprecation window ends. Shared middleware and observability should be version-agnostic to avoid duplication. 【F:root/app/main.py†L229-L274】
- **Graceful degradation:** Legacy push notification routes remain exposed without a version prefix to serve older clients. The same pattern should be followed for any v1 feature that needs a deprecation runway: keep the legacy router mounted, mark responses as deprecated in the OpenAPI schema, and gate new behavior behind the newer versioned prefix. 【F:root/app/main.py†L276-L281】

## Compatibility guarantees
- **Contract snapshots:** The canonical OpenAPI document is persisted under `tests/contracts/snapshots/api_openapi_v1.json`. Contract tests assert that the live schema is a superset of the snapshot, preventing removals or incompatible changes to documented fields. 【F:root/tests/contracts/test_openapi_contract.py†L37-L59】【F:root/tests/contracts/utils.py†L19-L61】
- **Core route coverage:** Regression checks ensure that key product areas (auth, users, news, events, schedule, notifications) remain available under the `/api/v1` namespace. Any removal or renaming of these routes will fail tests, prompting either a semver-major change or the addition of compatibility shims. 【F:root/tests/contracts/test_openapi_contract.py†L23-L53】

## Release checklist
- Update `API_VERSION` before shipping changes, choosing the semver increment based on whether the OpenAPI diff is additive or breaking. 【F:root/app/core/versioning.py†L6-L24】
- Regenerate the OpenAPI snapshot after intentional additive changes using the helper utilities in `tests/contracts/utils.py`, and commit the new snapshot alongside code changes.
- For breaking changes, introduce a new router (e.g., `/api/v2`), keep `/api/v1` mounted during the deprecation period, and document migration steps in the API reference.
