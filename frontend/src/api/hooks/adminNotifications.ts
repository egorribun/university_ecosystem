import {
  queryOptions,
  useQuery,
  type QueryClient,
  type QueryFunctionContext,
  type UseQueryOptions,
  type UseQueryResult,
} from "@tanstack/react-query"

import { fetchDeadLetterQueue } from "@/api/notifications"

/**
 * @fileoverview SSR-safe queryOptions factory for the dead-letter queue
 * (Wave 163 SW3). Closes W150 §Honesty #3 deferral for the AdminNotifications
 * page — REFACTOR of pre-W163 inline pattern (not a from-scratch factory).
 *
 * Pre-W163: AdminNotifications.tsx already used TanStack Query but with an
 * inline `queryKey = ["admin", "notifications", "dead-letter"]` constant
 * (file line 21) + inline `queryFn: () => fetchDeadLetterQueue()` inside
 * `useQuery` (file lines 83-86).
 *
 * Post-W163: extracted to factory; the queryKey shape is PRESERVED EXACTLY
 * (`["admin", "notifications", "dead-letter"]`) for cache identity
 * continuity — existing cache entries (if any) continue to hit on
 * factory consumers. Mutation paths (retry / purge / invalidate-on-success)
 * continue to invalidate the same key.
 *
 * Topics-related fetches (`fetchAdminUserTopics` + `updateAdminUserTopics`)
 * stay imperative inside the page (they're tied to a user-id input that
 * doesn't fit naturally into a TanStack Query slot; their existing
 * useState-based flow is preserved).
 */

export const adminDeadLetterQueueQueryKey = ["admin", "notifications", "dead-letter"] as const

export type AdminDeadLetterQueueQueryKey = typeof adminDeadLetterQueueQueryKey

export type AdminDeadLetterQueueData = Awaited<ReturnType<typeof fetchDeadLetterQueue>>

/** W112 SW2 activity.ts pattern — staleTime + gcTime only; retry behaviour
 * delegated to QueryClient (preserves pre-W163 inline useQuery defaults
 * EXACTLY — the inline pattern had no retry override, so the page's
 * QueryClient default applied. Adding retry here would surface 500-mock
 * errors only after retries complete, breaking findByText timeouts in
 * AdminNotifications.test.tsx). */
const QUERY_STALE_TIME_MS = 30_000
const QUERY_GC_TIME_MS = 5 * 60_000

/**
 * Pure factory for the dead-letter queue. Delegates to existing
 * `fetchDeadLetterQueue()` helper in `@/api/notifications` for fetch
 * semantics (route, error shaping, response normalisation).
 *
 * Wave 164 SW3 (Tier 4) — AbortSignal propagation NOW closed. Pre-W164 the
 * queryFn discarded `signal` (underscored unused) because
 * `fetchDeadLetterQueue()` was signal-unaware. W164 SW3 extended the helper
 * signature to `(params?, signal?)` (see `@/api/notifications:94-114`) and
 * the queryFn now forwards the TanStack Query AbortSignal so route unmounts
 * and refetch-replacement cancel in-flight axios requests cleanly. Closes
 * W163 SW3 NEW caveat (AdminNotifications signal propagation polish).
 */
export const adminDeadLetterQueueQueryOptions = () =>
  queryOptions({
    queryKey: adminDeadLetterQueueQueryKey,
    queryFn: async ({
      signal,
    }: QueryFunctionContext<AdminDeadLetterQueueQueryKey>): Promise<AdminDeadLetterQueueData> => {
      return fetchDeadLetterQueue(undefined, signal)
    },
    staleTime: QUERY_STALE_TIME_MS,
    gcTime: QUERY_GC_TIME_MS,
  })

type UseAdminDeadLetterQueueOptions = Omit<
  UseQueryOptions<
    AdminDeadLetterQueueData,
    Error,
    AdminDeadLetterQueueData,
    AdminDeadLetterQueueQueryKey
  >,
  "queryKey" | "queryFn"
>

/**
 * Component-side hook for the dead-letter queue. Thin wrapper around
 * `useQuery(adminDeadLetterQueueQueryOptions())`.
 */
export const useAdminDeadLetterQueueQuery = (
  options?: UseAdminDeadLetterQueueOptions
): UseQueryResult<AdminDeadLetterQueueData, Error> =>
  useQuery({ ...adminDeadLetterQueueQueryOptions(), ...options })

/**
 * Invalidate the dead-letter queue cache after a mutation (retry / purge).
 * Mirrors W135 SW1 `invalidateSessions` pattern.
 */
export const invalidateAdminDeadLetterQueue = async (queryClient: QueryClient) => {
  await queryClient.invalidateQueries({ queryKey: adminDeadLetterQueueQueryKey })
}
