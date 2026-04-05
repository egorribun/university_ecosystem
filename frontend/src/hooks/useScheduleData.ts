/**
 * useScheduleData — Orchestrator hook for the Schedule page.
 * Wave 65: Split into useScheduleConfig (i18n config) + useScheduleTime (ticker).
 *
 * Public API is UNCHANGED — all consumers still import `useScheduleData`
 * and destructure the same fields.
 */
import { useState, useEffect, useMemo, useCallback } from "react"
import { useQuery, useQueryClient } from "@tanstack/react-query"
import api from "@/api/client"
import { useAuth } from "@/contexts/AuthContext"
import {
  type Lesson,
  type ScheduleGroup,
  scheduleGroupsQueryKey,
  scheduleQueryKey,
  type ScheduleGroupsQueryKey,
  type ActiveScheduleQueryKey,
  type InactiveScheduleQueryKey,
  getTodayIdx,
  getTimeStr,
} from "@/components/schedule/scheduleUtils"
import { detectConflicts } from "@/utils/scheduleConflicts"
import { useScheduleConfig } from "./useScheduleConfig"
import { useScheduleTime } from "./useScheduleTime"

const QUERY_STALE_TIME_MS = 60_000
const QUERY_GC_TIME_MS = 5 * 60_000

/** Exponential backoff for flaky mobile connections (FIX-68-05). */
const retryDelay = (attempt: number) => Math.min(1_000 * 2 ** attempt, 10_000)

export function useScheduleData() {
  const { user } = useAuth()
  const queryClient = useQueryClient()
  const [selectedGroup, setSelectedGroup] = useState<string | null>(null)
  const [currentParity, setCurrentParity] = useState<"odd" | "even">("odd")

  // ── Config (i18n weekdays + lesson types) ──────────
  const config = useScheduleConfig()
  const {
    weekdayBackend,
    normalizeLessons,
  } = config

  // ── TanStack Query: Groups ─────────────────────────
  const groupsQuery = useQuery<ScheduleGroup[], Error, ScheduleGroup[], ScheduleGroupsQueryKey>({
    queryKey: scheduleGroupsQueryKey,
    queryFn: async () => {
      const res = await api.get("/groups")
      return Array.isArray(res.data) ? res.data : []
    },
    staleTime: QUERY_STALE_TIME_MS,
    gcTime: QUERY_GC_TIME_MS,
    networkMode: "online",
    retry: 2,
    retryDelay,
  })
  const groups = useMemo(() => groupsQuery.data ?? [], [groupsQuery.data])

  // ── TanStack Query: Schedule ───────────────────────
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
    staleTime: QUERY_STALE_TIME_MS,
    gcTime: QUERY_GC_TIME_MS,
    networkMode: "online",
    retry: 2,
    retryDelay,
  })

  const groupScheduleRaw = useMemo(() => scheduleQuery.data ?? [], [scheduleQuery.data])
  const groupSchedule = useMemo(
    () => normalizeLessons(groupScheduleRaw),
    [groupScheduleRaw, normalizeLessons]
  )

  // ── Auto-select group based on user role ───────────
  useEffect(() => {
    if (!user) return
    if (groups.length === 0) return

    if (user.role === "student" && user.group_id) {
      const userGroupExists = groups.some((g) => g.id === user.group_id)
      if (userGroupExists) {
        setSelectedGroup((prev) => prev ?? user.group_id ?? null)
      } else {
        setSelectedGroup((prev) => prev ?? groups[0]?.id ?? null)
      }
    } else {
      setSelectedGroup((prev) => prev ?? groups[0]?.id ?? null)
    }
  }, [user, groups])

  // ── Parity filter ──────────────────────────────────
  const filteredSchedule = useMemo(
    () => groupSchedule.filter((l) => l.parity === "both" || l.parity === currentParity),
    [groupSchedule, currentParity]
  )

  // ── Today + time calculations ──────────────────────
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

  const time = useScheduleTime(todayLessons, hasToday)

  // ── Conflict detection ─────────────────────────────
  const conflictedIds = useMemo(
    () => detectConflicts(filteredSchedule),
    [filteredSchedule],
  )

  // ── Lesson days for MiniCalendar ───────────────────
  // PERF-70-07: use year/month primitives — only recalculates on month change, not every 30s tick
  const calYear = time.nowTick.getFullYear()
  const calMonth = time.nowTick.getMonth()
  const lessonDays = useMemo(() => {
    const days = new Set<number>()
    const firstDay = new Date(calYear, calMonth, 1).getDay()
    const weekdayToOffset = new Map<string, number>()
    for (let i = 0; i < weekdayBackend.length; i++) {
      weekdayToOffset.set(weekdayBackend[i], i)
    }
    const daysInMonth = new Date(calYear, calMonth + 1, 0).getDate()
    for (const lesson of filteredSchedule) {
      const offset = weekdayToOffset.get(lesson.weekday)
      if (offset === undefined) continue
      const jsDay = offset === 6 ? 0 : offset + 1
      const firstOccurrence = 1 + ((jsDay - firstDay + 7) % 7)
      for (let d = firstOccurrence; d <= daysInMonth; d += 7) {
        days.add(d)
      }
    }
    return days
  }, [filteredSchedule, weekdayBackend, calYear, calMonth])

  // ── Optimistic updates ─────────────────────────────
  const applyScheduleUpdate = useCallback(
    (updater: (prev: Lesson[]) => Lesson[]) => {
      if (!scheduleKey || activeGroupId == null) return
      queryClient.setQueryData<Lesson[]>(scheduleKey, (prev) => {
        const base = Array.isArray(prev) ? [...prev] : []
        return normalizeLessons(updater(base))
      })
    },
    [scheduleKey, activeGroupId, queryClient, normalizeLessons]
  )

  const refresh = useCallback(() => {
    if (scheduleKey) {
      queryClient.invalidateQueries({ queryKey: scheduleKey })
    }
  }, [queryClient, scheduleKey])

  // ── Public API (unchanged from pre-refactor) ───────
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
    error: groupsQuery.error ?? scheduleQuery.error ?? null,
    refresh,
    applyScheduleUpdate,

    // Config (from useScheduleConfig)
    weekdayConfigs: config.weekdayConfigs,
    weekdayBackend: config.weekdayBackend,
    weekdayLabels: config.weekdayLabels,
    weekdayShort: config.weekdayShort,
    getDayLabel: config.getDayLabel,
    lessonTypeConfigs: config.lessonTypeConfigs,
    lessonTypeOptions: config.lessonTypeOptions,
    lessonTypeLabels: config.lessonTypeLabels,
    defaultLessonType: config.defaultLessonType,
    getLessonTypeColor: config.getLessonTypeColor,
    toBackendLessonType: config.toBackendLessonType,

    // Time/State (from useScheduleTime)
    todayIdx,
    hasToday,
    nowTick: time.nowTick,
    todayLessons,
    currentLesson: time.currentLesson,
    nextLesson: time.nextLesson,
    conflictedIds,
    lessonDays,
    timeLeftText: time.timeLeftText,
    currentProgress: time.currentProgress,
  }
}
