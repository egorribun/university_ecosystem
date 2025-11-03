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
import dayjs from "dayjs"
import isoWeek from "dayjs/plugin/isoWeek"
import "dayjs/locale/ru"
import "dayjs/locale/en"
import { useQuery, useQueryClient } from "@tanstack/react-query"
import { useTranslation } from "react-i18next"
import { getLocaleForLanguage, useLanguage } from "@/contexts/LanguageContext"
import { Button, Chip, ProgressBar, Tooltip } from "@/components/ui"
import Dialog from "@/components/Dialog"
import { cn } from "@/utils/cn"
import useMediaQuery from "@/hooks/useMediaQuery"

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
  useEffect(() => {
    if (!snack || typeof window === "undefined") return
    const id = window.setTimeout(() => setSnack(""), 2200)
    return () => window.clearTimeout(id)
  }, [snack])
  const addDayLabel = addDay ? getDayLabel(addDay) : ""
  const isMobile = useMediaQuery("(max-width:1730px)")
  const tableScrollRef = useRef<HTMLDivElement | null>(null)
  const headRefs = useRef<(HTMLTableCellElement | null)[]>([])
  const dayCardRefs = useRef<(HTMLDivElement | null)[]>([])
  if (headRefs.current.length !== weekdayBackend.length)
    headRefs.current = Array(weekdayBackend.length).fill(null)
  if (dayCardRefs.current.length !== weekdayBackend.length)
    dayCardRefs.current = Array(weekdayBackend.length).fill(null)
  const mainAlignClass = "mx-auto w-full max-w-[980px] px-4 sm:px-8 lg:px-16"
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

  const badgeGhostClass =
    "inline-flex items-center rounded-ue-pill border border-[color:var(--btn-border)] bg-[color:var(--btn-bg)] px-3 py-1.5 text-[clamp(0.78rem,0.7rem+0.35vw,0.98rem)] font-semibold tracking-tight text-[color:var(--nav-text)] shadow-[0_10px_24px_rgba(15,23,42,0.08)]"

  const headerCardClass =
    "rounded-ue-xl border border-[color:var(--btn-border)] bg-[color:color-mix(in_srgb,var(--card-bg)_96%,white_4%)] px-5 py-4 shadow-[0_12px_36px_rgba(15,23,42,0.14),0_4px_16px_rgba(15,23,42,0.08)]"

  const iconButtonClass =
    "inline-flex h-8 w-8 items-center justify-center rounded-full border border-[color:var(--btn-border)] bg-[color:var(--card-bg)] text-[color:var(--nav-link)] shadow-[0_6px_18px_rgba(15,23,42,0.12)] transition focus-visible:outline-none focus-visible:shadow-focus hover:bg-[color:var(--option-bg)]"

  const chipBaseClass =
    "inline-flex items-center gap-1.5 rounded-ue-pill border border-[color:var(--btn-border)] bg-[color:var(--card-bg)] px-3 py-1 text-[0.78rem] font-semibold tracking-tight text-[color:var(--page-text)] shadow-[0_8px_20px_rgba(15,23,42,0.12)]"

  const inputClass =
    "w-full rounded-ue-lg border border-[color:var(--btn-border)] bg-[color:color-mix(in_srgb,var(--card-bg)_94%,white_6%)] px-3 py-2.5 text-[color:var(--page-text)] shadow-[inset_0_1px_0_rgba(255,255,255,0.08)] transition focus:border-[color:var(--nav-link)] focus:outline-none focus:shadow-focus placeholder:text-[color:var(--placeholder-fg)]"

  const headerActions = (
    <div className="flex flex-wrap items-center gap-3 text-[color:var(--page-text)]">
      <span className="text-sm font-semibold uppercase tracking-[0.14em] text-[color:var(--secondary-text)]">
        {t("schedule:week.label")}
      </span>
      <Button
        size="sm"
        variant={currentParity === "odd" ? "solid" : "outline"}
        className={cn(
          "rounded-ue-full px-4",
          currentParity === "odd"
            ? "shadow-[0_10px_22px_rgba(37,99,235,0.28)]"
            : "border-[color:var(--btn-border)] bg-[color:var(--option-bg)] text-[color:var(--page-text)]"
        )}
        onClick={() => setCurrentParity("odd")}
      >
        {t("schedule:week.odd")}
      </Button>
      <Button
        size="sm"
        variant={currentParity === "even" ? "solid" : "outline"}
        className={cn(
          "rounded-ue-full px-4",
          currentParity === "even"
            ? "shadow-[0_10px_22px_rgba(37,99,235,0.28)]"
            : "border-[color:var(--btn-border)] bg-[color:var(--option-bg)] text-[color:var(--page-text)]"
        )}
        onClick={() => setCurrentParity("even")}
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
      <div className="pointer-events-none absolute -top-2.5 left-1/2 z-30 -translate-x-1/2">
        <Chip size="sm" className={cn(chipBaseClass, "chip-break !px-3 !py-1 text-[0.72rem]")}>
          {t("schedule:break", { minutes: gap })}
        </Chip>
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
    <button
      type="button"
      onClick={onOpen}
      className={cn(
        "group relative flex min-h-[148px] w-full cursor-pointer flex-col rounded-ue-lg border border-[color:var(--btn-border)] bg-[color:var(--option-bg)] px-5 pb-4 pt-3 text-left text-[color:var(--page-text)] shadow-[var(--option-shadow)] transition-[transform,box-shadow] duration-200 ease-out",
        "hover:-translate-y-[1px] hover:shadow-[0_12px_32px_rgba(15,23,42,0.18),0_3px_12px_rgba(15,23,42,0.12)] focus-visible:outline-none focus-visible:shadow-focus",
        hasBreakBefore ? "mt-6" : ""
      )}
      title={isConflict ? t("schedule:lesson.conflict") : undefined}
    >
      <span
        aria-hidden
        className="absolute -left-[1px] top-0 h-full w-1.5 rounded-bl-ue-lg rounded-tl-ue-lg"
        style={{ background: getLessonTypeColor(lesson.lesson_type) }}
      />
      <div className="flex flex-col gap-2">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <Chip
            size="sm"
            className={cn(
              "chip-type !border-transparent !px-3 !py-1 text-[0.72rem] font-semibold uppercase tracking-tight text-white shadow-[0_12px_24px_rgba(15,23,42,0.14)]",
              chipBaseClass
            )}
            style={{
              background: getLessonTypeColor(lesson.lesson_type),
              color: "#fff",
            }}
          >
            {lessonTypeLabels.get(lesson.lesson_type ?? "") ?? lesson.lesson_type ?? ""}
          </Chip>
          <Chip
            size="sm"
            className={cn(
              chipBaseClass,
              "chip-time !border-[color:var(--btn-border)] !bg-[color:var(--table-header-bg)] !px-3 !py-1 text-[0.72rem]"
            )}
            leadingIcon={<AccessTimeIcon style={{ fontSize: 16 }} />}
          >
            {`${getTimeStr(lesson)}–${getEndTimeStr(lesson)}`}
          </Chip>
        </div>
        <h3 className="line-clamp-2 text-[1.02rem] font-semibold leading-snug text-[color:var(--page-text)]">
          {lesson.subject}
        </h3>
        <div className="flex flex-wrap items-center gap-2">
          <Chip
            as="span"
            size="sm"
            className={cn(
              chipBaseClass,
              "!border-[color:var(--btn-border)] !bg-transparent !px-3 !py-1 text-[0.72rem]"
            )}
            leadingIcon={<SchoolIcon fontSize="small" />}
          >
            {lesson.teacher}
          </Chip>
          <Chip
            as="span"
            size="sm"
            className={cn(
              chipBaseClass,
              "!border-[color:var(--btn-border)] !bg-transparent !px-3 !py-1 text-[0.72rem]"
            )}
            leadingIcon={<RoomIcon fontSize="small" />}
          >
            {lesson.room}
          </Chip>
        </div>
      </div>
      <Tooltip content={t("schedule:lesson.details")}>
        <span className="pointer-events-none absolute bottom-3 right-3 text-[color:var(--secondary-text)]">
          <InfoOutlinedIcon style={{ fontSize: 18 }} />
        </span>
      </Tooltip>
      {(user?.role === "admin" || user?.role === "teacher") && (
        <button
          type="button"
          aria-label={t("schedule:aria.deleteLesson")}
          className={cn(
            iconButtonClass,
            "absolute right-3 top-3 z-20 h-8 w-8 bg-[color:var(--card-bg)] text-[color:var(--danger-text,#ef4444)]"
          )}
          onClick={(e) => {
            e.stopPropagation()
            onDelete()
          }}
        >
          <DeleteIcon fontSize="small" className="text-[color:var(--danger-text,#ef4444)]" />
        </button>
      )}
      {isConflict && (
        <div className="pointer-events-none absolute inset-0 rounded-ue-lg ring-[3px] ring-[rgba(239,83,80,0.3)]" />
      )}
    </button>
  )

  const renderTable = () => {
    const visibleRows = tableRows.slice(0, rowLimit)
    return (
      <div
        ref={tableScrollRef}
        className="schedule-table-container relative mx-auto w-full max-w-[min(98vw,1920px)] overflow-x-auto rounded-ue-2xl border border-[color:var(--btn-border)] bg-[color:var(--card-bg)] text-[color:var(--page-text)] shadow-[0_24px_56px_rgba(15,23,42,0.16)]"
        style={{ minHeight: 360 }}
      >
        <table className="schedule-table w-full border-collapse text-[0.97rem]">
          <thead className="sticky top-0 z-40 bg-[color:var(--table-header-bg)]">
            <tr>
              <th className="sticky left-0 z-50 min-w-[58px] border-b border-[color:var(--glass-border)] bg-[color:var(--table-header-bg)] px-4 py-3 text-center text-[clamp(0.98rem,1.7vw,1.13rem)] font-semibold uppercase tracking-wide">
                №
              </th>
              {weekdayBackend.map((day, idx) => {
                const label = weekdayLabels[idx] ?? day
                const isToday = hasToday && idx === todayIdx
                return (
                  <th
                    key={day}
                    ref={(el: HTMLTableCellElement | null) => {
                      headRefs.current[idx] = el
                    }}
                    className={cn(
                      "schedule-table-head sticky top-0 z-40 border-b border-[color:var(--glass-border)] px-4 py-3 text-center text-[clamp(0.97rem,1.4vw,1.11rem)] font-semibold uppercase tracking-wide transition-colors duration-200",
                      isToday
                        ? "bg-[color:var(--table-row-today)] shadow-[inset_0_0_0_1px_rgba(37,99,235,0.22)]"
                        : "bg-[color:var(--table-header-bg)]"
                    )}
                  >
                    <div className="flex items-center justify-center gap-2">
                      <span>{label}</span>
                      {(user?.role === "admin" || user?.role === "teacher") && (
                        <button
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation()
                            setAddDay(day)
                            setAddDialogOpen(true)
                          }}
                          className={cn(
                            iconButtonClass,
                            "ml-1 h-7 w-7 border-[color:var(--btn-border)] bg-[color:var(--card-bg)]"
                          )}
                          aria-label={t("schedule:aria.addLesson", { day: label })}
                        >
                          <AddIcon fontSize="small" />
                        </button>
                      )}
                    </div>
                  </th>
                )
              })}
            </tr>
          </thead>
          <tbody>
            {visibleRows.length === 0 ? (
              <tr>
                <td
                  className="px-6 py-14 text-center text-[color:var(--secondary-text)]"
                  colSpan={weekdayBackend.length + 1}
                >
                  {t("schedule:table.noLessons")}
                </td>
              </tr>
            ) : (
              visibleRows.map((row, rowIdx) => (
                <tr
                  key={rowIdx}
                  className="group transition-colors duration-200 hover:bg-[color:var(--table-row-hover)]"
                >
                  <th className="sticky left-0 z-30 border-b border-[color:var(--glass-border)] bg-[color:var(--table-header-bg)] px-4 py-3 text-center text-[clamp(0.98rem,1.7vw,1.13rem)] font-semibold">
                    {rowIdx + 1}
                  </th>
                  {row.map((lesson, colIdx) => {
                    const colIsToday = hasToday && colIdx === todayIdx
                    const cellClass = cn(
                      "schedule-table-cell relative border-b border-[color:var(--glass-border)] px-3 py-3 align-top transition-colors duration-200",
                      colIsToday ? "bg-[color:var(--table-row-today)]" : "bg-transparent"
                    )
                    if (!lesson) {
                      return (
                        <td key={`empty-${rowIdx}-${colIdx}`} className={cellClass}>
                          <div className="min-h-[148px] rounded-ue-lg border border-dashed border-[color:var(--glass-border)]" />
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
                      <td key={lesson.id ?? `${rowIdx}-${colIdx}`} className={cellClass}>
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
    <div className="flex w-full gap-2 overflow-x-auto pb-2 pl-1 pr-1">
      {weekdayBackend.map((day, i) => {
        const isToday = hasToday && i === todayIdx
        return (
          <Chip
            key={day}
            as="button"
            type="button"
            size="sm"
            className={cn(
              chipBaseClass,
              "chip-day flex-shrink-0 !px-3 !py-1 text-[0.75rem]",
              isToday
                ? "shadow-[0_12px_28px_rgba(37,99,235,0.32)]"
                : "border-[color:var(--btn-border)] bg-[color:var(--card-bg)]"
            )}
            onClick={() =>
              dayCardRefs.current[i]?.scrollIntoView({ behavior: "smooth", block: "start" })
            }
          >
            {weekdayShort[i] ?? getDayLabel(day)}
          </Chip>
        )
      })}
    </div>
  )

  const renderMobileCards = () => (
    <div className="mt-2 flex w-full flex-col gap-4">
      {renderMobileDayAnchors()}
      {weekdayBackend.map((day, dayIdx) => {
        const label = weekdayLabels[dayIdx] ?? day
        const lessons = filteredSchedule
          .filter((l) => l.weekday === day)
          .sort((a, b) => getTimeStr(a).localeCompare(getTimeStr(b)))
        return (
          <section
            key={day}
            ref={(el: HTMLDivElement | null) => {
              dayCardRefs.current[dayIdx] = el
            }}
            className={cn(
              "rounded-ue-2xl border border-[color:var(--btn-border)] bg-[color:var(--card-bg)] p-4 shadow-[0_10px_30px_rgba(15,23,42,0.16),0_3px_12px_rgba(15,23,42,0.08)]",
              hasToday && dayIdx === todayIdx ? "bg-[color:var(--table-row-today)]" : ""
            )}
          >
            <div className="mb-3 flex items-center gap-2">
              <h3 className="text-[1.12rem] font-semibold text-[color:var(--page-text)]">{label}</h3>
              {(user?.role === "admin" || user?.role === "teacher") && (
                <button
                  type="button"
                  className={cn(
                    iconButtonClass,
                    "ml-1 h-7 w-7 border-[color:var(--btn-border)] bg-[color:var(--card-bg)]"
                  )}
                  onClick={(e) => {
                    e.stopPropagation()
                    setAddDay(day)
                    setAddDialogOpen(true)
                  }}
                  aria-label={t("schedule:aria.addLesson", { day: label })}
                >
                  <AddIcon fontSize="small" />
                </button>
              )}
            </div>
            {lessons.length === 0 ? (
              <p className="text-[color:var(--secondary-text)]">
                {t("schedule:mobile.noLessons")}
              </p>
            ) : (
              <div className="flex flex-col gap-3">
                {lessons.map((lesson, idx) => {
                  const prev = lessons[idx - 1]
                  const gap = prev ? minutesDiff(prev.end_time, lesson.start_time) : 0
                  return (
                    <div key={lesson.id} className="space-y-2">
                      {idx > 0 && gap > 0 ? (
                        <Chip
                          size="sm"
                          className={cn(chipBaseClass, "chip-break !px-3 !py-1 text-[0.72rem]")}
                        >
                          {t("schedule:break", { minutes: gap })}
                        </Chip>
                      ) : null}
                      <button
                        type="button"
                        onClick={() => {
                          setDialogLesson(lesson)
                          setOpenDialog(true)
                        }}
                        className="group relative w-full rounded-ue-xl border border-[color:var(--btn-border)] bg-[color:var(--option-bg)] px-4 py-3 text-left text-[color:var(--page-text)] shadow-[var(--option-shadow)] transition-[transform,box-shadow,background-color] duration-200 ease-out hover:-translate-y-[1px] hover:bg-[color:var(--option-hover-bg)] hover:shadow-[0_12px_32px_rgba(15,23,42,0.18)] focus-visible:outline-none focus-visible:shadow-focus"
                      >
                        <span
                          aria-hidden
                          className="absolute left-0 top-0 h-full w-1.5 rounded-bl-ue-xl rounded-tl-ue-xl"
                          style={{ background: getLessonTypeColor(lesson.lesson_type) }}
                        />
                        <div className="flex flex-wrap items-center gap-2 pl-2">
                          <Chip
                            size="sm"
                            className={cn(
                              chipBaseClass,
                              "chip-type !border-transparent !px-3 !py-1 text-[0.72rem] font-semibold uppercase text-white"
                            )}
                            style={{
                              background: getLessonTypeColor(lesson.lesson_type),
                              color: "#fff",
                            }}
                          >
                            {lessonTypeLabels.get(lesson.lesson_type ?? "") ?? lesson.lesson_type ?? ""}
                          </Chip>
                          <Chip
                            size="sm"
                            className={cn(
                              chipBaseClass,
                              "chip-time !border-[color:var(--btn-border)] !bg-[color:var(--table-header-bg)] !px-3 !py-1 text-[0.72rem]"
                            )}
                            leadingIcon={<AccessTimeIcon style={{ fontSize: 16 }} />}
                          >
                            {`${getTimeStr(lesson)}–${getEndTimeStr(lesson)}`}
                          </Chip>
                        </div>
                        <h4 className="pl-2 pt-2 text-[1.02rem] font-semibold leading-snug text-[color:var(--page-text)]">
                          {lesson.subject}
                        </h4>
                        <div className="flex flex-wrap items-center gap-2 pl-2 pt-2">
                          <Chip
                            size="sm"
                            className={cn(
                              chipBaseClass,
                              "!border-[color:var(--btn-border)] !bg-transparent !px-3 !py-1 text-[0.72rem]"
                            )}
                            leadingIcon={<SchoolIcon fontSize="small" />}
                          >
                            {lesson.teacher}
                          </Chip>
                          <Chip
                            size="sm"
                            className={cn(
                              chipBaseClass,
                              "!border-[color:var(--btn-border)] !bg-transparent !px-3 !py-1 text-[0.72rem]"
                            )}
                            leadingIcon={<RoomIcon fontSize="small" />}
                          >
                            {lesson.room}
                          </Chip>
                        </div>
                      </button>
                    </div>
                  )
                })}
              </div>
            )}
          </section>
        )
      })}
    </div>
  )

  if (loading)
    return (
      <Layout>
        <div className="flex min-h-[70vh] items-center justify-center text-[color:var(--page-text)]">
          {t("common:statuses.loading")}
        </div>
      </Layout>
    )

  return (
    <Layout>

      <PageFadeIn>
        <style>{`
        @media print {
          body { background: #fff !important; color: #000 !important; }
          .no-print { display: none !important; }
          .schedule-table-container { box-shadow: none !important; border: 1px solid #999 !important; }
          .schedule-table { border-collapse: collapse !important; }
          .schedule-table th,
          .schedule-table td { border: 1px solid #999 !important; color: #000 !important; }
          .schedule-table thead th { background: #eee !important; color: #000 !important; }
        }
      `}</style>
        <div className="min-h-[100vh] w-full bg-[color:var(--page-bg)] pb-16 pt-12 text-[color:var(--page-text)]">
          <div className={cn(mainAlignClass, "space-y-6")}>
            <div
              data-fade
              style={{ "--fade-delay": "80ms" } as CSSProperties}
              className="flex flex-wrap items-center gap-3"
            >
              <span className="flex h-12 w-12 items-center justify-center rounded-ue-xl border border-[color:var(--btn-border)] bg-[color:color-mix(in_srgb,var(--card-bg)_96%,white_4%)] text-[color:var(--nav-link)] shadow-[0_18px_40px_rgba(37,99,235,0.22)]">
                <CalendarMonthIcon style={{ fontSize: 30 }} />
              </span>
              <h1 className="text-[clamp(1.8rem,4vw,2.7rem)] font-bold text-[color:var(--nav-link)]">
                {user?.role === "student"
                  ? t("schedule:title.student")
                  : t("schedule:title.default")}
              </h1>
              <span className={cn(badgeGhostClass, "translate-y-[8px]")}>{todayLabel}</span>
              {activeGroupName ? (
                <span className={cn(badgeGhostClass, "translate-y-[8px]")}>
                  {t("schedule:header.groupName", { name: activeGroupName })}
                </span>
              ) : null}
            </div>

            <div
              data-fade
              style={{ "--fade-delay": "140ms" } as CSSProperties}
            >
              {headerActions}
            </div>

            <div
              data-fade
              style={{ "--fade-delay": "200ms" } as CSSProperties}
              className={cn("no-print", headerCardClass, "space-y-3")}
            >
              {currentLesson ? (
                <div className="space-y-3">
                  <div className="flex flex-wrap items-center gap-2">
                    <Chip size="sm" className={cn(chipBaseClass, "chip-clock !px-3 !py-1 text-[0.72rem]")}>
                      {t("schedule:chips.current")}
                    </Chip>
                    <Chip
                      size="sm"
                      className={cn(
                        chipBaseClass,
                        "chip-time !border-[color:var(--btn-border)] !bg-[color:var(--table-header-bg)] !px-3 !py-1 text-[0.72rem]"
                      )}
                    >
                      {`${getTimeStr(currentLesson)}–${getEndTimeStr(currentLesson)}`}
                    </Chip>
                    <span className="text-[1.05rem] font-semibold text-[color:var(--page-text)]">
                      {currentLesson.subject}
                    </span>
                    {timeLeftText ? (
                      <Chip
                        size="sm"
                        className={cn(chipBaseClass, "chip-left !px-3 !py-1 text-[0.72rem]")}
                      >
                        {timeLeftText}
                      </Chip>
                    ) : null}
                  </div>
                  <div className="flex flex-wrap items-center gap-2">
                    <Chip
                      size="sm"
                      className={cn(
                        chipBaseClass,
                        "!border-[color:var(--btn-border)] !bg-transparent !px-3 !py-1 text-[0.72rem]"
                      )}
                      leadingIcon={<SchoolIcon fontSize="small" />}
                    >
                      {currentLesson.teacher}
                    </Chip>
                    <Chip
                      size="sm"
                      className={cn(
                        chipBaseClass,
                        "!border-[color:var(--btn-border)] !bg-transparent !px-3 !py-1 text-[0.72rem]"
                      )}
                      leadingIcon={<RoomIcon fontSize="small" />}
                    >
                      {currentLesson.room}
                    </Chip>
                  </div>
                  <ProgressBar
                    value={currentProgress}
                    className="h-2.5 rounded-ue-pill bg-[color:var(--progress-track)]"
                    barClassName="bg-[color:var(--progress-bar)]"
                    ariaLabel={t("schedule:aria.currentProgress")}
                  />
                </div>
              ) : nextLesson ? (
                <div className="flex flex-wrap items-center gap-2">
                  <Chip size="sm" className={cn(chipBaseClass, "chip-clock !px-3 !py-1 text-[0.72rem]")}>
                    {t("schedule:chips.next")}
                  </Chip>
                  <Chip
                    size="sm"
                    className={cn(
                      chipBaseClass,
                      "chip-time !border-[color:var(--btn-border)] !bg-[color:var(--table-header-bg)] !px-3 !py-1 text-[0.72rem]"
                    )}
                  >
                    {`${getTimeStr(nextLesson)}–${getEndTimeStr(nextLesson)}`}
                  </Chip>
                  <span className="text-[1.05rem] font-semibold text-[color:var(--page-text)]">
                    {nextLesson.subject}
                  </span>
                  {timeLeftText ? (
                    <Chip
                      size="sm"
                      className={cn(chipBaseClass, "chip-left !px-3 !py-1 text-[0.72rem]")}
                    >
                      {timeLeftText}
                    </Chip>
                  ) : null}
                </div>
              ) : (
                <p className="text-[color:var(--secondary-text)]">
                  {t("schedule:summary.noMoreToday")}
                </p>
              )}
            </div>

            {(user?.role === "teacher" || user?.role === "admin") && (
              <div
                data-fade
                style={{ "--fade-delay": "240ms" } as CSSProperties}
                className="no-print w-full max-w-sm"
              >
                <label className="mb-2 block text-sm font-semibold uppercase tracking-[0.18em] text-[color:var(--secondary-text)]">
                  {t("schedule:form.groupLabel")}
                </label>
                <div className="relative">
                  <select
                    value={selectedGroup ?? ""}
                    onChange={(e) => {
                      const value = e.target.value
                      setSelectedGroup(value ? Number(value) : null)
                    }}
                    className={cn(inputClass, "appearance-none pr-10")}
                  >
                    <option value="" disabled hidden>
                      {t("schedule:form.groupLabel")}
                    </option>
                    {groups.map((g) => (
                      <option value={g.id} key={g.id}>
                        {g.name}
                      </option>
                    ))}
                  </select>
                  <span className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-[color:var(--secondary-text)]">
                    ▾
                  </span>
                </div>
              </div>
            )}
          </div>
          <div
            data-fade
            style={{ "--fade-delay": "280ms" } as CSSProperties}
            className="mx-auto mt-10 w-full max-w-[1920px] px-2 sm:px-4"
          >
            {isMobile ? renderMobileCards() : renderTable()}
          </div>
        </div>

        <Dialog
          open={openDialog}
          onClose={() => setOpenDialog(false)}
          title={dialogLesson?.subject || t("schedule:dialog.detailsFallback")}
          bodyClassName="space-y-3 text-[color:var(--page-text)]"
          footer={
            <div className="flex flex-col gap-2 sm:flex-row sm:justify-end">
              {(user?.role === "admin" || user?.role === "teacher") && (
                <Button
                  variant="outline"
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
              <Button variant="outline" onClick={() => setOpenDialog(false)}>
                {t("schedule:buttons.close")}
              </Button>
            </div>
          }
          closeLabel={t("schedule:buttons.close")}
        >
          {dialogLesson ? (
            <div className="space-y-2">
              <p>
                <span className="font-semibold">{t("schedule:dialog.typeLabel")}:</span>{" "}
                <span
                  className="inline-flex rounded-ue-pill px-3 py-1 text-sm font-semibold text-white"
                  style={{ background: getLessonTypeColor(dialogLesson.lesson_type) }}
                >
                  {lessonTypeLabels.get(dialogLesson.lesson_type ?? "") ?? dialogLesson.lesson_type ?? ""}
                </span>
              </p>
              <p>
                <span className="font-semibold">{t("schedule:dialog.timeLabel")}:</span>{" "}
                {getTimeStr(dialogLesson)}–{getEndTimeStr(dialogLesson)}
              </p>
              <p>
                <span className="font-semibold">{t("schedule:dialog.teacherLabel")}:</span>{" "}
                {dialogLesson.teacher}
              </p>
              <p>
                <span className="font-semibold">{t("schedule:dialog.roomLabel")}:</span>{" "}
                {dialogLesson.room}
              </p>
            </div>
          ) : null}
        </Dialog>

        <Dialog
          open={editing}
          onClose={() => setEditing(false)}
          title={t("schedule:dialog.editTitle")}
          bodyClassName="space-y-3"
          footer={
            <div className="flex flex-col gap-2 sm:flex-row sm:justify-end">
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
              >
                {t("common:buttons.save")}
              </Button>
              <Button variant="outline" onClick={() => setEditing(false)}>
                {t("common:buttons.cancel")}
              </Button>
            </div>
          }
        >
          {editLesson ? (
            <div className="space-y-3">
              <label className="block">
                <span className="mb-1 block text-sm font-semibold text-[color:var(--secondary-text)]">
                  {t("schedule:form.subject")}
                </span>
                <input
                  type="text"
                  className={inputClass}
                  value={editLesson.subject}
                  onChange={(e) => setEditLesson({ ...editLesson, subject: e.target.value })}
                />
              </label>
              <label className="block">
                <span className="mb-1 block text-sm font-semibold text-[color:var(--secondary-text)]">
                  {t("schedule:form.teacher")}
                </span>
                <input
                  type="text"
                  className={inputClass}
                  value={editLesson.teacher}
                  onChange={(e) => setEditLesson({ ...editLesson, teacher: e.target.value })}
                />
              </label>
              <label className="block">
                <span className="mb-1 block text-sm font-semibold text-[color:var(--secondary-text)]">
                  {t("schedule:form.room")}
                </span>
                <input
                  type="text"
                  className={inputClass}
                  value={editLesson.room}
                  onChange={(e) => setEditLesson({ ...editLesson, room: e.target.value })}
                />
              </label>
              <label className="block">
                <span className="mb-1 block text-sm font-semibold text-[color:var(--secondary-text)]">
                  {t("schedule:form.lessonType")}
                </span>
                <select
                  className={inputClass}
                  value={editLesson.lesson_type}
                  onChange={(e) => setEditLesson({ ...editLesson, lesson_type: e.target.value })}
                >
                  {editingLessonTypeOptions.map((option) => (
                    <option value={option.value} key={option.value}>
                      {option.label}
                    </option>
                  ))}
                </select>
              </label>
              <label className="block">
                <span className="mb-1 block text-sm font-semibold text-[color:var(--secondary-text)]">
                  {t("schedule:form.day")}
                </span>
                <select
                  className={inputClass}
                  value={editLesson.weekday}
                  onChange={(e) => setEditLesson({ ...editLesson, weekday: e.target.value })}
                >
                  {weekdayBackend.map((day) => (
                    <option key={day} value={day}>
                      {getDayLabel(day)}
                    </option>
                  ))}
                </select>
              </label>
              <label className="block">
                <span className="mb-1 block text-sm font-semibold text-[color:var(--secondary-text)]">
                  {t("schedule:form.startTime")}
                </span>
                <input
                  type="time"
                  className={inputClass}
                  value={getTimeStr(editLesson)}
                  onChange={(e) =>
                    setEditLesson({
                      ...editLesson,
                      start_time: `${editLesson.start_time?.slice(0, 11) || dayjs().format("YYYY-MM-DDT")}${e.target.value}:00`,
                    })
                  }
                />
              </label>
              <label className="block">
                <span className="mb-1 block text-sm font-semibold text-[color:var(--secondary-text)]">
                  {t("schedule:form.endTime")}
                </span>
                <input
                  type="time"
                  className={inputClass}
                  value={getEndTimeStr(editLesson)}
                  onChange={(e) =>
                    setEditLesson({
                      ...editLesson,
                      end_time: `${editLesson.end_time?.slice(0, 11) || dayjs().format("YYYY-MM-DDT")}${e.target.value}:00`,
                    })
                  }
                />
              </label>
              <label className="block">
                <span className="mb-1 block text-sm font-semibold text-[color:var(--secondary-text)]">
                  {t("schedule:form.week")}
                </span>
                <select
                  className={inputClass}
                  value={editLesson.parity}
                  onChange={(e) =>
                    setEditLesson((prev) =>
                      prev ? { ...prev, parity: e.target.value as LessonParity } : prev
                    )
                  }
                >
                  <option value="both">{t("schedule:week.both")}</option>
                  <option value="odd">{t("schedule:week.odd")}</option>
                  <option value="even">{t("schedule:week.even")}</option>
                </select>
              </label>
            </div>
          ) : null}
        </Dialog>

        <Dialog
          open={addDialogOpen}
          onClose={() => setAddDialogOpen(false)}
          title={`${t("schedule:dialog.addTitle")}${addDayLabel ? " (" + addDayLabel + ")" : ""}`}
          bodyClassName="space-y-3"
          footer={
            <div className="flex flex-col gap-2 sm:flex-row sm:justify-end">
              <Button variant="solid" onClick={handleAddLesson}>
                {t("schedule:buttons.add")}
              </Button>
              <Button variant="outline" onClick={() => setAddDialogOpen(false)}>
                {t("common:buttons.cancel")}
              </Button>
            </div>
          }
        >
          <div className="space-y-3">
            <label className="block">
              <span className="mb-1 block text-sm font-semibold text-[color:var(--secondary-text)]">
                {t("schedule:form.subject")}
              </span>
              <input
                type="text"
                className={inputClass}
                value={addFields.subject}
                onChange={(e) => setAddFields({ ...addFields, subject: e.target.value })}
              />
            </label>
            <label className="block">
              <span className="mb-1 block text-sm font-semibold text-[color:var(--secondary-text)]">
                {t("schedule:form.teacher")}
              </span>
              <input
                type="text"
                className={inputClass}
                value={addFields.teacher}
                onChange={(e) => setAddFields({ ...addFields, teacher: e.target.value })}
              />
            </label>
            <label className="block">
              <span className="mb-1 block text-sm font-semibold text-[color:var(--secondary-text)]">
                {t("schedule:form.room")}
              </span>
              <input
                type="text"
                className={inputClass}
                value={addFields.room}
                onChange={(e) => setAddFields({ ...addFields, room: e.target.value })}
              />
            </label>
            <label className="block">
              <span className="mb-1 block text-sm font-semibold text-[color:var(--secondary-text)]">
                {t("schedule:form.lessonType")}
              </span>
              <select
                className={inputClass}
                value={addFields.lessonType}
                onChange={(e) => setAddFields({ ...addFields, lessonType: e.target.value })}
              >
                {lessonTypeOptions.map((option) => (
                  <option value={option.value} key={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </label>
            <label className="block">
              <span className="mb-1 block text-sm font-semibold text-[color:var(--secondary-text)]">
                {t("schedule:form.startTime")}
              </span>
              <input
                type="time"
                className={inputClass}
                value={addFields.startTime}
                onChange={(e) => setAddFields({ ...addFields, startTime: e.target.value })}
              />
            </label>
            <label className="block">
              <span className="mb-1 block text-sm font-semibold text-[color:var(--secondary-text)]">
                {t("schedule:form.endTime")}
              </span>
              <input
                type="time"
                className={inputClass}
                value={addFields.endTime}
                onChange={(e) => setAddFields({ ...addFields, endTime: e.target.value })}
              />
            </label>
            <label className="block">
              <span className="mb-1 block text-sm font-semibold text-[color:var(--secondary-text)]">
                {t("schedule:form.week")}
              </span>
              <select
                className={inputClass}
                value={addFields.parity}
                onChange={(e) =>
                  setAddFields((prev) => ({ ...prev, parity: e.target.value as LessonParity }))
                }
              >
                <option value="both">{t("schedule:week.both")}</option>
                <option value="odd">{t("schedule:week.odd")}</option>
                <option value="even">{t("schedule:week.even")}</option>
              </select>
            </label>
          </div>
        </Dialog>

        {snack ? (
          <div
            role="status"
            aria-live="polite"
            className="pointer-events-none fixed inset-x-0 bottom-6 z-[var(--ue-z-index-toast,1800)] flex justify-center"
          >
            <button
              type="button"
              onClick={() => setSnack("")}
              className="pointer-events-auto rounded-ue-lg border border-[color:var(--btn-border)] bg-[color:color-mix(in_srgb,var(--card-bg)_96%,white_4%)] px-4 py-2 text-sm font-semibold text-[color:var(--page-text)] shadow-[0_20px_40px_rgba(15,23,42,0.22)] focus-visible:outline-none focus-visible:shadow-focus"
            >
              {snack}
            </button>
          </div>
        ) : null}
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
