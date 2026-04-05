import { useMemo, useCallback } from "react"
import { useTranslation } from "react-i18next"
import { Calendar as TodayIcon } from "lucide-react"
import { Badge } from "@/components/ui"
import { EmptyState } from "@/components/ui/EmptyState"
import OfflineFallback from "@/components/feedback/OfflineFallback"
import { cn } from "@/utils/cn"
import { type Lesson, getTimeStr, minutesDiff } from "@/components/schedule/scheduleUtils"
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
> & {
  isOnline: boolean
  onDeleteLesson: (id: string) => void
  getLessonTypeColor: (type?: string | null) => string
  getLessonTypeLabel: (val?: string | null) => string
}

export function ScheduleListView({
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
}: ScheduleListViewProps) {
  const { t } = useTranslation(["schedule", "common"])
  const { openDialog, setAddDay } = useSchedulePage()
  const { compactMode } = useScheduleDisplayPreferences()

  const canEdit = user?.role === "admin" || user?.role === "teacher"

  /* ── Group lessons by day, sorted by time ────────────── */
  const lessonsByDay = useMemo(() => {
    const map = new Map<string, Lesson[]>()
    for (const day of weekdayBackend) {
      map.set(
        day,
        schedule
          .filter((l) => l.weekday === day)
          .sort((a, b) => getTimeStr(a).localeCompare(getTimeStr(b))),
      )
    }
    return map
  }, [schedule, weekdayBackend])

  const totalLessons = useMemo(
    () => schedule.length,
    [schedule],
  )

  const handleAdd = useCallback(
    (day: string) => {
      setAddDay(day)
      openDialog("add")
    },
    [setAddDay, openDialog],
  )

  // Pre-compute cumulative lesson counts per day for stable stagger index
  // FIX-65-LINT: moved before early returns to satisfy rules-of-hooks
  const dayCumulativeCounts = useMemo(() => {
    const counts: number[] = []
    let total = 0
    for (const day of weekdayBackend) {
      counts.push(total)
      total += (lessonsByDay.get(day)?.length ?? 0)
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
      <div className="flex items-center justify-center rounded-xl border border-glass-border/(--opacity-soft) bg-surface/(--opacity-dim) px-6 py-16 glass-noise">
        <EmptyState
          icon={
            <div className="sched-empty-icon relative">
              <TodayIcon size={28} />
              <div className="sched-empty-ring" />
            </div>
          }
          title={t("schedule:list.noLessons", { defaultValue: t("schedule:table.noLessons") })}
          description={t("schedule:empty.selectGroup", { defaultValue: "" })}
        />
      </div>
    )
  }

  return (
    <div className="schedule-list-container mx-auto w-full max-w-5xl space-y-6">
      {weekdayBackend.map((day, dayIdx) => {
        const label = weekdayLabels[dayIdx] ?? day
        const lessons = lessonsByDay.get(day) ?? []
        const isToday = hasToday && dayIdx === todayIdx
        const baseIndex = dayCumulativeCounts[dayIdx] ?? 0

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
                "sched-list-day-header sticky top-16 z-sticky mb-3 flex items-center gap-3 rounded-xl border border-glass-border px-4 py-3 backdrop-blur-xl glass-layer-matte glass-noise",
                isToday && "sched-today-header border-brand/(--opacity-dim)"
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
                  className="sched-today-badge sched-badge-matte bg-brand text-white font-bold shadow-glow-primary"
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
                  aria-label={t("schedule:actions.addLesson", { day: label, defaultValue: `Add lesson for ${label}` })}
                  className="ml-auto flex h-7 w-7 items-center justify-center rounded-lg border border-glass-border bg-surface/(--opacity-strong) text-brand transition-all duration-fast hover:bg-brand hover:text-white hover:shadow-sm focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-1"
                >
                  <span className="text-sm font-bold" aria-hidden="true">+</span>
                </button>
              )}
            </div>

            {/* ── Lesson list ────────────────────────────── */}
            {lessons.length === 0 ? (
              <div className="rounded-xl border border-dashed border-glass-border/(--opacity-soft) px-4 py-8 text-center text-sm text-text-secondary">
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
                      <LessonCard
                        lesson={lesson}
                        isConflict={isConflict}
                        isCurrent={isCurrent}
                        index={cardIndex}
                        compact={compactMode}
                        onOpen={() => openDialog("details", lesson)}
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
}
