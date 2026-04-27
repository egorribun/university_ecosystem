# ADR-021: Go Circuit Breaker Pattern (gobreaker)

## Status
Accepted

## Context
Backend-to-backend communication (e.g., `ws-hub` calling the `gateway` for auth) can lead to cascading failures if the downstream service is slow or down. This "thundering herd" can exhaust resources (goroutines, file descriptors) in the calling service.

## Decision
We integrated the **sony/gobreaker** library in Go clients interacting with internal APIs.

Configuration:
1. **Failure Threshold**: 10 consecutive failures trip the breaker.
2. **Timeout**: Breaker stays `Open` for 60s before transitioning to `Half-Open`.
3. **Success Threshold**: 1 successful call in `Half-Open` state closes the breaker.
4. **Fallback**: Requests return a `503 Service Unavailable` immediately while the breaker is open.

## Rationale
1. **Resilience**: Prevents a single slow service from bringing down the entire ecosystem.
2. **Self-Healing**: Allows downstream services time to recover without being hammered by retries.
3. **Observability**: Tripped breakers are logged and can be monitored to detect service degradation.
4. **Efficiency**: Saves CPU and network resources by skipping calls known to be failing.

## Consequences
- Requires explicit error handling for "Breaker Open" state in handlers.
- False positives: Transient network blips might trip the breaker (mitigated by consecutive failure requirement).

## References
- `services/ws-hub/pkg/hub/auth_client.go`
