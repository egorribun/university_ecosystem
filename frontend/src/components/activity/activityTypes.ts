export const EASE_OUT_EXPO = [0.22, 1, 0.36, 1] as const

export const PERIOD_VALUES = ["30d", "90d", "180d"] as const
export type PeriodKey = (typeof PERIOD_VALUES)[number]

export function periodDayCount(key: PeriodKey): number {
  switch (key) {
    case "30d":
      return 30
    case "90d":
      return 90
    case "180d":
      return 180
    default:
      return 0
  }
}

export const isPeriodKey = (value: unknown): value is PeriodKey =>
  typeof value === "string" && PERIOD_VALUES.includes(value as PeriodKey)

export type AttendanceStats = {
  percent: number
  present: number
  total: number
  trend: number
  periodLabel: string
  periodKey: string
  recent: Array<{ date: string; status: "present" | "absent" | "late"; course?: string }>
}

export type GradeStats = {
  average: number
  scale: "5" | "100" | "gpa"
  trend: number
  recent: Array<{ course: string; score: number; max?: number; date: string }>
}

export type ParticipationStats = {
  events: number
  hours?: number
  groups?: number
  trend: number
  recent: Array<{ title: string; date: string; role?: string }>
}

export type AttendanceSummaryResponse = {
  percent?: unknown
  present?: unknown
  total?: unknown
  trend?: unknown
  period_key?: unknown
  period_label?: unknown
  recent?: unknown
}

export type GradeSummaryResponse = {
  average?: unknown
  scale?: unknown
  trend?: unknown
  recent?: unknown
}

export type ParticipationSummaryResponse = {
  events?: unknown
  hours?: unknown
  groups?: unknown
  trend?: unknown
  recent?: unknown
}

export type DetailSection = "" | "attendance" | "grades" | "participation"
