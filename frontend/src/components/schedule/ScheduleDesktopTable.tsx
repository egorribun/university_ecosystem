import { memo, useMemo, useRef, useEffect, useCallback } from "react"
import { useTranslation } from "react-i18next"
import { Plus as AddIcon, Calendar as TodayIcon } from "lucide-react"
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
  | "currentProgress"
> & {
  isOnline: boolean
  getLessonTypeColor: (type?: string | null) => string
  getLessonTypeLabel: (val?: string | null) => string
  onDeleteLesson: (id: string) => void
  /** Lesson note indicators (FIX-67-02). CQ-71-06: non-optional — default empty Map at source */
  notesMap: Map<string, boolean>
}

export const ScheduleDesktopTable = memo(function ScheduleDesktopTable({
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
  currentProgress,
  notesMap,
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
  const tableRows = useMemo(() => buildTable(schedule, weekdayBackend), [schedule, weekdayBackend])

  const canEdit = user?.role === "admin" || user?.role === "teacher"
  const colCount = visibleDays.length + 1
  const isEmpty = tableRows.length === 0

  // RESP-70-02: detect horizontal overflow for scroll indicator
  const containerRef = useRef<HTMLDivElement>(null)
  const scrollRef = useRef<HTMLDivElement>(null)
  const checkOverflow = useCallback(() => {
    const el = scrollRef.current
    const container = containerRef.current
    if (!el || !container) return
    const overflows = el.scrollWidth > el.clientWidth
    container.toggleAttribute("data-overflows", overflows)
  }, [])
  // PERF-71-02: removed direct checkOverflow() call — ResizeObserver fires immediately on .observe()
  useEffect(() => {
    const el = scrollRef.current
    if (!el) return
    const ro = new ResizeObserver(checkOverflow)
    ro.observe(el)
    return () => ro.disconnect()
  }, [checkOverflow, visibleDays.length])

  return (
    <div ref={containerRef} className="schedule-grid-container mx-auto w-full">
      {/* ── Scrollable wrapper ──────────────────────────── */}
      <div ref={scrollRef} className="sched-scroll-wrapper">
        <div
          role="grid"
          aria-label={t("schedule:title.default")}
          aria-rowcount={tableRows.length + 1}
          aria-colcount={colCount}
          className="sched-card-matte w-full text-text-primary"
          style={{
            display: "grid",
            gridTemplateColumns: `var(--sched-grid-header-w) repeat(${visibleDays.length}, minmax(var(--sched-grid-col-min), 1fr))`,
            minWidth: `calc(var(--sched-grid-header-w) + ${visibleDays.length} * var(--sched-grid-col-min))`,
          }}
        >
          {/* ── Header row ────────────────────────────────────────────────
              Wave 120 SW3 (a11y/ARIA): wrapped header cells + each data
              row in `role="row"` containers with `display: contents` so
              CSS Grid layout is preserved (row is "transparent" to grid)
              while satisfying ARIA grid spec — `role="grid"` requires
              `role="row"` children, `role="columnheader"`/`rowheader`/
              `gridcell` require `role="row"` parent. Closes axe
              `aria-required-children` + `aria-required-parent`.
          */}
          <div role="row" aria-rowindex={1} style={{ display: "contents" }}>
            <div
              role="columnheader"
              aria-colindex={1}
              className="sched-sticky-col sched-sticky-header flex items-center justify-center border-b border-r px-2 py-3 text-xs font-bold text-text-muted-subtle"
              style={{ borderColor: "var(--sched-grid-border)" }}
            >
              {t("schedule:table.rowNumber")}
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
                    "sched-column-item sched-sticky-header sched-day-snap flex items-center justify-center gap-2 border-b px-3 py-3 text-sm font-semibold",
                    isTodayCol && "sched-today-header"
                  )}
                  style={
                    {
                      "--sched-col-i": colI,
                      borderColor: "var(--sched-grid-border)",
                    } as React.CSSProperties
                  }
                >
                  <span className={cn("tracking-tight", isTodayCol && "text-brand font-bold")}>
                    {label}
                  </span>
                  {isTodayCol && (
                    <span className="sched-today-badge inline-flex items-center gap-1 rounded-full bg-brand px-2 py-0.5 text-[0.5625rem] font-bold text-[var(--sched-on-accent)] shadow-glow-primary">
                      <TodayIcon size={9} aria-hidden="true" />
                      {t("schedule:toolbar.today", { defaultValue: "" })}
                    </span>
                  )}
                  {canEdit && (
                    <button
                      type="button"
                      aria-label={t("schedule:actions.addLesson", { day: label })}
                      className="flex h-6 w-6 items-center justify-center rounded-md text-text-secondary transition-all duration-fast hover:bg-brand hover:text-[var(--sched-on-accent)] focus-visible:ring-2 focus-visible:ring-brand"
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
          </div>

          {/* ── Empty state ─────────────────────────────────────────────
              Wrapped in `role="row"` + `role="gridcell"` (spanning all cols)
              so the grid still satisfies aria-required-children when no
              data rows exist (Wave 120 SW3).
          */}
          {isEmpty && (
            <div role="row" aria-rowindex={2} style={{ display: "contents" }}>
              <div
                role="gridcell"
                aria-colindex={1}
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
                    description={t("schedule:empty.selectGroup")}
                  />
                )}
              </div>
            </div>
          )}

          {/* ── Data rows ─────────────────────────────────── */}
          {tableRows.map((row, rowIdx) => {
            const visibleCells = visibleDays.map(({ idx: originalIdx }) => ({
              lesson: row[originalIdx] ?? null,
              originalIdx,
            }))

            return (
              <div
                key={`row-${rowIdx}`}
                role="row"
                aria-rowindex={rowIdx + 2}
                style={{ display: "contents" }}
              >
                {/* Row number — sticky left */}
                <div
                  role="rowheader"
                  aria-colindex={1}
                  className="sched-sticky-col flex items-center justify-center border-b border-r px-2 py-2 text-xs font-bold text-text-secondary"
                  style={{ borderColor: "var(--sched-grid-border)" }}
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
                        aria-colindex={colI + 2}
                        aria-label={t("schedule:table.emptyCell", {
                          day: visibleDays[colI]?.label ?? "",
                          row: rowIdx + 1,
                          defaultValue: "Empty",
                        })}
                        className={cn(
                          "sched-grid-cell sched-day-snap flex items-center justify-center border-b outline-none",
                          isTodayCol && "sched-today-col"
                        )}
                        style={{ borderColor: "var(--sched-grid-border)" }}
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
                  const breakMinutes = hasBreakBefore
                    ? minutesDiff(tableRows[rowIdx - 1]?.[originalIdx]?.end_time, lesson.start_time)
                    : 0

                  return (
                    <div
                      key={lesson.id}
                      id={`sched-cell-${rowIdx}-${colI}`}
                      role="gridcell"
                      tabIndex={-1}
                      aria-colindex={colI + 2}
                      className={cn(
                        "sched-grid-cell sched-day-snap relative border-b outline-none",
                        isTodayCol && "sched-today-col"
                      )}
                      style={{ borderColor: "var(--sched-grid-border)" }}
                    >
                      {/* Break indicator — compact pill */}
                      {hasBreakBefore && breakMinutes > 0 && (
                        <div className="mb-1 flex justify-center">
                          <span className="sched-break-pill">
                            {t("schedule:break", { minutes: breakMinutes })}
                          </span>
                        </div>
                      )}

                      <LessonCard
                        lesson={lesson}
                        isConflict={isConflict}
                        isCurrent={isCurrent}
                        currentProgress={isCurrent ? currentProgress : 0}
                        index={rowIdx * visibleDays.length + colI}
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
            )
          })}
        </div>
      </div>
    </div>
  )
})

export default ScheduleDesktopTable

