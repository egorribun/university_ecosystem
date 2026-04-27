# ADR-019: Client-side Caching Strategy (TanStack Query + IndexedDB)

## Status
Accepted

## Context
To provide a smooth, "premium" feel (Zero Friction Principle), the frontend needs to load data instantly where possible and handle offline/flaky network conditions gracefully. Standard in-memory caching (React state) is lost on page refresh.

## Decision
We adopted **TanStack Query (v5)** with a persistent **IndexedDB** adapter.

Implementation details:
1. **QueryClient**: Configured with reasonable `staleTime` (5m) and `gcTime` (30m).
2. **Persister**: Custom `idbPersister` using `idb-keyval` to serialize the cache to IndexedDB.
3. **Quota Management**: Defensive check against `QuotaExceededError` by calculating a device-specific quota (5% of available storage, capped at 50MB).
4. **Stale-While-Revalidate**: UI displays cached data immediately while background refetches ensure freshness.

## Rationale
1. **User Experience**: Sub-millisecond "re-entry" time for previously visited pages.
2. **Reliability**: App remains functional (in read-only mode) during brief API outages or tunnel transits.
3. **Data Integrity**: Automated background refetching ensures the cache doesn't drift too far from reality.
4. **Performance**: Reduced redundant API calls and JSON parsing on consecutive loads.

## Consequences
- Cache invalidation complexity: Mutations must explicitly `invalidateQueries` to reflect changes.
- Large JSON payloads can hit IndexedDB limits (mitigated by quota guard).
- Sensitive data might be persisted locally (sensitive queries must be marked `gcTime: 0`).

## References
- `frontend/src/app/queryClient.ts`
- `frontend/src/main.tsx`
