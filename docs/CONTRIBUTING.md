# Contributing Guide

Welcome to the **University Ecosystem Platform** contribution guide. Please follow these guidelines to ensure code quality, security, and repository consistency.

---

## 🎨 Git Commit & Branching Conventions

- **Branch Naming**: Use feature/topic branch names (e.g., `egorribun` or `feature/schedule-optimizations`).
- **Commit Style**: Use conventional commit format: `feat(scope): description` or `fix(scope): description`.
- **Commit Trailer Rules**:
  - **CRITICAL**: Do **NOT** include `Co-Authored-By: Antigravity <antigravity@google.com>` or any Antigravity trailers under any circumstances.
  - Do **NOT** associate testing coverage or testing roadmaps with waves in logs, comments, or commit messages (waves are strictly reserved for core business features).
- **Pre-commit Baseline**: After `detect-secrets` hook runs, always re-stage `.secrets.baseline` (`git add .secrets.baseline`) before retrying commit.

---

## ⚛️ Frontend Workflow (`frontend/`)

- **Dependencies**: Frontend dependencies are managed via `npm`. Run `npm install` from `frontend/` after checking out a branch.
- **Type Checking**: Run `npx tsc --noEmit` before opening a PR to verify TypeScript type safety.
- **Linting & Formatting**:
  - Run `npm run lint` (ESLint with zero-warning threshold).
  - Run `npm run format:check` (Prettier).
- **Unit & Component Testing**:
  - Run `npm run test` (Vitest suite covering pages, hooks, components, and i18n translation parity).
  - Translation tests in `src/tests/pageTranslations.test.tsx` verify localized copy across `en` and `ru`.
- **Validation**: Frontend schemas use **Valibot** (Zod has been completely removed).
- **Bundle Budget**: Frontend main JS chunk must stay under **500 KB** (enforced in CI via bundle analysis).

---

## 🐍 Backend Workflow (`app/`)

- **Runtime & Toolchain**: Python **3.14** managed via `uv`.
- **Dependency Sync**: Run `uv sync` to set up environment dependencies.
- **Linting & Formatting**:
  - `python -m ruff check app/`
  - `python -m ruff format app/`
  - `mypy app/` (Python 3.14 target).
- **Test Coverage**:
  - CI enforces the per-component thresholds from the
    [quality contract](../quality/quality-contract.json); do not duplicate or
    lower them in feature changes.
  - In the v2 coverage manifest, `source_roots` is the canonical report
    identity boundary while `coverage_scope` names the roots actually measured
    by each producer. Python coverage intentionally scopes to `app`; Alembic
    revisions remain reportable under `source_roots` and are verified by the
    PostgreSQL migration gate rather than treated as implicit coverage
    exclusions.
  - Run the canonical commands in the [testing guide](../TESTING.md) before
    opening a PR.
- **Exception Handling Conventions**:
  - Narrow exceptions to specific types with `# RZ-20-04` audit tags (e.g. `(OSError, ConnectionError)`).
  - Python 2 `except A, B:` syntax is strictly forbidden — always use `except (A, B):` tuple form.
  - Broad `except Exception:` catches must be tagged: `# RZ-22-01-JUSTIFIED: <reason>`.
- **ORM Models**: All SQLAlchemy relationships must have explicit `lazy="noload"` (enforced by MOD-30-01 gate).

---

## 🚀 Go Microservices Workflow (`services/`)

- **Services**: `gateway`, `ws-hub`, `file-processor`, `cmd/uni-cli`.
- **Linting**: `.golangci.yml` with `exhaustive` and `gosec` linters. Run `golangci-lint run ./...` inside service directories.
- **Unit & Integration Testing**:
  - `go test ./...` in each service directory.
  - `make test-integration` (runs ADR-022 Testcontainers-go integration suite covering NATS, Redis, and MinIO).

---

## 🦀 Rust Native Extension (`native/rust_ext`)

- **PyO3 & Rayon Engine**: Hot-path optimization for schedule conflict solver and HMAC calculations.
- **Building & Testing**:
  - `cd native/rust_ext`
  - `cargo test --no-default-features --lib`
  - `maturin develop` to compile local Python extension.

---

## 🛡️ Pre-push Security Checklist

Before pushing commits to remote:
1. Run pre-commit hooks: `pre-commit run --all-files`
2. Ensure `.secrets.baseline` is re-staged if modified.
3. Verify all automated CI status checks pass (`pytest`, `vitest`, `tsc`, `go test`, `cargo test`).
