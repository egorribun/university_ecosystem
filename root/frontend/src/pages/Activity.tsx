import Layout from "../components/Layout"
import axios from "../api/axios"
import { useEffect, useState, useCallback, useMemo } from "react"
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
import { alpha, useTheme, darken, lighten } from "@mui/material/styles"
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

const toNumber = (value: unknown, fallback = 0) => {
  const num = Number(value)
  return Number.isFinite(num) ? num : fallback
}

const easeOutExpo = [0.22, 1, 0.36, 1] as const

type AttendanceStats = {
  percent: number
  present: number
  total: number
  trend: number
  windowLabel: string
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
  const reduce = useReducedMotion()
  const isSm = useMediaQuery(theme.breakpoints.down("sm"))
  const isMd = useMediaQuery(theme.breakpoints.down("md"))
  const isXl = useMediaQuery(theme.breakpoints.up("xl"))
  const ringSize = isSm ? 68 : isMd ? 84 : isXl ? 104 : 96

  const [period, setPeriod] = useState<"30d" | "90d" | "180d">("90d")
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

  const labelByPeriod = (p: "30d" | "90d" | "180d") =>
    p === "30d" ? "за 30 дней" : p === "180d" ? "за 180 дней" : "за 90 дней"

  const fetchSummary = useCallback(async () => {
    setLoading(true)
    try {
      const [a, g, p] = await Promise.allSettled([
        axios.get("/stats/attendance", { params: { period } }),
        axios.get("/stats/grades", { params: { period } }),
        axios.get("/stats/participation", { params: { period } }),
      ])
      if (a.status === "fulfilled" && a.value?.data) {
        const d = a.value.data
        setAttendance({
          percent: toNumber(d.percent),
          present: toNumber(d.present),
          total: toNumber(d.total),
          trend: toNumber(d.trend),
          windowLabel: d.window_label || labelByPeriod(period),
          recent: Array.isArray(d.recent) ? d.recent : [],
        })
      } else {
        setAttendance({
          percent: 92,
          present: 83,
          total: 90,
          trend: 1.4,
          windowLabel: labelByPeriod(period),
          recent: [
            { date: "2025-09-19", status: "present", course: "Алгебра" },
            { date: "2025-09-18", status: "late", course: "История" },
            { date: "2025-09-17", status: "present", course: "Физика" },
          ],
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
        setGrades({
          average: 4.4,
          scale: "5",
          trend: 0.3,
          recent: [
            { course: "Алгебра", score: 5, date: "2025-09-18" },
            { course: "Физика", score: 4, date: "2025-09-16" },
            { course: "Литература", score: 5, date: "2025-09-13" },
          ],
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
        setParticipation({
          events: 6,
          hours: 12,
          groups: 2,
          trend: 2.0,
          recent: [
            { title: "Хакатон кафедры", date: "2025-09-14", role: "участник" },
            { title: "Турнир по баскетболу", date: "2025-09-07", role: "команда" },
          ],
        })
      }
    } finally {
      setLoading(false)
    }
  }, [period])

  useEffect(() => {
    fetchSummary()
  }, [fetchSummary])

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
      backgroundImage: `linear-gradient(180deg, ${alpha(base, theme.palette.mode === "dark" ? 0.2 : 0.5)} 0%, ${alpha(base, theme.palette.mode === "dark" ? 0.12 : 0.38)} 100%), linear-gradient(${tonal} , ${tonal})`,
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
      initial={{ y: reduce ? 0 : 16, opacity: reduce ? 1 : 0, scale: reduce ? 1 : 0.98 }}
      animate={{ y: 0, opacity: 1, scale: 1 }}
      transition={{ type: "spring", stiffness: 160, damping: 22, mass: 0.9 }}
      sx={{
        position: "relative",
        display: "flex",
        flexDirection: "column",
        height: "100%",
        borderRadius: 4,
        border: `1px solid ${cardBorder}`,
        overflow: "hidden",
        ...glass(tone),
        transition: theme.transitions.create(
          ["box-shadow", "transform", "background-color", "border-color"],
          { duration: 180 }
        ),
        "&:hover": {
          boxShadow: hoverShadow,
          transform: "translateY(-2px)",
          borderColor: cardBorder,
        },
        "&:active": { transform: "translateY(0)" },
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
              Активность
            </Typography>
          </Stack>
          <motion.div
            initial={{ opacity: 0, y: reduce ? 0 : 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.35 }}
          >
            <ToggleButtonGroup
              size="small"
              color="primary"
              value={period}
              exclusive
              onChange={(_, v) => v && setPeriod(v)}
              sx={{
                borderRadius: 999,
                p: 0.5,
                gap: 0.5,
                background: alpha(
                  theme.palette.primary.main,
                  theme.palette.mode === "dark" ? 0.12 : 0.1
                ),
                "& .MuiToggleButton-root": {
                  textTransform: "none",
                  px: 1.6,
                  py: 0.5,
                  borderRadius: 999,
                  border: 0,
                  fontWeight: 700,
                  color: theme.palette.text.primary,
                },
                "& .Mui-selected": {
                  background:
                    theme.palette.mode === "dark"
                      ? darken(theme.palette.background.paper, 0.4)
                      : lighten(theme.palette.background.paper, 0.4),
                  color: theme.palette.text.primary,
                },
              }}
            >
              <ToggleButton value="30d">30 дней</ToggleButton>
              <ToggleButton value="90d">90 дней</ToggleButton>
              <ToggleButton value="180d">180 дней</ToggleButton>
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
        >
          <CardShell tone="success" onClick={() => setDetail("attendance")}>
            <Stack direction="row" alignItems="center" spacing={2}>
              <AnimatedRing value={attendance?.percent ?? 0} size={ringSize} tone="success" />
              <Stack spacing={1} sx={{ flex: 1, minWidth: 0 }}>
                <Typography variant="overline" sx={{ letterSpacing: ".06em", color: subMuted }}>
                  Посещаемость
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
                >{`${attendance?.present ?? 0}/${attendance?.total ?? 0} ${attendance?.windowLabel || ""}`}</Typography>
              </Stack>
            </Stack>
          </CardShell>

          <CardShell tone="info" onClick={() => setDetail("grades")}>
            <Stack spacing={1}>
              <Typography variant="overline" sx={{ letterSpacing: ".06em", color: subMuted }}>
                Успеваемость
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
                Средний балл за период
              </Typography>
            </Stack>
          </CardShell>

          <CardShell tone="warning" onClick={() => setDetail("participation")}>
            <Stack spacing={1}>
              <Typography variant="overline" sx={{ letterSpacing: ".06ем", color: subMuted }}>
                Участие
              </Typography>
              <Stack direction="row" alignItems="center" spacing={1.2}>
                <Typography sx={numberSx}>{`${partEventsAnimated} событий`}</Typography>
                <TrendChip value={participation?.trend} />
              </Stack>
              <Typography variant="body2" sx={{ color: muted }}>
                {[
                  participation?.hours ? `${participation.hours} ч.` : null,
                  participation?.groups ? `${participation.groups} круж.` : null,
                ]
                  .filter(Boolean)
                  .join(" • ")}
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
                <Typography fontWeight={900}>Недавние посещения</Typography>
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
                    return (
                      <MotionListItem
                        key={i}
                        variants={listItemVariants}
                        initial="hidden"
                        animate="show"
                        exit={{ opacity: 0 }}
                        transition={{ delay: reduce ? 0 : i * 0.04 }}
                        sx={{ px: 0, py: 0.25 }}
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
                                  {r.course || "Занятие"}
                                </Typography>
                                <Typography component="span" sx={{ color: subMuted }}>
                                  {r.status === "present"
                                    ? "присутствовал"
                                    : r.status === "late"
                                      ? "опоздание"
                                      : "отсутствовал"}
                                </Typography>
                              </Box>
                            </Box>
                          }
                          secondary={new Date(r.date).toLocaleDateString()}
                          secondaryTypographyProps={{ sx: { color: subMuted } }}
                        />
                      </MotionListItem>
                    )
                  })}
                </AnimatePresence>
                {!loading && (!attendance?.recent || attendance.recent.length === 0) && (
                  <Typography variant="body2" sx={{ color: subMuted, px: 0.5, py: 0.5 }}>
                    Нет данных
                  </Typography>
                )}
              </List>
            </Stack>
          </CardShell>

          <CardShell onClick={() => setDetail("grades_recent")}>
            <Stack>
              <Stack direction="row" spacing={1} alignItems="center" mb={1}>
                <SchoolIcon fontSize="small" />
                <Typography fontWeight={900}>Недавние оценки</Typography>
              </Stack>
              <List dense disablePadding>
                <AnimatePresence initial={true}>
                  {(grades?.recent ?? []).slice(0, 6).map((r, i) => (
                    <MotionListItem
                      key={i}
                      variants={listItemVariants}
                      initial="hidden"
                      animate="show"
                      exit={{ opacity: 0 }}
                      transition={{ delay: reduce ? 0 : i * 0.04 }}
                      sx={{ px: 0, py: 0.25 }}
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
                        secondary={new Date(r.date).toLocaleDateString()}
                        secondaryTypographyProps={{ sx: { color: subMuted } }}
                      />
                    </MotionListItem>
                  ))}
                </AnimatePresence>
                {!loading && (!grades?.recent || grades.recent.length === 0) && (
                  <Typography variant="body2" sx={{ color: subMuted, px: 0.5, py: 0.5 }}>
                    Нет данных
                  </Typography>
                )}
              </List>
            </Stack>
          </CardShell>

          <CardShell onClick={() => setDetail("participation_recent")}>
            <Stack>
              <Stack direction="row" spacing={1} alignItems="center" mb={1}>
                <EmojiEventsIcon fontSize="small" />
                <Typography fontWeight={900}>Недавнее участие</Typography>
              </Stack>
              <List dense disablePadding>
                <AnimatePresence initial={true}>
                  {(participation?.recent ?? []).slice(0, 6).map((r, i) => (
                    <MotionListItem
                      key={i}
                      variants={listItemVariants}
                      initial="hidden"
                      animate="show"
                      exit={{ opacity: 0 }}
                      transition={{ delay: reduce ? 0 : i * 0.04 }}
                      sx={{ px: 0, py: 0.25 }}
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
                                {[new Date(r.date).toLocaleDateString(), r.role]
                                  .filter(Boolean)
                                  .join(" • ")}
                              </Typography>
                            </Box>
                          </Box>
                        }
                        secondary=""
                      />
                    </MotionListItem>
                  ))}
                </AnimatePresence>
                {!loading && (!participation?.recent || participation.recent.length === 0) && (
                  <Typography variant="body2" sx={{ color: subMuted, px: 0.5, py: 0.5 }}>
                    Нет данных
                  </Typography>
                )}
              </List>
            </Stack>
          </CardShell>
        </MotionBox>
      </MotionBox>

      <Dialog open={detail !== ""} onClose={() => setDetail("")} maxWidth="sm" fullWidth>
        <DialogTitle>
          {detail === "attendance" || detail === "attendance_recent"
            ? "Посещаемость"
            : detail === "grades" || detail === "grades_recent"
              ? "Успеваемость"
              : "Участие"}
        </DialogTitle>
        <DialogContent dividers>
          {detail === "attendance" && (
            <Stack spacing={2}>
              <Typography>
                Всего: {attendance?.present ?? 0}/{attendance?.total ?? 0}{" "}
                {attendance?.windowLabel || ""}
              </Typography>
              <LinearProgress
                variant="determinate"
                value={Math.max(0, Math.min(100, attendance?.percent ?? 0))}
                sx={{ height: 10, borderRadius: 8 }}
              />
              <List dense>
                {(attendance?.recent ?? []).map((r, i) => (
                  <ListItem key={i} sx={{ px: 0 }}>
                    <ListItemText
                      primary={`${r.course || "Занятие"} — ${r.status === "present" ? "присутствовал" : r.status === "late" ? "опоздание" : "отсутствовал"}`}
                      secondary={new Date(r.date).toLocaleDateString()}
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
                  <ListItem key={i} sx={{ px: 0 }}>
                    <ListItemText
                      primary={`${r.course} — ${r.score}${r.max ? "/" + r.max : ""}`}
                      secondary={new Date(r.date).toLocaleDateString()}
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
                  `${participation?.events ?? 0} событий`,
                  participation?.hours ? `${participation.hours} ч.` : null,
                  participation?.groups ? `${participation.groups} круж.` : null,
                ]
                  .filter(Boolean)
                  .join(" • ")}
              </Typography>
              <List dense>
                {(participation?.recent ?? []).map((r, i) => (
                  <ListItem key={i} sx={{ px: 0 }}>
                    <ListItemText
                      primary={r.title}
                      secondary={[new Date(r.date).toLocaleDateString(), r.role]
                        .filter(Boolean)
                        .join(" • ")}
                    />
                  </ListItem>
                ))}
              </List>
            </Stack>
          )}
          {detail === "attendance_recent" && (
            <List dense>
              {(attendance?.recent ?? []).map((r, i) => (
                <ListItem key={i} sx={{ px: 0 }}>
                  <ListItemText
                    primary={`${r.course || "Занятие"} — ${r.status === "present" ? "присутствовал" : r.status === "late" ? "опоздание" : "отсутствовал"}`}
                    secondary={new Date(r.date).toLocaleDateString()}
                  />
                </ListItem>
              ))}
            </List>
          )}
          {detail === "grades_recent" && (
            <List dense>
              {(grades?.recent ?? []).map((r, i) => (
                <ListItem key={i} sx={{ px: 0 }}>
                  <ListItemText
                    primary={`${r.course} — ${r.score}${r.max ? "/" + r.max : ""}`}
                    secondary={new Date(r.date).toLocaleDateString()}
                  />
                </ListItem>
              ))}
            </List>
          )}
          {detail === "participation_recent" && (
            <List dense>
              {(participation?.recent ?? []).map((r, i) => (
                <ListItem key={i} sx={{ px: 0 }}>
                  <ListItemText
                    primary={r.title}
                    secondary={[new Date(r.date).toLocaleDateString(), r.role]
                      .filter(Boolean)
                      .join(" • ")}
                  />
                </ListItem>
              ))}
            </List>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDetail("")}>Закрыть</Button>
        </DialogActions>
      </Dialog>
    </Layout>
  )
}
