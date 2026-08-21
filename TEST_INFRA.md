# E2E Test Infra: University Ecosystem Platform

## Test Philosophy
- Multi-stack end-to-end verification, quality contracts, and closed-loop regression prevention.
- Coverage Mandate: 100% statement, branch, function, and line coverage across critical backend and frontend paths per `quality/quality-contract.json`.
- Zero-Debt Target: All 14 PR #1249 CI/CD checks, mutation testing shards, and harness suites passing cleanly.

---

## Feature Inventory

| # | Feature | Source (requirement) | Tier 1 (Unit/Contract) | Tier 2 (Boundary/Security) | Tier 3 (Integration/Race) | Tier 4 (E2E/Matrix) |
|---|---------|----------------------|:----------------------:|:--------------------------:|:-------------------------:|:-------------------:|
| F1 | Skip Anti-Pattern Verification | `check_orphans_and_anti_patterns.py` | ✓ | ✓ | ✓ | ✓ |
| F2 | Auth Cookie Security Protocol | `test_auth_cookie_flow.py` | ✓ | ✓ | ✓ | ✓ |
| F3 | Helm Dependency Contracts | `test_docker_startup_contracts.py` | ✓ | ✓ | ✓ | ✓ |
| F4 | Mutmut Discovery Isolation | `mutmut_stats_shard.py` | ✓ | ✓ | ✓ | ✓ |
| F5 | Harness Safety Interceptor | `verify_challenger_pre_tool.py` | ✓ | ✓ | ✓ | ✓ |
| F6 | Asset Git Tracking | `git status` / `.gitignore` | ✓ | ✓ | ✓ | ✓ |
| F7 | Documentation Parity | `audit_links.py` / `compare_readmes.py` | ✓ | ✓ | ✓ | ✓ |
| F8 | WS-Hub Benchmark Ratio | `compare_paired_benchmarks.py` | ✓ | ✓ | ✓ | ✓ |
| F9 | Playwright Cross-Browser Matrix | `playwright test` (Chromium/Firefox/WebKit) | ✓ | ✓ | ✓ | ✓ |
| F10 | PR #1249 Aggregator Gate | `gh pr checks 1249` / `verify_harness.py` | ✓ | ✓ | ✓ | ✓ |

---

## Test Architecture
- **Developer Harness Test Runner**: `python verify_harness.py` (31 tests across 7 test suites).
- **Backend Test Runner**: `pytest tests/` (unit, integration, contracts, mutmut stats).
- **Frontend Test Runner**: `cd frontend && npm run test` (Vitest unit & store tests).
- **Frontend E2E Runner**: `cd frontend && npx playwright test` (Chromium, Firefox, WebKit, Mobile WebKit).
- **Go Microservices Tests**: `go test -v -race ./...` (services/gateway, services/ws-hub, services/file-processor).
- **Static Analysis & SAST**: `ruff check`, `mypy`, `golangci-lint`, `bandit`, `semgrep-sast`, `detect-secrets`.

---

## Acceptance Thresholds
- **Harness Acceptance**: 31/31 (100%) tests passing in `verify_harness.py`.
- **Pre-Tool Safety Challenger**: 73/73 (100%) tests passing in `scripts/verify_challenger_pre_tool.py`.
- **Quality Gate Aggregator**: `check_orphans_and_anti_patterns.py` returns 0 violations.
- **PR #1249 Checks**: 14/14 checks report `conclusion: SUCCESS`.
