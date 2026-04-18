import { useMemo } from "react"
import { useTranslation } from "react-i18next"
import { Flame } from "lucide-react"
import type { AttendanceStats, GradeStats, ParticipationStats } from "../types"

type ActivityMotivationProps = {
  attendance?: AttendanceStats | null
  grades?: GradeStats | null
  participation?: ParticipationStats | null
  hasInitiallyLoaded: boolean
}

export function ActivityMotivation({
  attendance,
  grades,
  participation,
  hasInitiallyLoaded,
}: ActivityMotivationProps) {
  const { t } = useTranslation(["activity"])

  const message = useMemo(() => {
    if (!hasInitiallyLoaded) return null
    const pct = attendance?.percent ?? 0
    if (pct >= 95) return t("activity:motivation.excellent")
    if (pct >= 80) return t("activity:motivation.good")
    if ((grades?.trend ?? 0) > 0) return t("activity:motivation.improving")
    if ((participation?.events ?? 0) >= 5) return t("activity:motivation.active")
    return t("activity:motivation.default")
  }, [hasInitiallyLoaded, attendance?.percent, grades?.trend, participation?.events, t])

  // RC-78-01: extract to primitive — React Compiler requires primitive deps, not property access
  const recentAttendance = attendance?.recent
  const streak = useMemo(() => {
    if (!recentAttendance?.length) return 0
    let count = 0
    for (const entry of recentAttendance) {
      if (entry.status === "present") count++
      else break
    }
    return count
  }, [recentAttendance])

  if (!hasInitiallyLoaded) return null

  return (
    <div className="mb-6 flex flex-wrap items-center gap-3" aria-live="polite">
      {streak > 2 && (
        <div
          className="activity-motivation-chip inline-flex items-center gap-1.5"
          aria-label={t("activity:a11y.streak")}
        >
          <Flame size={16} className="text-[var(--activity-streak-accent)]" aria-hidden="true" />
          <span>{t("activity:motivation.streakDays", { count: streak })}</span>
        </div>
      )}
      {message && (
        <p className="text-sm font-medium text-text-secondary">
          {message}
        </p>
      )}
    </div>
  )
}
