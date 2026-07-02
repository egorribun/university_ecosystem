import { describe, expect, it, vi } from "vitest"

const mocks = vi.hoisted(() => ({
  parseMinutes: vi.fn((s: string | null | undefined): number | null => {
    if (!s) return null
    const match = /(\d{2}):(\d{2})/.exec(s)
    if (match) {
      const h = Number(match[1])
      const m = Number(match[2])
      if (h >= 0 && h <= 23 && m >= 0 && m <= 59) return h * 60 + m
    }
    return null
  }),
  getTimeStr: vi.fn((lesson: { start_time: string | null }) => {
    if (!lesson?.start_time) return ""
    const match = /(\d{2}):(\d{2})/.exec(lesson.start_time)
    return match ? `${match[1]}:${match[2]}` : ""
  }),
}))

vi.mock("@/components/schedule/scheduleUtils", () => ({
  parseMinutes: mocks.parseMinutes,
  getTimeStr: mocks.getTimeStr,
}))

import { detectConflicts } from "@/utils/scheduleConflicts"

type TestLesson = {
  id: string
  weekday: string
  parity: "both"
  start_time: string | null
  end_time: string | null
}

const makeLesson = (overrides: Partial<TestLesson> & { id: string }): TestLesson => ({
  weekday: "Monday",
  parity: "both",
  start_time: "09:00",
  end_time: "10:30",
  ...overrides,
})

describe("scheduleConflicts — detectConflicts", () => {
  it("returns empty set for empty lessons array", () => {
    const result = detectConflicts([])
    expect(result.size).toBe(0)
  })

  it("returns empty set for a single lesson", () => {
    const result = detectConflicts([makeLesson({ id: "1" })])
    expect(result.size).toBe(0)
  })

  it("returns empty set when lessons are on different days", () => {
    const lessons = [
      makeLesson({ id: "1", weekday: "Monday", start_time: "09:00", end_time: "10:30" }),
      makeLesson({ id: "2", weekday: "Tuesday", start_time: "09:00", end_time: "10:30" }),
    ]
    const result = detectConflicts(lessons)
    expect(result.size).toBe(0)
  })

  it("returns empty set for adjacent (non-overlapping) lessons", () => {
    const lessons = [
      makeLesson({ id: "1", weekday: "Monday", start_time: "09:00", end_time: "10:30" }),
      makeLesson({ id: "2", weekday: "Monday", start_time: "10:30", end_time: "12:00" }),
    ]
    const result = detectConflicts(lessons)
    expect(result.size).toBe(0)
  })

  it("detects two overlapping lessons on the same day", () => {
    const lessons = [
      makeLesson({ id: "1", weekday: "Monday", start_time: "09:00", end_time: "10:30" }),
      makeLesson({ id: "2", weekday: "Monday", start_time: "10:00", end_time: "11:30" }),
    ]
    const result = detectConflicts(lessons)
    expect(result.has("1")).toBe(true)
    expect(result.has("2")).toBe(true)
  })

  it("detects fully contained lesson as conflict", () => {
    const lessons = [
      makeLesson({ id: "1", weekday: "Monday", start_time: "09:00", end_time: "12:00" }),
      makeLesson({ id: "2", weekday: "Monday", start_time: "10:00", end_time: "11:00" }),
    ]
    const result = detectConflicts(lessons)
    expect(result.has("1")).toBe(true)
    expect(result.has("2")).toBe(true)
  })

  it("detects multiple conflicts among three lessons", () => {
    const lessons = [
      makeLesson({ id: "1", weekday: "Monday", start_time: "09:00", end_time: "10:30" }),
      makeLesson({ id: "2", weekday: "Monday", start_time: "10:00", end_time: "11:30" }),
      makeLesson({ id: "3", weekday: "Monday", start_time: "11:00", end_time: "12:30" }),
    ]
    const result = detectConflicts(lessons)
    // 1 overlaps with 2, 2 overlaps with 3
    expect(result.has("1")).toBe(true)
    expect(result.has("2")).toBe(true)
    expect(result.has("3")).toBe(true)
  })

  it("only flags lessons that actually overlap (not unrelated ones)", () => {
    const lessons = [
      makeLesson({ id: "1", weekday: "Monday", start_time: "09:00", end_time: "10:00" }),
      makeLesson({ id: "2", weekday: "Monday", start_time: "09:30", end_time: "10:30" }),
      makeLesson({ id: "3", weekday: "Monday", start_time: "14:00", end_time: "15:30" }),
    ]
    const result = detectConflicts(lessons)
    expect(result.has("1")).toBe(true)
    expect(result.has("2")).toBe(true)
    expect(result.has("3")).toBe(false)
  })

  it("skips lessons with null start_time or end_time", () => {
    const lessons = [
      makeLesson({ id: "1", weekday: "Monday", start_time: "09:00", end_time: "10:30" }),
      makeLesson({ id: "2", weekday: "Monday", start_time: null, end_time: "11:30" }),
    ]
    const result = detectConflicts(lessons)
    expect(result.size).toBe(0)
  })

  it("handles conflicts across different days independently", () => {
    const lessons = [
      makeLesson({ id: "1", weekday: "Monday", start_time: "09:00", end_time: "10:30" }),
      makeLesson({ id: "2", weekday: "Monday", start_time: "10:00", end_time: "11:30" }),
      makeLesson({ id: "3", weekday: "Tuesday", start_time: "09:00", end_time: "10:30" }),
      makeLesson({ id: "4", weekday: "Tuesday", start_time: "10:00", end_time: "11:30" }),
    ]
    const result = detectConflicts(lessons)
    expect(result.size).toBe(4)
  })
})
