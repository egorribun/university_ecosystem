import * as v from "valibot"

/**
 * Schedule route search-param schema — Wave 112 SW3b URL-sync.
 *
 * Only `w` (week offset from today) is URL-synced. viewMode / compactMode /
 * showPastLessons / hiddenWeekdays stay in Zustand `useScheduleUIStore`
 * because they are user preferences, not shareable view state — Wave 65+
 * persists them to localStorage for cross-session continuity.
 *
 *   w — signed integer offset from current week (0 = this week, -1 =
 *       previous, +1 = next). Absent when w=0 (clean URL).
 */
export const scheduleSearchSchema = v.object({
  w: v.optional(
    v.pipe(
      v.string(),
      v.regex(/^-?\d+$/, "Week offset must be an integer"),
    ),
  ),
})

export type ScheduleSearch = v.InferOutput<typeof scheduleSearchSchema>
