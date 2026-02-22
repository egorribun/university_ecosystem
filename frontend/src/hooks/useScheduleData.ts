import { useState, useEffect, useMemo, useCallback } from "react"
import { useQuery, useQueryClient } from "@tanstack/react-query"
import { useTranslation } from "react-i18next"
import api from "@/api/client"
import { useAuth } from "@/contexts/AuthContext"
import {
  type Lesson,
  type ScheduleGroup,
  type WeekdayConfig,
  type LessonTypeConfig,
  scheduleGroupsQueryKey,
  scheduleQueryKey,
  groupsStorageKey,
  scheduleStorageKey,
  GROUPS_STORAGE_TTL_MS,
  SCHEDULE_STORAGE_TTL_MS,
  readFromStorage,
  writeToStorage,
  minimalWeekdayFallback,
  minimalLessonTypeFallback,
  defaultLessonTypeColor,
  type ScheduleGroupsQueryKey,
  type ActiveScheduleQueryKey,
  type InactiveScheduleQueryKey,
  parseMinutes,
  getTodayIdx,
  getTimeStr,
} from "@/components/schedule/scheduleUtils"

const QUERY_STALE_TIME_MS = 60_000
const QUERY_GC_TIME_MS = 5 * 60_000
const TICKER_INTERVAL_MS = 30_000

export function useScheduleData() {
  const { user } = useAuth()
  const queryClient = useQueryClient()
  const { t } = useTranslation(["schedule", "common"])
  const [selectedGroup, setSelectedGroup] = useState<string | null>(null)
  const [currentParity, setCurrentParity] = useState<"odd" | "even">("odd")
  const [nowTick, setNowTick] = useState(new Date())

  // Update time ticker
  // Update time ticker
  useEffect(() => {
    const id = setInterval(() => setNowTick(new Date()), TICKER_INTERVAL_MS)
    return () => clearInterval(id)
  }, [])

  const minutesNow = useMemo(() => nowTick.getHours() * 60 + nowTick.getMinutes(), [nowTick])

  // ============================================================================
  // CONFIGURATION (Weekdays & Lesson Types)
  // ============================================================================

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

  // ============================================================================
  // DATA FETCHING (Groups & Schedule)
  // ============================================================================

  const groupsStorageSnapshot = useMemo(
    () =>
      readFromStorage<ScheduleGroup[]>(groupsStorageKey, {
        maxAgeMs: GROUPS_STORAGE_TTL_MS,
      }),
    []
  )

  const groupsQuery = useQuery<ScheduleGroup[], Error, ScheduleGroup[], ScheduleGroupsQueryKey>({
    queryKey: scheduleGroupsQueryKey,
    queryFn: async () => {
      const res = await api.get("/groups")
      return Array.isArray(res.data) ? res.data : []
    },
    enabled: Boolean(user),
    staleTime: QUERY_STALE_TIME_MS,
    gcTime: QUERY_GC_TIME_MS,
    networkMode: "online",
    retry: 1,
    ...(groupsStorageSnapshot && {
      initialData: groupsStorageSnapshot.value,
      initialDataUpdatedAt: groupsStorageSnapshot.timestamp,
    }),
  })
  const groups = groupsQuery.data ?? []

  // Sync groups storage
  useEffect(() => {
    if (typeof window === "undefined") return
    if (!user) return
    if (!groupsQuery.dataUpdatedAt) return
    if (groupsQuery.isFetching) return
    const age = Date.now() - groupsQuery.dataUpdatedAt
    if (age >= GROUPS_STORAGE_TTL_MS) {
      queryClient.invalidateQueries({
        queryKey: scheduleGroupsQueryKey,
        exact: true,
        refetchType: "active",
      })
      return
    }
    const timeout = window.setTimeout(() => {
      queryClient.invalidateQueries({
        queryKey: scheduleGroupsQueryKey,
        exact: true,
        refetchType: "active",
      })
    }, GROUPS_STORAGE_TTL_MS - age)
    return () => window.clearTimeout(timeout)
  }, [groupsQuery.dataUpdatedAt, groupsQuery.isFetching, queryClient, user])

  useEffect(() => {
    if (!groupsQuery.isSuccess) return
    writeToStorage(groupsStorageKey, groupsQuery.data)
  }, [groupsQuery.data, groupsQuery.isSuccess])

  const activeGroupId = selectedGroup
  const scheduleKey = activeGroupId != null ? scheduleQueryKey(activeGroupId) : null

  const scheduleStorageSnapshot = useMemo(() => {
    if (activeGroupId == null) return undefined
    return readFromStorage<Lesson[]>(scheduleStorageKey(activeGroupId), {
      maxAgeMs: SCHEDULE_STORAGE_TTL_MS,
    })
  }, [activeGroupId])

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
    placeholderData: (previous) => {
      if (previous !== undefined) return previous
      return scheduleStorageSnapshot?.value
    },
    staleTime: QUERY_STALE_TIME_MS,
    gcTime: QUERY_GC_TIME_MS,
    networkMode: "online",
    retry: 1,
    ...(scheduleStorageSnapshot && {
      initialData: scheduleStorageSnapshot.value,
      initialDataUpdatedAt: scheduleStorageSnapshot.timestamp,
    }),
  })

  // Sync schedule storage
  useEffect(() => {
    if (typeof window === "undefined") return
    if (!scheduleKey) return
    if (!scheduleQuery.dataUpdatedAt) return
    if (scheduleQuery.isFetching) return
    const age = Date.now() - scheduleQuery.dataUpdatedAt
    if (age >= SCHEDULE_STORAGE_TTL_MS) {
      queryClient.invalidateQueries({
        queryKey: scheduleKey,
        exact: true,
        refetchType: "active",
      })
      return
    }
    const timeout = window.setTimeout(() => {
      queryClient.invalidateQueries({
        queryKey: scheduleKey,
        exact: true,
        refetchType: "active",
      })
    }, SCHEDULE_STORAGE_TTL_MS - age)
    return () => window.clearTimeout(timeout)
  }, [queryClient, scheduleKey, scheduleQuery.dataUpdatedAt, scheduleQuery.isFetching])

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

  // Select group based on user role
  useEffect(() => {
    if (!user) return
    if (groups.length === 0) return

    if (user.role === "student" && user.group_id) {
      // Check if user's group exists in available groups
      const userGroupExists = groups.some((g) => g.id === user.group_id)
      if (userGroupExists) {
        setSelectedGroup((prev) => prev ?? user.group_id ?? null)
      } else {
        // Fallback to first available group if user's group doesn't exist
        setSelectedGroup((prev) => prev ?? groups[0]?.id ?? null)
      }
    } else if (user.role === "teacher" || user.role === "admin") {
      setSelectedGroup((prev) => prev ?? groups[0]?.id ?? null)
    } else {
      // Fallback for any other case (e.g., student without group_id)
      setSelectedGroup((prev) => prev ?? groups[0]?.id ?? null)
    }
  }, [user, groups])

  // Filter schedule
  const filteredSchedule = useMemo(
    () => groupSchedule.filter((l) => l.parity === "both" || l.parity === currentParity),
    [groupSchedule, currentParity]
  )

  const todayIdx = getTodayIdx()
  const hasToday = todayIdx >= 0 && todayIdx < weekdayBackend.length

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

  // Conflict detection
  const conflictedIds = useMemo(() => {
    const byDay = new Map<string, Lesson[]>()
    for (const l of filteredSchedule) {
      const arr = byDay.get(l.weekday) ?? []
      arr.push(l)
      byDay.set(l.weekday, arr)
    }
    const set = new Set<string>()
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

  const toBackendLessonType = useCallback(
    (value?: string | null) => {
      if (!value) return ""
      const match = lessonTypeById.get(value)
      if (match) return match.backend[0] ?? value
      return value
    },
    [lessonTypeById]
  )

  const applyScheduleUpdate = useCallback(
    (updater: (prev: Lesson[]) => Lesson[]) => {
      if (!scheduleKey || activeGroupId == null) return
      queryClient.setQueryData<Lesson[]>(scheduleKey, (prev) => {
        const base = Array.isArray(prev) ? [...prev] : []
        const next = normalizeLessons(updater(base))
        writeToStorage(scheduleStorageKey(activeGroupId), next)
        return next
      })
    },
    [scheduleKey, activeGroupId, queryClient, normalizeLessons]
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

  const timeLeftText = useMemo(() => {
    let text = ""
    if (currentLesson) {
      const end = parseMinutes(currentLesson.end_time) ?? 0
      const left = Math.max(0, end - (nowTick.getHours() * 60 + nowTick.getMinutes()))
      const h = Math.floor(left / 60)
      const m = left % 60
      text = t("schedule:timeLeft.current", { duration: formatDuration(h, m) })
    } else if (nextLesson) {
      const start = parseMinutes(nextLesson.start_time) ?? 0
      const left = Math.max(0, start - (nowTick.getHours() * 60 + nowTick.getMinutes()))
      const h = Math.floor(left / 60)
      const m = left % 60
      text = t("schedule:timeLeft.next", { duration: formatDuration(h, m) })
    }
    return text
  }, [currentLesson, nextLesson, nowTick, t, formatDuration])

  const currentProgress = useMemo(() => {
    if (!currentLesson) return 0
    const s = parseMinutes(currentLesson.start_time)
    const e = parseMinutes(currentLesson.end_time)
    if (s == null || e == null || e <= s) return 0
    const span = e - s
    const passed = Math.min(Math.max(minutesNow - s, 0), span)
    return Math.round((passed / span) * 100)
  }, [currentLesson, minutesNow])

  const refresh = useCallback(() => {
    if (scheduleKey) {
      queryClient.invalidateQueries({ queryKey: scheduleKey })
    }
  }, [queryClient, scheduleKey])

  return {
    user,
    groups,
    selectedGroup,
    setSelectedGroup,
    currentParity,
    setCurrentParity,
    schedule: filteredSchedule,
    rawSchedule: groupSchedule,
    isLoading: groupsQuery.isLoading || scheduleQuery.isLoading,
    refresh,
    applyScheduleUpdate,

    // Config
    weekdayConfigs,
    weekdayBackend,
    weekdayLabels,
    weekdayShort,
    getDayLabel,
    lessonTypeConfigs,
    lessonTypeOptions,
    lessonTypeLabels,
    defaultLessonType,
    getLessonTypeColor,
    toBackendLessonType,

    // Time/State
    todayIdx,
    hasToday,
    nowTick,
    todayLessons,
    currentLesson,
    nextLesson,
    conflictedIds,
    timeLeftText,
    currentProgress,
  }
}
