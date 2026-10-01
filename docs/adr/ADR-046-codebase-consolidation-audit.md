# ADR-046: Codebase Consolidation After the 2026-10 Architecture Audit

## Status

Accepted

## Date

2026-10-01

## Context

A read-only audit of the whole repository (Python, TypeScript, Go, Rust, infra)
compared three views of every subsystem: what the code imports, what the
documents promise, and what the tests exercise. REST and GraphQL contracts were
already consistent (`frontend/openapi.json` equals `app.openapi()`;
`schema.graphql` equals the Strawberry export; every hand-written frontend call
resolves to a backend route). The findings were elsewhere: code kept alive only
by the 100 % coverage and mutation gates, and subsystems whose documentation
claimed behaviour the runtime did not have.

## Decisions

### Fixed (behaviour was wrong or missing)

| Subject | Decision |
|---|---|
| User statistics | `UserAnalyticsService` is the single implementation. Attendance means **event registration** (product decision): `registered / active events` in the window with a trend against the previous window. Participation reports hours, distinct event types and trend. The orphaned duplicate `StatsService` and `AnalyticsService` were removed. |
| Grades | The `grades` table is the single source of truth (statistics previously parsed free-text notification bodies). `GradeService` is wired through Dishka and exposed as `POST /api/v1/grades` and `PATCH /api/v1/grades/{id}` (teacher or admin; a teacher may only correct grades they assigned). Each change writes an audit domain event, notifies the student and invalidates the statistics cache. |
| Session validation | `app/services/auth/session_policy.py` is the one definition of "usable session" (ownership, revocation, expiry, **MFA epoch**). REST, GraphQL and the Python WebSocket fallback all apply it; before this change only REST rejected sessions minted before an MFA change. |
| SpiceDB Watch (ADR-020) | `start_permission_watch` is started from the lifespan in API processes, and the permission cache is also cleared after a cleanly closed stream. |
| Unknown-account login | Costs one Argon2 verification (`verify_dummy_password`) instead of a random sleep, so response time no longer reveals which e-mail addresses exist. |
| Dead letters | One coherent contour: the NATS task worker backs off exponentially, parks a task in `dead_letter_jobs` after `NATS_TASK_MAX_DELIVERIES` (default 5) and terminates it (previously it was NAKed forever); `/admin/dlq/replay` re-enqueues through the broker (previously every replay failed for lack of a handler); non-durable event-handler failures reach the in-memory DLQ; terminal outbox failures (`failed_outbox_events`) can be listed and requeued through `/admin/dlq/outbox`. |
| `VectorService` | The request-scoped provider is a finalizing generator, so the httpx pool is closed. |
| Search | `/api/v1/search` read Elasticsearch indices that nothing ever filled. News and events are now indexed from the domain events, removed on delete, and `python -m app.cli search reindex` rebuilds both indices. |
| ws-hub | The per-client inbound rate limit lived in an unreachable function; it is enforced in the live read loop again (`rate_limit_exceeded` frame). |
| Periodic cleanup | Documented as it really runs (hourly / 6 h / 02:00 UTC). The per-job `*_CLEANUP_INTERVAL_SECONDS` knobs, seven superseded per-service schedulers and the double partition scheduling were removed. |

### Retired (no production consumer)

Vector sharding (Python service, hash ring, Go gateway router) — it required a
Qdrant cluster that no compose file or chart deploys; ABAC engine; tag-based
cache invalidation; event decorators/registry/retry and NATS task registry;
ETag and timing middleware; retry, coalescing and batching helpers; the HMAC
`/api/v1/.well-known/jwks.json` stub; legacy ws-hub JWT validation and offline
replay helpers; unused gateway/file-processor JWT constructors; 25 frontend
components and utilities reachable only from tests and Storybook; 26 settings
that nothing read. The MinIO SDK client moved from `app/` to the chaos-test
helper `tests/minio_chaos_client.py`.

### Deliberately kept

- **GraphQL** stays: it is documented as a public API surface. Its
  authentication now matches REST. There is no in-repository consumer, so a
  future decision to retire it needs external-client evidence.
- **Python `/ws/chat` fallback** stays for topologies without ws-hub; its wire
  format differs from ws-hub for control errors (`message` vs `code`/`detail`),
  which the frontend schema tolerates. A shared frame schema is follow-up work.
- **Feature-flag scaffold** (flagd, admin page, OpenFeature) stays empty until
  the first flag is registered together with its evaluation call site
  (`tests/test_feature_flag_architecture_contract.py`).
- **`app/cli/migrate_passwords.py`** stays as the read-only bcrypt deployment
  gate.
- **Legacy non-Dishka auth adapters** stay until the tests that override them
  migrate (ADR-033).
- **`vector_chunks` table and `VectorChunk` model** stay. Nothing writes to
  them, but dropping a table needs a PostgreSQL-verified migration plus the
  ADR-036 inventory update, which could not be exercised in the audit
  environment.

## Consequences

- Roughly 30 k net lines of production, test and generated code are gone; the CI budget and the
  mutation universe shrink accordingly.
- Statistics values change: attendance is no longer a constant 100 %.
  Environments that stored grades only as `type="grade"` notifications must
  re-enter them through `POST /api/v1/grades`.
- `NATS_TASK_MAX_DELIVERIES`, `NATS_TASK_RETRY_BASE_DELAY_SECONDS` tune the
  task worker; Elasticsearch outages never fail the originating write, and
  `search reindex` repairs the drift afterwards.
