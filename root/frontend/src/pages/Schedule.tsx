import Layout from "../components/Layout"
import { useAuth } from "../contexts/AuthContext"
import { useState, useEffect, useMemo, useRef, useCallback, useDeferredValue, startTransition } from "react"
import api from "../api/axios"
import {
  Box,
  Typography,
  Button,
  Stack,
  TextField,
  MenuItem,
  Select,
  InputLabel,
  FormControl,
  Snackbar,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  IconButton,
  Paper,
  Tooltip,
  Dialog,
  DialogTitle,
  DialogContent,
  Chip,
  LinearProgress
} from "@mui/material"
import DeleteIcon from "@mui/icons-material/Delete"
import InfoOutlinedIcon from "@mui/icons-material/InfoOutlined"
import AddIcon from "@mui/icons-material/Add"
import CalendarMonthIcon from "@mui/icons-material/CalendarMonth"
import AccessTimeIcon from "@mui/icons-material/AccessTime"
import SchoolIcon from "@mui/icons-material/School"
import RoomIcon from "@mui/icons-material/Room"
import useMediaQuery from "@mui/material/useMediaQuery"
import dayjs from "dayjs"
import isoWeek from "dayjs/plugin/isoWeek"
import "dayjs/locale/ru"

dayjs.extend(isoWeek)
dayjs.locale("ru")

type Lesson = any

const days = [
  "Понедельник",
  "Вторник",
  "Среда",
  "Четверг",
  "Пятница",
  "Суббота"
] as const

const dayShort = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб"] as const

const lessonTypeColor: Record<string, string> = {
  "Лекция": "var(--badge-lec)",
  "ПЗ": "var(--badge-prac)",
  "ЛЗ": "var(--badge-lab)",
  "Проектная деятельность": "#607d8b"
}

function getTimeStr(lesson: Lesson) {
  if (!lesson?.start_time) return ""
  if (lesson.start_time.length >= 16 && lesson.start_time[10] === "T") return lesson.start_time.slice(11, 16)
  return lesson.start_time.slice(0, 5)
}

function getEndTimeStr(lesson: Lesson) {
  if (!lesson?.end_time) return ""
  if (lesson.end_time.length >= 16 && lesson.end_time[10] === "T") return lesson.end_time.slice(11, 16)
  return lesson.end_time.slice(0, 5)
}

function parseMinutes(s?: string | null) {
  if (!s) return null
  const hhmm = s.length >= 16 && s[10] === "T" ? s.slice(11, 16) : s.slice(0, 5)
  const [h, m] = hhmm.split(":").map(Number)
  if (Number.isNaN(h) || Number.isNaN(m)) return null
  return h * 60 + m
}

function buildTable(schedule: Lesson[]) {
  const lessonsByDay = days.map(day =>
    schedule
      .filter(l => l.weekday === day)
      .sort((a, b) => getTimeStr(a).localeCompare(getTimeStr(b)))
  )
  const maxLessons = Math.max(...lessonsByDay.map(arr => arr.length), 0)
  const rows: (Lesson | null)[][] = []
  for (let i = 0; i < maxLessons; ++i) rows.push(days.map((_, d) => lessonsByDay[d][i] || null))
  return rows
}

function getTodayIdx() {
  const iso = (dayjs() as any).isoWeekday?.() || dayjs().day()
  if (iso === 7) return -1
  return (iso - 1) as 0 | 1 | 2 | 3 | 4 | 5
}

function minutesDiff(a?: string, b?: string) {
  const ma = parseMinutes(a) ?? 0
  const mb = parseMinutes(b) ?? 0
  return mb - ma
}

const toDayjs = (s?: string | null) => {
  if (!s) return null
  if (s.length >= 16 && s.includes("T")) return dayjs(s)
  return dayjs(dayjs().format("YYYY-MM-DDT") + (s.length === 5 ? s + ":00" : s))
}

export default function Schedule() {
  const { user, loading } = useAuth()
  const [groups, setGroups] = useState<any[]>([])
  const [selectedGroup, setSelectedGroup] = useState<number | null>(null)
  const [groupSchedule, setGroupSchedule] = useState<Lesson[]>([])
  const [currentParity, setCurrentParity] = useState<"odd" | "even">("odd")
  const [snack, setSnack] = useState("")
  const [openDialog, setOpenDialog] = useState(false)
  const [dialogLesson, setDialogLesson] = useState<Lesson | null>(null)
  const [editing, setEditing] = useState(false)
  const [editLesson, setEditLesson] = useState<Lesson | null>(null)
  const [addDialogOpen, setAddDialogOpen] = useState(false)
  const [addDay, setAddDay] = useState<string>("")
  const [addFields, setAddFields] = useState({
    subject: "",
    teacher: "",
    room: "",
    lessonType: "Лекция",
    startTime: "",
    endTime: "",
    parity: "both"
  })
  const isMobile = useMediaQuery("(max-width:1730px)")
  const tableScrollRef = useRef<HTMLDivElement | null>(null)
  const headRefs = useRef<(HTMLTableCellElement | null)[]>([])
  const dayCardRefs = useRef<(HTMLDivElement | null)[]>([])
  if (headRefs.current.length !== days.length) headRefs.current = Array(days.length).fill(null)
  if (dayCardRefs.current.length !== days.length) dayCardRefs.current = Array(days.length).fill(null)
  const mainAlignSx = { ml: { xs: 0, sm: 2, md: 3, lg: 6 }, mr: { xs: 0, sm: 2, md: 3, lg: 6 } }
  const todayIdx = getTodayIdx()
  const hasToday = todayIdx >= 0 && todayIdx < days.length
  const [nowTick, setNowTick] = useState(dayjs())
  useEffect(() => {
    const id = setInterval(() => setNowTick(dayjs()), 30000)
    return () => clearInterval(id)
  }, [])
  const minutesNow = useMemo(() => nowTick.hour() * 60 + nowTick.minute(), [nowTick])

  const cachedGetGroups = useCallback(async () => {
    try {
      const res = await api.get("/groups")
      setGroups(Array.isArray(res.data) ? res.data : [])
      return res.data
    } catch {
      setGroups([])
      return []
    }
  }, [])

  const cacheKey = (gid: number) => `sched:${gid}`
  const etagKey = (gid: number) => `sched:${gid}:etag`

  const loadScheduleWithCache = useCallback(async (gid: number) => {
    try {
      const etag = localStorage.getItem(etagKey(gid)) || ""
      const res = await api.get(`/schedule/${gid}`, {
        headers: etag ? { "If-None-Match": etag } : {},
        validateStatus: s => s === 200 || s === 304
      })
      if (res.status === 304) {
        const cached = localStorage.getItem(cacheKey(gid))
        setGroupSchedule(cached ? JSON.parse(cached) : [])
      } else {
        setGroupSchedule(Array.isArray(res.data) ? res.data : [])
        const newTag = (res.headers?.etag as string) || ""
        localStorage.setItem(cacheKey(gid), JSON.stringify(res.data))
        if (newTag) localStorage.setItem(etagKey(gid), newTag)
      }
    } catch {
      const cached = localStorage.getItem(cacheKey(gid))
      setGroupSchedule(cached ? JSON.parse(cached) : [])
    }
  }, [])

  useEffect(() => {
    if (!user) return
    if (user.role === "student" && user.group_id) {
      setSelectedGroup(user.group_id)
      loadScheduleWithCache(user.group_id)
      cachedGetGroups()
      return
    }
    if (user.role === "teacher" || user.role === "admin") {
      cachedGetGroups().then(gs => {
        const firstGroup = gs?.length > 0 ? gs[0].id : null
        setSelectedGroup(firstGroup)
        if (firstGroup) loadScheduleWithCache(firstGroup)
        else setGroupSchedule([])
      })
    }
  }, [user, cachedGetGroups, loadScheduleWithCache])

  useEffect(() => {
    if (selectedGroup && (user?.role === "teacher" || user?.role === "admin")) {
      loadScheduleWithCache(selectedGroup)
    }
  }, [selectedGroup, user, loadScheduleWithCache])

  const filteredSchedule = useMemo(
    () => groupSchedule.filter(l => l.parity === "both" || l.parity === currentParity),
    [groupSchedule, currentParity]
  )

  const todayLessons = useMemo(() => {
    if (!hasToday) return []
    return filteredSchedule
      .filter(l => l.weekday === days[todayIdx])
      .sort((a, b) => getTimeStr(a).localeCompare(getTimeStr(b)))
  }, [filteredSchedule, hasToday, todayIdx])

  const currentLesson = useMemo(() => {
    if (!hasToday) return null
    return todayLessons.find(l => {
      const s = parseMinutes(l.start_time) ?? -1
      const e = parseMinutes(l.end_time) ?? -1
      return minutesNow >= s && minutesNow < e
    }) || null
  }, [todayLessons, minutesNow, hasToday])

  const nextLesson = useMemo(() => {
    if (!hasToday) return null
    if (currentLesson) {
      const endM = parseMinutes(currentLesson.end_time) ?? 0
      return todayLessons.find(l => (parseMinutes(l.start_time) ?? 0) > endM) || null
    }
    return todayLessons.find(l => (parseMinutes(l.start_time) ?? 0) > minutesNow) || null
  }, [todayLessons, currentLesson, minutesNow, hasToday])

  const [timeLeftText, setTimeLeftText] = useState<string>("")
  useEffect(() => {
    const fmtLeft = (h: number, m: number) => (h > 0 ? `${h}ч ${m}м` : `${m}м`)
    const calc = () => {
      if (currentLesson) {
        const end = parseMinutes(currentLesson.end_time) ?? 0
        const left = Math.max(0, end - (dayjs().hour() * 60 + dayjs().minute()))
        const h = Math.floor(left / 60)
        const m = left % 60
        setTimeLeftText(`До конца: ${fmtLeft(h, m)}`)
      } else if (nextLesson) {
        const start = parseMinutes(nextLesson.start_time) ?? 0
        const left = Math.max(0, start - (dayjs().hour() * 60 + dayjs().minute()))
        const h = Math.floor(left / 60)
        const m = left % 60
        setTimeLeftText(`До начала: ${fmtLeft(h, m)}`)
      } else {
        setTimeLeftText("")
      }
    }
    calc()
    const id = setInterval(calc, 30000)
    return () => clearInterval(id)
  }, [currentLesson, nextLesson])

  const currentProgress = useMemo(() => {
    if (!currentLesson) return 0
    const s = parseMinutes(currentLesson.start_time)
    const e = parseMinutes(currentLesson.end_time)
    if (s == null || e == null || e <= s) return 0
    const span = e - s
    const passed = Math.min(Math.max(minutesNow - s, 0), span)
    return Math.round((passed / span) * 100)
  }, [currentLesson, minutesNow])

  const tableRowsBase = useMemo(() => buildTable(filteredSchedule), [filteredSchedule])
  const tableRows = useDeferredValue(tableRowsBase)
  const [rowLimit, setRowLimit] = useState(0)
  useEffect(() => {
    setRowLimit(prev => {
      const start = Math.min(12, tableRows.length)
      return start
    })
  }, [tableRows.length])
  useEffect(() => {
    let cancelled = false
    const chunk = 12
    const step = () => {
      if (cancelled) return
      startTransition(() => {
        setRowLimit(prev => {
          const next = Math.min(prev + chunk, tableRows.length)
          return next
        })
      })
      if (!cancelled && rowLimit < tableRows.length) {
        if ("requestIdleCallback" in window) (window as any).requestIdleCallback(step)
        else setTimeout(step, 0)
      }
    }
    if (tableRows.length > 0 && rowLimit < tableRows.length) {
      if ("requestIdleCallback" in window) (window as any).requestIdleCallback(step)
      else setTimeout(step, 0)
    }
    return () => { cancelled = true }
  }, [tableRows, rowLimit])

  useEffect(() => {
    if (isMobile || !hasToday) return
    const container = tableScrollRef.current
    const cell = headRefs.current[todayIdx]
    if (container && cell) {
      const left = cell.offsetLeft - 120
      container.scrollTo({ left, behavior: "smooth" })
    }
  }, [rowLimit, isMobile, todayIdx, hasToday])

  const todayLabel = useMemo(() => dayjs().format("DD MMM, dddd"), [])
  const activeGroupName = groups.find(g => g.id === selectedGroup)?.name || ""

  const conflictedIds = useMemo(() => {
    const byDay = new Map<string, Lesson[]>()
    for (const l of filteredSchedule) {
      const arr = byDay.get(l.weekday) ?? []
      arr.push(l)
      byDay.set(l.weekday, arr)
    }
    const set = new Set<number>()
    for (const [, arr] of byDay) {
      arr.sort((a, b) => getTimeStr(a).localeCompare(getTimeStr(b)))
      for (let i = 0; i < arr.length; i++) {
        for (let j = i + 1; j < arr.length; j++) {
          const s1 = parseMinutes(arr[i].start_time), e1 = parseMinutes(arr[i].end_time)
          const s2 = parseMinutes(arr[j].start_time), e2 = parseMinutes(arr[j].end_time)
          if (s1 == null || e1 == null || s2 == null || e2 == null) continue
          const overlap = Math.max(s1, s2) < Math.min(e1, e2)
          if (overlap) { set.add(arr[i].id); set.add(arr[j].id) }
        }
      }
    }
    return set
  }, [filteredSchedule])

  const badgeBase = {
    display: "inline-flex",
    alignItems: "center",
    px: 1.3,
    py: 1.2,
    borderRadius: 999,
    fontWeight: 700,
    lineHeight: 1,
    fontSize: "clamp(.78rem, .7rem + .35vw, .98rem)",
    userSelect: "none",
    whiteSpace: "nowrap"
  } as const

  const badgeGhost = {
    ...badgeBase,
    background: "var(--btn-bg)",
    color: "var(--nav-text)",
    border: "1px solid var(--btn-border)"
  } as const

  const headerCardSx = {
    borderRadius: 4,
    p: 2,
    background: "var(--card-bg)",
    boxShadow: "0 12px 36px #00000012, 0 4px 14px #0000000a",
    border: "1px solid var(--btn-border)"
  }

  const headerActions = (
    <Stack direction="row" spacing={2} alignItems="center" mb={2.5} flexWrap="wrap">
      <Typography component="span">Неделя:</Typography>
      <Button
        variant={currentParity === "odd" ? "contained" : "outlined"}
        onClick={() => setCurrentParity("odd")}
      >
        Нечётная
      </Button>
      <Button
        variant={currentParity === "even" ? "contained" : "outlined"}
        onClick={() => setCurrentParity("even")}
      >
        Чётная
      </Button>
    </Stack>
  )

  const renderBreakChip = (rowIdx: number, colIdx: number) => {
    if (rowIdx === 0) return null
    const prev = tableRows[rowIdx - 1]?.[colIdx]
    const curr = tableRows[rowIdx]?.[colIdx]
    if (!prev || !curr) return null
    const gap = minutesDiff(prev.end_time, curr.start_time)
    if (gap <= 0) return null
    return (
      <Box
        sx={{
          position: "absolute",
          top: -10,
          left: "50%",
          transform: "translateX(-50%)",
          pointerEvents: "none",
          zIndex: 3
        }}
      >
        <Chip size="small" label={`перерыв ${gap} мин`} className="chip-break" />
      </Box>
    )
  }

  const lessonCardHeight = 148

  const LessonCellCard = ({
    lesson,
    isConflict,
    onDelete,
    onOpen,
    hasBreakBefore
  }: {
    lesson: Lesson
    isConflict: boolean
    onDelete: () => void
    onOpen: () => void
    hasBreakBefore: boolean
  }) => (
    <Box
      onClick={onOpen}
      sx={{
        minHeight: lessonCardHeight,
        p: 1.2,
        pl: 1.8,
        pr: 1.4,
        borderRadius: 2,
        background: "var(--option-bg)",
        border: "1px solid var(--btn-border)",
        boxShadow: "var(--option-shadow)",
        transition: "transform .2s, box-shadow .2s",
        position: "relative",
        cursor: "pointer",
        mt: hasBreakBefore ? 2.5 : 0,
        "&:hover": { transform: "translateY(-1px)", boxShadow: "0 10px 28px #0000001f, 0 2px 10px #0003" }
      }}
      title={isConflict ? "Пересечение по времени" : undefined}
    >
      <Box sx={{ position: "absolute", left: -1, top: -1, bottom: -1, width: 6, borderTopLeftRadius: 8, borderBottomLeftRadius: 8, background: lessonTypeColor[lesson.lesson_type] || "#888" }} />
      <Stack spacing={0.6}>
        <Stack direction="row" alignItems="center" justifyContent="space-between">
          <Chip
            size="small"
            label={lesson.lesson_type}
            sx={{ height: 22, fontWeight: 700, color: "#fff", background: lessonTypeColor[lesson.lesson_type] || "#888" }}
          />
          <Chip
            size="small"
            className="chip-time"
            icon={<AccessTimeIcon sx={{ fontSize: 16 }} />}
            label={`${getTimeStr(lesson)}–${getEndTimeStr(lesson)}`}
            sx={{ bgcolor: "transparent", border: "1px solid var(--btn-border)" }}
          />
        </Stack>
        <Typography
          fontWeight={800}
          sx={{
            color: "var(--page-text)",
            fontSize: "1rem",
            display: "-webkit-box",
            WebkitLineClamp: 2,
            WebkitBoxOrient: "vertical",
            overflow: "hidden"
          }}
        >
          {lesson.subject}
        </Typography>
        <Stack direction="row" gap={1} flexWrap="wrap">
          <Chip size="small" variant="outlined" icon={<SchoolIcon sx={{ fontSize: 16 }} />} label={lesson.teacher} sx={{ borderColor: "var(--btn-border)", color: "var(--page-text)" }} />
          <Chip size="small" variant="outlined" icon={<RoomIcon sx={{ fontSize: 16 }} />} label={lesson.room} sx={{ borderColor: "var(--btn-border)", color: "var(--page-text)" }} />
        </Stack>
      </Stack>
      <Tooltip title="Подробнее">
        <InfoOutlinedIcon sx={{ position: "absolute", right: 8, bottom: 8, fontSize: 18, color: "var(--secondary-text)" }} />
      </Tooltip>
      {(user?.role === "admin" || user?.role === "teacher") && (
        <IconButton
          aria-label="Удалить занятие"
          size="small"
          sx={{ position: "absolute", top: 6, right: 6, bgcolor: "var(--card-bg)", zIndex: 2 }}
          onClick={(e) => { e.stopPropagation(); onDelete() }}
        >
          <DeleteIcon fontSize="small" color="error" />
        </IconButton>
      )}
      {isConflict && <Box sx={{ position: "absolute", inset: 0, borderRadius: 2, boxShadow: "0 0 0 3px #ef535033 inset", pointerEvents: "none" }} />}
    </Box>
  )

  const renderTable = () => {
    const visibleRows = tableRows.slice(0, rowLimit)
    return (
      <TableContainer
        component={Paper}
        ref={tableScrollRef}
        sx={{
          width: "100%",
          maxWidth: "min(98vw,1920px)",
          mx: "auto",
          borderRadius: { xs: 2, md: 4 },
          boxShadow: 5,
          minHeight: 360,
          bgcolor: "var(--card-bg)",
          color: "var(--page-text)",
          overflowX: "auto",
          scrollBehavior: "smooth",
          contentVisibility: "auto",
          containIntrinsicSize: "600px"
        }}
      >
        <Table stickyHeader>
          <TableHead>
            <TableRow>
              <TableCell align="center" sx={{ fontWeight: 700, width: 45, background: "var(--table-header-bg)", zIndex: 10, position: "sticky", left: 0, color: "var(--page-text)", fontSize: "clamp(0.98rem,1.7vw,1.13rem)" }}>№</TableCell>
              {days.map((day, idx) => (
                <TableCell
                  align="center"
                  key={day}
                  ref={el => { headRefs.current[idx] = el }}
                  sx={{
                    fontWeight: 700,
                    background: hasToday && idx === todayIdx ? "var(--table-row-today)" : "var(--table-header-bg)",
                    fontSize: "clamp(0.97rem, 1.4vw, 1.11rem)",
                    zIndex: 5,
                    color: "var(--page-text)",
                    position: "relative",
                    borderLeft: hasToday && idx === todayIdx ? "2px solid #2563eb55" : undefined,
                    borderRight: hasToday && idx === todayIdx ? "2px solid #2563eb55" : undefined
                  }}
                >
                  <Box display="flex" alignItems="center" justifyContent="center" gap={0.5}>
                    {day}
                    {(user?.role === "admin" || user?.role === "teacher") && (
                      <IconButton
                        size="small"
                        onClick={e => {
                          e.stopPropagation()
                          setAddDay(day)
                          setAddDialogOpen(true)
                        }}
                        sx={{ ml: 1, border: "1px solid var(--btn-border)", bgcolor: "var(--card-bg)", "&:hover": { bgcolor: "var(--option-bg)" }, height: 26, width: 26 }}
                        aria-label={`Добавить занятие на день ${day}`}
                      >
                        <AddIcon fontSize="small" />
                      </IconButton>
                    )}
                  </Box>
                </TableCell>
              ))}
            </TableRow>
          </TableHead>
          <TableBody sx={{ contentVisibility: "auto" }}>
            {visibleRows.length === 0 ? (
              <TableRow>
                <TableCell align="center" colSpan={days.length + 1}>Нет занятий</TableCell>
              </TableRow>
            ) : (
              visibleRows.map((row, rowIdx) => (
                <TableRow key={rowIdx} sx={{ "&:hover": { background: "var(--table-row-hover)" } }}>
                  <TableCell align="center" sx={{ fontWeight: 700, background: "var(--table-header-bg)", position: "sticky", left: 0, color: "var(--page-text)", fontSize: "clamp(0.98rem,1.7vw,1.13rem)" }}>
                    {rowIdx + 1}
                  </TableCell>
                  {row.map((lesson, colIdx) => {
                    const colIsToday = hasToday && colIdx === todayIdx
                    if (!lesson) {
                      return (
                        <TableCell
                          key={`empty-${rowIdx}-${colIdx}`}
                          sx={{
                            background: colIsToday ? "var(--table-row-today)" : "transparent",
                            p: 1.2
                          }}
                        >
                          <Box sx={{ minHeight: lessonCardHeight, borderRadius: 2, border: "1px dashed var(--glass-border)", bgcolor: "transparent" }} />
                        </TableCell>
                      )
                    }
                    let hasBreakBefore = false
                    if (rowIdx > 0) {
                      const prev = visibleRows[rowIdx - 1]?.[colIdx]
                      if (prev) {
                        const gap = minutesDiff(prev.end_time, lesson.start_time)
                        hasBreakBefore = gap > 0
                      }
                    }
                    const isConflict = conflictedIds.has(lesson.id)
                    return (
                      <TableCell
                        align="center"
                        key={lesson.id ?? `${rowIdx}-${colIdx}`}
                        sx={{
                          position: "relative",
                          color: "var(--page-text)",
                          background: colIsToday ? "var(--table-row-today)" : "transparent",
                          overflow: "visible",
                          p: 1.2
                        }}
                      >
                        {renderBreakChip(rowIdx, colIdx)}
                        <LessonCellCard
                          lesson={lesson}
                          isConflict={isConflict}
                          hasBreakBefore={hasBreakBefore}
                          onOpen={() => { setDialogLesson(lesson); setOpenDialog(true) }}
                          onDelete={() => handleDeleteLesson(lesson.id)}
                        />
                      </TableCell>
                    )
                  })}
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </TableContainer>
    )
  }

  const renderMobileDayAnchors = () => (
    <Stack direction="row" gap={1} sx={{ overflowX: "auto", pb: 1, px: 0.5 }}>
      {days.map((d, i) => (
        <Chip
          key={d}
          clickable
          className="chip-day"
          color={hasToday && i === todayIdx ? "primary" : "default"}
          label={dayShort[i]}
          onClick={() => dayCardRefs.current[i]?.scrollIntoView({ behavior: "smooth", block: "start" })}
          sx={{ flex: "0 0 auto" }}
        />
      ))}
    </Stack>
  )

  const renderMobileCards = () => (
    <Stack spacing={2} sx={{ width: "100%", mt: 1 }}>
      {renderMobileDayAnchors()}
      {days.map((day, dayIdx) => {
        const lessons = filteredSchedule
          .filter(l => l.weekday === day)
          .sort((a, b) => getTimeStr(a).localeCompare(getTimeStr(b)))
        return (
          <Paper
            key={day}
            ref={el => { dayCardRefs.current[dayIdx] = el }}
            elevation={4}
            sx={{
              borderRadius: 3,
              p: 2,
              mb: 1,
              bgcolor: hasToday && dayIdx === todayIdx ? "var(--table-row-today)" : "var(--card-bg)",
              border: "1px solid var(--btn-border)",
              boxShadow: "0 10px 30px #00000014, 0 3px 12px #0000000a",
              contentVisibility: "auto",
              containIntrinsicSize: "400px"
            }}
          >
            <Box display="flex" alignItems="center" mb={1} gap={1}>
              <Typography fontWeight={800} fontSize="1.12rem">{day}</Typography>
              {(user?.role === "admin" || user?.role === "teacher") && (
                <IconButton
                  size="small"
                  onClick={e => {
                    e.stopPropagation()
                    setAddDay(day)
                    setAddDialogOpen(true)
                  }}
                  sx={{ ml: 0.5, border: "1px solid var(--btn-border)", bgcolor: "var(--card-bg)", "&:hover": { bgcolor: "var(--option-bg)" }, height: 26, width: 26 }}
                  aria-label={`Добавить занятие на день ${day}`}
                >
                  <AddIcon fontSize="small" />
                </IconButton>
              )}
            </Box>
            {lessons.length === 0 ? (
              <Typography sx={{ color: "var(--secondary-text)" }}>Нет занятий</Typography>
            ) : (
              <Stack spacing={1}>
                {lessons.map((lesson, idx) => {
                  const prev = lessons[idx - 1]
                  const gap = prev ? minutesDiff(prev.end_time, lesson.start_time) : 0
                  return (
                    <Box key={lesson.id}>
                      {idx > 0 && gap > 0 && (
                        <Chip size="small" label={`перерыв ${gap} мин`} className="chip-break" sx={{ mb: 0.8 }} />
                      )}
                      <Box
                        onClick={() => { setDialogLesson(lesson); setOpenDialog(true) }}
                        sx={{
                          p: 1.3,
                          borderRadius: 2,
                          background: "var(--option-bg)",
                          boxShadow: "var(--option-shadow)",
                          border: "1px solid var(--btn-border)",
                          cursor: "pointer",
                          transition: "transform .2s, box-shadow .2s",
                          "&:hover": { background: "var(--option-hover-bg)", transform: "translateY(-1px)", boxShadow: "0 8px 26px #2175ee20, 0 1.5px 8px #0002" },
                          position: "relative"
                        }}
                      >
                        <Box sx={{ position: "absolute", left: 0, top: 0, bottom: 0, width: 6, borderTopLeftRadius: 8, borderBottomLeftRadius: 8, background: lessonTypeColor[lesson.lesson_type] || "#888" }} />
                        <Stack direction="row" gap={1} alignItems="center" flexWrap="wrap" sx={{ pl: 1 }}>
                          <Chip size="small" label={lesson.lesson_type} className="chip-type" sx={{ background: lessonTypeColor[lesson.lesson_type] || "#888", color: "#fff", height: 24, fontWeight: 700 }} />
                          <Chip size="small" className="chip-time" icon={<AccessTimeIcon sx={{ fontSize: 16 }} />} label={`${getTimeStr(lesson)}–${getEndTimeStr(lesson)}`} />
                        </Stack>
                        <Typography fontWeight={700} fontSize="1.02rem" sx={{ color: "var(--page-text)", pl: 1, mt: 0.5, display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical", overflow: "hidden" }}>
                          {lesson.subject}
                        </Typography>
                        <Stack direction="row" gap={1} flexWrap="wrap" sx={{ pl: 1, mt: 0.4 }}>
                          <Chip size="small" variant="outlined" icon={<SchoolIcon sx={{ fontSize: 16 }} />} label={lesson.teacher} />
                          <Chip size="small" variant="outlined" icon={<RoomIcon sx={{ fontSize: 16 }} />} label={lesson.room} />
                        </Stack>
                      </Box>
                    </Box>
                  )
                })}
              </Stack>
            )}
          </Paper>
        )
      })}
    </Stack>
  )

  if (loading)
    return (
      <Layout>
        <Box minHeight="70vh" display="flex" alignItems="center" justifyContent="center">
          Загрузка...
        </Box>
      </Layout>
    )

  return (
    <Layout>
      <style>{`
        @media print {
          body { background: #fff !important; }
          .no-print { display: none !important; }
          table { box-shadow: none !important; }
          .MuiTableCell-root { border: 1px solid #999 !important; }
          .MuiTableHead-root .MuiTableCell-root { background: #eee !important; color: #000 !important; }
          .MuiPaper-root { box-shadow: none !important; }
        }
      `}</style>
      <Box sx={{ width: "100vw", minHeight: "100vh", bgcolor: "var(--page-bg)", color: "var(--page-text)", py: { xs: 3.5, sm: 3.5, md: 3.5, lg: 3.5 } }}>
        <Box sx={{ ...mainAlignSx, ml: { xs: 2, sm: 4, md: 5, lg: 8 }, mr: { xs: 2, sm: 4, md: 5, lg: 8 }, maxWidth: 980, mb: 2, mt: 0 }}>
          <Stack direction="row" alignItems="center" flexWrap="wrap" gap={1.3} mb={2.2} mt={0.5}>
            <CalendarMonthIcon color="primary" sx={{ fontSize: 34 }} />
            <Typography variant="h4" fontWeight={700} color="primary.main" sx={{ fontSize: "clamp(0.8rem, 5vw, 2.7rem)" }}>
              {user?.role === "student" ? "Расписание моей группы" : "Расписание групп"}
            </Typography>
            <Box sx={{ ...badgeGhost, transform: "translateY(8px)" }}>{todayLabel}</Box>
            {activeGroupName && <Box sx={{ ...badgeGhost, transform: "translateY(8px)" }}>Группа: {activeGroupName}</Box>}
          </Stack>

          <Stack direction="row" alignItems="center" flexWrap="wrap" gap={1} mb={2}>
            {headerActions}
          </Stack>

          <Box className="no-print" sx={{ ...headerCardSx, mb: 2 }}>
            {currentLesson ? (
              <Box>
                <Stack direction="row" alignItems="center" gap={1} flexWrap="wrap">
                  <Chip size="small" className="chip-clock" label="Сейчас идёт" />
                  <Chip size="small" className="chip-time" label={`${getTimeStr(currentLesson)}–${getEndTimeStr(currentLesson)}`} />
                  <Typography sx={{ fontWeight: 800 }}>{currentLesson.subject}</Typography>
                  {!!timeLeftText && <Chip size="small" className="chip-left" label={timeLeftText} />}
                </Stack>
                <Stack direction="row" gap={1} mt={1} flexWrap="wrap">
                  <Chip size="small" variant="outlined" icon={<SchoolIcon sx={{ fontSize: 16 }} />} label={currentLesson.teacher} />
                  <Chip size="small" variant="outlined" icon={<RoomIcon sx={{ fontSize: 16 }} />} label={currentLesson.room} />
                </Stack>
                <LinearProgress
                  value={currentProgress}
                  variant="determinate"
                  className="lesson-progress"
                  sx={{
                    mt: 1.5,
                    height: 8,
                    borderRadius: 999,
                    backgroundColor: "var(--progress-track)",
                    "& .MuiLinearProgress-bar": {
                      backgroundColor: "var(--progress-bar)",
                      transition: "transform 0.4s linear"
                    }
                  }}
                  aria-label="Прогресс текущего занятия"
                />
              </Box>
            ) : nextLesson ? (
              <Stack direction="row" alignItems="center" gap={1} flexWrap="wrap">
                <Chip size="small" className="chip-clock" label="Далее" />
                <Chip size="small" className="chip-time" label={`${getTimeStr(nextLesson)}–${getEndTimeStr(nextLesson)}`} />
                <Typography sx={{ fontWeight: 800 }}>{nextLesson.subject}</Typography>
                {!!timeLeftText && <Chip size="small" className="chip-left" label={timeLeftText} />}
              </Stack>
            ) : (
              <Typography sx={{ color: "var(--secondary-text)" }}>На сегодня занятий больше нет</Typography>
            )}
          </Box>

          {(user?.role === "teacher" || user?.role === "admin") && (
            <FormControl fullWidth sx={{ mb: 2, maxWidth: 340 }}>
              <InputLabel>Группа</InputLabel>
              <Select
                value={selectedGroup ?? ""}
                label="Группа"
                onChange={e => setSelectedGroup(Number(e.target.value))}
              >
                {groups.map(g => (
                  <MenuItem value={g.id} key={g.id}>{g.name}</MenuItem>
                ))}
              </Select>
            </FormControl>
          )}
        </Box>

        <Box sx={{ ...mainAlignSx, maxWidth: 1920, px: { xs: 1, md: 2 } }}>
          {isMobile ? renderMobileCards() : renderTable()}
        </Box>

        <Dialog open={openDialog} onClose={() => setOpenDialog(false)}>
          <DialogTitle>{dialogLesson?.subject || "Детали занятия"}</DialogTitle>
          <DialogContent>
            {dialogLesson && (
              <Box>
                <Box mb={1}>
                  <b>Тип:</b>{" "}
                  <span style={{ color: "#fff", background: lessonTypeColor[dialogLesson.lesson_type] || "#888", borderRadius: 5, padding: "2px 8px" }}>
                    {dialogLesson.lesson_type}
                  </span>
                </Box>
                <Box><b>Время:</b> {getTimeStr(dialogLesson)}–{getEndTimeStr(dialogLesson)}</Box>
                <Box><b>Преподаватель:</b> {dialogLesson.teacher}</Box>
                <Box><b>Аудитория:</b> {dialogLesson.room}</Box>
                <Stack direction="row" gap={1.2} mt={2}>
                  {(user?.role === "admin" || user?.role === "teacher") && (
                    <Button variant="outlined" onClick={() => { setEditing(true); setEditLesson(dialogLesson) }}>
                      Редактировать
                    </Button>
                  )}
                  <Button variant="outlined" color="secondary" onClick={() => setOpenDialog(false)}>
                    Закрыть
                  </Button>
                </Stack>
              </Box>
            )}
          </DialogContent>
        </Dialog>

        <Dialog open={editing} onClose={() => setEditing(false)}>
          <DialogTitle>Редактировать занятие</DialogTitle>
          <DialogContent>
            {editLesson && (
              <Stack spacing={2} mt={1}>
                <TextField label="Предмет" value={editLesson.subject} onChange={e => setEditLesson({ ...editLesson, subject: e.target.value })} />
                <TextField label="Преподаватель" value={editLesson.teacher} onChange={e => setEditLesson({ ...editLesson, teacher: e.target.value })} />
                <TextField label="Аудитория" value={editLesson.room} onChange={e => setEditLesson({ ...editLesson, room: e.target.value })} />
                <TextField select label="Тип занятия" value={editLesson.lesson_type} onChange={e => setEditLesson({ ...editLesson, lesson_type: e.target.value })}>
                  <MenuItem value="Лекция">Лекция</MenuItem>
                  <MenuItem value="ПЗ">Практика</MenuItem>
                  <MenuItem value="ЛЗ">Лабораторная</MenuItem>
                  <MenuItem value="Проектная деятельность">Проектная деятельность</MenuItem>
                </TextField>
                <TextField select label="День" value={editLesson.weekday} onChange={e => setEditLesson({ ...editLesson, weekday: e.target.value })}>
                  {days.map(day => <MenuItem key={day} value={day}>{day}</MenuItem>)}
                </TextField>
                <TextField
                  type="time"
                  label="Начало"
                  value={getTimeStr(editLesson)}
                  onChange={e => setEditLesson({ ...editLesson, start_time: `${editLesson.start_time?.slice(0, 11) || dayjs().format("YYYY-MM-DDT")}${e.target.value}:00` })}
                />
                <TextField
                  type="time"
                  label="Конец"
                  value={getEndTimeStr(editLesson)}
                  onChange={e => setEditLesson({ ...editLesson, end_time: `${editLesson.end_time?.slice(0, 11) || dayjs().format("YYYY-MM-DDT")}${e.target.value}:00` })}
                />
                <TextField select label="Неделя" value={editLesson.parity} onChange={e => setEditLesson({ ...editLesson, parity: e.target.value })}>
                  <MenuItem value="both">Обе</MenuItem>
                  <MenuItem value="odd">Нечётная</MenuItem>
                  <MenuItem value="even">Чётная</MenuItem>
                </TextField>
                <Box display="flex" gap={2} mt={2}>
                  <Button
                    variant="contained"
                    onClick={async () => {
                      if (!editLesson) return
                      const optimisticId = editLesson.id
                      const backup = groupSchedule
                      setGroupSchedule(prev => prev.map(l => l.id === optimisticId ? editLesson : l))
                      try {
                        await api.patch(`/schedule/${optimisticId}`, {
                          subject: editLesson.subject,
                          teacher: editLesson.teacher,
                          room: editLesson.room,
                          lesson_type: editLesson.lesson_type,
                          weekday: editLesson.weekday,
                          start_time: editLesson.start_time,
                          end_time: editLesson.end_time,
                          parity: editLesson.parity
                        })
                        setSnack("Изменения сохранены")
                        setEditing(false)
                        setOpenDialog(false)
                        if (selectedGroup) await loadScheduleWithCache(selectedGroup)
                      } catch {
                        setSnack("Ошибка при сохранении")
                        setGroupSchedule(backup)
                      }
                    }}
                  >
                    Сохранить
                  </Button>
                  <Button variant="outlined" color="secondary" onClick={() => setEditing(false)}>
                    Отмена
                  </Button>
                </Box>
              </Stack>
            )}
          </DialogContent>
        </Dialog>

        <Dialog open={addDialogOpen} onClose={() => setAddDialogOpen(false)}>
          <DialogTitle>Добавить занятие ({addDay})</DialogTitle>
          <DialogContent>
            <Stack spacing={2} mt={1} sx={{ minWidth: { xs: "auto", sm: 340 } }}>
              <TextField label="Предмет" value={addFields.subject} onChange={e => setAddFields({ ...addFields, subject: e.target.value })} fullWidth />
              <TextField label="Преподаватель" value={addFields.teacher} onChange={e => setAddFields({ ...addFields, teacher: e.target.value })} fullWidth />
              <TextField label="Аудитория" value={addFields.room} onChange={e => setAddFields({ ...addFields, room: e.target.value })} fullWidth />
              <TextField select label="Тип занятия" value={addFields.lessonType} onChange={e => setAddFields({ ...addFields, lessonType: e.target.value })} fullWidth>
                <MenuItem value="Лекция">Лекция</MenuItem>
                <MenuItem value="ПЗ">Практика</MenuItem>
                <MenuItem value="ЛЗ">Лабораторная</MenuItem>
                <MenuItem value="Проектная деятельность">Проектная деятельность</MenuItem>
              </TextField>
              <TextField type="time" label="Начало" value={addFields.startTime} onChange={e => setAddFields({ ...addFields, startTime: e.target.value })} fullWidth />
              <TextField type="time" label="Конец" value={addFields.endTime} onChange={e => setAddFields({ ...addFields, endTime: e.target.value })} fullWidth />
              <TextField select label="Неделя" value={addFields.parity} onChange={e => setAddFields({ ...addFields, parity: e.target.value })} fullWidth>
                <MenuItem value="both">Обе</MenuItem>
                <MenuItem value="odd">Нечётная</MenuItem>
                <MenuItem value="even">Чётная</MenuItem>
              </TextField>
              <Box display="flex" gap={2} mt={2}>
                <Button variant="contained" onClick={handleAddLesson}>Добавить</Button>
                <Button variant="outlined" color="secondary" onClick={() => setAddDialogOpen(false)}>Отмена</Button>
              </Box>
            </Stack>
          </DialogContent>
        </Dialog>

        <Snackbar
          open={!!snack}
          autoHideDuration={2200}
          onClose={() => setSnack("")}
          message={snack}
          anchorOrigin={{ vertical: "bottom", horizontal: "center" }}
        />
      </Box>
    </Layout>
  )

  async function handleAddLesson() {
    const { subject, teacher, room, lessonType, startTime, endTime, parity } = addFields
    if (!subject || !teacher || !room || !addDay || !startTime || !endTime || !selectedGroup) {
      setSnack("Заполните все поля")
      return
    }
    const optimistic: Lesson = {
      id: Date.now(),
      group_id: selectedGroup,
      subject,
      teacher,
      room,
      lesson_type: lessonType,
      weekday: addDay,
      start_time: dayjs().format("YYYY-MM-DDT") + startTime + ":00",
      end_time: dayjs().format("YYYY-MM-DDT") + endTime + ":00",
      parity
    }
    setGroupSchedule(prev => [...prev, optimistic])
    try {
      await api.post("/schedule", {
        group_id: selectedGroup,
        subject,
        teacher,
        room,
        lesson_type: lessonType,
        weekday: addDay,
        start_time: optimistic.start_time,
        end_time: optimistic.end_time,
        parity
      })
      setSnack("Занятие добавлено")
      setAddFields({ subject: "", teacher: "", room: "", lessonType: "Лекция", startTime: "", endTime: "", parity: "both" })
      setAddDialogOpen(false)
      if (selectedGroup) await loadScheduleWithCache(selectedGroup)
    } catch {
      setSnack("Ошибка при добавлении")
      setGroupSchedule(prev => prev.filter(l => l.id !== optimistic.id))
    }
  }

  async function handleDeleteLesson(id: number) {
    const backup = groupSchedule
    setGroupSchedule(prev => prev.filter(l => l.id !== id))
    try {
      await api.delete(`/schedule/${id}`)
      if (selectedGroup) await loadScheduleWithCache(selectedGroup)
      setSnack("Занятие удалено")
    } catch {
      setSnack("Ошибка при удалении")
      setGroupSchedule(backup)
    }
  }
}