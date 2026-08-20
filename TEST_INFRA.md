# E2E Test Infra: University Ecosystem Platform

## Test Philosophy
- Opaque-box, requirement-driven. Derived from `ORIGINAL_REQUEST.md`.
- Multi-tier validation: Feature Coverage (Tier 1), Boundary & Corner Cases (Tier 2), Cross-Feature Interactions (Tier 3), Real-World Application Workloads (Tier 4).

## Feature Inventory
| # | Feature | Source | Tier 1 | Tier 2 | Tier 3 |
|---|---------|--------|:------:|:------:|:------:|
| 1 | Frontend Docker Normalization & Build Pipeline | ORIGINAL_REQUEST §R1 | 5 | 5 | ✓ |
| 2 | Frontend Client/SSR/SW/Shell Artifacts | ORIGINAL_REQUEST §R1 | 5 | 5 | ✓ |
| 3 | Frontend 100% Test Coverage & Typing | ORIGINAL_REQUEST §R1 | 5 | 5 | ✓ |
| 4 | Backend OTEL Deadlock Resolution | ORIGINAL_REQUEST §R2 | 5 | 5 | ✓ |
| 5 | Python Backend 100% Coverage Suite | ORIGINAL_REQUEST §R2 | 5 | 5 | ✓ |
| 6 | Go Microservices 100% Statement Coverage | ORIGINAL_REQUEST §R2 | 5 | 5 | ✓ |
| 7 | Rust Native Crates Tests & Clippy | ORIGINAL_REQUEST §R2 | 5 | 5 | ✓ |
| 8 | Multi-Stack Static Analysis & Linters | ORIGINAL_REQUEST §R3 | 5 | 5 | ✓ |
| 9 | Database Migration Forward/Backward Roundtrip | ORIGINAL_REQUEST §R3 | 5 | 5 | ✓ |
| 10 | Security & Supply-Chain Scans | ORIGINAL_REQUEST §R3 | 5 | 5 | ✓ |
| 11 | Docker Compose 25-Service Health | ORIGINAL_REQUEST §R3 | 5 | 5 | ✓ |
| 12 | GitHub Repository Ruleset Governance | ORIGINAL_REQUEST §R4 | 5 | 5 | ✓ |
| 13 | Release Git Staging, Commit & CI Verification | ORIGINAL_REQUEST §R4 | 5 | 5 | ✓ |

## Test Architecture
- **E2E Playwright Suite**: `frontend/playwright.config.ts` (42 spec files across Chromium, Firefox, WebKit).
- **Backend Conformance & Contract Tests**: `tests/test_schemathesis_api.py`, `tests/contracts/`.
- **System Migration Test Harness**: `scripts/test_migrations.py`.
- **Full Docker Stack Health Probe Harness**: `scripts/dc.ps1 ps`, `start-docker.ps1`.
- **Security Audit Harness**: `scripts/audit_dependencies.py`, `scripts/verify_secrets_baseline.py`.

## Real-World Application Scenarios (Tier 4)
| # | Scenario | Features Exercised | Complexity |
|---|----------|--------------------|------------|
| 1 | Student Full Lifecycle (Registration -> Auth -> Event RSVP -> Chat Realtime -> Profile Update) | F2, F3, F5, F6, F7, F11 | High |
| 2 | Admin Moderation & RLS Enforcement (Content Moderation -> SpiceDB Authorization -> Audit Logs) | F4, F5, F6, F10, F11 | High |
| 3 | Realtime High-Throughput Chat Messaging & Presence Sync | F2, F6, F11 | High |
| 4 | File Upload & Async Processing Workflow (MinIO -> Temporal -> File Processor -> GraphQL) | F2, F5, F6, F11 | High |
| 5 | Database Migration Zero-Downtime Rollback & Re-apply | F9, F11 | Medium |
| 6 | Zero-Trust JWT Rotation & Token Revocation Handling | F4, F5, F6, F10 | High |

## Coverage Thresholds
- Tier 1: ≥65 test cases across 13 features
- Tier 2: ≥65 test cases covering boundary and corner conditions
- Tier 3: Pairwise coverage of all major feature pairs
- Tier 4: ≥6 realistic end-to-end workload scenarios
