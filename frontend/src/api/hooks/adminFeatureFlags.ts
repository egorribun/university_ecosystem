import {
  queryOptions,
  useQuery,
  type QueryClient,
  type QueryFunctionContext,
  type UseQueryOptions,
  type UseQueryResult,
} from "@tanstack/react-query"

import api from "@/api/client"
import type { FeatureFlag, FlagStatus } from "@/types/Admin"

/**
 * @fileoverview SSR-safe queryOptions factory for the /admin/feature-flags
 * page (Wave 163 SW3). Closes long-standing W150 §Honesty #3 deferral.
 *
 * Mirrors W129 events.ts + W130 schedule.ts + W133 users.ts + W134 sessions.ts
 * placement convention (`frontend/src/api/hooks/<name>.ts`).
 *
 * Pre-W163: AdminFeatureFlags.tsx consumed `GET /admin/feature-flags` via
 * raw `api.get` inside `useCallback fetchFlags` + `useState/useEffect`.
 * Post-W163: page consumes `useAdminFeatureFlagsQuery()` + mutation paths
 * route through `updateFeatureFlagInCache(queryClient, name, updated)` for
 * optimistic local cache updates.
 *
 * Cache identity: `adminFeatureFlagsQueryKey = ["admin", "feature-flags"]`.
 */

export const adminFeatureFlagsQueryKey = ["admin", "feature-flags"] as const

export type AdminFeatureFlagsQueryKey = typeof adminFeatureFlagsQueryKey

/** W112 SW2 activity.ts pattern — staleTime + gcTime only; retry behaviour
 * delegated to QueryClient (matches pre-W163 inline useQuery defaults). */
const QUERY_STALE_TIME_MS = 30_000
const QUERY_GC_TIME_MS = 5 * 60_000

/**
 * Pure factory for the `GET /admin/feature-flags` query.
 */
export const adminFeatureFlagsQueryOptions = () =>
  queryOptions({
    queryKey: adminFeatureFlagsQueryKey,
    queryFn: async ({
      signal,
    }: QueryFunctionContext<AdminFeatureFlagsQueryKey>): Promise<FeatureFlag[]> => {
      const { data } = await api.get<FeatureFlag[]>("/admin/feature-flags", { signal })
      return Array.isArray(data) ? data : []
    },
    staleTime: QUERY_STALE_TIME_MS,
    gcTime: QUERY_GC_TIME_MS,
  })

type UseAdminFeatureFlagsOptions = Omit<
  UseQueryOptions<FeatureFlag[], Error, FeatureFlag[], AdminFeatureFlagsQueryKey>,
  "queryKey" | "queryFn"
>

/**
 * Component-side hook for the feature-flags list. Thin wrapper around
 * `useQuery(adminFeatureFlagsQueryOptions())`.
 */
export const useAdminFeatureFlagsQuery = (
  options?: UseAdminFeatureFlagsOptions
): UseQueryResult<FeatureFlag[], Error> =>
  useQuery({ ...adminFeatureFlagsQueryOptions(), ...options })

/**
 * Optimistic cache update after a PATCH mutation. Centralising the cache
 * surface here (W135 SW1 sessions.ts pattern) means mutation paths don't
 * reach into the cache key shape directly.
 *
 * Caller flow:
 *   await api.patch(`/admin/feature-flags/${name}`, payload)
 *   updateFeatureFlagInCache(queryClient, name, { status, percentage })
 *
 * The update merges into the existing flag object; pass only the fields
 * that changed (e.g., `{ status: "enabled" }` or `{ status: "percentage",
 * percentage: 50 }`).
 *
 * No-op when the cache slot is empty / not yet populated.
 */
export const updateFeatureFlagInCache = (
  queryClient: QueryClient,
  name: string,
  update: Partial<Pick<FeatureFlag, "status" | "percentage">>
) => {
  queryClient.setQueryData<FeatureFlag[] | undefined>(adminFeatureFlagsQueryKey, (previous) => {
    if (!Array.isArray(previous)) return previous
    return previous.map((flag) => (flag.name === name ? { ...flag, ...update } : flag))
  })
}

/**
 * Invalidate the feature flags cache. Use this when the optimistic update
 * helper is not sufficient (e.g., PATCH returned a different shape than
 * expected, or the backend computed derived fields server-side).
 */
export const invalidateAdminFeatureFlags = async (queryClient: QueryClient) => {
  await queryClient.invalidateQueries({ queryKey: adminFeatureFlagsQueryKey })
}

export type { FeatureFlag, FlagStatus }
