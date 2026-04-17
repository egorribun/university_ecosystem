/**
 * Pure conflict detection — no hooks, no side effects.
 * Extracted from useScheduleData for testability.
 */

import { type Lesson, parseMinutes, getTimeStr } from "@/components/schedule/scheduleUtils"

/**
 * Detect overlapping lessons on the same day.
 * Returns a Set of lesson IDs that have time conflicts.
 */
export function detectConflicts(lessons: Lesson[]): Set<string> {
  const byDay = new Map<string, Lesson[]>()
  for (const l of lessons) {
    const arr = byDay.get(l.weekday) ?? []
    arr.push(l)
    byDay.set(l.weekday, arr)
  }

  const conflicted = new Set<string>()

  for (const [, dayLessons] of byDay) {
    dayLessons.sort((a, b) => getTimeStr(a).localeCompare(getTimeStr(b)))

    for (let i = 0; i < dayLessons.length; i++) {
      const li = dayLessons[i]!
      for (let j = i + 1; j < dayLessons.length; j++) {
        const lj = dayLessons[j]!
        const s1 = parseMinutes(li.start_time)
        const e1 = parseMinutes(li.end_time)
        const s2 = parseMinutes(lj.start_time)
        const e2 = parseMinutes(lj.end_time)

        if (s1 == null || e1 == null || s2 == null || e2 == null) continue

        const overlap = Math.max(s1, s2) < Math.min(e1, e2)
        if (overlap) {
          conflicted.add(li.id)
          conflicted.add(lj.id)
        }
      }
    }
  }

  return conflicted
}
