# API Changelog

All notable changes to the API will be documented in this file.

## [Unreleased]

### Added
- Per-endpoint rate limiting with path-specific rules
- Tag-based cache invalidation (`CacheTag` enum)
- Enhanced audit logging with `SecurityEvent` types
- Business metrics for product analytics

### Changed
- Rate limit headers now reflect endpoint-specific limits

## [1.0.0] - 2024-12-28

### Initial Release
- Authentication (JWT, TOTP MFA)
- User management
- Events, News, Schedule APIs
- Push notifications
- Real-time WebSocket chat
