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
  const { params, setParam } = useURLState<{ w?: string }>()
  const urlWeek = params.w ?? ""

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
  useEffect(() => {
    const expected = weekOffset === 0 ? "" : String(weekOffset)
    if (expected !== urlWeek) {
      setParam("w", expected)
    }
  }, [weekOffset, urlWeek, setParam])
}
