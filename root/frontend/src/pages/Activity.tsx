import Layout from "../components/Layout"
import PageFadeIn from "../components/PageFadeIn"
import axios from "../api/client"
import { useEffect, useState, useCallback, useMemo, useRef } from "react"
import {
  Box,
  Typography,
  Stack,
  Chip,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Button,
  List,
  ListItem,
  ListItemText,
  Card,
  CardContent,
  CardActionArea,
  LinearProgress,
  ToggleButton,
  ToggleButtonGroup,
  Divider,
  useMediaQuery,
} from "@mui/material"
import { alpha, useTheme } from "@mui/material/styles"
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
import { lightenColor } from "@/utils/color"

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

const MotionBox = motion(Box)
const MotionCard = motion(Card)
const MotionListItem = motion(ListItem)

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
  const theme = useTheme()
  const reduce = useReducedMotion()
  const color =
    tone === "success"
      ? theme.palette.success.main
      : tone === "info"
        ? theme.palette.info.main
        : theme.palette.warning.main
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
  return (
    <Box sx={{ position: "relative", width: size, height: size, flexShrink: 0 }}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} style={{ display: "block" }}>
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke={alpha(color, 0.15)}
          strokeWidth={stroke}
        />
        <motion.circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke={color}
          strokeWidth={stroke}
          strokeLinecap="round"
          strokeDasharray={c}
          style={{ strokeDashoffset: dash }}
        />
      </svg>
      <Box
        sx={{
          position: "absolute",
          inset: 0,
          display: "grid",
          placeItems: "center",
          fontWeight: 900,
          letterSpacing: "-.02em",
          fontVariantNumeric: "tabular-nums lining-nums",
        }}
      >
        {Math.round(value)}%
      </Box>
    </Box>
  )
}

export default function Activity() {
  const theme = useTheme()
  const { t } = useTranslation(["activity", "common"])
  const { language } = useLanguage()
  const locale = getLocaleForLanguage(language)
  const isDark = theme.palette.mode === "dark"
  const reduce = useReducedMotion()
  const isSm = useMediaQuery(theme.breakpoints.down("sm"))
  const isMd = useMediaQuery(theme.breakpoints.down("md"))
  const isXl = useMediaQuery(theme.breakpoints.up("xl"))
  const ringSize = isSm ? 68 : isMd ? 84 : isXl ? 104 : 96

  const darkToggleBase = alpha(theme.palette.common.white, 0.9)
  const darkToggleHover = alpha(theme.palette.common.white, 0.96)
  const darkToggleBorder = alpha(theme.palette.common.white, 0.24)
  const darkToggleSelected = lightenColor(theme.palette.primary.main, 0.6)

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

  const cardBorder = alpha(
    theme.palette.mode === "dark" ? theme.palette.common.white : theme.palette.common.black,
    0.08
  )
  const ringFocus = alpha(theme.palette.primary.main, 0.34)
  const hoverShadow =
    theme.palette.mode === "dark" ? "0 4px 24px rgba(0,0,0,.36)" : "0 10px 36px rgba(0,0,0,.12)"
  const muted = alpha(theme.palette.text.primary, 0.65)
  const subMuted = alpha(theme.palette.text.primary, 0.55)

  const glass = (tone: "neutral" | "success" | "info" | "warning" = "neutral") => {
    const base = theme.palette.background.default
    const tonal =
      tone === "success"
        ? alpha(theme.palette.success.main, theme.palette.mode === "dark" ? 0.12 : 0.1)
        : tone === "info"
          ? alpha(theme.palette.info.main, theme.palette.mode === "dark" ? 0.12 : 0.1)
          : tone === "warning"
            ? alpha(theme.palette.warning.main, theme.palette.mode === "dark" ? 0.12 : 0.1)
            : alpha(theme.palette.primary.main, 0)
    return {
      backgroundImage: `linear-gradient(180deg, ${alpha(
        base,
        theme.palette.mode === "dark" ? 0.2 : 0.5
      )} 0%, ${alpha(base, theme.palette.mode === "dark" ? 0.12 : 0.38)} 100%), linear-gradient(${tonal}, ${tonal})`,
      backdropFilter: "blur(12px)",
      WebkitBackdropFilter: "blur(12px)",
    }
  }

  const numberSx = {
    fontWeight: 900,
    letterSpacing: "-.02em",
    fontVariantNumeric: "tabular-nums lining-nums",
    fontSize: { xs: "1.75rem", md: "2rem", xl: "2.25rem" },
  } as const

  const TrendChip = ({ value }: { value?: number }) =>
    typeof value === "number" ? (
      <Chip
        size="small"
        icon={value >= 0 ? <TrendingUpIcon /> : <TrendingDownIcon />}
        label={`${value > 0 ? "+" : ""}${value.toFixed(1)}%`}
        color={value >= 0 ? "success" : "error"}
        variant="outlined"
        sx={{ fontWeight: 800, borderRadius: 2 }}
      />
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
  }) => (
    <MotionCard
      elevation={0}
      initial={{ y: reduce ? 0 : 14, opacity: reduce ? 1 : 0 }}
      animate={{ y: 0, opacity: 1 }}
      transition={{ type: "spring", stiffness: 260, damping: 32, mass: 1 }}
      sx={{
        position: "relative",
        display: "flex",
        flexDirection: "column",
        height: "100%",
        borderRadius: 4,
        border: `1px solid ${cardBorder}`,
        overflow: "hidden",
        ...glass(tone),
        willChange: reduce ? undefined : "transform, opacity",
        transform: "translateZ(0)",
        transition: theme.transitions.create(
          ["box-shadow", "transform", "background-color", "border-color"],
          { duration: 180 }
        ),
        "&:hover": reduce
          ? undefined
          : {
              boxShadow: hoverShadow,
              transform: "translateY(-2px) translateZ(0)",
              borderColor: cardBorder,
            },
        "&:active": { transform: "translateY(0) translateZ(0)" },
      }}
    >
      <CardActionArea
        onClick={onClick}
        sx={{
          borderRadius: 4,
          p: { xs: 2, md: 2.5, xl: 3 },
          display: "flex",
          flexDirection: "column",
          height: "100%",
          alignItems: "stretch",
          "&:focus-visible": { boxShadow: `0 0 0 3px ${ringFocus}` },
        }}
      >
        <CardContent sx={{ p: 0, display: "flex", flexDirection: "column", gap: 2, flex: 1 }}>
          {children}
        </CardContent>
      </CardActionArea>
    </MotionCard>
  )

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
        <MotionBox
          initial="hidden"
          animate="show"
          variants={headerVariants}
          sx={{
            width: "100%",
            minHeight: "100vh",
            px: { xs: 2, sm: 3, md: 4, xl: 6 },
            py: { xs: 2.5, md: 4 },
            pb: { xs: 9, md: 4 },
            boxSizing: "border-box",
            maxWidth: "100%",
            mx: "auto",
          }}
          style={
            reduce ? undefined : { willChange: "transform, opacity", transform: "translateZ(0)" }
          }
        >
          <Stack
            direction="row"
            alignItems="center"
            justifyContent="space-between"
            mb={{ xs: 2, md: 3 }}
            gap={2}
            flexWrap="wrap"
          >
            <Stack direction="row" alignItems="center" gap={1.25}>
              <Box
                sx={{
                  width: 34,
                  height: 34,
                  borderRadius: 3,
                  display: "grid",
                  placeItems: "center",
                  border: `1px solid ${cardBorder}`,
                  background: alpha(
                    theme.palette.primary.main,
                    theme.palette.mode === "dark" ? 0.1 : 0.06
                  ),
                }}
              >
                <TimelineIcon sx={{ fontSize: 20, color: theme.palette.primary.main }} />
              </Box>
              <Typography
                sx={{
                  fontWeight: 900,
                  fontSize: "clamp(1.5rem, 2.6vw, 2.4rem)",
                  letterSpacing: "-.01em",
                }}
              >
                {t("activity:title")}
              </Typography>
            </Stack>
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
              <ToggleButtonGroup
                size="small"
                color="primary"
                value={period}
                exclusive
                onChange={(_, v: PeriodKey | null) => v && setPeriod(v)}
                sx={{
                  borderRadius: 999,
                  p: 0.5,
                  gap: 0.5,
                  background: isDark
                    ? alpha(theme.palette.common.white, 0.08)
                    : alpha(theme.palette.primary.main, 0.1),
                  border: isDark
                    ? `1px solid ${darkToggleBorder}`
                    : `1px solid ${alpha(theme.palette.primary.main, 0.25)}`,
                  boxShadow: isDark
                    ? `0 12px 34px ${alpha(theme.palette.common.black, 0.46)}`
                    : undefined,
                  "& .MuiToggleButton-root": {
                    textTransform: "none",
                    px: 1.6,
                    py: 0.5,
                    borderRadius: 999,
                    border: 0,
                    fontWeight: 700,
                    color: theme.palette.common.white,
                    backgroundColor: isDark ? darkToggleBase : "transparent",
                    transition: theme.transitions.create(
                      ["background-color", "color", "box-shadow"],
                      {
                        duration: theme.transitions.duration.shortest,
                      }
                    ),
                    boxShadow: isDark
                      ? `0 2px 10px ${alpha(theme.palette.common.black, 0.32)}`
                      : undefined,
                    "&:hover": {
                      background: isDark
                        ? darkToggleHover
                        : alpha(theme.palette.primary.main, 0.12),
                    },
                    "&:not(.Mui-selected)": {
                      boxShadow: isDark
                        ? `0 1px 5px ${alpha(theme.palette.common.black, 0.25)}`
                        : undefined,
                    },
                  },
                  "& .Mui-selected": {
                    background: isDark
                      ? darkToggleSelected
                      : lightenColor(theme.palette.primary.main, 0.35),
                    color: theme.palette.common.white,
                    boxShadow: isDark
                      ? `0 8px 24px ${alpha(theme.palette.primary.main, 0.45)}`
                      : `0 2px 8px ${alpha(theme.palette.primary.main, 0.2)}`,
                  },
                  "& .Mui-selected:hover": {
                    background: isDark
                      ? lightenColor(darkToggleSelected, 0.12)
                      : lightenColor(theme.palette.primary.main, 0.3),
                  },
                }}
              >
                {periodOptions.map((option) => (
                  <ToggleButton key={option.value} value={option.value}>
                    {option.label}
                  </ToggleButton>
                ))}
              </ToggleButtonGroup>
            </motion.div>
          </Stack>

          <MotionBox
            variants={gridVariants}
            initial="hidden"
            animate="show"
            sx={{
              display: "grid",
              gridAutoFlow: "row dense",
              alignItems: "stretch",
              gridTemplateColumns: {
                xs: "1fr",
                sm: "repeat(2, minmax(0,1fr))",
                md: "repeat(3, minmax(0,1fr))",
              },
              rowGap: { xs: 2.5, sm: 3, md: 3 },
              columnGap: { xs: 2.5, sm: 3, md: 3 },
              mb: { xs: 2, md: 3 },
            }}
            style={
              reduce ? undefined : { willChange: "transform, opacity", transform: "translateZ(0)" }
            }
          >
            <CardShell tone="success" onClick={() => setDetail("attendance")}>
              <Stack direction="row" alignItems="center" spacing={2}>
                <AnimatedRing value={attendance?.percent ?? 0} size={ringSize} tone="success" />
                <Stack spacing={1} sx={{ flex: 1, minWidth: 0 }}>
                  <Typography variant="overline" sx={{ letterSpacing: ".06em", color: subMuted }}>
                    {t("activity:sections.attendance.title")}
                  </Typography>
                  <Stack direction="row" alignItems="center" spacing={1.2} flexWrap="wrap">
                    <Typography sx={numberSx}>{attendancePctAnimated}%</Typography>
                    <TrendChip value={attendance?.trend} />
                  </Stack>
                  <LinearProgress
                    variant="determinate"
                    value={progressAttendance}
                    sx={{
                      height: 8,
                      borderRadius: 999,
                      transition: "transform .6s ease",
                      bgcolor: alpha(theme.palette.success.main, 0.18),
                      "& .MuiLinearProgress-bar": {
                        borderRadius: 999,
                        backgroundColor: theme.palette.success.main,
                      },
                    }}
                  />
                  <Typography
                    variant="body2"
                    sx={{
                      color: muted,
                      whiteSpace: "nowrap",
                      overflow: "hidden",
                      textOverflow: "ellipsis",
                    }}
                  >
                    {t("activity:sections.attendance.summary", {
                      present: attendance?.present ?? 0,
                      total: attendance?.total ?? 0,
                      period: attendance?.periodLabel || labelByPeriod(period),
                    })}
                  </Typography>
                </Stack>
              </Stack>
            </CardShell>

            <CardShell tone="info" onClick={() => setDetail("grades")}>
              <Stack spacing={1}>
                <Typography variant="overline" sx={{ letterSpacing: ".06em", color: subMuted }}>
                  {t("activity:sections.grades.title")}
                </Typography>
                <Stack direction="row" alignItems="center" spacing={1.2}>
                  <Typography sx={numberSx}>
                    {grades?.scale === "gpa"
                      ? `GPA ${gradesAnimated}`
                      : grades?.scale === "100"
                        ? `${gradesAnimated}/100`
                        : `${gradesAnimated}/5`}
                  </Typography>
                  <TrendChip value={grades?.trend} />
                </Stack>
                <Typography variant="body2" sx={{ color: muted }}>
                  {t("activity:sections.grades.averageLabel")}
                </Typography>
              </Stack>
            </CardShell>

            <CardShell tone="warning" onClick={() => setDetail("participation")}>
              <Stack spacing={1}>
                <Typography variant="overline" sx={{ letterSpacing: ".06em", color: subMuted }}>
                  {t("activity:sections.participation.title")}
                </Typography>
                <Stack direction="row" alignItems="center" spacing={1.2}>
                  <Typography sx={numberSx}>
                    {t("activity:sections.participation.eventsCount", {
                      value: partEventsAnimated,
                      count: participation?.events ?? 0,
                    })}
                  </Typography>
                  <TrendChip value={participation?.trend} />
                </Stack>
                <Typography variant="body2" sx={{ color: muted }}>
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
                </Typography>
              </Stack>
            </CardShell>
          </MotionBox>

          <Divider sx={{ my: { xs: 2, md: 3 }, borderColor: cardBorder }} />

          <MotionBox
            variants={gridVariants}
            initial="hidden"
            animate="show"
            sx={{
              display: "grid",
              gridAutoFlow: "row dense",
              alignItems: "stretch",
              gridTemplateColumns: {
                xs: "1fr",
                sm: "repeat(2, minmax(0,1fr))",
                md: "repeat(3, minmax(0,1fr))",
              },
              rowGap: { xs: 2.5, sm: 3, md: 3 },
              columnGap: { xs: 2.5, sm: 3, md: 3 },
            }}
          >
            <CardShell onClick={() => setDetail("attendance_recent")}>
              <Stack>
                <Stack direction="row" spacing={1} alignItems="center" mb={1}>
                  <EventAvailableIcon fontSize="small" />
                  <Typography fontWeight={900}>
                    {t("activity:sections.attendance.recent")}
                  </Typography>
                </Stack>
                <List dense disablePadding>
                  <AnimatePresence initial={true}>
                    {(attendance?.recent ?? []).slice(0, 6).map((r, i) => {
                      const color =
                        r.status === "present"
                          ? theme.palette.success.main
                          : r.status === "late"
                            ? theme.palette.warning.main
                            : theme.palette.error.main
                      const attendanceRecord = r as Partial<{
                        id?: number | string
                        lesson_id?: number | string
                      }>
                      const itemKey =
                        pickKeyCandidate(attendanceRecord.id) ??
                        pickKeyCandidate(attendanceRecord.lesson_id) ??
                        attendanceItemKey(r, i)
                      return (
                        <MotionListItem
                          key={itemKey}
                          variants={listItemVariants}
                          initial="hidden"
                          animate="show"
                          exit={{ opacity: 0 }}
                          transition={{ delay: reduce ? 0 : i * 0.04 }}
                          sx={{
                            px: 0,
                            py: 0.25,
                            willChange: reduce ? undefined : "transform, opacity",
                            transform: "translateZ(0)",
                          }}
                        >
                          <ListItemText
                            primaryTypographyProps={{
                              sx: { display: "flex", alignItems: "center", gap: 1 },
                            }}
                            primary={
                              <Box sx={{ display: "flex", alignItems: "center", gap: 1.2 }}>
                                <Box
                                  sx={{
                                    width: 8,
                                    height: 8,
                                    borderRadius: 999,
                                    background: color,
                                    boxShadow: `0 0 0 3px ${alpha(color, 0.18)}`,
                                  }}
                                />
                                <Box
                                  sx={{
                                    display: "inline-flex",
                                    gap: 0.75,
                                    alignItems: "baseline",
                                    flexWrap: "wrap",
                                  }}
                                >
                                  <Typography component="span" sx={{ fontWeight: 700 }}>
                                    {r.course || attendanceLessonFallback}
                                  </Typography>
                                  <Typography component="span" sx={{ color: subMuted }}>
                                    {attendanceStatusLabel(r.status)}
                                  </Typography>
                                </Box>
                              </Box>
                            }
                            secondary={formatDate(r.date)}
                            secondaryTypographyProps={{ sx: { color: subMuted } }}
                          />
                        </MotionListItem>
                      )
                    })}
                  </AnimatePresence>
                  {!loading && (!attendance?.recent || attendance.recent.length === 0) && (
                    <Typography variant="body2" sx={{ color: subMuted, px: 0.5, py: 0.5 }}>
                      {noDataText}
                    </Typography>
                  )}
                </List>
              </Stack>
            </CardShell>

            <CardShell onClick={() => setDetail("grades_recent")}>
              <Stack>
                <Stack direction="row" spacing={1} alignItems="center" mb={1}>
                  <SchoolIcon fontSize="small" />
                  <Typography fontWeight={900}>{t("activity:sections.grades.recent")}</Typography>
                </Stack>
                <List dense disablePadding>
                  <AnimatePresence initial={true}>
                    {(grades?.recent ?? []).slice(0, 6).map((r, i) => {
                      const gradeRecord = r as Partial<{ id?: number | string }>
                      const itemKey = pickKeyCandidate(gradeRecord.id) ?? gradeItemKey(r, i)
                      return (
                        <MotionListItem
                          key={itemKey}
                          variants={listItemVariants}
                          initial="hidden"
                          animate="show"
                          exit={{ opacity: 0 }}
                          transition={{ delay: reduce ? 0 : i * 0.04 }}
                          sx={{
                            px: 0,
                            py: 0.25,
                            willChange: reduce ? undefined : "transform, opacity",
                            transform: "translateZ(0)",
                          }}
                        >
                          <ListItemText
                            primaryTypographyProps={{
                              sx: { display: "flex", alignItems: "center", gap: 1 },
                            }}
                            primary={
                              <Box sx={{ display: "flex", alignItems: "center", gap: 1.2 }}>
                                <Box
                                  sx={{
                                    width: 8,
                                    height: 8,
                                    borderRadius: 999,
                                    background: alpha(theme.palette.info.main, 0.9),
                                    boxShadow: `0 0 0 3px ${alpha(theme.palette.info.main, 0.18)}`,
                                  }}
                                />
                                <Box
                                  sx={{
                                    display: "inline-flex",
                                    gap: 0.75,
                                    alignItems: "baseline",
                                    flexWrap: "wrap",
                                  }}
                                >
                                  <Typography component="span" sx={{ fontWeight: 700 }}>
                                    {r.course}
                                  </Typography>
                                  <Typography component="span" sx={{ color: subMuted }}>
                                    {r.score}
                                    {r.max ? "/" + r.max : ""}
                                  </Typography>
                                </Box>
                              </Box>
                            }
                            secondary={formatDate(r.date)}
                            secondaryTypographyProps={{ sx: { color: subMuted } }}
                          />
                        </MotionListItem>
                      )
                    })}
                  </AnimatePresence>
                  {!loading && (!grades?.recent || grades.recent.length === 0) && (
                    <Typography variant="body2" sx={{ color: subMuted, px: 0.5, py: 0.5 }}>
                      {noDataText}
                    </Typography>
                  )}
                </List>
              </Stack>
            </CardShell>

            <CardShell onClick={() => setDetail("participation_recent")}>
              <Stack>
                <Stack direction="row" spacing={1} alignItems="center" mb={1}>
                  <EmojiEventsIcon fontSize="small" />
                  <Typography fontWeight={900}>
                    {t("activity:sections.participation.recent")}
                  </Typography>
                </Stack>
                <List dense disablePadding>
                  <AnimatePresence initial={true}>
                    {(participation?.recent ?? []).slice(0, 6).map((r, i) => {
                      const participationRecord = r as Partial<{ id?: number | string }>
                      const itemKey =
                        pickKeyCandidate(participationRecord.id) ?? participationItemKey(r, i)
                      return (
                        <MotionListItem
                          key={itemKey}
                          variants={listItemVariants}
                          initial="hidden"
                          animate="show"
                          exit={{ opacity: 0 }}
                          transition={{ delay: reduce ? 0 : i * 0.04 }}
                          sx={{
                            px: 0,
                            py: 0.25,
                            willChange: reduce ? undefined : "transform, opacity",
                            transform: "translateZ(0)",
                          }}
                        >
                          <ListItemText
                            primaryTypographyProps={{
                              sx: { display: "flex", alignItems: "center", gap: 1 },
                            }}
                            primary={
                              <Box sx={{ display: "flex", alignItems: "center", gap: 1.2 }}>
                                <Box
                                  sx={{
                                    width: 8,
                                    height: 8,
                                    borderRadius: 999,
                                    background: alpha(theme.palette.warning.main, 0.9),
                                    boxShadow: `0 0 0 3px ${alpha(theme.palette.warning.main, 0.18)}`,
                                  }}
                                />
                                <Box
                                  sx={{
                                    display: "inline-flex",
                                    gap: 0.75,
                                    alignItems: "baseline",
                                    flexWrap: "wrap",
                                  }}
                                >
                                  <Typography component="span" sx={{ fontWeight: 700 }}>
                                    {r.title}
                                  </Typography>
                                  <Typography component="span" sx={{ color: subMuted }}>
                                    {[formatDate(r.date), r.role].filter(Boolean).join(separator)}
                                  </Typography>
                                </Box>
                              </Box>
                            }
                          />
                        </MotionListItem>
                      )
                    })}
                  </AnimatePresence>
                  {!loading && (!participation?.recent || participation.recent.length === 0) && (
                    <Typography variant="body2" sx={{ color: subMuted, px: 0.5, py: 0.5 }}>
                      {noDataText}
                    </Typography>
                  )}
                </List>
              </Stack>
            </CardShell>
          </MotionBox>
        </MotionBox>

        <Dialog open={detail !== ""} onClose={() => setDetail("")} maxWidth="sm" fullWidth>
          <DialogTitle>
            {detailSection ? t(`activity:sections.${detailSection}.dialogTitle`) : ""}
          </DialogTitle>
          <DialogContent dividers>
            {detail === "attendance" && (
              <Stack spacing={2}>
                <Typography>
                  {t("activity:sections.attendance.dialogTotal", {
                    present: attendance?.present ?? 0,
                    total: attendance?.total ?? 0,
                    period: attendance?.periodLabel || labelByPeriod(period),
                  })}
                </Typography>
                <LinearProgress
                  variant="determinate"
                  value={Math.max(0, Math.min(100, attendance?.percent ?? 0))}
                  sx={{ height: 10, borderRadius: 8 }}
                />
                <List dense>
                  {(attendance?.recent ?? []).map((r, i) => (
                    <ListItem key={attendanceItemKey(r, i)} sx={{ px: 0 }}>
                      <ListItemText
                        primary={`${r.course || attendanceLessonFallback} — ${attendanceStatusLabel(r.status)}`}
                        secondary={formatDate(r.date)}
                      />
                    </ListItem>
                  ))}
                </List>
              </Stack>
            )}
            {detail === "grades" && (
              <Stack spacing={2}>
                <Typography>
                  {grades?.scale === "gpa"
                    ? `GPA ${(grades?.average ?? 0).toFixed(2)}`
                    : grades?.scale === "100"
                      ? `${Math.round(grades?.average ?? 0)}/100`
                      : `${(grades?.average ?? 0).toFixed(1)}/5`}
                </Typography>
                <List dense>
                  {(grades?.recent ?? []).map((r, i) => (
                    <ListItem key={gradeItemKey(r, i)} sx={{ px: 0 }}>
                      <ListItemText
                        primary={`${r.course} — ${r.score}${r.max ? "/" + r.max : ""}`}
                        secondary={formatDate(r.date)}
                      />
                    </ListItem>
                  ))}
                </List>
              </Stack>
            )}
            {detail === "participation" && (
              <Stack spacing={2}>
                <Typography>
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
                </Typography>
                <List dense>
                  {(participation?.recent ?? []).map((r, i) => (
                    <ListItem key={participationItemKey(r, i)} sx={{ px: 0 }}>
                      <ListItemText
                        primary={r.title}
                        secondary={[formatDate(r.date), r.role].filter(Boolean).join(separator)}
                      />
                    </ListItem>
                  ))}
                </List>
              </Stack>
            )}
            {detail === "attendance_recent" && (
              <List dense>
                {(attendance?.recent ?? []).map((r, i) => (
                  <ListItem key={attendanceItemKey(r, i)} sx={{ px: 0 }}>
                    <ListItemText
                      primary={`${r.course || attendanceLessonFallback} — ${attendanceStatusLabel(r.status)}`}
                      secondary={formatDate(r.date)}
                    />
                  </ListItem>
                ))}
              </List>
            )}
            {detail === "grades_recent" && (
              <List dense>
                {(grades?.recent ?? []).map((r, i) => (
                  <ListItem key={gradeItemKey(r, i)} sx={{ px: 0 }}>
                    <ListItemText
                      primary={`${r.course} — ${r.score}${r.max ? "/" + r.max : ""}`}
                      secondary={formatDate(r.date)}
                    />
                  </ListItem>
                ))}
              </List>
            )}
            {detail === "participation_recent" && (
              <List dense>
                {(participation?.recent ?? []).map((r, i) => (
                  <ListItem key={participationItemKey(r, i)} sx={{ px: 0 }}>
                    <ListItemText
                      primary={r.title}
                      secondary={[formatDate(r.date), r.role].filter(Boolean).join(separator)}
                    />
                  </ListItem>
                ))}
              </List>
            )}
          </DialogContent>
          <DialogActions>
            <Button onClick={() => setDetail("")}>{t("activity:dialog.close")}</Button>
          </DialogActions>
        </Dialog>
      </PageFadeIn>
    </Layout>
  )
}
