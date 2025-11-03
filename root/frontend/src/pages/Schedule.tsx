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
import DeleteIcon from "@mui/icons-material/Delete"
import InfoOutlinedIcon from "@mui/icons-material/InfoOutlined"
import AddIcon from "@mui/icons-material/Add"
import AccessTimeIcon from "@mui/icons-material/AccessTime"
import SchoolIcon from "@mui/icons-material/School"
import RoomIcon from "@mui/icons-material/Room"
import CalendarMonthIcon from "@mui/icons-material/CalendarMonth"
import useMediaQuery from "@/hooks/useMediaQuery"
import dayjs from "dayjs"
import isoWeek from "dayjs/plugin/isoWeek"
import "dayjs/locale/ru"
import "dayjs/locale/en"
import { useQuery, useQueryClient } from "@tanstack/react-query"
import { useTranslation } from "react-i18next"
import { getLocaleForLanguage, useLanguage } from "@/contexts/LanguageContext"
import { Button, Badge, ProgressBar, Tooltip } from "@/components/ui"
import Dialog from "@/components/Dialog"
import { cn } from "@/utils/cn"

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

function Snackbar({
  open,
  message,
  onClose,
}: {
  open: boolean
  message: string
  onClose: () => void
}) {
  useEffect(() => {
    if (!open || !message) return
    const timer = setTimeout(() => {
      onClose()
    }, 2200)
    return () => clearTimeout(timer)
  }, [open, message, onClose])

  if (!open || !message) return null

  return (
    <div className="fixed bottom-6 left-1/2 z-50 -translate-x-1/2 animate-in slide-in-from-bottom-4 fade-in">
      <div className="rounded-[1.25rem] border border-[color:color-mix(in_srgb,white_12%,var(--nav-link)_88%)] bg-[color:color-mix(in_srgb,var(--card-bg)_98%,white_2%)] px-5 py-3.5 text-sm font-semibold text-[color:var(--page-text)] shadow-[0_8px_24px_rgba(0,0,0,0.12),0_2px_8px_rgba(0,0,0,0.08)] backdrop-blur-md">
        {message}
      </div>
    </div>
  )
}

const fadeDelayStyle = (value: string): CSSProperties =>
  ({ "--fade-delay": value }) as CSSProperties

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
  }, [filteredSchedule, hasToday, todayIdx, weekdayBackend])

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

  const headerActions = (
    <div className="mb-7 flex flex-wrap items-center gap-3">
      <span className="text-sm font-semibold tracking-wide text-[color:color-mix(in_srgb,var(--secondary-text)_85%,white_15%)]">
        {t("schedule:week.label")}
      </span>
      <Button
        variant={currentParity === "odd" ? "solid" : "outline"}
        onClick={() => setCurrentParity("odd")}
        size="sm"
        className="font-semibold transition-transform duration-200 hover:-translate-y-[1px]"
      >
        {t("schedule:week.odd")}
      </Button>
      <Button
        variant={currentParity === "even" ? "solid" : "outline"}
        onClick={() => setCurrentParity("even")}
        size="sm"
        className="font-semibold transition-transform duration-200 hover:-translate-y-[1px]"
      >
        {t("schedule:week.even")}
      </Button>
    </div>
  )

  const renderBreakChip = (rowIdx: number, colIdx: number) => {
    if (rowIdx === 0) return null
    const prev = tableRows[rowIdx - 1]?.[colIdx]
    const curr = tableRows[rowIdx]?.[colIdx]
    if (!prev || !curr) return null
    const gap = minutesDiff(prev.end_time, curr.start_time)
    if (gap <= 0) return null
    return (
      <div className="absolute left-1/2 top-[-12px] z-[3] -translate-x-1/2 pointer-events-none">
        <Badge 
          size="xs" 
          className="chip-break font-medium bg-[color:color-mix(in_srgb,var(--card-bg)_94%,yellow_6%)] border-[color:color-mix(in_srgb,var(--nav-link)_25%,transparent)] text-[color:var(--page-text)] shadow-[0_2px_8px_rgba(0,0,0,0.08)]"
        >
          {t("schedule:break", { minutes: gap })}
        </Badge>
      </div>
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
    <div
      onClick={onOpen}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault()
          onOpen()
        }
      }}
      role="button"
      tabIndex={0}
      className={cn(
        "relative cursor-pointer rounded-ue-md border border-white/12 bg-[color:var(--option-bg)] shadow-surface transition-[transform,box-shadow] duration-200",
        hasBreakBefore ? "mt-6" : "",
        "hover:-translate-y-0.5 hover:shadow-[0_10px_28px_rgba(0,0,0,0.12),0_2px_10px_rgba(0,0,0,0.19)]",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--nav-link)] focus-visible:ring-offset-2"
      )}
      style={{ minHeight: lessonCardHeight, padding: "10px 11px 10px 14px" }}
      title={isConflict ? t("schedule:lesson.conflict") : undefined}
    >
      <div
        className="absolute left-[-1px] top-[-1px] bottom-[-1px] w-1.5 rounded-l-[8px]"
        style={{ background: getLessonTypeColor(lesson.lesson_type) }}
      />
      <div className="flex flex-col gap-1.5">
        <div className="flex items-center justify-between">
          <Badge
            size="xs"
            className="chip-type"
            style={{
              background: getLessonTypeColor(lesson.lesson_type),
              color: "#fff",
              height: "22px",
            }}
          >
            {lessonTypeLabels.get(lesson.lesson_type ?? "") ?? lesson.lesson_type ?? ""}
          </Badge>
          <Badge
            size="xs"
            variant="outline"
            className="chip-time"
            leadingIcon={<AccessTimeIcon className="text-[16px]" />}
          >
            {`${getTimeStr(lesson)}–${getEndTimeStr(lesson)}`}
          </Badge>
        </div>
        <h3
          className="text-base font-extrabold text-[color:var(--page-text)] line-clamp-2"
          style={{ fontSize: "1rem" }}
        >
          {lesson.subject}
        </h3>
        <div className="flex flex-wrap gap-2">
          <Badge
            size="xs"
            variant="outline"
            leadingIcon={<SchoolIcon className="text-[16px] text-[color:var(--nav-link)]" />}
            className="text-[color:var(--page-text)] border-white/12"
          >
            {lesson.teacher}
          </Badge>
          <Badge
            size="xs"
            variant="outline"
            leadingIcon={<RoomIcon className="text-[16px] text-[color:var(--nav-link)]" />}
            className="text-[color:var(--page-text)] border-white/12"
          >
            {lesson.room}
          </Badge>
        </div>
      </div>
      <Tooltip content={t("schedule:lesson.details")}>
        <InfoOutlinedIcon className="absolute bottom-2 right-2 text-[18px] text-[color:var(--secondary-text)]" />
      </Tooltip>
      {(user?.role === "admin" || user?.role === "teacher") && (
        <button
          aria-label={t("schedule:aria.deleteLesson")}
          className="absolute top-1.5 right-1.5 z-[2] rounded-md bg-[color:var(--card-bg)] p-1 transition-colors hover:bg-[color:var(--option-bg)]"
          onClick={(e) => {
            e.stopPropagation()
            onDelete()
          }}
        >
          <DeleteIcon className="text-red-500 text-[16px]" />
        </button>
      )}
      {isConflict && (
        <div className="pointer-events-none absolute inset-0 rounded-ue-md shadow-[inset_0_0_0_3px_rgba(239,83,80,0.2)]" />
      )}
    </div>
  )

  const renderTable = () => {
    const visibleRows = tableRows.slice(0, rowLimit)
    return (
      <div
        ref={tableScrollRef}
        className="mx-auto w-full max-w-[min(98vw,1920px)] overflow-x-auto rounded-[2rem] border border-[color:color-mix(in_srgb,white_10%,var(--nav-link)_90%)] bg-[color:color-mix(in_srgb,var(--card-bg)_99%,white_1%)] text-[color:var(--page-text)] shadow-[0_8px_32px_rgba(0,0,0,0.06),0_2px_8px_rgba(0,0,0,0.04)] [content-visibility:auto] [contain-intrinsic-size:600px] [scroll-behavior:smooth]"
        style={{ minHeight: 360 }}
      >
        <table className="w-full border-collapse">
          <thead className="sticky top-0 z-[5]">
            <tr>
              <th
                className="sticky left-0 z-[10] w-[50px] bg-[color:color-mix(in_srgb,var(--card-bg)_98%,white_2%)] px-4 py-4 text-center font-extrabold text-[color:var(--page-text)] shadow-[2px_0_4px_rgba(0,0,0,0.02)] backdrop-blur-sm"
                style={{ fontSize: "clamp(0.95rem,1.8vw,1.15rem)" }}
              >
                №
              </th>
              {weekdayBackend.map((day, idx) => {
                const label = weekdayLabels[idx] ?? day
                const isTodayCol = hasToday && idx === todayIdx
                return (
                  <th
                    key={day}
                    ref={(el: HTMLTableCellElement | null) => {
                      headRefs.current[idx] = el
                    }}
                    className={cn(
                      "relative px-4 py-4 text-center font-extrabold text-[color:var(--page-text)] transition-colors duration-200",
                      isTodayCol
                        ? "border-l-[3px] border-r-[3px] border-solid bg-[color:color-mix(in_srgb,var(--nav-link)_4%,var(--card-bg)_96%)] border-[color:color-mix(in_srgb,var(--nav-link)_35%,transparent)]"
                        : "bg-[color:color-mix(in_srgb,var(--card-bg)_97%,white_3%)]",
                      "z-[5] backdrop-blur-sm"
                    )}
                    style={{ fontSize: "clamp(0.94rem, 1.5vw, 1.12rem)" }}
                  >
                    <div className="flex items-center justify-center gap-2">
                      <span className={cn("tracking-tight", isTodayCol && "text-[color:var(--nav-link)]")}>
                        {label}
                      </span>
                      {(user?.role === "admin" || user?.role === "teacher") && (
                        <button
                          className="ml-1 flex h-7 w-7 items-center justify-center rounded-lg border border-[color:color-mix(in_srgb,white_15%,var(--nav-link)_85%)] bg-[color:color-mix(in_srgb,var(--card-bg)_92%,var(--nav-link)_8%)] text-[color:var(--nav-link)] transition-all duration-200 hover:border-[color:var(--nav-link)] hover:bg-[color:var(--nav-link)] hover:text-white hover:shadow-[0_4px_12px_color-mix(in_srgb,var(--nav-link)_25%,transparent)]"
                          onClick={(e) => {
                            e.stopPropagation()
                            setAddDay(day)
                            setAddDialogOpen(true)
                          }}
                          aria-label={t("schedule:aria.addLesson", { day: label })}
                        >
                          <AddIcon className="text-[14px]" />
                        </button>
                      )}
                    </div>
                  </th>
                )
              })}
            </tr>
          </thead>
          <tbody className="[content-visibility:auto]">
            {visibleRows.length === 0 ? (
              <tr>
                <td
                  colSpan={weekdayBackend.length + 1}
                  className="py-12 text-center text-[color:color-mix(in_srgb,var(--secondary-text)_70%,transparent)] text-base"
                >
                  {t("schedule:table.noLessons")}
                </td>
              </tr>
            ) : (
              visibleRows.map((row, rowIdx) => (
                <tr
                  key={rowIdx}
                  className="transition-colors duration-150 hover:bg-[color:color-mix(in_srgb,var(--nav-link)_1%,var(--card-bg)_99%)]"
                >
                  <td
                    className="sticky left-0 z-[10] bg-[color:color-mix(in_srgb,var(--card-bg)_98%,white_2%)] px-4 py-3 text-center font-bold text-[color:var(--page-text)] shadow-[2px_0_4px_rgba(0,0,0,0.02)] backdrop-blur-sm"
                    style={{ fontSize: "clamp(0.95rem,1.8vw,1.15rem)" }}
                  >
                    {rowIdx + 1}
                  </td>
                  {row.map((lesson, colIdx) => {
                    const colIsToday = hasToday && colIdx === todayIdx
                    if (!lesson) {
                      return (
                        <td
                          key={`empty-${rowIdx}-${colIdx}`}
                          className={cn(
                            "p-3",
                            colIsToday ? "bg-[color:color-mix(in_srgb,var(--nav-link)_2%,var(--card-bg)_98%)]" : ""
                          )}
                        >
                          <div className="min-h-[148px] rounded-ue-lg border border-dashed border-[color:color-mix(in_srgb,white_8%,var(--nav-link)_92%)] bg-[color:color-mix(in_srgb,var(--card-bg)_96%,white_4%)]" />
                        </td>
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
                      <td
                        key={lesson.id ?? `${rowIdx}-${colIdx}`}
                        className={cn(
                          "relative overflow-visible p-3 text-[color:var(--page-text)] transition-colors duration-150",
                          colIsToday ? "bg-[color:color-mix(in_srgb,var(--nav-link)_2%,var(--card-bg)_98%)]" : ""
                        )}
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
                      </td>
                    )
                  })}
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    )
  }

  const renderMobileDayAnchors = () => (
    <div className="flex gap-2 overflow-x-auto pb-2 px-1 scrollbar-hide">
      {weekdayBackend.map((day, i) => (
        <Badge
          key={day}
          as="button"
          variant={hasToday && i === todayIdx ? "solid" : "outline"}
          tone={hasToday && i === todayIdx ? "primary" : "default"}
          className="chip-day flex-shrink-0 font-semibold transition-all duration-200 hover:scale-105"
          onClick={() =>
            dayCardRefs.current[i]?.scrollIntoView({ behavior: "smooth", block: "start" })
          }
        >
          {weekdayShort[i] ?? getDayLabel(day)}
        </Badge>
      ))}
    </div>
  )

  const renderMobileCards = () => (
    <div className="mt-2 flex w-full flex-col gap-5">
      {renderMobileDayAnchors()}
      {weekdayBackend.map((day, dayIdx) => {
        const label = weekdayLabels[dayIdx] ?? day
        const lessons = filteredSchedule
          .filter((l) => l.weekday === day)
          .sort((a, b) => getTimeStr(a).localeCompare(getTimeStr(b)))
        const isToday = hasToday && dayIdx === todayIdx
        return (
          <div
            key={day}
            ref={(el: HTMLDivElement | null) => {
              dayCardRefs.current[dayIdx] = el
            }}
            className={cn(
              "group relative isolate mb-2 rounded-[1.75rem] border border-[color:color-mix(in_srgb,white_12%,var(--nav-link)_88%)] p-5 shadow-[0_6px_20px_rgba(0,0,0,0.06),0_2px_6px_rgba(0,0,0,0.04)] [content-visibility:auto] [contain-intrinsic-size:400px] transition-all duration-300",
              isToday
                ? "bg-[color:color-mix(in_srgb,var(--nav-link)_4%,var(--card-bg)_96%)] ring-2 ring-[color:color-mix(in_srgb,var(--nav-link)_25%,transparent)]"
                : "bg-[color:color-mix(in_srgb,var(--card-bg)_98%,white_2%)]"
            )}
          >
            <div className="mb-3 flex items-center gap-2">
              <h3 className={cn(
                "text-lg font-extrabold tracking-tight text-[color:var(--page-text)]",
                isToday && "text-[color:var(--nav-link)]"
              )}>
                {label}
              </h3>
              {(user?.role === "admin" || user?.role === "teacher") && (
                <button
                  className="ml-auto flex h-7 w-7 items-center justify-center rounded-lg border border-[color:color-mix(in_srgb,white_15%,var(--nav-link)_85%)] bg-[color:color-mix(in_srgb,var(--card-bg)_92%,var(--nav-link)_8%)] text-[color:var(--nav-link)] transition-all duration-200 hover:border-[color:var(--nav-link)] hover:bg-[color:var(--nav-link)] hover:text-white hover:shadow-[0_4px_12px_color-mix(in_srgb,var(--nav-link)_25%,transparent)]"
                  onClick={(e) => {
                    e.stopPropagation()
                    setAddDay(day)
                    setAddDialogOpen(true)
                  }}
                  aria-label={t("schedule:aria.addLesson", { day: label })}
                >
                  <AddIcon className="text-[14px]" />
                </button>
              )}
            </div>
            {lessons.length === 0 ? (
              <p className="text-[color:color-mix(in_srgb,var(--secondary-text)_70%,transparent)] text-sm">
                {t("schedule:mobile.noLessons")}
              </p>
            ) : (
              <div className="flex flex-col gap-3">
                {lessons.map((lesson, idx) => {
                  const prev = lessons[idx - 1]
                  const gap = prev ? minutesDiff(prev.end_time, lesson.start_time) : 0
                  const isConflict = conflictedIds.has(lesson.id)
                  return (
                    <div key={lesson.id}>
                      {idx > 0 && gap > 0 && (
                        <Badge 
                          size="xs" 
                          className="chip-break mb-2 font-medium bg-[color:color-mix(in_srgb,var(--card-bg)_94%,yellow_6%)] border-[color:color-mix(in_srgb,var(--nav-link)_25%,transparent)] text-[color:var(--page-text)] shadow-[0_2px_8px_rgba(0,0,0,0.08)]"
                        >
                          {t("schedule:break", { minutes: gap })}
                        </Badge>
                      )}
                      <div
                        onClick={() => {
                          setDialogLesson(lesson)
                          setOpenDialog(true)
                        }}
                        onKeyDown={(e) => {
                          if (e.key === "Enter" || e.key === " ") {
                            e.preventDefault()
                            setDialogLesson(lesson)
                            setOpenDialog(true)
                          }
                        }}
                        role="button"
                        tabIndex={0}
                        className={cn(
                          "relative isolate cursor-pointer rounded-ue-lg border border-[color:color-mix(in_srgb,white_12%,var(--nav-link)_88%)] bg-[color:color-mix(in_srgb,var(--card-bg)_98%,white_2%)] p-4 shadow-[0_2px_8px_rgba(0,0,0,0.04),0_1px_2px_rgba(0,0,0,0.06)] transition-all duration-300 hover:-translate-y-[2px] hover:border-[color:color-mix(in_srgb,white_20%,var(--nav-link)_80%)] hover:bg-[color:color-mix(in_srgb,var(--card-bg)_96%,white_4%)] hover:shadow-[0_8px_24px_rgba(0,0,0,0.08),0_4px_8px_rgba(0,0,0,0.06)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--nav-link)] focus-visible:ring-offset-2",
                          isConflict && "ring-2 ring-red-500/20"
                        )}
                      >
                        <div
                          className="absolute left-0 top-0 bottom-0 w-[3px] rounded-l-[10px]"
                          style={{ background: getLessonTypeColor(lesson.lesson_type) }}
                        />
                        <div className="flex flex-wrap items-center gap-2 pl-1">
                          <Badge
                            size="xs"
                            className="chip-type font-semibold"
                            style={{
                              background: getLessonTypeColor(lesson.lesson_type),
                              color: "#fff",
                              height: "24px",
                              paddingLeft: "8px",
                              paddingRight: "8px",
                            }}
                          >
                            {lessonTypeLabels.get(lesson.lesson_type ?? "") ??
                              lesson.lesson_type ??
                              ""}
                          </Badge>
                          <Badge
                            size="xs"
                            variant="outline"
                            className="chip-time font-medium"
                            leadingIcon={<AccessTimeIcon className="text-[15px]" />}
                          >
                            {`${getTimeStr(lesson)}–${getEndTimeStr(lesson)}`}
                          </Badge>
                        </div>
                        <h4 className="mt-2 line-clamp-2 pl-1 text-base font-bold leading-snug text-[color:var(--page-text)]">
                          {lesson.subject}
                        </h4>
                        <div className="mt-2 flex flex-wrap gap-2 pl-1">
                          <Badge
                            size="xs"
                            variant="outline"
                            leadingIcon={<SchoolIcon className="text-[15px]" />}
                            className="font-medium text-[color:var(--page-text)] border-[color:color-mix(in_srgb,white_18%,var(--nav-link)_82%)]"
                          >
                            {lesson.teacher}
                          </Badge>
                          <Badge
                            size="xs"
                            variant="outline"
                            leadingIcon={<RoomIcon className="text-[15px]" />}
                            className="font-medium text-[color:var(--page-text)] border-[color:color-mix(in_srgb,white_18%,var(--nav-link)_82%)]"
                          >
                            {lesson.room}
                          </Badge>
                        </div>
                        {isConflict && (
                          <div className="pointer-events-none absolute inset-0 rounded-ue-lg ring-2 ring-red-500/25 ring-inset" />
                        )}
                      </div>
                    </div>
                  )
                })}
              </div>
            )}
          </div>
        )
      })}
    </div>
  )

  if (loading)
    return (
      <Layout>
        <div className="flex min-h-[70vh] items-center justify-center">
          {t("common:statuses.loading")}
        </div>
      </Layout>
    )

  const inputClass =
    "w-full rounded-ue-lg border border-[color:color-mix(in_srgb,white_12%,var(--nav-link)_88%)] bg-[color:color-mix(in_srgb,var(--card-bg)_96%,white_4%)] px-4 py-3 text-[0.98rem] font-medium text-[color:var(--page-text)] shadow-[inset_0_1px_2px_rgba(0,0,0,0.04)] transition-all duration-200 focus:border-[color:var(--nav-link)] focus:outline-none focus:shadow-[0_0_0_3px_color-mix(in_srgb,var(--nav-link)_15%,transparent)] placeholder:text-[color:color-mix(in_srgb,var(--placeholder-fg)_70%,transparent)]"

  return (
    <Layout>
      <PageFadeIn>
        <style>{`
        @media print {
          body { background: #fff !important; }
          .no-print { display: none !important; }
          table { box-shadow: none !important; }
          td { border: 1px solid #999 !important; }
          thead th { background: #eee !important; color: #000 !important; }
        }
      `}</style>
        <div className="w-screen min-h-screen bg-[color:var(--page-bg)] text-[color:var(--page-text)] py-8 sm:py-10">
          <div className="mx-auto mb-4 mt-0 max-w-[980px] px-4 sm:px-6 md:px-8 lg:px-12">
            <div
              data-fade
              style={fadeDelayStyle("80ms")}
              className="mb-8 mt-1 flex flex-wrap items-center gap-3 sm:gap-4"
            >
              <div className="flex h-12 w-12 items-center justify-center rounded-full bg-[color:color-mix(in_srgb,var(--glass-bg)_70%,var(--nav-link)_30%)] text-[color:var(--nav-link)] shadow-[0_4px_16px_color-mix(in_srgb,var(--nav-link)_20%,transparent)]">
                <CalendarMonthIcon className="text-[2rem]" />
              </div>
              <h1 className="text-[clamp(1.6rem,5vw,2.75rem)] font-bold tracking-tight text-[color:var(--page-text)]">
                {user?.role === "student"
                  ? t("schedule:title.student")
                  : t("schedule:title.default")}
              </h1>
              <Badge
                variant="outline"
                className="translate-y-0.5 font-medium text-[clamp(0.8rem,0.75rem+0.35vw,0.98rem)] border-[color:color-mix(in_srgb,white_18%,var(--nav-link)_82%)]"
              >
                {todayLabel}
              </Badge>
              {activeGroupName && (
                <Badge
                  variant="outline"
                  className="translate-y-0.5 font-medium text-[clamp(0.8rem,0.75rem+0.35vw,0.98rem)] border-[color:color-mix(in_srgb,white_18%,var(--nav-link)_82%)]"
                >
                  {t("schedule:header.groupName", { name: activeGroupName })}
                </Badge>
              )}
            </div>

            <div data-fade style={fadeDelayStyle("140ms")} className="mb-6">
              {headerActions}
            </div>

            <div
              data-fade
              style={fadeDelayStyle("200ms")}
              className="no-print group relative isolate mb-6 overflow-hidden rounded-[1.75rem] border border-[color:color-mix(in_srgb,white_12%,var(--nav-link)_88%)] bg-[color:color-mix(in_srgb,var(--card-bg)_98%,white_2%)] p-6 shadow-[0_8px_32px_rgba(0,0,0,0.06),0_2px_8px_rgba(0,0,0,0.04)] transition-all duration-300 hover:shadow-[0_12px_40px_rgba(0,0,0,0.08),0_4px_12px_rgba(0,0,0,0.06)]"
            >
              <span
                aria-hidden="true"
                className="pointer-events-none absolute -right-24 top-1/2 h-64 w-64 -translate-y-1/2 rounded-full bg-[radial-gradient(circle,color-mix(in_srgb,var(--nav-link)_12%,transparent),transparent)] blur-3xl opacity-0 transition-opacity duration-500 group-hover:opacity-100"
              />
              {currentLesson ? (
                <div className="relative z-[1]">
                  <div className="mb-4 flex flex-wrap items-center gap-2.5">
                    <Badge 
                      size="sm" 
                      tone="primary"
                      className="chip-clock font-semibold"
                    >
                      {t("schedule:chips.current")}
                    </Badge>
                    <Badge 
                      size="sm" 
                      variant="outline" 
                      className="chip-time font-medium"
                      leadingIcon={<AccessTimeIcon className="text-[16px]" />}
                    >
                      {`${getTimeStr(currentLesson)}–${getEndTimeStr(currentLesson)}`}
                    </Badge>
                    <h3 className="text-lg font-extrabold tracking-tight text-[color:var(--page-text)]">
                      {currentLesson.subject}
                    </h3>
                    {!!timeLeftText && (
                      <Badge 
                        size="sm" 
                        className="chip-left font-semibold bg-[color:color-mix(in_srgb,var(--card-bg)_92%,var(--nav-link)_8%)]"
                      >
                        {timeLeftText}
                      </Badge>
                    )}
                  </div>
                  <div className="mb-4 flex flex-wrap gap-2.5">
                    <Badge
                      size="sm"
                      variant="outline"
                      leadingIcon={<SchoolIcon className="text-[16px]" />}
                      className="font-medium border-[color:color-mix(in_srgb,white_18%,var(--nav-link)_82%)]"
                    >
                      {currentLesson.teacher}
                    </Badge>
                    <Badge
                      size="sm"
                      variant="outline"
                      leadingIcon={<RoomIcon className="text-[16px]" />}
                      className="font-medium border-[color:color-mix(in_srgb,white_18%,var(--nav-link)_82%)]"
                    >
                      {currentLesson.room}
                    </Badge>
                  </div>
                  <ProgressBar
                    value={currentProgress}
                    className="mt-5 h-2.5 rounded-full"
                    barClassName="bg-[color:var(--progress-bar)] transition-[width] duration-300 rounded-full"
                    ariaLabel={t("schedule:aria.currentProgress")}
                  />
                </div>
              ) : nextLesson ? (
                <div className="relative z-[1] flex flex-wrap items-center gap-2.5">
                  <Badge 
                    size="sm" 
                    variant="outline"
                    tone="primary"
                    className="chip-clock font-semibold border-[color:color-mix(in_srgb,white_18%,var(--nav-link)_82%)]"
                  >
                    {t("schedule:chips.next")}
                  </Badge>
                  <Badge 
                    size="sm" 
                    variant="outline" 
                    className="chip-time font-medium"
                    leadingIcon={<AccessTimeIcon className="text-[16px]" />}
                  >
                    {`${getTimeStr(nextLesson)}–${getEndTimeStr(nextLesson)}`}
                  </Badge>
                  <h3 className="text-lg font-extrabold tracking-tight text-[color:var(--page-text)]">
                    {nextLesson.subject}
                  </h3>
                  {!!timeLeftText && (
                    <Badge 
                      size="sm" 
                      className="chip-left font-semibold bg-[color:color-mix(in_srgb,var(--card-bg)_92%,var(--nav-link)_8%)]"
                    >
                      {timeLeftText}
                    </Badge>
                  )}
                </div>
              ) : (
                <p className="text-[color:color-mix(in_srgb,var(--secondary-text)_70%,transparent)] text-base">
                  {t("schedule:summary.noMoreToday")}
                </p>
              )}
            </div>

            {(user?.role === "teacher" || user?.role === "admin") && (
              <div data-fade style={fadeDelayStyle("240ms")} className="mb-6 max-w-[360px]">
                <label className="mb-2 block text-sm font-semibold tracking-wide text-[color:color-mix(in_srgb,var(--secondary-text)_85%,white_15%)]">
                  {t("schedule:form.groupLabel")}
                </label>
                <select
                  value={selectedGroup ?? ""}
                  onChange={(e) => setSelectedGroup(Number(e.target.value))}
                  className={inputClass}
                >
                  {groups.map((g) => (
                    <option key={g.id} value={g.id}>
                      {g.name}
                    </option>
                  ))}
                </select>
              </div>
            )}
          </div>

          <div
            data-fade
            style={fadeDelayStyle("280ms")}
            className="mx-auto max-w-[1920px] px-2 md:px-4"
          >
            {isMobile ? renderMobileCards() : renderTable()}
          </div>

          <Dialog
            open={openDialog}
            onClose={() => setOpenDialog(false)}
            title={dialogLesson?.subject || t("schedule:dialog.detailsFallback")}
          >
            {dialogLesson && (
              <div className="space-y-4">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-sm font-semibold tracking-wide text-[color:color-mix(in_srgb,var(--secondary-text)_85%,white_15%)]">
                    {t("schedule:dialog.typeLabel")}:
                  </span>
                  <Badge
                    size="sm"
                    className="font-semibold"
                    style={{
                      color: "#fff",
                      background: getLessonTypeColor(dialogLesson.lesson_type),
                    }}
                  >
                    {lessonTypeLabels.get(dialogLesson.lesson_type ?? "") ??
                      dialogLesson.lesson_type ??
                      ""}
                  </Badge>
                </div>
                <div className="space-y-1">
                  <span className="text-sm font-semibold tracking-wide text-[color:color-mix(in_srgb,var(--secondary-text)_85%,white_15%)]">
                    {t("schedule:dialog.timeLabel")}:
                  </span>
                  <p className="text-base text-[color:var(--page-text)]">
                    {getTimeStr(dialogLesson)}–{getEndTimeStr(dialogLesson)}
                  </p>
                </div>
                <div className="space-y-1">
                  <span className="text-sm font-semibold tracking-wide text-[color:color-mix(in_srgb,var(--secondary-text)_85%,white_15%)]">
                    {t("schedule:dialog.teacherLabel")}:
                  </span>
                  <p className="text-base text-[color:var(--page-text)]">
                    {dialogLesson.teacher}
                  </p>
                </div>
                <div className="space-y-1">
                  <span className="text-sm font-semibold tracking-wide text-[color:color-mix(in_srgb,var(--secondary-text)_85%,white_15%)]">
                    {t("schedule:dialog.roomLabel")}:
                  </span>
                  <p className="text-base text-[color:var(--page-text)]">
                    {dialogLesson.room}
                  </p>
                </div>
                <div className="flex gap-3 pt-2">
                  {(user?.role === "admin" || user?.role === "teacher") && (
                    <Button
                      variant="solid"
                      onClick={() => {
                        if (!dialogLesson) return
                        setEditing(true)
                        setEditLesson({
                          ...dialogLesson,
                          lesson_type: resolveLessonTypeId(dialogLesson.lesson_type),
                        })
                        setOpenDialog(false)
                      }}
                      className="font-semibold"
                    >
                      {t("schedule:buttons.edit")}
                    </Button>
                  )}
                  <Button 
                    variant="outline" 
                    onClick={() => setOpenDialog(false)}
                    className="font-semibold"
                  >
                    {t("schedule:buttons.close")}
                  </Button>
                </div>
              </div>
            )}
          </Dialog>

          <Dialog
            open={editing}
            onClose={() => setEditing(false)}
            title={t("schedule:dialog.editTitle")}
          >
            {editLesson && (
              <div className="space-y-5 pt-2">
                <div>
                  <label className="mb-2 block text-sm font-semibold tracking-wide text-[color:color-mix(in_srgb,var(--secondary-text)_85%,white_15%)]">
                    {t("schedule:form.subject")}
                  </label>
                  <input
                    type="text"
                    value={editLesson.subject || ""}
                    onChange={(e) => setEditLesson({ ...editLesson, subject: e.target.value })}
                    className={inputClass}
                  />
                </div>
                <div>
                  <label className="mb-2 block text-sm font-semibold tracking-wide text-[color:color-mix(in_srgb,var(--secondary-text)_85%,white_15%)]">
                    {t("schedule:form.teacher")}
                  </label>
                  <input
                    type="text"
                    value={editLesson.teacher || ""}
                    onChange={(e) => setEditLesson({ ...editLesson, teacher: e.target.value })}
                    className={inputClass}
                  />
                </div>
                <div>
                  <label className="mb-2 block text-sm font-semibold tracking-wide text-[color:color-mix(in_srgb,var(--secondary-text)_85%,white_15%)]">
                    {t("schedule:form.room")}
                  </label>
                  <input
                    type="text"
                    value={editLesson.room || ""}
                    onChange={(e) => setEditLesson({ ...editLesson, room: e.target.value })}
                    className={inputClass}
                  />
                </div>
                <div>
                  <label className="mb-2 block text-sm font-semibold tracking-wide text-[color:color-mix(in_srgb,var(--secondary-text)_85%,white_15%)]">
                    {t("schedule:form.lessonType")}
                  </label>
                  <select
                    value={editLesson.lesson_type || ""}
                    onChange={(e) => setEditLesson({ ...editLesson, lesson_type: e.target.value })}
                    className={inputClass}
                  >
                    {editingLessonTypeOptions.map((option) => (
                      <option key={option.value} value={option.value}>
                        {option.label}
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="mb-2 block text-sm font-semibold tracking-wide text-[color:color-mix(in_srgb,var(--secondary-text)_85%,white_15%)]">
                    {t("schedule:form.day")}
                  </label>
                  <select
                    value={editLesson.weekday}
                    onChange={(e) => setEditLesson({ ...editLesson, weekday: e.target.value })}
                    className={inputClass}
                  >
                    {weekdayBackend.map((day) => (
                      <option key={day} value={day}>
                        {getDayLabel(day)}
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="mb-2 block text-sm font-semibold tracking-wide text-[color:color-mix(in_srgb,var(--secondary-text)_85%,white_15%)]">
                    {t("schedule:form.startTime")}
                  </label>
                  <input
                    type="time"
                    value={getTimeStr(editLesson)}
                    onChange={(e) =>
                      setEditLesson({
                        ...editLesson,
                        start_time: `${
                          editLesson.start_time?.slice(0, 11) || dayjs().format("YYYY-MM-DDT")
                        }${e.target.value}:00`,
                      })
                    }
                    className={inputClass}
                  />
                </div>
                <div>
                  <label className="mb-2 block text-sm font-semibold tracking-wide text-[color:color-mix(in_srgb,var(--secondary-text)_85%,white_15%)]">
                    {t("schedule:form.endTime")}
                  </label>
                  <input
                    type="time"
                    value={getEndTimeStr(editLesson)}
                    onChange={(e) =>
                      setEditLesson({
                        ...editLesson,
                        end_time: `${
                          editLesson.end_time?.slice(0, 11) || dayjs().format("YYYY-MM-DDT")
                        }${e.target.value}:00`,
                      })
                    }
                    className={inputClass}
                  />
                </div>
                <div>
                  <label className="mb-2 block text-sm font-semibold tracking-wide text-[color:color-mix(in_srgb,var(--secondary-text)_85%,white_15%)]">
                    {t("schedule:form.week")}
                  </label>
                  <select
                    value={editLesson.parity}
                    onChange={(e) =>
                      setEditLesson((prev) =>
                        prev ? { ...prev, parity: e.target.value as LessonParity } : prev
                      )
                    }
                    className={inputClass}
                  >
                    <option value="both">{t("schedule:week.both")}</option>
                    <option value="odd">{t("schedule:week.odd")}</option>
                    <option value="even">{t("schedule:week.even")}</option>
                  </select>
                </div>
                <div className="flex gap-4 pt-2">
                  <Button
                    variant="solid"
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
                    className="font-semibold"
                  >
                    {t("common:buttons.save")}
                  </Button>
                  <Button 
                    variant="outline" 
                    onClick={() => setEditing(false)}
                    className="font-semibold"
                  >
                    {t("common:buttons.cancel")}
                  </Button>
                </div>
              </div>
            )}
          </Dialog>

          <Dialog
            open={addDialogOpen}
            onClose={() => setAddDialogOpen(false)}
            title={`${t("schedule:dialog.addTitle")}${addDayLabel ? ` (${addDayLabel})` : ""}`}
          >
            <div className="space-y-5 pt-2 min-w-[280px] sm:min-w-[360px]">
              <div>
                <label className="mb-2 block text-sm font-semibold tracking-wide text-[color:color-mix(in_srgb,var(--secondary-text)_85%,white_15%)]">
                  {t("schedule:form.subject")}
                </label>
                <input
                  type="text"
                  value={addFields.subject}
                  onChange={(e) => setAddFields({ ...addFields, subject: e.target.value })}
                  className={inputClass}
                />
              </div>
              <div>
                <label className="mb-2 block text-sm font-semibold tracking-wide text-[color:color-mix(in_srgb,var(--secondary-text)_85%,white_15%)]">
                  {t("schedule:form.teacher")}
                </label>
                <input
                  type="text"
                  value={addFields.teacher}
                  onChange={(e) => setAddFields({ ...addFields, teacher: e.target.value })}
                  className={inputClass}
                />
              </div>
              <div>
                <label className="mb-2 block text-sm font-semibold tracking-wide text-[color:color-mix(in_srgb,var(--secondary-text)_85%,white_15%)]">
                  {t("schedule:form.room")}
                </label>
                <input
                  type="text"
                  value={addFields.room}
                  onChange={(e) => setAddFields({ ...addFields, room: e.target.value })}
                  className={inputClass}
                />
              </div>
              <div>
                <label className="mb-2 block text-sm font-semibold tracking-wide text-[color:color-mix(in_srgb,var(--secondary-text)_85%,white_15%)]">
                  {t("schedule:form.lessonType")}
                </label>
                <select
                  value={addFields.lessonType}
                  onChange={(e) => setAddFields({ ...addFields, lessonType: e.target.value })}
                  className={inputClass}
                >
                  {lessonTypeOptions.map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label className="mb-2 block text-sm font-semibold tracking-wide text-[color:color-mix(in_srgb,var(--secondary-text)_85%,white_15%)]">
                  {t("schedule:form.startTime")}
                </label>
                <input
                  type="time"
                  value={addFields.startTime}
                  onChange={(e) => setAddFields({ ...addFields, startTime: e.target.value })}
                  className={inputClass}
                />
              </div>
              <div>
                <label className="mb-2 block text-sm font-semibold tracking-wide text-[color:color-mix(in_srgb,var(--secondary-text)_85%,white_15%)]">
                  {t("schedule:form.endTime")}
                </label>
                <input
                  type="time"
                  value={addFields.endTime}
                  onChange={(e) => setAddFields({ ...addFields, endTime: e.target.value })}
                  className={inputClass}
                />
              </div>
              <div>
                <label className="mb-2 block text-sm font-semibold tracking-wide text-[color:color-mix(in_srgb,var(--secondary-text)_85%,white_15%)]">
                  {t("schedule:form.week")}
                </label>
                <select
                  value={addFields.parity}
                  onChange={(e) =>
                    setAddFields((prev) => ({ ...prev, parity: e.target.value as LessonParity }))
                  }
                  className={inputClass}
                >
                  <option value="both">{t("schedule:week.both")}</option>
                  <option value="odd">{t("schedule:week.odd")}</option>
                  <option value="even">{t("schedule:week.even")}</option>
                </select>
              </div>
              <div className="flex gap-4 pt-2">
                <Button variant="solid" onClick={handleAddLesson} className="font-semibold">
                  {t("schedule:buttons.add")}
                </Button>
                <Button 
                  variant="outline" 
                  onClick={() => setAddDialogOpen(false)}
                  className="font-semibold"
                >
                  {t("common:buttons.cancel")}
                </Button>
              </div>
            </div>
          </Dialog>

          <Snackbar open={!!snack} message={snack} onClose={() => setSnack("")} />
        </div>
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
