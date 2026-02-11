import Layout from "../components/Layout"
import PageFadeIn from "../components/PageFadeIn"
import axios from "../api/client"
import { useEffect, useState, useCallback, useMemo, useRef, type CSSProperties } from "react"
import {
  motion,
  AnimatePresence,
  useMotionValue,
  useTransform,
  animate,
  useReducedMotion,
} from "framer-motion"
import {
  Activity as TimelineIcon,
  TrendingUp as TrendingUpIcon,
  TrendingDown as TrendingDownIcon,
  CalendarCheck as EventAvailableIcon,
  GraduationCap as SchoolIcon,
  Award as EmojiEventsIcon,
} from "lucide-react"
import { useTranslation } from "react-i18next"
import { getLocaleForLanguage, useLanguage } from "@/contexts/LanguageContext"
import { Badge, Button, ProgressBar } from "@/components/ui"
import Dialog from "@/components/Dialog"
import { cn } from "@/utils/cn"
import useMediaQuery from "@/hooks/useMediaQuery"
import { breakpoints } from "@/theme/tokens"

const toNumber = (value: unknown, fallback = 0) => {
  const num = Number(value)
  return Number.isFinite(num) ? num : fallback
}

const easeOutExpo = [0.22, 1, 0.36, 1] as const
const periodValues = ["30d", "90d", "180d"] as const
type PeriodKey = (typeof periodValues)[number]
const periodDayCount = (key: PeriodKey): number => {
  switch (key) {
    case "30d":
      return 30
    case "90d":
      return 90
    case "180d":
      return 180
    default:
      return 0
  }
}

const isPeriodKey = (value: unknown): value is PeriodKey =>
  typeof value === "string" && periodValues.includes(value as PeriodKey)

type AttendanceStats = {
  percent: number
  present: number
  total: number
  trend: number
  periodLabel: string
  periodKey: string
  recent: Array<{ date: string; status: "present" | "absent" | "late"; course?: string }>
}
type GradeStats = {
  average: number
  scale: "5" | "100" | "gpa"
  trend: number
  recent: Array<{ course: string; score: number; max?: number; date: string }>
}
type ParticipationStats = {
  events: number
  hours?: number
  groups?: number
  trend: number
  recent: Array<{ title: string; date: string; role?: string }>
}

const defaultAttendanceRecent: AttendanceStats["recent"] = [
  { date: "2025-09-19", status: "present", course: "Algebra" },
  { date: "2025-09-18", status: "late", course: "History" },
  { date: "2025-09-17", status: "present", course: "Physics" },
]

const defaultGradeRecent: GradeStats["recent"] = [
  { course: "Algebra", score: 5, date: "2025-09-18" },
  { course: "Physics", score: 4, date: "2025-09-16" },
  { course: "Literature", score: 5, date: "2025-09-13" },
]

const defaultParticipationRecent: ParticipationStats["recent"] = [
  { title: "Department hackathon", date: "2025-09-14", role: "participant" },
  { title: "Basketball tournament", date: "2025-09-07", role: "team" },
]

const isAttendanceStatus = (value: unknown): value is AttendanceStats["recent"][number]["status"] =>
  value === "present" || value === "late" || value === "absent"

const parseAttendanceRecent = (value: unknown): AttendanceStats["recent"] => {
  if (!Array.isArray(value)) return []
  return value
    .map((item) => {
      if (!item || typeof item !== "object") return null
      const entry = item as Record<string, unknown>
      const date = typeof entry.date === "string" ? entry.date : null
      const status = entry.status
      if (!date || !isAttendanceStatus(status)) return null
      const course = typeof entry.course === "string" ? entry.course : undefined
      return {
        date,
        status,
        ...(course !== undefined ? { course } : {}),
      }
    })
    .filter((item): item is AttendanceStats["recent"][number] => item != null)
}

const parseGradeRecent = (value: unknown): GradeStats["recent"] => {
  if (!Array.isArray(value)) return []
  return value
    .map((item) => {
      if (!item || typeof item !== "object") return null
      const entry = item as Record<string, unknown>
      const course = typeof entry.course === "string" ? entry.course : null
      const score = toNumber(entry.score, Number.NaN)
      if (!course || Number.isNaN(score)) return null
      const maxRaw = entry.max
      const max = maxRaw != null ? toNumber(maxRaw, Number.NaN) : undefined
      const date = typeof entry.date === "string" ? entry.date : ""
      return {
        course,
        score,
        date,
        ...(max != null && !Number.isNaN(max) ? { max } : {}),
      }
    })
    .filter((item): item is GradeStats["recent"][number] => item != null)
}

const parseParticipationRecent = (value: unknown): ParticipationStats["recent"] => {
  if (!Array.isArray(value)) return []
  return value
    .map((item) => {
      if (!item || typeof item !== "object") return null
      const entry = item as Record<string, unknown>
      const title = typeof entry.title === "string" ? entry.title : null
      if (!title) return null
      const date = typeof entry.date === "string" ? entry.date : ""
      const role = typeof entry.role === "string" ? entry.role : undefined
      return {
        title,
        date,
        ...(role !== undefined ? { role } : {}),
      }
    })
    .filter((item): item is ParticipationStats["recent"][number] => item != null)
}

type AttendanceSummaryResponse = {
  percent?: unknown
  present?: unknown
  total?: unknown
  trend?: unknown
  period_key?: unknown
  period_label?: unknown
  recent?: unknown
}

type GradeSummaryResponse = {
  average?: unknown
  scale?: unknown
  trend?: unknown
  recent?: unknown
}

type ParticipationSummaryResponse = {
  events?: unknown
  hours?: unknown
  groups?: unknown
  trend?: unknown
  recent?: unknown
}

type DetailSection = "" | "attendance" | "grades" | "participation"

function useAnimatedNumber(target: number, duration = 0.9, fraction = 0) {
  const reduce = useReducedMotion()
  const mv = useMotionValue(reduce ? target : 0)
  const [val, setVal] = useState<number>(reduce ? target : 0)
  useEffect(() => {
    const controls = animate(mv, target, { duration: reduce ? 0 : duration, ease: easeOutExpo })
    const unsubscribe = mv.on("change", (value: number) => setVal(value))
    return () => {
      controls.stop()
      unsubscribe()
    }
  }, [target, duration, reduce, mv])
  return useMemo(() => Number(val).toFixed(fraction), [val, fraction])
}

function AnimatedRing({
  value,
  size = 96,
  tone,
}: {
  value: number
  size?: number
  tone: "success" | "info" | "warning"
}) {
  const reduce = useReducedMotion()
  const stroke = 8
  const r = (size - stroke) / 2
  const c = 2 * Math.PI * r
  const prevValueRef = useRef(value)
  const mv = useMotionValue(reduce ? value : prevValueRef.current)

  useEffect(() => {
    const controls = animate(mv, value, {
      duration: reduce ? 0 : 0.8,
      ease: easeOutExpo,
    })
    prevValueRef.current = value
    return () => controls.stop()
  }, [value, reduce, mv])

  const dash = useTransform(mv, (v) => c - (Math.max(0, Math.min(100, v)) / 100) * c)

  const colorClasses = {
    success: "stroke-success-text",
    info: "stroke-brand",
    warning: "stroke-warning-text",
  }

  const bgColorClasses = {
    success: "stroke-success-text/(--opacity-dim)",
    info: "stroke-brand/(--opacity-dim)",
    warning: "stroke-warning-text/(--opacity-dim)",
  }

  return (
    <div className="relative shrink-0" style={{ width: size, height: size }}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} className="block">
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          className={bgColorClasses[tone]}
          strokeWidth={stroke}
        />
        <motion.circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          className={colorClasses[tone]}
          strokeWidth={stroke}
          strokeLinecap="round"
          strokeDasharray={c}
          style={{ strokeDashoffset: dash }}
        />
      </svg>
      <div className="absolute inset-0 grid place-items-center font-black tracking-tighter tabular-nums lining-nums text-(--text-primary)">
        {Math.round(value)}%
      </div>
    </div>
  )
}

const fadeDelayStyle = (value: string): CSSProperties =>
  ({ "--fade-delay": value }) as CSSProperties

export default function Activity() {
  const { t } = useTranslation(["activity", "common"])
  const { language } = useLanguage()
  const locale = getLocaleForLanguage(language)
  const reduce = useReducedMotion()
  const isSm = useMediaQuery(`(max-width: ${breakpoints.small})`)
  const isMd = useMediaQuery(`(max-width: ${breakpoints.mobile})`)
  const isXl = useMediaQuery(`(min-width: ${breakpoints.desktop})`)
  const ringSize = isSm ? 68 : isMd ? 84 : isXl ? 104 : 96

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
      periodValues.map((value) => ({
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
  const fallbackAttendanceRecentRef = useRef(defaultAttendanceRecent)
  const fallbackGradeRecentRef = useRef(defaultGradeRecent)
  const fallbackParticipationRecentRef = useRef(defaultParticipationRecent)

  useEffect(() => {
    const attendanceRaw = t("activity:fallback.attendance.recent", {
      returnObjects: true,
    }) as unknown
    const attendanceParsed = parseAttendanceRecent(attendanceRaw)
    fallbackAttendanceRecentRef.current =
      attendanceParsed.length > 0 ? attendanceParsed : defaultAttendanceRecent

    const gradesRaw = t("activity:fallback.grades.recent", { returnObjects: true }) as unknown
    const gradesParsed = parseGradeRecent(gradesRaw)
    fallbackGradeRecentRef.current = gradesParsed.length > 0 ? gradesParsed : defaultGradeRecent

    const participationRaw = t("activity:fallback.participation.recent", {
      returnObjects: true,
    }) as unknown
    const participationParsed = parseParticipationRecent(participationRaw)
    fallbackParticipationRecentRef.current =
      participationParsed.length > 0 ? participationParsed : defaultParticipationRecent
  }, [t])

  const summaryRequestRef = useRef<AbortController | null>(null)

  const fetchSummary = useCallback(async () => {
    summaryRequestRef.current?.abort()
    const controller = new AbortController()
    summaryRequestRef.current = controller

    setLoading(true)

    try {
      const [a, g, p] = await Promise.allSettled([
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

  const TrendChip = ({ value }: { value?: number }) =>
    typeof value === "number" ? (
      <Badge
        size="xs"
        variant="outline"
        tone={value >= 0 ? "success" : "danger"}
        leadingIcon={
          value >= 0 ? (
            <TrendingUpIcon className="text-badge!" />
          ) : (
            <TrendingDownIcon className="text-badge!" />
          )
        }
        className="font-extrabold"
      >
        {`${value > 0 ? "+" : ""}${value.toFixed(1)}%`}
      </Badge>
    ) : null

  const attendanceItemKey = useCallback(
    (item: AttendanceStats["recent"][number], index: number) =>
      `${item?.date ?? index}-${item?.course ?? index}-${item?.status ?? ""}`,
    []
  )
  const gradeItemKey = useCallback(
    (item: GradeStats["recent"][number], index: number) =>
      `${item?.date ?? index}-${item?.course ?? index}-${item?.score ?? ""}-${item?.max ?? ""}`,
    []
  )
  const participationItemKey = useCallback(
    (item: ParticipationStats["recent"][number], index: number) =>
      `${item?.date ?? index}-${item?.title ?? index}-${item?.role ?? ""}`,
    []
  )
  const pickKeyCandidate = useCallback((value: unknown): string | number | undefined => {
    return typeof value === "number" || typeof value === "string" ? value : undefined
  }, [])

  const CardShell = ({
    tone = "neutral",
    onClick,
    children,
  }: {
    tone?: "neutral" | "success" | "info" | "warning"
    onClick?: () => void
    children: React.ReactNode
  }) => {
    const toneClasses = {
      neutral: "bg-glass-elevated",
      success:
        "bg-linear-to-b from-success-bg/(--opacity-soft) to-success-bg/(--opacity-medium) dark:from-success-bg/(--opacity-dim) dark:to-success-bg/(--opacity-medium)",
      info: "bg-linear-to-b from-brand/(--opacity-subtle) to-brand/(--opacity-dim) dark:from-brand/(--opacity-dim) dark:to-brand/(--opacity-soft)",
      warning:
        "bg-linear-to-b from-warning-bg/(--opacity-soft) to-warning-bg/(--opacity-medium) dark:from-warning-bg/(--opacity-dim) dark:to-warning-bg/(--opacity-medium)",
    }

    return (
      <motion.div
        initial={hasInitiallyLoaded ? false : { y: reduce ? 0 : 14, opacity: reduce ? 1 : 0 }}
        animate={{ y: 0, opacity: 1 }}
        transition={{ type: "spring", stiffness: 260, damping: 32, mass: 1 }}
        className={cn(
          "relative flex h-full flex-col overflow-hidden rounded-2xl border border-glass-border-subtle backdrop-blur-xl [-webkit-backdrop-filter:blur(12px)]",
          toneClasses[tone],
          "shadow-premium",
          "transition-all duration-180",
          reduce ? "" : "hover:-translate-y-0.5 hover:shadow-premium",
          "active:translate-y-0",
          onClick &&
            "cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-2"
        )}
        style={
          reduce ? undefined : { willChange: "transform, opacity", transform: "translateZ(0)" }
        }
      >
        <button
          onClick={onClick}
          className={cn(
            "flex h-full flex-col items-stretch rounded-2xl p-4 text-left md:p-6 xl:p-8",
            onClick ? "" : "pointer-events-none"
          )}
        >
          <div className="flex flex-1 flex-col gap-2">{children}</div>
        </button>
      </motion.div>
    )
  }

  const headerVariants = {
    hidden: { opacity: 0, y: reduce ? 0 : 10 },
    show: { opacity: 1, y: 0, transition: { duration: 0.35, ease: easeOutExpo } },
  }
  const gridVariants = {
    show: { transition: { staggerChildren: reduce ? 0 : 0.06, delayChildren: 0.05 } },
  }
  const listItemVariants = {
    hidden: { opacity: 0, y: reduce ? 0 : 8 },
    show: { opacity: 1, y: 0, transition: { duration: 0.28 } },
  }

  const attendancePctAnimated = useAnimatedNumber(
    Math.max(0, Math.min(100, attendance?.percent ?? 0)),
    0.9,
    0
  )
  const gradeAverage = toNumber(grades?.average)
  const gradeAnimatedValue = grades?.scale === "100" ? Math.round(gradeAverage) : gradeAverage
  const gradesAnimated = useAnimatedNumber(
    gradeAnimatedValue,
    0.9,
    grades?.scale === "gpa" ? 2 : grades?.scale === "5" ? 1 : 0
  )
  const partEventsAnimated = useAnimatedNumber(Math.round(participation?.events ?? 0), 0.9, 0)

  const progressAttendanceMv = useMotionValue(0)
  const [progressAttendance, setProgressAttendance] = useState(0)
  useEffect(() => {
    const target = Math.max(0, Math.min(100, attendance?.percent ?? 0))
    const controls = animate(progressAttendanceMv, target, {
      duration: reduce ? 0 : 0.9,
      ease: easeOutExpo,
    })
    const unsubscribe = progressAttendanceMv.on("change", (value: number) =>
      setProgressAttendance(value)
    )
    return () => {
      controls.stop()
      unsubscribe()
    }
  }, [attendance?.percent, reduce, progressAttendanceMv])

  return (
    <Layout>
      <PageFadeIn>
        <div className="w-screen min-h-screen bg-(--bg-page) text-(--text-primary) py-8 sm:py-10">
          <motion.div
            initial="hidden"
            animate="show"
            variants={headerVariants}
            className="px-2 pb-16 sm:px-4"
            style={
              reduce ? undefined : { willChange: "transform, opacity", transform: "translateZ(0)" }
            }
          >
            <div
              data-fade
              style={fadeDelayStyle("80ms")}
              className="mb-8 flex flex-wrap items-center gap-4 sm:gap-5"
            >
              <div className="flex h-12 w-12 items-center justify-center rounded-full bg-brand-subtle-bg text-brand shadow-glass transition-transform duration-200 hover:scale-105 backdrop-blur-sm">
                <TimelineIcon className="text-3xl" />
              </div>
              <h1 className="text-page-title font-bold tracking-tight text-(--text-primary)">
                {t("activity:title")}
              </h1>
            </div>
            <motion.div
              data-fade
              initial={{ opacity: 0, y: reduce ? 0 : 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: reduce ? 0 : 0.35 }}
              style={{
                ...(reduce ? {} : { willChange: "transform, opacity", transform: "translateZ(0)" }),
                ...fadeDelayStyle("140ms"),
              }}
              className="mb-6 inline-flex items-center gap-1 rounded-full border border-glass-border bg-(--bg-surface)/(--opacity-medium) p-1 shadow-premium backdrop-blur-xl [-webkit-backdrop-filter:blur(12px)] dark:border-glass-border dark:bg-(--bg-page)/(--opacity-medium) dark:shadow-premium"
            >
              {periodOptions.map((option) => (
                <button
                  key={option.value}
                  onClick={() => setPeriod(option.value)}
                  className={cn(
                    "relative rounded-full border-0 px-4 py-1.5 text-sm font-bold transition-colors duration-150",
                    period === option.value
                      ? "text-white"
                      : "bg-transparent text-(--text-primary) hover:bg-brand-subtle-bg hover:text-brand"
                  )}
                >
                  {period === option.value && (
                    <motion.span
                      layoutId="activity-period-indicator"
                      className="absolute inset-0 rounded-full bg-brand shadow-glass"
                      transition={{ type: "spring", stiffness: 400, damping: 30 }}
                    />
                  )}
                  <span className="relative z-(--z-base)">{option.label}</span>
                </button>
              ))}
            </motion.div>

            <motion.div
              variants={gridVariants}
              initial="hidden"
              animate="show"
              className="mb-4 grid grid-cols-1 gap-4 sm:grid-cols-2 md:mb-6 md:grid-cols-3 md:gap-6"
              style={
                reduce
                  ? undefined
                  : { willChange: "transform, opacity", transform: "translateZ(0)" }
              }
            >
              <CardShell tone="success" onClick={() => setDetail("attendance")}>
                <div className="flex items-center gap-4">
                  <AnimatedRing value={attendance?.percent ?? 0} size={ringSize} tone="success" />
                  <div className="flex min-w-0 flex-1 flex-col gap-1">
                    <p className="text-micro font-semibold uppercase tracking-wider text-(--text-tertiary)">
                      {t("activity:sections.attendance.title")}
                    </p>
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="text-(--fs-card-stat) font-black tracking-tighter tabular-nums lining-nums">
                        {attendancePctAnimated}%
                      </span>
                      <TrendChip value={attendance?.trend} />
                    </div>
                    <ProgressBar
                      value={progressAttendance}
                      className="h-2 rounded-full"
                      barClassName="bg-(--success-text) rounded-full transition-[width] duration-600"
                    />
                    <p className="truncate text-sm text-(--text-muted-subtle)">
                      {t("activity:sections.attendance.summary", {
                        present: attendance?.present ?? 0,
                        total: attendance?.total ?? 0,
                        period: attendance?.periodLabel || labelByPeriod(period),
                      })}
                    </p>
                  </div>
                </div>
              </CardShell>

              <CardShell tone="info" onClick={() => setDetail("grades")}>
                <div className="flex flex-col gap-1">
                  <p className="text-micro font-semibold uppercase tracking-wider text-(--text-label)">
                    {t("activity:sections.grades.title")}
                  </p>
                  <div className="flex items-center gap-2">
                    <span className="text-(--fs-card-stat) font-black tracking-tighter tabular-nums lining-nums">
                      {grades?.scale === "gpa"
                        ? `GPA ${gradesAnimated}`
                        : grades?.scale === "100"
                          ? `${gradesAnimated}/100`
                          : `${gradesAnimated}/5`}
                    </span>
                    <TrendChip value={grades?.trend} />
                  </div>
                  <p className="text-sm text-text-muted-subtle">
                    {t("activity:sections.grades.averageLabel")}
                  </p>
                </div>
              </CardShell>

              <CardShell tone="warning" onClick={() => setDetail("participation")}>
                <div className="flex flex-col gap-1">
                  <p className="text-micro font-semibold uppercase tracking-wider text-(--text-label)">
                    {t("activity:sections.participation.title")}
                  </p>
                  <div className="flex items-center gap-2">
                    <span className="text-card-stat font-black tracking-tighter tabular-nums lining-nums text-(--text-primary)">
                      {t("activity:sections.participation.eventsCount", {
                        value: partEventsAnimated,
                        count: participation?.events ?? 0,
                      })}
                    </span>
                    <TrendChip value={participation?.trend} />
                  </div>
                  <p className="text-sm text-text-muted-subtle">
                    {[
                      participation?.hours != null
                        ? t("activity:sections.participation.summaryHours", {
                            count: participation.hours ?? 0,
                          })
                        : null,
                      participation?.groups != null
                        ? t("activity:sections.participation.summaryGroups", {
                            count: participation.groups ?? 0,
                          })
                        : null,
                    ]
                      .filter(Boolean)
                      .join(separator)}
                  </p>
                </div>
              </CardShell>
            </motion.div>

            <div className="my-4 border-t border-glass-border-subtle md:my-6" />

            <motion.div
              variants={gridVariants}
              initial="hidden"
              animate="show"
              className="grid grid-cols-1 gap-4 sm:grid-cols-2 md:grid-cols-3 md:gap-6"
            >
              <CardShell onClick={() => setDetail("attendance_recent")}>
                <div className="flex flex-col">
                  <div className="mb-2 flex items-center gap-2">
                    <EventAvailableIcon className="text-base text-brand" />
                    <h3 className="font-black text-(--text-primary)">
                      {t("activity:sections.attendance.recent")}
                    </h3>
                  </div>
                  <div className="space-y-1">
                    <AnimatePresence initial={false}>
                      {(attendance?.recent ?? []).slice(0, 6).map((r, i) => {
                        const color =
                          r.status === "present"
                            ? "var(--success-text)"
                            : r.status === "late"
                              ? "var(--warning-text)"
                              : "var(--error-text)"
                        const darkColor =
                          r.status === "present"
                            ? "var(--success-text)"
                            : r.status === "late"
                              ? "var(--warning-text)"
                              : "var(--error-text)"
                        const attendanceRecord = r as Partial<{
                          id?: number | string
                          lesson_id?: number | string
                        }>
                        const itemKey =
                          pickKeyCandidate(attendanceRecord.id) ??
                          pickKeyCandidate(attendanceRecord.lesson_id) ??
                          attendanceItemKey(r, i)
                        return (
                          <motion.div
                            key={itemKey}
                            variants={listItemVariants}
                            initial={hasInitiallyLoaded ? false : "hidden"}
                            animate="show"
                            exit={{ opacity: 0 }}
                            transition={{ delay: reduce || hasInitiallyLoaded ? 0 : i * 0.04 }}
                            className="py-1"
                            style={
                              reduce
                                ? undefined
                                : { willChange: "transform, opacity", transform: "translateZ(0)" }
                            }
                          >
                            <div className="flex items-center gap-2">
                              <div
                                className="h-2 w-2 rounded-full dark:hidden"
                                style={{
                                  background: color,
                                  boxShadow: `0 0 0 3px ${color}18`,
                                }}
                              />
                              <div
                                className="hidden h-2 w-2 rounded-full dark:block"
                                style={{
                                  background: darkColor,
                                  boxShadow: `0 0 0 3px ${darkColor}18`,
                                }}
                              />
                              <div className="flex min-w-0 flex-1 flex-wrap items-baseline gap-1.5">
                                <span className="font-bold text-(--text-primary)">
                                  {r.course || attendanceLessonFallback}
                                </span>
                                <span className="text-sm text-(--text-label)">
                                  {attendanceStatusLabel(r.status)}
                                </span>
                              </div>
                            </div>
                            <p className="ml-4 text-xs text-(--text-label)">{formatDate(r.date)}</p>
                          </motion.div>
                        )
                      })}
                    </AnimatePresence>
                    {!loading && (!attendance?.recent || attendance.recent.length === 0) && (
                      <p className="px-1 py-1 text-sm text-(--text-label)">{noDataText}</p>
                    )}
                  </div>
                </div>
              </CardShell>

              <CardShell onClick={() => setDetail("grades_recent")}>
                <div className="flex flex-col">
                  <div className="mb-2 flex items-center gap-2">
                    <SchoolIcon className="text-base text-(--primary-main)" />
                    <h3 className="font-black text-(--text-primary)">
                      {t("activity:sections.grades.recent")}
                    </h3>
                  </div>
                  <div className="space-y-1">
                    <AnimatePresence initial={false}>
                      {(grades?.recent ?? []).slice(0, 6).map((r, i) => {
                        const gradeRecord = r as Partial<{ id?: number | string }>
                        const itemKey = pickKeyCandidate(gradeRecord.id) ?? gradeItemKey(r, i)
                        return (
                          <motion.div
                            key={itemKey}
                            variants={listItemVariants}
                            initial={hasInitiallyLoaded ? false : "hidden"}
                            animate="show"
                            exit={{ opacity: 0 }}
                            transition={{ delay: reduce || hasInitiallyLoaded ? 0 : i * 0.04 }}
                            className="py-1"
                            style={
                              reduce
                                ? undefined
                                : { willChange: "transform, opacity", transform: "translateZ(0)" }
                            }
                          >
                            <div className="flex items-center gap-2">
                              <div className="h-2 w-2 rounded-full bg-(--primary-main)/(--opacity-heavy) shadow-pulse-primary" />
                              <div className="flex min-w-0 flex-1 flex-wrap items-baseline gap-1.5">
                                <span className="font-bold text-(--text-primary)">{r.course}</span>
                                <span className="text-sm text-(--text-label)">
                                  {r.score}
                                  {r.max ? "/" + r.max : ""}
                                </span>
                              </div>
                            </div>
                            <p className="ml-4 text-xs text-(--text-label)">{formatDate(r.date)}</p>
                          </motion.div>
                        )
                      })}
                    </AnimatePresence>
                    {!loading && (!grades?.recent || grades.recent.length === 0) && (
                      <p className="px-1 py-1 text-sm text-(--text-label)">{noDataText}</p>
                    )}
                  </div>
                </div>
              </CardShell>

              <CardShell onClick={() => setDetail("participation_recent")}>
                <div className="flex flex-col">
                  <div className="mb-2 flex items-center gap-2">
                    <EmojiEventsIcon className="text-base text-(--primary-main)" />
                    <h3 className="font-black text-(--text-primary)">
                      {t("activity:sections.participation.recent")}
                    </h3>
                  </div>
                  <div className="space-y-1">
                    <AnimatePresence initial={false}>
                      {(participation?.recent ?? []).slice(0, 6).map((r, i) => {
                        const participationRecord = r as Partial<{ id?: number | string }>
                        const itemKey =
                          pickKeyCandidate(participationRecord.id) ?? participationItemKey(r, i)
                        return (
                          <motion.div
                            key={itemKey}
                            variants={listItemVariants}
                            initial={hasInitiallyLoaded ? false : "hidden"}
                            animate="show"
                            exit={{ opacity: 0 }}
                            transition={{ delay: reduce || hasInitiallyLoaded ? 0 : i * 0.04 }}
                            className="py-1"
                            style={
                              reduce
                                ? undefined
                                : { willChange: "transform, opacity", transform: "translateZ(0)" }
                            }
                          >
                            <div className="flex items-center gap-2">
                              <div className="h-2 w-2 rounded-full bg-(--warning-text)/(--opacity-heavy) shadow-pulse-warning" />
                              <div className="flex min-w-0 flex-1 flex-wrap items-baseline gap-1.5">
                                <span className="font-bold text-(--text-primary)">{r.title}</span>
                                <span className="text-sm text-(--text-label)">
                                  {[formatDate(r.date), r.role].filter(Boolean).join(separator)}
                                </span>
                              </div>
                            </div>
                          </motion.div>
                        )
                      })}
                    </AnimatePresence>
                    {!loading && (!participation?.recent || participation.recent.length === 0) && (
                      <p className="px-1 py-1 text-sm text-(--text-label)">{noDataText}</p>
                    )}
                  </div>
                </div>
              </CardShell>
            </motion.div>
          </motion.div>

          <Dialog
            open={detail !== ""}
            onClose={() => setDetail("")}
            title={detailSection ? t(`activity:sections.${detailSection}.dialogTitle`) : ""}
            size="md"
          >
            {detail === "attendance" && (
              <div className="space-y-4">
                <p className="text-base text-(--text-primary)">
                  {t("activity:sections.attendance.dialogTotal", {
                    present: attendance?.present ?? 0,
                    total: attendance?.total ?? 0,
                    period: attendance?.periodLabel || labelByPeriod(period),
                  })}
                </p>
                <ProgressBar
                  value={Math.max(0, Math.min(100, attendance?.percent ?? 0))}
                  className="h-2.5 rounded-lg"
                  barClassName="bg-(--success-text) rounded-lg"
                />
                <div className="space-y-2">
                  {(attendance?.recent ?? []).map((r, i) => (
                    <div key={attendanceItemKey(r, i)} className="space-y-0.5">
                      <p className="text-sm font-semibold text-(--text-primary)">
                        {`${r.course || attendanceLessonFallback} — ${attendanceStatusLabel(r.status)}`}
                      </p>
                      <p className="text-xs text-(--text-caption)">{formatDate(r.date)}</p>
                    </div>
                  ))}
                </div>
              </div>
            )}
            {detail === "grades" && (
              <div className="space-y-4">
                <p className="text-base font-semibold text-(--text-primary)">
                  {grades?.scale === "gpa"
                    ? `GPA ${(grades?.average ?? 0).toFixed(2)}`
                    : grades?.scale === "100"
                      ? `${Math.round(grades?.average ?? 0)}/100`
                      : `${(grades?.average ?? 0).toFixed(1)}/5`}
                </p>
                <div className="space-y-2">
                  {(grades?.recent ?? []).map((r, i) => (
                    <div key={gradeItemKey(r, i)} className="space-y-0.5">
                      <p className="text-sm font-semibold text-(--text-primary)">
                        {`${r.course} — ${r.score}${r.max ? "/" + r.max : ""}`}
                      </p>
                      <p className="text-xs text-(--text-caption)">{formatDate(r.date)}</p>
                    </div>
                  ))}
                </div>
              </div>
            )}
            {detail === "participation" && (
              <div className="space-y-4">
                <p className="text-base text-(--text-primary)">
                  {[
                    t("activity:sections.participation.eventsCount", {
                      value: String(participation?.events ?? 0),
                      count: participation?.events ?? 0,
                    }),
                    participation?.hours != null
                      ? t("activity:sections.participation.summaryHours", {
                          count: participation.hours ?? 0,
                        })
                      : null,
                    participation?.groups != null
                      ? t("activity:sections.participation.summaryGroups", {
                          count: participation.groups ?? 0,
                        })
                      : null,
                  ]
                    .filter(Boolean)
                    .join(separator)}
                </p>
                <div className="space-y-2">
                  {(participation?.recent ?? []).map((r, i) => (
                    <div key={participationItemKey(r, i)} className="space-y-0.5">
                      <p className="text-sm font-semibold text-(--text-primary)">{r.title}</p>
                      <p className="text-xs text-(--text-caption)">
                        {[formatDate(r.date), r.role].filter(Boolean).join(separator)}
                      </p>
                    </div>
                  ))}
                </div>
              </div>
            )}
            {detail === "attendance_recent" && (
              <div className="space-y-2">
                {(attendance?.recent ?? []).map((r, i) => (
                  <div key={attendanceItemKey(r, i)} className="space-y-0.5">
                    <p className="text-sm font-semibold text-(--text-primary)">
                      {`${r.course || attendanceLessonFallback} — ${attendanceStatusLabel(r.status)}`}
                    </p>
                    <p className="text-xs text-(--text-caption)">{formatDate(r.date)}</p>
                  </div>
                ))}
              </div>
            )}
            {detail === "grades_recent" && (
              <div className="space-y-2">
                {(grades?.recent ?? []).map((r, i) => (
                  <div key={gradeItemKey(r, i)} className="space-y-0.5">
                    <p className="text-sm font-semibold text-(--text-primary)">
                      {`${r.course} — ${r.score}${r.max ? "/" + r.max : ""}`}
                    </p>
                    <p className="text-xs text-(--text-caption)">{formatDate(r.date)}</p>
                  </div>
                ))}
              </div>
            )}
            {detail === "participation_recent" && (
              <div className="space-y-2">
                {(participation?.recent ?? []).map((r, i) => (
                  <div key={participationItemKey(r, i)} className="space-y-0.5">
                    <p className="text-sm font-semibold text-(--text-primary)">{r.title}</p>
                    <p className="text-xs text-(--text-caption)">
                      {[formatDate(r.date), r.role].filter(Boolean).join(separator)}
                    </p>
                  </div>
                ))}
              </div>
            )}
            <div className="mt-6 flex justify-end">
              <Button variant="outline" onClick={() => setDetail("")}>
                {t("activity:dialog.close")}
              </Button>
            </div>
          </Dialog>
        </div>
      </PageFadeIn>
    </Layout>
  )
}
