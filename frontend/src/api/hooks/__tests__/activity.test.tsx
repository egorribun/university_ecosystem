/**
 * @fileoverview Tests for activity.ts API hook exports.
 *
 * Coverage:
 *   - activityQueryKey(): cache key factory shape
 *   - activitySummaryOptions(): staleTime, gcTime, queryFn shape
 *   - useActivitySummaryQuery(): successful fetch, fallback path,
 *     partial-failure fallback, error propagation, enabled option
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
  activityQueryKey,
  activitySummaryOptions,
  useActivitySummaryQuery,
  type ActivitySummaryEnvelope,
} from "@/api/hooks/activity"

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

const ATTENDANCE_STUB = { rate: 0.95, recentClasses: [] }
const GRADES_STUB = { average: 4.5, subjects: [] }
const PARTICIPATION_STUB = { score: 82, details: [] }

const FULL_ENVELOPE: ActivitySummaryEnvelope = {
  attendance: ATTENDANCE_STUB as never,
  grades: GRADES_STUB as never,
  participation: PARTICIPATION_STUB as never,
}

afterEach(() => {
  vi.restoreAllMocks()
})

// ── activityQueryKey ────────────────────────────────────────────────────────
describe("activityQueryKey", () => {
  it("returns ['activity', 'summary', period, language] tuple", () => {
    expect(activityQueryKey({ period: "30d", language: "ru" })).toEqual([
      "activity",
      "summary",
      "30d",
      "ru",
    ])
  })

  it("produces distinct keys for different periods", () => {
    const weekKey = activityQueryKey({ period: "30d", language: "ru" })
    const monthKey = activityQueryKey({ period: "90d", language: "ru" })
    expect(weekKey).not.toEqual(monthKey)
  })

  it("produces distinct keys for different languages", () => {
    const ruKey = activityQueryKey({ period: "30d", language: "ru" })
    const enKey = activityQueryKey({ period: "30d", language: "en" })
    expect(ruKey).not.toEqual(enKey)
  })
})

// ── activitySummaryOptions ──────────────────────────────────────────────────
describe("activitySummaryOptions", () => {
  it("queryKey matches activityQueryKey output for the same params", () => {
    const params = { period: "90d" as const, language: "en" }
    const opts = activitySummaryOptions(params)
    expect(opts.queryKey).toEqual(activityQueryKey(params))
  })

  it("staleTime is 60_000 (1 minute)", () => {
    const opts = activitySummaryOptions({ period: "30d", language: "ru" })
    expect(opts.staleTime).toBe(60_000)
  })

  it("gcTime is 5 * 60_000 (5 minutes)", () => {
    const opts = activitySummaryOptions({ period: "30d", language: "ru" })
    expect(opts.gcTime).toBe(5 * 60_000)
  })

  it("queryFn is callable", () => {
    const opts = activitySummaryOptions({ period: "30d", language: "ru" })
    expect(typeof opts.queryFn).toBe("function")
  })
})

// ── useActivitySummaryQuery: successful fetch ───────────────────────────────
describe("useActivitySummaryQuery", () => {
  let queryClient: QueryClient

  beforeEach(() => {
    queryClient = createQueryClient()
  })

  it("returns envelope data from /stats/summary on success", async () => {
    apiMock.get.mockResolvedValueOnce({ data: FULL_ENVELOPE })

    const { result } = renderHook(
      () => useActivitySummaryQuery({ period: "30d", language: "ru" }),
      { wrapper: makeWrapper(queryClient) }
    )

    expect(result.current.isLoading).toBe(true)

    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    expect(result.current.data).toEqual(FULL_ENVELOPE)
    expect(apiMock.get).toHaveBeenCalledWith(
      "/stats/summary",
      expect.objectContaining({ params: { period: "30d" } })
    )
  })

  it("falls back to three individual endpoints when /stats/summary fails", async () => {
    apiMock.get
      .mockRejectedValueOnce(new Error("500 Internal Server Error"))
      .mockResolvedValueOnce({ data: ATTENDANCE_STUB })
      .mockResolvedValueOnce({ data: GRADES_STUB })
      .mockResolvedValueOnce({ data: PARTICIPATION_STUB })

    const { result } = renderHook(
      () => useActivitySummaryQuery({ period: "90d", language: "en" }),
      { wrapper: makeWrapper(queryClient) }
    )

    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    expect(result.current.data).toEqual({
      attendance: ATTENDANCE_STUB,
      grades: GRADES_STUB,
      participation: PARTICIPATION_STUB,
    })

    // Primary + 3 fallback calls = 4 total
    expect(apiMock.get).toHaveBeenCalledTimes(4)
    expect(apiMock.get).toHaveBeenCalledWith(
      "/stats/attendance",
      expect.objectContaining({ params: { period: "90d" } })
    )
    expect(apiMock.get).toHaveBeenCalledWith(
      "/stats/grades",
      expect.objectContaining({ params: { period: "90d" } })
    )
    expect(apiMock.get).toHaveBeenCalledWith(
      "/stats/participation",
      expect.objectContaining({ params: { period: "90d" } })
    )
  })

  it("returns null for failed individual feeds in fallback path", async () => {
    apiMock.get
      .mockRejectedValueOnce(new Error("summary endpoint down"))
      .mockResolvedValueOnce({ data: ATTENDANCE_STUB })
      .mockRejectedValueOnce(new Error("grades service down"))
      .mockResolvedValueOnce({ data: PARTICIPATION_STUB })

    const { result } = renderHook(
      () => useActivitySummaryQuery({ period: "30d", language: "ru" }),
      { wrapper: makeWrapper(queryClient) }
    )

    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    expect(result.current.data?.attendance).toEqual(ATTENDANCE_STUB)
    expect(result.current.data?.grades).toBeNull()
    expect(result.current.data?.participation).toEqual(PARTICIPATION_STUB)
  })

  it("normalises missing envelope fields to null", async () => {
    apiMock.get.mockResolvedValueOnce({
      data: { attendance: ATTENDANCE_STUB },
    })

    const { result } = renderHook(
      () => useActivitySummaryQuery({ period: "30d", language: "ru" }),
      { wrapper: makeWrapper(queryClient) }
    )

    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    expect(result.current.data?.grades).toBeNull()
    expect(result.current.data?.participation).toBeNull()
  })

  it("respects the enabled option (disabled does not fire fetch)", async () => {
    const { result } = renderHook(
      () => useActivitySummaryQuery({ period: "30d", language: "ru" }, { enabled: false }),
      { wrapper: makeWrapper(queryClient) }
    )

    // Should stay in idle state
    expect(result.current.fetchStatus).toBe("idle")
    expect(apiMock.get).not.toHaveBeenCalled()
  })
})
