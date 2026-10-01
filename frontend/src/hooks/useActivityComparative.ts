import { useMemo } from "react"
import type { AttendanceStats, GradeStats, ParticipationStats } from "@/features/activity/types"

type WindowStat = { current: number; previous: number; delta: number }

export type ComparativeStats = {
  attendance: WindowStat
  grades: WindowStat
  participation: WindowStat
  hasData: boolean
}

const computeDelta = (current: number, previous: number) =>
  previous > 0 ? ((current - previous) / previous) * 100 : current > 0 ? 100 : 0

/**
 * The backend reports each metric for the selected window together with its
 * `trend` against the immediately preceding window of the same length, so the
 * previous value is `current - trend`. Deriving the comparison from those
 * fields keeps one definition of "previous" across the cards and trend chips
 * (the `recent` lists are truncated and cannot be split reliably).
 */
const toWindowStat = (current: number, trend: number): WindowStat => {
  const previous = Math.max(0, current - trend)
  return { current, previous, delta: computeDelta(current, previous) }
}

export function useActivityComparative(
  attendance: AttendanceStats | null | undefined,
  grades: GradeStats | null | undefined,
  participation: ParticipationStats | null | undefined
): ComparativeStats {
  // RC-78-01: extract to primitives for React Compiler
  const attPercent = attendance?.percent ?? 0
  const attTrend = attendance?.trend ?? 0
  const attTotal = attendance?.total ?? 0
  const grdAverage = grades?.average ?? 0
  const grdTrend = grades?.trend ?? 0
  const grdCount = grades?.recent.length ?? 0
  const prtEvents = participation?.events ?? 0
  const prtTrend = participation?.trend ?? 0

  return useMemo(
    () => ({
      attendance: toWindowStat(attPercent, attTrend),
      grades: toWindowStat(grdAverage, grdTrend),
      participation: toWindowStat(prtEvents, prtTrend),
      hasData: attTotal > 0 || grdCount > 0 || prtEvents > 0,
    }),
    [attPercent, attTrend, attTotal, grdAverage, grdTrend, grdCount, prtEvents, prtTrend]
  )
}
