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
 * Note: `fetchDeadLetterQueue()` is signal-unaware in the pre-W163
 * implementation, so the AbortSignal forwarded by TanStack Query is
 * currently not propagated to the underlying axios call. This matches
 * pre-W163 behaviour exactly (the inline useQuery also discarded the
 * signal). Tightening signal propagation would be a separate W164+
 * polish — out of scope for the W163 SW3 factory extraction.
 */
export const adminDeadLetterQueueQueryOptions = () =>
  queryOptions({
    queryKey: adminDeadLetterQueueQueryKey,
    queryFn: async ({
      signal: _signal,
    }: QueryFunctionContext<AdminDeadLetterQueueQueryKey>): Promise<AdminDeadLetterQueueData> => {
      return fetchDeadLetterQueue()
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
