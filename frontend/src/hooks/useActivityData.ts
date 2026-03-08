import { useState, useCallback, useMemo, useEffect, useRef } from "react"
import { useTranslation } from "react-i18next"
import axios from "@/api/client"
import { useLanguage, getLocaleForLanguage } from "@/contexts/LanguageContext"
import {
  type PeriodKey,
  type AttendanceStats,
  type GradeStats,
  type ParticipationStats,
  type DetailSection,
  type AttendanceSummaryResponse,
  type GradeSummaryResponse,
  type ParticipationSummaryResponse,
  PERIOD_VALUES,
  periodDayCount,
  isPeriodKey,
} from "@/components/activity/activityTypes"
import {
  toNumber,
  parseAttendanceRecent,
  parseGradeRecent,
  parseParticipationRecent,
  DEFAULT_ATTENDANCE_RECENT,
  DEFAULT_GRADE_RECENT,
  DEFAULT_PARTICIPATION_RECENT,
} from "@/components/activity/activityParsers"

export default function useActivityData() {
  const { t } = useTranslation(["activity", "common"])
  const { language } = useLanguage()
  const locale = getLocaleForLanguage(language)

  const [period, setPeriod] = useState<PeriodKey>("90d")
  const [attendance, setAttendance] = useState<AttendanceStats | null>(null)
  const [grades, setGrades] = useState<GradeStats | null>(null)
  const [participation, setParticipation] = useState<ParticipationStats | null>(null)
  const [loading, setLoading] = useState(false)
  const [hasInitiallyLoaded, setHasInitiallyLoaded] = useState(false)
  const [detail, setDetail] = useState<
    | ""
    | "attendance"
    | "grades"
    | "participation"
    | "attendance_recent"
    | "grades_recent"
    | "participation_recent"
  >("")

  const detailSection: DetailSection = detail.startsWith("attendance")
    ? "attendance"
    : detail.startsWith("grades")
      ? "grades"
      : detail.startsWith("participation")
        ? "participation"
        : ""

  const labelByPeriod = useCallback(
    (p: PeriodKey) =>
      t(`activity:period.labels.${p}`, {
        defaultValue: p,
        count: periodDayCount(p),
      }),
    [t]
  )

  const periodOptions = useMemo(
    () =>
      PERIOD_VALUES.map((value) => ({
        value,
        label: t(`activity:period.options.${value}`, {
          defaultValue: value,
          count: periodDayCount(value),
        }),
      })),
    [t]
  )

  const separator = t("activity:common.separator", { defaultValue: " • " })
  const noDataText = t("activity:common.noData")
  const attendanceLessonFallback = t("activity:sections.attendance.lessonFallback")

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
      t(`activity:sections.attendance.status.${status}`, { defaultValue: status }),
    [t]
  )

  const fallbackAttendanceRecentRef = useRef(DEFAULT_ATTENDANCE_RECENT)
  const fallbackGradeRecentRef = useRef(DEFAULT_GRADE_RECENT)
  const fallbackParticipationRecentRef = useRef(DEFAULT_PARTICIPATION_RECENT)

  useEffect(() => {
    const attendanceRaw = t("activity:fallback.attendance.recent", {
      returnObjects: true,
    }) as unknown
    const attendanceParsed = parseAttendanceRecent(attendanceRaw)
    fallbackAttendanceRecentRef.current =
      attendanceParsed.length > 0 ? attendanceParsed : DEFAULT_ATTENDANCE_RECENT

    const gradesRaw = t("activity:fallback.grades.recent", { returnObjects: true }) as unknown
    const gradesParsed = parseGradeRecent(gradesRaw)
    fallbackGradeRecentRef.current = gradesParsed.length > 0 ? gradesParsed : DEFAULT_GRADE_RECENT

    const participationRaw = t("activity:fallback.participation.recent", {
      returnObjects: true,
    }) as unknown
    const participationParsed = parseParticipationRecent(participationRaw)
    fallbackParticipationRecentRef.current =
      participationParsed.length > 0 ? participationParsed : DEFAULT_PARTICIPATION_RECENT
  }, [t])

  const summaryRequestRef = useRef<AbortController | null>(null)

  const fetchSummary = useCallback(async () => {
    summaryRequestRef.current?.abort()
    const controller = new AbortController()
    summaryRequestRef.current = controller

    setLoading(true)

    // PERF-1: /stats/summary — single round-trip instead of three separate requests.
    // Falls back to individual endpoints on failure (older backend / per-service outage).
    type SummaryEnvelope = {
      attendance: AttendanceSummaryResponse | null
      grades: GradeSummaryResponse | null
      participation: ParticipationSummaryResponse | null
    }
    type SettledLike<T> = { status: "fulfilled"; value: { data: T } } | { status: "rejected" }
    const _toSettled = <T>(data: T | null): SettledLike<T> =>
      data != null ? { status: "fulfilled", value: { data } } : { status: "rejected" }

    try {
      let a: SettledLike<AttendanceSummaryResponse>
      let g: SettledLike<GradeSummaryResponse>
      let p: SettledLike<ParticipationSummaryResponse>

      try {
        const summary = await axios.get<SummaryEnvelope>("/stats/summary", {
          params: { period },
          signal: controller.signal,
        })
        a = _toSettled(summary.data?.attendance ?? null)
        g = _toSettled(summary.data?.grades ?? null)
        p = _toSettled(summary.data?.participation ?? null)
      } catch {
        // Fallback: individual requests for older backend or per-endpoint failure.
        ;[a, g, p] = await Promise.allSettled([
          axios.get<AttendanceSummaryResponse>("/stats/attendance", {
            params: { period },
            signal: controller.signal,
          }),
          axios.get<GradeSummaryResponse>("/stats/grades", {
            params: { period },
            signal: controller.signal,
          }),
          axios.get<ParticipationSummaryResponse>("/stats/participation", {
            params: { period },
            signal: controller.signal,
          }),
        ])
      }

      if (controller.signal.aborted) {
        return
      }

      if (a.status === "fulfilled" && a.value?.data) {
        const d = a.value.data
        const resolvedPeriodKey: PeriodKey = isPeriodKey(d.period_key) ? d.period_key : period
        const periodLabel =
          typeof d.period_label === "string" && d.period_label.trim()
            ? d.period_label
            : labelByPeriod(resolvedPeriodKey)
        setAttendance({
          percent: toNumber(d.percent),
          present: toNumber(d.present),
          total: toNumber(d.total),
          trend: toNumber(d.trend),
          periodKey: resolvedPeriodKey,
          periodLabel,
          recent: Array.isArray(d.recent) ? d.recent : [],
        })
      } else {
        const fallbackRecent = fallbackAttendanceRecentRef.current
        setAttendance({
          percent: 92,
          present: 83,
          total: 90,
          trend: 1.4,
          periodKey: period,
          periodLabel: labelByPeriod(period),
          recent: fallbackRecent.map((item) => ({ ...item })),
        })
      }
      if (g.status === "fulfilled" && g.value?.data) {
        const d = g.value.data
        setGrades({
          average: toNumber(d.average, 4.4),
          scale: (d.scale as GradeStats["scale"]) || "5",
          trend: toNumber(d.trend, 0.3),
          recent: Array.isArray(d.recent) ? d.recent : [],
        })
      } else {
        const fallbackRecent = fallbackGradeRecentRef.current
        setGrades({
          average: 4.4,
          scale: "5",
          trend: 0.3,
          recent: fallbackRecent.map((item) => ({ ...item })),
        })
      }
      if (p.status === "fulfilled" && p.value?.data) {
        const d = p.value.data
        setParticipation({
          events: toNumber(d.events),
          hours: d.hours != null ? toNumber(d.hours) : undefined,
          groups: d.groups != null ? toNumber(d.groups) : undefined,
          trend: toNumber(d.trend),
          recent: Array.isArray(d.recent) ? d.recent : [],
        })
      } else {
        const fallbackRecent = fallbackParticipationRecentRef.current
        setParticipation({
          events: 6,
          hours: 12,
          groups: 2,
          trend: 2.0,
          recent: fallbackRecent.map((item) => ({ ...item })),
        })
      }
    } finally {
      if (summaryRequestRef.current === controller) {
        summaryRequestRef.current = null
      }
      if (!controller.signal.aborted) {
        setLoading(false)
        setHasInitiallyLoaded(true)
      }
    }
  }, [period, labelByPeriod])

  useEffect(() => {
    void fetchSummary()
  }, [fetchSummary, language])

  useEffect(() => {
    return () => {
      summaryRequestRef.current?.abort()
    }
  }, [])

  return {
    t,
    period,
    setPeriod,
    attendance,
    grades,
    participation,
    loading,
    hasInitiallyLoaded,
    detail,
    setDetail,
    detailSection,
    periodOptions,
    separator,
    noDataText,
    attendanceLessonFallback,
    formatDate,
    attendanceStatusLabel,
    labelByPeriod,
  }
}
