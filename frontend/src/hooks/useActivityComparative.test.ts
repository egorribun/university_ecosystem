import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { renderHook } from "@testing-library/react"

import { useActivityComparative, type ComparativeStats } from "./useActivityComparative"
import type { AttendanceStats, GradeStats, ParticipationStats } from "@/features/activity/types"

/**
 * Tests for the period-split client-side comparative hook.
 *
 * The hook splits the configured period in half and compares the current
 * half to the previous half. Time-of-day boundaries matter (the cutoff
 * uses end-of-day at 23:59:59.999 today minus halfDays), so all tests
 * pin a fake clock at a known UTC instant via `vi.setSystemTime`.
 */

const FIXED_NOW = new Date("2026-05-15T12:00:00Z")
//        ↑ today's end-of-day in any tz lands on 2026-05-15T23:59:59.999 local

beforeEach(() => {
  vi.useFakeTimers()
  vi.setSystemTime(FIXED_NOW)
})

afterEach(() => {
  vi.useRealTimers()
})

function makeAttendance(
  records: Array<{ date: string; status: "present" | "absent" | "late" }>
): AttendanceStats {
  return {
    percent: 0,
    present: 0,
    total: 0,
    trend: 0,
    periodLabel: "",
    periodKey: "",
    recent: records,
  }
}

function makeGrades(records: Array<{ score: number; date: string }>): GradeStats {
  return {
    average: 0,
    scale: "100",
    trend: 0,
    recent: records.map((r) => ({ course: "x", score: r.score, date: r.date })),
  }
}

function makeParticipation(records: Array<{ date: string }>): ParticipationStats {
  return {
    events: 0,
    trend: 0,
    recent: records.map((r) => ({ title: "x", date: r.date })),
  }
}

function run(
  attendance: AttendanceStats | null,
  grades: GradeStats | null,
  participation: ParticipationStats | null,
  period: "30d" | "90d" | "180d" = "30d"
): ComparativeStats {
  const { result } = renderHook(() =>
    useActivityComparative(attendance, grades, participation, period)
  )
  return result.current
}

// ── Empty / missing inputs ──────────────────────────────────────────────────

describe("useActivityComparative — empty input", () => {
  it("returns zeroed stats and hasData=false for null inputs", () => {
    const stats = run(null, null, null)
    expect(stats.hasData).toBe(false)
    expect(stats.attendance).toEqual({ current: 0, previous: 0, delta: 0 })
    expect(stats.grades).toEqual({ current: 0, previous: 0, delta: 0 })
    expect(stats.participation).toEqual({ current: 0, previous: 0, delta: 0 })
  })

  it("returns zeroed stats and hasData=false for empty recent arrays", () => {
    const stats = run(makeAttendance([]), makeGrades([]), makeParticipation([]))
    expect(stats.hasData).toBe(false)
  })

  it("hasData=true when ANY recent array has entries", () => {
    const stats = run(makeAttendance([{ date: "2026-05-14", status: "present" }]), null, null)
    expect(stats.hasData).toBe(true)
  })
})

// ── Attendance: percent in current half vs previous half ────────────────────

describe("useActivityComparative — attendance", () => {
  it("computes 100% when all current-half records are present", () => {
    // 30d period → halfDays=15 → midpoint at 2026-04-30 23:59:59.999 (local).
    // Dates strictly AFTER midpoint are 'current half'.
    const stats = run(
      makeAttendance([
        { date: "2026-05-14", status: "present" }, // current half
        { date: "2026-05-10", status: "present" }, // current half
        { date: "2026-04-20", status: "present" }, // previous half
      ]),
      null,
      null
    )
    expect(stats.attendance.current).toBe(100)
    expect(stats.attendance.previous).toBe(100)
    expect(stats.attendance.delta).toBe(0)
  })

  it("computes 50% when half are absent in current period", () => {
    const stats = run(
      makeAttendance([
        { date: "2026-05-14", status: "present" },
        { date: "2026-05-10", status: "absent" },
        { date: "2026-04-20", status: "present" },
        { date: "2026-04-15", status: "present" },
      ]),
      null,
      null
    )
    expect(stats.attendance.current).toBe(50)
    expect(stats.attendance.previous).toBe(100)
    expect(stats.attendance.delta).toBe(-50) // 50% drop
  })

  it("treats 'late' as not-present for current-rate calculation", () => {
    const stats = run(
      makeAttendance([
        { date: "2026-05-14", status: "late" },
        { date: "2026-05-12", status: "present" },
      ]),
      null,
      null
    )
    expect(stats.attendance.current).toBe(50)
  })

  it("counts a previous-half absence without increasing the present total", () => {
    const stats = run(
      makeAttendance([
        { date: "2026-05-14", status: "present" },
        { date: "2026-04-20", status: "absent" },
      ]),
      null,
      null
    )
    expect(stats.attendance.previous).toBe(0)
  })
})

// ── Grades: average in current vs previous ──────────────────────────────────

describe("useActivityComparative — grades", () => {
  it("averages scores in each half", () => {
    const stats = run(
      null,
      makeGrades([
        { score: 90, date: "2026-05-14" }, // current
        { score: 80, date: "2026-05-10" }, // current
        { score: 70, date: "2026-04-15" }, // previous
        { score: 60, date: "2026-04-10" }, // previous
      ]),
      null
    )
    expect(stats.grades.current).toBe(85)
    expect(stats.grades.previous).toBe(65)
    // delta = (85 - 65) / 65 * 100 ≈ 30.77
    expect(stats.grades.delta).toBeCloseTo(30.77, 1)
  })

  it("returns 0/0/0 when no grades fall in either half", () => {
    const stats = run(null, makeGrades([]), null)
    expect(stats.grades).toEqual({ current: 0, previous: 0, delta: 0 })
  })
})

// ── Participation: event counts in current vs previous ─────────────────────

describe("useActivityComparative — participation", () => {
  it("counts events in each half", () => {
    const stats = run(
      null,
      null,
      makeParticipation([
        { date: "2026-05-13" }, // current
        { date: "2026-05-08" }, // current
        { date: "2026-04-10" }, // previous
      ])
    )
    expect(stats.participation.current).toBe(2)
    expect(stats.participation.previous).toBe(1)
    // delta = (2 - 1) / 1 * 100 = 100
    expect(stats.participation.delta).toBe(100)
  })
})

// ── Delta arithmetic edges ──────────────────────────────────────────────────

describe("useActivityComparative — delta arithmetic", () => {
  it("returns 100% delta when previous is 0 but current is positive", () => {
    const stats = run(
      null,
      null,
      makeParticipation([{ date: "2026-05-14" }]) // 1 current, 0 previous
    )
    expect(stats.participation.delta).toBe(100)
  })

  it("returns 0% delta when both halves are 0", () => {
    const stats = run(null, null, makeParticipation([]))
    expect(stats.participation.delta).toBe(0)
  })

  it("returns negative delta when current < previous", () => {
    const stats = run(
      null,
      null,
      makeParticipation([
        { date: "2026-04-10" }, // previous
        { date: "2026-04-09" }, // previous
        { date: "2026-04-08" }, // previous
        { date: "2026-04-07" }, // previous
      ])
    )
    // 0 current vs 4 previous → delta = (0 - 4) / 4 * 100 = -100
    expect(stats.participation.delta).toBe(-100)
  })
})

// ── Period scale: 90d / 180d ────────────────────────────────────────────────

describe("useActivityComparative — period scaling", () => {
  it("uses a wider midpoint for 90d", () => {
    // 90d/2 = 45 days → midpoint at 2026-03-31 23:59:59.999 local.
    const stats = run(
      null,
      null,
      makeParticipation([
        { date: "2026-05-01" }, // current half (after midpoint)
        { date: "2026-04-15" }, // current half
        { date: "2026-03-15" }, // previous half (before midpoint)
      ]),
      "90d"
    )
    expect(stats.participation.current).toBe(2)
    expect(stats.participation.previous).toBe(1)
  })

  it("uses an even wider midpoint for 180d", () => {
    // 180d/2 = 90 days → midpoint at 2026-02-14 23:59:59.999 local.
    const stats = run(
      null,
      null,
      makeParticipation([
        { date: "2026-04-01" }, // current half
        { date: "2026-03-01" }, // current half
        { date: "2026-01-15" }, // previous half
      ]),
      "180d"
    )
    expect(stats.participation.current).toBe(2)
    expect(stats.participation.previous).toBe(1)
  })
})
