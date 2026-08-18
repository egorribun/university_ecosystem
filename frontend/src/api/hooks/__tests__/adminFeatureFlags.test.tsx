/**
 * @fileoverview Tests for adminFeatureFlags.ts API hook exports.
 *
 * Coverage:
 *   - adminFeatureFlagsQueryKey: static cache key
 *   - adminFeatureFlagsQueryOptions(): staleTime, gcTime, queryFn shape,
 *     non-array response normalisation
 *   - useAdminFeatureFlagsQuery(): success, loading, error states
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

const buildFlag = (overrides: Partial<FeatureFlag> = {}): FeatureFlag => ({
  name: overrides.name ?? "dark_mode",
  enabled: true,
  default: false,
  description: "Test flag",
  provider: "flagd Provider",
  evaluation_reason: "DEFAULT",
  management: "gitops",
  config_path: "k8s/flagd/flags.json",
  ...overrides,
})

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
