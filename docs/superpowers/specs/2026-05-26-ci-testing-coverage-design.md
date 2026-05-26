# Design Doc: CI Testing & Code Coverage Enhancements

- **Date**: 2026-05-26
- **Status**: Proposed
- **Author**: Antigravity AI

---

## 1. Goal & Context

The goal is to establish robust, comprehensive, and high-fidelity testing gates in the CI pipeline across all three main stacks (Python FastAPI backend, Go microservices, and React frontend) and raise quality thresholds. 

Current issues:
- **Python backend** is at ~79% coverage. The gates in CI/local are 78%/79% respectively.
- **Go microservices** (`gateway`, `ws-hub`, `file-processor`) report extremely low coverage (1.4% to 31%) because several key test files are hidden behind the `//go:build integration` build tag even though they require no external infrastructure. The CI coverage threshold is set to a placeholder of `1%`.
- **React frontend** Vitest coverage is misconfigured, counting all build output files (bundles in `dist/`, Storybook artifacts, third-party packages) and reporting a skewed `19.16%` coverage, which fails the `60%` quality gate.

---

## 2. Proposed Changes

### 2.1. Frontend Vitest Coverage Fix
We will refine [vitest.config.ts](file:///c:/Users/egorribun/Documents/university_ecosystem/frontend/vitest.config.ts) to restrict the scope of coverage analysis to code inside `src/` while omitting generated code, tests, and mock directories.

**Configuration Updates**:
- `include`: `["src/**/*"]`
- `exclude`: 
  - `src/tests/**/*`
  - `src/**/__tests__/**/*`
  - `src/**/*.test.{ts,tsx}`
  - `src/setupTests.ts`
  - `src/routeTree.gen.ts` (TanStack Router auto-generated routes)
  - `src/api/generated/**/*` (openapi-ts auto-generated client)
  - `**/*.d.ts`
- **Thresholds**: Raised to `statements: 70`, `branches: 65`, `functions: 70`, `lines: 70`.

### 2.2. Go Microservices Testing Setup & File Reclassification
To solve the version mismatch local compile error, local verification scripts will prepend the downloaded 1.26.2 toolchain path to `Path`.
We will also reclassify several test files that do not require external containers from "integration" to "unit" tests, bringing them into the standard `go test` coverage run.

**Reclassified Files**:
- **[server_integration_test.go](file:///c:/Users/egorribun/Documents/university_ecosystem/services/file-processor/internal/service/server_integration_test.go)** → Rename to `server_test.go` and remove `//go:build integration` (covers `validateProcessFileRequest`).
- **[graphql_depth_integration_test.go](file:///c:/Users/egorribun/Documents/university_ecosystem/services/file-processor/internal/middleware/graphql_depth_integration_test.go)** → Rename to `graphql_depth_test.go` and remove `//go:build integration` (covers GraphQL query depth middleware).

**New Unit Tests**:
- `services/ws-hub/pkg/config/config_test.go` (tests env var parsing and slices).
- `services/ws-hub/internal/telemetry/telemetry_test.go` (tests Sentry/OTel tracer provider initialization).
- `services/gateway/internal/handlers/handlers_test.go` (add assertions covering the mapped gRPC code outputs).

**CI Threshold**:
- Parameterize `reusable-go-tests.yml` to accept `coverage-threshold` (default `50`).
- Update `ci.yml` to call `go-tests` with `coverage-threshold: 50`.

### 2.3. Python Backend Coverage Booster
We will add `tests/test_backend_coverage_booster.py` to cover untested edge cases in core utility files and repositories.

**Coverage Targets**:
- `app/services/group_service.py` (missing validation and exception flows).
- `app/utils/uuid_v7.py` (timestamp boundaries and string transformations).
- `app/utils/migrations.py` (runtime validation helpers).
- `app/utils/pagination.py` (negative page sizes, limits, and offset boundaries).

**CI/Local Threshold**:
- Update `fail_under` in `pyproject.toml` to `80`.
- Update `coverage-threshold` in `ci.yml` backend tests step to `80`.

### 2.4. CI Workflow Artifacts & Reporting
- Add `--coverage` to `npm run test:ci` in `frontend/package.json`.
- Add an artifact upload step in `reusable-frontend-tests.yml` to save `frontend/coverage/` reports.

---

## 3. Verification Plan

### 3.1. Automated Verification
- **Python**: Run `uv run pytest --cov=app --cov-report=term-missing` locally and ensure coverage is >= 80%.
- **Go**: Run `$env:Path = 'C:\Users\egorribun\go\pkg\mod\golang.org\toolchain@v0.0.1-go1.26.2.windows-amd64\bin;' + $env:Path; cd services/gateway ; go test -cover ./...` (and repeat for other services) and ensure coverage is >= 50%.
- **Frontend**: Run `npm run test:ci --prefix frontend` and check if coverage threshold passes >= 70%.

### 3.2. CI Verification
- Push changes to a test branch and ensure all CI runs (diagnostic, pre-commit, backend-tests, go-tests, frontend-tests) compile and pass successfully.
- Verify that coverage HTML/XML zip artifacts are correctly uploaded to the GitHub Actions run summary.
