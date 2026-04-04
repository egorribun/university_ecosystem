import { useMemo } from "react"
import { useTranslation } from "react-i18next"
import { Plus as AddIcon, Calendar as TodayIcon } from "lucide-react"
import { Fragment } from "react"
import { Badge } from "@/components/ui"
import { EmptyState } from "@/components/ui/EmptyState"
import OfflineFallback from "@/components/feedback/OfflineFallback"
import { cn } from "@/utils/cn"
import { buildTable, minutesDiff } from "@/components/schedule/scheduleUtils"
import { LessonCard } from "@/components/schedule/LessonCard"
import { useScheduleData } from "@/hooks/useScheduleData"
import { useSchedulePage } from "@/contexts/SchedulePageContext"
import { useHiddenWeekdays, useScheduleDisplayPreferences } from "@/stores/scheduleUIStore"

type ScheduleDesktopTableProps = Pick<
  ReturnType<typeof useScheduleData>,
  | "schedule"
  | "weekdayBackend"
  | "weekdayLabels"
  | "hasToday"
  | "todayIdx"
  | "conflictedIds"
  | "user"
  | "rawSchedule"
  | "refresh"
  | "currentLesson"
> & {
  isOnline: boolean
  getLessonTypeColor: (type?: string | null) => string
  getLessonTypeLabel: (val?: string | null) => string
  onDeleteLesson: (id: string) => void
}

export function ScheduleDesktopTable({
  schedule,
  weekdayBackend,
  weekdayLabels,
  hasToday,
  todayIdx,
  conflictedIds,
  user,
  rawSchedule,
  refresh,
  isOnline,
  getLessonTypeColor,
  getLessonTypeLabel,
  onDeleteLesson,
  currentLesson,
}: ScheduleDesktopTableProps) {
  const { t } = useTranslation(["schedule", "common"])
  const { openDialog, setAddDay } = useSchedulePage()
  const hiddenWeekdays = useHiddenWeekdays()
  const { compactMode } = useScheduleDisplayPreferences()

  /* ── Filter visible weekdays ──────────────────────────── */
  const visibleDays = useMemo(() => {
    return weekdayBackend
      .map((day, idx) => ({ day, idx, label: weekdayLabels[idx] ?? day }))
      .filter((_, i) => !hiddenWeekdays.includes(i))
  }, [weekdayBackend, weekdayLabels, hiddenWeekdays])

  /* ── Build grid data ──────────────────────────────────── */
  const tableRows = useMemo(
    () => buildTable(schedule, weekdayBackend),
    [schedule, weekdayBackend],
  )

  const canEdit = user?.role === "admin" || user?.role === "teacher"
  const colCount = visibleDays.length + 1
  const isEmpty = tableRows.length === 0

  return (
    <div className="schedule-grid-container mx-auto w-full max-w-(--layout-max-ultrawide)">
      <div
        role="grid"
        aria-label={t("schedule:title.default")}
        aria-rowcount={tableRows.length + 1}
        aria-colcount={colCount}
        className="overflow-hidden rounded-xl border border-glass-border bg-surface/(--opacity-medium) text-text-primary shadow-glass backdrop-blur-md"
        style={{
          display: "grid",
          gridTemplateColumns: `3.5rem repeat(${visibleDays.length}, 1fr)`,
        }}
      >
        {/* ── Header row ──────────────────────────────────── */}
        <div
          role="columnheader"
          aria-colindex={1}
          className="sticky top-0 z-sticky flex items-center justify-center border-b border-r border-glass-border bg-surface-raised px-2 py-3 font-extrabold text-primary shadow-sm backdrop-blur-md glass-layer-matte glass-noise"
        >
          №
        </div>
        {visibleDays.map(({ day, idx, label }, colI) => {
          const isTodayCol = hasToday && idx === todayIdx
          return (
            <div
              key={day}
              role="columnheader"
              aria-colindex={colI + 2}
              aria-current={isTodayCol ? "date" : undefined}
              className={cn(
                "sched-column-item sticky top-0 z-sticky flex items-center justify-center gap-2 border-b border-glass-border px-3 py-3 font-semibold backdrop-blur-md glass-layer-matte glass-noise",
                isTodayCol && "sched-today-header"
              )}
              style={{ "--sched-col-i": colI } as React.CSSProperties}
            >
              <span className={cn("tracking-tight", isTodayCol && "text-brand font-bold")}>
                {label}
              </span>
              {isTodayCol && (
                <span className="sched-today-badge inline-flex items-center gap-1 rounded-full bg-brand px-2 py-0.5 text-[0.625rem] font-bold text-white shadow-glow-primary">
                  <TodayIcon size={10} aria-hidden="true" />
                  {t("schedule:toolbar.today", { defaultValue: "" })}
                </span>
              )}
              {canEdit && (
                <button
                  type="button"
                  aria-label={t("schedule:actions.addLesson", { day: label })}
                  className="flex h-7 w-7 items-center justify-center rounded-lg border border-glass-border bg-surface/(--opacity-strong) text-brand transition-all duration-fast hover:bg-brand hover:text-white hover:shadow-sm focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-1"
                  onClick={(e) => {
                    e.stopPropagation()
                    setAddDay(day)
                    openDialog("add")
                  }}
                >
                  <AddIcon className="h-3.5 w-3.5" aria-hidden="true" />
                </button>
              )}
            </div>
          )
        })}

        {/* ── Empty state ─────────────────────────────────── */}
        {isEmpty && (
          <div
            style={{ gridColumn: `1 / -1` }}
            className="flex items-center justify-center px-6 py-16"
          >
            {!isOnline && rawSchedule.length === 0 ? (
              <OfflineFallback onRetry={refresh} />
            ) : (
              <EmptyState
                icon={
                  <div className="sched-empty-icon relative">
                    <TodayIcon size={28} />
                    <div className="sched-empty-ring" />
                  </div>
                }
                title={t("schedule:table.noLessons")}
                description={t("schedule:empty.selectGroup", { defaultValue: "" })}
              />
            )}
          </div>
        )}

        {/* ── Data rows ───────────────────────────────────── */}
        {tableRows.map((row, rowIdx) => {
          // Filter row to only show visible day columns
          const visibleCells = visibleDays.map(({ idx: originalIdx }) => ({
            lesson: row[originalIdx] ?? null,
            originalIdx,
          }))

          return (
            <Fragment key={`row-${rowIdx}`}>
                {/* Row number */}
                <div
                  role="rowheader"
                  aria-rowindex={rowIdx + 2}
                  aria-colindex={1}
                  className="sticky left-0 z-sticky flex items-center justify-center border-b border-r border-glass-border bg-surface/(--opacity-strong) px-2 py-3 font-bold shadow-sm backdrop-blur-md glass-layer-matte glass-noise"
                >
                  {rowIdx + 1}
                </div>

                {/* Day cells */}
                {visibleCells.map(({ lesson, originalIdx }, colI) => {
                  const isTodayCol = hasToday && originalIdx === todayIdx
                  const isCurrent = lesson != null && currentLesson?.id === lesson.id

                  if (!lesson) {
                    return (
                      <div
                        key={`empty-${rowIdx}-${colI}`}
                        id={`sched-cell-${rowIdx}-${colI}`}
                        role="gridcell"
                        tabIndex={-1}
                        aria-rowindex={rowIdx + 2}
                        aria-colindex={colI + 2}
                        className={cn(
                          "sched-grid-cell flex items-center justify-center border-b border-glass-border/(--opacity-soft) outline-none",
                          isTodayCol && "sched-today-col"
                        )}
                      >
                        <div className="sched-empty-cell w-full" />
                      </div>
                    )
                  }

                  let hasBreakBefore = false
                  if (rowIdx > 0) {
                    const prev = tableRows[rowIdx - 1]?.[originalIdx]
                    if (prev) {
                      hasBreakBefore = minutesDiff(prev.end_time, lesson.start_time) > 0
                    }
                  }

                  const isConflict = conflictedIds.has(lesson.id)

                  return (
                    <div
                      key={lesson.id}
                      id={`sched-cell-${rowIdx}-${colI}`}
                      role="gridcell"
                      tabIndex={-1}
                      aria-rowindex={rowIdx + 2}
                      aria-colindex={colI + 2}
                      className={cn(
                        "sched-grid-cell relative border-b border-glass-border/(--opacity-soft) outline-none",
                        isTodayCol && "sched-today-col"
                      )}
                    >
                      {/* Break indicator */}
                      {hasBreakBefore && (
                        <div className="absolute -top-3 left-1/2 z-deep -translate-x-1/2">
                          <Badge
                            size="xs"
                            className="chip-break whitespace-nowrap font-medium bg-warning-bg/(--opacity-dim) border border-warning-border/(--opacity-soft) text-warning-text shadow-sm"
                          >
                            {t("schedule:break", {
                              minutes: minutesDiff(
                                tableRows[rowIdx - 1]?.[originalIdx]?.end_time,
                                lesson.start_time,
                              ),
                            })}
                          </Badge>
                        </div>
                      )}

                      <LessonCard
                        lesson={lesson}
                        isConflict={isConflict}
                        isCurrent={isCurrent}
                        index={rowIdx * visibleDays.length + colI}
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
              </Fragment>
            )
          })}
      </div>
    </div>
  )
}
