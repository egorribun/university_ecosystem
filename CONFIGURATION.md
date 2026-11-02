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
| `DATABASE_URL` | `postgresql+asyncpg://ue_app:pass@host/db`: runtime login for the backend and outbox worker. Use a `NOSUPERUSER NOBYPASSRLS` role with DML grants only and no `ue_rls_bypass` membership, so the tenant policies apply to every request. Never use the bootstrap superuser or `ue_migrator`. | Required |
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

**Database login roles.** `infrastructure/postgres-roles/bootstrap-app-roles.sql` provisions the Compose roles on every start, before migrations. `ue_app` (backend, outbox worker) and `ue_worker` (notifications worker) are `NOSUPERUSER NOBYPASSRLS` with DML grants only. `ue_migrator` owns the schema and runs Alembic only; it is a superuser because the baseline creates the non-trusted pgvector extension and comments on it. Membership in `ue_rls_bypass` is the only grant that lifts the tenant policies for query access, and a session GUC never lifts them. Maintenance jobs need different authority: `pg_dump` runs with `row_security=off`, so a dump login needs the `BYPASSRLS` attribute, because membership does not satisfy it. Provision a SELECT-only `BYPASSRLS` login for `backup-database-url`. The `migrate_passwords` inventory fails closed unless its login is a `ue_rls_bypass` member.

---

## 🔒 Authentication & Security

| Variable | Description | Default |
|----------|-------------|---------|
| `SECRET_KEY` | Primary JWT signing secret | Required |
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
| `REVOCATION_REDIS_URL` | Dedicated persistent/noeviction Redis URL for session revocation | Required outside development |
| `NATS_URL` | NATS message bus endpoint | `nats://127.0.0.1:4222` |
| `NATS_AUTH_TOKEN` | NATS authentication token | Empty locally; required in production |
| `NATS_TASK_MAX_DELIVERIES` | Delivery attempts of a background task before it is parked in the dead-letter queue (`/admin/dlq`) | `5` |
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
| `OTEL_EXPORTER_OTLP_ENDPOINT` | OpenTelemetry collector endpoint | `http://localhost:4317` |
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
`Settings` (for example `os.environ` in `app/core/nats_broker.py`, the Go services
and the Temporal entrypoint) are documented in their thematic sections and are not
part of this inventory.

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
| `SECURITY_CONNECT_SRC_EXTRA` | Security connect src extra. Defined in `app/core/config/mixins/csp_settings.py`. | `https://api.spotify.com,https://fcm.googleapis.com,https://fcmregistrations.googleapis.com,https://*.push.services.mozilla.com,https://updates.push.services.mozilla.com,https://*.push.apple.com` |
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
| `SENTRY_TRACES_SAMPLE_RATE` | Sentry traces sample rate. Defined in `app/core/config/observability.py`. | `0.0` |
| `SERVICE_VERSION` | Service version. Defined in `app/core/config/observability.py`. | Empty |

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
| `STATIC_DIR` | Static dir. Defined in `app/core/config/storage.py`. | `app/static` |
| `STORAGE_S3_ACCESS_KEY_ID` | Storage S3 access key ID. Defined in `app/core/config/storage.py`. | Empty |
| `STORAGE_S3_BASE_URL` | Storage S3 base URL. Defined in `app/core/config/storage.py`. | Empty |
| `STORAGE_S3_SECRET_ACCESS_KEY` | Storage S3 secret access key. Defined in `app/core/config/storage.py`. | Empty |
