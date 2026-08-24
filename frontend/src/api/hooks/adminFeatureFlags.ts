import {
  queryOptions,
  useQuery,
  type QueryFunctionContext,
  type UseQueryOptions,
  type UseQueryResult,
} from "@tanstack/react-query"

import api from "@/api/client"
import type { FeatureFlag } from "@/types/Admin"

/**
 * @fileoverview SSR-safe queryOptions factory for the /admin/feature-flags
 * page (Wave 163 SW3). Closes long-standing W150 §Honesty #3 deferral.
 *
 * Mirrors W129 events.ts + W130 schedule.ts + W133 users.ts + W134 sessions.ts
 * placement convention (`frontend/src/api/hooks/<name>.ts`).
 *
 * Pre-W163: AdminFeatureFlags.tsx consumed `GET /admin/feature-flags` via
 * raw `api.get` inside `useCallback fetchFlags` + `useState/useEffect`.
 * The API is intentionally read-only: flag definitions are managed through
 * the reviewed GitOps workflow, not optimistic browser mutations.
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

export type { FeatureFlag }
