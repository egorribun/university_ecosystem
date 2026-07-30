import { memo, useCallback, useMemo, useState } from "react"
import { useTranslation } from "react-i18next"
import { ActivityTimelineItem } from "./ActivityTimelineItem"
import type { AttendanceStats, GradeStats, ParticipationStats, TimelineEntry } from "../types"

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

function getDateGroup(
  dateStr: string,
  todayStr: string,
  yesterdayStr: string,
  t: (key: string) => string
): string {
  if (dateStr === todayStr) return t("activity:timeline.today")
  if (dateStr === yesterdayStr) return t("activity:timeline.yesterday")
  return dateStr
}

export const ActivityTimeline = memo(function ActivityTimeline({
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
      entries.push({
        type: "attendance",
        date: item.date,
        course: item.course,
        status: item.status,
      })
    }
    for (const item of grades?.recent ?? []) {
      entries.push({
        type: "grade",
        date: item.date,
        course: item.course,
        score: item.score,
        max: item.max,
      })
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

  const hasMore = visibleCount < allEntries.length

  // Date group helpers — memoized to avoid recalculating every render (A9)
  const { todayStr, yesterdayStr } = useMemo(() => {
    const now = new Date()
    const ts = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`
    const prev = new Date(now)
    prev.setDate(prev.getDate() - 1)
    const ys = `${prev.getFullYear()}-${String(prev.getMonth() + 1).padStart(2, "0")}-${String(prev.getDate()).padStart(2, "0")}`
    return { todayStr: ts, yesterdayStr: ys }
  }, [])

  // Stable key builder — avoids collision when same type+date (A15)
  const getEntryKey = useCallback((entry: TimelineEntry, index: number): string => {
    if (entry.type === "attendance")
      return `att-${entry.date}-${entry.status}-${entry.course ?? ""}-${index}`
    if (entry.type === "grade") return `grd-${entry.date}-${entry.course}-${entry.score}-${index}`
    return `prt-${entry.date}-${entry.title}-${index}`
  }, [])

  // H1: Precompute date groups + stagger indices — no mutable state in render map (React Compiler)
  const visibleItems = useMemo(() => {
    const visible = allEntries.slice(0, visibleCount)
    let lastGroup = ""
    let stagger = 0
    return visible.map((entry, i) => {
      const dateKey = entry.date.slice(0, 10)
      const dateGroup = getDateGroup(dateKey, todayStr, yesterdayStr, t)
      const showDateHeader = dateGroup !== lastGroup
      lastGroup = dateGroup
      return {
        entry,
        key: getEntryKey(entry, i),
        dateKey,
        dateGroup,
        showDateHeader,
        staggerIndex: stagger++,
      }
    })
  }, [allEntries, visibleCount, todayStr, yesterdayStr, t, getEntryKey])

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

  return (
    <section aria-label={t("activity:a11y.timeline")}>
      <h2 className="mb-4 text-lg font-extrabold text-text-primary">
        {t("activity:timeline.title")}
      </h2>

      {/* Wave 116 polish — removed `role="feed"` (requires children with
          `role="article"` per ARIA 1.2 `aria-required-children`). This is a
          static date-grouped history, not an infinite-scroll feed; the outer
          `<section aria-label>` preserves the accessible region semantics. */}
      <div className="relative">
        {/* Vertical timeline line */}
        <div className="activity-timeline-line" />

        {visibleItems.map((item) => (
          <div key={item.key}>
            {item.showDateHeader && (
              <div className="relative mb-2 mt-4 pl-10 first:mt-0">
                {/* M4: semantic heading for screen reader section navigation */}
                <h3 className="text-xs font-bold uppercase tracking-wider text-text-tertiary">
                  {item.dateGroup === item.dateKey ? formatDate(item.dateKey) : item.dateGroup}
                </h3>
              </div>
            )}
            <ActivityTimelineItem
              entry={item.entry}
              formatDate={formatDate}
              attendanceStatusLabel={attendanceStatusLabel}
              staggerIndex={item.staggerIndex}
            />
          </div>
        ))}
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
})

export default ActivityTimeline

