/**
 * @fileoverview Tests for adminAudit.ts API hook exports.
 *
 * Coverage:
 *   - adminAuditLogsQueryKey(): cache key factory shape with filters + pagination
 *   - adminAuditLogsQueryOptions(): staleTime, gcTime, queryFn shape,
 *     pagination offset conversion, filter omission
 *   - useAdminAuditLogsQuery(): success, loading, error states
 *   - invalidateAdminAuditLogs(): invalidation helper
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { renderHook, waitFor } from "@testing-library/react"
import type { PropsWithChildren } from "react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

// ── Mock the axios-based API client ─────────────────────────────────────────
const apiMock = vi.hoisted(() => ({
  get: vi.fn(),
}))
vi.mock("@/api/client", () => ({ default: apiMock }))

import {
  adminAuditLogsQueryKey,
  adminAuditLogsQueryOptions,
  invalidateAdminAuditLogs,
  useAdminAuditLogsQuery,
  type AdminAuditFilters,
  type AdminAuditPagination,
} from "@/api/hooks/adminAudit"

// ── Helpers ─────────────────────────────────────────────────────────────────
const makeWrapper = (queryClient: QueryClient) => {
  const Wrapper = ({ children }: PropsWithChildren) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  )
  return Wrapper
}

const createQueryClient = () =>
  new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  })

const EMPTY_FILTERS: AdminAuditFilters = { resource_type: "", action: "" }
const FILLED_FILTERS: AdminAuditFilters = {
  resource_type: "user",
  action: "update",
}
const DEFAULT_PAGINATION: AdminAuditPagination = { page: 0, rowsPerPage: 25 }

const AUDIT_LOG_STUB = {
  items: [
    {
      id: "log-1",
      resource_type: "user",
      action: "update",
      timestamp: "2026-06-28T10:00:00Z",
    },
  ],
  total: 1,
}

afterEach(() => {
  vi.restoreAllMocks()
})

// ── adminAuditLogsQueryKey ──────────────────────────────────────────────────
describe("adminAuditLogsQueryKey", () => {
  it("returns ['admin', 'audit-logs', filters, pagination] tuple", () => {
    const key = adminAuditLogsQueryKey(EMPTY_FILTERS, DEFAULT_PAGINATION)
    expect(key).toEqual(["admin", "audit-logs", EMPTY_FILTERS, DEFAULT_PAGINATION])
  })

  it("produces distinct keys for different filters", () => {
    const emptyKey = adminAuditLogsQueryKey(EMPTY_FILTERS, DEFAULT_PAGINATION)
    const filledKey = adminAuditLogsQueryKey(FILLED_FILTERS, DEFAULT_PAGINATION)
    expect(emptyKey).not.toEqual(filledKey)
  })

  it("produces distinct keys for different pagination", () => {
    const page0 = adminAuditLogsQueryKey(EMPTY_FILTERS, { page: 0, rowsPerPage: 25 })
    const page1 = adminAuditLogsQueryKey(EMPTY_FILTERS, { page: 1, rowsPerPage: 25 })
    expect(page0).not.toEqual(page1)
  })
})

// ── adminAuditLogsQueryOptions ──────────────────────────────────────────────
describe("adminAuditLogsQueryOptions", () => {
  it("queryKey matches adminAuditLogsQueryKey for same args", () => {
    const opts = adminAuditLogsQueryOptions(FILLED_FILTERS, DEFAULT_PAGINATION)
    expect(opts.queryKey).toEqual(adminAuditLogsQueryKey(FILLED_FILTERS, DEFAULT_PAGINATION))
  })

  it("staleTime is 30_000 (30 seconds)", () => {
    const opts = adminAuditLogsQueryOptions(EMPTY_FILTERS, DEFAULT_PAGINATION)
    expect(opts.staleTime).toBe(30_000)
  })

  it("gcTime is 5 * 60_000 (5 minutes)", () => {
    const opts = adminAuditLogsQueryOptions(EMPTY_FILTERS, DEFAULT_PAGINATION)
    expect(opts.gcTime).toBe(5 * 60_000)
  })

  it("queryFn is callable", () => {
    const opts = adminAuditLogsQueryOptions(EMPTY_FILTERS, DEFAULT_PAGINATION)
    expect(typeof opts.queryFn).toBe("function")
  })
})

// ── useAdminAuditLogsQuery ──────────────────────────────────────────────────
describe("useAdminAuditLogsQuery", () => {
  let queryClient: QueryClient

  beforeEach(() => {
    queryClient = createQueryClient()
  })

  it("fetches audit logs and returns data on success", async () => {
    apiMock.get.mockResolvedValueOnce({ data: AUDIT_LOG_STUB })

    const { result } = renderHook(() => useAdminAuditLogsQuery(EMPTY_FILTERS, DEFAULT_PAGINATION), {
      wrapper: makeWrapper(queryClient),
    })

    expect(result.current.isLoading).toBe(true)

    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    expect(result.current.data).toEqual(AUDIT_LOG_STUB)
  })

  it("converts page/rowsPerPage to limit/offset in API call", async () => {
    apiMock.get.mockResolvedValueOnce({ data: AUDIT_LOG_STUB })

    const pagination: AdminAuditPagination = { page: 2, rowsPerPage: 10 }
    const { result } = renderHook(() => useAdminAuditLogsQuery(EMPTY_FILTERS, pagination), {
      wrapper: makeWrapper(queryClient),
    })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    expect(apiMock.get).toHaveBeenCalledWith(
      "/admin/audit",
      expect.objectContaining({
        params: expect.objectContaining({ limit: 10, offset: 20 }),
      })
    )
  })

  it("omits empty filter values from API params", async () => {
    apiMock.get.mockResolvedValueOnce({ data: AUDIT_LOG_STUB })

    const { result } = renderHook(() => useAdminAuditLogsQuery(EMPTY_FILTERS, DEFAULT_PAGINATION), {
      wrapper: makeWrapper(queryClient),
    })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    const callParams = apiMock.get.mock.calls[0]?.[1]?.params as Record<string, unknown>
    expect(callParams).not.toHaveProperty("resource_type")
    expect(callParams).not.toHaveProperty("action")
  })

  it("includes non-empty filter values in API params", async () => {
    apiMock.get.mockResolvedValueOnce({ data: AUDIT_LOG_STUB })

    const { result } = renderHook(
      () => useAdminAuditLogsQuery(FILLED_FILTERS, DEFAULT_PAGINATION),
      { wrapper: makeWrapper(queryClient) }
    )

    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    expect(apiMock.get).toHaveBeenCalledWith(
      "/admin/audit",
      expect.objectContaining({
        params: expect.objectContaining({
          resource_type: "user",
          action: "update",
        }),
      })
    )
  })

  it("enters error state when API call fails", async () => {
    apiMock.get.mockRejectedValueOnce(new Error("403 Forbidden"))

    const { result } = renderHook(() => useAdminAuditLogsQuery(EMPTY_FILTERS, DEFAULT_PAGINATION), {
      wrapper: makeWrapper(queryClient),
    })

    await waitFor(() => expect(result.current.isError).toBe(true))

    expect(result.current.error).toBeInstanceOf(Error)
    expect(result.current.error?.message).toBe("403 Forbidden")
  })

  it("respects the enabled option", async () => {
    const { result } = renderHook(
      () =>
        useAdminAuditLogsQuery(EMPTY_FILTERS, DEFAULT_PAGINATION, {
          enabled: false,
        }),
      { wrapper: makeWrapper(queryClient) }
    )

    expect(result.current.fetchStatus).toBe("idle")
    expect(apiMock.get).not.toHaveBeenCalled()
  })
})

// ── invalidateAdminAuditLogs ────────────────────────────────────────────────
describe("invalidateAdminAuditLogs", () => {
  it("invalidates all audit-log cache slots via prefix match", async () => {
    const client = new QueryClient()
    const spy = vi.spyOn(client, "invalidateQueries")

    await invalidateAdminAuditLogs(client)

    expect(spy).toHaveBeenCalledWith({
      queryKey: ["admin", "audit-logs"],
    })
  })

  it("returns the underlying invalidateQueries promise (awaitable)", async () => {
    const client = new QueryClient()
    const result = invalidateAdminAuditLogs(client)
    expect(result).toBeInstanceOf(Promise)
    await expect(result).resolves.toBeUndefined()
  })
})
