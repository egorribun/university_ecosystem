/**
 * @fileoverview Tests for adminFeatureFlags.ts API hook exports.
 *
 * Coverage:
 *   - adminFeatureFlagsQueryKey: static cache key
 *   - adminFeatureFlagsQueryOptions(): staleTime, gcTime, queryFn shape,
 *     non-array response normalisation
 *   - useAdminFeatureFlagsQuery(): success, loading, error states
 *   - updateFeatureFlagInCache(): optimistic cache update (merge, no-op
 *     on empty cache, no-op on non-array, name-scoped writes)
 *   - invalidateAdminFeatureFlags(): invalidation helper
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
  adminFeatureFlagsQueryKey,
  adminFeatureFlagsQueryOptions,
  invalidateAdminFeatureFlags,
  updateFeatureFlagInCache,
  useAdminFeatureFlagsQuery,
} from "@/api/hooks/adminFeatureFlags"
import type { FeatureFlag } from "@/types/Admin"

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

const buildFlag = (overrides: Partial<FeatureFlag> = {}): FeatureFlag =>
  ({
    name: overrides.name ?? "dark_mode",
    status: "enabled",
    percentage: 100,
    ...overrides,
  }) as FeatureFlag

afterEach(() => {
  vi.restoreAllMocks()
})

// ── adminFeatureFlagsQueryKey ───────────────────────────────────────────────
describe("adminFeatureFlagsQueryKey", () => {
  it("is the static tuple ['admin', 'feature-flags']", () => {
    expect(adminFeatureFlagsQueryKey).toEqual(["admin", "feature-flags"])
  })

  it("matches adminFeatureFlagsQueryOptions().queryKey reference identity", () => {
    expect(adminFeatureFlagsQueryOptions().queryKey).toBe(adminFeatureFlagsQueryKey)
  })
})

// ── adminFeatureFlagsQueryOptions ───────────────────────────────────────────
describe("adminFeatureFlagsQueryOptions", () => {
  it("staleTime is 30_000 (30 seconds)", () => {
    expect(adminFeatureFlagsQueryOptions().staleTime).toBe(30_000)
  })

  it("gcTime is 5 * 60_000 (5 minutes)", () => {
    expect(adminFeatureFlagsQueryOptions().gcTime).toBe(5 * 60_000)
  })

  it("queryFn is callable", () => {
    expect(typeof adminFeatureFlagsQueryOptions().queryFn).toBe("function")
  })
})

// ── useAdminFeatureFlagsQuery ───────────────────────────────────────────────
describe("useAdminFeatureFlagsQuery", () => {
  let queryClient: QueryClient

  beforeEach(() => {
    queryClient = createQueryClient()
  })

  it("fetches feature flags and returns data on success", async () => {
    const flags = [buildFlag({ name: "dark_mode" }), buildFlag({ name: "beta_feature" })]
    apiMock.get.mockResolvedValueOnce({ data: flags })

    const { result } = renderHook(() => useAdminFeatureFlagsQuery(), {
      wrapper: makeWrapper(queryClient),
    })

    expect(result.current.isLoading).toBe(true)

    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    expect(result.current.data).toEqual(flags)
    expect(apiMock.get).toHaveBeenCalledWith(
      "/admin/feature-flags",
      expect.objectContaining({ signal: expect.any(AbortSignal) })
    )
  })

  it("normalises non-array response to empty array", async () => {
    apiMock.get.mockResolvedValueOnce({ data: null })

    const { result } = renderHook(() => useAdminFeatureFlagsQuery(), {
      wrapper: makeWrapper(queryClient),
    })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    expect(result.current.data).toEqual([])
  })

  it("enters error state when API call fails", async () => {
    apiMock.get.mockRejectedValueOnce(new Error("500 Server Error"))

    const { result } = renderHook(() => useAdminFeatureFlagsQuery(), {
      wrapper: makeWrapper(queryClient),
    })

    await waitFor(() => expect(result.current.isError).toBe(true))

    expect(result.current.error?.message).toBe("500 Server Error")
  })

  it("respects the enabled option", async () => {
    const { result } = renderHook(() => useAdminFeatureFlagsQuery({ enabled: false }), {
      wrapper: makeWrapper(queryClient),
    })

    expect(result.current.fetchStatus).toBe("idle")
    expect(apiMock.get).not.toHaveBeenCalled()
  })
})

// ── updateFeatureFlagInCache ────────────────────────────────────────────────
describe("updateFeatureFlagInCache", () => {
  it("merges update into the matching flag by name", () => {
    const client = new QueryClient()
    const flag1 = buildFlag({ name: "f1", status: "disabled" })
    const flag2 = buildFlag({ name: "f2", status: "disabled" })
    client.setQueryData(adminFeatureFlagsQueryKey, [flag1, flag2])

    updateFeatureFlagInCache(client, "f1", { status: "enabled" })

    const after = client.getQueryData(adminFeatureFlagsQueryKey) as FeatureFlag[]
    expect(after).toHaveLength(2)
    expect(after[0]?.status).toBe("enabled")
    expect(after[1]?.status).toBe("disabled")
  })

  it("preserves untouched fields during partial update", () => {
    const client = new QueryClient()
    const flag = buildFlag({ name: "f1", status: "percentage", percentage: 50 })
    client.setQueryData(adminFeatureFlagsQueryKey, [flag])

    updateFeatureFlagInCache(client, "f1", { percentage: 75 })

    const after = client.getQueryData(adminFeatureFlagsQueryKey) as FeatureFlag[]
    expect(after[0]?.status).toBe("percentage")
    expect(after[0]?.percentage).toBe(75)
  })

  it("is a no-op when the cache slot is undefined", () => {
    const client = new QueryClient()
    updateFeatureFlagInCache(client, "f1", { status: "enabled" })
    expect(client.getQueryData(adminFeatureFlagsQueryKey)).toBeUndefined()
  })

  it("is a no-op when the cache slot is not an array (defensive)", () => {
    const client = new QueryClient()
    client.setQueryData(adminFeatureFlagsQueryKey, "corrupt" as unknown)
    updateFeatureFlagInCache(client, "f1", { status: "enabled" })
    expect(client.getQueryData(adminFeatureFlagsQueryKey)).toBe("corrupt")
  })

  it("does not modify flags that do not match the name", () => {
    const client = new QueryClient()
    const flag1 = buildFlag({ name: "keep_me", status: "disabled" })
    const flag2 = buildFlag({ name: "update_me", status: "disabled" })
    client.setQueryData(adminFeatureFlagsQueryKey, [flag1, flag2])

    updateFeatureFlagInCache(client, "update_me", { status: "enabled" })

    const after = client.getQueryData(adminFeatureFlagsQueryKey) as FeatureFlag[]
    expect(after[0]).toEqual(flag1)
    expect(after[1]?.status).toBe("enabled")
  })
})

// ── invalidateAdminFeatureFlags ─────────────────────────────────────────────
describe("invalidateAdminFeatureFlags", () => {
  it("invalidates the feature-flags cache slot", async () => {
    const client = new QueryClient()
    const spy = vi.spyOn(client, "invalidateQueries")

    await invalidateAdminFeatureFlags(client)

    expect(spy).toHaveBeenCalledWith({
      queryKey: adminFeatureFlagsQueryKey,
    })
  })

  it("returns the underlying invalidateQueries promise (awaitable)", async () => {
    const client = new QueryClient()
    const result = invalidateAdminFeatureFlags(client)
    expect(result).toBeInstanceOf(Promise)
    await expect(result).resolves.toBeUndefined()
  })
})
