import { useEffect, useRef } from "react"
import { useURLState } from "@/hooks/useURLState"
import { useScheduleUIStore } from "@/stores/scheduleUIStore"

/**
 * Keeps the shareable week offset in the URL and the display store aligned.
 * The URL is authoritative on mount; afterwards only the side that changed
 * drives the other side. This prevents a stale counterpart from undoing a
 * user change while its router update is still pending.
 */
export function useScheduleURLSync(): void {
  const { params, setParam } = useURLState<{ w?: number }>()
  const urlWeek = params.w !== undefined ? String(params.w) : ""

  const weekOffset = useScheduleUIStore((state) => state.weekOffset)
  const setWeekOffset = useScheduleUIStore((state) => state.setWeekOffset)

  const isInitialSyncRef = useRef(true)
  const lastUrlWeekRef = useRef(urlWeek)
  const lastWeekOffsetRef = useRef(weekOffset)

  useEffect(() => {
    if (isInitialSyncRef.current) {
      isInitialSyncRef.current = false
      lastUrlWeekRef.current = urlWeek
      lastWeekOffsetRef.current = weekOffset

      const parsed = urlWeek === "" ? 0 : Number.parseInt(urlWeek, 10)
      const initialOffset = Number.isFinite(parsed) ? parsed : 0
      if (initialOffset !== weekOffset) {
        setWeekOffset(initialOffset)
      }
      return
    }

    const urlChanged = urlWeek !== lastUrlWeekRef.current
    const weekOffsetChanged = weekOffset !== lastWeekOffsetRef.current
    lastUrlWeekRef.current = urlWeek
    lastWeekOffsetRef.current = weekOffset

    if (urlChanged) {
      const parsed = urlWeek === "" ? 0 : Number.parseInt(urlWeek, 10)
      const next = Number.isFinite(parsed) ? parsed : 0
      if (next !== weekOffset) {
        setWeekOffset(next)
      }
      return
    }

    if (weekOffsetChanged) {
      const expected: number | "" = weekOffset === 0 ? "" : weekOffset
      const expectedURL = expected === "" ? "" : String(expected)
      if (expectedURL !== urlWeek) {
        setParam("w", expected)
      }
    }
  }, [urlWeek, weekOffset, setWeekOffset, setParam])
}
