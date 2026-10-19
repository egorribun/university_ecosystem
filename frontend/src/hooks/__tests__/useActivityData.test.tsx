import { renderHook } from "@testing-library/react"
import { vi, describe, it, expect, beforeEach } from "vitest"
import useActivityData from "../useActivityData"
import { useActivitySummaryQuery } from "@/api/hooks/activity"

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, _options?: unknown) => {
      if (key === "activity:period.labels.90d") return `90 days`
      if (key === "activity:period.options.90d") return `90 days option`
      if (key === "activity:fallback.attendance.recent") return []
      if (key === "activity:fallback.grades.recent") return []
      if (key === "activity:fallback.participation.recent") return []
      return key
    },
  }),
}))

vi.mock("@/contexts/LanguageContext", () => ({
  useLanguage: () => ({ language: "en" }),
  getLocaleForLanguage: () => "en-US",
}))

vi.mock("@/api/hooks/activity", () => ({
  useActivitySummaryQuery: vi.fn(),
}))

vi.mock("@/hooks/useURLState", () => ({
  useURLState: () => ({
    params: { p: "90d" },
    setParam: vi.fn(),
  }),
}))

describe("useActivityData", () => {
  const mockData = {
    attendance: {
      percent: 95,
      present: 19,
      total: 20,
      trend: 2.5,
      streak_days: 7,
      period_key: "90d",
      daily: [
        { date: "2026-04-21", registered: 0, total: 1 },
        { date: "2026-04-20", registered: 1, total: 2 },
      ],
      recent: [
        { date: "2026-04-20T10:00:00Z", status: "present" },
        { date: "2026-04-21T10:00:00Z", status: "present" },
      ],
    },
    grades: {
      average: 4.8,
      scale: "5",
      trend: 0.1,
      recent: [
        { date: "2026-04-20T10:00:00Z", course: "Math", score: 5 },
        { date: "2026-04-21T10:00:00Z", course: "Math", score: 4 },
      ],
    },
    participation: {
      events: 10,
      hours: 20,
      trend: 5.0,
      recent: [{ date: "2026-04-20T10:00:00Z", title: "Workshop" }],
    },
  }

  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(useActivitySummaryQuery).mockReturnValue({
      data: mockData,
      isFetching: false,
      isSuccess: true,
    } as unknown as ReturnType<typeof useActivitySummaryQuery>)
  })

  it("processes summary data correctly", () => {
    const { result } = renderHook(() => useActivityData())

    expect(result.current.attendance?.percent).toBe(95)
    expect(result.current.attendance).toMatchObject({ streakDays: 7 })
    expect(result.current.grades?.average).toBe(4.8)
    expect(result.current.participation?.events).toBe(10)
    expect(result.current.availability).toEqual({
      attendance: true,
      grades: true,
      participation: true,
    })
    expect(result.current.hasAnyData).toBe(true)
    expect(result.current.isPartial).toBe(false)
  })

  it("treats successful zero-valued summaries as an empty activity state", () => {
    vi.mocked(useActivitySummaryQuery).mockReturnValue({
      data: {
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
      },
      isFetching: false,
      isSuccess: true,
    } as unknown as ReturnType<typeof useActivitySummaryQuery>)

    const { result } = renderHook(() => useActivityData())

    expect(result.current.availability).toEqual({
      attendance: true,
      grades: true,
      participation: true,
    })
    expect(result.current.hasAnyData).toBe(false)
    expect(result.current.isPartial).toBe(false)
  })

  it("does not mistake an unavailable empty feed for a complete empty state", () => {
    vi.mocked(useActivitySummaryQuery).mockReturnValue({
      data: {
        attendance: null,
        grades: { average: 0, scale: "5", trend: 0, recent: [] },
        participation: { events: 0, hours: 0, groups: 0, trend: 0, recent: [] },
      },
      isFetching: false,
      isSuccess: true,
    } as unknown as ReturnType<typeof useActivitySummaryQuery>)

    const { result } = renderHook(() => useActivityData())

    expect(result.current.availability).toEqual({
      attendance: false,
      grades: true,
      participation: true,
    })
    expect(result.current.hasAnyData).toBe(false)
    expect(result.current.isPartial).toBe(true)
  })

  it("uses complete daily attendance aggregates instead of the recent sample", () => {
    const { result } = renderHook(() => useActivityData())

    // All recent rows are present, but they are not each day's denominator.
    expect(result.current.attendanceTrendData).toEqual([
      { date: "2026-04-20", value: 50 },
      { date: "2026-04-21", value: 0 },
    ])
    expect(result.current.gradesBySubject).toEqual([{ label: "Math", value: 4.5, max: 5 }])
  })

  it("does not synthesize trend points from recent rows without daily aggregates", () => {
    const recentOnlyAttendance = {
      percent: 95,
      present: 19,
      total: 20,
      trend: 2.5,
      period_key: "90d",
      recent: mockData.attendance.recent,
    }
    vi.mocked(useActivitySummaryQuery).mockReturnValue({
      data: { ...mockData, attendance: recentOnlyAttendance },
      isFetching: false,
      isSuccess: true,
    } as unknown as ReturnType<typeof useActivitySummaryQuery>)

    const { result } = renderHook(() => useActivityData())

    expect(result.current.attendanceTrendData).toEqual([])
  })

  it("retains zero-registration daily points when the recent feed is empty", () => {
    vi.mocked(useActivitySummaryQuery).mockReturnValue({
      data: {
        ...mockData,
        attendance: {
          ...mockData.attendance,
          present: 0,
          total: 1,
          percent: 0,
          recent: [],
          daily: [{ date: "2026-04-21", registered: 0, total: 1 }],
        },
      },
      isFetching: false,
      isSuccess: true,
    } as unknown as ReturnType<typeof useActivitySummaryQuery>)

    const { result } = renderHook(() => useActivityData())

    expect(result.current.attendanceTrendData).toEqual([{ date: "2026-04-21", value: 0 }])
  })

  it("rejects malformed daily counters without inventing percentages", () => {
    vi.mocked(useActivitySummaryQuery).mockReturnValue({
      data: {
        ...mockData,
        attendance: {
          ...mockData.attendance,
          daily: [
            null,
            5,
            {},
            { date: "not a date", registered: 1, total: 2 },
            { date: "2026-04-21", registered: -1, total: 2 },
            { date: "2026-04-21", registered: 3, total: 2 },
            { date: "2026-04-21", registered: 0, total: 0 },
            { date: "2026-04-21", registered: 0.5, total: 2 },
            { date: "2026-04-21", registered: Number.POSITIVE_INFINITY, total: 2 },
            { date: "2026-04-21", registered: 1, total: Number.NaN },
            { date: "2026-04-21", registered: 1, total: 2 },
          ],
        },
      },
      isFetching: false,
      isSuccess: true,
    } as unknown as ReturnType<typeof useActivitySummaryQuery>)

    const { result } = renderHook(() => useActivityData())

    expect(result.current.attendanceTrendData).toEqual([{ date: "2026-04-21", value: 50 }])
  })

  it.each([undefined, null, -1, 1.5, Number.NaN, Number.POSITIVE_INFINITY, true, "7"])(
    "does not invent an authoritative streak from invalid value %s",
    (streakDays) => {
      vi.mocked(useActivitySummaryQuery).mockReturnValue({
        data: { ...mockData, attendance: { ...mockData.attendance, streak_days: streakDays } },
        isFetching: false,
        isSuccess: true,
      } as unknown as ReturnType<typeof useActivitySummaryQuery>)

      const { result } = renderHook(() => useActivityData())

      expect(Reflect.get(result.current.attendance ?? {}, "streakDays")).toBeUndefined()
    }
  )

  it("treats the capped boundary day and earlier days as unknown, not zero", () => {
    const capped = Array.from({ length: 5 }, (_, index) => ({
      date: `2026-04-${String(20 - index).padStart(2, "0")}T10:00:00Z`,
      status: "present",
    }))
    vi.mocked(useActivitySummaryQuery).mockReturnValue({
      data: { ...mockData, attendance: { ...mockData.attendance, recent: capped } },
      isFetching: false,
      isSuccess: true,
    } as unknown as ReturnType<typeof useActivitySummaryQuery>)

    const { result } = renderHook(() => useActivityData())

    // April 16 may be truncated by the row cap; complete coverage starts the next day.
    expect(result.current.heatmapCoveredFrom).toBe("2026-04-17")
  })

  it("keeps the latest coverage boundary across several capped sections", () => {
    const dayAt = (day: number) => `2026-04-${String(day).padStart(2, "0")}T10:00:00Z`
    // Newest-first, as the backend returns the recent items.
    const newestFirst = (newest: number) => Array.from({ length: 5 }, (_, index) => newest - index)
    // Oldest-first, so the oldest item is not always the last one.
    const oldestFirst = (oldest: number) => Array.from({ length: 5 }, (_, index) => oldest + index)
    vi.mocked(useActivitySummaryQuery).mockReturnValue({
      data: {
        ...mockData,
        attendance: {
          ...mockData.attendance,
          recent: newestFirst(22).map((day) => ({ date: dayAt(day), status: "present" })),
        },
        grades: {
          ...mockData.grades,
          recent: oldestFirst(16).map((day) => ({ date: dayAt(day), course: "Math", score: 5 })),
        },
        participation: {
          ...mockData.participation,
          recent: newestFirst(24).map((day) => ({
            date: dayAt(day),
            title: "Workshop",
            role: "participant",
          })),
        },
      },
      isFetching: false,
      isSuccess: true,
    } as unknown as ReturnType<typeof useActivitySummaryQuery>)

    const { result } = renderHook(() => useActivityData())

    // Incomplete boundary days are April 18, 16 and 20; complete coverage starts April 21.
    expect(result.current.heatmapCoveredFrom).toBe("2026-04-21")
  })

  it("reports no coverage boundary while every section is complete", () => {
    const { result } = renderHook(() => useActivityData())

    expect(result.current.heatmapCoveredFrom).toBeNull()
  })

  it.each([
    { scale: "100", max: 100 },
    { scale: "gpa", max: 4 },
  ] as const)(
    "bounds subject grades by the sample's $scale scale when items carry no max",
    ({ scale, max }) => {
      vi.mocked(useActivitySummaryQuery).mockReturnValue({
        data: {
          ...mockData,
          grades: {
            average: 87,
            scale,
            trend: 0,
            recent: [{ date: "2026-04-20T10:00:00Z", course: "Math", score: 87, max: null }],
          },
        },
        isFetching: false,
        isSuccess: true,
      } as unknown as ReturnType<typeof useActivitySummaryQuery>)

      const { result } = renderHook(() => useActivityData())

      expect(result.current.gradesBySubject).toEqual([{ label: "Math", value: 87, max }])
    }
  )

  it("handles loading state correctly", () => {
    vi.mocked(useActivitySummaryQuery).mockReturnValue({
      data: undefined,
      isFetching: true,
      isSuccess: false,
    } as unknown as ReturnType<typeof useActivitySummaryQuery>)

    const { result } = renderHook(() => useActivityData())
    expect(result.current.loading).toBe(true)
    expect(result.current.attendance).toBeNull()
  })

  it("uses heatmap aggregation correctly", () => {
    const { result } = renderHook(() => useActivityData())

    // 20th has attendance, grade, participation -> 3
    // 21st has attendance, grade -> 2
    expect(result.current.heatmapData.get("2026-04-20")).toBe(3)
    expect(result.current.heatmapData.get("2026-04-21")).toBe(2)
  })

  it("preserves an honest empty state when the backend returns no data", () => {
    vi.mocked(useActivitySummaryQuery).mockReturnValue({
      data: null,
      isFetching: false,
      isSuccess: true,
    } as unknown as ReturnType<typeof useActivitySummaryQuery>)

    const { result } = renderHook(() => useActivityData())

    expect(result.current.attendance).toBeNull()
    expect(result.current.grades).toBeNull()
    expect(result.current.participation).toBeNull()
    expect(result.current.hasAnyData).toBe(false)
  })

  it("exposes query failure and a stable retry action", () => {
    const refetch = vi.fn()
    vi.mocked(useActivitySummaryQuery).mockReturnValue({
      data: undefined,
      isFetching: false,
      isSuccess: false,
      isError: true,
      error: new Error("offline"),
      refetch,
    } as unknown as ReturnType<typeof useActivitySummaryQuery>)

    const { result } = renderHook(() => useActivityData())
    expect(result.current.isError).toBe(true)
    expect(result.current.error).toEqual(new Error("offline"))
    expect(result.current.refetch).toBe(refetch)
  })

  it("exposes feed-level availability for a partial envelope", () => {
    vi.mocked(useActivitySummaryQuery).mockReturnValue({
      data: { ...mockData, attendance: null },
      isFetching: false,
      isSuccess: true,
      isError: false,
      error: null,
      refetch: vi.fn(),
    } as unknown as ReturnType<typeof useActivitySummaryQuery>)

    const { result } = renderHook(() => useActivityData())
    expect(result.current.attendance).toBeNull()
    expect(result.current.availability).toEqual({
      attendance: false,
      grades: true,
      participation: true,
    })
    expect(result.current.isPartial).toBe(true)
  })

  it("formats a campus calendar date without shifting it to the browser's previous day", () => {
    const original = Date.prototype.toLocaleDateString
    type DateFormatArgs = Parameters<Date["toLocaleDateString"]>
    function browserFormat(this: Date, ...[locales, options]: DateFormatArgs) {
      return original.call(this, locales, {
        ...options,
        timeZone: options?.timeZone ?? "America/Los_Angeles",
      })
    }
    const spy = vi.spyOn(Date.prototype, "toLocaleDateString").mockImplementation(browserFormat)
    try {
      const { result } = renderHook(() => useActivityData())

      expect(result.current.formatDate("2026-04-20")).toBe("April 20, 2026")
    } finally {
      spy.mockRestore()
    }
  })

  it("keeps a capped boundary day unknown despite complete daily attendance totals", () => {
    const recent = Array.from({ length: 5 }, (_, index) => ({
      date: `2026-04-20T${String(15 - index).padStart(2, "0")}:00:00+00:00`,
      status: "present",
      course: `Event ${index}`,
    }))
    vi.mocked(useActivitySummaryQuery).mockReturnValue({
      data: {
        attendance: {
          percent: 100,
          present: 6,
          total: 6,
          trend: 100,
          streak_days: 1,
          period_key: "90d",
          daily: [{ date: "2026-04-20", registered: 6, total: 6 }],
          recent,
        },
        grades: { average: 0, scale: "5", trend: 0, recent: [] },
        participation: {
          events: 6,
          hours: 6,
          groups: 1,
          trend: 6,
          recent: recent.map(({ date, course }) => ({
            date,
            title: course,
            role: "workshop",
          })),
        },
      },
      isFetching: false,
      isSuccess: true,
    } as unknown as ReturnType<typeof useActivitySummaryQuery>)

    const { result } = renderHook(() => useActivityData())

    expect(result.current.attendance?.daily).toEqual([
      { date: "2026-04-20", registered: 6, total: 6 },
    ])
    expect(result.current.attendance?.recent).toHaveLength(5)
    expect(result.current.participation?.events).toBe(6)
    expect(result.current.participation?.recent).toHaveLength(5)
    // Ten sampled contributions are not a complete count for this day.
    expect(result.current.heatmapData.get("2026-04-20")).toBe(10)
    expect(result.current.heatmapCoveredFrom).toBe("2026-04-21")
  })

  it.each(["not-a-date", "2026-04-31"])(
    "preserves the legacy boundary for malformed capped dates: %s",
    (date) => {
      vi.mocked(useActivitySummaryQuery).mockReturnValue({
        data: {
          ...mockData,
          attendance: {
            ...mockData.attendance,
            recent: Array.from({ length: 5 }, () => ({ date, status: "present" })),
          },
        },
        isFetching: false,
        isSuccess: true,
      } as unknown as ReturnType<typeof useActivitySummaryQuery>)

      const { result } = renderHook(() => useActivityData())

      expect(result.current.heatmapCoveredFrom).toBe(date.slice(0, 10))
    }
  )
})
