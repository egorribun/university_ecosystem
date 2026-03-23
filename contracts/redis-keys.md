# Redis Key Contracts

This document is the authoritative registry for **every Redis key pattern** used
across the university-ecosystem services.  It serves as an explicit contract
between Python backend, Go gateway, Go ws-hub, and any future service that
shares the Redis instance.

> **Rule:** Before adding a new Redis key pattern in any service, add it here
> first (PR required).  Before deleting a key pattern, confirm no other service
> reads or writes it.

---

## Format Conventions

| Notation         | Meaning                              |
|------------------|--------------------------------------|
| `{jti}`          | JWT ID (UUID v4, 36 chars)           |
| `{sid}`          | Session ID (UUID v7)                 |
| `{user_id}`      | User UUID                            |
| `{chat_id}`      | Chat/Room UUID                       |
| `{key}`          | Hashed composite identifier (SHA256) |
| `{challenge_type}` | MFA challenge type string          |
| `{method}`       | Auth method string                   |
| `{token}`        | Short-lived challenge token          |

---

## Key Registry

### Authentication & Session

| Key Pattern | TTL | Owner (write) | Readers | Purpose |
|-------------|-----|---------------|---------|---------|
| `session:{sid}` | JWT expiry | Python `app/auth/redis_session.py` | Python API | Active session data |
| `session:v2:{sid}` | JWT expiry | Python `app/services/auth/redis_session.py` | Python API | Active session data (v2 schema) |
| `revoked:jti:{jti}` | remaining JWT lifetime | Python `app/auth/redis_session.py`, `app/services/auth/redis_session.py` | Python API (`app/api/deps/auth.py`, `app/api/ws/auth.py`, `app/services/auth/graphql_token_validator.py`), Go gateway (`middleware/auth.go`) | Revocation list for logged-out JWTs |

**Pub/Sub channels:**

| Channel | Publisher | Subscriber | Payload |
|---------|-----------|------------|---------|
| `session:revocations` | Python (`app/auth/redis_session.py:78`) | Go gateway (`middleware/auth.go:141`) | `{jti}` — raw JWT ID string |

> **Cross-service invariant (tested in `tests/integration/test_redis_contract.py`):**
> The gateway subscribes to `session:revocations` and derives the revocation key as
> `fmt.Sprintf("revoked:jti:%s", msg.Payload)`.  The Python backend MUST publish the
> raw `jti` (not the session ID) to this channel, and MUST write the revocation record
> under the key `revoked:jti:{jti}`.

---

### WebSocket Upgrade Tickets

| Key Pattern | TTL | Owner (write) | Readers | Purpose |
|-------------|-----|---------------|---------|---------|
| `ott:ws:{ticket}` | 15s | Python `app/api/ws/ticket.py` | Python WS handler (`app/api/ws/auth.py`), Go ws-hub (`pkg/hub/handlers.go`) | One-time WebSocket upgrade ticket; consumed atomically via GETDEL |

**Value format:** `{user_id}:{jti}` — colon-joined UUID strings (no colons in UUIDs).

> **Cross-service invariant (RZ-W14-01, audit 2026-03-23 Wave 14):**
> The `ott:ws:` prefix and the `{user_id}:{jti}` value format are shared between
> Python (issuer) and both WS auth consumers (Python WS handler + Go ws-hub).
> Both consumers perform GETDEL — the first consumer wins; concurrent duplicates
> are silently rejected (ticket already deleted).  Ticket TTL is 15 seconds.

---

### Rate Limiting

| Key Pattern | TTL | Owner | Readers | Purpose |
|-------------|-----|-------|---------|---------|
| `rate-limit:{key}` | `window_ms` | Python `app/core/ratelimit/strategies/redis.py` | Python (same module) | Sliding-window sorted-set rate limit |

---

### MFA / Fingerprint

| Key Pattern | TTL | Owner | Readers | Purpose |
|-------------|-----|-------|---------|---------|
| `mfa:{challenge_type}:{user_id}` | challenge TTL | Python `app/auth/mfa/challenge.py` | Python MFA handlers | Active MFA challenge tracking |
| `mfa:fp:{token}` | challenge remaining TTL | Python `app/core/fingerprint.py` | Python fingerprint validator | Device fingerprint for MFA step-up |

---

### ETag Cache

| Key Pattern | TTL | Owner | Readers | Purpose |
|-------------|-----|-------|---------|---------|
| `ue:etag-cache:v{VERSION}:{path}` | 30s debounce flush | Python ETag service | Frontend (via HTTP ETag header) | Per-path ETag cache with schema version |

---

## Change Log

| Date | Author | Change |
|------|--------|--------|
| 2026-03-23 | Wave 14 audit | Initial document created (MOD-W14-04) |
