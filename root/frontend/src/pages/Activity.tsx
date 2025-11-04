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
import TimelineIcon from "@mui/icons-material/Timeline"
import TrendingUpIcon from "@mui/icons-material/TrendingUp"
import TrendingDownIcon from "@mui/icons-material/TrendingDown"
import EventAvailableIcon from "@mui/icons-material/EventAvailable"
import SchoolIcon from "@mui/icons-material/School"
import EmojiEventsIcon from "@mui/icons-material/EmojiEvents"
import { useTranslation } from "react-i18next"
import { getLocaleForLanguage, useLanguage } from "@/contexts/LanguageContext"
import { Badge, Button, ProgressBar } from "@/components/ui"
import Dialog from "@/components/Dialog"
import { cn } from "@/utils/cn"
import useMediaQuery from "@/hooks/useMediaQuery"

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
  const mv = useMotionValue(reduce ? value : 0)

  useEffect(() => {
    const controls = animate(mv, value, {
      duration: reduce ? 0 : 1.1,
      type: "spring",
      stiffness: 120,
      damping: 24,
    })
    return () => controls.stop()
  }, [value, reduce, mv])

  const dash = useTransform(mv, (v) => c - (Math.max(0, Math.min(100, v)) / 100) * c)

  const colorClasses = {
    success: "stroke-[#10b981] dark:stroke-[#34d399]",
    info: "stroke-[#3b82f6] dark:stroke-[#60a5fa]",
    warning: "stroke-[#f59e0b] dark:stroke-[#fbbf24]",
  }

  const bgColorClasses = {
    success: "stroke-[#10b981]/15 dark:stroke-[#34d399]/15",
    info: "stroke-[#3b82f6]/15 dark:stroke-[#60a5fa]/15",
    warning: "stroke-[#f59e0b]/15 dark:stroke-[#fbbf24]/15",
  }

  return (
    <div className="relative flex-shrink-0" style={{ width: size, height: size }}>
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
      <div className="absolute inset-0 grid place-items-center font-black tracking-tighter tabular-nums lining-nums text-[color:var(--page-text)]">
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
  const isSm = useMediaQuery("(max-width: 640px)")
  const isMd = useMediaQuery("(max-width: 768px)")
  const isXl = useMediaQuery("(min-width: 1280px)")
  const ringSize = isSm ? 68 : isMd ? 84 : isXl ? 104 : 96

  const [period, setPeriod] = useState<PeriodKey>("90d")
  const [attendance, setAttendance] = useState<AttendanceStats | null>(null)
  const [grades, setGrades] = useState<GradeStats | null>(null)
  const [participation, setParticipation] = useState<ParticipationStats | null>(null)
  const [loading, setLoading] = useState(false)
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
            <TrendingUpIcon className="!text-[0.7rem]" />
          ) : (
            <TrendingDownIcon className="!text-[0.7rem]" />
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
      neutral:
        "bg-[color:color-mix(in_srgb,var(--card-bg)_96%,white_4%)] dark:bg-[color:color-mix(in_srgb,var(--card-bg)_94%,transparent_6%)]",
      success:
        "bg-[linear-gradient(180deg,color-mix(in_srgb,var(--card-bg)_96%,white_4%)_0%,color-mix(in_srgb,var(--card-bg)_92%,white_8%)_100%),linear-gradient(#10b981/10,#10b981/10)] dark:bg-[linear-gradient(180deg,color-mix(in_srgb,var(--card-bg)_94%,transparent_6%)_0%,color-mix(in_srgb,var(--card-bg)_88%,transparent_12%)_100%),linear-gradient(#34d399/12,#34d399/12)]",
      info: "bg-[linear-gradient(180deg,color-mix(in_srgb,var(--card-bg)_96%,white_4%)_0%,color-mix(in_srgb,var(--card-bg)_92%,white_8%)_100%),linear-gradient(#3b82f6/10,#3b82f6/10)] dark:bg-[linear-gradient(180deg,color-mix(in_srgb,var(--card-bg)_94%,transparent_6%)_0%,color-mix(in_srgb,var(--card-bg)_88%,transparent_12%)_100%),linear-gradient(#60a5fa/12,#60a5fa/12)]",
      warning:
        "bg-[linear-gradient(180deg,color-mix(in_srgb,var(--card-bg)_96%,white_4%)_0%,color-mix(in_srgb,var(--card-bg)_92%,white_8%)_100%),linear-gradient(#f59e0b/10,#f59e0b/10)] dark:bg-[linear-gradient(180deg,color-mix(in_srgb,var(--card-bg)_94%,transparent_6%)_0%,color-mix(in_srgb,var(--card-bg)_88%,transparent_12%)_100%),linear-gradient(#fbbf24/12,#fbbf24/12)]",
    }

    return (
      <motion.div
        initial={{ y: reduce ? 0 : 14, opacity: reduce ? 1 : 0 }}
        animate={{ y: 0, opacity: 1 }}
        transition={{ type: "spring", stiffness: 260, damping: 32, mass: 1 }}
        className={cn(
          "relative flex h-full flex-col overflow-hidden rounded-2xl border border-[color:color-mix(in_srgb,white_12%,var(--nav-link)_88%)] backdrop-blur-xl [-webkit-backdrop-filter:blur(12px)]",
          toneClasses[tone],
          "shadow-[0_4px_16px_rgba(0,0,0,0.08),0_2px_6px_rgba(0,0,0,0.04)] dark:shadow-[0_6px_20px_rgba(0,0,0,0.16),0_2px_8px_rgba(0,0,0,0.08)]",
          "transition-all duration-180",
          reduce
            ? ""
            : "hover:-translate-y-0.5 hover:shadow-[0_10px_36px_rgba(0,0,0,0.12),0_4px_12px_rgba(0,0,0,0.08)] dark:hover:shadow-[0_4px_24px_rgba(0,0,0,0.36)]",
          "active:translate-y-0",
          onClick &&
            "cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--nav-link)] focus-visible:ring-offset-2"
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
        <motion.div
          initial="hidden"
          animate="show"
          variants={headerVariants}
          className="mx-auto w-full max-w-full px-4 py-6 pb-16 sm:px-6 md:px-8 md:py-8 xl:px-12 xl:pb-8"
          style={
            reduce ? undefined : { willChange: "transform, opacity", transform: "translateZ(0)" }
          }
        >
          <div
            data-fade
            style={fadeDelayStyle("80ms")}
            className="mb-4 flex flex-wrap items-center justify-between gap-4 md:mb-6"
          >
            <div className="flex items-center gap-3">
              <span className="inline-flex h-[34px] w-[34px] items-center justify-center rounded-xl border border-[color:color-mix(in_srgb,white_12%,var(--nav-link)_88%)] bg-[color:color-mix(in_srgb,var(--card-bg)_92%,var(--nav-link)_8%)] text-[color:var(--nav-link)] shadow-surface dark:bg-[color:color-mix(in_srgb,var(--card-bg)_88%,var(--nav-link)_12%)]">
                <TimelineIcon className="text-[20px]" />
              </span>
              <h1 className="text-[clamp(1.5rem,2.6vw,2.4rem)] font-black tracking-tight text-[color:var(--page-text)]">
                {t("activity:title")}
              </h1>
            </div>
            <motion.div
              initial={{ opacity: 0, y: reduce ? 0 : 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: reduce ? 0 : 0.35 }}
              style={
                reduce
                  ? undefined
                  : { willChange: "transform, opacity", transform: "translateZ(0)" }
              }
            >
              <div className="inline-flex items-center gap-1 rounded-full border border-[color:color-mix(in_srgb,white_12%,var(--nav-link)_88%)] bg-[color:color-mix(in_srgb,var(--card-bg)_96%,white_4%)] p-1 shadow-[0_4px_12px_rgba(0,0,0,0.08),0_2px_4px_rgba(0,0,0,0.04)] backdrop-blur-xl [-webkit-backdrop-filter:blur(12px)] dark:border-[color:color-mix(in_srgb,white_8%,var(--nav-link)_92%)] dark:bg-[color:color-mix(in_srgb,var(--card-bg)_94%,transparent_6%)] dark:shadow-[0_12px_34px_rgba(0,0,0,0.46)]">
                {periodOptions.map((option) => (
                  <button
                    key={option.value}
                    onClick={() => setPeriod(option.value)}
                    className={cn(
                      "rounded-full border-0 px-4 py-1.5 text-sm font-bold transition-all duration-150",
                      period === option.value
                        ? "bg-[color:var(--nav-link)] text-white shadow-[0_4px_12px_color-mix(in_srgb,var(--nav-link)_35%,transparent)] dark:shadow-[0_8px_24px_color-mix(in_srgb,var(--nav-link)_45%,transparent)]"
                        : "bg-transparent text-[color:var(--page-text)] hover:bg-[color:color-mix(in_srgb,var(--nav-link)_12%,transparent)] hover:text-[color:var(--nav-link)] dark:bg-[color:color-mix(in_srgb,white_8%,transparent)] dark:text-white dark:hover:bg-[color:color-mix(in_srgb,white_12%,transparent)]"
                    )}
                  >
                    {option.label}
                  </button>
                ))}
              </div>
            </motion.div>
          </div>

          <motion.div
            variants={gridVariants}
            initial="hidden"
            animate="show"
            className="mb-4 grid grid-cols-1 gap-4 sm:grid-cols-2 md:mb-6 md:grid-cols-3 md:gap-6"
            style={
              reduce ? undefined : { willChange: "transform, opacity", transform: "translateZ(0)" }
            }
          >
            <CardShell tone="success" onClick={() => setDetail("attendance")}>
              <div className="flex items-center gap-4">
                <AnimatedRing value={attendance?.percent ?? 0} size={ringSize} tone="success" />
                <div className="flex min-w-0 flex-1 flex-col gap-1">
                  <p className="text-[0.65rem] font-semibold uppercase tracking-wider text-[color:color-mix(in_srgb,var(--secondary-text)_55%,transparent)]">
                    {t("activity:sections.attendance.title")}
                  </p>
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-[clamp(1.75rem,2vw,2.25rem)] font-black tracking-tighter tabular-nums lining-nums text-[color:var(--page-text)]">
                      {attendancePctAnimated}%
                    </span>
                    <TrendChip value={attendance?.trend} />
                  </div>
                  <ProgressBar
                    value={progressAttendance}
                    className="h-2 rounded-full"
                    barClassName="bg-[#10b981] dark:bg-[#34d399] rounded-full transition-[width] duration-600"
                  />
                  <p className="truncate text-sm text-[color:color-mix(in_srgb,var(--secondary-text)_65%,transparent)]">
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
                <p className="text-[0.65rem] font-semibold uppercase tracking-wider text-[color:color-mix(in_srgb,var(--secondary-text)_55%,transparent)]">
                  {t("activity:sections.grades.title")}
                </p>
                <div className="flex items-center gap-2">
                  <span className="text-[clamp(1.75rem,2vw,2.25rem)] font-black tracking-tighter tabular-nums lining-nums text-[color:var(--page-text)]">
                    {grades?.scale === "gpa"
                      ? `GPA ${gradesAnimated}`
                      : grades?.scale === "100"
                        ? `${gradesAnimated}/100`
                        : `${gradesAnimated}/5`}
                  </span>
                  <TrendChip value={grades?.trend} />
                </div>
                <p className="text-sm text-[color:color-mix(in_srgb,var(--secondary-text)_65%,transparent)]">
                  {t("activity:sections.grades.averageLabel")}
                </p>
              </div>
            </CardShell>

            <CardShell tone="warning" onClick={() => setDetail("participation")}>
              <div className="flex flex-col gap-1">
                <p className="text-[0.65rem] font-semibold uppercase tracking-wider text-[color:color-mix(in_srgb,var(--secondary-text)_55%,transparent)]">
                  {t("activity:sections.participation.title")}
                </p>
                <div className="flex items-center gap-2">
                  <span className="text-[clamp(1.75rem,2vw,2.25rem)] font-black tracking-tighter tabular-nums lining-nums text-[color:var(--page-text)]">
                    {t("activity:sections.participation.eventsCount", {
                      value: partEventsAnimated,
                      count: participation?.events ?? 0,
                    })}
                  </span>
                  <TrendChip value={participation?.trend} />
                </div>
                <p className="text-sm text-[color:color-mix(in_srgb,var(--secondary-text)_65%,transparent)]">
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

          <div className="my-4 border-t border-[color:color-mix(in_srgb,white_12%,var(--nav-link)_88%)] md:my-6 dark:border-[color:color-mix(in_srgb,white_8%,var(--nav-link)_92%)]" />

          <motion.div
            variants={gridVariants}
            initial="hidden"
            animate="show"
            className="grid grid-cols-1 gap-4 sm:grid-cols-2 md:grid-cols-3 md:gap-6"
          >
            <CardShell onClick={() => setDetail("attendance_recent")}>
              <div className="flex flex-col">
                <div className="mb-2 flex items-center gap-2">
                  <EventAvailableIcon className="text-base text-[color:var(--nav-link)]" />
                  <h3 className="font-black text-[color:var(--page-text)]">
                    {t("activity:sections.attendance.recent")}
                  </h3>
                </div>
                <div className="space-y-1">
                  <AnimatePresence initial={true}>
                    {(attendance?.recent ?? []).slice(0, 6).map((r, i) => {
                      const color =
                        r.status === "present"
                          ? "#10b981"
                          : r.status === "late"
                            ? "#f59e0b"
                            : "#ef4444"
                      const darkColor =
                        r.status === "present"
                          ? "#34d399"
                          : r.status === "late"
                            ? "#fbbf24"
                            : "#f87171"
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
                          initial="hidden"
                          animate="show"
                          exit={{ opacity: 0 }}
                          transition={{ delay: reduce ? 0 : i * 0.04 }}
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
                              <span className="font-bold text-[color:var(--page-text)]">
                                {r.course || attendanceLessonFallback}
                              </span>
                              <span className="text-sm text-[color:color-mix(in_srgb,var(--secondary-text)_55%,transparent)]">
                                {attendanceStatusLabel(r.status)}
                              </span>
                            </div>
                          </div>
                          <p className="ml-4 text-xs text-[color:color-mix(in_srgb,var(--secondary-text)_55%,transparent)]">
                            {formatDate(r.date)}
                          </p>
                        </motion.div>
                      )
                    })}
                  </AnimatePresence>
                  {!loading && (!attendance?.recent || attendance.recent.length === 0) && (
                    <p className="px-1 py-1 text-sm text-[color:color-mix(in_srgb,var(--secondary-text)_55%,transparent)]">
                      {noDataText}
                    </p>
                  )}
                </div>
              </div>
            </CardShell>

            <CardShell onClick={() => setDetail("grades_recent")}>
              <div className="flex flex-col">
                <div className="mb-2 flex items-center gap-2">
                  <SchoolIcon className="text-base text-[color:var(--nav-link)]" />
                  <h3 className="font-black text-[color:var(--page-text)]">
                    {t("activity:sections.grades.recent")}
                  </h3>
                </div>
                <div className="space-y-1">
                  <AnimatePresence initial={true}>
                    {(grades?.recent ?? []).slice(0, 6).map((r, i) => {
                      const gradeRecord = r as Partial<{ id?: number | string }>
                      const itemKey = pickKeyCandidate(gradeRecord.id) ?? gradeItemKey(r, i)
                      return (
                        <motion.div
                          key={itemKey}
                          variants={listItemVariants}
                          initial="hidden"
                          animate="show"
                          exit={{ opacity: 0 }}
                          transition={{ delay: reduce ? 0 : i * 0.04 }}
                          className="py-1"
                          style={
                            reduce
                              ? undefined
                              : { willChange: "transform, opacity", transform: "translateZ(0)" }
                          }
                        >
                          <div className="flex items-center gap-2">
                            <div className="h-2 w-2 rounded-full bg-[#3b82f6]/90 shadow-[0_0_0_3px_#3b82f618] dark:bg-[#60a5fa]/90 dark:shadow-[0_0_0_3px_#60a5fa18]" />
                            <div className="flex min-w-0 flex-1 flex-wrap items-baseline gap-1.5">
                              <span className="font-bold text-[color:var(--page-text)]">
                                {r.course}
                              </span>
                              <span className="text-sm text-[color:color-mix(in_srgb,var(--secondary-text)_55%,transparent)]">
                                {r.score}
                                {r.max ? "/" + r.max : ""}
                              </span>
                            </div>
                          </div>
                          <p className="ml-4 text-xs text-[color:color-mix(in_srgb,var(--secondary-text)_55%,transparent)]">
                            {formatDate(r.date)}
                          </p>
                        </motion.div>
                      )
                    })}
                  </AnimatePresence>
                  {!loading && (!grades?.recent || grades.recent.length === 0) && (
                    <p className="px-1 py-1 text-sm text-[color:color-mix(in_srgb,var(--secondary-text)_55%,transparent)]">
                      {noDataText}
                    </p>
                  )}
                </div>
              </div>
            </CardShell>

            <CardShell onClick={() => setDetail("participation_recent")}>
              <div className="flex flex-col">
                <div className="mb-2 flex items-center gap-2">
                  <EmojiEventsIcon className="text-base text-[color:var(--nav-link)]" />
                  <h3 className="font-black text-[color:var(--page-text)]">
                    {t("activity:sections.participation.recent")}
                  </h3>
                </div>
                <div className="space-y-1">
                  <AnimatePresence initial={true}>
                    {(participation?.recent ?? []).slice(0, 6).map((r, i) => {
                      const participationRecord = r as Partial<{ id?: number | string }>
                      const itemKey =
                        pickKeyCandidate(participationRecord.id) ?? participationItemKey(r, i)
                      return (
                        <motion.div
                          key={itemKey}
                          variants={listItemVariants}
                          initial="hidden"
                          animate="show"
                          exit={{ opacity: 0 }}
                          transition={{ delay: reduce ? 0 : i * 0.04 }}
                          className="py-1"
                          style={
                            reduce
                              ? undefined
                              : { willChange: "transform, opacity", transform: "translateZ(0)" }
                          }
                        >
                          <div className="flex items-center gap-2">
                            <div className="h-2 w-2 rounded-full bg-[#f59e0b]/90 shadow-[0_0_0_3px_#f59e0b18] dark:bg-[#fbbf24]/90 dark:shadow-[0_0_0_3px_#fbbf2418]" />
                            <div className="flex min-w-0 flex-1 flex-wrap items-baseline gap-1.5">
                              <span className="font-bold text-[color:var(--page-text)]">
                                {r.title}
                              </span>
                              <span className="text-sm text-[color:color-mix(in_srgb,var(--secondary-text)_55%,transparent)]">
                                {[formatDate(r.date), r.role].filter(Boolean).join(separator)}
                              </span>
                            </div>
                          </div>
                        </motion.div>
                      )
                    })}
                  </AnimatePresence>
                  {!loading && (!participation?.recent || participation.recent.length === 0) && (
                    <p className="px-1 py-1 text-sm text-[color:color-mix(in_srgb,var(--secondary-text)_55%,transparent)]">
                      {noDataText}
                    </p>
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
              <p className="text-base text-[color:var(--page-text)]">
                {t("activity:sections.attendance.dialogTotal", {
                  present: attendance?.present ?? 0,
                  total: attendance?.total ?? 0,
                  period: attendance?.periodLabel || labelByPeriod(period),
                })}
              </p>
              <ProgressBar
                value={Math.max(0, Math.min(100, attendance?.percent ?? 0))}
                className="h-2.5 rounded-lg"
                barClassName="bg-[#10b981] dark:bg-[#34d399] rounded-lg"
              />
              <div className="space-y-2">
                {(attendance?.recent ?? []).map((r, i) => (
                  <div key={attendanceItemKey(r, i)} className="space-y-0.5">
                    <p className="text-sm font-semibold text-[color:var(--page-text)]">
                      {`${r.course || attendanceLessonFallback} — ${attendanceStatusLabel(r.status)}`}
                    </p>
                    <p className="text-xs text-[color:color-mix(in_srgb,var(--secondary-text)_65%,transparent)]">
                      {formatDate(r.date)}
                    </p>
                  </div>
                ))}
              </div>
            </div>
          )}
          {detail === "grades" && (
            <div className="space-y-4">
              <p className="text-base font-semibold text-[color:var(--page-text)]">
                {grades?.scale === "gpa"
                  ? `GPA ${(grades?.average ?? 0).toFixed(2)}`
                  : grades?.scale === "100"
                    ? `${Math.round(grades?.average ?? 0)}/100`
                    : `${(grades?.average ?? 0).toFixed(1)}/5`}
              </p>
              <div className="space-y-2">
                {(grades?.recent ?? []).map((r, i) => (
                  <div key={gradeItemKey(r, i)} className="space-y-0.5">
                    <p className="text-sm font-semibold text-[color:var(--page-text)]">
                      {`${r.course} — ${r.score}${r.max ? "/" + r.max : ""}`}
                    </p>
                    <p className="text-xs text-[color:color-mix(in_srgb,var(--secondary-text)_65%,transparent)]">
                      {formatDate(r.date)}
                    </p>
                  </div>
                ))}
              </div>
            </div>
          )}
          {detail === "participation" && (
            <div className="space-y-4">
              <p className="text-base text-[color:var(--page-text)]">
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
                    <p className="text-sm font-semibold text-[color:var(--page-text)]">{r.title}</p>
                    <p className="text-xs text-[color:color-mix(in_srgb,var(--secondary-text)_65%,transparent)]">
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
                  <p className="text-sm font-semibold text-[color:var(--page-text)]">
                    {`${r.course || attendanceLessonFallback} — ${attendanceStatusLabel(r.status)}`}
                  </p>
                  <p className="text-xs text-[color:color-mix(in_srgb,var(--secondary-text)_65%,transparent)]">
                    {formatDate(r.date)}
                  </p>
                </div>
              ))}
            </div>
          )}
          {detail === "grades_recent" && (
            <div className="space-y-2">
              {(grades?.recent ?? []).map((r, i) => (
                <div key={gradeItemKey(r, i)} className="space-y-0.5">
                  <p className="text-sm font-semibold text-[color:var(--page-text)]">
                    {`${r.course} — ${r.score}${r.max ? "/" + r.max : ""}`}
                  </p>
                  <p className="text-xs text-[color:color-mix(in_srgb,var(--secondary-text)_65%,transparent)]">
                    {formatDate(r.date)}
                  </p>
                </div>
              ))}
            </div>
          )}
          {detail === "participation_recent" && (
            <div className="space-y-2">
              {(participation?.recent ?? []).map((r, i) => (
                <div key={participationItemKey(r, i)} className="space-y-0.5">
                  <p className="text-sm font-semibold text-[color:var(--page-text)]">{r.title}</p>
                  <p className="text-xs text-[color:color-mix(in_srgb,var(--secondary-text)_65%,transparent)]">
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
      </PageFadeIn>
    </Layout>
  )
}
