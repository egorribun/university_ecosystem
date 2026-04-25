# API Changelog

All notable changes to the API will be documented in this file.

## [Unreleased]

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
