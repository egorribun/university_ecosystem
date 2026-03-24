# CLAUDE.md — University Ecosystem Platform

## Project Structure
- Python backend: `app/` (FastAPI + SQLAlchemy 2.0 + Pydantic v2)
- TypeScript frontend: `frontend/src/` (React + Vite + TanStack Query + Framer Motion)
- Rust optimizer: `rust_optimizer/` (PyO3 FFI)
- Go services: `services/` (ws-hub, etc.)
- Alembic migrations: `alembic/versions/` (111 files)
- Config: `app/core/config/` (15 classes, diamond inheritance, 174+ fields)

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
- Frontend debounce: `useDebounced` from `@/hooks/useDebounced` (300-350ms)
- Frontend memo: `React.memo()` on list/grid/dashboard components

## Gotchas
- Glob `**/alembic/versions/*.py` may not find files on Windows; use `**/*alembic*/**/*.py`
- mypy: `type: ignore[return-value]` not needed when returning `self` from subclass
- ruff S105: false positive on field names containing "password" (enum values, API URLs) — use per-file-ignores, not inline noqa
- `.secrets.baseline` changes on every commit — always re-stage before retry
- Pre-commit hooks block on ANY ruff error including pre-existing — must suppress via pyproject.toml

## Audit Trail
- Wave 19: 315 fixes across 174 files (feat(wave19) commit)
- Wave 20: 22 issues, 53 files, +1724/-206 — full report in `TOTAL_AUDIT_2026.md`
- Remaining 22 `except Exception` in services — each documented and justified
