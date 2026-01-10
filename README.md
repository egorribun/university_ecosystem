# University Ecosystem Platform

Unified platform for university life that delivers schedules, news, stories, events, campus map links, user profiles, push notifications, and Spotify integration. The stack pairs a FastAPI backend with a Vite/React frontend (enhanced with **Framer Motion** for animations), backed by PostgreSQL and optional Redis for caching and rate limiting.

## Prerequisites

- **Python 3.11+** with `pip`
- **Node.js 20.19+** with `npm`
- **Docker & Docker Compose** (recommended for local development)
- **PostgreSQL 16** (or SQLite for lightweight dev via `AUTO_CREATE_SCHEMA`)
- Optional system packages: `libmagic` for file-type detection and a running `clamd` service when malware scanning is enabled

## Repository layout

```
.
├── docker-compose.yml         # Backend + frontend + PostgreSQL + Redis + worker
├── docker-compose.prod.yml    # Production overlay
├── Makefile / justfile        # Common dev tasks (lint, test, serve, etc.)
├── start-dev.ps1              # Windows PowerShell quick-start script
├── docs/                      # Deployment, localization, and contributing guides
│   └── observability/         # Grafana dashboard & Prometheus alerts JSON
├── scripts/
│   ├── loadtesting/           # k6 / Locust scenarios
│   ├── audit_dependencies.py  # Dependency vulnerability checker
│   └── enforce_secret_strength.py  # Secret strength validation
├── security/                  # Security policies and checklists
├── root/
│   ├── app/                   # FastAPI application, services, and workers
│   ├── frontend/              # Vite + React single-page app
│   ├── tests/                 # Backend test suite (pytest)
│   ├── alembic/               # Database migrations
│   ├── requirements*.txt      # Python dependencies
│   ├── .env.example           # Reference environment configuration
│   ├── create_invite_code.py  # Utility for generating invite codes
│   └── create_test_user.py    # Utility for creating test user accounts
├── .github/workflows/         # CI/CD pipelines (ci.yml, codeql.yml, container-security.yml, gitleaks.yml)
└── SECURITY.md                # Security policy
```

## Documentation

- [Deployment guide (Russian)](docs/DEPLOY.md)
- [Deployment guide (English)](docs/DEPLOY.en.md)
- [Localization guidelines](docs/LOCALIZATION.md)
- [API versioning](docs/api_versioning.md)
- [Manual MFA checklist](docs/manual-mfa-checklist.md)
- [Observability (Grafana, Prometheus)](docs/observability/)
- [Contributing](docs/CONTRIBUTING.md)

## Getting started

### 1. Configure environment variables

Copy the template and replace placeholder secrets before running services:

```bash
cp root/.env.example root/.env
```

Important backend values include `DATABASE_URL`, `SECRET_KEY`, `FRONTEND_ORIGIN(S)`, and the VAPID/Spotify credentials. Redis-related toggles (`CACHE_ENABLED`, `CACHE_REDIS_URL`, `RATE_LIMIT_STORAGE_BACKEND`, `RATE_LIMIT_STORAGE_URI`) default to in-memory behavior unless you enable Redis. For quick SQLite development you may set `AUTO_CREATE_SCHEMA=1`, but production deployments should run Alembic migrations instead.

For environments backed by external object storage, the `/healthz` storage probe now includes two tuning knobs: set `HEALTH_STORAGE_PROBE_ENABLED=true` to run the full write/delete check, and adjust `HEALTH_STORAGE_PROBE_MIN_INTERVAL_SECONDS` to reuse a cached result between calls. When the heavy probe is disabled, the healthcheck falls back to lightweight bucket/list checks when available.

Docker Compose reads the `POSTGRES_USER`, `POSTGRES_PASSWORD`, and `POSTGRES_DB` values from `root/.env`. The defaults are set to non-default development credentials (`university` / `local_dev_pg_password_ChangeMe_123456`) but **must be changed for any shared or remote host** along with the generated `DATABASE_URL` connection string.

Frontend builds read `VITE_*` variables at build time (for example `VITE_BACKEND_ORIGIN`, `VITE_MAP_CONSTRUCTOR_ID`, `VITE_APP_RELEASE`, `VITE_SENTRY_DSN`).

### 2. Run database migrations

Apply the latest Alembic migrations before starting the API:

```bash
cd root
export DATABASE_URL=postgresql+asyncpg://user:password@host:5432/university
alembic upgrade head
```

Alembic reads the connection string from `root/alembic.ini`. Docker Compose includes a one-off `migrations` service that executes `alembic upgrade head` automatically before the API and worker start, and you can rerun it manually with:

```bash
docker compose run --rm backend alembic upgrade head
```

### 3. Run the full stack with Docker (recommended)

```bash
docker compose up --build
```

The stack builds the backend, frontend, and notifications worker images, starts PostgreSQL and Redis, and exposes services at:

- Backend API: http://localhost:8000
- Backend metrics: http://localhost:8000/metrics (enable via `ENABLE_METRICS_ENDPOINT` and credentials)
- Frontend UI: http://localhost:8080
- Worker metrics: http://localhost:9101/metrics

PostgreSQL (`127.0.0.1:5432`) and Redis (`127.0.0.1:6379`) bindings are scoped to localhost to avoid accidental exposure on public hosts. Adjust the bindings only when you explicitly need external access.

Redis-backed cache and rate limiting are enabled by default in Compose via `CACHE_ENABLED=true`, `CACHE_REDIS_URL=redis://redis:6379/0`, `RATE_LIMIT_STORAGE_BACKEND=redis`, and `RATE_LIMIT_STORAGE_URI=redis://redis:6379/1`.

### 4. Windows PowerShell quick-start

For Windows developers, the `start-dev.ps1` script automates local setup:

```powershell
.\start-dev.ps1
```

This creates a Python virtual environment in `root/.venv`, installs dependencies, generates a minimal `.env`, and launches both the FastAPI backend (using SQLite) and Vite dev server in separate terminals. The frontend opens automatically at http://localhost:5173.

### 5. Run services manually (alternative)

#### Backend (FastAPI)

```bash
cd root
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
# optional: pip install -r requirements-dev.txt
export DATABASE_URL=postgresql+asyncpg://user:password@host:5432/university
uvicorn app.main:app --reload
```

SQLite development is supported by pointing `DATABASE_URL` to `sqlite+aiosqlite:///./dev.db` and enabling `AUTO_CREATE_SCHEMA=1`. Production-style setups should run Alembic migrations and keep `AUTO_CREATE_SCHEMA` disabled. When malware scanning is required, run a `clamd` daemon and set `EVENT_FILE_SCANNER_ENABLED=true` with the host/port or Unix socket values from `root/.env.example`.

#### Frontend (Vite + React)

```bash
cd root/frontend
npm install
VITE_BACKEND_ORIGIN=http://localhost:8000 npm run dev
```

### Background worker

Run the dedicated notifications worker when you need scheduled or queued push delivery:

```bash
cd root
python -m venv .venv
source .venv/bin/activate
python -m app.workers.notifications
```

Set `NOTIFICATIONS_SCHEDULER_INLINE_ENABLED=false` when the API and worker run separately so the scheduler is only active in the worker process. Worker metrics are published on the configured host/port (default `9101`).

## Platform capabilities

- REST APIs for chat, events, news, schedules, sessions, Spotify, stats, stories, users, and push notifications
- WebSocket chat updates at `/ws/chat` with cookie auth or `Sec-WebSocket-Protocol`/`Authorization` tokens (query-param tokens only when `websocket_query_param_compat` is enabled)
- Push notifications with VAPID keys and a dedicated delivery worker; dead-letter queues and retention cleanup are built in
- Optional Redis cache and rate limiting middleware; `/stats/*` responses and schedule payloads use Redis-backed caching when enabled
- Configurable CORS, security headers (including COOP/COEP/CORP toggles), gzip compression, and proxy header support
- Observability hooks for OpenTelemetry and Sentry; Prometheus metrics available via `/metrics` when enabled
- Multi-factor authentication via TOTP only (one authenticator app per user); recovery codes and hardware keys are not used
- File safety: optional ClamAV scanning for uploaded event attachments, strict MIME detection, and a 5 MB limit for profile/news images with automatic resizing and WebP optimization
- Session, notification, story, password-reset, MFA-challenge, email-change, and dead-letter cleanup jobs run on startup with periodic schedulers controlled by environment variables

## Frontend specifics

- Vite dev server proxies API calls to the configured backend origin
- Localization assets are generated from `public/manifest.source.json` via `npm run generate:manifests`
- Client-side logging is centralized in `src/app/logger.ts`; global handlers capture unhandled Promise and Axios errors
- Authenticated state synchronizes across tabs through `localStorage` updates and `BroadcastChannel` messages
- **World-Class Polish**:
  - **Fluid Navigation**: "Active Pill" animations on mobile bottom navigation.
  - **Premium Interactions**: "Spotlight" hover effects on cards and tactile spring animations on interaction.
  - **Optimized Loading**: Responsive skeletons (`ScheduleSkeleton`) replace generic spinners for a smoother perceived performance.
  - **PWA Ready**: Offline support with service worker caching for news and schedule data.

## Image uploads

Uploaded profile photos and news images are limited to **5 MB**. The backend automatically resizes images within the `IMAGE_MAX_WIDTH` × `IMAGE_MAX_HEIGHT` bounds (default 1920×1920), strips EXIF metadata, and stores them as WebP (PNG when transparency is required).

## Running tests and linters

### Common make/just shortcuts

Repeatable local tasks mirror the CI steps and are exposed through the repository `Makefile` (or `justfile` if you prefer `just`):

- `make install` / `just install` — install pinned backend and frontend dependencies.
- `make lint` — run pre-commit hooks plus the frontend ESLint/manifest/Prettier checks used in CI.
- `make backend-test` / `make frontend-test` — execute the full backend pytest suite and the frontend typecheck + vitest pipeline.
- `make backend-typecheck` — run mypy with the same configuration as CI.
- `make frontend-build` — build the production bundle.
- `make backend-serve` / `make frontend-dev` — start the FastAPI dev server and Vite dev server on the same ports used in the devcontainer tasks.
- `make alembic-check` — run an upgrade/downgrade cycle against a temporary SQLite database to mirror the migration gate.
- `make generate-api` — regenerate the OpenAPI JSON and TypeScript client used by the frontend.

### Reproducible environments

- Python dependencies are pinned with `pip-compile`. Source files live in `root/requirements.in` and `root/requirements-dev.in`, and the compiled locks consumed by CI are `root/requirements.txt` and `root/requirements-dev.txt`. Regenerate pins with:
  ```bash
  pip-compile root/requirements.in -o root/requirements.txt
  pip-compile root/requirements-dev.in -o root/requirements-dev.txt
  ```
- Node dependencies are locked via `root/frontend/package-lock.json`. Use `npm ci` (as the CI does) to install, and pass `--frozen-lockfile` if you run Yarn/PNPM locally to guarantee the lockfile is respected.
- Dev containers and VS Code tasks are wired to the same make targets so local runs stay in sync with the workflow commands.

### Backend
- Install backend development dependencies:
  ```bash
  cd root
  pip install -r requirements.txt -r requirements-dev.txt
  ```
- Run the unit test suite:
  ```bash
  cd root
  pytest
  ```
- Static analysis and formatting checks (mirrors CI):
  ```bash
  cd root
  ruff check app tests
  ruff format --check app tests
  ```

### Frontend
- Lint the TypeScript/React codebase:
  ```bash
  cd root/frontend
  npm run lint
  ```
- Regenerate localized PWA manifests after editing `public/manifest.source.json`:
  ```bash
  npm run generate:manifests
  npm run manifests:check
  ```
- Type-check and run unit tests:
  ```bash
  npm run typecheck
  npm run test
  ```
- End-to-end tests and Lighthouse budgets:
  ```bash
  npm run test:e2e
  npm run lhci
  ```

## Performance profiling & caching

- Switch cache implementations by setting `CACHE_BACKEND` to `redis`, `memory`,
  or `none`; adjust warmup targets with `CACHE_WARMUP_GROUPS`,
  `CACHE_WARMUP_STATS_USERS`, and `CACHE_WARMUP_PERIODS` (comma-separated IDs).
- Enable startup cache warming via `CACHE_WARMUP_ENABLED=true` to prefetch
  schedule/stat payloads and avoid cold responses in deployments.
- k6 and Locust scenarios for `/schedule`, `/news`, `/events`, and `/chat`
  live in `scripts/loadtesting/`.

## Security and contributions

- Report vulnerabilities responsibly via [SECURITY.md](SECURITY.md)
- Follow the guidelines in [docs/CONTRIBUTING.md](docs/CONTRIBUTING.md) before opening pull requests

Happy hacking!
