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
| `revoked:jti:{jti}` | remaining JWT lifetime; safe 24h fallback when the session key is missing or unbounded | Python `app/auth/redis_session.py`, `app/services/auth/redis_session.py` via `app/auth/revocation.py` | Python API (`app/api/deps/auth.py`, `app/api/ws/auth.py`, `app/services/auth/graphql_token_validator.py`), Go gateway (`middleware/auth.go`), Go ws-hub (`pkg/hub/handlers.go`) | Revocation list for logged-out JWTs |

**Pub/Sub channels:**

| Channel | Publisher | Subscriber | Payload |
|---------|-----------|------------|---------|
| `session:revocations` | Python (`app/auth/redis_session.py`, `app/services/auth/redis_session.py`) | Go gateway (`middleware/auth.go`) | `{jti}` — raw JWT ID string |

> **Cross-service invariant (tested in `tests/integration/test_redis_contract.py`):**
> The gateway subscribes to `session:revocations` and derives the revocation key as
> `fmt.Sprintf("revoked:jti:%s", msg.Payload)`.  The Python backend MUST publish the
> raw `jti` (not the session ID) to this channel, and MUST write the revocation record
> under the key `revoked:jti:{jti}` before deleting cached session state. If the
> source session key has TTL `0`, `-1`, or `-2`, the producer MUST use the
> authoritative session expiry or the 24-hour maximum accepted token age. A failed
> tombstone write MUST fail the revoke operation and MUST NOT delete the session key.
> The ws-hub MUST check this key after atomically consuming an upgrade ticket
> and fail closed if the lookup errors, so a pre-logout ticket is rejected once
> the revocation record exists. Every producer and consumer MUST use the same
> dedicated `REVOCATION_REDIS_URL`. The shipped Compose and Helm topology
> provisions this as a persistent, AOF-backed Redis/Valkey process with
> `maxmemory-policy noeviction`. Backend `CACHE_REDIS_URL` and gateway/ws-hub
> `REDIS_URL` remain cache/rate-limit transports and MUST NOT be reused for
> revocation checks. Logical DB separation inside an eviction-enabled cache is
> insufficient because Redis eviction policy is process-wide. The gateway L1
> cache stores only positive revocation tombstones; a negative `EXISTS` result is
> never cached. This guarantees that a Redis or Pub/Sub partition forces a live
> lookup and fail-closed authentication instead of reusing stale "not revoked"
> state. The Pub/Sub listener also health-checks Redis and purges L1 before
> reconnecting after a detected outage.

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
> Tenant identity is intentionally excluded: a request header is not proof of
> tenant membership. A future tenant-aware ticket format requires server-side
> authorization plus an atomic versioned contract update in both consumers.

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

### Idempotency (send_message dedup)

| Key Pattern | Value | TTL | Owner | Consumer |
|-------------|-------|-----|-------|----------|
| `idempotency:{method}:{user_id}:{key_hash}` | `{response_body_json}` | 86400s (24h) | Python backend (`app/core/middleware.py`) | Python backend (same module) |

**Field details:**
- `{method}`: HTTP method + path, e.g., `POST:/api/v1/messages`
- `{user_id}`: User UUID (prevents cross-user replay)
- `{key_hash}`: SHA-256 of the `Idempotency-Key` header value (hex, 64 chars)

**Behaviour on cache hit:** Returns `200 OK` with the cached response body; the request handler is not invoked a second time.

> **Security note (Wave 4):** The `user_id` component prevents user A from replaying user B's idempotent request. The SHA-256 hash avoids storing the raw header value in Redis.

---

### Presence

| Key Pattern | Value | TTL | Owner | Consumer |
|-------------|-------|-----|-------|----------|
| `presence:{chat_id}` | Sorted Set: `{user_id}` → `last_seen_unix_ms` | 300s rolling | ws-hub (via NATS event) | Python `app/api/ws/presence.py` (`get_presence_audience`) |

**Constraints:**
- Maximum 500 members per room (`_PRESENCE_AUDIENCE_LIMIT` in `presence.py`).
- TTL is refreshed on each heartbeat; members with stale scores are evicted server-side.

> **Cross-service invariant (Wave 5):** The ws-hub publishes presence events to NATS; the Python backend updates the Sorted Set and enforces the 500-member cap. Presence data is advisory — authorization always goes through SpiceDB.

---

## Change Log

| Date | Author | Change |
|------|--------|--------|
| 2026-03-23 | Wave 14 audit | Initial document created (MOD-W14-04) |
| 2026-03-23 | Wave 15 audit | Added Idempotency and Presence key contracts (TD-W15-05) |
