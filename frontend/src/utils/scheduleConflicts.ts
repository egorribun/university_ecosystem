/**
 * Pure conflict detection — no hooks, no side effects.
 * Extracted from useScheduleData for testability.
 */

import { type Lesson, parseMinutes } from "@/components/schedule/scheduleUtils"

/**
 * Detect overlapping lessons on the same day.
 * Returns a Set of lesson IDs that have time conflicts.
 */
export function detectConflicts(lessons: Lesson[]): Set<string> {
  // An unparseable time becomes NaN, and every comparison with NaN is false,
  // so such a lesson never conflicts.
  const byDay = new Map<string, { id: string; start: number; end: number }[]>()
  for (const lesson of lessons) {
    const range = {
      id: lesson.id,
      start: parseMinutes(lesson.start_time) ?? Number.NaN,
      end: parseMinutes(lesson.end_time) ?? Number.NaN,
    }
    const day = byDay.get(lesson.weekday)
    if (day) day.push(range)
    else byDay.set(lesson.weekday, [range])
  }

  const conflicted = new Set<string>()
  for (const ranges of byDay.values()) {
    for (const [index, a] of ranges.entries()) {
      for (const b of ranges.slice(index + 1)) {
        if (Math.max(a.start, b.start) < Math.min(a.end, b.end)) {
          conflicted.add(a.id)
          conflicted.add(b.id)
        }
      }
    }
  }
  return conflicted
}
