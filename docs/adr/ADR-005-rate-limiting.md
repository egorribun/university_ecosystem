# ADR-005: Rate Limiting Strategy

## Status

Accepted

## Context

The API requires protection against abuse, brute-force attacks, and resource exhaustion. Requirements:

- Per-endpoint rate limits
- Authentication-aware limiting
- Graceful degradation if Redis unavailable
- Progressive delays for failed auth attempts

## Decision

We implement a multi-layer rate limiting strategy:

### Sliding Window Algorithm

Using Redis sorted sets with `ZADD`/`ZREMRANGEBYSCORE`:

- Precise request tracking
- Memory-efficient with TTL cleanup
- Atomic operations via Lua script

### Endpoint-Specific Limits

```python
EndpointRateLimit("/api/v1/auth/login", 5, 60)   # 5 req/min (security)
EndpointRateLimit("/api/v1/users/me", 120, 60)   # 120 req/min (navigation)
EndpointRateLimit("/api/v1/events/", 120, 60)    # 120 req/min (read-heavy)
EndpointRateLimit("/api/v1/notifications", 120, 60) # 120 req/min (polling)
```

### Progressive Delay for Auth Failures

`ProgressiveDelayTracker` implements exponential backoff:

- 1st failure: 1s delay
- 2nd failure: 2s delay
- 3rd failure: 5s delay
- Max: 30s delay
- Auto-reset after 15 min or successful auth

### Fallback Behavior

- Memory-based sliding window when Redis unavailable
- Isolated per-middleware namespaces for testing

### Identifier Resolution

1. Bearer token (hashed)
2. Cookie token (hashed)
3. Client IP address

## Consequences

**Positive:**

- Effective brute-force mitigation
- Configurable per-endpoint limits
- Resilient to Redis failures

**Negative:**

- Memory usage grows with traffic
- Delay adds latency for legitimate users after failed attempts

## Addendum: per-user bucketing for verified access tokens (2026-11-04)

Decided by the orchestrator under the owner's standing authority for secure
defaults (AUD-164; follows commit f75194e2f). This addendum supersedes the
"Identifier Resolution" list above.

**Semantics: bucketing only.** A rate-limit key may be derived from a verified
token, but the key grants no access. Both `RateLimitMiddleware` and
`sensitive_route_limit` use `extract_user_id_for_ratelimit`, which:

- accepts only a token that passes `decode_token` (signature, `exp`, `aud`,
  `iss`, `jti`, known `kid`);
- rejects a token that declares a type marker other than `access` (`typ`,
  `type`, `token_type`, `token_use`, `purpose`). The codebase mints no
  refresh or MFA JWTs today, so this is a defence for future token kinds;
- requires `sub` to be the canonical lowercase hyphenated UUID.

Any other case (absent, expired, wrong audience or issuer, unknown or foreign
key, non-Bearer or malformed `Authorization`, non-UUID `sub`) uses the client IP
key. Client IPs come from `resolve_client_ip`, which honours `X-Forwarded-For`
and `Forwarded` only when the immediate peer is a configured trusted proxy.

**Route policy.** Login (`/api/v1/auth/login`, including `/login/json`),
register (`/api/v1/auth/register`) and password routes (`/api/v1/password`)
always use the IP key, whatever token is presented. `uses_ip_bucket` matches
on path segments, case-insensitively: `/api/v1/auth/loginx` is not the login
route. MFA endpoints (`/api/v1/auth/mfa/*`) are not in this list and follow the
per-user rule.

**Accepted residuals (not defects; tests document them):**

- Revocation and account state are not consulted. A signature-valid token that
  was logged out, revoked or belongs to a deactivated user keeps its own bucket
  until it expires. The key only spends the budget, so access stays governed by
  the authentication dependency.
- One actor who holds N accounts gets N buckets on non-auth routes. Auth routes
  stay per-IP, so credential guessing is not multiplied by accounts.
- A non-Bearer `Authorization` header is ignored for keying. The cookie fallback
  still applies when no Bearer token is present.

Tests: `tests/test_authenticated_rate_limit_buckets.py`.
