# Configuration Reference

This document describes all environment variables used by the University Ecosystem backend.

## 🔴 Required Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `DATABASE_URL` | PostgreSQL connection string | - |
| `SECRET_KEY` | JWT signing secret (min 32 chars) | - |
| `AUDIT_LOG_SECRET` | Audit log signing secret (min 32 chars) | - |

---

## Database

| Variable | Description | Default |
|----------|-------------|---------|
| `DATABASE_URL` | `postgresql+asyncpg://user:pass@host/db` | Required |
| `DATABASE_POOL_SIZE` | Connection pool size | `5` |
| `DATABASE_MAX_OVERFLOW` | Max overflow connections | `10` |
| `DATABASE_POOL_TIMEOUT` | Connection timeout (seconds) | `30.0` |
| `DATABASE_POOL_RECYCLE` | Recycle connections after (seconds) | `1800` |
| `AUTO_CREATE_SCHEMA` | Auto-create DB tables (dev only) | Auto |

---

## Authentication & Security

| Variable | Description | Default |
|----------|-------------|---------|
| `SECRET_KEY` | JWT signing secret | Required |
| `AUDIT_LOG_SECRET` | HMAC key for audit log signatures (min 32 chars; comma-separated for rotation) | Required |
| `ALGORITHM` | JWT algorithm | `HS256` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Token TTL | `60` |
| `MAX_SESSIONS_PER_USER` | Concurrent sessions (0=unlimited) | `5` |
| `AUTH_LOCKOUT_THRESHOLDS` | Lockout rules `attempts:seconds` | `5:30,8:300,10:3600` |

### MFA Settings

| Variable | Description | Default |
|----------|-------------|---------|
| `MFA_ENABLED` | Enable MFA | `false` |
| `MFA_TOTP_ISSUER` | TOTP app name | `University Ecosystem` |
| `MFA_CHALLENGE_TTL_SECONDS` | Challenge validity | `300` |
| `MFA_CHALLENGE_MAX_ATTEMPTS` | Max attempts | `5` |
| `TRUSTED_DEVICE_EXPIRE_DAYS` | Remember device period | `30` |

---

## Cache & Redis

| Variable | Description | Default |
|----------|-------------|---------|
| `CACHE_BACKEND` | `redis`, `memory`, `none` | `redis` |
| `CACHE_ENABLED` | Enable caching | `true` |
| `CACHE_REDIS_URL` | Redis URL | `redis://127.0.0.1:6379/0` |
| `CACHE_DEFAULT_TTL_SECONDS` | Default cache TTL | `300` |
| `STATS_CACHE_TTL_SECONDS` | Stats cache TTL | `180` |

---

## Rate Limiting

| Variable | Description | Default |
|----------|-------------|---------|
| `RATE_LIMIT_ENABLED` | Enable rate limiting | `true` |
| `RATE_LIMIT_DEFAULT` | Default rate | `100/minute` |
| `RATE_LIMIT_SENSITIVE` | Sensitive endpoints rate | `5/minute` |
| `RATE_LIMIT_STORAGE_BACKEND` | `memory` or `redis` | `memory` |

---

## Security Headers

| Variable | Description | Default |
|----------|-------------|---------|
| `SECURITY_CSP` | Custom CSP policy | Built-in |
| `SECURITY_CSP_REPORT_URI` | CSP violation report URL | Empty |
| `SECURITY_HSTS_ENABLED` | Enable HSTS | `true` |
| `SECURITY_HSTS_MAX_AGE` | HSTS max-age | `31536000` |
| `SECURITY_X_FRAME_OPTIONS` | X-Frame-Options | `DENY` |
| `ENABLE_COOP` | Cross-Origin-Opener-Policy | `false` |
| `ENABLE_COEP` | Cross-Origin-Embedder-Policy | `false` |

---

## Storage

| Variable | Description | Default |
|----------|-------------|---------|
| `STORAGE_BACKEND` | `static`, `s3`, `minio` | `static` |
| `STORAGE_STATIC_BASE_URL` | Static files URL | `/static` |
| `STORAGE_S3_BUCKET` | S3 bucket name | Empty |
| `STORAGE_S3_REGION` | S3 region | Empty |
| `STORAGE_S3_ACCESS_KEY_ID` | S3 access key | Empty |
| `STORAGE_S3_SECRET_ACCESS_KEY` | S3 secret | Empty |

---

## Observability

| Variable | Description | Default |
|----------|-------------|---------|
| `ENABLE_OTEL` | Enable OpenTelemetry | `true` |
| `OTEL_SERVICE_NAME` | Service name | `university-ecosystem` |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | OTLP endpoint | `http://localhost:4317` |
| `SENTRY_DSN` | Sentry DSN | Empty |
| `LOG_LEVEL` | Log level | `INFO` |

---

## Push Notifications

| Variable | Description | Default |
|----------|-------------|---------|
| `VAPID_PUBLIC_KEY` | VAPID public key | Empty |
| `VAPID_PRIVATE_KEY` | VAPID private key | Empty |
| `VAPID_SUBJECT` | VAPID subject (`mailto:` or URL) | Empty |
| `NOTIFICATIONS_RETENTION_DAYS` | Keep notifications | `90` |

---

## File Scanning

| Variable | Description | Default |
|----------|-------------|---------|
| `EVENT_FILE_SCANNER_ENABLED` | Enable malware scanning | `false` |
| `EVENT_FILE_SCANNER_BACKEND` | `clamd` | `clamd` |
| `EVENT_FILE_SCANNER_HOST` | ClamAV host | `127.0.0.1` |
| `EVENT_FILE_SCANNER_PORT` | ClamAV port | `3310` |

---

## Frontend & CORS

| Variable | Description | Default |
|----------|-------------|---------|
| `FRONTEND_ORIGIN` | Primary frontend URL | `http://localhost:5173` |
| `FRONTEND_ORIGINS` | Additional origins (comma-separated) | Empty |
| `CORS_ALLOW_CREDENTIALS` | Allow cookies | `true` |
| `CORS_ALLOW_METHODS` | Allowed HTTP methods | GET,POST,PUT,PATCH,DELETE,OPTIONS |

---

## Environment

| Variable | Description | Default |
|----------|-------------|---------|
| `ENVIRONMENT` | `development`, `production`, `testing` | `development` |

> **Tip**: In development mode (`ENVIRONMENT=development`), missing required variables will use fallback values.
