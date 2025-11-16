# Frontend and media deployment

_[Russian version](DEPLOY.md) · [English version](DEPLOY.en.md)_

## Environment variables

- Before building the frontend, set `VITE_BACKEND_ORIGIN` (for example via `frontend/.env.production`).
- To render the interactive map, set `VITE_MAP_CONSTRUCTOR_ID` — the Yandex Maps constructor ID for the campus.
- The `root/.env.example` file is only a template; set your own secrets via `.env` or environment variables in production.
- All variables prefixed with `VITE_` are inlined into the code during `npm run build`; changing them after the build has no effect.
- During CI/CD export `SERVICE_VERSION` (or `APP_VERSION`) before launching containers to propagate the build identifier to OpenTelemetry (`service.version`). The frontend build automatically reuses these variables — alongside common CI commit identifiers such as `SOURCE_VERSION`, `VERCEL_GIT_COMMIT`, or `GITHUB_SHA` — when `VITE_APP_RELEASE` is not explicitly provided.
- Set `VITE_APP_RELEASE` to forward the release identifier to Sentry. Values are embedded at build time.
- To enable client-side error monitoring, set `VITE_SENTRY_DSN` and, if needed, `VITE_ENVIRONMENT`. The SDK does not activate automatically in dev builds.
- The frontend logger (`src/app/logger.ts`) automatically sends `logError`/`logWarning` to Sentry and mirrors the output in the console. Unhandled `Promise`/`axios` errors are captured by global handlers (`initGlobalErrorHandlers()` is invoked in `src/main.tsx`).
- To collect Web Vitals, set `VITE_ENABLE_WEB_VITALS=true`. Optionally send metrics to your own endpoint through `VITE_WEB_VITALS_ENDPOINT` (otherwise they are printed to the console). The flag is ignored in dev/test environments, so CI will not fail even when the variable is enabled.
- Backend and frontend must run over HTTPS, otherwise the browser blocks `/media` and `/static`.
- To limit requests, configure the backend with `RATE_LIMIT_STORAGE_BACKEND` and `RATE_LIMIT_STORAGE_URI`. The value `redis` + a Redis URL (for example, `redis://user:pass@host:6379/0`) enables a shared storage for the middleware and sensitive endpoints. Use `memory` or `memory://` for a simple single-process mode without external Redis.
- To expose Prometheus metrics, set `ENABLE_METRICS_ENDPOINT=true` and configure durable values for `METRICS_BASIC_AUTH_USERNAME` and `METRICS_BASIC_AUTH_PASSWORD` (docker-compose no longer injects placeholders). The backend refuses to serve `/metrics` if the password equals a known placeholder such as `changeme`.
- To attach the `Cross-Origin-Resource-Policy` header, set `ENABLE_CORP=true`. Customize the value via `CORP_VALUE` (defaults to `same-site`; `same-origin` and `cross-origin` are also accepted).

## Database migrations

- Before launching a new release, run `alembic upgrade head`:

  ```bash
  cd root
  export DATABASE_URL=postgresql+asyncpg://user:password@host:5432/university
  alembic upgrade head
  ```

- Alembic reads the connection string from `root/alembic.ini`. If that sample URL
  does not match your target database, provide the correct value through the
  `DATABASE_URL` environment variable (reuse the same URL as the application).
- Docker Compose now includes a one-off `migrations` service that runs
  `alembic upgrade head` before the API and worker containers start. You can rerun
  migrations manually when needed:

  ```bash
  docker compose run --rm backend alembic upgrade head
  ```

### Database connection pool

- In production environments use the SQLAlchemy pool: set `DATABASE_POOL_SIZE` (base pool size), `DATABASE_MAX_OVERFLOW` (additional connections above the pool), `DATABASE_POOL_TIMEOUT` (seconds to wait for a free connection), and `DATABASE_POOL_RECYCLE` (seconds before a forced connection close). Default values are `5`, `10`, `30`, and `1800` respectively.
- For dev/test environments the application automatically switches to `NullPool` so each connection opens anew; pool parameters are ignored. This avoids SQLite locks and helps with local development.
- Before deploying to PostgreSQL or another production database, choose values within the database limits. For example, on a server limited to 20 connections you could set `DATABASE_POOL_SIZE=5` and `DATABASE_MAX_OVERFLOW=5`, leaving room for background jobs and external tools.

### SQLite specifics

- Event search relies on PostgreSQL's `tsvector` type with a GIN index. When the
  app runs on SQLite (local development, unit tests) Alembic creates a plain text
  `events.search_vector` column and `crud.get_all_events` automatically falls back
  to `LIKE` filtering. No additional configuration is required, but SQLite search
  results are not ranked by relevance.

### Background task metrics

- `/metrics` now publishes counters and histograms for background cleanup jobs:
  - `periodic_task_notifications_retention_*` — removal of old notifications and deliveries.
  - `periodic_task_password_reset_cleanup_*` — cleanup of password reset tokens.
  - `periodic_task_session_cleanup_*` — removal of expired user sessions.
  - `periodic_task_story_cleanup_*` — cleanup of expired stories.
  - `periodic_task_mfa_challenge_cleanup_*` — deletion of expired or consumed MFA challenges.
- Each job exposes:
  - `*_runs_total` — number of successful iterations.
  - `*_errors_total` — number of runs ending with an exception.
  - `*_deleted_total` — total number of deleted records across all time.
  - `*_duration_seconds{_bucket,_sum,_count}` — execution time histogram.

```bash
# example
cd frontend
cp .env.production .env.local      # if needed
VITE_APP_RELEASE=$(git rev-parse --short HEAD) \
  VITE_BACKEND_ORIGIN=https://api.example.com npm run build
```

- Localized PWA manifests are generated from `public/manifest.source.json`.
  Run `npm run generate:manifests` before building or `npm run manifests:check`
  to ensure the files in `public/` are up to date.

### Spotify tokens

- The backend encrypts Spotify access/refresh tokens with Fernet. Before enabling the integration, set `SPOTIFY_TOKEN_SECRET` — a base64 string generated by `Fernet.generate_key()`.

```bash
python - <<'PY'
from cryptography.fernet import Fernet
print(Fernet.generate_key().decode())
PY
```

- To rotate keys, list several comma-separated values: set the new key first and keep the old one second (`SPOTIFY_TOKEN_SECRET="new_key,old_key"`). After deploying, run the script below to re-encrypt stored values and drop the dependency on the old key, then remove it from the variable and restart services.

```bash
python - <<'PY'
import asyncio
from sqlalchemy import text

from app.core.database import async_session
from app.utils.encryption import rotate_encrypted_string


async def main() -> None:
    async with async_session() as session:
        rows = await session.execute(
            text(
                "SELECT id, spotify_access_token, spotify_refresh_token FROM users"
            )
        )
        for row in rows.all():
            await session.execute(
                text(
                    "UPDATE users SET spotify_access_token = :access, "
                    "spotify_refresh_token = :refresh WHERE id = :user_id"
                ),
                {
                    "user_id": row.id,
                    "access": rotate_encrypted_string(row.spotify_access_token),
                    "refresh": rotate_encrypted_string(row.spotify_refresh_token),
                },
            )
        await session.commit()


asyncio.run(main())
PY
```

## Docker image

- `root/frontend.Dockerfile` is built in two stages: the `builder` stage runs `npm ci && npm run build`, and the final image is based on `nginx:alpine` and contains only the `dist/` contents.
- `VITE_BACKEND_ORIGIN` is passed via `--build-arg` (see `docker-compose.yml`). For local development it is already set to `http://localhost:8000`.
- Static assets are served by Nginx with caching: files in `assets/` receive `Cache-Control: public, max-age=31536000, immutable`, and `index.html` gets `Cache-Control: no-cache`.
- The container listens on port `80`. In docker-compose it is forwarded to `8080`, so the SPA is available at http://localhost:8080.

```bash
# example local build
docker compose build frontend
docker compose up frontend
```

## Reverse proxy (Nginx)

If the frontend and API run on different hosts, proxy static files and media through the same domain as the SPA. This avoids CORS/Service Worker artifacts and allows absolute links to the API domain.

```nginx
server {
    listen 443 ssl;
    server_name app.example.com;

    location / {
        root /var/www/app/dist; # built frontend
        try_files $uri /index.html;
    }

    location /static/ {
        proxy_pass https://api.example.com/static/;
        proxy_set_header Host api.example.com;
        proxy_set_header X-Forwarded-Proto https;
        proxy_redirect off;
    }

    location /media/ {
        proxy_pass https://api.example.com/media/;
        proxy_set_header Host api.example.com;
        proxy_set_header X-Forwarded-Proto https;
        proxy_redirect off;
    }
}
```

> Alternative: set `VITE_BACKEND_ORIGIN=https://api.example.com` and serve `/media`/`/static` directly from the API domain (without a proxy) while keeping full HTTPS.

## Backend system dependencies

- The backend uses `python-magic` to inspect file contents, so install the `libmagic` packages on hosts running the backend (for example, `apt install libmagic1 libmagic-dev` on Debian/Ubuntu or `apk add file` on Alpine).
- To perform antivirus checks for uploaded files, run a `clamd` service (for example from the `clamav-daemon` package or the `clamav/clamav` Docker image).
  - Enable scanning by setting `EVENT_FILE_SCANNER_ENABLED=true`.
  - By default the backend connects to `clamd` over TCP (`EVENT_FILE_SCANNER_HOST` and `EVENT_FILE_SCANNER_PORT`, default `127.0.0.1:3310`).
  - For a Unix socket, provide the path via `EVENT_FILE_SCANNER_SOCKET` (takes precedence over host/port).
  - The connection timeout is configured via `EVENT_FILE_SCANNER_TIMEOUT` (seconds).
  - The `/healthz` endpoint verifies availability with a lightweight `PING` command and does not upload probe data.
  - When the scanner is unavailable, upload requests return HTTP 503, and when a threat is detected they return HTTP 422 with a localized message.
- Email delivery (such as password resets) must be non-blocking. The backend uses `anyio.to_thread.run_sync` so SMTP calls run in a separate thread and do not block the event loop; avoid calling SMTP directly from coroutines when customizing.

## Notifications worker

- Start a dedicated worker to send push notifications: `python -m app.workers.notifications`.
- When running the API and worker in separate processes, disable the built-in scheduler in the API by setting `NOTIFICATIONS_SCHEDULER_INLINE_ENABLED=false`.
- The worker publishes health and Prometheus metrics at `http://<host>:9101/healthz` and `http://<host>:9101/metrics` (change the port via `NOTIFICATIONS_WORKER_METRICS_PORT`).
- docker-compose already includes a `notifications-worker` service with the `unless-stopped` restart policy.
- Jobs in the dead-letter queue are automatically removed after 30 days (`NOTIFICATION_QUEUE_DEAD_LETTER_RETENTION_DAYS`). The check interval is controlled by `NOTIFICATION_QUEUE_DEAD_LETTER_CLEANUP_INTERVAL_SECONDS` (minimum 300 seconds; set `0` to disable the scheduler).

## User session cleanup

- The API automatically removes stale records from `active_sessions` at startup and then every 15 minutes.
- Adjust the frequency via `SESSION_CLEANUP_INTERVAL_SECONDS` (minimum 30 seconds). Setting the value to `0` disables the background scheduler; you can run the cleanup manually with `python -m app.services.session_cleanup` inside the container/virtual environment.
- Session revocations (logout, `/auth/sessions/*`) now delete database rows immediately. Run the cleanup script once after upgrading to purge any previously revoked-but-not-deleted rows so that operator dashboards and the `/auth/sessions` UI stay in sync.

## MFA challenge cleanup

- The `cleanup_stale_mfa_challenges` utility removes rows where both `expires_at` and `consumed_at` are older than `MFA_CHALLENGE_CLEANUP_GRACE_PERIOD_SECONDS`.
- The scheduler runs every 10 minutes by default (`MFA_CHALLENGE_CLEANUP_INTERVAL_SECONDS`, minimum 30 seconds). Set the value to `0` to disable the background loop; you can still run the job manually via `python -m app.services.mfa_challenge_cleanup`.
- We recommend triggering the cleanup every 5–10 minutes so the table does not grow indefinitely and login flows stay responsive. Monitor `periodic_task_mfa_challenge_cleanup_runs_total`, `_errors_total`, and `_deleted_total` to spot anomalies or repeated failures.
