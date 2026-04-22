import { useMemo } from "react"
import type {
  AttendanceStats,
  GradeStats,
  ParticipationStats,
  PeriodKey,
} from "@/features/activity/types"
import { periodDayCount } from "@/features/activity/types"

type HalfStat = { current: number; previous: number; delta: number }

export type ComparativeStats = {
  attendance: HalfStat
  grades: HalfStat
  participation: HalfStat
  hasData: boolean
}

/** Split a period in half and compare current vs previous half */
export function useActivityComparative(
  attendance: AttendanceStats | null | undefined,
  grades: GradeStats | null | undefined,
  participation: ParticipationStats | null | undefined,
  period: PeriodKey
): ComparativeStats {
  // RC-78-01: extract to primitives for React Compiler
  const attRecent = attendance?.recent
  const grdRecent = grades?.recent
  const prtRecent = participation?.recent

  return useMemo(() => {
    const days = periodDayCount(period)
    const halfDays = Math.floor(days / 2)
    const now = new Date()
    now.setHours(23, 59, 59, 999)
    const midpoint = new Date(now)
    midpoint.setDate(midpoint.getDate() - halfDays)

    const isCurrentHalf = (dateStr: string) => {
      const d = new Date(dateStr + "T00:00:00") // local parse — avoid UTC midnight shift (M2)
      return d > midpoint && d <= now
    }

    // Attendance: % in current half vs previous half
    let attCurPresent = 0,
      attCurTotal = 0,
      attPrevPresent = 0,
      attPrevTotal = 0
    for (const item of attRecent ?? []) {
      if (isCurrentHalf(item.date)) {
        attCurTotal++
        if (item.status === "present") attCurPresent++
      } else {
        attPrevTotal++
        if (item.status === "present") attPrevPresent++
      }
    }
    const attCurPct = attCurTotal > 0 ? (attCurPresent / attCurTotal) * 100 : 0
    const attPrevPct = attPrevTotal > 0 ? (attPrevPresent / attPrevTotal) * 100 : 0

    // Grades: avg score in current half vs previous half
    let grdCurSum = 0,
      grdCurCount = 0,
      grdPrevSum = 0,
      grdPrevCount = 0
    for (const item of grdRecent ?? []) {
      if (isCurrentHalf(item.date)) {
        grdCurSum += item.score
        grdCurCount++
      } else {
        grdPrevSum += item.score
        grdPrevCount++
      }
    }
    const grdCurAvg = grdCurCount > 0 ? grdCurSum / grdCurCount : 0
    const grdPrevAvg = grdPrevCount > 0 ? grdPrevSum / grdPrevCount : 0

    // Participation: event count in current half vs previous half
    let prtCurCount = 0,
      prtPrevCount = 0
    for (const item of prtRecent ?? []) {
      if (isCurrentHalf(item.date)) prtCurCount++
      else prtPrevCount++
    }

    const computeDelta = (current: number, previous: number) =>
      previous > 0 ? ((current - previous) / previous) * 100 : current > 0 ? 100 : 0

    const hasData =
      (attRecent?.length ?? 0) > 0 || (grdRecent?.length ?? 0) > 0 || (prtRecent?.length ?? 0) > 0

    return {
      attendance: {
        current: attCurPct,
        previous: attPrevPct,
        delta: computeDelta(attCurPct, attPrevPct),
      },
      grades: {
        current: grdCurAvg,
        previous: grdPrevAvg,
        delta: computeDelta(grdCurAvg, grdPrevAvg),
      },
      participation: {
        current: prtCurCount,
        previous: prtPrevCount,
        delta: computeDelta(prtCurCount, prtPrevCount),
      },
      hasData,
    }
  }, [attRecent, grdRecent, prtRecent, period])
}
