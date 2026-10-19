import { describe, expect, it } from "vitest"

import {
  parseAttendanceRecent,
  parseAttendanceDaily,
  parseStreakDays,
  parseGradeRecent,
  parseParticipationRecent,
  toNumber,
} from "../parsers"
import { isGradeScale, isPeriodKey, periodDayCount } from "../types"

describe("activity parsers closure", () => {
  it("normalizes finite numbers and period/scale guards", () => {
    expect(toNumber("42")).toBe(42)
    expect(toNumber("not-a-number", 7)).toBe(7)
    expect(toNumber(Number.POSITIVE_INFINITY, 9)).toBe(9)
    expect(periodDayCount("30d")).toBe(30)
    expect(periodDayCount("90d")).toBe(90)
    expect(periodDayCount("180d")).toBe(180)
    expect(periodDayCount("365d" as never)).toBe(0)
    expect(isPeriodKey("30d")).toBe(true)
    expect(isPeriodKey("365d")).toBe(false)
    expect(isPeriodKey(30)).toBe(false)
    expect(isGradeScale("5")).toBe(true)
    expect(isGradeScale("100")).toBe(true)
    expect(isGradeScale("gpa")).toBe(true)
    expect(isGradeScale("percent")).toBe(false)
    expect(isGradeScale(null)).toBe(false)
  })

  it("filters and normalizes attendance records", () => {
    expect(parseAttendanceRecent(null)).toEqual([])
    expect(
      parseAttendanceRecent([
        null,
        4,
        {},
        { date: "", status: "present" },
        { date: "2026-01-01", status: "unknown" },
        { date: "2026-01-02", status: "present", course: "Math" },
        { date: "2026-01-03", status: "late", course: 42 },
        { date: "2026-01-04", status: "absent" },
      ])
    ).toEqual([
      { date: "2026-01-02", status: "present", course: "Math" },
      { date: "2026-01-03", status: "late" },
      { date: "2026-01-04", status: "absent" },
    ])
  })

  it("filters and normalizes grade records with optional max/date", () => {
    expect(parseGradeRecent("not-an-array")).toEqual([])
    expect(
      parseGradeRecent([
        null,
        { course: "", score: 5 },
        { course: 42, score: 1 },
        { course: "Math", score: "bad" },
        { course: "Physics", score: 4, max: 5, date: "2026-01-01" },
        { course: "History", score: "3", max: null, date: 42 },
        { course: "Art", score: 2, max: "bad" },
      ])
    ).toEqual([
      { course: "Physics", score: 4, max: 5, date: "2026-01-01" },
      { course: "History", score: 3, date: "" },
      { course: "Art", score: 2, date: "" },
    ])
  })

  it("filters and normalizes participation records and optional roles", () => {
    expect(parseParticipationRecent(undefined)).toEqual([])
    expect(
      parseParticipationRecent([
        null,
        { title: "" },
        { title: 42 },
        { title: "Hackathon", date: "2026-01-02", role: "participant" },
        { title: "Tournament", date: 42, role: 5 },
        { title: "Seminar" },
      ])
    ).toEqual([
      { title: "Hackathon", date: "2026-01-02", role: "participant" },
      { title: "Tournament", date: "" },
      { title: "Seminar", date: "" },
    ])
  })
})

describe("registration aggregate parsers", () => {
  it("retains valid leap days and rejects impossible or non-calendar dates", () => {
    const valid = { date: "2024-02-29", registered: 0, total: 2 }
    expect(
      parseAttendanceDaily([
        valid,
        { ...valid, date: "2026-02-29" },
        { ...valid, date: "2026-13-01" },
        { ...valid, date: "2026-04-20T00:00:00Z" },
        { ...valid, date: 20260420 },
        { ...valid, registered: "1" },
        { ...valid, total: 1.5 },
        { ...valid, total: Number.MAX_SAFE_INTEGER + 1 },
      ])
    ).toEqual([valid])
    expect(parseAttendanceDaily(undefined)).toEqual([])
    expect(parseAttendanceDaily({})).toEqual([])
  })

  it("accepts only safe nonnegative integer streak counts", () => {
    expect(parseStreakDays(0)).toBe(0)
    expect(parseStreakDays(36)).toBe(36)
    for (const value of [null, true, "3", -1, 0.5, Number.NaN, Infinity, 2 ** 53]) {
      expect(parseStreakDays(value)).toBeUndefined()
    }
  })
})
