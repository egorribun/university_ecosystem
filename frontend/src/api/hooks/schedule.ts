/**
 * @fileoverview SSR-safe queryOptions factories for the /schedule page.
 *
 * Wave 130 SW1 — extracted from `useScheduleData()` (frontend/src/hooks/
 * useScheduleData.ts) so the route loader can call `ensureQueryData()` /
 * `prefetchQuery()` against the same cache keys the runtime hook uses
 * (cache identity preserved per W129 SW2 + SW5 pattern).
 *
 * Mirrors the W129 events.ts:261-272 + news.ts factory placement
 * convention. The runtime hook continues to spread the factory result
 * via `useQuery({ ...factory(args) })` so its public API stays
 * unchanged.
 *
 * Usage:
 *
 * ```ts
 * // Loader (server-side prefetch)
 * loader: async ({ context }) =>
 *   Promise.allSettled([
 *     context.queryClient.ensureQueryData(scheduleGroupsQueryOptions()),
 *   ])
 *
 * // Hook (component-side consumer)
 * useQuery(scheduleGroupsQueryOptions())
 * ```
 */
import type { QueryFunctionContext } from "@tanstack/react-query"

import api from "@/api/client"
import {
  type Lesson,
  type ScheduleGroup,
  scheduleGroupsQueryKey,
  scheduleQueryKey,
  type ActiveScheduleQueryKey,
  type InactiveScheduleQueryKey,
  type ScheduleGroupsQueryKey,
} from "@/components/schedule/scheduleUtils"

/** Wave 130 — kept in sync with `useScheduleData`'s historical values. */
const QUERY_STALE_TIME_MS = 60_000
const QUERY_GC_TIME_MS = 5 * 60_000

/**
 * Exponential backoff for flaky mobile connections (FIX-68-05; preserved
 * verbatim from `useScheduleData.ts`).
 */
const retryDelay = (attempt: number) => Math.min(1_000 * 2 ** attempt, 10_000)

/**
 * Wave 130 SW1 — pure factory for the `/groups` query.
 *
 * Used by `useScheduleData()` (runtime) AND the /schedule loader
 * (`routes/_auth/schedule.tsx`, SSR). queryKey + queryFn shape
 * preserved from the prior inline `useQuery` call so existing cache
 * entries hydrate cleanly.
 */
export const scheduleGroupsQueryOptions = () => ({
  queryKey: scheduleGroupsQueryKey,
  queryFn: async ({
    signal,
  }: QueryFunctionContext<ScheduleGroupsQueryKey>): Promise<ScheduleGroup[]> => {
    const res = await api.get("/groups", { signal })
    return Array.isArray(res.data) ? (res.data as ScheduleGroup[]) : []
  },
  staleTime: QUERY_STALE_TIME_MS,
  gcTime: QUERY_GC_TIME_MS,
  networkMode: "online" as const,
  retry: 2,
  retryDelay,
})

/**
 * Wave 130 SW1 — pure factory for the `/schedule/{groupId}` query.
 *
 * The hook spreads this with `enabled: groupId != null`. SSR loaders
 * SHOULD pass a known-non-null `groupId` (e.g. derived from a
 * future /users/me prefetch) — until then, /schedule SSR prefetches
 * only the groups list (W130 SW2; lessons fetch client-side).
 */
export const pageScheduleQueryOptions = (groupId: string | null) => ({
  queryKey: (groupId != null
    ? scheduleQueryKey(groupId)
    : (["schedule", "group", "none"] as const)) as
    ActiveScheduleQueryKey | InactiveScheduleQueryKey,
  queryFn: async ({
    signal,
  }: QueryFunctionContext<ActiveScheduleQueryKey | InactiveScheduleQueryKey>): Promise<
    Lesson[]
  > => {
    if (groupId == null) return []
    const res = await api.get(`/schedule/${groupId}`, { signal })
    return Array.isArray(res.data) ? (res.data as Lesson[]) : []
  },
  enabled: groupId != null,
  staleTime: QUERY_STALE_TIME_MS,
  gcTime: QUERY_GC_TIME_MS,
  networkMode: "online" as const,
  retry: 2,
  retryDelay,
})
