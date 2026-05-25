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
 *
 * Wave 147 SW5 — accept BOTH number and numeric-string for `w`.
 *
 * Per the Wave 120 SW5 Map URL-sync gotcha (`tokens/map.ts schema.ts`),
 * TanStack Router's `parseSearch` coerces numeric-looking URL params to
 * numbers — so `?w=1` arrives at the route's `validateSearch` as the
 * NUMBER `1`, not the string `"1"`. The pre-W147 schema `v.string()` then
 * rejected with "Invalid type: Expected string but received 1", crashing
 * the route's SSR with a 500. The `?w=N` URL is reachable from any user
 * who clicks "next week" in `ScheduleWeekNav` (Wave 112 SW3b → useURLState
 * writes `w` as a string via `setParam`, but TanStack Router's serializer
 * + parser round-trip strips the quotes for clean URLs like `?w=1`).
 *
 * Same union pattern as `frontend/src/features/map/schema.ts` —
 * `v.union([v.number(), v.pipe(v.string(), v.transform(parseFloat))])` —
 * with an additional integer regex guard on the string variant (week
 * offset must be a signed integer; map coords can be floats).
 */
export const scheduleSearchSchema = v.object({
  w: v.optional(
    v.union([
      v.pipe(v.number(), v.integer("Week offset must be an integer")),
      v.pipe(
        v.string(),
        v.regex(/^-?\d+$/, "Week offset must be an integer"),
        v.transform((s) => Number.parseInt(s, 10))
      ),
    ])
  ),
})

export type ScheduleSearch = v.InferOutput<typeof scheduleSearchSchema>
