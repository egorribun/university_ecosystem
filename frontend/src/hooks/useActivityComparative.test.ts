import { describe, expect, it } from "vitest"
import { renderHook } from "@testing-library/react"

import { useActivityComparative, type ComparativeStats } from "./useActivityComparative"
import type { AttendanceStats, GradeStats, ParticipationStats } from "@/features/activity/types"

/**
 * Tests for the server-trend based comparative hook.
 *
 * The backend reports each metric for the selected window plus its `trend`
 * against the preceding window of the same length, so the previous value is
 * `current - trend` and the hook only derives the relative delta.
 */

function makeAttendance(percent: number, trend: number, total = 10): AttendanceStats {
  return {
    percent,
    present: Math.round((percent / 100) * total),
    total,
    trend,
    periodLabel: "30d",
    periodKey: "30d",
    recent: [],
  }
}

function makeGrades(average: number, trend: number, recentCount = 1): GradeStats {
  return {
    average,
    scale: "5",
    trend,
    recent: Array.from({ length: recentCount }, (_, index) => ({
      course: `c${index}`,
      score: average,
      date: "2026-05-10",
    })),
  }
}

function makeParticipation(events: number, trend: number): ParticipationStats {
  return { events, trend, recent: [] }
}

function run(
  attendance: AttendanceStats | null,
  grades: GradeStats | null,
  participation: ParticipationStats | null
): ComparativeStats {
  const { result } = renderHook(() => useActivityComparative(attendance, grades, participation))
  return result.current
}

describe("useActivityComparative — empty input", () => {
  it("reports no data and zeroed windows for null inputs", () => {
    const stats = run(null, null, null)
    expect(stats.hasData).toBe(false)
    expect(stats.attendance).toEqual({ current: 0, previous: 0, delta: 0 })
    expect(stats.grades).toEqual({ current: 0, previous: 0, delta: 0 })
    expect(stats.participation).toEqual({ current: 0, previous: 0, delta: 0 })
  })

  it("treats a window with zero totals as having no data", () => {
    expect(run(makeAttendance(0, 0, 0), makeGrades(0, 0, 0), makeParticipation(0, 0)).hasData).toBe(
      false
    )
  })
})

describe("useActivityComparative — hasData", () => {
  it("is true when attendance has records", () => {
    expect(run(makeAttendance(50, 0, 4), null, null).hasData).toBe(true)
  })

  it("is true when grades have recent entries", () => {
    expect(run(null, makeGrades(4, 0), null).hasData).toBe(true)
  })

  it("is true when participation has events", () => {
    expect(run(null, null, makeParticipation(2, 0)).hasData).toBe(true)
  })
})

describe("useActivityComparative — previous window from the server trend", () => {
  it("derives the previous attendance percent as current minus trend", () => {
    const { attendance } = run(makeAttendance(80, 20), null, null)
    expect(attendance.current).toBe(80)
    expect(attendance.previous).toBe(60)
    expect(attendance.delta).toBeCloseTo(33.333, 2)
  })

  it("derives the previous grade average and a negative delta", () => {
    const { grades } = run(null, makeGrades(4, -1), null)
    expect(grades.previous).toBe(5)
    expect(grades.delta).toBeCloseTo(-20, 5)
  })

  it("derives the previous participation count", () => {
    const { participation } = run(null, null, makeParticipation(5, 2))
    expect(participation).toEqual({ current: 5, previous: 3, delta: (2 / 3) * 100 })
  })

  it("clamps the previous value at zero and reports a 100% delta", () => {
    const { participation } = run(null, null, makeParticipation(3, 7))
    expect(participation.previous).toBe(0)
    expect(participation.delta).toBe(100)
  })

  it("reports zero delta when both windows are empty", () => {
    expect(run(makeAttendance(0, 0, 3), null, null).attendance.delta).toBe(0)
  })

  it("reports zero delta for an unchanged value", () => {
    expect(run(null, makeGrades(4.5, 0), null).grades.delta).toBe(0)
  })
})
