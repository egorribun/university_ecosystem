# Security Policy

## Supported Versions
We actively maintain and provide security updates for the latest released version of this project. Older versions may no longer receive security fixes, so upgrading to the most recent release is strongly recommended.

## Reporting a Vulnerability
If you discover a vulnerability, please report it privately so we can address it promptly. We aim to acknowledge new reports within 24 hours for Critical vulnerabilities and 48 hours for High vulnerabilities.

---

## 🔒 Password Hashing & Authentication Architecture

- **Algorithm**: Password hashing relies **exclusively on Argon2id** (Passlib parameters: Time: 3, Memory: 64 MB, Parallelism: 4).
- **Legacy Verification Removed**: Bcrypt verification has been completely removed (TD-21-04). All accounts use Argon2id.
- **Argon2 Concurrency Cap**: Argon2 hashing concurrency is capped at 4 concurrent hashing tasks per worker process to cap peak memory allocation at 128 MiB (PERF-24-04).
- **Hardware & Passkey MFA**: Native support for **WebAuthn / FIDO2** (Passkeys) alongside TOTP.
- **Pwned Password Checks**: SHA-1 is used *exclusively* for the [Have I Been Pwned API](https://haveibeenpwned.com/API/v3#PwnedPasswords) k-anonymity check. Only the first 5 characters of the hash are transmitted; the full hash is never stored.

---

## 🔐 Zero-Trust ReBAC & Feature Flags

- **Relationship-Based Access Control (ReBAC)**: Granular permission management is powered by **SpiceDB** (Zanzibar-inspired architecture defined in `schema.zed`).
- **SpiceDB Watch Stream**: Real-time permission changes are monitored via `SpiceDB Watch API` (`app/core/spicedb_watch.py`) to trigger immediate cache invalidations and WebSocket session revocations.
- **Feature Flags**: Dynamic feature flags managed via **OpenFeature** + **flagd** (`app/core/feature_flags.py`).

---

## 🛡️ Microservices & Network Security

- **JWKS Key Rotation & Hot Pre-Warming**:
  - Go Gateway executes `StartJWKSRefresher` for background polling and atomic key swaps (MOD-W17-03).
  - Go `ws-hub` subscribes to `keys.rotated` NATS subject for instant JWKS pre-warming (RZ-21-05).
- **Rate Limiting & Circuit Breakers**:
  - `RedisCircuitBreaker` in `app/core/ratelimit/circuit_breaker.py` operates a 3-state machine with exponential backoff (PERF-30-01).
  - Go Gateway provides 2-tier rate limiting fallback (3 req/60s per instance on double Redis+memory failure, failing closed with 503).
- **WebSocket Ingress Protection (`ws-hub`)**:
  - Oversized messages (>60 KB) are rejected at ingress and send a `message_too_large` error frame before fan-out (RZ-23-05, RZ-31-02).
  - Pre-checks `maxClients` in `HandleWebSocket` prior to HTTP upgrade (TD-31-05).
  - Message types are strictly validated at boundary via `allowedMessageTypes` map (MOD-27-02).
- **File Processor Path Traversal Guards**:
  - `sourceKey` and `destKey` path traversal inputs are rejected at gRPC boundary with length capped to 1024 bytes (RZ-26-04, RZ-27-04).
  - GraphQL depth limit (10) and query timeout (30s) enforced (RZ-24-05).

---

## 🌐 CSRF, SSRF & Header Security

- **CSRF Nonce Timing Uniformity**: `secrets.token_hex(16)` is always executed to normalize timing (RZ-27-06), and anonymous nonces are validated via compiled regex `_ANON_NONCE_RE` (RZ-28-02).
- **SSRF Protection**: `validate_url_not_internal()` blocks internal IP ranges and unauthorized internal domain callbacks (`app/core/ssrf.py`).
- **HTTP Security Headers**:
  - `Strict-Transport-Security: max-age=31536000; includeSubDomains; preload`
  - `Content-Security-Policy`: strict per-response nonces (`nonce-...`), framing disabled (`frame-ancestors 'none'`).
  - `Cross-Origin-Opener-Policy: same-origin` and `Cross-Origin-Embedder-Policy: require-corp`.
- **Valkey / Redis Eviction Policy**: Configured to `volatile-lru` (RZ-21-02) ensuring un-expiring security tokens are never evicted unexpectedly.

---

## 📊 PII Redaction & Audit Logging

- **PII Redaction**: All log events pass through `_redact_pii` structlog processor (`app/core/logging.py`) stripping emails and phone numbers.
- **Authentication Audit Trail**: Authentication events emit structured JSON payloads (`event`, `user_id`, `ip`, `request_id`). Sensitive credentials (passwords, tokens) are strictly excluded.
- **Sanitized Static Storage**: `StaticFSStorage._validate_resolved_path()` verifies `is_relative_to(base_dir)` and rejects symlinks (RZ-30-02).

---

## 🚨 Dependency Audit & Vulnerability Reporting

- **Automated Dependency Audits**: CI runs `npm audit` on `frontend/package-lock.json`, `pip audit` on Python packages, and `govulncheck` on Go services.
- **Automated Scanners**: Pre-commit and CI pipelines run **Semgrep**, **Trivy**, **Bandit**, and **Gitleaks** with `.secrets.baseline` integrity checks.
- **Reporting Vulnerabilities**: Submit a GitHub Security Advisory via the **Security** tab or contact `security@university.example.com`.

### Response SLA (MOD-W8-03)

| Severity | Acknowledgement | Triage | Fix |
|:---|:---:|:---:|:---:|
| **Critical** | 24 hours | 48 hours | 7 days |
| **High** | 48 hours | 5 days | 30 days |
| **Medium** | 5 days | 14 days | 90 days |
| **Low** | 5 days | 30 days | Best-effort |

---

<div align="center">
  © 2026 University Ecosystem Security Team • All Rights Reserved.
</div>
