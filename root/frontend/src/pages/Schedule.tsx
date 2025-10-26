import Layout from "../components/Layout"
import PageFadeIn from "../components/PageFadeIn"
import { useAuth } from "../contexts/AuthContext"
import {
  useState,
  useEffect,
  useMemo,
  useRef,
  useDeferredValue,
  startTransition,
  useCallback,
  type CSSProperties,
} from "react"
import api from "../api/client"
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
  LinearProgress,
} from "@mui/material"
import DeleteIcon from "@mui/icons-material/Delete"
import InfoOutlinedIcon from "@mui/icons-material/InfoOutlined"
import AddIcon from "@mui/icons-material/Add"
import AccessTimeIcon from "@mui/icons-material/AccessTime"
import SchoolIcon from "@mui/icons-material/School"
import RoomIcon from "@mui/icons-material/Room"
import CalendarMonthIcon from "@mui/icons-material/CalendarMonth"
import useMediaQuery from "@mui/material/useMediaQuery"
import dayjs from "dayjs"
import isoWeek from "dayjs/plugin/isoWeek"
import "dayjs/locale/ru"
import "dayjs/locale/en"
import { useQuery, useQueryClient } from "@tanstack/react-query"
import { useTranslation } from "react-i18next"
import { getLocaleForLanguage, useLanguage } from "@/contexts/LanguageContext"

dayjs.extend(isoWeek)

const scheduleGroupsQueryKey = ["schedule", "groups"] as const
const scheduleQueryKey = (groupId: number) => ["schedule", "group", groupId] as const
type ScheduleGroupsQueryKey = typeof scheduleGroupsQueryKey
type InactiveScheduleQueryKey = readonly ["schedule", "group", "none"]
type ActiveScheduleQueryKey = ReturnType<typeof scheduleQueryKey>

const groupsStorageKey = "sched:groups"
const scheduleStorageKey = (groupId: number) => `sched:${groupId}`

const readFromStorage = <T,>(key: string): T | undefined => {
  if (typeof window === "undefined") return undefined
  try {
    const raw = window.localStorage.getItem(key)
    if (!raw) return undefined
    return JSON.parse(raw) as T
  } catch {
    return undefined
  }
}

const writeToStorage = (key: string, value: unknown) => {
  if (typeof window === "undefined") return
  try {
    window.localStorage.setItem(key, JSON.stringify(value))
  } catch {
    /* noop */
  }
}

type LessonParity = "odd" | "even" | "both"
type LessonWeekday = string

type Lesson = {
  id: number
  weekday: LessonWeekday
  parity: LessonParity
  start_time: string | null
  end_time: string | null
  subject?: string | null
  teacher?: string | null
  room?: string | null
  lesson_type?: string | null
  group_id?: number | null
}

type AddLessonFields = {
  subject: string
  teacher: string
  room: string
  lessonType: string
  startTime: string
  endTime: string
  parity: LessonParity
}

type ScheduleGroup = {
  id: number
  name: string
  [key: string]: unknown
}

type LessonTypeConfig = {
  id: string
  backend: string[]
  label: string
  color: string
}

type WeekdayConfig = {
  id: string
  backend: string[]
  long: string
  short: string
}

const defaultLessonTypeColor = "#888"

const minimalLessonTypeFallback: LessonTypeConfig = {
  id: "lesson",
  backend: ["lesson"],
  label: "Lesson",
  color: defaultLessonTypeColor,
}

const minimalWeekdayFallback: WeekdayConfig[] = [
  { id: "mon", backend: ["Monday"], long: "Monday", short: "Mon" },
  { id: "tue", backend: ["Tuesday"], long: "Tuesday", short: "Tue" },
  { id: "wed", backend: ["Wednesday"], long: "Wednesday", short: "Wed" },
  { id: "thu", backend: ["Thursday"], long: "Thursday", short: "Thu" },
  { id: "fri", backend: ["Friday"], long: "Friday", short: "Fri" },
  { id: "sat", backend: ["Saturday"], long: "Saturday", short: "Sat" },
]

const groupsPlaceholder = (previous?: ScheduleGroup[]) => {
  if (previous !== undefined) return previous
  return readFromStorage<ScheduleGroup[]>(groupsStorageKey)
}

const schedulePlaceholder = (groupId: number | null, previous?: Lesson[]) => {
  if (previous !== undefined) return previous
  if (groupId == null) return previous
  return readFromStorage<Lesson[]>(scheduleStorageKey(groupId))
}

function getTimeStr(lesson: Lesson) {
  if (!lesson?.start_time) return ""
  if (lesson.start_time.length >= 16 && lesson.start_time[10] === "T")
    return lesson.start_time.slice(11, 16)
  return lesson.start_time.slice(0, 5)
}

function getEndTimeStr(lesson: Lesson) {
  if (!lesson?.end_time) return ""
  if (lesson.end_time.length >= 16 && lesson.end_time[10] === "T")
    return lesson.end_time.slice(11, 16)
  return lesson.end_time.slice(0, 5)
}

function parseMinutes(s?: string | null) {
  if (!s) return null
  const hhmm = s.length >= 16 && s[10] === "T" ? s.slice(11, 16) : s.slice(0, 5)
  const [h, m] = hhmm.split(":").map(Number)
  if (Number.isNaN(h) || Number.isNaN(m)) return null
  return h * 60 + m
}

function buildTable(schedule: Lesson[], weekdayOrder: readonly string[]) {
  const lessonsByDay = weekdayOrder.map((day) =>
    schedule
      .filter((l) => l.weekday === day)
      .sort((a, b) => getTimeStr(a).localeCompare(getTimeStr(b)))
  )
  const maxLessons = Math.max(...lessonsByDay.map((arr) => arr.length), 0)
  const rows: (Lesson | null)[][] = []
  for (let i = 0; i < maxLessons; ++i)
    rows.push(weekdayOrder.map((_, d) => lessonsByDay[d][i] || null))
  return rows
}

function getTodayIdx() {
  const iso = (dayjs() as any).isoWeekday?.() || dayjs().day()
  if (iso === 7) return -1
  return (iso - 1) as 0 | 1 | 2 | 3 | 4 | 5
}

function minutesDiff(a?: string | null, b?: string | null) {
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
  const queryClient = useQueryClient()
  const { t } = useTranslation(["schedule", "common"])
  const { language } = useLanguage()
  const locale = getLocaleForLanguage(language)
  const weekdayConfigs = useMemo(() => {
    const rawItems = t("schedule:weekdays.items", { returnObjects: true }) as unknown
    const rawOrder = t("schedule:weekdays.order", { returnObjects: true }) as unknown
    const items =
      rawItems && typeof rawItems === "object" && !Array.isArray(rawItems)
        ? (rawItems as Record<string, unknown>)
        : {}
    const fallbackById = new Map(minimalWeekdayFallback.map((item) => [item.id, item]))
    const baseOrder =
      Array.isArray(rawOrder) && rawOrder.length > 0
        ? rawOrder.filter((id): id is string => typeof id === "string" && id.length > 0)
        : (Object.keys(items) as string[])
    const configs: WeekdayConfig[] = []
    const seen = new Set<string>()
    const toConfig = (id: string, value?: unknown): WeekdayConfig => {
      const fallback = fallbackById.get(id) ?? {
        id,
        backend: [id],
        long: id,
        short: id.slice(0, 3),
      }
      const entry =
        value && typeof value === "object" && !Array.isArray(value)
          ? (value as Record<string, unknown>)
          : undefined
      let backend: string[] = []
      if (Array.isArray(entry?.backend)) {
        backend = entry.backend.filter(
          (item): item is string => typeof item === "string" && item.length > 0
        )
      } else if (typeof entry?.backend === "string" && entry.backend.length > 0) {
        backend = [entry.backend]
      }
      if (backend.length === 0) backend = [...fallback.backend]
      const long =
        typeof entry?.long === "string" && entry.long.length > 0 ? entry.long : fallback.long
      const short =
        typeof entry?.short === "string" && entry.short.length > 0 ? entry.short : fallback.short
      return { id, backend, long, short }
    }
    for (const id of baseOrder) {
      seen.add(id)
      configs.push(toConfig(id, items[id]))
    }
    for (const [id, value] of Object.entries(items)) {
      if (seen.has(id)) continue
      configs.push(toConfig(id, value))
    }
    if (configs.length === 0) return [...minimalWeekdayFallback]
    return configs
  }, [t])
  const weekdayBackend = useMemo(
    () => weekdayConfigs.map((config) => config.backend[0] ?? config.id),
    [weekdayConfigs]
  )
  const weekdayLabels = useMemo(() => weekdayConfigs.map((config) => config.long), [weekdayConfigs])
  const weekdayShort = useMemo(() => weekdayConfigs.map((config) => config.short), [weekdayConfigs])
  const weekdayLabelMap = useMemo(() => {
    const map = new Map<string, string>()
    for (const config of weekdayConfigs) {
      map.set(config.id, config.long)
      for (const backend of config.backend) {
        map.set(backend, config.long)
      }
    }
    return map
  }, [weekdayConfigs])
  const getDayLabel = useCallback(
    (value: string) => weekdayLabelMap.get(value) ?? value,
    [weekdayLabelMap]
  )
  const weekdayCanonicalMap = useMemo(() => {
    const map = new Map<string, string>()
    for (const config of weekdayConfigs) {
      const primary = config.backend[0] ?? config.id
      map.set(config.id, primary)
      for (const backend of config.backend) {
        map.set(backend, primary)
      }
    }
    return map
  }, [weekdayConfigs])
  const normalizeLessons = useCallback(
    (lessons: Lesson[]) => {
      let changed = false
      const normalized = lessons.map((lesson) => {
        if (!lesson || typeof lesson.weekday !== "string") return lesson
        const canonical = weekdayCanonicalMap.get(lesson.weekday)
        if (!canonical || canonical === lesson.weekday) return lesson
        changed = true
        return { ...lesson, weekday: canonical }
      })
      return changed ? normalized : lessons
    },
    [weekdayCanonicalMap]
  )
  const lessonTypeConfigs = useMemo(() => {
    const rawItems = t("schedule:lessonTypes.items", { returnObjects: true }) as unknown
    const rawOrder = t("schedule:lessonTypes.order", { returnObjects: true }) as unknown
    const items =
      rawItems && typeof rawItems === "object" && !Array.isArray(rawItems)
        ? (rawItems as Record<string, unknown>)
        : {}
    const baseOrder =
      Array.isArray(rawOrder) && rawOrder.length > 0
        ? rawOrder.filter((id): id is string => typeof id === "string" && id.length > 0)
        : (Object.keys(items) as string[])
    const configs: LessonTypeConfig[] = []
    const seen = new Set<string>()
    const toConfig = (id: string, value?: unknown): LessonTypeConfig => {
      const fallback = {
        id,
        backend: [id],
        label: id,
        color: defaultLessonTypeColor,
      }
      const entry =
        value && typeof value === "object" && !Array.isArray(value)
          ? (value as Record<string, unknown>)
          : undefined
      let backend: string[] = []
      if (Array.isArray(entry?.backend)) {
        backend = entry.backend.filter(
          (item): item is string => typeof item === "string" && item.length > 0
        )
      } else if (typeof entry?.backend === "string" && entry.backend.length > 0) {
        backend = [entry.backend]
      }
      if (backend.length === 0) backend = [...fallback.backend]
      const label =
        typeof entry?.label === "string" && entry.label.length > 0 ? entry.label : fallback.label
      const color =
        typeof entry?.color === "string" && entry.color.length > 0 ? entry.color : fallback.color
      return { id, backend, label, color }
    }
    for (const id of baseOrder) {
      seen.add(id)
      configs.push(toConfig(id, items[id]))
    }
    for (const [id, value] of Object.entries(items)) {
      if (seen.has(id)) continue
      configs.push(toConfig(id, value))
    }
    if (configs.length === 0) return [minimalLessonTypeFallback]
    return configs
  }, [t])
  const lessonTypeById = useMemo(
    () => new Map(lessonTypeConfigs.map((config) => [config.id, config])),
    [lessonTypeConfigs]
  )
  const lessonTypeByBackend = useMemo(() => {
    const map = new Map<string, LessonTypeConfig>()
    for (const config of lessonTypeConfigs) {
      for (const backend of config.backend) {
        map.set(backend, config)
      }
    }
    return map
  }, [lessonTypeConfigs])
  const lessonTypeLabels = useMemo(() => {
    const map = new Map<string, string>()
    for (const config of lessonTypeConfigs) {
      map.set(config.id, config.label)
      for (const backend of config.backend) {
        map.set(backend, config.label)
      }
    }
    return map
  }, [lessonTypeConfigs])
  const lessonTypeOptions = useMemo(
    () => lessonTypeConfigs.map((config) => ({ value: config.id, label: config.label })),
    [lessonTypeConfigs]
  )
  const defaultLessonType = lessonTypeOptions[0]?.value ?? minimalLessonTypeFallback.id ?? ""
  const getLessonTypeColor = useCallback(
    (value?: string | null) => {
      if (!value) return defaultLessonTypeColor
      const match = lessonTypeById.get(value) ?? lessonTypeByBackend.get(value)
      return match?.color ?? defaultLessonTypeColor
    },
    [lessonTypeByBackend, lessonTypeById]
  )
  const resolveLessonTypeId = useCallback(
    (value?: string | null) => {
      if (!value) return defaultLessonType
      if (lessonTypeById.has(value)) return value
      const match = lessonTypeByBackend.get(value)
      return match ? match.id : value
    },
    [defaultLessonType, lessonTypeByBackend, lessonTypeById]
  )
  const toBackendLessonType = useCallback(
    (value?: string | null) => {
      if (!value) return ""
      const match = lessonTypeById.get(value)
      if (match) return match.backend[0] ?? value
      return value
    },
    [lessonTypeById]
  )
  const formatDuration = useCallback(
    (hours: number, minutes: number) => {
      const parts: string[] = []
      if (hours > 0) {
        parts.push(t("schedule:time.hours", { count: hours }))
      }
      if (minutes > 0 || hours === 0) {
        parts.push(t("schedule:time.minutes", { count: minutes }))
      }
      return parts.join(" ")
    },
    [t]
  )
  const [selectedGroup, setSelectedGroup] = useState<number | null>(null)
  const [currentParity, setCurrentParity] = useState<"odd" | "even">("odd")
  const [snack, setSnack] = useState("")
  const [openDialog, setOpenDialog] = useState(false)
  const [dialogLesson, setDialogLesson] = useState<Lesson | null>(null)
  const [editing, setEditing] = useState(false)
  const [editLesson, setEditLesson] = useState<Lesson | null>(null)
  const [addDialogOpen, setAddDialogOpen] = useState(false)
  const [addDay, setAddDay] = useState<string>("")
  const [addFields, setAddFields] = useState<AddLessonFields>({
    subject: "",
    teacher: "",
    room: "",
    lessonType: defaultLessonType,
    startTime: "",
    endTime: "",
    parity: "both",
  })
  useEffect(() => {
    if (!defaultLessonType) return
    setAddFields((prev) => {
      if (lessonTypeOptions.some((option) => option.value === prev.lessonType)) return prev
      return { ...prev, lessonType: defaultLessonType }
    })
  }, [lessonTypeOptions, defaultLessonType])
  const editingLessonTypeOptions = useMemo(() => {
    if (!editLesson?.lesson_type) return lessonTypeOptions
    if (lessonTypeOptions.some((option) => option.value === editLesson.lesson_type))
      return lessonTypeOptions
    return [
      ...lessonTypeOptions,
      {
        value: editLesson.lesson_type,
        label: lessonTypeLabels.get(editLesson.lesson_type) ?? editLesson.lesson_type,
      },
    ]
  }, [editLesson?.lesson_type, lessonTypeLabels, lessonTypeOptions])
  const addDayLabel = addDay ? getDayLabel(addDay) : ""
  const isMobile = useMediaQuery("(max-width:1730px)")
  const tableScrollRef = useRef<HTMLDivElement | null>(null)
  const headRefs = useRef<(HTMLTableCellElement | null)[]>([])
  const dayCardRefs = useRef<(HTMLDivElement | null)[]>([])
  if (headRefs.current.length !== weekdayBackend.length)
    headRefs.current = Array(weekdayBackend.length).fill(null)
  if (dayCardRefs.current.length !== weekdayBackend.length)
    dayCardRefs.current = Array(weekdayBackend.length).fill(null)
  const mainAlignSx = { ml: { xs: 0, sm: 2, md: 3, lg: 6 }, mr: { xs: 0, sm: 2, md: 3, lg: 6 } }
  const todayIdx = getTodayIdx()
  const hasToday = todayIdx >= 0 && todayIdx < weekdayBackend.length
  const [nowTick, setNowTick] = useState(dayjs())
  useEffect(() => {
    const id = setInterval(() => setNowTick(dayjs()), 30000)
    return () => clearInterval(id)
  }, [])
  const minutesNow = useMemo(() => nowTick.hour() * 60 + nowTick.minute(), [nowTick])

  const groupsQuery = useQuery<ScheduleGroup[], Error, ScheduleGroup[], ScheduleGroupsQueryKey>({
    queryKey: scheduleGroupsQueryKey,
    queryFn: async () => {
      const res = await api.get("/groups")
      return Array.isArray(res.data) ? res.data : []
    },
    enabled: Boolean(user),
    placeholderData: groupsPlaceholder,
    staleTime: 60_000,
    gcTime: 5 * 60_000,
    networkMode: "online",
    retry: 1,
  })
  const groups = groupsQuery.data ?? []

  useEffect(() => {
    if (!groupsQuery.isSuccess) return
    writeToStorage(groupsStorageKey, groupsQuery.data)
  }, [groupsQuery.data, groupsQuery.isSuccess])

  const activeGroupId = selectedGroup
  const scheduleKey = activeGroupId != null ? scheduleQueryKey(activeGroupId) : null

  const scheduleQuery = useQuery<
    Lesson[],
    Error,
    Lesson[],
    ActiveScheduleQueryKey | InactiveScheduleQueryKey
  >({
    queryKey: (scheduleKey ?? ["schedule", "group", "none"]) as
      | ActiveScheduleQueryKey
      | InactiveScheduleQueryKey,
    queryFn: async () => {
      if (activeGroupId == null) return []
      const res = await api.get(`/schedule/${activeGroupId}`)
      return Array.isArray(res.data) ? res.data : []
    },
    enabled: activeGroupId != null,
    placeholderData: (previous) => schedulePlaceholder(activeGroupId, previous),
    staleTime: 60_000,
    gcTime: 5 * 60_000,
    networkMode: "online",
    retry: 1,
  })
  const groupScheduleRaw = scheduleQuery.data ?? []
  const groupSchedule = useMemo(
    () => normalizeLessons(groupScheduleRaw),
    [groupScheduleRaw, normalizeLessons]
  )

  useEffect(() => {
    if (!scheduleQuery.isSuccess) return
    if (activeGroupId == null) return
    writeToStorage(scheduleStorageKey(activeGroupId), groupSchedule)
  }, [scheduleQuery.isSuccess, activeGroupId, groupSchedule])

  const applyScheduleUpdate = (updater: (prev: Lesson[]) => Lesson[]) => {
    if (!scheduleKey || activeGroupId == null) return
    queryClient.setQueryData<Lesson[]>(scheduleKey, (prev) => {
      const base = Array.isArray(prev) ? [...prev] : []
      const next = normalizeLessons(updater(base))
      writeToStorage(scheduleStorageKey(activeGroupId), next)
      return next
    })
  }

  useEffect(() => {
    if (!user) return
    if (user.role === "student" && user.group_id) {
      setSelectedGroup((prev) => prev ?? user.group_id ?? null)
    }
  }, [user])

  useEffect(() => {
    if (!user) return
    if ((user.role === "teacher" || user.role === "admin") && groups.length > 0) {
      setSelectedGroup((prev) => prev ?? groups[0]?.id ?? null)
    }
  }, [user, groups])

  const filteredSchedule = useMemo(
    () => groupSchedule.filter((l) => l.parity === "both" || l.parity === currentParity),
    [groupSchedule, currentParity]
  )

  const todayLessons = useMemo(() => {
    if (!hasToday) return []
    const today = weekdayBackend.at(todayIdx)
    if (!today) return []
    return filteredSchedule
      .filter((l) => l.weekday === today)
      .sort((a, b) => getTimeStr(a).localeCompare(getTimeStr(b)))
  }, [filteredSchedule, hasToday, todayIdx])

  const currentLesson = useMemo(() => {
    if (!hasToday) return null
    return (
      todayLessons.find((l) => {
        const s = parseMinutes(l.start_time) ?? -1
        const e = parseMinutes(l.end_time) ?? -1
        return minutesNow >= s && minutesNow < e
      }) || null
    )
  }, [todayLessons, minutesNow, hasToday])

  const nextLesson = useMemo(() => {
    if (!hasToday) return null
    if (currentLesson) {
      const endM = parseMinutes(currentLesson.end_time) ?? 0
      return todayLessons.find((l) => (parseMinutes(l.start_time) ?? 0) > endM) || null
    }
    return todayLessons.find((l) => (parseMinutes(l.start_time) ?? 0) > minutesNow) || null
  }, [todayLessons, currentLesson, minutesNow, hasToday])

  const [timeLeftText, setTimeLeftText] = useState<string>("")
  useEffect(() => {
    const calc = () => {
      if (currentLesson) {
        const end = parseMinutes(currentLesson.end_time) ?? 0
        const left = Math.max(0, end - (dayjs().hour() * 60 + dayjs().minute()))
        const h = Math.floor(left / 60)
        const m = left % 60
        setTimeLeftText(t("schedule:timeLeft.current", { duration: formatDuration(h, m) }))
      } else if (nextLesson) {
        const start = parseMinutes(nextLesson.start_time) ?? 0
        const left = Math.max(0, start - (dayjs().hour() * 60 + dayjs().minute()))
        const h = Math.floor(left / 60)
        const m = left % 60
        setTimeLeftText(t("schedule:timeLeft.next", { duration: formatDuration(h, m) }))
      } else {
        setTimeLeftText("")
      }
    }
    calc()
    const id = setInterval(calc, 30000)
    return () => clearInterval(id)
  }, [currentLesson, nextLesson, t, formatDuration])

  const currentProgress = useMemo(() => {
    if (!currentLesson) return 0
    const s = parseMinutes(currentLesson.start_time)
    const e = parseMinutes(currentLesson.end_time)
    if (s == null || e == null || e <= s) return 0
    const span = e - s
    const passed = Math.min(Math.max(minutesNow - s, 0), span)
    return Math.round((passed / span) * 100)
  }, [currentLesson, minutesNow])

  const tableRowsBase = useMemo(
    () => buildTable(filteredSchedule, weekdayBackend),
    [filteredSchedule, weekdayBackend]
  )
  const tableRows = useDeferredValue(tableRowsBase)
  const [rowLimit, setRowLimit] = useState(0)
  useEffect(() => {
    setRowLimit((prev) => {
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
        setRowLimit((prev) => {
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
    return () => {
      cancelled = true
    }
  }, [tableRows, rowLimit])

  useEffect(() => {
    if (isMobile || !hasToday) return
    const container = tableScrollRef.current
    const cell = todayIdx >= 0 ? headRefs.current[todayIdx] : null
    if (container && cell) {
      const left = cell.offsetLeft - 120
      container.scrollTo({ left, behavior: "smooth" })
    }
  }, [rowLimit, isMobile, todayIdx, hasToday])

  const todayLabel = useMemo(() => {
    const formatter = new Intl.DateTimeFormat(locale, {
      weekday: "long",
      day: "2-digit",
      month: "short",
    })
    const parts = formatter.formatToParts(new Date())
    const dayPart = parts.find((part) => part.type === "day")?.value ?? ""
    const monthPart = parts.find((part) => part.type === "month")?.value ?? ""
    const weekdayPart = parts.find((part) => part.type === "weekday")?.value ?? ""
    const datePart = [dayPart, monthPart].filter(Boolean).join(" ")
    return `${datePart}${weekdayPart ? `, ${weekdayPart}` : ""}`
  }, [locale])
  const activeGroupName = groups.find((g) => g.id === selectedGroup)?.name || ""

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
          const s1 = parseMinutes(arr[i].start_time),
            e1 = parseMinutes(arr[i].end_time)
          const s2 = parseMinutes(arr[j].start_time),
            e2 = parseMinutes(arr[j].end_time)
          if (s1 == null || e1 == null || s2 == null || e2 == null) continue
          const overlap = Math.max(s1, s2) < Math.min(e1, e2)
          if (overlap) {
            set.add(arr[i].id)
            set.add(arr[j].id)
          }
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
    whiteSpace: "nowrap",
  } as const

  const badgeGhost = {
    ...badgeBase,
    background: "var(--btn-bg)",
    color: "var(--nav-text)",
    border: "1px solid var(--btn-border)",
  } as const

  const headerCardSx = {
    borderRadius: 4,
    p: 2,
    background: "var(--card-bg)",
    boxShadow: "0 12px 36px #00000012, 0 4px 14px #0000000a",
    border: "1px solid var(--btn-border)",
  }

  const headerActions = (
    <Stack direction="row" spacing={2} alignItems="center" mb={2.5} flexWrap="wrap">
      <Typography component="span">{t("schedule:week.label")}</Typography>
      <Button
        variant={currentParity === "odd" ? "contained" : "outlined"}
        onClick={() => setCurrentParity("odd")}
      >
        {t("schedule:week.odd")}
      </Button>
      <Button
        variant={currentParity === "even" ? "contained" : "outlined"}
        onClick={() => setCurrentParity("even")}
      >
        {t("schedule:week.even")}
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
          zIndex: 3,
        }}
      >
        <Chip size="small" label={t("schedule:break", { minutes: gap })} className="chip-break" />
      </Box>
    )
  }

  const lessonCardHeight = 148

  const LessonCellCard = ({
    lesson,
    isConflict,
    onDelete,
    onOpen,
    hasBreakBefore,
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
        "&:hover": {
          transform: "translateY(-1px)",
          boxShadow: "0 10px 28px #0000001f, 0 2px 10px #0003",
        },
      }}
      title={isConflict ? t("schedule:lesson.conflict") : undefined}
    >
      <Box
        sx={{
          position: "absolute",
          left: -1,
          top: -1,
          bottom: -1,
          width: 6,
          borderTopLeftRadius: 8,
          borderBottomLeftRadius: 8,
          background: getLessonTypeColor(lesson.lesson_type),
        }}
      />
      <Stack spacing={0.6}>
        <Stack direction="row" alignItems="center" justifyContent="space-between">
          <Chip
            size="small"
            label={lessonTypeLabels.get(lesson.lesson_type ?? "") ?? lesson.lesson_type ?? ""}
            sx={{
              height: 22,
              fontWeight: 700,
              color: "#fff",
              background: getLessonTypeColor(lesson.lesson_type),
            }}
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
            overflow: "hidden",
          }}
        >
          {lesson.subject}
        </Typography>
        <Stack direction="row" gap={1} flexWrap="wrap">
          <Chip
            size="small"
            variant="outlined"
            icon={<SchoolIcon sx={{ fontSize: 16 }} />}
            label={lesson.teacher}
            sx={{ borderColor: "var(--btn-border)", color: "var(--page-text)" }}
          />
          <Chip
            size="small"
            variant="outlined"
            icon={<RoomIcon sx={{ fontSize: 16 }} />}
            label={lesson.room}
            sx={{ borderColor: "var(--btn-border)", color: "var(--page-text)" }}
          />
        </Stack>
      </Stack>
      <Tooltip title={t("schedule:lesson.details")}>
        <InfoOutlinedIcon
          sx={{
            position: "absolute",
            right: 8,
            bottom: 8,
            fontSize: 18,
            color: "var(--secondary-text)",
          }}
        />
      </Tooltip>
      {(user?.role === "admin" || user?.role === "teacher") && (
        <IconButton
          aria-label={t("schedule:aria.deleteLesson")}
          size="small"
          sx={{ position: "absolute", top: 6, right: 6, bgcolor: "var(--card-bg)", zIndex: 2 }}
          onClick={(e) => {
            e.stopPropagation()
            onDelete()
          }}
        >
          <DeleteIcon fontSize="small" color="error" />
        </IconButton>
      )}
      {isConflict && (
        <Box
          sx={{
            position: "absolute",
            inset: 0,
            borderRadius: 2,
            boxShadow: "0 0 0 3px #ef535033 inset",
            pointerEvents: "none",
          }}
        />
      )}
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
          containIntrinsicSize: "600px",
        }}
      >
        <Table stickyHeader>
          <TableHead>
            <TableRow>
              <TableCell
                align="center"
                sx={{
                  fontWeight: 700,
                  width: 45,
                  background: "var(--table-header-bg)",
                  zIndex: 10,
                  position: "sticky",
                  left: 0,
                  color: "var(--page-text)",
                  fontSize: "clamp(0.98rem,1.7vw,1.13rem)",
                }}
              >
                №
              </TableCell>
              {weekdayBackend.map((day, idx) => {
                const label = weekdayLabels[idx] ?? day
                return (
                  <TableCell
                    align="center"
                    key={day}
                    ref={(el: HTMLTableCellElement | null) => {
                      headRefs.current[idx] = el
                    }}
                    sx={{
                      fontWeight: 700,
                      background:
                        hasToday && idx === todayIdx
                          ? "var(--table-row-today)"
                          : "var(--table-header-bg)",
                      fontSize: "clamp(0.97rem, 1.4vw, 1.11rem)",
                      zIndex: 5,
                      color: "var(--page-text)",
                      position: "relative",
                      borderLeft: hasToday && idx === todayIdx ? "2px solid #2563eb55" : undefined,
                      borderRight: hasToday && idx === todayIdx ? "2px solid #2563eb55" : undefined,
                    }}
                  >
                    <Box display="flex" alignItems="center" justifyContent="center" gap={0.5}>
                      {label}
                      {(user?.role === "admin" || user?.role === "teacher") && (
                        <IconButton
                          size="small"
                          onClick={(e) => {
                            e.stopPropagation()
                            setAddDay(day)
                            setAddDialogOpen(true)
                          }}
                          sx={{
                            ml: 1,
                            border: "1px solid var(--btn-border)",
                            bgcolor: "var(--card-bg)",
                            "&:hover": { bgcolor: "var(--option-bg)" },
                            height: 26,
                            width: 26,
                          }}
                          aria-label={t("schedule:aria.addLesson", { day: label })}
                        >
                          <AddIcon fontSize="small" />
                        </IconButton>
                      )}
                    </Box>
                  </TableCell>
                )
              })}
            </TableRow>
          </TableHead>
          <TableBody sx={{ contentVisibility: "auto" }}>
            {visibleRows.length === 0 ? (
              <TableRow>
                <TableCell align="center" colSpan={weekdayBackend.length + 1}>
                  {t("schedule:table.noLessons")}
                </TableCell>
              </TableRow>
            ) : (
              visibleRows.map((row, rowIdx) => (
                <TableRow key={rowIdx} sx={{ "&:hover": { background: "var(--table-row-hover)" } }}>
                  <TableCell
                    align="center"
                    sx={{
                      fontWeight: 700,
                      background: "var(--table-header-bg)",
                      position: "sticky",
                      left: 0,
                      color: "var(--page-text)",
                      fontSize: "clamp(0.98rem,1.7vw,1.13rem)",
                    }}
                  >
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
                            p: 1.2,
                          }}
                        >
                          <Box
                            sx={{
                              minHeight: lessonCardHeight,
                              borderRadius: 2,
                              border: "1px dashed var(--glass-border)",
                              bgcolor: "transparent",
                            }}
                          />
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
                          p: 1.2,
                        }}
                      >
                        {renderBreakChip(rowIdx, colIdx)}
                        <LessonCellCard
                          lesson={lesson}
                          isConflict={isConflict}
                          hasBreakBefore={hasBreakBefore}
                          onOpen={() => {
                            setDialogLesson(lesson)
                            setOpenDialog(true)
                          }}
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
      {weekdayBackend.map((day, i) => (
        <Chip
          key={day}
          clickable
          className="chip-day"
          color={hasToday && i === todayIdx ? "primary" : "default"}
          label={weekdayShort[i] ?? getDayLabel(day)}
          onClick={() =>
            dayCardRefs.current[i]?.scrollIntoView({ behavior: "smooth", block: "start" })
          }
          sx={{ flex: "0 0 auto" }}
        />
      ))}
    </Stack>
  )

  const renderMobileCards = () => (
    <Stack spacing={2} sx={{ width: "100%", mt: 1 }}>
      {renderMobileDayAnchors()}
      {weekdayBackend.map((day, dayIdx) => {
        const label = weekdayLabels[dayIdx] ?? day
        const lessons = filteredSchedule
          .filter((l) => l.weekday === day)
          .sort((a, b) => getTimeStr(a).localeCompare(getTimeStr(b)))
        return (
          <Paper
            key={day}
            ref={(el: HTMLDivElement | null) => {
              dayCardRefs.current[dayIdx] = el
            }}
            elevation={4}
            sx={{
              borderRadius: 3,
              p: 2,
              mb: 1,
              bgcolor:
                hasToday && dayIdx === todayIdx ? "var(--table-row-today)" : "var(--card-bg)",
              border: "1px solid var(--btn-border)",
              boxShadow: "0 10px 30px #00000014, 0 3px 12px #0000000a",
              contentVisibility: "auto",
              containIntrinsicSize: "400px",
            }}
          >
            <Box display="flex" alignItems="center" mb={1} gap={1}>
              <Typography fontWeight={800} fontSize="1.12rem">
                {label}
              </Typography>
              {(user?.role === "admin" || user?.role === "teacher") && (
                <IconButton
                  size="small"
                  onClick={(e) => {
                    e.stopPropagation()
                    setAddDay(day)
                    setAddDialogOpen(true)
                  }}
                  sx={{
                    ml: 0.5,
                    border: "1px solid var(--btn-border)",
                    bgcolor: "var(--card-bg)",
                    "&:hover": { bgcolor: "var(--option-bg)" },
                    height: 26,
                    width: 26,
                  }}
                  aria-label={t("schedule:aria.addLesson", { day: label })}
                >
                  <AddIcon fontSize="small" />
                </IconButton>
              )}
            </Box>
            {lessons.length === 0 ? (
              <Typography sx={{ color: "var(--secondary-text)" }}>
                {t("schedule:mobile.noLessons")}
              </Typography>
            ) : (
              <Stack spacing={1}>
                {lessons.map((lesson, idx) => {
                  const prev = lessons[idx - 1]
                  const gap = prev ? minutesDiff(prev.end_time, lesson.start_time) : 0
                  return (
                    <Box key={lesson.id}>
                      {idx > 0 && gap > 0 && (
                        <Chip
                          size="small"
                          label={t("schedule:break", { minutes: gap })}
                          className="chip-break"
                          sx={{ mb: 0.8 }}
                        />
                      )}
                      <Box
                        onClick={() => {
                          setDialogLesson(lesson)
                          setOpenDialog(true)
                        }}
                        sx={{
                          p: 1.3,
                          borderRadius: 2,
                          background: "var(--option-bg)",
                          boxShadow: "var(--option-shadow)",
                          border: "1px solid var(--btn-border)",
                          cursor: "pointer",
                          transition: "transform .2s, box-shadow .2s",
                          "&:hover": {
                            background: "var(--option-hover-bg)",
                            transform: "translateY(-1px)",
                            boxShadow: "0 8px 26px #2175ee20, 0 1.5px 8px #0002",
                          },
                          position: "relative",
                        }}
                      >
                        <Box
                          sx={{
                            position: "absolute",
                            left: 0,
                            top: 0,
                            bottom: 0,
                            width: 6,
                            borderTopLeftRadius: 8,
                            borderBottomLeftRadius: 8,
                            background: getLessonTypeColor(lesson.lesson_type),
                          }}
                        />
                        <Stack
                          direction="row"
                          gap={1}
                          alignItems="center"
                          flexWrap="wrap"
                          sx={{ pl: 1 }}
                        >
                          <Chip
                            size="small"
                            label={
                              lessonTypeLabels.get(lesson.lesson_type ?? "") ??
                              lesson.lesson_type ??
                              ""
                            }
                            className="chip-type"
                            sx={{
                              background: getLessonTypeColor(lesson.lesson_type),
                              color: "#fff",
                              height: 24,
                              fontWeight: 700,
                            }}
                          />
                          <Chip
                            size="small"
                            className="chip-time"
                            icon={<AccessTimeIcon sx={{ fontSize: 16 }} />}
                            label={`${getTimeStr(lesson)}–${getEndTimeStr(lesson)}`}
                          />
                        </Stack>
                        <Typography
                          fontWeight={700}
                          fontSize="1.02rem"
                          sx={{
                            color: "var(--page-text)",
                            pl: 1,
                            mt: 0.5,
                            display: "-webkit-box",
                            WebkitLineClamp: 2,
                            WebkitBoxOrient: "vertical",
                            overflow: "hidden",
                          }}
                        >
                          {lesson.subject}
                        </Typography>
                        <Stack direction="row" gap={1} flexWrap="wrap" sx={{ pl: 1, mt: 0.4 }}>
                          <Chip
                            size="small"
                            variant="outlined"
                            icon={<SchoolIcon sx={{ fontSize: 16 }} />}
                            label={lesson.teacher}
                          />
                          <Chip
                            size="small"
                            variant="outlined"
                            icon={<RoomIcon sx={{ fontSize: 16 }} />}
                            label={lesson.room}
                          />
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
          {t("common:statuses.loading")}
        </Box>
      </Layout>
    )

  return (
    <Layout>
      <PageFadeIn>
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
        <Box
          sx={{
            width: "100vw",
            minHeight: "100vh",
            bgcolor: "var(--page-bg)",
            color: "var(--page-text)",
            py: { xs: 3.5, sm: 3.5, md: 3.5, lg: 3.5 },
          }}
        >
          <Box
            sx={{
              ...mainAlignSx,
              ml: { xs: 2, sm: 4, md: 5, lg: 8 },
              mr: { xs: 2, sm: 4, md: 5, lg: 8 },
              maxWidth: 980,
              mb: 2,
              mt: 0,
            }}
          >
            <Stack
              data-fade
              style={{ "--fade-delay": "80ms" } as CSSProperties}
              direction="row"
              alignItems="center"
              flexWrap="wrap"
              gap={1.3}
              mb={2.2}
              mt={0.5}
            >
              <CalendarMonthIcon color="primary" sx={{ fontSize: 34 }} />
              <Typography
                variant="h4"
                fontWeight={700}
                color="primary.main"
                sx={{ fontSize: "clamp(0.8rem, 5vw, 2.7rem)" }}
              >
                {user?.role === "student"
                  ? t("schedule:title.student")
                  : t("schedule:title.default")}
              </Typography>
              <Box sx={{ ...badgeGhost, transform: "translateY(8px)" }}>{todayLabel}</Box>
              {activeGroupName && (
                <Box sx={{ ...badgeGhost, transform: "translateY(8px)" }}>
                  {t("schedule:header.groupName", { name: activeGroupName })}
                </Box>
              )}
            </Stack>

            <Stack
              data-fade
              style={{ "--fade-delay": "140ms" } as CSSProperties}
              direction="row"
              alignItems="center"
              flexWrap="wrap"
              gap={1}
              mb={2}
            >
              {headerActions}
            </Stack>

            <Box
              data-fade
              style={{ "--fade-delay": "200ms" } as CSSProperties}
              className="no-print"
              sx={{ ...headerCardSx, mb: 2 }}
            >
              {currentLesson ? (
                <Box>
                  <Stack direction="row" alignItems="center" gap={1} flexWrap="wrap">
                    <Chip size="small" className="chip-clock" label={t("schedule:chips.current")} />
                    <Chip
                      size="small"
                      className="chip-time"
                      label={`${getTimeStr(currentLesson)}–${getEndTimeStr(currentLesson)}`}
                    />
                    <Typography sx={{ fontWeight: 800 }}>{currentLesson.subject}</Typography>
                    {!!timeLeftText && (
                      <Chip size="small" className="chip-left" label={timeLeftText} />
                    )}
                  </Stack>
                  <Stack direction="row" gap={1} mt={1} flexWrap="wrap">
                    <Chip
                      size="small"
                      variant="outlined"
                      icon={<SchoolIcon sx={{ fontSize: 16 }} />}
                      label={currentLesson.teacher}
                    />
                    <Chip
                      size="small"
                      variant="outlined"
                      icon={<RoomIcon sx={{ fontSize: 16 }} />}
                      label={currentLesson.room}
                    />
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
                        transition: "transform 0.4s linear",
                      },
                    }}
                    aria-label={t("schedule:aria.currentProgress")}
                  />
                </Box>
              ) : nextLesson ? (
                <Stack direction="row" alignItems="center" gap={1} flexWrap="wrap">
                  <Chip size="small" className="chip-clock" label={t("schedule:chips.next")} />
                  <Chip
                    size="small"
                    className="chip-time"
                    label={`${getTimeStr(nextLesson)}–${getEndTimeStr(nextLesson)}`}
                  />
                  <Typography sx={{ fontWeight: 800 }}>{nextLesson.subject}</Typography>
                  {!!timeLeftText && (
                    <Chip size="small" className="chip-left" label={timeLeftText} />
                  )}
                </Stack>
              ) : (
                <Typography sx={{ color: "var(--secondary-text)" }}>
                  {t("schedule:summary.noMoreToday")}
                </Typography>
              )}
            </Box>

            {(user?.role === "teacher" || user?.role === "admin") && (
              <FormControl
                data-fade
                style={{ "--fade-delay": "240ms" } as CSSProperties}
                fullWidth
                sx={{ mb: 2, maxWidth: 340 }}
              >
                <InputLabel>{t("schedule:form.groupLabel")}</InputLabel>
                <Select
                  value={selectedGroup ?? ""}
                  label={t("schedule:form.groupLabel")}
                  onChange={(e) => setSelectedGroup(Number(e.target.value))}
                >
                  {groups.map((g) => (
                    <MenuItem value={g.id} key={g.id}>
                      {g.name}
                    </MenuItem>
                  ))}
                </Select>
              </FormControl>
            )}
          </Box>

          <Box
            data-fade
            style={{ "--fade-delay": "280ms" } as CSSProperties}
            sx={{ ...mainAlignSx, maxWidth: 1920, px: { xs: 1, md: 2 } }}
          >
            {isMobile ? renderMobileCards() : renderTable()}
          </Box>

          <Dialog open={openDialog} onClose={() => setOpenDialog(false)}>
            <DialogTitle>
              {dialogLesson?.subject || t("schedule:dialog.detailsFallback")}
            </DialogTitle>
            <DialogContent>
              {dialogLesson && (
                <Box>
                  <Box mb={1}>
                    <b>{t("schedule:dialog.typeLabel")}:</b>{" "}
                    <span
                      style={{
                        color: "#fff",
                        background: getLessonTypeColor(dialogLesson.lesson_type),
                        borderRadius: 5,
                        padding: "2px 8px",
                      }}
                    >
                      {lessonTypeLabels.get(dialogLesson.lesson_type ?? "") ??
                        dialogLesson.lesson_type ??
                        ""}
                    </span>
                  </Box>
                  <Box>
                    <b>{t("schedule:dialog.timeLabel")}:</b> {getTimeStr(dialogLesson)}–
                    {getEndTimeStr(dialogLesson)}
                  </Box>
                  <Box>
                    <b>{t("schedule:dialog.teacherLabel")}:</b> {dialogLesson.teacher}
                  </Box>
                  <Box>
                    <b>{t("schedule:dialog.roomLabel")}:</b> {dialogLesson.room}
                  </Box>
                  <Stack direction="row" gap={1.2} mt={2}>
                    {(user?.role === "admin" || user?.role === "teacher") && (
                      <Button
                        variant="outlined"
                        onClick={() => {
                          if (!dialogLesson) return
                          setEditing(true)
                          setEditLesson({
                            ...dialogLesson,
                            lesson_type: resolveLessonTypeId(dialogLesson.lesson_type),
                          })
                        }}
                      >
                        {t("schedule:buttons.edit")}
                      </Button>
                    )}
                    <Button
                      variant="outlined"
                      color="secondary"
                      onClick={() => setOpenDialog(false)}
                    >
                      {t("schedule:buttons.close")}
                    </Button>
                  </Stack>
                </Box>
              )}
            </DialogContent>
          </Dialog>

          <Dialog open={editing} onClose={() => setEditing(false)}>
            <DialogTitle>{t("schedule:dialog.editTitle")}</DialogTitle>
            <DialogContent>
              {editLesson && (
                <Stack spacing={2} mt={1}>
                  <TextField
                    label={t("schedule:form.subject")}
                    value={editLesson.subject}
                    onChange={(e) => setEditLesson({ ...editLesson, subject: e.target.value })}
                  />
                  <TextField
                    label={t("schedule:form.teacher")}
                    value={editLesson.teacher}
                    onChange={(e) => setEditLesson({ ...editLesson, teacher: e.target.value })}
                  />
                  <TextField
                    label={t("schedule:form.room")}
                    value={editLesson.room}
                    onChange={(e) => setEditLesson({ ...editLesson, room: e.target.value })}
                  />
                  <TextField
                    select
                    label={t("schedule:form.lessonType")}
                    value={editLesson.lesson_type}
                    onChange={(e) => setEditLesson({ ...editLesson, lesson_type: e.target.value })}
                  >
                    {editingLessonTypeOptions.map((option) => (
                      <MenuItem value={option.value} key={option.value}>
                        {option.label}
                      </MenuItem>
                    ))}
                  </TextField>
                  <TextField
                    select
                    label={t("schedule:form.day")}
                    value={editLesson.weekday}
                    onChange={(e) => setEditLesson({ ...editLesson, weekday: e.target.value })}
                  >
                    {weekdayBackend.map((day) => (
                      <MenuItem key={day} value={day}>
                        {getDayLabel(day)}
                      </MenuItem>
                    ))}
                  </TextField>
                  <TextField
                    type="time"
                    label={t("schedule:form.startTime")}
                    value={getTimeStr(editLesson)}
                    onChange={(e) =>
                      setEditLesson({
                        ...editLesson,
                        start_time: `${editLesson.start_time?.slice(0, 11) || dayjs().format("YYYY-MM-DDT")}${e.target.value}:00`,
                      })
                    }
                  />
                  <TextField
                    type="time"
                    label={t("schedule:form.endTime")}
                    value={getEndTimeStr(editLesson)}
                    onChange={(e) =>
                      setEditLesson({
                        ...editLesson,
                        end_time: `${editLesson.end_time?.slice(0, 11) || dayjs().format("YYYY-MM-DDT")}${e.target.value}:00`,
                      })
                    }
                  />
                  <TextField
                    select
                    label={t("schedule:form.week")}
                    value={editLesson.parity}
                    onChange={(e) =>
                      setEditLesson((prev) =>
                        prev ? { ...prev, parity: e.target.value as LessonParity } : prev
                      )
                    }
                  >
                    <MenuItem value="both">{t("schedule:week.both")}</MenuItem>
                    <MenuItem value="odd">{t("schedule:week.odd")}</MenuItem>
                    <MenuItem value="even">{t("schedule:week.even")}</MenuItem>
                  </TextField>
                  <Box display="flex" gap={2} mt={2}>
                    <Button
                      variant="contained"
                      onClick={async () => {
                        if (!editLesson) return
                        const optimisticId = editLesson.id
                        const backup = groupSchedule.map((l) => ({ ...l }))
                        const backendLessonType = toBackendLessonType(editLesson.lesson_type)
                        const updatedLesson: Lesson = {
                          ...editLesson,
                          lesson_type: backendLessonType,
                        }
                        applyScheduleUpdate((prev) =>
                          prev.map((l) => (l.id === optimisticId ? updatedLesson : l))
                        )
                        try {
                          await api.patch(`/schedule/${optimisticId}`, {
                            subject: editLesson.subject,
                            teacher: editLesson.teacher,
                            room: editLesson.room,
                            lesson_type: backendLessonType,
                            weekday: editLesson.weekday,
                            start_time: editLesson.start_time,
                            end_time: editLesson.end_time,
                            parity: editLesson.parity,
                          })
                          setSnack(t("schedule:snackbar.updated"))
                          setEditing(false)
                          setOpenDialog(false)
                          await scheduleQuery.refetch().catch(() => {})
                        } catch {
                          setSnack(t("schedule:snackbar.updateError"))
                          applyScheduleUpdate(() => backup)
                        }
                      }}
                    >
                      {t("common:buttons.save")}
                    </Button>
                    <Button variant="outlined" color="secondary" onClick={() => setEditing(false)}>
                      {t("common:buttons.cancel")}
                    </Button>
                  </Box>
                </Stack>
              )}
            </DialogContent>
          </Dialog>

          <Dialog open={addDialogOpen} onClose={() => setAddDialogOpen(false)}>
            <DialogTitle>
              {`${t("schedule:dialog.addTitle")}${addDayLabel ? ` (${addDayLabel})` : ""}`}
            </DialogTitle>
            <DialogContent>
              <Stack spacing={2} mt={1} sx={{ minWidth: { xs: "auto", sm: 340 } }}>
                <TextField
                  label={t("schedule:form.subject")}
                  value={addFields.subject}
                  onChange={(e) => setAddFields({ ...addFields, subject: e.target.value })}
                  fullWidth
                />
                <TextField
                  label={t("schedule:form.teacher")}
                  value={addFields.teacher}
                  onChange={(e) => setAddFields({ ...addFields, teacher: e.target.value })}
                  fullWidth
                />
                <TextField
                  label={t("schedule:form.room")}
                  value={addFields.room}
                  onChange={(e) => setAddFields({ ...addFields, room: e.target.value })}
                  fullWidth
                />
                <TextField
                  select
                  label={t("schedule:form.lessonType")}
                  value={addFields.lessonType}
                  onChange={(e) => setAddFields({ ...addFields, lessonType: e.target.value })}
                  fullWidth
                >
                  {lessonTypeOptions.map((option) => (
                    <MenuItem value={option.value} key={option.value}>
                      {option.label}
                    </MenuItem>
                  ))}
                </TextField>
                <TextField
                  type="time"
                  label={t("schedule:form.startTime")}
                  value={addFields.startTime}
                  onChange={(e) => setAddFields({ ...addFields, startTime: e.target.value })}
                  fullWidth
                />
                <TextField
                  type="time"
                  label={t("schedule:form.endTime")}
                  value={addFields.endTime}
                  onChange={(e) => setAddFields({ ...addFields, endTime: e.target.value })}
                  fullWidth
                />
                <TextField
                  select
                  label={t("schedule:form.week")}
                  value={addFields.parity}
                  onChange={(e) =>
                    setAddFields((prev) => ({ ...prev, parity: e.target.value as LessonParity }))
                  }
                  fullWidth
                >
                  <MenuItem value="both">{t("schedule:week.both")}</MenuItem>
                  <MenuItem value="odd">{t("schedule:week.odd")}</MenuItem>
                  <MenuItem value="even">{t("schedule:week.even")}</MenuItem>
                </TextField>
                <Box display="flex" gap={2} mt={2}>
                  <Button variant="contained" onClick={handleAddLesson}>
                    {t("schedule:buttons.add")}
                  </Button>
                  <Button
                    variant="outlined"
                    color="secondary"
                    onClick={() => setAddDialogOpen(false)}
                  >
                    {t("common:buttons.cancel")}
                  </Button>
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
      </PageFadeIn>
    </Layout>
  )

  async function handleAddLesson() {
    const { subject, teacher, room, lessonType, startTime, endTime, parity } = addFields
    if (!subject || !teacher || !room || !addDay || !startTime || !endTime || !selectedGroup) {
      setSnack(t("schedule:snackbar.fillAllFields"))
      return
    }
    const backendLessonType = toBackendLessonType(lessonType)
    const optimistic: Lesson = {
      id: Date.now(),
      group_id: selectedGroup,
      subject,
      teacher,
      room,
      lesson_type: backendLessonType,
      weekday: addDay,
      start_time: dayjs().format("YYYY-MM-DDT") + startTime + ":00",
      end_time: dayjs().format("YYYY-MM-DDT") + endTime + ":00",
      parity,
    }
    applyScheduleUpdate((prev) => [...prev, optimistic])
    try {
      await api.post("/schedule", {
        group_id: selectedGroup,
        subject,
        teacher,
        room,
        lesson_type: backendLessonType,
        weekday: addDay,
        start_time: optimistic.start_time,
        end_time: optimistic.end_time,
        parity,
      })
      setSnack(t("schedule:snackbar.added"))
      setAddFields({
        subject: "",
        teacher: "",
        room: "",
        lessonType: defaultLessonType,
        startTime: "",
        endTime: "",
        parity: "both",
      })
      setAddDialogOpen(false)
      await scheduleQuery.refetch().catch(() => {})
    } catch {
      setSnack(t("schedule:snackbar.addError"))
      applyScheduleUpdate((prev) => prev.filter((l) => l.id !== optimistic.id))
    }
  }

  async function handleDeleteLesson(id: number) {
    const backup = groupSchedule.map((l) => ({ ...l }))
    applyScheduleUpdate((prev) => prev.filter((l) => l.id !== id))
    try {
      await api.delete(`/schedule/${id}`)
      await scheduleQuery.refetch().catch(() => {})
      setSnack(t("schedule:snackbar.deleted"))
    } catch {
      setSnack(t("schedule:snackbar.deleteError"))
      applyScheduleUpdate(() => backup)
    }
  }
}
