import { describe, expect, it } from "vitest"
import { detectConflicts } from "../scheduleConflicts"
import type { Lesson } from "@/components/schedule/scheduleUtils"

// ---------------------------------------------------------------------------
// Factory helper — builds a minimal Lesson object
// ---------------------------------------------------------------------------
const makeLesson = (
  id: string,
  weekday: string,
  startTime: string,
  endTime: string
): Lesson => ({
  id,
  weekday,
  parity: "both",
  start_time: startTime,
  end_time: endTime,
})

describe("detectConflicts", () => {
  // ---------------------------------------------------------------------------
  // Empty / trivial
  // ---------------------------------------------------------------------------
  it("returns an empty set for no lessons", () => {
    expect(detectConflicts([])).toEqual(new Set())
  })

  it("returns an empty set for a single lesson", () => {
    const lessons = [makeLesson("a", "Monday", "09:00", "10:30")]
    expect(detectConflicts(lessons)).toEqual(new Set())
  })

  // ---------------------------------------------------------------------------
  // No conflict — lessons are consecutive
  // ---------------------------------------------------------------------------
  it("returns empty set when lessons are back-to-back (no overlap)", () => {
    const lessons = [
      makeLesson("a", "Monday", "09:00", "10:30"),
      makeLesson("b", "Monday", "10:30", "12:00"), // starts exactly when first ends
    ]
    expect(detectConflicts(lessons)).toEqual(new Set())
  })

  it("returns empty set when lessons on the same day do not overlap", () => {
    const lessons = [
      makeLesson("a", "Monday", "09:00", "10:00"),
      makeLesson("b", "Monday", "11:00", "12:00"),
    ]
    expect(detectConflicts(lessons)).toEqual(new Set())
  })

  // ---------------------------------------------------------------------------
  // Conflict detected
  // ---------------------------------------------------------------------------
  it("flags two overlapping lessons", () => {
    const lessons = [
      makeLesson("a", "Monday", "09:00", "11:00"),
      makeLesson("b", "Monday", "10:00", "12:00"),
    ]
    const result = detectConflicts(lessons)
    expect(result).toContain("a")
    expect(result).toContain("b")
    expect(result.size).toBe(2)
  })

  it("flags lesson fully contained inside another", () => {
    const lessons = [
      makeLesson("outer", "Tuesday", "08:00", "14:00"),
      makeLesson("inner", "Tuesday", "10:00", "11:00"),
    ]
    const result = detectConflicts(lessons)
    expect(result).toContain("outer")
    expect(result).toContain("inner")
  })

  it("flags three-way conflict on one day", () => {
    const lessons = [
      makeLesson("x", "Wednesday", "09:00", "11:00"),
      makeLesson("y", "Wednesday", "10:00", "12:00"),
      makeLesson("z", "Wednesday", "10:30", "11:30"),
    ]
    const result = detectConflicts(lessons)
    expect(result.size).toBe(3)
  })

  // ---------------------------------------------------------------------------
  // Cross-day isolation — conflicts on different days must not bleed through
  // ---------------------------------------------------------------------------
  it("does not flag lessons on different days with identical times", () => {
    const lessons = [
      makeLesson("mon", "Monday", "09:00", "10:30"),
      makeLesson("tue", "Tuesday", "09:00", "10:30"),
    ]
    expect(detectConflicts(lessons)).toEqual(new Set())
  })

  it("detects conflict only on the affected day when another day is clean", () => {
    const lessons = [
      // Monday conflict
      makeLesson("a", "Monday", "09:00", "11:00"),
      makeLesson("b", "Monday", "10:00", "12:00"),
      // Tuesday clean
      makeLesson("c", "Tuesday", "09:00", "10:00"),
    ]
    const result = detectConflicts(lessons)
    expect(result).toContain("a")
    expect(result).toContain("b")
    expect(result).not.toContain("c")
  })

  // ---------------------------------------------------------------------------
  // Null / missing times — must not throw
  // ---------------------------------------------------------------------------
  it("skips lessons with null start_time without throwing", () => {
    const lessons = [
      { id: "null-start", weekday: "Monday", parity: "both" as const, start_time: null, end_time: "10:00" },
      makeLesson("ok", "Monday", "09:00", "10:00"),
    ]
    expect(() => detectConflicts(lessons)).not.toThrow()
  })

  it("skips lessons with null end_time without throwing", () => {
    const lessons = [
      { id: "null-end", weekday: "Monday", parity: "both" as const, start_time: "09:00", end_time: null },
      makeLesson("ok", "Monday", "11:00", "12:00"),
    ]
    expect(() => detectConflicts(lessons)).not.toThrow()
  })
})
