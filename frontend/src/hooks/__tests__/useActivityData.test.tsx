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
      period_key: "90d",
      recent: [
        { date: "2026-04-20T10:00:00Z", status: "present" },
        { date: "2026-04-21T10:00:00Z", status: "absent" },
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
    expect(result.current.grades?.average).toBe(4.8)
    expect(result.current.participation?.events).toBe(10)
    expect(result.current.availability).toEqual({
      attendance: true,
      grades: true,
      participation: true,
    })
    expect(result.current.isPartial).toBe(false)
  })

  it("derives chart data correctly", () => {
    const { result } = renderHook(() => useActivityData())

    // Attendance trend: one day present, one day absent
    expect(result.current.attendanceTrendData).toHaveLength(2)
    // 2026-04-20 is present (100%)
    expect(result.current.attendanceTrendData[0]!.value).toBe(100)
    // 2026-04-21 is absent (0%)
    expect(result.current.attendanceTrendData[1]!.value).toBe(0)

    // Grades by subject
    expect(result.current.gradesBySubject).toHaveLength(1)
    expect(result.current.gradesBySubject[0]!.label).toBe("Math")
    expect(result.current.gradesBySubject[0]!.value).toBe(4.5) // (5+4)/2
  })

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
})
