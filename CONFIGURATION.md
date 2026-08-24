# Configuration Reference

This document describes all environment variables used by the University Ecosystem backend.

## 🔴 Required Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `DATABASE_URL` | PostgreSQL connection string | - |
| `SECRET_KEY` | Primary JWT signing secret (min 32 chars) | - |
| `AUDIT_LOG_SECRET` | Audit log signing secret (min 32 chars) | - |
| `INTERNAL_HMAC_SECRET` | Internal gateway signature key (Required in production) | - |

---

## 💾 Database

| Variable | Description | Default |
|----------|-------------|---------|
| `DATABASE_URL` | `postgresql+asyncpg://user:pass@host/db` | Required |
| `DATABASE_POOL_SIZE` | Connection pool size | `5` |
| `DATABASE_MAX_OVERFLOW` | Max overflow connections | `10` |
| `DATABASE_POOL_TIMEOUT` | Connection timeout (seconds) | `30.0` |
| `DATABASE_POOL_RECYCLE` | Recycle connections after (seconds) | `540` |
| `DATABASE_STATEMENT_CACHE_SIZE` | asyncpg statement cache (0=PgBouncer) | `0` |
| `AUTO_CREATE_SCHEMA` | Auto-create DB tables (dev only) | Auto |
| `SLOW_QUERY_LOGGING_ENABLED` | Enable slow query logging | `true` |
| `SLOW_QUERY_THRESHOLD_MS` | Threshold for slow query alerts | `500.0` |

---

## 🔒 Authentication & Security

| Variable | Description | Default |
|----------|-------------|---------|
| `SECRET_KEY` | Primary JWT signing secret | Required |
| `ALGORITHM` | JWT algorithm | `HS256` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Token TTL | `60` |
| `MAX_SESSIONS_PER_USER` | Concurrent sessions (0=unlimited) | `5` |
| `AUTH_LOCKOUT_THRESHOLDS` | Lockout rules `attempts:seconds` | `5:30,8:300,10:3600` |
| `CSRF_HMAC_SECRET` | Key for signing CSRF tokens | (derived) |
| `INTERNAL_HMAC_SECRET` | Verifies gateway `X-User-ID` headers | Required in Prod |
| `AUDIT_LOG_SECRET` | HMAC key for audit log signatures (min 32 chars) | Required |

### MFA Settings

| Variable | Description | Default |
|----------|-------------|---------|
| `MFA_ENABLED` | Enable MFA | `false` |
| `MFA_TOTP_ISSUER` | TOTP app name | `University Ecosystem` |
| `MFA_CHALLENGE_TTL_SECONDS` | Challenge validity | `300` |
| `MFA_CHALLENGE_MAX_ATTEMPTS` | Max attempts | `5` |
| `TRUSTED_DEVICE_EXPIRE_DAYS` | Remember device period | `30` |

---

## ⚡ Cache & Rate Limiting

| Variable | Description | Default |
|----------|-------------|---------|
| `CACHE_BACKEND` | `redis`, `memory`, `none` | `redis` |
| `CACHE_ENABLED` | Enable caching | `true` |
| `CACHE_REDIS_URL` | Redis URL | `redis://127.0.0.1:6379/0` |
| `RATE_LIMIT_ENABLED` | Enable rate limiting | `true` |
| `RATE_LIMIT_DEFAULT` | Default rate | `100/minute` |
| `RATE_LIMIT_STORAGE_BACKEND` | `memory` or `redis` | `memory` |
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
| `CHAT_MAX_MESSAGE_LENGTH` | Max characters per message | `10000` |

---

## 🏗️ Integrations

| Variable | Description | Default |
|----------|-------------|---------|
| `SPOTIFY_CLIENT_ID` | Spotify Client ID | Empty |
| `SPOTIFY_CLIENT_SECRET` | Spotify Secret (`_FILE` supported) | Empty |
| `SPOTIFY_OAUTH_STATE_SECRET`| Secret for OAuth2 state JWTs | Empty |
| `SPICEDB_ENDPOINT` | SpiceDB gRPC endpoint | `spicedb:50051` |
| `SPICEDB_PRESHARED_KEY` | SpiceDB auth key (`_FILE` supported) | `dev-key` |
| `ELASTICSEARCH_URL` | Search engine endpoint | `http://localhost:9200` |
| `ELASTICSEARCH_PASSWORD` | ES password (`_FILE` supported) | Required |
| `WS_HUB_INTERNAL_URL` | ws-hub control API | `http://ws-hub:8081` |
| `WS_HUB_INTERNAL_SECRET` | HMAC for ws-hub cache invalidation | Required |
| `IDEMPOTENCY_HMAC_SECRET` | signs idempotency keys | Empty |
| `RUST_OPTIMIZER_URL` | Schedule optimization sidecar | `(8080)` |

---

## ⚙️ Background Workers & Retention

### Transactional Outbox

| Variable | Description | Default |
|----------|-------------|---------|
| `OUTBOX_BATCH_SIZE` | Events processed per poll cycle | `50` |
| `OUTBOX_POLL_INTERVAL` | Polling interval (seconds) | `0.1` |
| `OUTBOX_MAX_RETRIES` | Dispatch attempts before DLQ | `5` |

### Data Retention

| Variable | Description | Default |
|----------|-------------|---------|
| `RETENTION_LOGS_DAYS` | Days to keep audit logs | `90` |
| `RETENTION_CHATS_DAYS` | Days to keep archived chats | `365` |

---

## 📧 Notifications (Email/Push)

| Variable | Description | Default |
|----------|-------------|---------|
| `NOTIFY_PROVIDER` | `smtp`, `mailgun`, `ses`, `console` | `smtp` |
| `SMTP_HOST` | SMTP server hostname | `localhost` |
| `SMTP_PORT` | SMTP server port | `1025` |
| `VAPID_PUBLIC_KEY` | VAPID public key for WebPush | Empty |
| `VAPID_PRIVATE_KEY` | VAPID private key for WebPush | Empty |
| `NOTIFICATIONS_RETENTION_DAYS` | Days to keep notification history | `90` |

---

## 🌐 Environment

| Variable | Description | Default |
|----------|-------------|---------|
| `ENVIRONMENT` | `development`, `production`, `testing` | `development` |
| `FRONTEND_ORIGIN` | Primary frontend URL for CORS | `http://localhost:5173` |
| `ENABLE_OTEL` | Enable OpenTelemetry tracing | `true` |
| `LOG_LEVEL` | Logging verbosity | `INFO` |

> **Tip**: Secrets can be provided via files using the `_FILE` suffix (e.g., `DATABASE_URL_FILE=/run/secrets/db_url`) to support Docker/Kubernetes secrets securely.
