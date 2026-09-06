/**
 * Schedule Types and Utilities
 *
 * Shared types and helper functions for the Schedule page components.
 */

// dayjs import removed
import { toDate } from "@/utils/date"
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

/* FIX-72-06: tightened from index signature — matches GroupOut shape */
export type ScheduleGroup = {
  id: string
  name: string
  course?: number | null
  faculty?: string | null
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

  const timestamp = parsed.timestamp
  if (!Number.isFinite(timestamp)) {
    storage.remove()
    return undefined
  }
  const ts = timestamp

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

/** Regex to extract HH:MM from various backend time formats (FIX-68-02). */
const TIME_RE = /(\d{2}):(\d{2})/

/** Safely extract HH:MM string from a lesson time field. Returns "" if invalid. */
function extractHHMM(raw: string | null | undefined): string {
  if (typeof raw !== "string") return ""
  if (raw.length === 0) return ""
  const match = TIME_RE.exec(raw)
  return match ? `${match[1]}:${match[2]}` : ""
}

export function getTimeStr(lesson: Lesson): string {
  return extractHHMM(lesson?.start_time)
}

export function getEndTimeStr(lesson: Lesson): string {
  return extractHHMM(lesson?.end_time)
}

export function parseMinutes(s?: string | null): number | null {
  if (!s) return null
  // Fast path: extract HH:MM via regex (FIX-68-02)
  const match = TIME_RE.exec(s)
  if (match) {
    const h = Number(match[1])
    const m = Number(match[2])
    // TIME_RE only accepts decimal digits, so lower bounds are implicit.
    // Keep the actual domain checks focused on the upper clock limits.
    if (h <= 23 && m <= 59) return h * 60 + m
    return null
  }
  // Fallback: full date parse
  const d = toDate(s)
  if (!d || isNaN(d.getTime())) return null
  return d.getHours() * 60 + d.getMinutes()
}

export function minutesDiff(a?: string | null, b?: string | null): number {
  const ma = parseMinutes(a) ?? 0
  const mb = parseMinutes(b) ?? 0
  return mb - ma
}

// Moved to utils/date.ts or used directly
export { toDate }

export function getTodayIdx(): number {
  const d = new Date()
  const day = d.getDay() // 0 (Sun) to 6 (Sat)
  return day - 1
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
  return Array.from({ length: maxLessons }, (_, rowIndex) =>
    weekdayOrder.map((_, dayIndex) => lessonsByDay[dayIndex]![rowIndex] ?? null)
  )
}

// ============================================================================
// CONSTANTS
// ============================================================================

export const defaultLessonTypeColor = "var(--lesson-type-default)"

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
// LESSON GROUPING (CQ-71-05: shared between MobileView + ListView)
// ============================================================================

/** Group lessons by weekday, sorted by start time within each day */
export function buildLessonsByDay(
  schedule: Lesson[],
  weekdayBackend: string[]
): Map<string, Lesson[]> {
  const map = new Map<string, Lesson[]>()
  for (const day of weekdayBackend) {
    map.set(
      day,
      schedule
        .filter((l) => l.weekday === day)
        .sort((a, b) => getTimeStr(a).localeCompare(getTimeStr(b)))
    )
  }
  return map
}

// ============================================================================
// QUERY KEYS
// ============================================================================

export const scheduleGroupsQueryKey = ["schedule", "groups"] as const
export const scheduleQueryKey = (groupId: string) => ["schedule", "group", groupId] as const

export type ScheduleGroupsQueryKey = typeof scheduleGroupsQueryKey
export type InactiveScheduleQueryKey = readonly ["schedule", "group", "none"]
export type ActiveScheduleQueryKey = ReturnType<typeof scheduleQueryKey>
