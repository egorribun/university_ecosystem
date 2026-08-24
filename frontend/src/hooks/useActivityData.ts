import { useCallback, useEffect, useMemo, useState } from "react"
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
  DEFAULT_ATTENDANCE_RECENT,
  DEFAULT_GRADE_RECENT,
  DEFAULT_PARTICIPATION_RECENT,
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

  // i18n returnObjects fallbacks — stored in state (not refs) so React
  // Compiler can track them as useMemo dependencies without flagging a
  // ref-read during render (RC-78-01 / RC-91-01 pattern).
  const [fallbackAttendanceRecent, setFallbackAttendanceRecent] =
    useState(DEFAULT_ATTENDANCE_RECENT)
  const [fallbackGradeRecent, setFallbackGradeRecent] = useState(DEFAULT_GRADE_RECENT)
  const [fallbackParticipationRecent, setFallbackParticipationRecent] = useState(
    DEFAULT_PARTICIPATION_RECENT
  )

  // react-i18next returnObjects returns TFunctionResult which doesn't narrow
  // to unknown[]. Cast to `unknown` is safe because each value passes through
  // typed parsers below. Language-change is the only trigger — re-render cost
  // is negligible compared to the correctness win.
  useEffect(() => {
    const attendanceRaw = t("activity:fallback.attendance.recent", {
      returnObjects: true,
    }) as unknown
    const attendanceParsed = parseAttendanceRecent(attendanceRaw)
    setFallbackAttendanceRecent(
      attendanceParsed.length > 0 ? attendanceParsed : DEFAULT_ATTENDANCE_RECENT
    )

    const gradesRaw = t("activity:fallback.grades.recent", { returnObjects: true }) as unknown
    const gradesParsed = parseGradeRecent(gradesRaw)
    setFallbackGradeRecent(gradesParsed.length > 0 ? gradesParsed : DEFAULT_GRADE_RECENT)

    const participationRaw = t("activity:fallback.participation.recent", {
      returnObjects: true,
    }) as unknown
    const participationParsed = parseParticipationRecent(participationRaw)
    setFallbackParticipationRecent(
      participationParsed.length > 0 ? participationParsed : DEFAULT_PARTICIPATION_RECENT
    )
  }, [t])

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
    if (!hasInitiallyLoaded) return null
    // Per-section fallback when /stats/summary or /stats/attendance returns null.
    return {
      percent: 92,
      present: 83,
      total: 90,
      trend: 1.4,
      periodKey: period,
      periodLabel: labelByPeriod(period),
      recent: fallbackAttendanceRecent.map((item) => ({ ...item })),
    }
  }, [envelope?.attendance, period, labelByPeriod, hasInitiallyLoaded, fallbackAttendanceRecent])

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
    if (!hasInitiallyLoaded) return null
    return {
      average: 4.4,
      scale: "5",
      trend: 0.3,
      recent: fallbackGradeRecent.map((item) => ({ ...item })),
    }
  }, [envelope?.grades, hasInitiallyLoaded, fallbackGradeRecent])

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
    if (!hasInitiallyLoaded) return null
    return {
      events: 6,
      hours: 12,
      groups: 2,
      trend: 2.0,
      recent: fallbackParticipationRecent.map((item) => ({ ...item })),
    }
  }, [envelope?.participation, hasInitiallyLoaded, fallbackParticipationRecent])

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
    periodOptions,
    separator,
    formatDate,
    attendanceStatusLabel,
    attendanceTrendData,
    gradesBySubject,
    heatmapData,
  }
}
