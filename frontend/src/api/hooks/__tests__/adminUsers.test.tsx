/**
 * @fileoverview Tests for adminUsers.ts API hook exports.
 *
 * Coverage:
 *   - adminUsersQueryKey(): cache key factory shape with filters
 *   - adminGroupsQueryKey: static cache key
 *   - adminUsersQueryOptions(): staleTime, gcTime, queryFn shape,
 *     filter omission for empty values, non-array normalisation
 *   - adminGroupsQueryOptions(): queryFn shape, non-array normalisation
 *   - useAdminUsersQuery(): success, loading, error, enabled states
 *   - useAdminGroupsQuery(): success, error states
 *   - invalidateAdminUsers(): scoped invalidation
 *   - invalidateAllAdminUsers(): prefix-match invalidation
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
  adminGroupsQueryKey,
  adminGroupsQueryOptions,
  adminUsersQueryKey,
  adminUsersQueryOptions,
  invalidateAdminUsers,
  invalidateAllAdminUsers,
  useAdminGroupsQuery,
  useAdminUsersQuery,
  type AdminUser,
  type AdminUserFilters,
  type Group,
} from "@/api/hooks/adminUsers"

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

const EMPTY_FILTERS: AdminUserFilters = {
  full_name: "",
  group_id: "",
  role: "",
}

const FILLED_FILTERS: AdminUserFilters = {
  full_name: "John",
  group_id: "group-1",
  role: "student",
}

const USERS_STUB: AdminUser[] = [
  {
    id: "u1",
    full_name: "John Doe",
    email: "john@example.com",
    role: "student",
    group_id: "group-1",
  },
]

const GROUPS_STUB: Group[] = [
  { id: "g1", name: "CS-101" },
  { id: "g2", name: "MATH-201" },
]

afterEach(() => {
  vi.restoreAllMocks()
})

// ── adminUsersQueryKey ──────────────────────────────────────────────────────
describe("adminUsersQueryKey", () => {
  it("returns ['admin', 'users', filters] tuple", () => {
    const key = adminUsersQueryKey(EMPTY_FILTERS)
    expect(key).toEqual(["admin", "users", EMPTY_FILTERS])
  })

  it("produces distinct keys for different filters", () => {
    const emptyKey = adminUsersQueryKey(EMPTY_FILTERS)
    const filledKey = adminUsersQueryKey(FILLED_FILTERS)
    expect(emptyKey).not.toEqual(filledKey)
  })

  it("preserves empty-string filter values in the key (no stripping)", () => {
    const key = adminUsersQueryKey(EMPTY_FILTERS)
    expect(key[2]).toEqual({ full_name: "", group_id: "", role: "" })
  })
})

// ── adminGroupsQueryKey ─────────────────────────────────────────────────────
describe("adminGroupsQueryKey", () => {
  it("is the static tuple ['admin', 'groups']", () => {
    expect(adminGroupsQueryKey).toEqual(["admin", "groups"])
  })

  it("matches adminGroupsQueryOptions().queryKey reference identity", () => {
    expect(adminGroupsQueryOptions().queryKey).toBe(adminGroupsQueryKey)
  })
})

// ── adminUsersQueryOptions ──────────────────────────────────────────────────
describe("adminUsersQueryOptions", () => {
  it("queryKey matches adminUsersQueryKey for same filters", () => {
    const opts = adminUsersQueryOptions(FILLED_FILTERS)
    expect(opts.queryKey).toEqual(adminUsersQueryKey(FILLED_FILTERS))
  })

  it("staleTime is 30_000 (30 seconds)", () => {
    expect(adminUsersQueryOptions(EMPTY_FILTERS).staleTime).toBe(30_000)
  })

  it("gcTime is 5 * 60_000 (5 minutes)", () => {
    expect(adminUsersQueryOptions(EMPTY_FILTERS).gcTime).toBe(5 * 60_000)
  })

  it("queryFn is callable", () => {
    expect(typeof adminUsersQueryOptions(EMPTY_FILTERS).queryFn).toBe("function")
  })
})

// ── adminGroupsQueryOptions ─────────────────────────────────────────────────
describe("adminGroupsQueryOptions", () => {
  it("staleTime is 30_000 (30 seconds)", () => {
    expect(adminGroupsQueryOptions().staleTime).toBe(30_000)
  })

  it("gcTime is 5 * 60_000 (5 minutes)", () => {
    expect(adminGroupsQueryOptions().gcTime).toBe(5 * 60_000)
  })

  it("queryFn is callable", () => {
    expect(typeof adminGroupsQueryOptions().queryFn).toBe("function")
  })
})

// ── useAdminUsersQuery ──────────────────────────────────────────────────────
describe("useAdminUsersQuery", () => {
  let queryClient: QueryClient

  beforeEach(() => {
    queryClient = createQueryClient()
  })

  it("fetches users and returns data on success", async () => {
    apiMock.get.mockResolvedValueOnce({ data: USERS_STUB })

    const { result } = renderHook(() => useAdminUsersQuery(EMPTY_FILTERS), {
      wrapper: makeWrapper(queryClient),
    })

    expect(result.current.isLoading).toBe(true)

    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    expect(result.current.data).toEqual(USERS_STUB)
  })

  it("omits empty filter values from API params", async () => {
    apiMock.get.mockResolvedValueOnce({ data: USERS_STUB })

    const { result } = renderHook(() => useAdminUsersQuery(EMPTY_FILTERS), {
      wrapper: makeWrapper(queryClient),
    })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    const callParams = apiMock.get.mock.calls[0]?.[1]?.params as Record<string, unknown>
    expect(callParams).not.toHaveProperty("full_name")
    expect(callParams).not.toHaveProperty("group_id")
    expect(callParams).not.toHaveProperty("role")
  })

  it("includes non-empty filter values in API params", async () => {
    apiMock.get.mockResolvedValueOnce({ data: USERS_STUB })

    const { result } = renderHook(() => useAdminUsersQuery(FILLED_FILTERS), {
      wrapper: makeWrapper(queryClient),
    })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    expect(apiMock.get).toHaveBeenCalledWith(
      "/users",
      expect.objectContaining({
        params: expect.objectContaining({
          full_name: "John",
          group_id: "group-1",
          role: "student",
        }),
      })
    )
  })

  it("normalises non-array response to empty array", async () => {
    apiMock.get.mockResolvedValueOnce({ data: null })

    const { result } = renderHook(() => useAdminUsersQuery(EMPTY_FILTERS), {
      wrapper: makeWrapper(queryClient),
    })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    expect(result.current.data).toEqual([])
  })

  it("enters error state when API call fails", async () => {
    apiMock.get.mockRejectedValueOnce(new Error("Network Error"))

    const { result } = renderHook(() => useAdminUsersQuery(EMPTY_FILTERS), {
      wrapper: makeWrapper(queryClient),
    })

    await waitFor(() => expect(result.current.isError).toBe(true))

    expect(result.current.error?.message).toBe("Network Error")
  })

  it("respects the enabled option", async () => {
    const { result } = renderHook(() => useAdminUsersQuery(EMPTY_FILTERS, { enabled: false }), {
      wrapper: makeWrapper(queryClient),
    })

    expect(result.current.fetchStatus).toBe("idle")
    expect(apiMock.get).not.toHaveBeenCalled()
  })
})

// ── useAdminGroupsQuery ─────────────────────────────────────────────────────
describe("useAdminGroupsQuery", () => {
  let queryClient: QueryClient

  beforeEach(() => {
    queryClient = createQueryClient()
  })

  it("fetches groups and returns data on success", async () => {
    apiMock.get.mockResolvedValueOnce({ data: GROUPS_STUB })

    const { result } = renderHook(() => useAdminGroupsQuery(), {
      wrapper: makeWrapper(queryClient),
    })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    expect(result.current.data).toEqual(GROUPS_STUB)
    expect(apiMock.get).toHaveBeenCalledWith(
      "/groups",
      expect.objectContaining({ signal: expect.any(AbortSignal) })
    )
  })

  it("normalises non-array response to empty array", async () => {
    apiMock.get.mockResolvedValueOnce({ data: "not-an-array" })

    const { result } = renderHook(() => useAdminGroupsQuery(), {
      wrapper: makeWrapper(queryClient),
    })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    expect(result.current.data).toEqual([])
  })

  it("enters error state when API call fails", async () => {
    apiMock.get.mockRejectedValueOnce(new Error("403 Forbidden"))

    const { result } = renderHook(() => useAdminGroupsQuery(), {
      wrapper: makeWrapper(queryClient),
    })

    await waitFor(() => expect(result.current.isError).toBe(true))

    expect(result.current.error?.message).toBe("403 Forbidden")
  })
})

// ── invalidateAdminUsers ────────────────────────────────────────────────────
describe("invalidateAdminUsers", () => {
  it("invalidates the specific filter-scoped cache slot", async () => {
    const client = new QueryClient()
    const spy = vi.spyOn(client, "invalidateQueries")

    await invalidateAdminUsers(client, FILLED_FILTERS)

    expect(spy).toHaveBeenCalledWith({
      queryKey: adminUsersQueryKey(FILLED_FILTERS),
    })
  })

  it("returns the underlying invalidateQueries promise (awaitable)", async () => {
    const client = new QueryClient()
    const result = invalidateAdminUsers(client, EMPTY_FILTERS)
    expect(result).toBeInstanceOf(Promise)
    await expect(result).resolves.toBeUndefined()
  })
})

// ── invalidateAllAdminUsers ─────────────────────────────────────────────────
describe("invalidateAllAdminUsers", () => {
  it("invalidates all admin user cache slots via prefix match", async () => {
    const client = new QueryClient()
    const spy = vi.spyOn(client, "invalidateQueries")

    await invalidateAllAdminUsers(client)

    expect(spy).toHaveBeenCalledWith({ queryKey: ["admin", "users"] })
  })

  it("returns the underlying invalidateQueries promise (awaitable)", async () => {
    const client = new QueryClient()
    const result = invalidateAllAdminUsers(client)
    expect(result).toBeInstanceOf(Promise)
    await expect(result).resolves.toBeUndefined()
  })
})
