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

---

## Key Registry

### Authentication & Session

| Key Pattern | TTL | Owner (write) | Readers | Purpose |
|-------------|-----|---------------|---------|---------|
| `session:{sid}` | JWT expiry | Python `app/auth/redis_session.py` | Python API | Active session data |
| `session:v2:{sid}` | JWT expiry | Python `app/services/auth/redis_session.py` | Python API | Active session data (v2 schema) |
| `revoked:jti:{jti}` | remaining JWT lifetime; safe 24h fallback when the session key is missing or unbounded | Python `app/auth/redis_session.py`, `app/services/auth/redis_session.py` via `app/auth/revocation.py`; irreversible MFA retirement migration `202608250002` | Python API (`app/api/deps/auth.py`, `app/api/ws/auth.py`, `app/services/auth/graphql_token_validator.py`), Go gateway (`middleware/auth.go`), Go ws-hub (`pkg/hub/handlers.go`) | Revocation list for logged-out JWTs and already-upgraded real-time sessions |

**Pub/Sub channels:**

| Channel | Publisher | Subscriber | Payload |
|---------|-----------|------------|---------|
| `session:revocations` | Python (`app/auth/redis_session.py`, `app/services/auth/redis_session.py`); irreversible MFA retirement migration `202608250002` | Go gateway (`middleware/auth.go`), Go ws-hub (`pkg/hub/session_revocation.go`) | `{jti}` — raw JWT ID string |

> **Cross-service invariant (tested in `tests/integration/test_redis_contract.py`):**
> The gateway subscribes to `session:revocations` and derives the revocation key as
> `fmt.Sprintf("revoked:jti:%s", msg.Payload)`.  The Python backend MUST publish the
> raw `jti` (not the session ID) to this channel, and MUST write the revocation record
> under the key `revoked:jti:{jti}` before deleting cached session state. If the
> source session key has TTL `0`, `-1`, or `-2`, the producer MUST use the
> authoritative session expiry or the 24-hour maximum accepted token age. A failed
> tombstone write MUST fail the revoke operation and MUST NOT delete the session key.
> The ws-hub MUST retain the JTI after atomically consuming an upgrade ticket,
> check this key both at upgrade and before every incoming user action, and fail
> closed if the lookup errors. It must also subscribe to this channel and close
> only connections carrying the published JTI; Pub/Sub improves prompt teardown
> but is not an authorization source. This protects already-upgraded WebSocket
> and WebTransport sessions when a notification is missed. Upgrade-ticket JTIs
> must be UUIDs; malformed identities are rejected before a transport is
> accepted, rather than relying on the listener to interpret them. Every producer and consumer MUST use the same
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
>
> The dedicated store disables Redis administrative and server-control commands
> (`ACL`, `CONFIG`, `FLUSH*`, `FUNCTION`, `MIGRATE`, `MODULE`, `MONITOR`,
> `REPLICAOF`/`SLAVEOF`, and `SHUTDOWN`). This is a bounded server-side
> denylist, not per-client ACL isolation: a principal that holds the shared
> write credential can still write arbitrary tombstones. Credential scope and
> rotation therefore remain part of the Kubernetes Secret and workload-identity
> boundary; no component may treat command disabling as authorization. The
> dedicated credential is always
> `revocation-redis-credentials` / `revocation-redis-password`, distinct from
> the ordinary cache `redis-credentials` / `redis-password`. The
> `university-connections` Secret distributes the resulting URL only to the
> backend, migration Job, gateway, and ws-hub. Outbox and notification workers
> receive neither that URL nor NetworkPolicy egress to the store, and their
> explicit process role disables the Python revocation-client capability.

---

### WebSocket Upgrade Tickets

| Key Pattern | TTL | Owner (write) | Readers | Purpose |
|-------------|-----|---------------|---------|---------|
| `ott:ws:{ticket}` | 15s | Python `app/api/ws/ticket.py` | Python WS handler (`app/api/ws/auth.py`), Go ws-hub (`pkg/hub/handlers.go`) | One-time WebSocket upgrade ticket; consumed atomically via GETDEL |

**Value format:** `{user_id}:{jti}:{expires_at_unix_seconds}` — exactly three
non-empty colon-delimited fields. The final field is the floor of the authoritative
`ActiveSession.expires_at` UTC Unix timestamp: a positive signed-int64 value encoded
as ASCII decimal, with no sign, whitespace, leading zeros, fraction, or exponent.
It is never derived from a sliding session-cache TTL.

> **Cross-service invariant (RZ-W14-01, audit 2026-03-23 Wave 14):**
> The `ott:ws:` prefix and this three-field value format are shared between
> Python (issuer) and both WS auth consumers (Python WS handler + Go ws-hub).
> Both consumers perform GETDEL — the first consumer wins; concurrent duplicates
> are rejected (ticket already deleted). Ticket TTL is 15 seconds by default and
> limits when the upgrade can occur. The embedded session expiry independently
> limits the authenticated connection and is checked before accepting the ticket.
> Both consumers reject legacy two-field tickets and invalid or expired cutoffs;
> rollout can therefore require clients with outstanding legacy tickets to request
> a new ticket. No legacy-format fallback is permitted.
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

The MFA client fingerprint (`app/core/fingerprint.py`, HMAC-SHA256 digest) is
not a Redis key: it is stored in PostgreSQL as `mfa_challenges.client_fingerprint`.

---

### ETag Cache

| Key Pattern | TTL | Owner | Readers | Purpose |
|-------------|-----|-------|---------|---------|
There is no separate ETag key. Each cached response entry (`CacheEntry` in
`app/deps/cache.py`) carries the SHA-256 ETag of its serialized payload, and
`app/api/deps/etag.py` answers `If-None-Match` from that entry.

---

### Idempotency (send_message dedup)

| Key Pattern | Value | TTL | Owner | Consumer |
|-------------|-------|-----|-------|----------|
| `idm:msg:{digest}` | `{"status": "pending"}`, then `{"status": "completed", "message_id": "<uuid>"}` | 300s while pending (`SET NX`), 86400s (24h) once completed | Python backend (`app/services/chat/command_service.py`, `_make_idempotency_key`) | Python backend (same module) |

**Field details:**
- `{digest}`: HMAC-BLAKE2b of `{chat_id}:{user_id}:{Idempotency-Key}` keyed with `IDEMPOTENCY_HMAC_SECRET`; plain BLAKE2b (16-byte digest) when the secret is empty. Neither the chat, the user nor the raw header value is recoverable from the key.

**Behaviour on cache hit:** A completed entry stores only the message ID; the backend re-reads the message from the database and returns it instead of sending a duplicate. Message content never sits in Redis.

> **Security note:** Binding `chat_id` and `user_id` into the digest prevents user A from replaying user B's idempotent request.

---

### Presence

| Key Pattern | Value | TTL | Owner | Consumer |
|-------------|-------|-----|-------|----------|
| `v{N}:user:{user_id}:presence_audience` | JSON list of user UUIDs | 3600s | Python `app/api/ws/presence.py` (`_get_presence_audience`, via the tiered cache and `versioned_key`) | Python (same module); invalidated by `invalidate_presence_audience_cache` |

**Constraints:**
- The audience is resolved from chat participants in PostgreSQL and capped at 500 users (`ChatRepository._PRESENCE_AUDIENCE_LIMIT`).
- A bounded in-process cache (30 s TTL) shields the database when the shared cache is disabled or empty.
- The optional Redis Pub/Sub bridge (`PRESENCE_PUBSUB_ENABLED`, channel `PRESENCE_PUBSUB_CHANNEL`, default `presence_updates`) only fans presence events out between backend replicas.

> Presence data is advisory — authorization always goes through SpiceDB.

---

## Change Log

| Date | Author | Change |
|------|--------|--------|
| 2026-03-23 | Wave 14 audit | Initial document created (MOD-W14-04) |
| 2026-03-23 | Wave 15 audit | Added Idempotency and Presence key contracts (TD-W15-05) |
| 2026-09-29 | Documentation audit | Aligned the Idempotency, Presence, ETag and MFA fingerprint entries with the implementation |
