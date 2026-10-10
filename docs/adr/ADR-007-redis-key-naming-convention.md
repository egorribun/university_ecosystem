# ADR-007: Redis Key Naming Convention and Contract Registry

## Status
Accepted (Wave 14, 2026-03-23)

## Context

At the time this ADR was written, the university ecosystem shared a single Redis instance across four services: Python backend, Go gateway, Go ws-hub, and Go file-processor. Over time, each service had independently chosen key patterns with no cross-team documentation. This led to:

- Silent key conflicts (two services using the same prefix for different purposes)
- No contract enforcement — one service changing a key format silently breaks another
- No TTL policy document — unclear when keys expire, causing memory growth surprises
- Difficulty auditing the blast radius of a Redis key format change

Current deployments separate revocation state from cache and rate-limit traffic. The backend uses `REVOCATION_REDIS_URL` separately from `CACHE_REDIS_URL`; the gateway and ws-hub use
`REVOCATION_REDIS_URL` separately from their `REDIS_URL`; and file-processor uses
`FP_REVOCATION_REDIS_URL`. Compose and the Helm chart bind revocation connections
to the dedicated revocation store. This updates the deployment context, not the
contract: Decision 1 still requires every key pattern to be registered, and
Decision 4 still requires an explicit expiry for every key and architecture review
for any persistent key.

The gateway's session revocation mechanism depends critically on the exact format `revoked:jti:{jti}` matching what the Python backend writes. A format divergence causes tokens to never be revoked at the gateway layer without any error.

## Decision

1. **Every Redis key pattern must be registered in `contracts/redis-keys.md` before deployment.**
2. **Standard format:** `{namespace}:{discriminator}:{identifier}` — namespaces group related keys; discriminators separate sub-types; identifiers are UUIDs or hashed values.
3. **No raw secrets in keys** — use SHA-256 hashes for user-provided values (`Idempotency-Key` header).
4. **TTL is mandatory** — every key must have an explicit expiry; `PERSIST` keys require architecture review.
5. **Integration tests in `tests/integration/test_redis_contract.py`** verify that each cross-service key is written exactly as documented.

## Format Examples

| Namespace | Discriminator | Identifier | Full Key |
|-----------|---------------|------------|----------|
| `revoked` | `jti` | `{jti}` | `revoked:jti:{jti-uuid}` |
| `ott` | `ws` | `{ticket}` | `ott:ws:{random-hex}` |
| `rate-limit` | _(none)_ | `{composite}` | `rate-limit:{user}:{path}` |
| `session` | `v2` | `{sid}` | `session:v2:{sid-uuid}` |

## Consequences

**Positive:**
- Single source of truth for all Redis keys.
- New keys require explicit PR review of `contracts/redis-keys.md`.
- Integration tests catch format regressions before deployment.

**Negative:**
- PR overhead for adding new keys.
- Existing undocumented keys need retroactive registration (ongoing).

## Implementation

- `contracts/redis-keys.md` — authoritative registry
- `tests/integration/test_redis_contract.py` — contract enforcement tests
- Pre-commit hook: `grep -r 'redis_client\.(set|hset|zadd)' app/ | grep -v contracts` (future)
