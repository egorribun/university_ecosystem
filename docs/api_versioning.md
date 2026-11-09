# API versioning and compatibility

## Current contract

The FastAPI application publishes semantic API version `1.1.1`. This API contract version is separate from the MVP release version `1.0.0`. Its REST
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

## My-events paging and v1 limit exception (AUD-260)

`GET /api/v1/events/my/page` provides cursor-based paging and server-side
category and date filters. `limit` is 1–100 (default 20). The response contains
`items`, `total` (null), `limit`, `cursor`, `next_cursor`, and `has_more`.
Clients should follow `next_cursor` until `has_more` is false, keeping the same
locale, filters, sort, limit, and upcoming cutoff for each cursor chain.
`lang` selects the response locale using the existing locale fallback rules.
`newest` and `upcoming` retain ascending start-time and ID order;
`newest_desc` adds descending start-time and ID order. `popular` uses actual
attendance counts and server ordering. Page items expose those actual counts.

The owner approved a narrow, intentional v1 compatibility exception for
`GET /api/v1/events/my`: accounts with up to 100 registrations still receive
the complete array in ascending start-time and ID order, with the legacy zero
participant counts. An account with more than 100 receives HTTP 409 with
problem code `events_my_pagination_required`, `legacy_limit: 100`,
`pagination_url: /api/v1/events/my/page`, and a `Link` to the page endpoint.
This changes behavior for existing array clients with more than 100 entries;
they must migrate to the page endpoint and handle its cursor and filters. The
exception is specific to AUD-260 and does not authorize other v1 breaks.

Both My routes and event detail read fresh data before deriving an ETag. They
do not reuse a server-side cached payload, and send `Cache-Control: private,
no-store`. Conditional 304 responses are based on the freshly derived payload;
overflow is checked before returning a legacy 304. This contract describes the
source change, not a claim that deployed clients have already migrated.

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

## Event datetime validation (API 1.1.1)

Event creation and public updates reject mixed timezone-aware and naive
start/end pairs with a validation error (HTTP 422), rather than leaking a
comparison TypeError. All-naive and all-aware pairs retain their existing
ordering semantics. Public updates still require both non-null endpoints
when either is supplied; title-only and internal partial-time updates remain
unchanged. The timezone correction does not modify stored data. String-input
bounds are governed by the separate owner-approved exception below.


## One-time v1 input-bound exception: events (2026-10-21)

For AUD-256, the owner explicitly approved restricting event creation and
updates in the existing v1 API after reviewing the compatibility impact.
The migrated Event columns have no string-length bound, even though ORM metadata
declares lengths; these request limits are therefore a deliberate narrowing,
not merely enforcement of an already universal database constraint.
This exception is limited to AUD-256 and does not authorize other breaking
v1 changes. API 1.1.1 retains the separately verified timezone patch.

After inherited whitespace trimming and the existing field sanitizers:
- title, title_en, location, location_en and speaker are bounded to 512 characters;
- event_type and event_type_en are bounded to 128 characters;
- image_url is bounded to 2048 characters.

Non-space overflow is rejected as a validation error (HTTP 422).
For compatibility with bounded character-column storage, only excess U+0020 spaces
exposed by later CleanStr control removal are normalized to the bounded
prefix; spaces inside that prefix remain intact. Non-space characters are
never silently truncated. Ordinary edge whitespace retains its existing
normalization, and optional whitespace-only text still becomes None.
These are post-normalization bounds, not a raw-input JSON Schema maxLength:
raw input can be longer while normalizing to a valid stored value.

Description/about Text fields and their translations remain uncapped.
No migration, existing-row rewrite, truncation or deletion is part of this
change. Existing long rows remain readable, and omitted fields in a partial
update are not newly validated or rewritten. Only newly supplied bounded
fields are subject to the input rules.

Validation messages use the existing schema-level translation convention:
without request locale context, they default to English. Both English and
Russian dictionary entries exist; this change does not add Accept-Language
propagation into Pydantic validation.
