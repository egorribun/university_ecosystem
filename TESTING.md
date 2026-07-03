# Testing Guide & Architecture

This document provides a comprehensive guide to the testing infrastructure, architectures, coverage thresholds, and local execution commands for the University Ecosystem project.

---

## 1. Test Architecture

The project contains a multi-language stack (Python, Go, Rust, TypeScript/React). Each stack has a dedicated test suite:

### 1.1 Python Backend (`pytest`)
- Located in `tests/`.
- Uses `pytest-asyncio` for asynchronous endpoint and database testing.
- Uses `coverage` to enforce statement and branch coverage floors.
- Validates FastAPI endpoints, PostgreSQL operations, Redis keyspace events, NATS task queue worker cycles, and security properties.

### 1.2 Go Services (`go test`)
- Located in `services/gateway`, `services/ws-hub`, and `services/file-processor`.
- Standard Go testing toolchain with mocks, and in-memory NATS broker simulations.
- Assures robust handler upgrades, JWKS validation, and configuration parsing.

### 1.3 Rust Crates (`cargo test`)
- Located in `crates/` and `native/`.
- Validates pure algorithmic helpers, schedule optimization bounds, FFI bindings (`pyo3`), and WebAssembly modules.

### 1.4 Frontend (`vitest` & `playwright`)
- Located in `frontend/`.
- **Unit/Component tests**: Run via Vitest. Employs fake timers and mocks for Web APIs (Tilt, weather data, push subscription events).
- **End-to-End (E2E) tests**: Run via Playwright to verify full user authentication and app flows.

---

## 2. Running Tests Locally

### 2.1 Python Backend
```bash
# Run all Python tests (except performance & schemathesis)
uv run pytest tests/ -v --tb=short -x --ignore=tests/performance --ignore=tests/test_schemathesis_api.py
```

### 2.2 Go Services
```bash
# Run tests for all Go services
go test ./services/... -v
```

### 2.3 Rust Crates
```bash
# Run tests for all Rust crates
cargo test --workspace
```

### 2.4 Frontend
```bash
# Run frontend unit/component tests
npm run test --prefix frontend

# Run E2E tests
npm run test:e2e --prefix frontend
```

---

## 3. Active Coverage Thresholds & Gates

Each module has enforced coverage requirements that must be met in local testing and CI:

| Module | Floor Requirement | Tool |
|---|---|---|
| **Python Backend** | $\ge 90\%$ statements | `coverage` |
| **Go Gateway** | $\ge 90\%$ statements | `go tool cover` |
| **Go WS-Hub** | $\ge 90\%$ statements | `go tool cover` |
| **Go File-Processor** | $\ge 90\%$ statements | `go tool cover` |
| **Rust Crates** | $\ge 95\%$ statements | `cargo-llvm-cov` |
| **Frontend** | $\ge 92\%$ statements, $\ge 81\%$ branches | `vitest` |

---

## 4. Wave Roadmap Tracker
- [x] **Wave 1**: Python Backend Unit Coverage (Auth & MFA) — **COMPLETED**
- [x] **Wave 2**: Go Services Coverage Upgrade ($\ge 90\%$) — **COMPLETED**
- [x] **Wave 3**: Rust Core Coverage Upgrade ($\ge 95\%$) — **COMPLETED**
- [x] **Wave 4**: Frontend Unit & E2E Coverage Upgrade — **COMPLETED**
- [x] **Wave 5**: Integration, Contract & Security Coverage Expansion — **COMPLETED**
- [x] **Wave 6**: Observability, Documentation, Final CI Gate — **COMPLETED**

---

## 5. Adding New Tests

1. **Python**: Place tests under `tests/` with the `test_` prefix. Ensure async tests are decorated with `@pytest.mark.asyncio`.
2. **Go**: Create a `*_test.go` file next to the source code being tested.
3. **Rust**: Write unit tests in a `tests` module inside `src/lib.rs` decorated with `#[cfg(test)]`.
4. **Frontend**: Add `.test.tsx` or `.test.ts` files under `__tests__` directories in components or hooks.
