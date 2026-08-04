import { act, renderHook, waitFor } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"

const mocks = vi.hoisted(() => {
  const translationMode = { value: "empty" as "empty" | "valid" }
  const t = vi.fn((key: string, options?: { returnObjects?: boolean }) => {
    if (options?.returnObjects && translationMode.value === "valid") {
      if (key === "activity:fallback.attendance.recent") {
        return [{ date: "2026-05-01", status: "present", course: "Math" }]
      }
      if (key === "activity:fallback.grades.recent") {
        return [{ date: "2026-05-01", course: "Math", score: 5, max: 5 }]
      }
      if (key === "activity:fallback.participation.recent") {
        return [{ date: "2026-05-01", title: "Workshop", role: "participant" }]
      }
    }
    return key
  })

  return {
    query: vi.fn(),
    setParam: vi.fn(),
    params: { p: "invalid" as string | undefined },
    translationMode,
    t,
  }
})

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: mocks.t }),
}))

vi.mock("@/contexts/LanguageContext", () => ({
  useLanguage: () => ({ language: "en" }),
  getLocaleForLanguage: () => "en-US",
}))

vi.mock("@/api/hooks/activity", () => ({
  useActivitySummaryQuery: () => mocks.query(),
}))

vi.mock("@/hooks/useURLState", () => ({
  useURLState: () => ({ params: mocks.params, setParam: mocks.setParam }),
}))

import useActivityData from "../useActivityData"

describe("useActivityData defensive derivation branches", () => {
  it("normalizes an invalid period, exposes period callbacks, and formats dates", () => {
    mocks.translationMode.value = "empty"
    mocks.params.p = "not-a-period"
    mocks.query.mockReturnValue({ data: undefined, isFetching: false, isSuccess: false })

    const { result } = renderHook(() => useActivityData())
    expect(result.current.period).toBe("90d")
    expect(result.current.periodOptions).toHaveLength(3)
    expect(result.current.formatDate()).toBe("")
    expect(result.current.formatDate("not-a-date")).toBe("")
    expect(result.current.formatDate("2026-05-01T00:00:00Z")).toContain("2026")
    expect(result.current.attendanceStatusLabel("late")).toContain("late")

    act(() => {
      result.current.setPeriod("30d")
      result.current.setPeriod("90d")
    })
    expect(mocks.setParam).toHaveBeenNthCalledWith(1, "p", "30d")
    expect(mocks.setParam).toHaveBeenNthCalledWith(2, "p", "")
  })

  it("uses defensive per-section fallbacks for malformed server fields", () => {
    mocks.params.p = "30d"
    mocks.query.mockReturnValue({
      data: {
        attendance: {
          percent: "bad",
          present: null,
          total: "10",
          trend: undefined,
          period_key: "bad",
          period_label: "   ",
          recent: null,
        },
        grades: { average: null, scale: "invalid", trend: null, recent: null },
        participation: { events: "4", hours: null, groups: null, trend: null, recent: null },
      },
      isFetching: false,
      isSuccess: true,
    })

    const { result } = renderHook(() => useActivityData())
    expect(result.current.period).toBe("30d")
    expect(result.current.attendance).toMatchObject({
      percent: 0,
      present: 0,
      total: 10,
      trend: 0,
      periodKey: "30d",
      periodLabel: "activity:period.labels.30d",
      recent: [],
    })
    expect(result.current.grades).toMatchObject({ average: 0, scale: "5", trend: 0 })
    expect(result.current.participation).toMatchObject({ events: 4, hours: undefined, groups: undefined })
  })

  it("parses non-empty translated fallback arrays after a successful empty response", async () => {
    mocks.params.p = "90d"
    mocks.translationMode.value = "valid"
    mocks.query.mockReturnValue({ data: null, isFetching: false, isSuccess: true })

    const { result } = renderHook(() => useActivityData())
    await waitFor(() => {
      expect(result.current.attendance?.recent).toHaveLength(1)
      expect(result.current.grades?.recent).toHaveLength(1)
      expect(result.current.participation?.recent).toHaveLength(1)
    })
    expect(result.current.heatmapData.get("2026-05-01")).toBe(3)
  })
})
