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
