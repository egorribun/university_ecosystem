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
      for (let j = i + 1; j < dayLessons.length; j++) {
        const s1 = parseMinutes(dayLessons[i].start_time)
        const e1 = parseMinutes(dayLessons[i].end_time)
        const s2 = parseMinutes(dayLessons[j].start_time)
        const e2 = parseMinutes(dayLessons[j].end_time)

        if (s1 == null || e1 == null || s2 == null || e2 == null) continue

        const overlap = Math.max(s1, s2) < Math.min(e1, e2)
        if (overlap) {
          conflicted.add(dayLessons[i].id)
          conflicted.add(dayLessons[j].id)
        }
      }
    }
  }

  return conflicted
}
