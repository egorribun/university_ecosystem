# Configuration Reference

This document describes the operator-facing environment variables used by the
University Ecosystem backend. Defaults in this document are the runtime
`Settings` defaults; `.env.example` is an explicit local profile and may set a
different value intentionally. Values supplied through `*_FILE` secret mounts
take precedence over the corresponding plaintext variable.

## 🔴 Required Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `DATABASE_URL` | PostgreSQL connection string | - |
| `SECRET_KEY` | Primary JWT signing secret (min 32 chars) | - |
| `AUDIT_LOG_SECRET` | Audit log signing secret (min 32 chars) | - |
| `INTERNAL_HMAC_SECRET` | Internal gateway signature key (Required in production) | - |
| `TOKEN_HMAC_SECRET` | Dedicated HMAC key for password-reset and email-change tokens (min 32 bytes; required in staging/production) | - |

---

## 💾 Database

| Variable | Description | Default |
|----------|-------------|---------|
| `DATABASE_URL` | `postgresql+asyncpg://user:pass@host/db` | Required |
| `DATABASE_POOL_SIZE` | Base SQLAlchemy pool size; defaults to `2 * cgroup-aware CPU count + 1` (CPU quota capped at 32) | Formula |
| `DATABASE_MAX_OVERFLOW` | Additional connections above the base pool; defaults to `4 * cgroup-aware CPU count` | Formula |
| `DATABASE_POOL_TIMEOUT` | Connection timeout (seconds) | `30.0` |
| `DATABASE_POOL_RECYCLE` | Recycle connections after (seconds) | `540` |
| `DATABASE_STATEMENT_CACHE_SIZE` | asyncpg statement cache (0=PgBouncer) | `0` |
| `AUTO_CREATE_SCHEMA` | Auto-create DB tables (development/test only; otherwise migrations are required) | `true` in development/test, `false` otherwise |
| `SLOW_QUERY_LOGGING_ENABLED` | Enable slow query logging | `true` |
| `SLOW_QUERY_THRESHOLD_MS` | Threshold for slow query alerts | `500.0` |
| `SLOW_QUERY_EXPLAIN_ENABLED` | Include `EXPLAIN` details for slow queries | `false` |

---

## 🔒 Authentication & Security

| Variable | Description | Default |
|----------|-------------|---------|
| `SECRET_KEY` | Primary JWT signing secret | Required |
| `ALGORITHM` | JWT algorithm; `HS256` is permitted only for local development/testing | `RS256` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Token TTL | `60` |
| `MAX_SESSIONS_PER_USER` | Concurrent sessions (0=unlimited) | `5` |
| `AUTH_LOCKOUT_THRESHOLDS` | Lockout rules `attempts:seconds` | `5:30,8:300,10:3600` |
| `CSRF_HMAC_SECRET` | Independent HMAC key for signed CSRF cookies; unsigned fallback is development/testing only | Empty locally; required outside development |
| `INTERNAL_HMAC_SECRET` | Verifies the gateway `X-Internal-Signature` identity assertion (minimum 32 bytes) | Required outside development |
| `AUDIT_LOG_SECRET` | HMAC key for audit log signatures (min 32 chars) | Required |
| `TOKEN_HMAC_SECRET` | Dedicated HMAC key for password-reset and email-change token digests | Required in staging/prod |
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
| `CACHE_BACKEND` | `redis`, `memory`, `none` | `redis` |
| `CACHE_ENABLED` | Enable caching | `true` |
| `CACHE_REDIS_URL` | Redis URL | `redis://127.0.0.1:6379/0` |
| `REVOCATION_REDIS_URL` | Dedicated persistent/noeviction Redis URL for session revocation | Required outside development |
| `NATS_URL` | NATS message bus endpoint | `nats://127.0.0.1:4222` |
| `NATS_AUTH_TOKEN` | NATS authentication token | Empty locally; required in production |
| `RATE_LIMIT_ENABLED` | Enable rate limiting | `true` |
| `RATE_LIMIT_DEFAULT` | Default rate | `200/minute` |
| `RATE_LIMIT_STORAGE_BACKEND` | `memory` or `redis` | `memory` |
| `RATE_LIMIT_STORAGE_URI` | Storage URI when the rate limiter backend is Redis | `memory://` |
| `TRUSTED_PROXIES` | Allowed `X-Forwarded-For` source IPs | Empty |

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

| Variable | Description | Default |
|----------|-------------|---------|
| `STORAGE_BACKEND` | `static`, `local`, `s3`, `minio` | `static` |
| `STORAGE_STATIC_BASE_URL` | Public URL for static files | `/static` |
| `STORAGE_S3_BUCKET` | S3 bucket name | Empty |
| `STORAGE_S3_REGION` | AWS Region | Empty |
| `STORAGE_S3_ENDPOINT_URL` | Custom S3 endpoint (for MinIO) | Empty |
| `EVENT_FILE_SCANNER_ENABLED` | Enable ClamAV virus scanning | `false` |
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
| `ELASTICSEARCH_PASSWORD` | ES password (`_FILE` supported) | Required |
| `WS_HUB_INTERNAL_URL` | ws-hub control API | `http://ws-hub:8081` |
| `WS_HUB_INTERNAL_SECRET` | HMAC for ws-hub cache invalidation | Required |
| `INTERNAL_AUTH_TOKEN` | Token for ws-hub's exact room-participant callback; managed Compose/Helm/K8s deployments derive it from the existing ws-hub secret | Empty in development |
| `IDEMPOTENCY_HMAC_SECRET` | signs idempotency keys | Empty |
| `RUST_OPTIMIZER_URL` | Schedule optimization sidecar | `http://rust-optimizer:8080` |

---

## ⚙️ Background Workers & Retention

### Transactional Outbox

| Variable | Description | Default |
|----------|-------------|---------|
| `OUTBOX_BATCH_SIZE` | Events processed per poll cycle by the active embedded worker | `20` |
| `OUTBOX_POLL_INTERVAL_SECONDS` | Polling interval (seconds) for the active embedded worker | `5.0` |
| `OUTBOX_MAX_RETRIES` | Dispatch attempts before DLQ | `5` |
| `EMBEDDED_OUTBOX_WORKER_ENABLED` | Enable the embedded polling outbox worker | `true` |
| `EMBEDDED_CDC_OUTBOX_WORKER_ENABLED` | Use PostgreSQL logical replication instead of polling. Replaces, never accompanies, the polling worker — both publish the same events. Requires `wal_level=logical`. | `false` |

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

> **Tip**: Secrets can be provided via files using the `_FILE` suffix (e.g., `DATABASE_URL_FILE=/run/secrets/db_url`) to support Docker/Kubernetes secrets securely.
