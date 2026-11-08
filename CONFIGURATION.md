# Configuration Reference

This document describes the operator-facing environment variables used by the
University Ecosystem backend. Every typed `Settings` field is listed in the sections
above or in the [complete Settings inventory](#complete-settings-inventory) at the end;
`tests/test_configuration_settings_inventory.py` fails when a field is undocumented.
Defaults in this document are the runtime
`Settings` defaults; `.env.example` is an explicit local profile and may set a
different value intentionally. Only settings with an implemented `*_FILE`
variant accept secret-file mounts; the file value takes precedence over the
corresponding plaintext variable.

## 🔴 Required Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `DATABASE_URL` | PostgreSQL connection string | - |
| `SECRET_KEY` | Primary JWT signing secret (min 32 chars) | - |
| `AUDIT_LOG_SECRET` | Audit log signing secret (min 32 chars; use a random value outside development) | Development placeholder; must be overridden outside development |
| `INTERNAL_HMAC_SECRET` | Internal gateway signature key (Required in production) | - |
| `TOKEN_HMAC_SECRET` | Dedicated HMAC key for password-reset and email-change tokens (min 32 bytes; required in staging/production) | - |

---

## 💾 Database

| Variable | Description | Default |
|----------|-------------|---------|
| `DATABASE_URL` | `postgresql+asyncpg://ue_app:pass@host/db`: runtime login for the backend and outbox worker. Use a `NOSUPERUSER NOBYPASSRLS` role with DML grants only and no `ue_rls_bypass` membership, so the tenant policies apply to every request. Never use the bootstrap superuser or `ue_migrator`. | Validated at startup |
| `NOTIFICATIONS_DATABASE_URL` | Compose stacks only: `ue_worker` login for the notifications worker. Membership in `ue_rls_bypass` lets its schedule-reminder scan read every tenant. The application does not read this name. | Required by `docker-compose.yml` |
| `MIGRATION_DATABASE_URL` | Compose stacks only: `ue_migrator` login for the `migrations` service (`alembic upgrade head`). It owns the schema and is the only superuser login outside bootstrap. The application does not read this name. | Required by `docker-compose.yml` |
| `UE_APP_DB_PASSWORD`, `UE_WORKER_DB_PASSWORD`, `UE_MIGRATOR_DB_PASSWORD` | Compose and bootstrap inputs: passwords for the `ue_app`, `ue_worker` and `ue_migrator` logins. `start-docker.ps1` generates them as alphanumeric values; `postgres-roles-init` applies them on every start. | Generated |
| `DATABASE_POOL_SIZE` | Base SQLAlchemy pool size; defaults to `2 * cgroup-aware CPU count + 1` (CPU quota capped at 32) | Formula |
| `DATABASE_MAX_OVERFLOW` | Additional connections above the base pool; defaults to `4 * cgroup-aware CPU count` | Formula |
| `DATABASE_POOL_TIMEOUT` | Connection timeout (seconds) | `30.0` |
| `DATABASE_POOL_RECYCLE` | Recycle connections after (seconds) | `540` |
| `DATABASE_STATEMENT_CACHE_SIZE` | asyncpg statement cache (0=PgBouncer) | `0` |
| `AUTO_CREATE_SCHEMA` | Auto-create DB tables (development/test only; otherwise migrations are required) | `true` in development/test, `false` otherwise |
| `SLOW_QUERY_LOGGING_ENABLED` | Enable slow query logging | `true` |
| `SLOW_QUERY_THRESHOLD_MS` | Threshold for slow query alerts | `500.0` |
| `SLOW_QUERY_EXPLAIN_ENABLED` | Include `EXPLAIN` details for slow queries | `false` |

**Database login roles.** `infrastructure/postgres-roles/bootstrap-app-roles.sql` provisions the Compose roles on every start, before migrations. `ue_app` (backend, outbox worker) and `ue_worker` (notifications worker) are `NOSUPERUSER NOBYPASSRLS` with DML grants only. `ue_migrator` owns the schema and runs Alembic only; it is a superuser because the baseline creates the non-trusted pgvector extension and comments on it.

**Runtime credential scope.** Compose gives each container only the credentials it needs, enforced by `tests/test_compose_runtime_credential_isolation.py`. The backend and migrations take the names-only `docker-compose.runtime-app.allowlist`, and the notifications and outbox workers take `docker-compose.runtime-worker.allowlist` (full stack: the launcher-redacted `.env.docker.workers`). An allowlisted name is injected only when the interpolation file (`.env` or `.env.docker`) defines it. The superuser password, the three role passwords and the URLs that embed them are never listed. The backend and outbox worker receive only `DATABASE_URL` (`ue_app`), the notifications worker only its own `ue_worker` URL, and migrations only `ue_migrator`. Bootstrap one-shots (`postgres-roles-init`, `postgres-databases-init`, `spicedb-migrate`, `temporal-admin-tools`) and the `postgres` server may see the superuser password, and `postgres-roles-init` the role passwords. **Known gap:** `spicedb` and `temporal` still authenticate to PostgreSQL as the bootstrap superuser because no dedicated roles exist yet; provisioning `ue_spicedb` and `ue_temporal` in `infrastructure/postgres-roles` closes it. Membership in `ue_rls_bypass` is the only grant that lifts the tenant policies for query access, and a session GUC never lifts them. Maintenance jobs need different authority: `pg_dump` runs with `row_security=off`, so a dump login needs the `BYPASSRLS` attribute, because membership does not satisfy it. Provision a SELECT-only `BYPASSRLS` login for `backup-database-url`. The `migrate_passwords` inventory fails closed unless its login is a `ue_rls_bypass` member.

---

## 🔒 Authentication & Security

| Variable | Description | Default |
|----------|-------------|---------|
| `MVP_TENANT_ID` | Optional operator-configured UUID of the existing active organization for single-organization MVP routing. It does not authenticate users, create a tenant, or grant an RLS bypass; missing or inactive configured tenants fail closed. When unset, no default tenant is selected and existing fail-closed RLS behavior remains. | Unset (`None`) |
| `SECRET_KEY` | Primary JWT signing secret | Validated at startup |
| `ALGORITHM` | JWT algorithm; `HS256` is permitted only for local development/testing | `RS256` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Token TTL; ws-hub's `WS_REVOCATION_REPLAY_WINDOW_SECONDS` must be at least this many seconds | `60` |
| `MAX_SESSIONS_PER_USER` | Concurrent sessions (0=unlimited) | `5` |
| `AUTH_LOCKOUT_THRESHOLDS` | Lockout rules `attempts:seconds` | `5:30,8:300,10:3600` |
| `CSRF_HMAC_SECRET` | Independent HMAC key for signed CSRF cookies; unsigned fallback is development/testing only | Empty locally; required outside development |
| `INTERNAL_HMAC_SECRET` | Verifies the gateway `X-Internal-Signature` identity assertion (minimum 32 bytes) | Required outside development |
| `AUDIT_LOG_SECRET` | HMAC key for audit log signatures (min 32 chars) | Development placeholder; must be overridden outside development |
| `TOKEN_HMAC_SECRET` | Dedicated HMAC key for password-reset and email-change token digests | Required in staging/prod |
| `PASSWORD_HIBP_CHECK_ENABLED` | Screens new passwords against the Have I Been Pwned range API (k-anonymity prefix only). Staging and production turn it on when unset and reject an explicit `false` | `false` in development; forced `true` in staging/production |
| `JWT_PRIVATE_KEY_PATH` | RS256 private key path used to mint access tokens | `.secrets/jwt_rs256.pem` |
| `JWT_AUDIENCE` | Expected JWT audience for zero-trust consumers | `university-ecosystem-api` |
| `JWT_ISSUER` | Stable JWT issuer for zero-trust consumers | `university-ecosystem` |
| `JWT_SIGNING_KEYS` | Comma-separated `kid:secret` rotation entries | Empty (uses the RS256 private key or local fallback) |
| `JWT_ACTIVE_KID` | Active signing key ID when `JWT_SIGNING_KEYS` is configured | Empty (first configured key) |

### MFA Settings

| Variable | Description | Default |
|----------|-------------|---------|
| `MFA_ENABLED` | Enable MFA | `false` |
| `MFA_TOTP_ISSUER` | TOTP app name | `University Ecosystem` |
| `MFA_TOTP_ENCRYPTION_KEYS` | Comma-separated `kid:Fernet-key` ring for TOTP enrollment ciphertext; non-active entries are legacy decrypt keys | Empty in development; required for API and migrations in staging/production |
| `MFA_TOTP_ACTIVE_ENCRYPTION_KEY_ID` | Non-secret key ID used to encrypt new TOTP enrollments | Empty in development; required for API and migrations in staging/production |
| `MFA_CHALLENGE_TTL_SECONDS` | Challenge validity | `600` (the local `.env.example` explicitly overrides this to `300`) |
| `MFA_CHALLENGE_MAX_ATTEMPTS` | Max attempts | `5` |
| `MFA_STEP_UP_TTL_SECONDS` | Step-up authentication validity | `300` |
| `MFA_EMAIL_OTP_TTL_SECONDS` | Email OTP validity | `600` |
| `MFA_EMAIL_OTP_RESEND_COOLDOWN_SECONDS` | Minimum interval between OTP deliveries | `60` |
| `MFA_EMAIL_OTP_HMAC_KEYS` | Comma-separated email OTP HMAC key ring (`kid:base64url`) | Empty locally; required when email OTP is enabled |
| `MFA_EMAIL_OTP_ACTIVE_HMAC_KEY_ID` | Active email OTP HMAC key ID | Empty locally |
| `MFA_EMAIL_DELIVERY_KEKS` | Comma-separated delivery encryption key ring (`kid:base64url`) | Empty locally; required when email OTP is enabled |
| `MFA_EMAIL_DELIVERY_ACTIVE_KEK_ID` | Active email delivery encryption key ID | Empty locally |
| `MFA_TRUSTED_DEVICE_HMAC_KEYS` | Trusted-device HMAC key ring | Empty locally; required when trusted devices are enabled |
| `MFA_TRUSTED_DEVICE_ACTIVE_HMAC_KEY_ID` | Active trusted-device HMAC key ID | Empty locally |
| `TRUSTED_DEVICE_EXPIRE_DAYS` | Remember device period | `30` |

---

## ⚡ Cache & Rate Limiting

| Variable | Description | Default |
|----------|-------------|---------|
| `CACHE_BACKEND` | `redis`, `memory`, `tiered`, `none`, `nats` | `redis` |
| `CACHE_ENABLED` | Enable caching | `true` |
| `CACHE_REDIS_URL` | Redis URL | `redis://127.0.0.1:6379/0` |
| `REVOCATION_REDIS_URL` | Dedicated persistent/noeviction Redis URL for session revocation. The Go gateway defaults to `redis://redis:6379/0`, while ws-hub defaults to `redis://revocation-redis:6379/0`; deployment configuration must supply the intended store. | Required outside development |
| `NATS_URL` | NATS message bus endpoint | `nats://127.0.0.1:4222` |
| `NATS_AUTH_TOKEN` | NATS authentication token | Empty locally; required in production |
| `NATS_TASK_MAX_DELIVERIES` | Delivery attempts of a background task before it is parked in the dead-letter queue (`/admin/dlq`). Read directly from the process environment in `app/core/nats_broker.py`, not through `Settings`. | `5` |
| `NATS_TASK_RETRY_BASE_DELAY_SECONDS` | First redelivery delay of a failed task; doubles per attempt up to 300 s. Read with `os.environ` in `app/core/nats_broker.py`, not through `Settings` | `5` |
| `RATE_LIMIT_ENABLED` | Enable rate limiting | `true` |
| `RATE_LIMIT_DEFAULT` | Default rate | `200/minute` |
| `RATE_LIMIT_STORAGE_BACKEND` | `memory` or `redis` | `memory` |
| `RATE_LIMIT_STORAGE_URI` | Storage URI when the rate limiter backend is Redis | `memory://` |
| `TRUSTED_PROXIES` | Comma-separated IPs/CIDRs of the gateway and edge peers whose `X-Forwarded-For` the API trusts. Staging/production API processes must list at least one; the Helm chart renders `backend.config.trustedProxies` and rejects an empty, loopback-only or universal list | Empty (trusts no peer; development only) |

---

## 🛡️ Security Headers & Image Proxy

| Variable | Description | Default |
|----------|-------------|---------|
| `SECURITY_CSP` | Custom Content Security Policy | Built-in |
| `SECURITY_HSTS_ENABLED` | Enable HSTS | `true` |
| `SECURITY_X_FRAME_OPTIONS` | X-Frame-Options (`DENY`, `SAMEORIGIN`) | `DENY` |
| `IMGPROXY_KEY` | Hex key for imgproxy signing | Empty |
| `IMGPROXY_SALT` | Hex salt for imgproxy signing | Empty |
| `IMGPROXY_BASE_URL` | Public imgproxy route (Caddy strips the prefix) | `http://localhost/imgproxy` |

---

## 📁 Storage & File Processing

StaticFS public media remains relative by default. Chat attachments persist an
absolute storage identity but are still downloaded only through the authorized
chat API; `STORAGE_STATIC_ORIGIN` does not make private directories public or
cause a redirect. Configure it from trusted backend settings, never request Host
or frontend origin. Keep it stable after uploading attachments: changing an
identity prefix does not migrate existing stored URLs. An explicitly absolute
HTTP(S) `STORAGE_STATIC_BASE_URL` takes precedence; only its scheme casing is
canonicalized for private identities, leaving public URLs unchanged. Private
identity generation rejects ambiguous URL keys/bases before final attachment
directory preparation/save; existing quarantine behavior, generic literal
local-key operations and S3 behavior are unchanged.

| Variable | Description | Default |
|----------|-------------|---------|
| `STORAGE_BACKEND` | `static`, `local`, `s3`, `minio` | `static` |
| `STORAGE_STATIC_BASE_URL` | Public URL for static files; an absolute HTTP(S) prefix also identifies private StaticFS attachments | `/static` |
| `STORAGE_STATIC_ORIGIN` | Trusted backend origin with a lowercase HTTP(S) scheme for persisted private StaticFS identities when the public prefix is relative; no path, credentials, query or fragment | `http://localhost:8000` |
| `STORAGE_QUARANTINE_QUOTA_BYTES` | Charged rejected-upload payload bytes per shared storage scope | `1073741824` |
| `STORAGE_QUARANTINE_RETENTION_DAYS` | TTL for acknowledged stored quarantine objects; ambiguous pending writes remain charged | `7` |
| `STORAGE_QUARANTINE_SWEEP_INTERVAL_SECONDS` | API quarantine cleanup interval | `300` |
| `STORAGE_QUARANTINE_INVENTORY_PAGE_SIZE` | Maximum objects per bootstrap inventory page | `100` |
| `STORAGE_QUARANTINE_SCOPE_ID` | Shared scope override for aliases of one physical store; see [quarantine runbook](docs/runbooks/upload-quarantine.md) | Empty |
| `STORAGE_S3_BUCKET` | S3 bucket name | Empty |
| `STORAGE_S3_REGION` | AWS Region | Empty |
| `STORAGE_S3_ENDPOINT_URL` | Custom S3 endpoint (for example the Compose SeaweedFS service `http://minio:9000`) | Empty |
| `EVENT_FILE_SCANNER_ENABLED` | Enable ClamAV scanning (must be true in staging/production) | `false` (runtime default) |
| `EVENT_FILE_MAX_SIZE_BYTES` | Max upload size (default 10MB) | `10485760` |
| `CHAT_MAX_MESSAGE_LENGTH` | Max characters per message | `32768` |

---

## 🏗️ Integrations

| Variable | Description | Default |
|----------|-------------|---------|
| `SPOTIFY_CLIENT_ID` | Spotify Client ID | Empty |
| `SPOTIFY_CLIENT_SECRET` | Spotify Secret (`_FILE` supported) | Empty |
| `SPOTIFY_OAUTH_STATE_SECRET`| Secret for OAuth2 state JWTs | Empty |
| `SPICEDB_ENDPOINT` | SpiceDB gRPC endpoint | `spicedb:50051` |
| `SPICEDB_PRESHARED_KEY` | SpiceDB auth key (`_FILE` supported); the development sentinel is rejected outside development | `development-preshared-key` (development only) |
| `ELASTICSEARCH_URL` | Search engine endpoint; production/staging requires `https://` | `http://localhost:9200` (local only) |
| `ELASTICSEARCH_PASSWORD` | ES password (`_FILE` supported) | Empty; required outside development/test unless CI |
| `WS_HUB_INTERNAL_SECRET` | HMAC for ws-hub cache invalidation (`_FILE` supported) | Empty; required outside development/test unless CI |
| `INTERNAL_AUTH_TOKEN` | Token for ws-hub's exact room-participant callback; managed Compose/Helm/K8s deployments derive it from the existing ws-hub secret | Empty in development |
| `IDEMPOTENCY_HMAC_SECRET` | HMAC key that signs idempotency keys (`_FILE` supported). An empty key makes keys enumerable from the `Idempotency-Key` header, so startup refuses it outside development/test unless CI | Empty (development only) |
| `TEMPORAL_JWKS_URL` | Temporal service: the `https://` JWKS endpoint whose keys its default authorizer trusts. `services/temporal/entrypoint.sh` refuses empty or plain-HTTP values; Compose sets `https://caddy:8443/.well-known/jwks.json`, which Caddy serves with its internal CA | Required (no default) |
| `WS_HUB_METRICS_ADDR` | Bind address of ws-hub's scrape-only Prometheus listener, separate from the public WebSocket port (AUD-438). The Helm chart binds `:9108` and admits only the monitoring namespace | `127.0.0.1:9108` |
| `WS_REVOCATION_REPLAY_WINDOW_SECONDS` | How far back a late-starting ws-hub replica replays room revocations from `CACHE_INVALIDATIONS`. It must be at least `ACCESS_TOKEN_EXPIRE_MINUTES` × 60; the Helm value `wsHub.config.revocationReplayWindowSeconds` is validated against it | `3600` |

---

## ⚙️ Background Workers & Retention

| Variable | Description | Default |
|----------|-------------|---------|
| `NOTIFICATIONS_WORKER_METRICS_HOST` | Notifications worker health and metrics listener address | `127.0.0.1` |
| `NOTIFICATIONS_WORKER_METRICS_PORT` | Notifications worker listener port; `0` disables the listener | `9101` |

### Transactional Outbox

| Variable | Description | Default |
|----------|-------------|---------|
| `OUTBOX_BATCH_SIZE` | Events processed per poll cycle by the active embedded worker | `20` |
| `OUTBOX_POLL_INTERVAL_SECONDS` | Polling interval (seconds) for the active embedded worker | `5.0` |
| `OUTBOX_MAX_RETRIES` | Dispatch attempts before DLQ | `5` |
| `EMBEDDED_OUTBOX_WORKER_ENABLED` | Enable the embedded polling outbox worker | `true` |
| `EMBEDDED_CDC_OUTBOX_WORKER_ENABLED` | Unsupported/deferred. Keep `false`: `true` is rejected before startup resources are opened. Use the polling outbox worker. Standalone CDC is also rejected before connecting or provisioning; production integration remains deferred under [ADR-037](docs/adr/ADR-037-cdc-outbox-transport-ownership.md). | `false` |

---

## 📧 Notifications (Email/Push)

| Variable | Description | Default |
|----------|-------------|---------|
| `SMTP_HOST` | SMTP server hostname | Empty (the local `.env.example` uses `127.0.0.1`) |
| `SMTP_PORT` | SMTP server port | `0` (the local `.env.example` uses `1025`) |
| `SMTP_SECURITY` | SMTP transport security (`none`, `starttls`, or `ssl`) | `none` |
| `SMTP_STARTTLS` | Enable STARTTLS compatibility flag for the SMTP client | `false` |
| `SMTP_USER` | SMTP username | Empty |
| `SMTP_PASSWORD` | SMTP password (`_FILE` supported) | Empty |
| `MAIL_FROM` | Sender address for transactional mail | `no-reply@example.com` |
| `VAPID_PUBLIC_KEY` | VAPID public key for WebPush | Empty |
| `VAPID_PRIVATE_KEY` | VAPID private key for WebPush | Empty |
| `NOTIFICATIONS_RETENTION_DAYS` | Days to keep notification history | `90` |

---

## 🌐 Environment

| Variable | Description | Default |
|----------|-------------|---------|
| `ENVIRONMENT` | `dev`, `development`, `local`, `test`, `testing`, `staging`, or `production` | `development` |
| `FRONTEND_ORIGIN` | Primary frontend URL for CORS | `http://localhost:5173` |
| `ENABLE_OTEL` | Enable OpenTelemetry tracing | `true` |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | OpenTelemetry collector endpoint. The Go gateway defaults to `tempo:4317`. | `http://localhost:4317` (backend) |
| `LOG_LEVEL` | Logging verbosity | `INFO` |

> **Tip**: `_FILE` loading is limited to the explicit secret-field allowlist in
> [the backend configuration](app/core/config/base.py). It includes, for example,
> `DATABASE_URL`, `AUDIT_LOG_SECRET`, `CSRF_HMAC_SECRET` and
> `MFA_TOTP_ENCRYPTION_KEYS`; the file value takes precedence over plaintext.
> `MFA_TOTP_ACTIVE_ENCRYPTION_KEY_ID` is a non-secret key name supplied directly
> through the environment and does not support `_FILE`. Other settings do not
> automatically accept a `_FILE` suffix.

The active TOTP key must be independent of every configured Spotify key and of
Spotify's `SECRET_KEY`-derived fallback. During migration, a non-active TOTP ring
entry may retain the previous Spotify key so existing enrollment ciphertext
remains readable. New writes always use the active TOTP key. Local development
with an empty ring derives a domain-separated key from `SECRET_KEY`; this fallback
is rejected outside development/testing. The explicit non-auth `outbox-worker` and
`notifications-worker` roles may start without the ring; TOTP crypto calls in those
roles fail closed.

---

## Complete Settings Inventory

Fields that are not listed in a thematic section above. Defaults are the runtime
`Settings` defaults read from the model; secret-valued defaults are shown as
placeholders and the secret source is named in the code. Variables read outside
`Settings` are listed in [Variables read outside Settings](#variables-read-outside-settings)
and are not part of this inventory.

### `app/core/config/app_gen.py`

| Variable | Description | Default |
|----------|-------------|---------|
| `ACCESS_LOG_RETENTION_DAYS` | Access log retention (days). Defined in `app/core/config/app_gen.py`. | `365` |
| `APP_PROCESS_ROLE` | The deployment manifests set these explicitly for background workers. API/migration processes retain the secure defaults and therefore cannot start with the revocation capability silently disabled. Defined in `app/core/config/app_gen.py`. | `api` |
| `ATTENDANCE_TOKEN_SECRET` | Attendance token secret. Defined in `app/core/config/app_gen.py`. | Empty |
| `ATTENDANCE_TOKEN_TTL_SECONDS` | Attendance token TTL (seconds). Defined in `app/core/config/app_gen.py`. | `300` |
| `CAMPUS_TIMEZONE` | Campus timezone. Defined in `app/core/config/app_gen.py`. | `UTC` |
| `EMAIL_CHANGE_CLEANUP_RETENTION_MINUTES` | Email change cleanup retention (minutes). Defined in `app/core/config/app_gen.py`. | `45` |
| `EMBEDDING_API_BASE` | Embedding API base. Defined in `app/core/config/app_gen.py`. | `https://api.openai.com/v1` |
| `EMBEDDING_API_KEY` | Embedding API key. Defined in `app/core/config/app_gen.py`. | Empty |
| `EMBEDDING_DIMENSIONS` | Embedding dimensions. Defined in `app/core/config/app_gen.py`. | `1536` |
| `EMBEDDING_MODEL` | Embedding model. Defined in `app/core/config/app_gen.py`. | `text-embedding-3-small` |
| `ENABLE_METRICS_ENDPOINT` | Enable metrics endpoint. Defined in `app/core/config/app_gen.py`. | `false` |
| `FAILED_LOGIN_RETENTION_DAYS` | Failed login retention (days). Defined in `app/core/config/app_gen.py`. | `30` |
| `HEALTH_STORAGE_PROBE_MIN_INTERVAL_SECONDS` | Health storage probe min interval (seconds). Defined in `app/core/config/app_gen.py`. | `3600` |
| `METRICS_ALLOWLIST` | Metrics allowlist. Defined in `app/core/config/app_gen.py`. | Empty |
| `METRICS_BASIC_AUTH_PASSWORD` | Metrics basic auth password. Defined in `app/core/config/app_gen.py`. | Empty |
| `METRICS_BASIC_AUTH_USERNAME` | Metrics basic auth username. Defined in `app/core/config/app_gen.py`. | Empty |
| `MFA_CHALLENGE_CLEANUP_GRACE_PERIOD_SECONDS` | MFA challenge cleanup grace period (seconds). Defined in `app/core/config/app_gen.py`. | `600` |
| `MFA_RETENTION_DAYS` | MFA retention (days). Defined in `app/core/config/app_gen.py`. | `30` |
| `PARTITION_MANAGEMENT_ENABLED` | Partition management enabled. Defined in `app/core/config/app_gen.py`. | `true` |
| `PARTITION_MANAGEMENT_INTERVAL_SECONDS` | Partition management interval (seconds). Defined in `app/core/config/app_gen.py`. | `86400` |
| `PARTITION_RETENTION_DAYS` | Partition retention (days). Defined in `app/core/config/app_gen.py`. | `365` |
| `PARTITION_WARMUP_MONTHS` | Partition warmup months. Defined in `app/core/config/app_gen.py`. | `1` |
| `PASSWORD_RESET_CLEANUP_RETENTION_MINUTES` | Password reset cleanup retention (minutes). Defined in `app/core/config/app_gen.py`. | `45` |
| `PASSWORD_RESET_MAX_ACTIVE_TOKENS` | Password reset max active tokens. Defined in `app/core/config/app_gen.py`. | `1` |
| `PRESENCE_PING_MIN_INTERVAL_SECONDS` | Presence ping min interval (seconds). Defined in `app/core/config/app_gen.py`. | `5` |
| `PRESENCE_PUBSUB_CHANNEL` | Presence pubsub channel. Defined in `app/core/config/app_gen.py`. | `presence_updates` |
| `PRESENCE_PUBSUB_ENABLED` | Presence pubsub enabled. Defined in `app/core/config/app_gen.py`. | `false` |
| `PRIVACY_CLEANUP_INTERVAL_SECONDS` | Privacy cleanup interval (seconds). Defined in `app/core/config/app_gen.py`. | `86400` |
| `REVOCATION_REDIS_ACCESS_ENABLED` | Revocation redis access enabled. Defined in `app/core/config/app_gen.py`. | `true` |
| `SEMANTIC_SEARCH_ENABLED` | Semantic Search. Defined in `app/core/config/app_gen.py`. | `true` |
| `SESSION_RETENTION_DAYS` | Session retention (days). Defined in `app/core/config/app_gen.py`. | `90` |
| `STORIES_CLEANUP_ENABLED` | Stories cleanup enabled. Defined in `app/core/config/app_gen.py`. | `true` |
| `WS_MAX_CONNECTIONS_PER_USER` | WS max connections per user. Defined in `app/core/config/app_gen.py`. | `5` |
| `WS_MESSAGE_BURST` | WS message burst. Defined in `app/core/config/app_gen.py`. | `10.0` |
| `WS_MESSAGE_RATE` | WS message rate. Defined in `app/core/config/app_gen.py`. | `5.0` |
| `WS_TICKET_TTL_SECONDS` | WS ticket TTL (seconds). Defined in `app/core/config/app_gen.py`. | `15` |

### `app/core/config/cache.py`

| Variable | Description | Default |
|----------|-------------|---------|
| `CACHE_CONFIG_MAX_SIZE` | Cache config max size. Defined in `app/core/config/cache.py`. | `100` |
| `CACHE_CONFIG_TTL_S` | Cache config TTL s. Defined in `app/core/config/cache.py`. | `300.0` |
| `CACHE_DEFAULT_TTL_SECONDS` | Cache default TTL (seconds). Defined in `app/core/config/cache.py`. | `300` |
| `CACHE_L1_TTL_SECONDS` | Cache l1 TTL (seconds). Defined in `app/core/config/cache.py`. | `60` |
| `CACHE_NATS_BUCKET` | Cache NATS bucket. Defined in `app/core/config/cache.py`. | `ue_cache` |
| `CACHE_NEWS_L1_MAX_SIZE` | Cache news l1 max size. Defined in `app/core/config/cache.py`. | `200` |
| `CACHE_NEWS_L1_TTL_S` | Cache news l1 TTL s. Defined in `app/core/config/cache.py`. | `60.0` |
| `CACHE_NEWS_L2_TTL_S` | Cache news l2 TTL s. Defined in `app/core/config/cache.py`. | `3600.0` |
| `CACHE_SCHEDULE_L1_MAX_SIZE` | Cache schedule l1 max size. Defined in `app/core/config/cache.py`. | `100` |
| `CACHE_SCHEDULE_L1_TTL_S` | Cache schedule l1 TTL s. Defined in `app/core/config/cache.py`. | `120.0` |
| `CACHE_SCHEDULE_L2_TTL_S` | Cache schedule l2 TTL s. Defined in `app/core/config/cache.py`. | `7200.0` |
| `CACHE_USER_MAX_SIZE` | Cache user max size. Defined in `app/core/config/cache.py`. | `500` |
| `CACHE_USER_TTL_S` | Cache user TTL s. Defined in `app/core/config/cache.py`. | `60.0` |
| `CACHE_WARMUP_ENABLED` | Cache warmup enabled. Defined in `app/core/config/cache.py`. | `false` |
| `CACHE_WARMUP_GROUPS` | Cache warmup groups. Defined in `app/core/config/cache.py`. | Empty |
| `CACHE_WARMUP_MAX_AGE_SECONDS` | Cache warmup max age (seconds). Defined in `app/core/config/cache.py`. | `120` |
| `CACHE_WARMUP_PERIODS` | Cache warmup periods. Defined in `app/core/config/cache.py`. | `30d,90d` |
| `CACHE_WARMUP_STATS_USERS` | Cache warmup stats users. Defined in `app/core/config/cache.py`. | Empty |
| `SESSION_STORAGE_BACKEND` | Session storage backend. Defined in `app/core/config/cache.py`. | `redis` |
| `STATS_CACHE_TTL_SECONDS` | Stats cache TTL (seconds). Defined in `app/core/config/cache.py`. | `180` |

### `app/core/config/database.py`

| Variable | Description | Default |
|----------|-------------|---------|
| `DATABASE_READ_REPLICA_URL` | Database read replica URL. Defined in `app/core/config/database.py`. | Unset |

### `app/core/config/integrations.py`

| Variable | Description | Default |
|----------|-------------|---------|
| `ELASTICSEARCH_USER` | Elasticsearch user. Defined in `app/core/config/integrations.py`. | `elastic` |
| `FLAGD_HOST` | Flagd host. Defined in `app/core/config/integrations.py`. | `localhost` |
| `FLAGD_PORT` | Flagd port. Defined in `app/core/config/integrations.py`. | `8013` |
| `SPOTIFY_REDIRECT_URI` | Spotify redirect URI. Defined in `app/core/config/integrations.py`. | `http://localhost:8000/spotify/callback` |
| `SPOTIFY_SCOPES` | Spotify scopes. Defined in `app/core/config/integrations.py`. | `user-read-currently-playing user-read-playback-state` |
| `SPOTIFY_TOKEN_SECRET` | Spotify token secret. Defined in `app/core/config/integrations.py`. | Empty |

### `app/core/config/mixins/cors_settings.py`

| Variable | Description | Default |
|----------|-------------|---------|
| `ALLOWED_HOSTS` | Allowed hosts. Defined in `app/core/config/mixins/cors_settings.py`. | Empty |
| `APP_BASE_URL` | App base URL. Defined in `app/core/config/mixins/cors_settings.py`. | `http://localhost:5173` |
| `CORS_ALLOW_CREDENTIALS` | CORS allow credentials. Defined in `app/core/config/mixins/cors_settings.py`. | `true` |
| `CORS_ALLOW_HEADERS` | CORS allow headers. Defined in `app/core/config/mixins/cors_settings.py`. | `Accept,Accept-Language,Authorization,Content-Language,Content-Type,Origin,X-Requested-With,x-profile-cache-envelope` |
| `CORS_ALLOW_METHODS` | CORS allow methods. Defined in `app/core/config/mixins/cors_settings.py`. | `GET,POST,PUT,PATCH,DELETE,OPTIONS` |
| `CORS_EXPOSE_HEADERS` | CORS expose headers. Defined in `app/core/config/mixins/cors_settings.py`. | Empty |
| `FRONTEND_ORIGINS` | Frontend origins. Defined in `app/core/config/mixins/cors_settings.py`. | Empty |
| `INTERNAL_ALLOWED_IPS` | Internal allowed ips. Defined in `app/core/config/mixins/cors_settings.py`. | `127.0.0.1,::1` |
| `INTERNAL_AUTH_HEADER` | Internal auth header. Defined in `app/core/config/mixins/cors_settings.py`. | `X-Internal-Token` |
| `REQUEST_ID_HEADER` | Request ID header. Defined in `app/core/config/mixins/cors_settings.py`. | `x-request-id` |
| `TRACE_HEADER` | Trace header. Defined in `app/core/config/mixins/cors_settings.py`. | `x-trace-id` |
| `TRUSTED_HOSTS` | Trusted hosts. Defined in `app/core/config/mixins/cors_settings.py`. | `localhost,127.0.0.1` |

### `app/core/config/mixins/csp_settings.py`

| Variable | Description | Default |
|----------|-------------|---------|
| `COEP_VALUE` | Coep value. Defined in `app/core/config/mixins/csp_settings.py`. | `require-corp` |
| `CORP_VALUE` | Corp value. Defined in `app/core/config/mixins/csp_settings.py`. | `same-site` |
| `ENABLE_COEP` | Enable coep. Defined in `app/core/config/mixins/csp_settings.py`. | `false` |
| `ENABLE_COOP` | Enable coop. Defined in `app/core/config/mixins/csp_settings.py`. | `true` |
| `ENABLE_CORP` | Enable corp. Defined in `app/core/config/mixins/csp_settings.py`. | `true` |
| `ENABLE_STRICT_SECURITY_HEADERS` | Enable strict security headers. Defined in `app/core/config/mixins/csp_settings.py`. | Unset |
| `SECURITY_CONNECT_SRC_EXTRA` | Security connect src extra. Defined in `app/core/config/mixins/csp_settings.py`. | `https://api.open-meteo.com,https://api.spotify.com,https://fcm.googleapis.com,https://fcmregistrations.googleapis.com,https://*.push.services.mozilla.com,https://updates.push.services.mozilla.com,https://*.push.apple.com` |
| `SECURITY_COOKIE_SAMESITE_OVERRIDE` | Security cookie samesite override. Defined in `app/core/config/mixins/csp_settings.py`. | Empty |
| `SECURITY_CSP_REPORT_ONLY` | Security CSP report only. Defined in `app/core/config/mixins/csp_settings.py`. | Unset |
| `SECURITY_CSP_REPORT_URI` | Security CSP report URI. Defined in `app/core/config/mixins/csp_settings.py`. | Empty |
| `SECURITY_HSTS_BEHIND_PROXY` | Security hsts behind proxy. Defined in `app/core/config/mixins/csp_settings.py`. | `false` |
| `SECURITY_HSTS_INCLUDE_SUBDOMAINS` | Security hsts include subdomains. Defined in `app/core/config/mixins/csp_settings.py`. | `true` |
| `SECURITY_HSTS_MAX_AGE` | Security hsts max age. Defined in `app/core/config/mixins/csp_settings.py`. | `31536000` |
| `SECURITY_HSTS_PRELOAD` | Security hsts preload. Defined in `app/core/config/mixins/csp_settings.py`. | `true` |
| `SECURITY_PERMISSIONS_POLICY` | Security permissions policy. Defined in `app/core/config/mixins/csp_settings.py`. | `accelerometer=(), autoplay=(), camera=(), cross-origin-isolated=(), display-capture=(), encrypted-media=(), fullscreen=(), geolocation=(), gyroscope=(), keyboard-map=(), magnetometer=(), microphone=(), midi=(), payment=(), picture-in-picture=(), publickey-credentials-get=(), screen-wake-lock=(), sync-xhr=(self), usb=(), web-share=(), xr-spatial-tracking=(), clipboard-read=(), clipboard-write=(), gamepad=()` |
| `SECURITY_REFERRER_POLICY` | Security referrer policy. Defined in `app/core/config/mixins/csp_settings.py`. | `no-referrer` |
| `SECURITY_X_CONTENT_TYPE_OPTIONS` | Security x content type options. Defined in `app/core/config/mixins/csp_settings.py`. | `nosniff` |

### `app/core/config/mixins/mfa_settings.py`

| Variable | Description | Default |
|----------|-------------|---------|
| `MFA_DEFAULT_METHOD` | MFA default method. Defined in `app/core/config/mixins/mfa_settings.py`. | Unset |
| `MFA_TOTP_ATTEMPT_HOURLY_LIMIT` | MFA TOTP attempt hourly limit. Defined in `app/core/config/mixins/mfa_settings.py`. | `15` |
| `MFA_TOTP_ATTEMPT_LIMIT` | MFA TOTP attempt limit. Defined in `app/core/config/mixins/mfa_settings.py`. | `5` |
| `MFA_TOTP_INITIAL_SKEW_WINDOWS` | MFA TOTP initial skew windows. Defined in `app/core/config/mixins/mfa_settings.py`. | `1` |
| `PASSWORD_HIBP_API_URL` | Password HIBP API URL. Defined in `app/core/config/mixins/mfa_settings.py`. | `https://api.pwnedpasswords.com/range` |
| `PASSWORD_HIBP_FAIL_OPEN` | Password HIBP fail open. Defined in `app/core/config/mixins/mfa_settings.py`. | `false` |
| `PASSWORD_HIBP_TIMEOUT_SECONDS` | Password HIBP timeout (seconds). Defined in `app/core/config/mixins/mfa_settings.py`. | `5` |
| `PASSWORD_MAX_LENGTH` | Password max length. Defined in `app/core/config/mixins/mfa_settings.py`. | `200` |
| `PASSWORD_MIN_CHARACTER_CLASSES` | Password min character classes. Defined in `app/core/config/mixins/mfa_settings.py`. | `3` |
| `PASSWORD_MIN_LENGTH` | Password min length. Defined in `app/core/config/mixins/mfa_settings.py`. | `12` |
| `PASSWORD_REQUIRE_DIGIT` | Password require digit. Defined in `app/core/config/mixins/mfa_settings.py`. | `true` |
| `PASSWORD_REQUIRE_LOWERCASE` | Password require lowercase. Defined in `app/core/config/mixins/mfa_settings.py`. | `true` |
| `PASSWORD_REQUIRE_SPECIAL` | Password require special. Defined in `app/core/config/mixins/mfa_settings.py`. | `true` |
| `PASSWORD_REQUIRE_UPPERCASE` | Password require uppercase. Defined in `app/core/config/mixins/mfa_settings.py`. | `true` |
| `PASSWORD_ZXCVBN_MIN_SCORE` | Password zxcvbn min score. Defined in `app/core/config/mixins/mfa_settings.py`. | `2` |
| `TRUSTED_DEVICE_COOKIE_NAME` | Trusted device cookie name. Defined in `app/core/config/mixins/mfa_settings.py`. | `trusted_device` |

### `app/core/config/mixins/rate_limit_settings.py`

| Variable | Description | Default |
|----------|-------------|---------|
| `AUTH_LOCKOUT_HISTORY_MINUTES` | Auth lockout history (minutes). Defined in `app/core/config/mixins/rate_limit_settings.py`. | `1440` |
| `RATE_LIMIT_AUTH_LOGIN` | Rate limit auth login. Defined in `app/core/config/mixins/rate_limit_settings.py`. | `5/minute` |
| `RATE_LIMIT_AUTH_MFA` | Rate limit auth MFA. Defined in `app/core/config/mixins/rate_limit_settings.py`. | `5/minute` |
| `RATE_LIMIT_AUTH_PASSWORD_RESET` | Rate limit auth password reset. Defined in `app/core/config/mixins/rate_limit_settings.py`. | `3/minute` |
| `RATE_LIMIT_AUTH_REGISTER` | Rate limit auth register. Defined in `app/core/config/mixins/rate_limit_settings.py`. | `5/minute` |
| `RATE_LIMIT_CHAT` | Rate limit chat. Defined in `app/core/config/mixins/rate_limit_settings.py`. | `120/minute` |
| `RATE_LIMIT_EVENTS` | Rate limit events. Defined in `app/core/config/mixins/rate_limit_settings.py`. | `120/minute` |
| `RATE_LIMIT_GRAPHQL` | Rate limit graphql. Defined in `app/core/config/mixins/rate_limit_settings.py`. | `30/minute` |
| `RATE_LIMIT_HEADERS_ENABLED` | Rate limit headers enabled. Defined in `app/core/config/mixins/rate_limit_settings.py`. | `true` |
| `RATE_LIMIT_INTERACTIONS` | Rate limit interactions. Defined in `app/core/config/mixins/rate_limit_settings.py`. | `200/minute` |
| `RATE_LIMIT_NEWS` | Rate limit news. Defined in `app/core/config/mixins/rate_limit_settings.py`. | `120/minute` |
| `RATE_LIMIT_SENSITIVE` | Rate limit sensitive. Defined in `app/core/config/mixins/rate_limit_settings.py`. | `5/minute` |
| `RATE_LIMIT_STATIC` | Rate limit static. Defined in `app/core/config/mixins/rate_limit_settings.py`. | `300/minute` |
| `RATE_LIMIT_STORIES` | Rate limit stories. Defined in `app/core/config/mixins/rate_limit_settings.py`. | `120/minute` |
| `RATE_LIMIT_UPLOAD` | Rate limit upload. Defined in `app/core/config/mixins/rate_limit_settings.py`. | `10/minute` |
| `RATE_LIMIT_USERS_AVATAR` | Rate limit users avatar. Defined in `app/core/config/mixins/rate_limit_settings.py`. | `10/minute` |
| `RATE_LIMIT_USERS_ME` | Rate limit users me. Defined in `app/core/config/mixins/rate_limit_settings.py`. | `120/minute` |
| `RATE_LIMIT_WEBSOCKET` | Rate limit websocket. Defined in `app/core/config/mixins/rate_limit_settings.py`. | `60/minute` |

### `app/core/config/notifications.py`

| Variable | Description | Default |
|----------|-------------|---------|
| `NOTIFICATIONS_ALLOWED_PUSH_TOPICS` | Notifications allowed push topics. Defined in `app/core/config/notifications.py`. | `['news.published', 'schedule.changed', 'events.published', 'chat.message.created', 'system.release']` |
| `NOTIFICATIONS_QUEUE_IN_MEMORY_ONLY` | Notifications queue in memory only. Defined in `app/core/config/notifications.py`. | `false` |
| `NOTIFICATIONS_RETENTION_BATCH_SIZE` | Notifications retention batch size. Defined in `app/core/config/notifications.py`. | `500` |
| `NOTIFICATIONS_SCHEDULER_MAX_BACKOFF_SECONDS` | Notifications scheduler max backoff (seconds). Defined in `app/core/config/notifications.py`. | `300` |
| `NOTIFICATIONS_SCHEDULER_POLL_SECONDS` | Notifications scheduler poll (seconds). Defined in `app/core/config/notifications.py`. | `30` |
| `NOTIFICATIONS_SCHEDULER_WINDOW_MINUTES` | Notifications scheduler window (minutes). Defined in `app/core/config/notifications.py`. | `6` |
| `NOTIFICATION_QUEUE_DEAD_LETTER_RETENTION_DAYS` | Notification queue dead letter retention (days). Defined in `app/core/config/notifications.py`. | `30` |
| `SMTP_MFA_TOTAL_TIMEOUT_SECONDS` | SMTP MFA total timeout (seconds). Defined in `app/core/config/notifications.py`. | `60` |
| `VAPID_SUBJECT` | VAPID subject. Defined in `app/core/config/notifications.py`. | Empty |

### `app/core/config/observability.py`

| Variable | Description | Default |
|----------|-------------|---------|
| `CWV_ALLOWED_ORIGINS` | CWV allowed origins. Defined in `app/core/config/observability.py`. | Empty |
| `CWV_DEPLOYED_AT` | CWV deployed at. Defined in `app/core/config/observability.py`. | Unset |
| `CWV_DEPLOYMENT_RUN_ATTEMPT` | CWV deployment run attempt. Defined in `app/core/config/observability.py`. | `0` |
| `CWV_DEPLOYMENT_RUN_ID` | CWV deployment run ID. Defined in `app/core/config/observability.py`. | `0` |
| `CWV_DEPLOYMENT_URL` | CWV deployment URL. Defined in `app/core/config/observability.py`. | Empty |
| `CWV_ENVELOPE_TTL_SECONDS` | CWV envelope TTL (seconds). Defined in `app/core/config/observability.py`. | `300` |
| `CWV_EXPORT_OIDC_ENABLED` | CWV export oidc enabled. Defined in `app/core/config/observability.py`. | `false` |
| `CWV_EXPORT_OIDC_REPOSITORY` | CWV export oidc repository. Defined in `app/core/config/observability.py`. | Empty |
| `CWV_EXPORT_OIDC_SUBJECT` | CWV export oidc subject. Defined in `app/core/config/observability.py`. | Empty |
| `CWV_EXPORT_OIDC_WORKFLOW_REF` | CWV export oidc workflow ref. Defined in `app/core/config/observability.py`. | Empty |
| `CWV_FRONTEND_IMAGE_DIGEST` | CWV frontend image digest. Defined in `app/core/config/observability.py`. | Empty |
| `CWV_MANUAL_TESTER_USER_IDS` | Operator-curated manual staging testers. Kept in the application Secret; raw UUIDs never enter observations or exported evidence. Defined in `app/core/config/observability.py`. | Empty |
| `CWV_RELEASE_SHA` | CWV release sha. Defined in `app/core/config/observability.py`. | Empty |
| `CWV_RETENTION_DAYS` | CWV retention (days). Defined in `app/core/config/observability.py`. | `30` |
| `CWV_RUM_ENABLED` | Trusted field-CWV collection is opt-in and validated fail-closed at startup. Defined in `app/core/config/observability.py`. | `false` |
| `CWV_RUM_SIGNING_SECRET` | CWV RUM signing secret. Defined in `app/core/config/observability.py`. | Empty |
| `ENABLE_OTEL_LOGS` | Enable OTEL logs. Defined in `app/core/config/observability.py`. | `true` |
| `ENABLE_OTEL_METRICS` | Enable OTEL metrics. Defined in `app/core/config/observability.py`. | `true` |
| `OTEL_EXPORTER_OTLP_HEADERS` | OTEL exporter otlp headers. Defined in `app/core/config/observability.py`. | Empty |
| `OTEL_SERVICE_NAME` | OTEL service name. Defined in `app/core/config/observability.py`. | `university-ecosystem` |
| `OTEL_TRACE_SAMPLER_RATIO` | OTEL trace sampler ratio. Defined in `app/core/config/observability.py`. | `1.0` |
| `SENTRY_DSN` | Sentry DSN. Defined in `app/core/config/observability.py`. | Empty |
| `SENTRY_ENVIRONMENT` | Sentry environment. Defined in `app/core/config/observability.py`. | Empty |
| `SENTRY_PROFILES_SAMPLE_RATE` | Sentry profiles sample rate. Defined in `app/core/config/observability.py`. | `0.0` |
| `SENTRY_TRACES_SAMPLE_RATE` | Sentry traces sample rate. The Go gateway defaults to `1.0`; the backend field is defined in `app/core/config/observability.py`. | `0.0` (backend) |
| `SERVICE_VERSION` | Backend telemetry service version; the backend also accepts `APP_VERSION` as an alias. Defined in `app/core/config/observability.py`. | Empty |

### `app/core/config/security.py`

| Variable | Description | Default |
|----------|-------------|---------|
| `API_V2_PREFIX` | API v2 prefix. Defined in `app/core/config/security.py`. | `/api/v2` |
| `CAMPUS_SUBNETS` | Campus subnets. Defined in `app/core/config/security.py`. | `['192.168.0.0/16', '10.0.0.0/8', '127.0.0.1/32']` |
| `CONTROL_WORK_GRACE_MINUTES` | Control work grace (minutes). Defined in `app/core/config/security.py`. | `15` |
| `GEOIP_DATABASE_PATH` | Geoip database path. Defined in `app/core/config/security.py`. | Unset |
| `MONITORING_HEAVY_PROBE_ENABLED` | Monitoring heavy probe enabled. Defined in `app/core/config/security.py`. | `false` |

### `app/core/config/storage.py`

| Variable | Description | Default |
|----------|-------------|---------|
| `CHAT_ATTACHMENT_ALLOWED_EXTENSIONS` | Chat attachment allowed extensions. Defined in `app/core/config/storage.py`. | `.jpg,.jpeg,.png,.webp,.gif,.mp4,.mov,.pdf,.txt` |
| `CHAT_ATTACHMENT_ALLOWED_MIME_TYPES` | Chat attachment allowed mime types. Defined in `app/core/config/storage.py`. | `image/jpeg,image/png,image/webp,image/gif,video/mp4,video/quicktime,application/pdf,text/plain` |
| `CHAT_ATTACHMENT_MAX_FILES` | Chat attachment max files. Defined in `app/core/config/storage.py`. | `5` |
| `CHAT_ATTACHMENT_MAX_SIZE_BYTES` | Chat attachment max size (bytes). Defined in `app/core/config/storage.py`. | `15728640` |
| `CHAT_ATTACHMENT_MAX_TOTAL_BYTES` | Chat attachment max total (bytes). Defined in `app/core/config/storage.py`. | `31457280` |
| `CHAT_GROUP_MAX_MEMBERS` | Chat group max members. Defined in `app/core/config/storage.py`. | `100` |
| `CHAT_GROUP_MIN_MEMBERS` | Chat group min members. Defined in `app/core/config/storage.py`. | `3` |
| `EVENT_FILE_ALLOWED_EXTENSIONS` | Event file allowed extensions. Defined in `app/core/config/storage.py`. | `.pdf,.txt,.doc,.docx,.xls,.xlsx` |
| `EVENT_FILE_ALLOWED_MIME_TYPES` | Event file allowed mime types. Defined in `app/core/config/storage.py`. | `application/pdf,text/plain,application/msword,application/vnd.openxmlformats-officedocument.wordprocessingml.document,application/vnd.ms-excel,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet` |
| `EVENT_FILE_SCANNER_BACKEND` | Event file scanner backend. Defined in `app/core/config/storage.py`. | `clamd` |
| `EVENT_FILE_SCANNER_HOST` | Event file scanner host. Defined in `app/core/config/storage.py`. | `127.0.0.1` |
| `EVENT_FILE_SCANNER_MAX_DURATION_SEC` | Event file scanner max duration sec. Defined in `app/core/config/storage.py`. | `10.0` |
| `EVENT_FILE_SCANNER_MAX_SIZE_MB` | Event file scanner max size (MB). Defined in `app/core/config/storage.py`. | `25.0` |
| `EVENT_FILE_SCANNER_PORT` | Event file scanner port. Defined in `app/core/config/storage.py`. | `3310` |
| `EVENT_FILE_SCANNER_SOCKET` | Event file scanner socket. Defined in `app/core/config/storage.py`. | Empty |
| `EVENT_FILE_SCANNER_TIMEOUT` | Event file scanner timeout. Defined in `app/core/config/storage.py`. | `30.0` |
| `HEALTH_STORAGE_PROBE_ENABLED` | Health storage probe enabled. Defined in `app/core/config/storage.py`. | `true` |
| `IMAGE_MAX_HEIGHT` | Image max height. Defined in `app/core/config/storage.py`. | `1920` |
| `IMAGE_MAX_PIXELS` | Guard decoder allocations before EXIF transpose/load. The upper bound is intentionally finite so deployments cannot disable the resource policy by supplying an unbounded environment value. Defined in `app/core/config/storage.py`. | `25000000` |
| `IMAGE_MAX_WIDTH` | Image max width. Defined in `app/core/config/storage.py`. | `1920` |
| `IMAGE_PROXY_ALLOWED_WIDTHS` | Image proxy allowed widths. Defined in `app/core/config/storage.py`. | `100,200,400,800,1200,1600` |
| `IMAGE_PROXY_ENABLED` | Image proxy enabled. Defined in `app/core/config/storage.py`. | `true` |
| `MINIO_BUCKET` | Minio bucket. Defined in `app/core/config/storage.py`. | `uploads` |
| `MINIO_ENDPOINT` | Minio endpoint. Defined in `app/core/config/storage.py`. | `minio:9000` |
| `MINIO_SECURE` | Minio secure. Defined in `app/core/config/storage.py`. | `false` |
| `RESPONSE_COMPRESSION_ENABLED` | Response compression enabled. Defined in `app/core/config/storage.py`. | `true` |
| `ENABLE_RESPONSE_COMPRESSION` | Backward-compatible alias for `RESPONSE_COMPRESSION_ENABLED`. | `true` |
| `STATIC_DIR` | Static dir. Defined in `app/core/config/storage.py`. | `app/static` |
| `STORAGE_S3_ACCESS_KEY_ID` | Storage S3 access key ID. Defined in `app/core/config/storage.py`. | Empty |
| `STORAGE_S3_BASE_URL` | Storage S3 base URL. Defined in `app/core/config/storage.py`. | Empty |
| `STORAGE_S3_SECRET_ACCESS_KEY` | Storage S3 secret access key. Defined in `app/core/config/storage.py`. | Empty |

## Variables read outside Settings

These names are read directly from the process environment by the `app` package,
not through the `Settings` model. `tests/test_configuration_outside_settings_drift.py`
derives the set from literal keys and simple module constants used in `os.environ`
or `os.getenv` reads, and fails when a name has no row with a documented default.

| Variable | Description | Default |
|----------|-------------|---------|
| `CI` | CI runner flag. Together with `GITHUB_ACTIONS` it relaxes secret enforcement for tooling steps; set by the CI platform, not by operators. Read in `app/core/config/__init__.py`, `app/core/config/integrations.py` and `app/core/settings_sources.py`. | Unset (not CI) |
| `GITHUB_ACTIONS` | GitHub Actions runner flag; same effect as `CI` (`true` only). | Unset (not CI) |
| `ENABLE_PROFILING` | Selects the Pyroscope profiler when `true` (case-insensitive); any other value uses the no-op profiler. Read in `app/core/profiling.py`. | `false` |
| `PYROSCOPE_SERVER_ADDRESS` | Pyroscope server URL used when profiling is enabled and no explicit address is passed. | `http://pyroscope:4040` |
| `ENV_FILE_PATH` | Overrides the environment file read by the settings sources. An empty or nonexistent path disables the file; an explicitly selected file or `.env` identical to the example is accepted with a warning. Read in `app/core/settings_sources.py`. | Unset (first existing project-root `.env` or `.env.local`, otherwise no file) |
| `ENV_EXAMPLE_PATH` | Overrides the example file used to detect an unedited copy in `ENV_FILE_PATH`. | `.env.example` in the project root |
| `OTEL_SDK_DISABLED` | OpenTelemetry kill switch read before any provider or exporter starts; `1`, `true`, `yes` or `on` disable the SDK. Read in `app/core/observability.py`. | Unset (SDK enabled) |
| `OUTBOX_WORKER_RUNTIME_DIR` | Directory for the outbox worker PID and heartbeat markers. Read in `app/workers/outbox.py`. | System temporary directory |
| `NATS_TASK_TIMEOUT_SECONDS` | Per-task timeout for the NATS task worker in `app/core/nats_broker.py`. | `30` |
| `NATS_FETCH_BATCH_SIZE` | Messages fetched per NATS task-worker batch, clamped to 1 through 100. | `20` |
| `SPICEDB_INSECURE` | Permits a plaintext SpiceDB connection when `true`; TLS is otherwise forced. Local development only. Read in `app/core/spicedb.py`. | `false` |
| `AUD373_TLS_DIAGNOSTICS` | Opt-in, bounded AUD-373 handshake proof telemetry when internal HTTP mTLS is enabled. Only the exact value `1` enables it; all other values leave it disabled. Read in `app/server/spiffe_worker.py`; it does not change TLS verification or authorization. | Unset (disabled) |
| `INTERNAL_HTTP_MTLS_SERVER_SPIFFE_ID` | Exact backend workload identity; required when internal HTTP mTLS is enabled. | Unset |
| `INTERNAL_HTTP_MTLS_ALLOWED_CLIENT_SPIFFE_IDS` | Comma-separated, unique client identities in the server trust domain; must include the backend's own probe identity when internal HTTP mTLS is enabled. | Unset |

### Frontend SSR runtime

The production Node wrapper and SSR entry points also read process environment
variables. The drift check covers literal reads in `frontend/scripts/server-prod.mjs`,
`frontend/src/server.ts`, `frontend/src/api/backendOrigin.ts` and
`frontend/src/ssrAuth.ts`; it is not an inventory of all frontend build variables.
Use a trusted backend origin without embedded credentials. The Vite build-time
fallback is also used by browser code, so it must not contain secrets.

| Variable | Description | Default |
|----------|-------------|---------|
| `HOST` | Address on which the production SSR wrapper listens. | `0.0.0.0` |
| `PORT` | SSR wrapper listen port; the explicitly enabled Lighthouse SSR preview can override it. | `3000` when unset |
| `BACKEND_ORIGIN` | Backend origin for SSR API and JWKS requests. A nonempty runtime value takes precedence over the build-time `VITE_BACKEND_ORIGIN`. | Build-time origin when nonempty; otherwise `http://localhost:8000` |
| `JWT_ISSUER` | Issuer expected by SSR JWT verification; use the same value as the backend. Blank or invalid values fail authentication. | Unset in production (authentication fails closed); `university-ecosystem` when omitted outside production |
| `NODE_ENV` | Node mode used by SSR issuer validation. The frontend container sets `production`. | Unset in the process unless supplied |
| `TSS_PRERENDERING` | TanStack build flag: `true` uses a placeholder nonce and suppresses the request-origin getter during prerendering. Leave unset for live requests. | Unset |

### Go services (gateway, ws-hub, file-processor)

These names are read by the Go services under `services/gateway`, `services/ws-hub` and
`services/file-processor`. `tests/test_configuration_outside_settings_drift.py` derives
the set from literal names passed to `os.Getenv`, `os.LookupEnv`, the `getEnv*`
helpers, secret readers and the file-processor secret table. It separately checks the
file-processor's `FP_`-prefixed Viper struct fields. A secret-capable name also accepts
a `<NAME>_FILE` mount where the Go code reads it through `readSecretEnv` or the `_FILE` lookup.
Among environment variables for file-processor fields explicitly bound in
`bindConfigEnvironment`, Viper checks the `FP_` name first and falls back to the
bound unprefixed name when it is absent. An explicitly empty `FP_` value takes
precedence over the unprefixed name.

| Variable | Description | Default |
|----------|-------------|---------|
| `GATEWAY_PORT` | Gateway HTTP listen port. | `8080` |
| `GATEWAY_H3_ENABLED` | Enables the HTTP/3 listener on the gateway. | `true` |
| `GATEWAY_H3_PORT` | HTTP/3 listen port on the gateway. | `8443` |
| `GATEWAY_H3_ALT_SVC_MAX_AGE` | `Alt-Svc` max-age advertised for HTTP/3, in seconds. | `2592000` |
| `GATEWAY_TRUSTED_PROXIES` | Comma-separated proxy addresses whose forwarded client IP is trusted. | Unset (no trusted proxies) |
| `ALLOWED_ORIGINS` | Comma-separated browser origins accepted by the gateway for CORS. | `http://localhost:3000,http://localhost:5173` |
| `APP_VERSION` | Version label reported by the gateway; the backend also accepts it as an alias for `SERVICE_VERSION`. | `unknown` (Go gateway); Empty (backend, same as `SERVICE_VERSION`) |
| `VITE_ENVIRONMENT` | Environment name the gateway reads for its runtime mode (`development`, `staging` or `production`). | `development` |
| `GIN_MODE` | Gin mode; the gateway switches to test mode when it is `test`. Read, not set by operators in production. | Unset |
| `BACKEND_URL` | Gateway upstream URL for the backend service. | `http://backend:8000` |
| `BACKEND_INTERNAL_URL` | ws-hub upstream URL for internal calls to the backend. | `http://backend:8000` |
| `BACKEND_SPIFFE_ID` | SPIFFE ID expected for the backend peer. | `spiffe://university.ecosystem/ns/default/sa/app` |
| `FILE_PROCESSOR_ADDR` | gRPC address of the file-processor service. | `file-processor:50051` |
| `FILE_PROCESSOR_SPIFFE_ID` | SPIFFE ID expected for the file-processor peer. | `spiffe://university.ecosystem/ns/default/sa/file-processor` |
| `FILE_PROCESSING_CAPABILITY_SECRET` | Gateway secret that signs file-processing capabilities (`_FILE` supported); minimum strength enforced at startup. | Validated at startup |
| `WSHUB_URL` | Gateway upstream URL for the ws-hub service. | `http://ws-hub:8081` |
| `GRPC_USE_TLS` | gRPC TLS toggle; only the exact value `false` disables TLS. | `true` |
| `GRPC_CA_FILE` | CA bundle for verifying gRPC peers. | Unset |
| `GRPC_CLIENT_CERT_FILE` | Client certificate presented on gRPC calls. | Unset |
| `GRPC_CLIENT_KEY_FILE` | Private key for `GRPC_CLIENT_CERT_FILE`. | Unset |
| `GRPC_CLIENT_IDENTITY_URI` | Expected SPIFFE URI SAN of the gRPC client identity. | Unset |
| `GRPC_SERVER_NAME` | Server name used to verify the gRPC TLS certificate. | Unset |
| `INTERNAL_HTTP_MTLS_ENABLED` | Enables mutual TLS for internal HTTP calls in the gateway and backend; must parse as a boolean. The backend requires its server identity, allowed clients and Workload API socket when enabled. | `false` |
| `TLS_CERT_FILE` | Certificate file for the gateway's own TLS listener. | Unset |
| `TLS_KEY_FILE` | Private key file for `TLS_CERT_FILE`. | Unset |
| `JWT_SECRET` | Gateway JWT verification secret (`_FILE` supported). | Validated at startup |
| `JWKS_ENDPOINT` | Gateway JWKS URL for RS256 key discovery. | Unset |
| `JWKS_PUBLIC_KEY_PEM` | Optional RS256 public key in PEM form. | Unset |
| `JWKS_REFRESH_INTERVAL` | JWKS refresh interval in seconds. | `300` |
| `JWKS_URL` | ws-hub JWKS URL used to verify tokens. | `http://backend:8000/.well-known/jwks.json` |
| `JWT_SECRETS` | ws-hub ring of JWT verification secrets for rotation (`_FILE` supported). | Unset (single-secret mode) |
| `REDIS_URL` | Redis URL read by the gateway and ws-hub (`_FILE` supported). | Gateway: `redis://redis:6379/3`; ws-hub: `redis:6379` |
| `REDIS_DB` | Redis logical database index for ws-hub. | `0` |
| `REDIS_PASSWORD` | Redis password for ws-hub (`_FILE` supported). | Unset |
| `NATS_USER` | NATS user for ws-hub (`_FILE` supported). | Unset |
| `NATS_PASSWORD` | NATS password for ws-hub (`_FILE` supported). | Unset |
| `NATS_STREAM_CHAT` | JetStream stream name for chat events. | `CHAT_EVENTS` |
| `NATS_STREAM_NOTIFICATIONS` | JetStream stream name for notification events. | `NOTIFICATIONS_EVENTS` |
| `WS_NATS_ACK_POLICY` | ws-hub NATS consumer ack policy. Only `explicit` is accepted; any other value fails startup (AUD-478). | `explicit` |
| `WS_NATS_ACK_WAIT_SECONDS` | ws-hub durable consumer ack wait in seconds. Must be an integer from 31 through 600 and exceed the 30 s callback timeout. | `60` |
| `WS_NATS_MAX_DELIVER` | ws-hub durable consumer maximum redeliveries of one invalidation. Must be an integer from 5 through 100. | `20` |
| `WS_NATS_INACTIVE_THRESHOLD_SECONDS` | ws-hub ephemeral consumer inactive threshold in seconds. Must be an integer from 60 through 86400. Helm mirrors these four keys under `wsHub.config.natsConsumer`. | `300` |
| `ENABLE_JETSTREAM` | Enables JetStream consumers in ws-hub. | `true` |
| `WS_HUB_PORT` | ws-hub HTTP and WebSocket listen port. | `8081` |
| `WS_HUB_WT_PORT` | ws-hub WebTransport port; falls back to `WT_PORT`. | `8443` |
| `WT_PORT` | Fallback WebTransport port when `WS_HUB_WT_PORT` is unset. | `8443` |
| `WS_ALLOWED_ORIGINS` | Comma-separated origins accepted for WebSocket upgrades in addition to the same-origin check. | Unset (none added) |
| `WS_HUB_MAX_CLIENTS` | Maximum concurrent WebSocket clients per ws-hub process. | `10000` |
| `WS_UPGRADE_RATE_PER_MINUTE` | WebSocket upgrades allowed per client IP per minute at the Caddy edge and in ws-hub, also the ws-hub burst. Clients behind one NAT share it. | `10` |
| `WS_SEND_BUFFER_SIZE` | Per-client outbound frame buffer size. | `256` |
| `WS_BROADCAST_BUFFER_SIZE` | Broadcast fan-out buffer size. | `4096` |
| `WS_BROADCAST_WORKERS` | Broadcast worker count, capped at 12. | `2 * GOMAXPROCS` (capped) |
| `WS_CLIENT_MSG_RATE_LIMIT` | Per-client inbound message rate, messages per second. | `10` |
| `WS_CLIENT_MSG_BURST` | Per-client inbound message burst size. | `20` |
| `AUTH_CLIENT_MAX_CONNS_PER_HOST` | Maximum pooled connections per host for the ws-hub auth client; non-positive values are ignored. | `20` |
| `RATE_LIMIT_RPS` | Gateway rate limit, requests per second per instance. | `100` |
| `RATE_LIMIT_BURST` | Gateway rate-limit burst size. | `200` |
| `SPIFFE_ENABLED` | Enables SPIFFE identity in the gateway; only the exact value `true` enables it. | `false` |
| `SPIFFE_ENDPOINT_SOCKET` | SPIFFE Workload API socket path. The backend has no default and requires an absolute Unix socket when internal HTTP mTLS is enabled. | `unix:///run/spire/sockets/agent.sock` (Go gateway and ws-hub) |
| `SPIFFE_TRUST_DOMAIN` | SPIFFE trust domain. | `university.ecosystem` |
| `SPIFFE_MY_ID` | SPIFFE ID of the gateway workload. | `spiffe://university.ecosystem/ns/default/sa/gateway` |
| `FP_JWT_SECRET` | file-processor JWT verification secret (`_FILE` supported); startup requires this, an RSA public key or a JWKS URL. | Unset |
| `FP_MINIO_ACCESS_KEY` | file-processor MinIO access key (`_FILE` supported); startup requires a nonempty value. | Bundled development credential in `configureViper` |
| `FP_MINIO_SECRET_KEY` | file-processor MinIO secret key (`_FILE` supported); startup requires a nonempty value. | Bundled development credential in `configureViper` |
| `FP_NATS_URL` | file-processor NATS URL (`_FILE` supported). | `nats://nats:4222` |
| `FP_PROCESSING_CAPABILITY_SECRET` | file-processor secret that verifies processing capabilities (`_FILE` supported); validated in staging and production. | Unset |
| `FP_REVOCATION_REDIS_URL` | file-processor revocation Redis URL (`_FILE` supported). | Unset |
| `FP_SCHEMA_PATH` | Path to a GraphQL schema file that replaces the bundled `schema.graphql`. | Unset (bundled schema) |
| `FP_GRPC_PORT` | file-processor gRPC listen port. | `50051` |
| `FP_GRAPHQL_PORT` | file-processor GraphQL listen port. | `8080` |
| `FP_TEMPORAL_HOST` | Temporal server address. | `temporal:7233` |
| `FP_TEMPORAL_TLS_DISABLED` | Disables TLS for the local Temporal connection; staging and production require `false`. | `true` |
| `FP_TEMPORAL_API_KEY_FILE` | Path to the Temporal service token file. | Unset |
| `FP_MINIO_BUCKET` | S3-compatible storage bucket. | `uploads` |
| `FP_MINIO_ENDPOINT` | S3-compatible storage endpoint. | `minio:9000` |
| `FP_MINIO_SECURE` | Enables TLS to S3-compatible storage; staging and production require `true`. | `false` |
| `FP_JWT_AUDIENCE` | JWT audience accepted by the file-processor. | `university-ecosystem-api` |
| `FP_JWT_ISSUER` | JWT issuer accepted by the file-processor. | `university-ecosystem` |
| `FP_JWKS_URL` | Backend JWKS endpoint. HTTPS is required when internal HTTP mTLS is enabled. | Unset |
| `FP_JWKS_REFRESH_INTERVAL` | JWKS refresh interval in seconds; nonpositive values fall back to the default. | `300` |
| `FP_JWT_ACTIVE_KID` | Key identifier for the static PEM fallback. | `primary` |
| `FP_RSA_PUBLIC_KEY_PEM` | Inline RSA public key for JWT verification. | Unset |
| `FP_RSA_PUBLIC_KEY_FILE` | Path to an RSA public key for JWT verification. | Unset |
| `FP_SENTRY_DSN` | Sentry DSN for the file-processor. | Unset |
| `FP_ENVIRONMENT` | Runtime mode: development, test, testing, staging or production. | `development` |
| `FP_OTLP_ENDPOINT` | OpenTelemetry collector gRPC endpoint. | `tempo:4317` |
| `FP_OTLP_INSECURE` | Disables TLS for the OpenTelemetry exporter; staging and production require `false`. | `true` |
| `FP_SPIFFE_ENABLED` | Enables SPIFFE identity on the gRPC listener. | `false` |
| `FP_SPIFFE_ENDPOINT_SOCKET` | SPIFFE Workload API socket path. | `unix:///run/spire/sockets/agent.sock` |
| `FP_SPIFFE_TRUST_DOMAIN` | SPIFFE trust domain. | `university.ecosystem` |
| `FP_SPIFFE_MY_ID` | SPIFFE identity of the file-processor. | `spiffe://university.ecosystem/ns/default/sa/file-processor` |
| `FP_ALLOWED_CLIENT_SPIFFE_IDS` | Exact SPIFFE client identities permitted by the gRPC listener. | `spiffe://university.ecosystem/ns/default/sa/gateway` |
| `FP_INTERNAL_HTTP_MTLS_ENABLED` | Enables SPIFFE mTLS for HTTP requests to the backend, independently of the gRPC listener. | `false` |
| `FP_BACKEND_SPIFFE_ID` | Exact backend identity required when internal HTTP mTLS is enabled. | Unset |
| `FP_GRPC_TLS_CERT_FILE` | Server certificate for conventional gRPC mTLS; required in staging/production when SPIFFE is disabled. | Unset |
| `FP_GRPC_TLS_KEY_FILE` | Server key for conventional gRPC mTLS; required in staging/production when SPIFFE is disabled. | Unset |
| `FP_GRPC_CLIENT_CA_FILE` | Client CA for conventional gRPC mTLS; required in staging/production when SPIFFE is disabled. | Unset |
| `FP_GRPC_ALLOWED_CLIENT_URIS` | Exact client URI SAN allowlist for conventional gRPC mTLS; required in staging/production when SPIFFE is disabled. | Empty |
