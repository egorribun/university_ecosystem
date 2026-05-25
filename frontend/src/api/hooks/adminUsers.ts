import {
  queryOptions,
  useQuery,
  type QueryClient,
  type QueryFunctionContext,
  type UseQueryOptions,
  type UseQueryResult,
} from "@tanstack/react-query"

import api from "@/api/client"

/**
 * @fileoverview SSR-safe queryOptions factories for the /admin/users page
 * (Wave 163 SW3). Closes long-standing W150 §Honesty #3 deferral —
 * "TanStack Query factories for 4 admin pages" — finally landed.
 *
 * Two factories live here (mirroring W129 events.ts placement convention
 * which co-locates list + detail factories in one file):
 *
 *   1. `adminUsersQueryOptions(filters)` for `GET /users` with optional
 *      filters spread into query params.
 *   2. `adminGroupsQueryOptions()` for `GET /groups` (no filters).
 *
 * Pre-W163, the AdminUsers page consumed these via raw `api.get` calls
 * inside `useCallback fetchUsers / fetchGroups` + `useState/useEffect`
 * chains. After SW3, the page consumes the factories via `useQuery` for
 * cache identity continuity, mutation invalidation paths, and SSR
 * loader compatibility (forward-compat with W128+ SSR architecture).
 *
 * Cache identity preserved:
 *   - `adminUsersQueryKey(filters) = ["admin", "users", filters]` — filters
 *     object spread into key tuple. Empty-string filter values stay in the
 *     key so cache hits on `{full_name: "", group_id: "", role: ""}` are
 *     correct.
 *   - `adminGroupsQueryKey = ["admin", "groups"]`.
 *
 * NOT placed under `frontend/src/features/admin/hooks/` because the
 * codebase convention (verified W163 Phase 3 Review against
 * `frontend/src/api/hooks/activity.ts`) is `frontend/src/api/hooks/<name>.ts`
 * for all per-page query factories — features/X/ directories hold
 * orchestrators + components, NOT data-fetching hooks.
 */

export type UserRole = "student" | "teacher" | "admin"

export type AdminUser = {
  id: string
  full_name: string
  email: string
  role: UserRole
  group_id: string | null
  avatar_url?: string | null
}

export type Group = { id: string; name: string }

export type AdminUserFilters = {
  full_name: string
  group_id: string
  role: "" | UserRole
}

/**
 * Cache key for the admin user list. Filters are part of the key so
 * different filter combinations populate distinct cache slots; identical
 * filters hit the same slot. Empty-string filter values preserved (the
 * caller decides whether to debounce filter updates via `useDebounced`).
 */
export const adminUsersQueryKey = (filters: AdminUserFilters) =>
  ["admin", "users", filters] as const

export type AdminUsersQueryKey = ReturnType<typeof adminUsersQueryKey>

export const adminGroupsQueryKey = ["admin", "groups"] as const

export type AdminGroupsQueryKey = typeof adminGroupsQueryKey

/** Aligned with W112 SW2 activity.ts factory defaults — staleTime + gcTime only;
 * retry behaviour delegated to the QueryClient (pre-W163 AdminUsers had no
 * retry override, so the page-level useQuery's QueryClient default applies). */
const QUERY_STALE_TIME_MS = 30_000
const QUERY_GC_TIME_MS = 5 * 60_000

/**
 * Pure factory for the `GET /users` query with optional filters. The
 * filters object is converted to query params; empty values are omitted
 * from the request (matches pre-W163 fetchUsers behaviour exactly).
 */
export const adminUsersQueryOptions = (filters: AdminUserFilters) =>
  queryOptions({
    queryKey: adminUsersQueryKey(filters),
    queryFn: async ({ signal }: QueryFunctionContext<AdminUsersQueryKey>): Promise<AdminUser[]> => {
      const params: Record<string, string> = {}
      if (filters.full_name) params.full_name = filters.full_name
      if (filters.group_id) params.group_id = filters.group_id
      if (filters.role) params.role = filters.role
      const { data } = await api.get<AdminUser[]>("/users", { params, signal })
      return Array.isArray(data) ? data : []
    },
    staleTime: QUERY_STALE_TIME_MS,
    gcTime: QUERY_GC_TIME_MS,
  })

/** Pure factory for the `GET /groups` query — no filters, no params. */
export const adminGroupsQueryOptions = () =>
  queryOptions({
    queryKey: adminGroupsQueryKey,
    queryFn: async ({ signal }: QueryFunctionContext<AdminGroupsQueryKey>): Promise<Group[]> => {
      const { data } = await api.get<Group[]>("/groups", { signal })
      return Array.isArray(data) ? data : []
    },
    staleTime: QUERY_STALE_TIME_MS,
    gcTime: QUERY_GC_TIME_MS,
  })

type UseAdminUsersOptions = Omit<
  UseQueryOptions<AdminUser[], Error, AdminUser[], AdminUsersQueryKey>,
  "queryKey" | "queryFn"
>

type UseAdminGroupsOptions = Omit<
  UseQueryOptions<Group[], Error, Group[], AdminGroupsQueryKey>,
  "queryKey" | "queryFn"
>

/**
 * Component-side hook for the admin user list. Thin wrapper around
 * `useQuery(adminUsersQueryOptions(filters))` — the indirection lets
 * consumers pass `enabled`, `select`, etc. without re-deriving the cache
 * key. For non-component contexts (loaders, prefetch), use the factory
 * directly.
 */
export const useAdminUsersQuery = (
  filters: AdminUserFilters,
  options?: UseAdminUsersOptions
): UseQueryResult<AdminUser[], Error> =>
  useQuery({ ...adminUsersQueryOptions(filters), ...options })

/** Component-side hook for the groups list. */
export const useAdminGroupsQuery = (
  options?: UseAdminGroupsOptions
): UseQueryResult<Group[], Error> => useQuery({ ...adminGroupsQueryOptions(), ...options })

/**
 * Invalidate the admin user list cache after a mutation (PATCH group,
 * DELETE user). Mirrors W135 SW1 `invalidateSessions` pattern. The
 * filters argument routes invalidation to a specific cache slot; pass the
 * same filters object that `useAdminUsersQuery` consumed to ensure cache
 * identity. For invalidating ALL slots regardless of filters, use
 * `queryClient.invalidateQueries({ queryKey: ["admin", "users"] })` directly
 * (prefix match).
 */
export const invalidateAdminUsers = async (queryClient: QueryClient, filters: AdminUserFilters) => {
  await queryClient.invalidateQueries({ queryKey: adminUsersQueryKey(filters) })
}

/**
 * Invalidate ALL admin user list cache slots regardless of filters. Used
 * after a DELETE mutation where the new state should propagate to every
 * possible filter combination the user might have viewed.
 */
export const invalidateAllAdminUsers = async (queryClient: QueryClient) => {
  await queryClient.invalidateQueries({ queryKey: ["admin", "users"] })
}
