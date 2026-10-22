import * as v from "valibot"
import type { AttendanceDaily, AttendanceStats, GradeStats, ParticipationStats } from "./types"

export const toNumber = (value: unknown, fallback = 0): number => {
  const num = Number(value)
  return Number.isFinite(num) ? num : fallback
}

const isAttendanceStatus = (value: unknown): value is AttendanceStats["recent"][number]["status"] =>
  value === "present" || value === "late" || value === "absent"

export const parseAttendanceRecent = (value: unknown): AttendanceStats["recent"] => {
  if (!Array.isArray(value)) return []
  return value
    .map((item) => {
      if (!item || typeof item !== "object") return null
      // Safe narrowing: null/object guard above ensures item is a non-null object
      const entry = item as Record<string, unknown>
      const date = typeof entry.date === "string" ? entry.date : null
      const status = entry.status
      if (!date || !isAttendanceStatus(status)) return null
      const course = typeof entry.course === "string" ? entry.course : undefined
      return {
        date,
        status,
        ...(course !== undefined ? { course } : {}),
      }
    })
    .filter((item): item is AttendanceStats["recent"][number] => item != null)
}

export const parseGradeRecent = (value: unknown): GradeStats["recent"] => {
  if (!Array.isArray(value)) return []
  return value
    .map((item) => {
      if (!item || typeof item !== "object") return null
      // Safe narrowing: null/object guard above ensures item is a non-null object
      const entry = item as Record<string, unknown>
      const course = typeof entry.course === "string" ? entry.course : null
      const score = toNumber(entry.score, Number.NaN)
      if (!course || Number.isNaN(score)) return null
      const maxRaw = entry.max
      const max = maxRaw != null ? toNumber(maxRaw, Number.NaN) : undefined
      const date = typeof entry.date === "string" ? entry.date : ""
      return {
        course,
        score,
        date,
        ...(max != null && !Number.isNaN(max) ? { max } : {}),
      }
    })
    .filter((item): item is GradeStats["recent"][number] => item != null)
}

export const parseParticipationRecent = (value: unknown): ParticipationStats["recent"] => {
  if (!Array.isArray(value)) return []
  return value
    .map((item) => {
      if (!item || typeof item !== "object") return null
      // Safe narrowing: null/object guard above ensures item is a non-null object
      const entry = item as Record<string, unknown>
      const title = typeof entry.title === "string" ? entry.title : null
      if (!title) return null
      const date = typeof entry.date === "string" ? entry.date : ""
      const role = typeof entry.role === "string" ? entry.role : undefined
      return {
        title,
        date,
        ...(role !== undefined ? { role } : {}),
      }
    })
    .filter((item): item is ParticipationStats["recent"][number] => item != null)
}

const registrationCountSchema = v.pipe(
  v.number(),
  v.check((value) => Number.isSafeInteger(value) && value >= 0)
)

const attendanceDailySchema = v.pipe(
  v.object({
    date: v.pipe(
      v.string(),
      v.check(
        (value) =>
          /^\d{4}-\d{2}-\d{2}$/.test(value) &&
          Number.isFinite(Date.parse(value)) &&
          new Date(value).toISOString().slice(0, 10) === value
      )
    ),
    registered: registrationCountSchema,
    total: registrationCountSchema,
  }),
  v.check(({ registered, total }) => total > 0 && registered <= total)
)

/** Reject malformed counters instead of inventing a registration percentage. */
export const parseAttendanceDaily = (value: unknown): AttendanceDaily[] => {
  if (!Array.isArray(value)) return []
  return value.flatMap((item) => {
    const parsed = v.safeParse(attendanceDailySchema, item)
    return parsed.success ? [parsed.output] : []
  })
}

export const parseStreakDays = (value: unknown): number | undefined => {
  const parsed = v.safeParse(registrationCountSchema, value)
  return parsed.success ? parsed.output : undefined
}
