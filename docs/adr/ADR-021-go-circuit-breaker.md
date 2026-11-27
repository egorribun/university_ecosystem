# ADR-021: Go Circuit Breaker Pattern (gobreaker)

## Status
Accepted

## Context
Backend-to-backend communication (e.g., `ws-hub` calling the backend internal API for room authorization) can lead to cascading failures if the downstream service is slow or down. This "thundering herd" can exhaust resources (goroutines, file descriptors) in the calling service.

## Decision
We integrated the **sony/gobreaker** library in Go clients interacting with internal APIs.

Configuration:
1. **Failure Threshold**: more than 10 consecutive failures (the 11th) trip the breaker.
2. **Timeout**: Breaker stays `Open` for 10s before transitioning to `Half-Open`.
3. **Half-Open probes**: `Half-Open` admits up to 5 requests (`MaxRequests: 5`) before deciding.
4. **Fallback**: While the breaker is open, room authorization fails closed: `CanJoinRoom` returns `false` without calling the backend.

## Rationale
1. **Resilience**: Prevents a single slow service from bringing down the entire ecosystem.
2. **Self-Healing**: Allows downstream services time to recover without being hammered by retries.
3. **Observability**: Tripped breakers are logged and can be monitored to detect service degradation.
4. **Efficiency**: Saves CPU and network resources by skipping calls known to be failing.

## Scope

The breaker protects the ws-hub → backend client only. The gateway → backend reverse proxy relies on bounded timeouts (30 s response-header timeout) and has no breaker or retry; adding one is an open design question, not an omission of this ADR.

## Consequences
- Requires explicit error handling for "Breaker Open" state in handlers.
- False positives: Transient network blips might trip the breaker (mitigated by consecutive failure requirement).

## References
- `services/ws-hub/pkg/hub/auth_client.go`
