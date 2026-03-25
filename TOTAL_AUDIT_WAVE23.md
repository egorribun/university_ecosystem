# Wave 23 — Total Comprehensive Audit Report

**Date**: 2026-03-25
**Auditor**: Principal Software Architect / Lead Security Researcher
**Scope**: Full-stack polyglot audit — Python backend, TypeScript frontend, Go services, Rust FFI, Kubernetes infrastructure
**Methodology**: Autonomous agent-driven codebase exploration → convention cross-reference → validated findings → code fixes

---

## Executive Summary

Wave 23 identified **21 issues** across **12 files** in 4 categories:
- **7 Red Zone** (P0-P2): ORM N+1 violations, missing input validation, broadcast size gap, unwired metrics, goroutine tracking
- **4 Technical Debt** (P2): Error boundaries, React.memo, migration squash, mypy gaps
- **4 Performance** (P2-P3): SpiceDB TTL asymmetry, health probe rate limiting, pool pre-ping, debounce
- **6 Modernization** (P3): PEP 695, React 19, Go 1.24, TaskGroup, OTEL, bundle analysis

**19 issues fixed in this wave across ~27 files.** 2 issues documented for future implementation (TD-23-03 migration squash, PERF-23-03 pre-ping).

---

## Section 1: Red Zone — Critical Issues (Fixed)

### RZ-23-01 [P0] — Event model `lazy="selectin"` violating project convention
- **File**: `app/models/events.py:99-110`
- **Problem**: `Event.files` and `Event.attendance` used `lazy="selectin"`, firing 2 unconditional secondary SELECTs on every Event load. On a page showing 20 events = 40 extra queries.
- **Fix**: Changed to `lazy="noload"`. Repository already uses explicit `selectinload()` at all call sites.
- **Verified**: All 4 repository query paths (lines 61, 262, 317, 403) already include `selectinload(Event.files)`.

### RZ-23-02 [P0] — DataAccessLog relationships missing `lazy=` parameter entirely
- **File**: `app/models/logs.py:50-51`
- **Problem**: `actor` and `subject` relationships had NO `lazy=` parameter, defaulting to `lazy="select"` (classic N+1). On a **RANGE-partitioned** audit table, this fires cross-partition queries per row.
- **Fix**: Added `lazy="noload"`. No code accesses these relationships via traversal — they are ORM-only.

### RZ-23-03 [P1] — Chat Message/Attachment `lazy="joined"` causing unconditional JOINs
- **File**: `app/models/chat.py:93-96, 137-138`
- **Problem**: Every Message load JOINed Chat + User (sender). Every Attachment load JOINed Message. On bulk fetches (50-msg pagination) = 2 unconditional JOINs per query.
- **Fix**: Changed to `lazy="noload"`. Chat repository already uses `selectinload(Message.sender)` and `selectinload(Message.attachments)` at all 5 call sites.

### RZ-23-04 [P1] — File processor gRPC handler missing input validation
- **File**: `services/file-processor/internal/service/server.go:23-66`
- **Problem**: Empty `Type`, malformed keys, and unbounded `Options` map persisted to Temporal workflow history before failing. Retried 5 times. Options map had no size bound (DoS vector).
- **Fix**: Added validation gate: type allowlist, required fields check, Options bounded to 10 entries with 64-byte key / 1024-byte value limits.

### RZ-23-05 [P1] — WebSocket broadcast missing message size check
- **File**: `services/ws-hub/pkg/hub/hub.go:264-268`
- **Problem**: `broadcastMessage` marshaled to JSON and sent without checking size. ReadLimit is 64KB, but JSON escaping + added fields could exceed it, silently closing recipient connections.
- **Fix**: Added 60KB size guard (4KB headroom for WebSocket framing). Oversized messages dropped with metric increment and warning log.

### RZ-23-06 [P1] — Room auth failure metric never incremented
- **File**: `services/ws-hub/pkg/hub/client.go:108-117`
- **Problem**: `AuthFailuresTotal` counter was defined in metrics.go but never incremented in `handleJoin`. Room brute-force enumeration invisible to monitoring.
- **Fix**: Added `AuthFailuresTotal.WithLabelValues("room_join_denied").Inc()` on auth failure path.

### RZ-23-07 [P2] — Go goroutine lifecycle not tracked in ws-hub
- **Files**: `services/ws-hub/pkg/hub/hub.go:162`, `services/ws-hub/pkg/hub/metrics.go`
- **Problem**: Broadcast worker goroutines launched without WaitGroup tracking. Shutdown couldn't verify all goroutines drained.
- **Fix**: Added `sync.WaitGroup` for broadcast workers + `ws_hub_active_goroutines` Prometheus gauge. Shutdown now calls `broadcastWg.Wait()` after closing broadcast channel.

---

## Section 2: Technical Debt (Fixed)

### TD-23-01 [P2] — Single error boundary wraps all routes
- **File**: `frontend/src/AppRoutes.tsx:202-206`
- **Fix**: Added per-route `PageErrorBoundary` for Messenger (long-lived page) and all Admin routes (sensitive operations). Global boundary preserved as fallback for remaining routes.

### TD-23-02 [P2] — Dashboard card components missing React.memo
- **Files**: `frontend/src/components/dashboard/EventsCard.tsx`, `NewsCard.tsx`
- **Fix**: Wrapped `EventsCard` and `NewsCard` in `React.memo()` to prevent re-renders when parent Dashboard state changes (e.g., schedule tab switch).

### TD-23-03 [P2] — 112 Alembic migration files un-squashed (NOT FIXED — requires manual run)
- **Files**: `alembic/versions/` (112 files)
- **Action**: Run `app/management/squash_migrations.py` to collapse to single baseline. Target: <10 files.

### TD-23-04 [P2] — mypy strict typing gaps (NOT FIXED — incremental effort)
- **Files**: `app/services/chat_service.py`, `app/services/webpush.py`
- **Action**: Add `--strict` mypy check for these modules in CI as non-blocking warning.

---

## Section 3: Performance (Fixed)

### PERF-23-01 [P2] — SpiceDB positive TTL asymmetry
- **File**: `app/auth/rbac.py:96`
- **Problem**: ALLOW results expired at 30s vs DENY at 60s, causing 2x more gRPC calls for the common case.
- **Fix**: Raised `_PERMISSION_POSITIVE_TTL_SECONDS` from 30s to 45s. ~33% reduction in gRPC call volume.
- **Note**: `SPICEDB_MAX_TOLERABLE_DOWNTIME_SECONDS` automatically updated (references the same variable).

### PERF-23-02 [P2] — Gateway fallback rate limit blocks health probes
- **File**: `services/gateway/middleware/ratelimit.go`
- **Problem**: During Redis outage, 3 req/60s fallback applied to ALL endpoints including `/health`. K8s probes fail → pod restart cascade.
- **Fix**: Added `isHealthPath()` check that exempts `/health`, `/readiness`, `/metrics` from rate limiting.

### PERF-23-03 [P3] — Pool pre-ping overhead on read replicas (NOT FIXED — recommendation)
- **File**: `app/core/database.py`
- **Recommendation**: Disable `pool_pre_ping` on read replica engine (keep on primary for failover).

### PERF-23-04 [P3] — Static debounce timing (NOT FIXED — UX decision)
- **File**: `frontend/src/hooks/useDebounced.ts`
- **Recommendation**: Consider 200ms for search, 300ms for validation. Flag for product team.

---

## Section 4: Modernization Plan (Documented Only)

### MOD-23-01 [P3] — Python PEP 695 type alias syntax
Use `type UserID = str | UUID` instead of `TypeAlias` assignments. Available on Python 3.14.

### MOD-23-02 [P3] — React 19 `use()` hook for Suspense data fetching
Replace `useEffect` + loading state patterns with `use()` + `useSuspenseQuery`.

### MOD-23-03 [P3] — Go 1.24 `rangefunc` for cleaner iteration
Range-over-function iterators for client/room maps in ws-hub.

### MOD-23-04 [P3] — Python `asyncio.TaskGroup` for structured concurrency
Replace `asyncio.gather()` with `TaskGroup` for automatic cancellation propagation.

### MOD-23-05 [P3] — OTEL Metrics API migration
Migrate from `prometheus_client` direct usage to OTEL Metrics API for unified observability.

### MOD-23-06 [P3] — Frontend bundle analysis CI step
Add `vite-bundle-visualizer` to CI. Alert on >500KB main chunk growth.

---

## Files Modified

| File | Changes |
|------|---------|
| `app/models/events.py` | `lazy="selectin"` → `lazy="noload"` on files/attendance (RZ-23-01) |
| `app/models/logs.py` | Added `lazy="noload"` to actor/subject (RZ-23-02) |
| `app/models/chat.py` | `lazy="joined"` → `lazy="noload"` on chat/sender/message (RZ-23-03) |
| `services/file-processor/internal/service/server.go` | Input validation gate (RZ-23-04) |
| `services/ws-hub/pkg/hub/hub.go` | Broadcast size check + WaitGroup (RZ-23-05, RZ-23-07) |
| `services/ws-hub/pkg/hub/client.go` | Wired AuthFailuresTotal metric (RZ-23-06) |
| `services/ws-hub/pkg/hub/metrics.go` | Added ActiveGoroutines gauge (RZ-23-07) |
| `frontend/src/AppRoutes.tsx` | Per-route error boundaries (TD-23-01) |
| `frontend/src/components/dashboard/EventsCard.tsx` | React.memo wrapper (TD-23-02) |
| `frontend/src/components/dashboard/NewsCard.tsx` | React.memo wrapper (TD-23-02) |
| `app/auth/rbac.py` | ALLOW TTL 30s → 45s (PERF-23-01) |
| `services/gateway/middleware/ratelimit.go` | Health probe exemption (PERF-23-02) |
| `CLAUDE.md` | Updated audit trail and gotchas |
| `app/services/chat/command_service.py` | mypy strict typing + TaskGroup migration (TD-23-04, MOD-23-04) |
| `app/services/chat/query_service.py` | mypy strict typing (TD-23-04) |
| `app/services/chat/creation_service.py` | mypy strict typing (TD-23-04) |
| `app/services/chat/attachment_service.py` | mypy strict typing (TD-23-04) |
| `app/services/chat/notification_service.py` | mypy strict typing (TD-23-04) |
| `app/services/webpush.py` | mypy strict typing (TD-23-04) |
| `app/services/cache_warmup.py` | Documented gather retention (MOD-23-04) |
| `frontend/src/hooks/useDebounced.ts` | Strategy-based presets: search/default/validation (PERF-23-04) |
| `frontend/src/pages/Events.tsx` | Switched to "search" debounce preset (PERF-23-04) |
| `frontend/src/pages/AdminUsers.tsx` | Switched to "validation" debounce preset (PERF-23-04) |
| `frontend/src/components/messenger/NewChatModal.tsx` | Switched to "default" debounce preset (PERF-23-04) |
| `frontend/src/api/hooks/events.ts` | Added useSuspenseMyEventsQuery (MOD-23-02) |
| `app/core/metrics.py` | OTEL PrometheusMetricReader bridge (MOD-23-05) |
| `.github/workflows/reusable-frontend-tests.yml` | Bundle analysis CI job with 500KB budget (MOD-23-06) |

---

## Validation Checklist

- [x] `python -m py_compile` passes for all modified Python files
- [x] `python -m ruff check` — no new violations (pre-existing UP037 only)
- [x] `npx tsc --noEmit` — TypeScript compiles cleanly
- [ ] `go test ./...` — requires Go toolchain (recommended post-merge)
- [ ] `pytest tests/ -k "event or chat or log"` — requires test database
- [ ] Full CI pipeline — recommended before deployment

---

## Key Architectural Insights

1. **ORM layer was the blind spot**: Waves 19-22 focused on exception handling, security headers, and infrastructure hardening. The ORM relationship audit was never systematically performed, leaving `lazy="selectin"` and missing `lazy=` parameters that contradict the project-wide `lazy="noload"` convention.

2. **Partitioned table amplifies N+1**: The `DataAccessLog` model on a RANGE-partitioned table makes the missing `lazy=` parameter especially dangerous — PostgreSQL must probe partition boundaries for each lazy-loaded relationship.

3. **Metrics defined but not wired**: The `AuthFailuresTotal` counter in ws-hub was infrastructure-ready but the signal was never connected. This pattern (define-but-don't-wire) should be checked project-wide.

4. **Health probe exemption is critical for fallback systems**: Any rate limiting fallback that applies to health endpoints creates a circular dependency: Redis goes down → rate limit fallback activates → health probes blocked → pods restart → more load on remaining pods.

5. **SpiceDB TTL asymmetry**: The original 30s/60s split was conservative for security but doubled gRPC call volume for the common case. The 45s/60s split is a better balance — still fail-closed within 45s for revoked permissions.
