import {
  queryOptions,
  useQuery,
  type QueryClient,
  type QueryFunctionContext,
  type UseQueryOptions,
  type UseQueryResult,
} from "@tanstack/react-query"

import api from "@/api/client"
import type { AuditLogList } from "@/types/Admin"

/**
 * @fileoverview SSR-safe queryOptions factory for the /admin/audit page
 * (Wave 163 SW3). Closes W150 §Honesty #3 deferral for the audit page.
 *
 * Pre-W163: AdminAudit.tsx consumed `GET /admin/audit` via raw `api.get`
 * inside `useCallback fetchLogs` + `useState/useEffect`, with manual
 * loading state, manual pagination (page + rowsPerPage), manual filter
 * state (resource_type + action).
 *
 * Post-W163: page consumes `useAdminAuditLogsQuery(filters, pagination)`.
 * Filters + pagination are part of the cache key, so different filter or
 * pagination combinations populate distinct cache slots — pagination
 * round-trips don't refetch already-cached pages.
 *
 * Cache identity:
 *   `adminAuditLogsQueryKey(filters, pagination) =
 *     ["admin", "audit-logs", filters, pagination]`
 */

export type AdminAuditFilters = {
  resource_type: string
  action: string
}

export type AdminAuditPagination = {
  page: number
  rowsPerPage: number
}

export const adminAuditLogsQueryKey = (
  filters: AdminAuditFilters,
  pagination: AdminAuditPagination
) => ["admin", "audit-logs", filters, pagination] as const

export type AdminAuditLogsQueryKey = ReturnType<typeof adminAuditLogsQueryKey>

/** W112 SW2 activity.ts pattern — staleTime + gcTime only; retry behaviour
 * delegated to QueryClient (matches pre-W163 inline useQuery defaults). */
const QUERY_STALE_TIME_MS = 30_000
const QUERY_GC_TIME_MS = 5 * 60_000

/**
 * Pure factory for the `GET /admin/audit` query with filters + pagination.
 * Pagination is converted from `{page, rowsPerPage}` to `{limit, offset}`
 * (matches pre-W163 fetchLogs behaviour exactly).
 */
export const adminAuditLogsQueryOptions = (
  filters: AdminAuditFilters,
  pagination: AdminAuditPagination
) =>
  queryOptions({
    queryKey: adminAuditLogsQueryKey(filters, pagination),
    queryFn: async ({
      signal,
    }: QueryFunctionContext<AdminAuditLogsQueryKey>): Promise<AuditLogList> => {
      const params: Record<string, unknown> = {
        limit: pagination.rowsPerPage,
        offset: pagination.page * pagination.rowsPerPage,
      }
      if (filters.resource_type) params.resource_type = filters.resource_type
      if (filters.action) params.action = filters.action
      const { data } = await api.get<AuditLogList>("/admin/audit", { params, signal })
      return data
    },
    staleTime: QUERY_STALE_TIME_MS,
    gcTime: QUERY_GC_TIME_MS,
  })

type UseAdminAuditLogsOptions = Omit<
  UseQueryOptions<AuditLogList, Error, AuditLogList, AdminAuditLogsQueryKey>,
  "queryKey" | "queryFn"
>

/**
 * Component-side hook for the audit log list. Thin wrapper around
 * `useQuery(adminAuditLogsQueryOptions(filters, pagination))`.
 */
export const useAdminAuditLogsQuery = (
  filters: AdminAuditFilters,
  pagination: AdminAuditPagination,
  options?: UseAdminAuditLogsOptions
): UseQueryResult<AuditLogList, Error> =>
  useQuery({ ...adminAuditLogsQueryOptions(filters, pagination), ...options })

/**
 * Invalidate ALL admin audit log cache slots regardless of filters or
 * pagination. Used when the audit log has new entries and the user
 * should see them on next page load (rare; audit logs are append-only
 * + immutable from the user's perspective).
 */
export const invalidateAdminAuditLogs = async (queryClient: QueryClient) => {
  await queryClient.invalidateQueries({ queryKey: ["admin", "audit-logs"] })
}
