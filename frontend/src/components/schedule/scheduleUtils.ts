/**
 * Schedule Types and Utilities
 *
 * Shared types and helper functions for the Schedule page components.
 */

import dayjs from "dayjs"
import { StorageItem } from "@/utils/storage"

// ============================================================================
// TYPES
// ============================================================================

export type LessonParity = "odd" | "even" | "both"
export type LessonWeekday = string

export type Lesson = {
  id: string
  weekday: LessonWeekday
  parity: LessonParity
  start_time: string | null
  end_time: string | null
  subject?: string | null
  teacher?: string | null
  room?: string | null
  lesson_type?: string | null
  group_id?: string | null
}

export type AddLessonFields = {
  subject: string
  teacher: string
  room: string
  lessonType: string
  startTime: string
  endTime: string
  parity: LessonParity
}

export type ScheduleGroup = {
  id: string
  name: string
  [key: string]: unknown
}

export type LessonTypeConfig = {
  id: string
  backend: string[]
  label: string
  color: string
}

export type WeekdayConfig = {
  id: string
  backend: string[]
  long: string
  short: string
}

// ============================================================================
// STORAGE
// ============================================================================

export const STORAGE_SCHEMA_VERSION = 1
export const GROUPS_STORAGE_TTL_MS = 5 * 60_000
export const SCHEDULE_STORAGE_TTL_MS = 5 * 60_000

type StoredPayload<T> = {
  version: number
  timestamp: number
  data: T
}

export type StorageReadResult<T> = {
  value: T
  timestamp: number
}

type StorageReadOptions = {
  maxAgeMs?: number
  version?: number
}

type StorageWriteOptions = {
  version?: number
}

export const groupsStorageKey = "sched:groups"
export const scheduleStorageKey = (groupId: string) => `sched:${groupId}`

export const readFromStorage = <T>(
  key: string,
  { maxAgeMs = SCHEDULE_STORAGE_TTL_MS, version = STORAGE_SCHEMA_VERSION }: StorageReadOptions = {}
): StorageReadResult<T> | undefined => {
  const storage = new StorageItem<StoredPayload<T>>(key)
  const parsed = storage.get()

  if (!parsed || typeof parsed !== "object") return undefined

  if (parsed.version !== version) {
    storage.remove()
    return undefined
  }

  const ts = typeof parsed.timestamp === "number" ? parsed.timestamp : NaN
  if (!Number.isFinite(ts)) {
    storage.remove()
    return undefined
  }

  if (Date.now() - ts > maxAgeMs) {
    storage.remove()
    return undefined
  }

  if (!("data" in parsed)) return undefined
  return { value: parsed.data, timestamp: ts }
}

export const writeToStorage = <T>(
  key: string,
  value: T,
  { version = STORAGE_SCHEMA_VERSION }: StorageWriteOptions = {}
) => {
  const storage = new StorageItem<StoredPayload<T>>(key)
  const payload: StoredPayload<T> = {
    version,
    timestamp: Date.now(),
    data: value,
  }
  storage.set(payload)
}

// ============================================================================
// TIME UTILITIES
// ============================================================================

export function getTimeStr(lesson: Lesson): string {
  if (!lesson?.start_time) return ""
  if (lesson.start_time.length >= 16 && lesson.start_time[10] === "T")
    return lesson.start_time.slice(11, 16)
  return lesson.start_time.slice(0, 5)
}

export function getEndTimeStr(lesson: Lesson): string {
  if (!lesson?.end_time) return ""
  if (lesson.end_time.length >= 16 && lesson.end_time[10] === "T")
    return lesson.end_time.slice(11, 16)
  return lesson.end_time.slice(0, 5)
}

export function parseMinutes(s?: string | null): number | null {
  if (!s) return null
  const hhmm = s.length >= 16 && s[10] === "T" ? s.slice(11, 16) : s.slice(0, 5)
  const [h, m] = hhmm.split(":").map(Number)
  if (Number.isNaN(h) || Number.isNaN(m)) return null
  return h * 60 + m
}

export function minutesDiff(a?: string | null, b?: string | null): number {
  const ma = parseMinutes(a) ?? 0
  const mb = parseMinutes(b) ?? 0
  return mb - ma
}

export const toDayjs = (s?: string | null) => {
  if (!s) return null
  if (s.length >= 16 && s.includes("T")) return dayjs(s)
  return dayjs(dayjs().format("YYYY-MM-DDT") + (s.length === 5 ? s + ":00" : s))
}

export function getTodayIdx(): number {
  const d = dayjs()
  const iso = typeof d.isoWeekday === "function" ? d.isoWeekday() : d.day()
  if (iso === 7) return -1
  return (iso - 1) as 0 | 1 | 2 | 3 | 4 | 5
}

// ============================================================================
// TABLE BUILDING
// ============================================================================

export function buildTable(
  schedule: Lesson[],
  weekdayOrder: readonly string[]
): (Lesson | null)[][] {
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

// ============================================================================
// CONSTANTS
// ============================================================================

export const defaultLessonTypeColor = "#888"

export const minimalLessonTypeFallback: LessonTypeConfig = {
  id: "lesson",
  backend: ["lesson"],
  label: "Lesson",
  color: defaultLessonTypeColor,
}

export const minimalWeekdayFallback: WeekdayConfig[] = [
  { id: "mon", backend: ["Monday"], long: "Monday", short: "Mon" },
  { id: "tue", backend: ["Tuesday"], long: "Tuesday", short: "Tue" },
  { id: "wed", backend: ["Wednesday"], long: "Wednesday", short: "Wed" },
  { id: "thu", backend: ["Thursday"], long: "Thursday", short: "Thu" },
  { id: "fri", backend: ["Friday"], long: "Friday", short: "Fri" },
  { id: "sat", backend: ["Saturday"], long: "Saturday", short: "Sat" },
]

// ============================================================================
// QUERY KEYS
// ============================================================================

export const scheduleGroupsQueryKey = ["schedule", "groups"] as const
export const scheduleQueryKey = (groupId: string) => ["schedule", "group", groupId] as const

export type ScheduleGroupsQueryKey = typeof scheduleGroupsQueryKey
export type InactiveScheduleQueryKey = readonly ["schedule", "group", "none"]
export type ActiveScheduleQueryKey = ReturnType<typeof scheduleQueryKey>




