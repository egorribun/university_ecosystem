/**
 * @fileoverview SSR-safe queryOptions factory for the active sessions list
 * (`GET /auth/sessions`).
 *
 * Wave 134 SW2 — extracted as a queryOptions factory mirroring the W129
 * (events.ts, news.ts), W130 (schedule.ts), and W133 (users.ts) pattern,
 * so the `/settings` route loader can call `ensureQueryData()` to prefetch
 * the user's session list server-side when the route is loaded with
 * `?tab=2` (Security tab).
 *
 * Pre-W134, the sessions list was fetched client-side via inline
 * `useQuery` inside `useSessionManagement` (gated by `tabActive`). After
 * SW2, the same factory is consumed by both the loader (SSR pre-fetch on
 * tab=2) and `useSessionManagement` (client-side runtime fetch on
 * security-tab activation), unifying the cache slot.
 *
 * Cache identity: `sessionsQueryKey(userId)` returns the SAME tuple shape
 * `["auth", "sessions", userId]` previously used by `useSessionManagement`
 * line 50 (Wave 133 baseline). SSR-prefetched entries hydrate cleanly.
 *
 * SSR cookie forwarding: the underlying `api.get("/auth/sessions")`
 * request goes through the W133 SW1 axios interceptor that injects the
 * `access_token_v2` HttpOnly cookie from `requestCookieStorage` on Node
 * SSR. Browser path uses `withCredentials: true` as before.
 *
 * Usage:
 *
 * ```ts
 * // Loader (server-side conditional prefetch on tab=2)
 * loader: async ({ context, search }) => {
 *   const userResult = await context.queryClient
 *     .ensureQueryData(currentUserQueryOptions())
 *     .catch(() => null)
 *   if (search.tab === 2 && userResult?.id) {
 *     await context.queryClient
 *       .ensureQueryData(sessionsQueryOptions(userResult.id))
 *       .catch(() => undefined)
 *   }
 * }
 *
 * // Hook (component-side consumer)
 * useQuery({
 *   ...sessionsQueryOptions(user?.id ?? "me"),
 *   enabled: tabActive && Boolean(user),
 * })
 * ```
 */
import type { QueryFunctionContext } from "@tanstack/react-query"

import api from "@/api/client"
import type { ActiveSession } from "@/types/Session"

/**
 * QueryKey for the active sessions list. Stable across SSR and browser
 * paths so `ensureQueryData()` populates the same cache that
 * `useQuery(sessionsQueryOptions(userId))` reads from.
 *
 * The userId tuple element is required by the existing
 * `useSessionManagement` cache key shape (line 50, pre-W134) — preserves
 * cache identity for in-flight queries. Pass `"me"` as the fallback when
 * the auth user is not yet resolved (matches pre-W134 behaviour).
 */
export const sessionsQueryKey = (userId: string) => ["auth", "sessions", userId] as const

export type SessionsQueryKey = ReturnType<typeof sessionsQueryKey>

/** Wave 134 SW2 — kept in sync with pre-W134 useSessionManagement defaults. */
const QUERY_STALE_TIME_MS = 30_000
const QUERY_GC_TIME_MS = 5 * 60_000

/**
 * Exponential backoff for flaky mobile connections (FIX-68-05; mirrors
 * W130 schedule.ts + W133 users.ts).
 */
const retryDelay = (attempt: number) => Math.min(1_000 * 2 ** attempt, 10_000)

/**
 * Wave 134 SW2 — pure factory for the `GET /auth/sessions` query.
 *
 * Used by:
 *  - `/settings` SSR loader (`routes/_auth/settings.tsx`) when the route
 *    URL contains `?tab=2` (Security tab) — prefetches the sessions list
 *    server-side so the page renders with data already present, not a
 *    skeleton.
 *  - `useSessionManagement` (`pages/settings/hooks/useSessionManagement.ts`)
 *    on the client side when `tabActive` becomes true.
 */
export const sessionsQueryOptions = (userId: string) => ({
  queryKey: sessionsQueryKey(userId),
  queryFn: async ({
    signal,
  }: QueryFunctionContext<SessionsQueryKey>): Promise<ActiveSession[]> => {
    const { data } = await api.get<ActiveSession[]>("/auth/sessions", { signal })
    return data
  },
  staleTime: QUERY_STALE_TIME_MS,
  gcTime: QUERY_GC_TIME_MS,
  networkMode: "online" as const,
  retry: 2,
  retryDelay,
})
