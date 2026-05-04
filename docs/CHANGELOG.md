# API Changelog

All notable changes to the API will be documented in this file.

## [Unreleased]

### Added
- Unit tests for Go `InternalAPIAuthClient` in `ws-hub` service (Pkg/Hub).
- Unit tests for `MaxQueryDepthMiddleware` and query depth estimation in `file-processor`.
- Expanded frontend hook coverage: `useScheduleTime`, `useShare`, `useActivityData`.
- Unit tests for Trusted Types utilities in frontend.
- Property-based tests for UUIDv7 (monotonicity), HTML sanitization (idempotency), and pagination bounds.

### Changed
- i18n (routine-g3): canonicalised four shared dialog labels under
  `common:buttons.{cancel,confirm,clear,delete}` and dropped the
  top-level alias once all callers migrated. `confirm` and `clear`
  added to the `buttons` block (previously only `cancel`/`delete`
  existed there). Six messenger / page call-sites refactored.

### Fixed
- Contracts (routine): explicit `encoding="utf-8"` when reading the
  OpenAPI snapshot in `tests/contracts/test_openapi_contract.py`.
  Default `Path.read_text()` uses platform locale (cp1251 on
  Windows) and corrupts the em-dash in route descriptions; Linux
  CI was unaffected because UTF-8 is the locale default.
- i18n (routine-g3): closed 26 missing keys that were shipping as
  English fallbacks to RU users — `system:pageError.*`,
  `notifications:new`, 12 messenger keys (Profile modal, dialogs,
  selectChatDesc), `dashboard:pageTitle`, `common:{active,inactive}`.
- A11y (routine-g3): replaced 7 hardcoded English `aria-label`
  values on a `<html lang="ru">` document with `t()` calls
  (WCAG 3.1.2 Language of Parts) — ChatWindow message list,
  MessageInput Remove/Attachments buttons, NavbarOverflowMenu,
  UserMenu loading state, ProfileCardSkeleton, ScheduleCardSkeleton.

### Tests
- Backend (routine, primary-device verification): the 17 new test
  modules from secondary-device contributions (~4 100 LoC across
  `tests/test_ratelimit_concurrency.py`,
  `tests/test_cache_invalidation_coherence.py`,
  `tests/test_webpush_retry.py`,
  `tests/graphql/test_permissions.py`,
  `tests/cqrs/test_bus.py`,
  `tests/services/test_chat_helpers.py`,
  csrf / etag / query-batching / sanitization / quiet-hours /
  property-based suites) verified end-to-end on primary via
  `uv run pytest tests/`: **2 805 passed / 25 skipped / 0 failed**.
- Frontend (routine, primary-device verification): full vitest run
  green at **859 passed / 12 skipped / 0 failed** (130 test files);
  i18n parity 18/18; e2e Playwright chromium full sweep + URL-state
  6/6 + cross-browser a11y 14p + 2 flaky-passed (effective 16/0).
- Backend (routine-e5): full ADR-022 testcontainers integration test
  set landed across all three Go services — **10 of 11 §Decision tests
  shipped** in this routine session (combined with prior session's
  `b65ba02a1`). Run via `make -C services/{ws-hub,file-processor,gateway}
  test-integration` (Docker required) or via the new CI jobs (advisory
  initially per ADR §Migration step 5).
  - **ws-hub (5 tests)**: `TestIntegration_NATSChatMessageDelivery`,
    `NATSMalformedMessageDropped`, `BroadcastOversizedMessageDropped`
    (RZ-23-05 60 KB cap), `HandleRegisterMaxClients` (TD-31-05
    authoritative enforcement), `HandleWebSocketPrecheckMaxClients`
    (TD-31-05 HTTP 503 pre-check via real Redis ticket validation).
  - **file-processor (3 tests)**: `MinIOResizeImageHappyPath`
    (rescoped from MinIO+ClamAV — ClamAV not yet integrated in
    production code per workflow.go:57), `GraphQLDepthAndTimeout`
    (RZ-24-05 depth=10 + timeout=30s), `GRPCPathTraversalRejection`
    (RZ-27-04 + RZ-26-04 max key length 1024).
  - **gateway (4 tests + 1 unit)**: `RateLimiterRedisInMemoryFallback`
    (replaces planned RedisCircuitBreaker — gateway uses 2-tier
    fallback per P0-W5-04 / RZ-22-06, not a circuit breaker),
    `L1CacheXFetchProbabilisticRefresh` (PERF-31-02 — paired with
    `TestShouldRefreshProbabilistic_BoundaryAndStatistical` unit test
    deriving the e^(-remaining/ttl) refresh-rate formula),
    `GRPCDefaultTimeout` (RZ-31-05), `OTELCompositePropagator`
    (MOD-31-02, W3C TraceContext + Baggage).
  - Versions: testcontainers-go v0.42.0; nats:2.12-alpine;
    redis:7-alpine; minio/minio:RELEASE.2025-09-07T16-13-09Z (matches
    prod docker-compose). All 12 integration tests pass on warm Docker
    in ~10s combined wall-clock.

### Docs
- ADR-022 (routine-e5): **finalized — Status `Proposed → Accepted
  (2026-05-04, primary device routine)`**. New `## Implementation Notes`
  section documents the 10/11 §Decision deliverable, container versions
  used (testcontainers-go v0.42.0 + nats:2.12-alpine + redis:7-alpine +
  minio/minio:RELEASE.2025-09-07T16-13-09Z), and the **4 documented
  deferrals** with explicit blocking-condition rationale:
  1. ws-hub NATS JetStream Nak/redeliver — current code uses core NATS
     pub/sub, JetStream-mode tests are a future-wave item.
  2. ws-hub JWKS hot-reload — needs httptest JWKS-server fixture +
     token-signing harness, scoped as own future-wave item.
  3. file-processor ClamAV scan — production code lacks ClamAV
     integration (workflow.go:57 has only "v2: reserved" comment).
     §Decision test #1 was rescoped to MinIO-only happy path.
  4. gateway RedisCircuitBreaker — `circuit_breaker.py` exists in the
     Python backend (PERF-30-01) but not in the Go gateway. Replaced
     with `RateLimiterRedisInMemoryFallback` covering the actual Go
     gateway resilience pattern (2-tier fallback per P0-W5-04 /
     RZ-22-06). Porting to Go is a separate scope decision.
  CI jobs `go-integration-{ws-hub,file-processor,gateway}` wired into
  `ci.yml` as **advisory (non-blocking) initially** per ADR §Migration
  step 5: listed in `ci-success.needs` so the workflow waits for them,
  but excluded from the blocking results array. Status reported via
  `$GITHUB_STEP_SUMMARY` in a 3-row table. Promote to blocking once
  30-day flake rate < 1 %.
- F4 (routine): `frontend/src/hooks/index.ts` barrel with
  `@fileoverview` JSDoc — single stable surface for 54 root-level
  hooks (`import { useDebounced, ... } from "@/hooks"`).
  Sub-folders (`auth/`, `features/`, `ui/`) keep their internal
  organisation and are not re-exported.

## [1.1.0] - 2026-04-26

### Added
- Per-endpoint rate limiting with path-specific rules
- Tag-based cache invalidation (`CacheTag` enum)
- Enhanced audit logging with `SecurityEvent` types
- Business metrics for product analytics
- New architectural decision records (ADR-014 through ADR-017) regarding testing strategies
- Storybook integration for frontend component documentation (`EventsHeader`, `NewsList`, `NewsFormDialog`)

### Changed
- Rate limit headers now reflect endpoint-specific limits
- Go toolchain upgraded to v1.26.2 across all backend services (`gateway`, `file-processor`, `ws-hub`, `uni-cli`) to resolve standard library vulnerabilities
- Enforced strict static type checking in Python configuration module by replacing `type: ignore` suppressions with `typing.cast`
- Stabilized Lighthouse CI pipeline by adding `VITE_LHCI` toggle to mock unperformant redirect routes

### Fixed
- MFA race conditions mitigated by enforcing row-level locking (`SELECT FOR UPDATE`) during challenge consumption
- Go `osv-scanner` and `govulncheck` CI pipeline pathing and vulnerability suppressions
- Frontend test suite flakes associated with multiple elements and i18n translation key assertions

## [1.0.0] - 2024-12-28

### Initial Release
- Authentication (JWT, TOTP MFA)
- User management
- Events, News, Schedule APIs
- Push notifications
- Real-time WebSocket chat
