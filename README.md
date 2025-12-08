# University Ecosystem Platform

Unified platform for university life that delivers schedules, news, stories, events, campus map links, user profiles, push notifications, and Spotify integration. The stack pairs a FastAPI backend with a Vite/React frontend, backed by PostgreSQL and optional Redis for caching and rate limiting.

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
├── docs/                      # Deployment, localization, and contributing guides
├── root/
│   ├── app/                   # FastAPI application, services, and workers
│   ├── frontend/              # Vite + React single-page app
│   ├── tests/                 # Backend test suite (pytest)
│   ├── requirements*.txt      # Python dependencies
│   ├── .env.example           # Reference environment configuration
│   ├── alembic/               # Database migrations
│   └── create_invite_code.py  # Utility for generating invite codes
└── SECURITY.md                # Security policy
```

## Documentation

- [Deployment guide (Russian)](docs/DEPLOY.md)
- [Deployment guide (English)](docs/DEPLOY.en.md)
- [Localization guidelines](docs/LOCALIZATION.md)
- [Manual MFA checklist](docs/manual-mfa-checklist.md)
- [Contributing](docs/CONTRIBUTING.md)

## Getting started

### 1. Configure environment variables

Copy the template and replace placeholder secrets before running services:

```bash
cp root/.env.example root/.env
```

Important backend values include `DATABASE_URL`, `SECRET_KEY`, `FRONTEND_ORIGIN(S)`, and the VAPID/Spotify credentials. Redis-related toggles (`CACHE_ENABLED`, `CACHE_REDIS_URL`, `RATE_LIMIT_STORAGE_BACKEND`, `RATE_LIMIT_STORAGE_URI`) default to in-memory behavior unless you enable Redis. For quick SQLite development you may set `AUTO_CREATE_SCHEMA=1`, but production deployments should run Alembic migrations instead.

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

Redis-backed cache and rate limiting are enabled by default in Compose via `CACHE_ENABLED=true`, `CACHE_REDIS_URL=redis://redis:6379/0`, `RATE_LIMIT_STORAGE_BACKEND=redis`, and `RATE_LIMIT_STORAGE_URI=redis://redis:6379/1`.

### 4. Run services manually (alternative)

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
- Authentication state synchronizes across tabs through `localStorage` updates and `BroadcastChannel` messages

## Image uploads

Uploaded profile photos and news images are limited to **5 MB**. The backend automatically resizes images within the `IMAGE_MAX_WIDTH` × `IMAGE_MAX_HEIGHT` bounds (default 1920×1920), strips EXIF metadata, and stores them as WebP (PNG when transparency is required).

## Running tests and linters

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

## Security and contributions

- Report vulnerabilities responsibly via [SECURITY.md](SECURITY.md)
- Follow the guidelines in [docs/CONTRIBUTING.md](docs/CONTRIBUTING.md) before opening pull requests

Happy hacking!
