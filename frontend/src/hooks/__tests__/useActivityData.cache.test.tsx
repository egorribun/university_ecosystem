import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { act, renderHook, waitFor } from "@testing-library/react"
import type { PropsWithChildren } from "react"
import { describe, expect, it, vi } from "vitest"

import { activityQueryKey, type ActivitySummaryEnvelope } from "@/api/hooks/activity"
import useActivityData from "../useActivityData"

vi.mock("@/contexts/LanguageContext", () => ({
  useLanguage: () => ({ language: "en" }),
  getLocaleForLanguage: () => "en-US",
}))

vi.mock("@/hooks/useURLState", () => ({
  useURLState: () => ({ params: { p: "90d" }, setParam: () => undefined }),
}))

const queryKey = activityQueryKey({ period: "90d", language: "en" })

const emptySummary = (): ActivitySummaryEnvelope => ({
  attendance: {
    percent: 0,
    present: 0,
    total: 0,
    trend: 0,
    period_key: "90d",
    recent: [],
  },
  grades: { average: 0, scale: "5", trend: 0, recent: [] },
  participation: { events: 0, hours: 0, groups: 0, trend: 0, recent: [] },
})

const populatedSummary = (): ActivitySummaryEnvelope => ({
  attendance: {
    percent: 100,
    present: 3,
    total: 3,
    trend: 25,
    period_key: "90d",
    recent: [
      { date: "2026-05-02T10:00:00Z", status: "present", course: "Physics" },
      { date: "2026-05-01T15:00:00Z", status: "present", course: "Math" },
      { date: "2026-05-01T09:00:00Z", status: "present", course: "Literature" },
    ],
  },
  grades: {
    average: 4,
    scale: "5",
    trend: 1,
    recent: [
      { date: "2026-05-02T11:00:00Z", course: "Math", score: 5, max: null },
      { date: "2026-05-01T11:00:00Z", course: "Math", score: 3, max: null },
    ],
  },
  participation: {
    events: 1,
    hours: 2,
    groups: 1,
    trend: 1,
    recent: [{ date: "2026-05-02T14:00:00Z", title: "Workshop", role: "participant" }],
  },
})

type ActivityHook = ReturnType<typeof useActivityData>

async function withCachedSummary(
  summary: ActivitySummaryEnvelope,
  check: (result: { current: ActivityHook }, client: QueryClient) => void | Promise<void>
) {
  // A fresh cache entry uses the actual summary query's one-minute stale window.
  // No query hook is mocked, and this test owns the entire client lifecycle.
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const Wrapper = ({ children }: PropsWithChildren) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  )
  let unmount: (() => void) | undefined
  try {
    client.setQueryData<ActivitySummaryEnvelope>(queryKey, summary)
    const view = renderHook(() => useActivityData(), { wrapper: Wrapper })
    unmount = view.unmount
    await check(view.result, client)
  } finally {
    try {
      unmount?.()
    } finally {
      try {
        await client.cancelQueries()
      } finally {
        client.clear()
      }
    }
  }
}

describe("useActivityData cached summary contracts", () => {
  it("refreshes summaries and derived charts when a cached empty summary gains activity", async () => {
    await withCachedSummary(emptySummary(), async (result, client) => {
      expect(result.current).toMatchObject({
        loading: false,
        hasInitiallyLoaded: true,
        hasAnyData: false,
        isPartial: false,
        isError: false,
        availability: { attendance: true, grades: true, participation: true },
        attendanceTrendData: [],
        gradesBySubject: [],
      })
      expect(result.current.heatmapData.size).toBe(0)

      act(() => {
        client.setQueryData<ActivitySummaryEnvelope>(queryKey, populatedSummary())
      })

      await waitFor(
        () => {
          expect(result.current.attendance).toMatchObject({
            percent: 100,
            present: 3,
            total: 3,
            trend: 25,
            periodKey: "90d",
          })
          expect(result.current.grades).toMatchObject({ average: 4, scale: "5", trend: 1 })
          expect(result.current.participation).toMatchObject({
            events: 1,
            hours: 2,
            groups: 1,
            trend: 1,
          })
          expect(result.current.attendanceTrendData).toEqual([
            { date: "2026-05-01", value: 100 },
            { date: "2026-05-02", value: 100 },
          ])
          expect(result.current.gradesBySubject).toEqual([{ label: "Math", value: 4, max: 5 }])
          expect([...result.current.heatmapData.entries()].sort()).toEqual([
            ["2026-05-01", 3],
            ["2026-05-02", 3],
          ])
          expect(result.current.hasAnyData).toBe(true)
        },
        { timeout: 1_000 }
      )

      // A later empty response must also remove the previous charts and totals.
      act(() => {
        client.setQueryData<ActivitySummaryEnvelope>(queryKey, emptySummary())
      })
      await waitFor(
        () => {
          expect(result.current.attendance).toMatchObject({ present: 0, total: 0, recent: [] })
          expect(result.current.grades).toMatchObject({ average: 0, recent: [] })
          expect(result.current.participation).toMatchObject({
            events: 0,
            hours: 0,
            groups: 0,
            recent: [],
          })
          expect(result.current.attendanceTrendData).toEqual([])
          expect(result.current.gradesBySubject).toEqual([])
          expect(result.current.heatmapData.size).toBe(0)
          expect(result.current.hasAnyData).toBe(false)
          expect(result.current.isPartial).toBe(false)
        },
        { timeout: 1_000 }
      )
    })
  })

  it.each(["attendance", "grades", "participation"] as const)(
    "keeps activity visible when %s is the only available feed",
    async (feed) => {
      const populated = populatedSummary()
      const summary: ActivitySummaryEnvelope = {
        attendance: null,
        grades: null,
        participation: null,
        [feed]: populated[feed],
      }
      await withCachedSummary(summary, (result) => {
        expect(result.current.hasInitiallyLoaded).toBe(true)
        expect(result.current.hasAnyData).toBe(true)
        expect(result.current.isPartial).toBe(true)
        expect(result.current.isError).toBe(false)
        expect(result.current.availability).toEqual({
          attendance: feed === "attendance",
          grades: feed === "grades",
          participation: feed === "participation",
        })
        for (const unavailable of ["attendance", "grades", "participation"] as const) {
          if (unavailable !== feed) expect(result.current[unavailable]).toBeNull()
        }
      })
    }
  )

  it.each(["attendance", "grades", "participation"] as const)(
    "distinguishes a successful empty %s feed from the two unavailable feeds",
    async (feed) => {
      const empty = emptySummary()
      const summary: ActivitySummaryEnvelope = {
        attendance: null,
        grades: null,
        participation: null,
        [feed]: empty[feed],
      }
      await withCachedSummary(summary, (result) => {
        expect(result.current.hasInitiallyLoaded).toBe(true)
        expect(result.current.hasAnyData).toBe(false)
        expect(result.current.isPartial).toBe(true)
        expect(result.current.availability).toEqual({
          attendance: feed === "attendance",
          grades: feed === "grades",
          participation: feed === "participation",
        })
        expect(result.current.attendanceTrendData).toEqual([])
        expect(result.current.gradesBySubject).toEqual([])
        expect(result.current.heatmapData.size).toBe(0)
      })
    }
  )
})
