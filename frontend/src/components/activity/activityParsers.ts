import type { AttendanceStats, GradeStats, ParticipationStats } from "./activityTypes"

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

export const DEFAULT_ATTENDANCE_RECENT: AttendanceStats["recent"] = [
  { date: "2025-09-19", status: "present", course: "Algebra" },
  { date: "2025-09-18", status: "late", course: "History" },
  { date: "2025-09-17", status: "present", course: "Physics" },
]

export const DEFAULT_GRADE_RECENT: GradeStats["recent"] = [
  { course: "Algebra", score: 5, date: "2025-09-18" },
  { course: "Physics", score: 4, date: "2025-09-16" },
  { course: "Literature", score: 5, date: "2025-09-13" },
]

export const DEFAULT_PARTICIPATION_RECENT: ParticipationStats["recent"] = [
  { title: "Department hackathon", date: "2025-09-14", role: "participant" },
  { title: "Basketball tournament", date: "2025-09-07", role: "team" },
]
