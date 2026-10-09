# Redis Key Contracts

This document is the authoritative registry for **every Redis key pattern** used
across the university-ecosystem services. It serves as an explicit contract
between the Python backend, Go gateway, Go ws-hub, file processor, and any future
service that shares the Redis instance.

> **Rule:** Before adding a new Redis key pattern in any service, add it here
> first (PR required).  Before deleting a key pattern, confirm no other service
> reads or writes it.

---

## Format Conventions

| Notation         | Meaning                              |
|------------------|--------------------------------------|
| `{jti}`          | JWT ID (UUID v4, 36 chars)           |
| `{user_id}`      | User UUID                            |
| `{chat_id}`      | Chat/Room UUID                       |
| `{key}`          | Hashed composite identifier (SHA256) |
| `{challenge_type}` | MFA challenge type string          |
| `{room_id}`      | Room UUID                            |
| `{nonce}`        | OAuth or processing-capability nonce |
| `{probe_id}`     | Unique health-probe identifier         |
| `{window_minute}`| Unix-minute rate-limit window       |
| `{ip}`           | Request IP used by anonymous GraphQL limits |
| `{identifier}`   | Caller-supplied progressive-delay identity |
| `{prefix}`       | Configured cache or delay namespace |
| `{version}`      | Cache generation/version token      |
| `{locale}`       | Normalized response locale           |
| `{sha256}`       | Lowercase SHA-256 digest             |
| `{caller_key}`   | A registered caller key shape       |
| `{kind}`         | Normalized statistics kind (known values: attendance, grades, participation) |
| `{period_key}`   | Normalized period key; `default` is used when absent  |
| `{min_id}`       | Lower ID in the sorted direct-chat participant pair   |
| `{max_id}`       | Higher ID in the sorted direct-chat participant pair  |

---

## Key Registry

### Authentication & Session

| Key Pattern | TTL | Owner (write) | Readers | Purpose |
|-------------|-----|---------------|---------|---------|
| `session:{jti}` | Remaining supplied session expiry (`expires_at - now`) | Python `app/auth/redis_session.py` | Python API | Active session data keyed by the JWT ID |
| `session:v2:{jti}` | Configured `access_token_expire_minutes * 60` (currently 60 minutes by default); refreshed by `update_last_seen` | Python `app/services/auth/redis_session.py` | Python API | Active session metadata cache (v2 schema), keyed by the JWT ID |
| `revoked:jti:{jti}` | remaining JWT lifetime; safe 24h fallback when the session key is missing or unbounded | Python `app/auth/redis_session.py`, `app/services/auth/redis_session.py` via `app/auth/revocation.py`; irreversible MFA retirement migration `202608250002` | Python API (`app/api/deps/auth.py`, `app/api/ws/auth.py`, `app/services/auth/graphql_token_validator.py`), Go gateway (`middleware/auth.go`), Go ws-hub (`pkg/hub/handlers.go`), Go file processor (`cmd/file-processor/auth.go`) | Revocation list for logged-out JWTs and already-upgraded real-time sessions |

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
> accepted, rather than relying on the listener to interpret them. Every producer
> and consumer MUST use the same dedicated revocation store. Backend, gateway,
> and ws-hub receive it as `REVOCATION_REDIS_URL`; file-processor receives it as
> `FP_REVOCATION_REDIS_URL`. The shipped Compose and Helm topology
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
> backend, migration Job, gateway, ws-hub, and file-processor. Outbox and notification workers
> receive neither that URL nor NetworkPolicy egress to the store, and their
> explicit process role disables the Python revocation-client capability.

### Room Authorization Cache

| Key Pattern | TTL | Owner (write) | Readers / invalidators | Purpose |
|-------------|-----|---------------|------------------------|---------|
| `auth:perms:{user_id}:{room_id}` | 60s (`authCacheTTL`) | Go ws-hub (`services/ws-hub/pkg/hub/auth_client.go`) | Go ws-hub; Python SpiceDB watcher invalidates matching entries (`app/core/spicedb_watch.py`) | Short-lived room authorization result cache; values are `0` or `1` |

---

### Processing Capability Replay Guard

| Key Pattern | TTL | Owner (write) | Readers | Purpose |
|-------------|-----|---------------|---------|---------|
| `file-processor:capability-replay:v1:{sha256}` | Remaining capability lifetime (`expires_at - now`, supplied at runtime) | Go file processor (`services/file-processor/cmd/file-processor/auth.go`) | Go file processor (same module) | Atomic `SET NX` admission keyed by the SHA-256 digest of a one-time processing-capability nonce |

---

### Spotify OAuth State

| Key Pattern | TTL | Owner (write) | Readers | Purpose |
|-------------|-----|---------------|---------|---------|
| `oauth:spotify:{nonce}` | 600s | Python `app/api/spotify.py` authorization flow | Python Spotify callback (`app/api/spotify.py`) | One-time binding between the OAuth state and the initiating user/session |

The flow creates the value with `SET NX` and consumes it with `GETDEL`. It uses
the dedicated revocation Redis client; callback state is single-use.

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

### Chat Creation Lock

| Key Pattern | TTL / Wait | Owner (write) | Readers | Purpose |
|-------------|------------|---------------|---------|---------|
| `chat_init:{min_id}:{max_id}` | 5s lease; acquisition waits up to 4s | Python `app/services/chat/creation_service.py` | Python direct-message creation (`create_chat`) | Distributed lock for creating one direct-message chat for the sorted participant ID pair |

---

### Rate Limiting

| Key Pattern | TTL | Owner | Readers | Purpose |
|-------------|-----|-------|---------|---------|
| `rate-limit:{key}` | `window_ms` | Python `app/core/ratelimit/strategies/redis.py` | Python (same module) | Sliding-window sorted-set rate limit |
| `{key_prefix}:{identifier}` (default `progressive_delay:{identifier}`) | Configured `ttl_seconds` (default 900s); refreshed on each failure | Python `app/core/ratelimit/delay.py` | Python (same tracker) | Progressive failed-attempt delay; prefix and TTL can be configured |
| `rate:user:{user_id}` | On accepted requests, the dependency stores the key with `EX ceil(reset_after)` when positive; reset is derived from configured GCRA rate/burst with a 1-second period. Rejected requests do not write. | Go gateway (`services/gateway/middleware/ratelimit.go`, `redis_rate/v10`) | Go gateway rate limiter | Per-user distributed rate limit |
| `rate:ip:{ip}` | On accepted requests, the dependency stores the key with `EX ceil(reset_after)` when positive; reset is derived from configured GCRA rate/burst with a 1-second period. Rejected requests do not write. | Go gateway (`services/gateway/middleware/ratelimit.go`, `redis_rate/v10`) | Go gateway rate limiter | IP fallback distributed rate limit |

---

### GraphQL Rate Limits

| Key Pattern | TTL | Owner (write) | Readers | Purpose |
|-------------|-----|---------------|---------|---------|
| `gql:token_bucket:{user_id}` | `ttl` argument (current default 3600s) | Python `app/graphql/extensions.py` | Python (same module) | Authenticated GraphQL token bucket; Lua refreshes expiration on each request |
| `gql:token_bucket:ip:{ip}` | `ttl` argument (current default 3600s) | Python `app/graphql/extensions.py` | Python (same module) | Anonymous GraphQL token bucket; Lua refreshes expiration on each request |
| `gql:cost:{user_id}:{window_minute}` | 120s | Python `app/graphql/extensions.py` | Python (same module) | Per-user query-cost counter for a tumbling minute window |

The token-bucket helper accepts a TTL argument; the current GraphQL middleware
uses its 3600-second default. Both limit families fall back to process-local
state when Redis is unavailable.

---

### Security Event Store

| Key Pattern | TTL / Bound | Owner (write) | Readers | Purpose |
|-------------|-------------|---------------|---------|---------|
| `security:suspicious_events` | No key TTL; approximate stream `MAXLEN ~ 50000` | Python `app/services/fraud_detection_service.py` (`FraudDetectionService`, provided by DI) | Python (same service) | Implemented suspicious-session stream; no invocation was found in the reviewed production-source search |
| `security:high_events:{user_id}` | 3600s after each high-severity write | Python `app/services/fraud_detection_service.py` | Python (same service) | Per-user sorted set for recent high-severity event counts |

**ADR-007 TTL status:** Decision 4 requires an explicit expiry for every key and
architecture review for persistent keys. `MAXLEN ~ 50000` bounds stream length;
it does not expire the key. The current stream writer has no TTL and no ADR-007
review or approved exception was found in the reviewed records. Treat this as an
open policy gap; this registry entry does not grant an exception.

---

### MFA / Fingerprint

MFA challenge issuance passes `mfa:{challenge_type}:{user_id}` as an identifier
to the shared Redis sliding-window strategy. The concrete Redis key is
`rate-limit:mfa:{challenge_type}:{user_id}`, covered by `rate-limit:{key}` above.
Challenge records are `MfaChallenge` PostgreSQL rows; the flow does not use a
separate Redis challenge-state key.

The MFA client fingerprint (`app/core/fingerprint.py`, HMAC-SHA256 digest) is
not a Redis key: it is stored in PostgreSQL as `mfa_challenges.client_fingerprint`.

---

### Statistics Cache

| Key Pattern | TTL | Owner (write) | Readers | Purpose |
|-------------|-----|---------------|---------|---------|
| `stats:{kind}:{user_id}:{period_key}` | Configured `stats_cache_ttl_seconds` (default 180s; `set_cached_stats` accepts a per-call override) | Python `app/services/stats_cache.py` | Python analytics service (`app/services/user/analytics_service.py`), CQRS query (`app/cqrs/queries.py`), cache warmup (`app/services/cache_warmup.py`) | Per-user attendance, grade, or participation statistics by normalized period |

---

### ETag and Cached API Responses

There is no separate ETag key. Each cached response entry (`CacheEntry` in
`app/deps/cache.py`) carries the SHA-256 ETag of its serialized payload, and
`app/api/deps/etag.py` answers `If-None-Match` from that entry. The cache key
itself is `prefix:{version}:{locale}:{sha256}`, where `{sha256}` hashes the
normalized request parameters.

| Key Pattern | TTL | Owner (write) | Readers | Purpose |
|-------------|-----|---------------|---------|---------|
| `events:list:{version}:{locale}:{sha256}` | Configured `cache_default_ttl_seconds` (default 300s) | Python events list endpoint (`app/api/events.py`) | Python events API | Localized, parameterized event list response |
| `ue:events:my:{version}:{locale}:{sha256}` | Configured `cache_default_ttl_seconds` (default 300s) | Python personal events endpoint (`app/api/events.py`) | Python events API | Authenticated user's event list response; user and tenant context are in the parameter digest |
| `ue:events:detail:{version}:{locale}:{sha256}` | Configured `cache_default_ttl_seconds` (default 300s) | Python event detail endpoint (`app/api/events.py`) | Python events API | Event detail response |
| `news:list:{version}:{locale}:{sha256}` | Configured `cache_default_ttl_seconds` (default 300s) | Python news list endpoint (`app/api/news.py`) | Python news API | Localized, parameterized news list response |
| `ue:news:item:{version}:{locale}:{sha256}` | Configured `cache_default_ttl_seconds` (default 300s) | Python news item endpoint (`app/api/news.py`) | Python news API | News item response |
| `ue:stories:list:{version}:{locale}:{sha256}` | Configured `cache_default_ttl_seconds` (default 300s) | Python stories endpoint (`app/api/stories.py`) | Python stories API | Localized stories response |
| `ue:news:list:{version}:{locale}:{sha256}` | Configured `cache_default_ttl_seconds` (default 300s) | Python cache warmup (`app/services/cache_warmup.py`) | Not consumed by the current news-list endpoint | Startup warmup's news-page entry |
| `ue:events:list:{version}:{locale}:{sha256}` | Configured `cache_default_ttl_seconds` (default 300s) | Python cache warmup (`app/services/cache_warmup.py`) | Not consumed by the current events-list endpoint | Startup warmup's events-page entry |

The warmup and endpoint list prefixes currently differ (`ue:news:list` versus
`news:list`, and `ue:events:list` versus `events:list`). The key builder preserves
the supplied prefix, so these startup entries do not warm those request paths.
This records the current implementation gap; it does not certify cache warmup.

The TTL column records the current configured default, not a fixed invariant;
`cache_default_ttl_seconds` is runtime-configurable. The generator and writers
are `app/api/deps/etag.py` and the endpoint/warmup modules listed above.

---

### Image Proxy Cache

| Key Pattern | TTL | Owner (write) | Readers | Purpose |
|-------------|-----|---------------|---------|---------|
| `image_proxy:{sha256}` | 86400s (24h) | Python `app/services/image_proxy.py` | Python (same service) | Cached transformed image bytes keyed by a digest of source path, width, and format |

---

### Schedule Cache

| Key Pattern | TTL | Owner (write) | Readers | Purpose |
|-------------|-----|---------------|---------|---------|
| `schedule:groups` | `cache_schedule_l2_ttl_s` for repository cache (default 7200s) | Python `app/repositories/schedule_repository.py` | Python schedule repository | Cached schedule group list |
| `schedule:group:{group_id}` | Repository L2 `cache_schedule_l2_ttl_s` (default 7200s); cache warmup uses configured `cache_default_ttl_seconds` (default 300s) | Python `app/repositories/schedule_repository.py`, `app/services/cache_warmup.py` | Python schedule API, repository, and warmup | Schedule rows for one group |

Both TTL settings are runtime-configurable; these defaults describe current
configuration and are not fixed key-contract constants.

---

### Health Probe

| Key Pattern | TTL | Owner (write) | Readers | Purpose |
|-------------|-----|---------------|---------|---------|
| `healthz:{probe_id}` | 5s; invalidated immediately in the probe's `finally` block | Python `app/api/health.py` | Python readiness endpoint (same module) | Temporary cache write/read health probe |

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

The Redis key shape is registered under **Versioned Cache Caller Keys** below.

**Constraints:**
- The audience is resolved from chat participants in PostgreSQL and capped at 500 users (`ChatRepository._PRESENCE_AUDIENCE_LIMIT`).
- A bounded in-process cache (30 s TTL) shields the database when the shared cache is disabled or empty.
- The optional Redis Pub/Sub bridge (`PRESENCE_PUBSUB_ENABLED`, channel `PRESENCE_PUBSUB_CHANNEL`, default `presence_updates`) only fans presence events out between backend replicas.

> Presence data is advisory — authorization always goes through SpiceDB.

---

### Shared Cache Version Keys

| Key Pattern | TTL | Owner (write) | Readers | Purpose |
|-------------|-----|---------------|---------|---------|
| `events:list:version` | No explicit Redis expiration | Python `app/core/cache_versioning.py` (`events_cache_version`) | Python events-list cache callers | Shared invalidation counter for event-list cache entries |
| `news:list:version` | No explicit Redis expiration | Python `app/core/cache_versioning.py` (`news_cache_version`) | Python news-list cache callers | Shared invalidation counter for news-list cache entries |

`CacheVersionManager` forms its Redis counter as `{prefix}:version`; the two
rows above are the current Redis-backed instances. The same module uses a
backend-specific generation entry when the selected cache is not Redis, so that
entry is not a Redis key.

**ADR-007 TTL status:** Both current Redis counters are created with `INCR` or
`SET` and no expiry. Decision 4 requires an explicit expiry for every key and
architecture review for persistent keys. No ADR-007 review or approved exception
was found in the reviewed records. Treat these counters as open policy gaps;
this registry entry does not grant an exception.

### Versioned Cache Caller Keys

| Key Pattern | TTL | Owner (write) | Readers / invalidators | Purpose |
|-------------|-----|---------------|------------------------|---------|
| `v{N}:{caller_key}` | Caller-specific; see registered shapes below | Python `app/deps/cache.py` (`versioned_key`) | Python cache callers | Shared versioned-key namespace; current helper version is `N = 1` |
| `v{N}:user:{user_id}:presence_audience` | 3600s | Python `app/api/ws/presence.py` | Python presence module; invalidated by `invalidate_presence_audience_cache` | Presence audience cache |
| `v{N}:chat:{chat_id}:participants` | 3600s | Python `app/api/ws/connection_manager.py` | Python connection manager; invalidated by `app/api/ws/presence.py` | Cached participant IDs for one chat |

`versioned_key` emits `v{N}:{caller_key}` and the exact current caller shapes
above are registered separately. Register each new caller pattern and its TTL
here before adding it; the generic namespace does not waive that rule.

---

## Change Log

| Date | Author | Change |
|------|--------|--------|
| 2026-03-23 | Wave 14 audit | Initial document created (MOD-W14-04) |
| 2026-03-23 | Wave 15 audit | Added Idempotency and Presence key contracts (TD-W15-05) |
| 2026-09-29 | Documentation audit | Aligned the Idempotency, Presence, ETag and MFA fingerprint entries with the implementation |
| 2026-10-10 | Source alignment review | Preserved ADR-007 registration and TTL rules; registered source-verified key families and marked current no-expiry implementations as policy gaps |
