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

| Module | Floor Requirement | Tool | Last Updated |
|---|---|---|---|
| **Python Backend** | $\ge 93\%$ statements, $\ge 91\%$ branches | `coverage` | Wave 7 |
| **Go Gateway** | $\ge 90\%$ statements | `go tool cover` | Wave 8 |
| **Go WS-Hub** | $\ge 90\%$ statements | `go tool cover` | Wave 8 |
| **Go File-Processor** | $\ge 90\%$ statements | `go tool cover` | Wave 8 |
| **Rust Crates** | $\ge 95\%$ statements | `cargo-llvm-cov` | Wave 9 |
| **Frontend** | $\ge 92\%$ statements, $\ge 83\%$ branches | `vitest` | Wave 10 |

---

## 4. Wave Roadmap Tracker
- [x] **Wave 1**: Python Backend Unit Coverage (Auth & MFA) — **COMPLETED**
- [x] **Wave 2**: Go Services Coverage Upgrade ($\ge 90\%$) — **COMPLETED**
- [x] **Wave 3**: Rust Core Coverage Upgrade ($\ge 95\%$) — **COMPLETED**
- [x] **Wave 4**: Frontend Unit & E2E Coverage Upgrade — **COMPLETED**
- [x] **Wave 5**: Integration, Contract & Security Coverage Expansion — **COMPLETED**
- [x] **Wave 6**: Observability, Documentation, Final CI Gate — **COMPLETED**
- [x] **Wave 7**: Python Branch Coverage Ratchet (`fail_under` 91→93, mutation gate scripts) — **COMPLETED**
- [x] **Wave 8**: Go Coverage Gate Enforcement (Makefile `go-test-gates` target) — **COMPLETED**
- [x] **Wave 9**: Rust proptest + criterion benchmarks + fuzz targets — **COMPLETED**
- [x] **Wave 10**: Frontend branches threshold raise (81→83) + new test files — **COMPLETED**
- [x] **Wave 11**: E2E spec expansion (5 new spec files) — **COMPLETED**
- [x] **Wave 12**: Integration test expansion (postgres + nats layers) — **COMPLETED**
- [x] **Wave 13**: Contract test expansion (OpenAPI drift + NATS subjects) — **COMPLETED**
- [x] **Wave 14**: Chaos + Fuzz corpus tests — **COMPLETED**

---

## 5. Adding New Tests

1. **Python**: Place tests under `tests/` with the `test_` prefix. Async tests do **not** need `@pytest.mark.asyncio` — `asyncio_mode = 'auto'` is set in `pyproject.toml`.
2. **Go**: Create a `*_test.go` file next to the source code being tested.
3. **Rust**: Write unit tests in a `tests` module inside `src/lib.rs` decorated with `#[cfg(test)]`.
4. **Frontend**: Add `.test.tsx` or `.test.ts` files under `__tests__` directories in components or hooks.
5. **Integration tests**: Use `pytest.mark.integration` and gate with `RUN_INTEGRATION_TESTS=1` if they require Docker/PostgreSQL.
6. **Chaos tests**: Use `pytest.mark.chaos` and `pytest.mark.slow`; no Docker required for in-process chaos tests.
7. **Fuzz corpus**: Add new inputs to `tests/fuzz/test_fuzz_corpus.py` after a fuzzing session discovers a crash-triggering input.
