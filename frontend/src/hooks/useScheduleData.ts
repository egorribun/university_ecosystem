/**
 * useScheduleData — Orchestrator hook for the Schedule page.
 * Wave 65: Split into useScheduleConfig (i18n config) + useScheduleTime (ticker).
 *
 * Public API is UNCHANGED — all consumers still import `useScheduleData`
 * and destructure the same fields.
 */
import { useState, useEffect, useMemo, useCallback } from "react"
import { useQuery, useQueryClient } from "@tanstack/react-query"
import { pageScheduleQueryOptions, scheduleGroupsQueryOptions } from "@/api/hooks/schedule"
import { useAuth } from "@/contexts/AuthContext"
import {
  type Lesson,
  scheduleQueryKey,
  getTodayIdx,
  getTimeStr,
} from "@/components/schedule/scheduleUtils"
import { detectConflicts } from "@/utils/scheduleConflicts"
import { getDatabase, type ScheduleDoc } from "@/db"
import { useScheduleConfig } from "./useScheduleConfig"
import { useScheduleTime } from "./useScheduleTime"

export function useScheduleData() {
  const { user } = useAuth()
  const queryClient = useQueryClient()
  const [selectedGroup, setSelectedGroup] = useState<string | null>(null)
  const [currentParity, setCurrentParity] = useState<"odd" | "even">("odd")

  // ── Config (i18n weekdays + lesson types) ──────────
  const config = useScheduleConfig()
  const { weekdayBackend, normalizeLessons } = config

  // ── TanStack Query: Groups ─────────────────────────
  // Wave 130 SW1 — factory shared with the /schedule SSR loader
  // (frontend/src/api/hooks/schedule.ts). queryKey shape preserved
  // so cache entries hydrate cleanly across SSR → client.
  const groupsQuery = useQuery(scheduleGroupsQueryOptions())
  const groups = useMemo(() => groupsQuery.data ?? [], [groupsQuery.data])

  // ── TanStack Query: Schedule ───────────────────────
  const activeGroupId = selectedGroup
  const scheduleKey = activeGroupId != null ? scheduleQueryKey(activeGroupId) : null

  const scheduleQuery = useQuery(pageScheduleQueryOptions(activeGroupId))

  const groupScheduleRaw = useMemo(() => scheduleQuery.data ?? [], [scheduleQuery.data])
  const groupSchedule = useMemo(
    () => normalizeLessons(groupScheduleRaw),
    [groupScheduleRaw, normalizeLessons]
  )

  // ── Persist Schedule to RxDB for Offline Access ─────
  useEffect(() => {
    if (activeGroupId && groupScheduleRaw.length > 0) {
      getDatabase()
        .then((db) => {
          const docs: ScheduleDoc[] = groupScheduleRaw.map((lesson: Record<string, unknown>) => ({
            id: String(lesson.id ?? ""),
            group_id: activeGroupId,
            subject:
              typeof lesson.subject === "string"
                ? lesson.subject
                : lesson.subject && typeof lesson.subject === "object" && "name" in lesson.subject
                  ? String((lesson.subject as { name?: unknown }).name ?? "")
                  : String(lesson.subject ?? ""),
            teacher:
              typeof lesson.teacher === "string"
                ? lesson.teacher
                : lesson.teacher && typeof lesson.teacher === "object" && "name" in lesson.teacher
                  ? String((lesson.teacher as { name?: unknown }).name ?? "")
                  : String(lesson.teacher ?? ""),
            room: typeof lesson.room === "string" ? lesson.room : String(lesson.room ?? ""),
            building:
              typeof lesson.building === "string" ? lesson.building : String(lesson.building ?? ""),
            weekday: String(lesson.weekday ?? ""),
            start_time: String(lesson.start_time ?? ""),
            end_time: String(lesson.end_time ?? ""),
            parity: String(lesson.parity ?? "both"),
            lesson_type: String(lesson.lesson_type ?? "lecture"),
            updated_at: new Date().toISOString(),
          }))
          db.schedule.bulkUpsert(docs).catch(() => {})
        })
        .catch(() => {})
    }
  }, [activeGroupId, groupScheduleRaw])

  // ── Auto-select group based on user role ───────────
  useEffect(() => {
    if (!user) return
    if (groups.length === 0) return

    const userGroupId = user.group_id
    if (user.role === "student" && userGroupId) {
      const userGroupExists = groups.some((g) => g.id === userGroupId)
      if (userGroupExists) {
        setSelectedGroup((prev) => prev ?? userGroupId)
      } else {
        setSelectedGroup((prev) => prev ?? groups[0]!.id)
      }
    } else {
      setSelectedGroup((prev) => prev ?? groups[0]!.id)
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
    const today = weekdayBackend.at(todayIdx)!
    return filteredSchedule
      .filter((l) => l.weekday === today)
      .sort((a, b) => getTimeStr(a).localeCompare(getTimeStr(b)))
  }, [filteredSchedule, hasToday, todayIdx, weekdayBackend])

  const time = useScheduleTime(todayLessons, hasToday)

  // ── Conflict detection ─────────────────────────────
  const conflictedIds = useMemo(() => detectConflicts(filteredSchedule), [filteredSchedule])

  // ── Lesson days for MiniCalendar ───────────────────
  // PERF-70-07: use year/month primitives — only recalculates on month change, not every 30s tick
  const calYear = time.nowTick.getFullYear()
  const calMonth = time.nowTick.getMonth()
  const lessonDays = useMemo(() => {
    const days = new Set<number>()
    const firstDay = new Date(calYear, calMonth, 1).getDay()
    const weekdayToOffset = new Map<string, number>()
    for (let i = 0; i < weekdayBackend.length; i++) {
      weekdayToOffset.set(weekdayBackend[i]!, i)
    }
    const daysInMonth = new Date(calYear, calMonth + 1, 0).getDate()
    for (const lesson of filteredSchedule) {
      const offset = weekdayToOffset.get(lesson.weekday)
      if (offset === undefined) continue
      const jsDay = (offset + 1) % 7
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
    timeLeftShort: time.timeLeftShort,
    currentProgress: time.currentProgress,
  }
}
