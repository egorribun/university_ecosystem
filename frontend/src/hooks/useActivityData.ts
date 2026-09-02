import { useCallback, useMemo } from "react"
import { useTranslation } from "react-i18next"
import { useLanguage, getLocaleForLanguage } from "@/contexts/LanguageContext"
import { useActivitySummaryQuery } from "@/api/hooks/activity"
import { useURLState } from "@/hooks/useURLState"
import {
  type PeriodKey,
  type AttendanceStats,
  type GradeStats,
  type ParticipationStats,
  PERIOD_VALUES,
  periodDayCount,
  isPeriodKey,
  isGradeScale,
} from "@/features/activity/types"
import {
  toNumber,
  parseAttendanceRecent,
  parseGradeRecent,
  parseParticipationRecent,
} from "@/features/activity/parsers"

/**
 * useActivityData — Wave 112 SW2.
 *
 * Public API is byte-equivalent to the previous bare-axios implementation:
 * consumers (ActivityFeature) get the same `attendance/grades/participation`
 * objects with fallback defaults, the same loading/hasInitiallyLoaded flags,
 * and the same derived chart/heatmap data.
 *
 * What changed: data fetching + cancellation now flows through TanStack Query
 * (`useActivitySummaryQuery`). Benefits:
 *   - Automatic dedup across hook instances
 *   - Background refetch on window focus / reconnect (default behaviour)
 *   - 60s staleTime — sub-minute refetches are wasteful for summary stats
 *   - AbortSignal handled by query → no manual AbortController bookkeeping
 *   - Cache survives unmount → instant period-switch back to a visited window
 *
 * The translation/parsing layer (toNumber, parseAttendanceRecent, etc.)
 * stays here as `useMemo` derivations — they're UI concerns, not fetch concerns.
 */
export default function useActivityData() {
  const { t } = useTranslation(["activity", "common"])
  const { language } = useLanguage()
  const locale = getLocaleForLanguage(language)

  // URL-synced period — refresh and share now preserve the selected window
  // (Wave 112 SW3). Falls back to "90d" when absent or unrecognised.
  const { params, setParam } = useURLState<{ p?: PeriodKey }>()
  const period: PeriodKey = params.p && isPeriodKey(params.p) ? params.p : "90d"
  const setPeriod = useCallback(
    (next: PeriodKey) => {
      // Keep the URL clean: default value → remove the param.
      setParam("p", next === "90d" ? "" : next)
    },
    [setParam]
  )

  const labelByPeriod = useCallback(
    (p: PeriodKey) =>
      t(`activity:period.labels.${p}`, {
        count: periodDayCount(p),
      }),
    [t]
  )

  const periodOptions = useMemo(
    () =>
      PERIOD_VALUES.map((value) => ({
        value,
        label: t(`activity:period.options.${value}`, {
          count: periodDayCount(value),
        }),
      })),
    [t]
  )

  const separator = t("activity:common.separator")

  const formatDate = useCallback(
    (value?: string | null) => {
      if (!value) return ""
      const date = new Date(value)
      if (Number.isNaN(date.getTime())) return ""
      return date.toLocaleDateString(locale, {
        day: "numeric",
        month: "long",
        year: "numeric",
      })
    },
    [locale]
  )

  const attendanceStatusLabel = useCallback(
    (status: AttendanceStats["recent"][number]["status"]) =>
      t(`activity:sections.attendance.status.${status}`),
    [t]
  )

  // ── Data fetching via TanStack Query ────────────
  const summaryQuery = useActivitySummaryQuery({ period, language })
  const envelope = summaryQuery.data
  const loading = summaryQuery.isFetching
  const hasInitiallyLoaded = summaryQuery.isSuccess

  const attendance = useMemo<AttendanceStats | null>(() => {
    const d = envelope?.attendance
    if (d) {
      const resolvedPeriodKey: PeriodKey = isPeriodKey(d.period_key) ? d.period_key : period
      const periodLabel =
        typeof d.period_label === "string" && d.period_label.trim()
          ? d.period_label
          : labelByPeriod(resolvedPeriodKey)
      return {
        percent: toNumber(d.percent),
        present: toNumber(d.present),
        total: toNumber(d.total),
        trend: toNumber(d.trend),
        periodKey: resolvedPeriodKey,
        periodLabel,
        recent: parseAttendanceRecent(d.recent),
      }
    }
    return null
  }, [envelope?.attendance, period, labelByPeriod])

  const grades = useMemo<GradeStats | null>(() => {
    const d = envelope?.grades
    if (d) {
      return {
        average: toNumber(d.average, 4.4),
        scale: isGradeScale(d.scale) ? d.scale : "5",
        trend: toNumber(d.trend, 0.3),
        recent: parseGradeRecent(d.recent),
      }
    }
    return null
  }, [envelope?.grades])

  const participation = useMemo<ParticipationStats | null>(() => {
    const d = envelope?.participation
    if (d) {
      return {
        events: toNumber(d.events),
        hours: d.hours != null ? toNumber(d.hours) : undefined,
        groups: d.groups != null ? toNumber(d.groups) : undefined,
        trend: toNumber(d.trend),
        recent: parseParticipationRecent(d.recent),
      }
    }
    return null
  }, [envelope?.participation])

  const hasAnyData = Boolean(attendance || grades || participation)
  const availability = {
    attendance: Boolean(envelope?.attendance),
    grades: Boolean(envelope?.grades),
    participation: Boolean(envelope?.participation),
  }
  const isPartial =
    hasInitiallyLoaded &&
    hasAnyData &&
    (!availability.attendance || !availability.grades || !availability.participation)

  // ── Chart data derivation (Phase B) ───────────────
  const attendanceTrendData = useMemo(() => {
    const recent = attendance?.recent
    if (!recent?.length) return []
    const byDate = new Map<string, { present: number; total: number }>()
    for (const item of recent) {
      const key = item.date.slice(0, 10)
      const prev = byDate.get(key) ?? { present: 0, total: 0 }
      byDate.set(key, {
        present: prev.present + (item.status === "present" ? 1 : 0),
        total: prev.total + 1,
      })
    }
    return [...byDate.entries()]
      .map(([date, { present, total }]) => ({
        date,
        value: Math.round((present / total) * 100),
      }))
      .sort((a, b) => a.date.localeCompare(b.date))
  }, [attendance?.recent])

  const gradesBySubject = useMemo(() => {
    const recent = grades?.recent
    if (!recent?.length) return []
    const bySubject = new Map<string, { sum: number; count: number; max: number }>()
    for (const item of recent) {
      const prev = bySubject.get(item.course) ?? { sum: 0, count: 0, max: item.max ?? 5 }
      bySubject.set(item.course, {
        sum: prev.sum + item.score,
        count: prev.count + 1,
        max: item.max ?? prev.max,
      })
    }
    return [...bySubject.entries()].map(([label, { sum, count, max }]) => ({
      label,
      value: sum / count,
      max,
    }))
  }, [grades?.recent])

  // Heatmap data — merge all recent arrays into date→count map
  const heatmapData = useMemo(() => {
    const map = new Map<string, number>()
    const inc = (date: string) => {
      const key = date.slice(0, 10)
      map.set(key, (map.get(key) ?? 0) + 1)
    }
    for (const item of attendance?.recent ?? []) inc(item.date)
    for (const item of grades?.recent ?? []) inc(item.date)
    for (const item of participation?.recent ?? []) inc(item.date)
    return map
  }, [attendance?.recent, grades?.recent, participation?.recent])

  return {
    t,
    period,
    setPeriod,
    attendance,
    grades,
    participation,
    loading,
    hasInitiallyLoaded,
    hasAnyData,
    availability,
    isPartial,
    isError: summaryQuery.isError,
    error: summaryQuery.error,
    refetch: summaryQuery.refetch,
    periodOptions,
    separator,
    formatDate,
    attendanceStatusLabel,
    attendanceTrendData,
    gradesBySubject,
    heatmapData,
  }
}
