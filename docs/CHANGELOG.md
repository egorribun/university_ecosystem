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
- Backend (routine-e5): two ws-hub NATS integration tests via
  testcontainers-go (`hub_integration_test.go`, `//go:build integration`)
  — `TestIntegration_NATSChatMessageDelivery` and
  `TestIntegration_NATSMalformedMessageDropped`. Run via
  `make -C services/ws-hub test-integration` (Docker required).
  Remaining ADR-022 tests (file-processor, gateway, two more
  ws-hub) deferred to follow-up routine sessions.

### Docs
- ADR-022 (routine-e5): scaffolding for testcontainers integration
  testing — three Makefiles (`test-integration` target gated behind
  `//go:build integration`), testcontainers-go @ v0.42.0 added to
  ws-hub / file-processor / gateway go.mod, new reusable workflow
  `.github/workflows/reusable-go-integration-tests.yml`. ADR status
  remains `Proposed` until the full test set lands; non-blocking
  initially per ADR §Migration step 5.
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
