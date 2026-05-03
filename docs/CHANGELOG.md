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
<!-- Behavioural / configuration changes that don't fit Added go here. -->

### Fixed
<!-- Bug fixes go here. Reference the audit / wave / issue identifier. -->

### Tests
<!-- Test-only additions (no production code change). Backend / frontend /
     E2E grouped here; mention the module and the type of test
     (property-based, concurrency, axe, interaction). -->

### Docs
<!-- Docstring / JSDoc / ADR / README changes. -->

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
