import { useEffect } from "react"
import { useURLState } from "@/hooks/useURLState"
import { useScheduleUIStore } from "@/stores/scheduleUIStore"

/**
 * useScheduleURLSync — Wave 112 SW3b sync-bridge between the Schedule
 * route's `w` URL parameter and the Zustand `weekOffset` state.
 *
 * Why a bridge instead of replacing Zustand state with URL state?
 *   1. `useScheduleUIStore` has 10+ consumers (selector hooks, settings
 *      panel, mobile view, keyboard nav) that all read `weekOffset`
 *      through the existing selector pattern. Swapping the source would
 *      require touching every call site.
 *   2. Unit tests assert on `useScheduleUIStore.getState().weekOffset`
 *      directly — preserving the store's API keeps those green without
 *      router mocking.
 *   3. Zustand's idempotent `set` naturally breaks ping-pong: if URL
 *      change produces an offset already in the store, the `set` is a
 *      no-op and doesn't re-trigger the effect that writes to URL.
 *
 * Flow:
 *   URL `?w=2` → parse → setWeekOffset(2) → Zustand
 *   User clicks "Next week" → Zustand weekOffset++ → URL `?w=N` (or
 *   removed entirely when N = 0 for clean share links)
 *
 * Mount this hook once at the top of the Schedule page/feature.
 */
export function useScheduleURLSync(): void {
  // W147 SW5 — `w` is now `number` (Valibot v.transform converts the URL
  // string to number at parse time per W120 SW5 mapSearchSchema pattern, so
  // TanStack Router's number-coercion of `?w=1` doesn't trip Valibot type
  // validation). useURLState's generic accepts the new shape; consumer logic
  // below already coerces via Number.parseInt + Number.isFinite guards.
  const { params, setParam } = useURLState<{ w?: number }>()
  const urlWeek = params.w !== undefined ? String(params.w) : ""

  const weekOffset = useScheduleUIStore((state) => state.weekOffset)
  const setWeekOffset = useScheduleUIStore((state) => state.setWeekOffset)

  // URL → store. Parse the URL value and push into the store when they
  // disagree. The `next !== weekOffset` guard is what prevents the
  // ping-pong with the store→URL effect below: once URL and store align,
  // both effects become no-ops until the next external change.
  useEffect(() => {
    const parsed = urlWeek === "" ? 0 : Number.parseInt(urlWeek, 10)
    const next = Number.isFinite(parsed) ? parsed : 0
    if (next !== weekOffset) {
      setWeekOffset(next)
    }
  }, [urlWeek, weekOffset, setWeekOffset])

  // Store → URL. Write the current offset (absent when 0 for clean URLs).
  // W147 SW5 — setParam now takes `number` for `w` (was `string` pre-W147
  // before the schema's v.transform converted parsed strings to numbers).
  // Use empty string to clear the param when offset is 0 (useURLState's
  // sentinel for removal); otherwise pass the number directly.
  useEffect(() => {
    const expected: number | "" = weekOffset === 0 ? "" : weekOffset
    const expectedURL = expected === "" ? "" : String(expected)
    if (expectedURL !== urlWeek) {
      setParam("w", expected)
    }
  }, [weekOffset, urlWeek, setParam])
}
