# University Ecosystem Platform

A unified university platform that brings together the class schedule, news, stories, events, campus maps, user profiles, notifications, and Spotify integration in a single modern experience for students, faculty, and staff.

## Prerequisites
Before running the project locally make sure you have the following tooling available:

- **Docker & Docker Compose** (optional but recommended for a one-command stack)
- **Python 3.11+** with `pip`
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
│   ├── .env.example           # Reference configuration for local development
│   └── create_invite_code.py  # Helper script for generating invite codes
└── SECURITY.md                # Security policy (linked below)
```

## Documentation

- [Deployment guide (Russian)](docs/DEPLOY.md)
- [Deployment guide (English)](docs/DEPLOY.en.md)
- [Localization guidelines](docs/LOCALIZATION.md)
- [Contributing](docs/CONTRIBUTING.md)

## Quick start

### 1. Configure environment variables
Copy the sample environment file and adjust it to your setup:

```bash
cp root/.env.example root/.env
```

> The most important variables are documented below; see `root/.env.example` for the full list.
> The example file is provided for reference only—create a real `.env` (or set
> process environment variables) with unique secrets before starting the
> backend.

### 2. Run database migrations

Apply the latest Alembic migrations before starting the API:

```bash
cd root
# Reuse the same connection string you configure for DATABASE_URL
export DATABASE_URL=postgresql+asyncpg://user:password@host:5432/university
alembic upgrade head
```

Alembic reads the database URL from `root/alembic.ini`; when the bundled sample
URL does not match your target database, set the `DATABASE_URL` environment
variable before running the command. In Docker Compose, a one-off
`migrations` service now executes `alembic upgrade head` automatically before
the API and worker containers start. You can rerun migrations on demand with:

```bash
docker compose run --rm backend alembic upgrade head
```

### 3. Run the full stack with Docker (recommended)

```bash
docker compose up --build
```

This command builds the backend, frontend, and notifications worker images, starts PostgreSQL, and exposes the services at:

- Backend API: http://localhost:8000
- Backend metrics: http://localhost:8000/metrics (enable via `ENABLE_METRICS_ENDPOINT`)
- Frontend UI: http://localhost:8080
- Worker metrics: http://localhost:9101/metrics

#### Opt in to Redis-backed features

The Compose stack now includes a `redis` service that mirrors the cache and
rate-limiting infrastructure used in production. To enable Redis locally you
have two options:

1. **Rely on the Compose defaults.** The `backend` and `notifications-worker`
   containers already set `CACHE_ENABLED=true`,
   `CACHE_REDIS_URL=redis://redis:6379/0`, and configure rate limiting to use
   Redis (`RATE_LIMIT_STORAGE_BACKEND=redis`, `RATE_LIMIT_STORAGE_URI=redis://redis:6379/1`).
   When you run `docker compose up` these overrides take effect automatically.
2. **Apply the same settings when running services outside of Docker.** Copy
   the commented examples in [`root/.env.example`](root/.env.example) into your
   local `.env` file, then start the backend/worker after exporting the Redis
   environment variables.

With Redis enabled you can test cache hits, TTL expirations, and distributed
rate limiting behavior exactly as it will run in production.

#### Schedule API caching & conditional GETs

The schedule endpoint (`GET /schedule/{group_id}`) emits entity tags when the
cache backend is enabled. Each response sets `Cache-Control: private,
max-age=300` and an `Expires` header 5 minutes in the future so API consumers
can reuse data between polls. Send the previously observed `ETag` value via
`If-None-Match` to receive a `304 Not Modified` response with the same cache
headers whenever the schedule has not changed.

### 4. Run services manually (alternative)

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

> Frontend dependencies and build outputs are intentionally excluded from the repository. Run `npm install` to restore `node_modules` and `npm run build` (or `npm run dev`) to regenerate any `dev-dist` artifacts locally.

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
| `PASSWORD_RESET_CLEANUP_INTERVAL_SECONDS` | Interval between password reset token cleanup runs (`0` disables the scheduler). | `3600` |
| `PASSWORD_RESET_CLEANUP_RETENTION_MINUTES` | Minutes to keep used reset tokens before purging them (`0` deletes immediately). | `45` |
| `PASSWORD_RESET_MAX_ACTIVE_TOKENS` | Maximum number of active (unused) password reset tokens kept per user. | `1` |
| `CACHE_*` & `RATE_LIMIT_*` | Toggle and configure caching and rate limiting backends. | In-memory |
| `IMAGE_MAX_WIDTH` / `IMAGE_MAX_HEIGHT` | Bounding box applied to uploaded images before storage. | `1920` |
| `ENABLE_RESPONSE_COMPRESSION` | Enable gzip compression for larger API responses (≥512&nbsp;bytes). | `true` |
| `SERVICE_VERSION` / `APP_VERSION` | Release identifier propagated to OpenTelemetry (`service.version`) and Sentry (`release`). | Empty |
| `ENABLE_OTEL`, `SENTRY_DSN` | Observability & error tracking toggles. | Disabled |
| `ENABLE_METRICS_ENDPOINT` | Expose the Prometheus `/metrics` endpoint on the backend. | `false` |
| `METRICS_BASIC_AUTH_USERNAME` / `METRICS_BASIC_AUTH_PASSWORD` | Optional HTTP basic auth credentials protecting `/metrics`. | Empty |
| `METRICS_ALLOWLIST` | Comma-separated list of IPs, CIDR blocks, or hostnames allowed to access `/metrics`. | Empty |
| `ENABLE_CORP` | Enable the `Cross-Origin-Resource-Policy` response header for static assets/APIs. | `false` |
| `CORP_VALUE` | Value applied to the CORP header when enabled (`same-origin`, `same-site`, or `cross-origin`). | `same-site` |
| `VITE_SENTRY_DSN` | Frontend Sentry DSN used to initialize error tracking. | Empty |
| `VITE_ENVIRONMENT` | Optional environment label propagated to the frontend observability SDK. | Derived from Vite build mode |
| `VITE_ENABLE_WEB_VITALS` | Enable Web Vitals collection in the frontend (`true`/`1`/`yes`). | `false` |
| `VITE_WEB_VITALS_ENDPOINT` | Optional endpoint accepting POSTed Web Vitals metrics (JSON). Logs to the console when unset. | Empty |

Refer to [`root/app/core/config.py`](root/app/core/config.py) for the complete configuration model and validation logic. If you create `root/.env` it will be loaded automatically; otherwise the application relies entirely on process environment variables. The sample `root/.env.example` is not loaded automatically.

During CI/CD deployments export `SERVICE_VERSION` (or `APP_VERSION`) to match the build being released—for example `export SERVICE_VERSION=$(git describe --tags --always)` before starting the API and worker containers. The value is forwarded to OpenTelemetry (`service.version`) and Sentry (`release`) so traces and errors can be tied back to the exact build.

Password reset tokens are trimmed during startup and by a periodic background job. The API always keeps the most recent
`PASSWORD_RESET_MAX_ACTIVE_TOKENS` unused tokens for each user (default: one token) and reuses existing records when that limit is
reached. By default, used tokens are purged after `PASSWORD_RESET_CLEANUP_RETENTION_MINUTES` (matching the 45&nbsp;minute expiry
window) and the scheduler runs every `PASSWORD_RESET_CLEANUP_INTERVAL_SECONDS`. Set either value to `0` to disable automatic
cleanup, or increase the interval if you prefer less frequent maintenance.

> **Security note:** When exposing the metrics endpoint, set `METRICS_BASIC_AUTH_USERNAME` and
> `METRICS_BASIC_AUTH_PASSWORD` in your `.env` file (or Compose override) to unique, strong values.
> The backend refuses to serve `/metrics` when `METRICS_BASIC_AUTH_PASSWORD` uses a known placeholder
> to prevent deployments with weak credentials.

> **Authentication cookies:** The `Settings.cookie_secure` flag mirrors `ENABLE_STRICT_SECURITY_HEADERS`.
> In production (strict mode), login cookies include the `Secure` attribute and require HTTPS. During
> local development and automated tests, strict headers are disabled by default so the cookie omits
> `Secure`, allowing sign-in flows to work over `http://localhost`.

## Multi-factor authentication

The platform now standardizes on authenticator apps (TOTP) as the sole multi-factor authentication
option. Hardware security keys, WebAuthn ceremonies, and one-time recovery codes were removed from
both the backend and frontend, and the recovery-code database/table has been retired. Each user can
connect exactly one authenticator app, confirm it with six-digit codes, and when that authenticator
is revoked the account's MFA requirements are cleared automatically until a new TOTP enrollment is
added. Because recovery codes are no longer issued or accepted, administrators should ensure
everyone keeps their authenticator registered before enabling "MFA required" on an account.

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
- Static analysis and formatting checks (the pre-commit hook runs `ruff check --fix` with the default rule set so commits match CI expectations):
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
- Regenerate localized PWA manifests after editing
  `public/manifest.source.json`:
  ```bash
  npm run generate:manifests
  npm run manifests:check    # CI runs this to ensure the output is committed
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

## Stats API caching

The `/stats/*` endpoints cache responses per `(user_id, period)` key using Redis for **3 minutes** by default. The cache is
automatically invalidated when a student registers for or unregisters from an event, and when new grade notifications are issued.
Administrators can bypass the cache for a single request by appending `?skip_cache=true` to the stats URL; other roles always use
the cached payload when available.

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
- Client-side logging is centralized via `src/app/logger.ts`: call `logError`/`logWarning` instead of `console.*` to forward issues to Sentry with console fallbacks. Unhandled promise and Axios errors are captured globally by `initGlobalErrorHandlers()` during app bootstrap.

## Additional documentation
- [Deployment guide](docs/DEPLOY.md) — infrastructure and CI/CD recommendations.
- [Localization workflow](docs/LOCALIZATION.md) — guidance for translating UI copy.

## Security and contributions
- Report security vulnerabilities responsibly via the process described in [SECURITY.md](SECURITY.md).
- Read the contribution guidelines in [docs/CONTRIBUTING.md](docs/CONTRIBUTING.md) before opening pull requests.

Happy hacking!
