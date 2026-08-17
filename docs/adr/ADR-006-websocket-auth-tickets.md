# ADR-006: WebSocket Authentication via One-Time Upgrade Tickets

## Status
Accepted (Wave 14, 2026-03-23)

## Context

Prior to Wave 14, WebSocket upgrade requests were authenticated by embedding the JWT in the `Sec-WebSocket-Protocol` header. This exposed the JTI to proxy access logs, reverse-proxy middleware, and any network observer with access to log infrastructure. WebSocket upgrade headers are not encrypted at the application layer in the same way as body content.

The specific vulnerability (RZ-W14-01) was:
- JWT sent in a header visible to nginx, haproxy, and API gateway logs
- JTI could be extracted from logs and used to impersonate the session before expiry
- Log aggregation systems (ELK, Loki) may retain these logs for months

## Decision

Replaced JWT-in-header with a **one-time upgrade ticket (OTT)** pattern:

1. Frontend calls `POST /ws/ticket` (authenticated via HttpOnly session cookie) to obtain a short-lived ticket.
2. Backend generates a cryptographically random ticket, stores `{user_id}:{jti}` under Redis key `ott:ws:{ticket}` with TTL=15s.
3. Frontend includes the ticket as a query parameter: `wss://host/ws?ticket={ticket}`.
4. ws-hub (Go) and Python WS handler consume the ticket atomically via Redis `GETDEL` — first consumer wins, replays are rejected.
5. After consumption, each handler checks `revoked:jti:{jti}` in the dedicated revocation store and fails closed if that store is unavailable. A ticket minted before logout therefore cannot outlive its JWT session.

**Redis key contract:** `ott:ws:{ticket}` → `{user_id}:{jti}`, TTL 15s. See `contracts/redis-keys.md`.

Tenant selection is deliberately not encoded in the ticket. Client-supplied
`X-Tenant-ID` is only a routing hint and cannot establish membership; promoting
it into WebSocket identity would allow cross-tenant spoofing. Tenant-aware OTTs
require membership resolution by the issuer and a versioned consumer contract.

## Consequences

**Positive:**
- JTI never appears in proxy logs or access logs.
- Ticket is single-use (GETDEL atomicity prevents replay).
- Short TTL (15s) limits the replay window even if tickets are somehow leaked.
- Logout and administrative revocation invalidate already-issued tickets before upgrade.
- Decouples WS auth from the `Sec-WebSocket-Protocol` mechanism.

**Negative:**
- One additional HTTP round-trip before each WebSocket connection.
- Frontend must handle `POST /ws/ticket` failure gracefully (abort + show auth error, not silent fallback).

## Alternatives Rejected

- **Signed URL with expiry**: No revocation mechanism; leaking the URL grants access until expiry.
- **Cookie-only auth**: Requires browser to send cookies on WS upgrade, which works but does not provide JTI revocation granularity at the WS layer.
- **Keep JWT-in-subprotocol**: Too many log exposure vectors.

## Implementation

- `app/api/ws/ticket.py` — ticket issuance endpoint
- `app/api/ws/auth.py` — `get_user_from_ticket()` (Python WS handler)
- `services/ws-hub/pkg/hub/handlers.go` — ticket validation (Go)
- `app/auth/revocation.py` — durable, tombstone-first cross-service revocation contract
- `frontend/src/hooks/useChatWebSocket.ts` — ticket fetch with proper 401/403 handling
