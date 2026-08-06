import { memo, useMemo, useCallback } from "react"
import { useTranslation } from "react-i18next"
import { Calendar as TodayIcon, Plus as AddIcon } from "lucide-react"
import { Badge } from "@/components/ui"
import { EmptyState } from "@/components/ui/EmptyState"
import OfflineFallback from "@/components/feedback/OfflineFallback"
import { cn } from "@/utils/cn"
import { buildLessonsByDay, minutesDiff } from "@/components/schedule/scheduleUtils"
import { LessonCard } from "@/components/schedule/LessonCard"
import { useScheduleData } from "@/hooks/useScheduleData"
import { useSchedulePage } from "@/contexts/SchedulePageContext"
import { useScheduleDisplayPreferences } from "@/stores/scheduleUIStore"

type ScheduleListViewProps = Pick<
  ReturnType<typeof useScheduleData>,
  | "schedule"
  | "weekdayBackend"
  | "weekdayLabels"
  | "hasToday"
  | "todayIdx"
  | "rawSchedule"
  | "refresh"
  | "user"
  | "conflictedIds"
  | "currentLesson"
  | "currentProgress"
> & {
  isOnline: boolean
  onDeleteLesson: (id: string) => void
  getLessonTypeColor: (type?: string | null) => string
  getLessonTypeLabel: (val?: string | null) => string
  /** Lesson note indicators (FIX-67-02). CQ-71-06: non-optional */
  notesMap: Map<string, boolean>
}

export const ScheduleListView = memo(function ScheduleListView({
  schedule,
  weekdayBackend,
  weekdayLabels,
  hasToday,
  todayIdx,
  rawSchedule,
  refresh,
  user,
  conflictedIds,
  isOnline,
  onDeleteLesson,
  getLessonTypeColor,
  getLessonTypeLabel,
  currentLesson,
  currentProgress,
  notesMap,
}: ScheduleListViewProps) {
  const { t } = useTranslation(["schedule", "common"])
  const { openDialog, setAddDay } = useSchedulePage()
  const { compactMode } = useScheduleDisplayPreferences()

  const canEdit = user?.role === "admin" || user?.role === "teacher"

  /* ── Group lessons by day, sorted by time (CQ-71-05: shared utility) ── */
  const lessonsByDay = useMemo(
    () => buildLessonsByDay(schedule, weekdayBackend),
    [schedule, weekdayBackend]
  )

  // CQ-71-01: no useMemo needed for primitive .length access
  const totalLessons = schedule.length

  const handleAdd = useCallback(
    (day: string) => {
      setAddDay(day)
      openDialog("add")
    },
    [setAddDay, openDialog]
  )

  // Pre-compute cumulative lesson counts per day for stable stagger index
  // FIX-65-LINT: moved before early returns to satisfy rules-of-hooks
  const dayCumulativeCounts = useMemo(() => {
    const counts: number[] = []
    let total = 0
    for (const day of weekdayBackend) {
      counts.push(total)
      // buildLessonsByDay initializes an entry for every weekdayBackend item.
      total += lessonsByDay.get(day)!.length
    }
    return counts
  }, [weekdayBackend, lessonsByDay])

  if (!isOnline && rawSchedule.length === 0) {
    return (
      <div className="flex items-center justify-center px-6 py-16">
        <OfflineFallback onRetry={refresh} />
      </div>
    )
  }

  if (totalLessons === 0) {
    return (
      <div className="flex items-center justify-center rounded-xl sched-matte-card px-6 py-16">
        <EmptyState
          icon={
            <div className="sched-empty-icon relative">
              <TodayIcon size={28} />
              <div className="sched-empty-ring" />
            </div>
          }
          title={t("schedule:list.noLessons", { defaultValue: t("schedule:table.noLessons") })}
          description={t("schedule:empty.selectGroup")}
        />
      </div>
    )
  }

  return (
    <div className="schedule-list-container mx-auto w-full max-w-5xl space-y-6">
      {weekdayBackend.map((day, dayIdx) => {
        const label = weekdayLabels[dayIdx] ?? day
        const lessons = lessonsByDay.get(day)!
        const isToday = hasToday && dayIdx === todayIdx
        const baseIndex = dayCumulativeCounts[dayIdx]!

        return (
          <section
            key={day}
            aria-label={label}
            className="sched-column-item"
            style={{ "--sched-col-i": dayIdx } as React.CSSProperties}
          >
            {/* ── Sticky day header ──────────────────────── */}
            <div
              className={cn(
                "sched-list-day-header sticky top-16 z-sticky mb-3 flex items-center gap-3 rounded-xl sched-matte-card px-4 py-3 backdrop-blur-xl",
                isToday && "sched-today-header"
              )}
            >
              <h3
                className={cn(
                  "text-base font-extrabold tracking-tight",
                  isToday ? "text-brand" : "text-text-primary"
                )}
              >
                {label}
              </h3>
              {isToday && (
                <Badge
                  size="xs"
                  className="sched-today-badge sched-badge-matte bg-brand text-[var(--sched-on-accent)] font-bold shadow-glow-primary"
                >
                  {t("schedule:toolbar.today", { defaultValue: "" })}
                </Badge>
              )}
              <Badge size="xs" variant="outline" className="font-medium opacity-70">
                {lessons.length}
              </Badge>
              {canEdit && (
                <button
                  type="button"
                  onClick={() => handleAdd(day)}
                  aria-label={t("schedule:actions.addLesson", {
                    day: label,
                    defaultValue: `Add lesson for ${label}`,
                  })}
                  className="ml-auto flex h-9 w-9 min-h-[44px] min-w-[44px] items-center justify-center rounded-lg sched-settings-btn text-brand hover:bg-brand hover:text-[var(--sched-on-accent)] focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-1"
                >
                  {/* A11Y-71-01: consistent SVG icon instead of text + */}
                  <AddIcon size={14} aria-hidden="true" />
                </button>
              )}
            </div>

            {/* ── Lesson list ────────────────────────────── */}
            {lessons.length === 0 ? (
              <div className="rounded-xl border border-dashed border-surface-elevated/(--opacity-medium) px-4 py-8 text-center text-sm text-text-secondary">
                {t("schedule:mobile.noLessons")}
              </div>
            ) : (
              <div className="space-y-3">
                {lessons.map((lesson, idx) => {
                  const prev = lessons[idx - 1]
                  const gap = prev ? minutesDiff(prev.end_time, lesson.start_time) : 0
                  const isConflict = conflictedIds.has(lesson.id)
                  const isCurrent = lesson.id === currentLesson?.id
                  const cardIndex = baseIndex + idx

                  return (
                    <div key={lesson.id}>
                      {/* ── Break connector ─────────────── */}
                      {idx > 0 && gap > 0 && (
                        <div className="mb-2.5 flex items-center gap-2 px-1">
                          <div className="sched-timeline-dot" />
                          <div className="sched-timeline-line flex-1" />
                          <span className="sched-break-pill">
                            {t("schedule:break", { minutes: gap })}
                          </span>
                          <div className="sched-timeline-line flex-1" />
                          <div className="sched-timeline-dot" />
                        </div>
                      )}
                      {/* FIX-71-01: thread currentProgress for glow urgency */}
                      <LessonCard
                        lesson={lesson}
                        isConflict={isConflict}
                        isCurrent={isCurrent}
                        currentProgress={isCurrent ? (currentProgress ?? 0) : 0}
                        index={cardIndex}
                        compact={compactMode}
                        hasNote={notesMap.get(lesson.id) ?? false}
                        onDelete={() => onDeleteLesson(lesson.id)}
                        canEdit={canEdit}
                        getLessonTypeColor={getLessonTypeColor}
                        getLessonTypeLabel={getLessonTypeLabel}
                      />
                    </div>
                  )
                })}
              </div>
            )}
          </section>
        )
      })}
    </div>
  )
})

export default ScheduleListView
