import { useMemo, useState } from "react"
import { useTranslation } from "react-i18next"
import { ActivityTimelineItem } from "./ActivityTimelineItem"
import type {
  AttendanceStats,
  GradeStats,
  ParticipationStats,
  TimelineEntry,
} from "./activityTypes"

type ActivityTimelineProps = {
  attendance?: AttendanceStats | null
  grades?: GradeStats | null
  participation?: ParticipationStats | null
  hasInitiallyLoaded: boolean
  attendanceStatusLabel: (status: "present" | "absent" | "late") => string
  formatDate: (date: string) => string
}

const INITIAL_VISIBLE = 10
const LOAD_MORE_COUNT = 10

function getDateGroup(dateStr: string, todayStr: string, yesterdayStr: string, t: (key: string) => string): string {
  if (dateStr === todayStr) return t("activity:timeline.today")
  if (dateStr === yesterdayStr) return t("activity:timeline.yesterday")
  return dateStr
}

export function ActivityTimeline({
  attendance,
  grades,
  participation,
  hasInitiallyLoaded,
  attendanceStatusLabel,
  formatDate,
}: ActivityTimelineProps) {
  const { t } = useTranslation(["activity"])
  const [visibleCount, setVisibleCount] = useState(INITIAL_VISIBLE)

  // Merge all recent arrays into a single sorted timeline
  const allEntries = useMemo((): TimelineEntry[] => {
    const entries: TimelineEntry[] = []

    for (const item of attendance?.recent ?? []) {
      entries.push({ type: "attendance", date: item.date, course: item.course, status: item.status })
    }
    for (const item of grades?.recent ?? []) {
      entries.push({ type: "grade", date: item.date, course: item.course, score: item.score, max: item.max })
    }
    for (const item of participation?.recent ?? []) {
      entries.push({ type: "participation", date: item.date, title: item.title, role: item.role })
    }

    // Sort descending by date
    entries.sort((a, b) => {
      const da = new Date(a.date).getTime()
      const db = new Date(b.date).getTime()
      if (Number.isNaN(da) && Number.isNaN(db)) return 0
      if (Number.isNaN(da)) return 1
      if (Number.isNaN(db)) return -1
      return db - da
    })

    return entries
  }, [attendance?.recent, grades?.recent, participation?.recent])

  const visibleEntries = allEntries.slice(0, visibleCount)
  const hasMore = visibleCount < allEntries.length

  // Date group helpers
  const today = new Date()
  const todayStr = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, "0")}-${String(today.getDate()).padStart(2, "0")}`
  const yesterday = new Date(today)
  yesterday.setDate(yesterday.getDate() - 1)
  const yesterdayStr = `${yesterday.getFullYear()}-${String(yesterday.getMonth() + 1).padStart(2, "0")}-${String(yesterday.getDate()).padStart(2, "0")}`

  if (!hasInitiallyLoaded) return null

  if (allEntries.length === 0) {
    return (
      <section aria-label={t("activity:a11y.timeline")}>
        <h2 className="mb-4 text-lg font-extrabold text-text-primary">
          {t("activity:timeline.title")}
        </h2>
        <div className="activity-card-matte p-6 text-center">
          <p className="text-sm text-text-secondary">{t("activity:timeline.noActivity")}</p>
        </div>
      </section>
    )
  }

  // Group entries by date for rendering date headers
  let lastDateGroup = ""
  let staggerIndex = 0

  return (
    <section aria-label={t("activity:a11y.timeline")}>
      <h2 className="mb-4 text-lg font-extrabold text-text-primary">
        {t("activity:timeline.title")}
      </h2>

      <div className="relative" role="feed">
        {/* Vertical timeline line */}
        <div className="activity-timeline-line" />

        {visibleEntries.map((entry, i) => {
          const dateKey = entry.date.slice(0, 10)
          const dateGroup = getDateGroup(dateKey, todayStr, yesterdayStr, t)
          const showDateHeader = dateGroup !== lastDateGroup
          lastDateGroup = dateGroup
          const currentStagger = staggerIndex++

          return (
            <div key={`${entry.type}-${entry.date}-${i}`}>
              {showDateHeader && (
                <div className="relative mb-2 mt-4 pl-10 first:mt-0">
                  <p className="text-xs font-bold uppercase tracking-wider text-text-tertiary">
                    {dateGroup === dateKey ? formatDate(dateKey) : dateGroup}
                  </p>
                </div>
              )}
              <ActivityTimelineItem
                entry={entry}
                formatDate={formatDate}
                attendanceStatusLabel={attendanceStatusLabel}
                staggerIndex={currentStagger}
              />
            </div>
          )
        })}
      </div>

      {hasMore && (
        <div className="mt-4 flex justify-center">
          <button
            type="button"
            onClick={() => setVisibleCount((c) => c + LOAD_MORE_COUNT)}
            className="matte-chip min-h-[44px] px-6 py-2 text-sm font-semibold text-text-primary transition-transform hover:-translate-y-0.5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
          >
            {t("activity:timeline.showMore")}
          </button>
        </div>
      )}
    </section>
  )
}
