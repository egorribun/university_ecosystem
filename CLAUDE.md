# CLAUDE.md — University Ecosystem Platform

## Project Structure
- Python backend: `app/` (FastAPI + SQLAlchemy 2.0 + Pydantic v2) — **Python >=3.13,<3.15**
- TypeScript frontend: `frontend/src/` (React 19 + Vite + TanStack Query + Zustand + Framer Motion)
- Rust optimizer: `native/rust_ext/` (PyO3 FFI — schedule conflicts, partition management, HMAC)
- Go services: `services/` (ws-hub, file-processor, gateway, caddy)
- Alembic migrations: `alembic/versions/` (112 files; squash script: `app/management/squash_migrations.py`)
- Config: `app/core/config/` (15 classes, _NamespaceView composition Phase 2, 174+ fields)
- Feature flags: `app/core/feature_flags.py` (OpenFeature + flagd; K8s config: `k8s/flagd/`)
- Observability: OTEL tracing (Tempo), OTEL log bridge, Sentry, Prometheus, Pyroscope

## Commands
- `python -m ruff check app/` — lint backend (S104/S105 suppressed via per-file-ignores)
- `python -m ruff format app/` — format backend
- `cd frontend && npx tsc --noEmit` — typecheck frontend
- `python -m py_compile <file>` — quick syntax check
- Pre-commit runs: ruff, ruff-format, detect-secrets, bandit, mypy
- After detect-secrets hook: `git add .secrets.baseline` (always re-stage)

## Code Conventions
- Commit style: `feat(waveXX): description` with `Co-Authored-By` trailer
- Branch: `egorribun`
- Exception handling: narrowed to specific types with `# RZ-20-04` audit comments
  - DB/network: `(OSError, ConnectionError)`
  - File ops: `(FileNotFoundError, OSError)`
  - Redis: `(ConnectionError, TimeoutError, OSError)`
  - PyO3/Rust: `(RuntimeError, ImportError, OSError)`
  - Keep broad `except Exception` only for: re-raise-after-cleanup, convert-to-domain, handler-nak, fail-closed auth
- Models: ALL relationships must have explicit `lazy="noload"` — prevent N+1
- Settings: use `@cached_property` namespace accessors (settings.db, settings.security, etc.)
  - Phase 2 (Wave 21): accessors return `_NamespaceView` proxies, not `self`
- Frontend validation: **Valibot only** (Zod removed in Wave 21)
- Frontend debounce: `useDebounced` from `@/hooks/useDebounced` (300-350ms)
- Frontend memo: `React.memo()` on list/grid/dashboard components
- GraphQL: 5 defense layers — QueryDepthLimiter, MaxTokensLimiter, QueryCostExtension, RequestTimeoutExtension, PersistedQueryExtension (prod only)
- Feature flags: `from app.core.feature_flags import is_enabled` (async) or `is_enabled_sync`
- Password hashing: Argon2id only — **bcrypt verification removed** (TD-21-04, Wave 21)
- Valkey eviction: `volatile-lru` (changed from allkeys-lru in Wave 21 — RZ-21-02)

## Gotchas
- Glob `**/alembic/versions/*.py` may not find files on Windows; use `**/*alembic*/**/*.py`
- mypy: `type: ignore[return-value]` not needed when returning `self` from subclass
- ruff S105: false positive on field names containing "password" (enum values, API URLs) — use per-file-ignores, not inline noqa
- `.secrets.baseline` changes on every commit — always re-stage before retry
- Pre-commit hooks block on ANY ruff error including pre-existing — must suppress via pyproject.toml
- `docs/` files with example passwords need `# pragma: allowlist secret` for detect-secrets
- OpenFeature SDK is optional — feature_flags.py gracefully degrades when not installed
- ruff target-version is `py314`; mypy python_version is `3.14`
- Backend Dockerfile uses `python:3.14-slim-bookworm` (both builder and runtime stages)
- ws-hub auth cache: empty `room_id` in NATS `cache.invalidate` triggers wildcard eviction (RZ-21-03)
- ws-hub subscribes to `keys.rotated` NATS subject for JWKS pre-warming (RZ-21-05)

## Audit Trail
- Wave 19: 315 fixes across 174 files (feat(wave19) commit)
- Wave 20: 22 issues, 53 files, +1724/-206 — full report in `TOTAL_AUDIT_2026.md`
- Wave 21: 21 issues, 24 files, +1694/-528 — full report in `TOTAL_AUDIT_WAVE21.md`
- Remaining `except Exception` in services — each documented and justified
- Renovate Bot configured (`renovate.json`) for automated dependency updates
- SBOM generation (Syft/SPDX) added to CI pipeline
- Property-based tests (Hypothesis) in `tests/test_property_based.py`
