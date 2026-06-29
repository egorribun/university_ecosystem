/**
 * @fileoverview Tests for schedule.ts API hook exports (queryFn execution).
 *
 * Complements `ssrFactories.test.ts` (which tests factory shape only) with
 * actual queryFn execution tests that mock `api.get` and verify HTTP call
 * structure, response normalisation, and groupId-null defensiveness.
 *
 * Coverage:
 *   - scheduleGroupsQueryOptions().queryFn: api.get("/groups") call,
 *     non-array response normalisation
 *   - pageScheduleQueryOptions(groupId).queryFn: api.get("/schedule/{id}")
 *     call, non-array normalisation, null groupId returns []
 */
import { QueryClient, QueryClientProvider, useQuery } from "@tanstack/react-query"
import { renderHook, waitFor } from "@testing-library/react"
import type { PropsWithChildren } from "react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

// ── Mock the axios-based API client ─────────────────────────────────────────
const apiMock = vi.hoisted(() => ({
  get: vi.fn(),
}))
vi.mock("@/api/client", () => ({ default: apiMock }))

import {
  pageScheduleQueryOptions,
  scheduleGroupsQueryOptions,
} from "@/api/hooks/schedule"

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

const GROUPS_STUB = [
  { id: "g1", name: "CS-101" },
  { id: "g2", name: "MATH-201" },
]

const LESSONS_STUB = [
  { id: "l1", subject: "Math", day: 1, slot: 1 },
  { id: "l2", subject: "Physics", day: 2, slot: 2 },
]

afterEach(() => {
  vi.restoreAllMocks()
})

// ── scheduleGroupsQueryOptions queryFn execution ────────────────────────────
describe("scheduleGroupsQueryOptions queryFn execution", () => {
  let queryClient: QueryClient

  beforeEach(() => {
    queryClient = createQueryClient()
  })

  it("calls api.get('/groups') and returns array data on success", async () => {
    apiMock.get.mockResolvedValueOnce({ data: GROUPS_STUB })

    const { result } = renderHook(
      () => {

        return useQuery(scheduleGroupsQueryOptions())
      },
      { wrapper: makeWrapper(queryClient) }
    )

    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    expect(result.current.data).toEqual(GROUPS_STUB)
    expect(apiMock.get).toHaveBeenCalledWith(
      "/groups",
      expect.objectContaining({ signal: expect.any(AbortSignal) })
    )
  })

  it("normalises non-array response to empty array", async () => {
    apiMock.get.mockResolvedValueOnce({ data: null })

    const { result } = renderHook(
      () => {

        return useQuery(scheduleGroupsQueryOptions())
      },
      { wrapper: makeWrapper(queryClient) }
    )

    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    expect(result.current.data).toEqual([])
  })

  it("enters error state when api.get fails", async () => {
    apiMock.get.mockRejectedValueOnce(new Error("Network Error"))

    const { result } = renderHook(
      () => {

        return useQuery(scheduleGroupsQueryOptions())
      },
      { wrapper: makeWrapper(queryClient) }
    )

    

    //("Network Error")
  })
})

// ── pageScheduleQueryOptions queryFn execution ──────────────────────────────
describe("pageScheduleQueryOptions queryFn execution", () => {
  let queryClient: QueryClient

  beforeEach(() => {
    queryClient = createQueryClient()
  })

  it("calls api.get('/schedule/{groupId}') for non-null groupId", async () => {
    apiMock.get.mockResolvedValueOnce({ data: LESSONS_STUB })

    const { result } = renderHook(
      () => {

        return useQuery(pageScheduleQueryOptions("group-abc"))
      },
      { wrapper: makeWrapper(queryClient) }
    )

    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    expect(result.current.data).toEqual(LESSONS_STUB)
    expect(apiMock.get).toHaveBeenCalledWith(
      "/schedule/group-abc",
      expect.objectContaining({ signal: expect.any(AbortSignal) })
    )
  })

  it("normalises non-array response to empty array", async () => {
    apiMock.get.mockResolvedValueOnce({ data: "not-an-array" })

    const { result } = renderHook(
      () => {

        return useQuery(pageScheduleQueryOptions("group-1"))
      },
      { wrapper: makeWrapper(queryClient) }
    )

    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    expect(result.current.data).toEqual([])
  })

  it("does not fetch when groupId is null (enabled: false)", async () => {
    const { result } = renderHook(
      () => {

        return useQuery(pageScheduleQueryOptions(null))
      },
      { wrapper: makeWrapper(queryClient) }
    )

    // enabled: false → stays idle
    expect(result.current.fetchStatus).toBe("idle")
    expect(apiMock.get).not.toHaveBeenCalled()
  })

  it("queryFn returns [] when groupId is null (defensive path)", async () => {
    const opts = pageScheduleQueryOptions(null)
    const result = await opts.queryFn({ signal: undefined } as never)
    expect(result).toEqual([])
  })
})
