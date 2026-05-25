/**
 * @fileoverview SSR-safe queryOptions factory for the current user (`/users/me`).
 *
 * Wave 133 SW2 — extracted as a queryOptions factory mirroring the W129/W130
 * pattern (events.ts, news.ts, schedule.ts), so route loaders can call
 * `ensureQueryData()` to prefetch authenticated user data server-side.
 *
 * The factory's `queryFn` delegates to the existing `fetchCurrentUser`
 * (`frontend/src/hooks/auth/useProfileSync.ts:485-515`) — preserving the
 * cache-envelope header logic + retry-on-500-with-cleared-cache behaviour.
 * No duplication.
 *
 * `useProfileSync` continues to call `fetchCurrentUser` directly for its
 * lifecycle bootstrap (synchronous read from localStorage envelope + async
 * crypto verify); this factory is purely for SSR loaders + future client
 * `useQuery` consumers (e.g. when AuthContext eventually migrates to
 * React Query — out of scope for W133).
 *
 * The cookie-forwarding infrastructure (W133 SW1) ensures the SSR-side
 * `api.get("/users/me")` request includes the `access_token_v2` HttpOnly
 * cookie via the `__ssrCookieGetter__` axios interceptor branch.
 *
 * Usage:
 *
 * ```ts
 * // Loader (server-side prefetch)
 * loader: async ({ context }) => {
 *   const userResult = await context.queryClient
 *     .ensureQueryData(currentUserQueryOptions())
 *     .catch(() => null)
 *   if (userResult?.group_id) {
 *     await context.queryClient.ensureQueryData(
 *       pageScheduleQueryOptions(userResult.group_id),
 *     )
 *   }
 * }
 *
 * // Hook (component-side consumer; not currently used in W133)
 * useQuery(currentUserQueryOptions())
 * ```
 */
import type { QueryFunctionContext } from "@tanstack/react-query"

import { fetchCurrentUser } from "@/hooks/auth/useProfileSync"
import type { User } from "@/types/User"

/**
 * QueryKey for the current user. Stable across SSR and browser paths so
 * `ensureQueryData()` populates the same cache that any future
 * `useQuery(currentUserQueryOptions())` call would read from.
 */
export const currentUserQueryKey = ["users", "me"] as const

export type CurrentUserQueryKey = typeof currentUserQueryKey

/** Wave 133 — kept in sync with W130 schedule.ts factory defaults. */
const QUERY_STALE_TIME_MS = 60_000
const QUERY_GC_TIME_MS = 5 * 60_000

/**
 * Exponential backoff for flaky mobile connections (FIX-68-05; verbatim
 * from `useScheduleData.ts` via W130 SW1 schedule.ts).
 */
const retryDelay = (attempt: number) => Math.min(1_000 * 2 ** attempt, 10_000)

/**
 * Wave 133 SW2 — pure factory for the `/users/me` query.
 *
 * Used by SSR loaders (e.g. `routes/_auth/schedule.tsx`,
 * `routes/_auth/profile.tsx`, `routes/_auth/settings.tsx`) to prefetch
 * the authenticated user server-side. The runtime `useProfileSync` hook
 * does NOT consume this factory in W133 — it continues to call
 * `fetchCurrentUser` directly for its synchronous-bootstrap-then-async-init
 * lifecycle. Migration of useProfileSync to React Query is scoped
 * separately (would require unifying the localStorage envelope path with
 * the queryClient cache; out of scope for this wave).
 *
 * SSR cookie forwarding: the underlying `fetchCurrentUser` calls
 * `api.get("/users/me", { skipRateLimitQueue: true })`, which goes
 * through the W133 SW1 axios interceptor that injects the
 * `access_token_v2` HttpOnly cookie from `requestCookieStorage` on
 * Node SSR. Browser path uses `withCredentials: true` as before.
 */
export const currentUserQueryOptions = () => ({
  queryKey: currentUserQueryKey,
  queryFn: async ({ signal }: QueryFunctionContext<CurrentUserQueryKey>): Promise<User> => {
    return fetchCurrentUser({ signal })
  },
  staleTime: QUERY_STALE_TIME_MS,
  gcTime: QUERY_GC_TIME_MS,
  networkMode: "online" as const,
  retry: 2,
  retryDelay,
})
