# University Ecosystem Platform

A unified university platform that brings together the class schedule, news, events, campus maps, user profiles, notifications, and Spotify integration in a single modern experience for students, faculty, and staff.

## Prerequisites
Before running the project locally make sure you have the following tooling available:

- **Docker & Docker Compose** (optional but recommended for a one-command stack)
- **Python 3.12+** with `pip`
- **Node.js 20.19+** and `npm`
- **PostgreSQL 16** (only if you are not relying on Docker)

## Repository layout

```
.
├── docker-compose.yml         # Production-like stack for local development
├── docs/                      # Additional guides (deployment, localization, contributing)
├── root/
│   ├── app/                   # FastAPI backend application code (includes workers)
│   ├── frontend/              # Vite + React single-page frontend
│   ├── tests/                 # Backend tests (pytest)
│   ├── requirements*.txt      # Python dependencies for backend and workers
│   ├── .env.example           # Sample configuration for local development
│   └── create_invite_code.py  # Helper script for generating invite codes
└── SECURITY.md                # Security policy (linked below)
```

## Quick start

### 1. Configure environment variables
Copy the sample environment file and adjust it to your setup:

```bash
cp root/.env.example root/.env
```

> The most important variables are documented below; see `root/.env.example` for the full list.

### 2. Run the full stack with Docker (recommended)

```bash
docker compose up --build
```

This command builds the backend, frontend, and notifications worker images, starts PostgreSQL, and exposes the services at:

- Backend API: http://localhost:8000
- Frontend UI: http://localhost:8080
- Worker metrics: http://localhost:9101/metrics

### 3. Run services manually (alternative)

#### Backend (FastAPI)
```bash
cd root
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

#### Frontend (Vite + React)
```bash
cd root/frontend
npm install
npm run dev -- --host
```
The dev server exposes the UI at http://localhost:5173 and proxies API calls to the backend origin configured via `VITE_BACKEND_ORIGIN`.

#### Notifications worker
```bash
cd root
source .venv/bin/activate
python -m app.workers.notifications
```
The worker reads scheduled notification jobs from the database and exposes Prometheus metrics on `NOTIFICATIONS_WORKER_METRICS_PORT` (default 9101).

## Environment variables
Key settings you may want to adjust for local development:

| Variable | Description | Default |
| --- | --- | --- |
| `DATABASE_URL` | SQLAlchemy connection string used by the backend and worker. | `postgresql+asyncpg://postgres:1@127.0.0.1:5432/university` |
| `SECRET_KEY` | Secret used to sign JWT tokens. Generate a unique value before deploying. | example random string |
| `FRONTEND_ORIGIN` | Primary origin permitted by CORS and used in generated links. | `http://localhost:5173` |
| `FRONTEND_ORIGINS` | Comma-separated list of allowed CORS origins. | `http://localhost:5173,http://127.0.0.1:5173` |
| `APP_BASE_URL` | Base URL used inside emails and notifications. | `http://localhost:5173` |
| `SMTP_*` | Outgoing email server configuration. | Empty (email disabled) |
| `SPOTIFY_*` | OAuth credentials required for Spotify integration. | Empty |
| `SPOTIFY_TOKEN_SECRET` | Comma-separated Fernet keys used to encrypt Spotify access/refresh tokens (first key is used for new data). | Empty |
| `VAPID_*` | Keys used to send web push notifications. | Empty |
| `NOTIFICATIONS_WEBPUSH_CONCURRENCY_LIMIT` | Maximum number of simultaneous web push delivery jobs. | `10` |
| `NOTIFICATIONS_RETENTION_DAYS` | Number of days to keep read notifications before purging them. | `90` |
| `NOTIFICATIONS_RETENTION_CLEANUP_INTERVAL_SECONDS` | Interval between background retention cleanup runs. | `86400` |
| `CACHE_*` & `RATE_LIMIT_*` | Toggle and configure caching and rate limiting backends. | In-memory |
| `IMAGE_MAX_WIDTH` / `IMAGE_MAX_HEIGHT` | Bounding box applied to uploaded images before storage. | `1920` |
| `ENABLE_OTEL`, `SENTRY_DSN` | Observability & error tracking toggles. | Disabled |
| `VITE_SENTRY_DSN` | Frontend Sentry DSN used to initialize error tracking. | Empty |
| `VITE_ENVIRONMENT` | Optional environment label propagated to the frontend observability SDK. | Derived from Vite build mode |

Refer to [`root/app/core/config.py`](root/app/core/config.py) for the complete configuration model and validation logic. The `.env` file is loaded automatically when you start the backend or worker.

## Image uploads

Uploaded profile photos and news images are limited to **5&nbsp;MB**. The backend
automatically resizes images so they fit within the `IMAGE_MAX_WIDTH` ×
`IMAGE_MAX_HEIGHT` bounding box (default 1920×1920), strips EXIF metadata, and
stores them as optimized WebP files (PNG when transparency is required).

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
- Static analysis and formatting checks:
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
- Type-check and run unit tests:
  ```bash
  npm run typecheck
  npm run test
  ```
- End-to-end tests and Lighthouse budgets are available via:
  ```bash
  npm run test:e2e
  npm run lhci
  ```

#### Multi-tab authentication state

The frontend caches a lightweight profile snapshot in `localStorage` to speed up reloads. Changes to this cache trigger both the
native `storage` event and a `BroadcastChannel` message so that other open tabs synchronize immediately. Logging out or being
signed out in one tab clears the cached profile and authentication state everywhere.

## Architecture overview

```
+-------------------+       +---------------------------+
|  React Frontend   | <---> | FastAPI Backend (app/)    |
|  (Vite dev server)|       | REST + Web Push APIs      |
+-------------------+       | Notifications scheduler   |
            |               | Session cleanup job       |
            v               +-----------+---------------+
    Browser fetch/API                    |
                                         v
                                 +---------------+
                                 | PostgreSQL 16 |
                                 | Primary data  |
                                 +-------+-------+
                                         |
                                         v
                              +----------------------+
                              | Notifications worker |
                              | Background delivery  |
                              | Prometheus metrics   |
                              +----------------------+
```

- The frontend communicates with the backend via REST APIs, proxied through the Vite dev server in development.
- Scheduled notifications are stored in PostgreSQL; the inline scheduler (optional) or the dedicated worker consumes them.
- Observability integrations (OpenTelemetry, Sentry) are opt-in and controlled through environment variables.

## Additional documentation
- [Deployment guide](docs/DEPLOY.md) — infrastructure and CI/CD recommendations.
- [Localization workflow](docs/LOCALIZATION.md) — guidance for translating UI copy.

## Security and contributions
- Report security vulnerabilities responsibly via the process described in [SECURITY.md](SECURITY.md).
- Read the contribution guidelines in [docs/CONTRIBUTING.md](docs/CONTRIBUTING.md) before opening pull requests.

Happy hacking!
