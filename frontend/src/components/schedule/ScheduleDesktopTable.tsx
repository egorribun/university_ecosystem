import {
  useState,
  useEffect,
  useRef,
  useDeferredValue,
  startTransition,
  useMemo,
  useCallback,
} from "react"
import { useTranslation } from "react-i18next"
import { Plus as AddIcon } from "lucide-react"
import { Badge } from "@/components/ui"
import OfflineFallback from "@/components/OfflineFallback"
import { cn } from "@/utils/cn"
import { type Lesson, buildTable, minutesDiff } from "@/components/schedule/scheduleUtils"
import { LessonCard } from "@/components/schedule/LessonCard"
import { useScheduleData } from "@/hooks/useScheduleData"
import { useSchedulePage } from "@/contexts/SchedulePageContext"

const SCROLL_OFFSET_PX = 120

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
  | "isLoading"
  | "lessonTypeLabels"
> & {
  isOnline: boolean
  getLessonTypeColor: (type?: string | null) => string
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
  lessonTypeLabels,
  getLessonTypeColor,
  onDeleteLesson,
}: ScheduleDesktopTableProps) {
  const { t } = useTranslation(["schedule", "common"])
  const { openDialog, setAddDay } = useSchedulePage()

  const tableScrollRef = useRef<HTMLDivElement | null>(null)
  const headRefs = useRef<(HTMLTableCellElement | null)[]>([])


  const tableRowsBase = useMemo(
    () => buildTable(schedule, weekdayBackend),
    [schedule, weekdayBackend]
  )
  const tableRows = useDeferredValue(tableRowsBase)
  const [rowLimit, setRowLimit] = useState(0)

  // Virtualization / Incremental Rendering Logic
  useEffect(() => {
    setRowLimit(() => Math.min(12, tableRows.length))
  }, [tableRows.length])

  useEffect(() => {
    let cancelled = false
    const chunk = 12
    const step = () => {
      if (cancelled) return
      startTransition(() => {
        setRowLimit((prev) => Math.min(prev + chunk, tableRows.length))
      })
      if (!cancelled && rowLimit < tableRows.length) {
        if ("requestIdleCallback" in window) window.requestIdleCallback(step)
        else setTimeout(step, 0)
      }
    }
    if (tableRows.length > 0 && rowLimit < tableRows.length) {
      if ("requestIdleCallback" in window) window.requestIdleCallback(step)
      else setTimeout(step, 0)
    }
    return () => {
      cancelled = true
    }
  }, [tableRows, rowLimit])

  // Scroll to today
  useEffect(() => {
    if (!hasToday) return
    const container = tableScrollRef.current
    const cell = todayIdx >= 0 ? headRefs.current[todayIdx] : null
    if (container && cell) {
      const left = cell.offsetLeft - SCROLL_OFFSET_PX
      container.scrollTo({ left, behavior: "smooth" })
    }
  }, [rowLimit, todayIdx, hasToday])

  const getLessonTypeLabel = useCallback(
    (val?: string | null) => lessonTypeLabels.get(val ?? "") ?? val ?? "",
    [lessonTypeLabels]
  )

  const renderBreakChip = (rowIdx: number, colIdx: number) => {
    if (rowIdx === 0) return null
    const prev = tableRows[rowIdx - 1]?.[colIdx]
    const curr = tableRows[rowIdx]?.[colIdx]
    if (!prev || !curr) return null
    const gap = minutesDiff(prev.end_time, curr.start_time)
    if (gap <= 0) return null
    return (
      <div className="pointer-events-none absolute left-1/(--opacity-trace) top-[calc(var(--space-4)*-1)] z-deep -translate-x-1/(--opacity-trace)">
        <Badge
          size="xs"
          className="chip-break font-medium bg-warning-bg/(--opacity-dim) border border-warning-border/(--opacity-soft) text-warning-text shadow-sm"
        >
          {t("schedule:break", { minutes: gap })}
        </Badge>
      </div>
    )
  }

  // renderBreakChip helper above

  const visibleRows = tableRows.slice(0, rowLimit)

  return (
    <div
      ref={tableScrollRef}
      className="scrollbar-hide min-h-(--min-h-hero-md) mx-auto w-full max-w-(--layout-max-ultrawide) overflow-x-auto rounded-lg border border-glass-border bg-surface/(--opacity-medium) text-text-primary shadow-glass backdrop-blur-md scroll-smooth"
    >
      <table className="w-full border-collapse">
        <thead className="sticky top-0 z-sticky shadow-sm">
          <tr>
            <th className="sticky left-0 z-navbar w-(--w-sidebar-collapsed) border-r border-glass-border bg-surface-raised px-4 py-4 text-center font-extrabold text-primary shadow-md backdrop-blur-md">
              №
            </th>
            {weekdayBackend.map((day, idx) => {
              const label = weekdayLabels[idx] ?? day
              const isTodayCol = hasToday && idx === todayIdx
              return (
                <th
                  key={day}
                  ref={(el) => {
                    headRefs.current[idx] = el
                  }}
                  className={cn(
                    isTodayCol
                      ? "bg-brand/(--opacity-subtle) shadow-focus"
                      : "bg-surface/(--opacity-medium)",
                    "z-surface backdrop-blur-md transition-colors duration-fast"
                  )}
                >
                  <div className="flex items-center justify-center gap-2">
                    <span className={cn("tracking-tight", isTodayCol && "text-brand")}>
                      {label}
                    </span>
                    {(user?.role === "admin" || user?.role === "teacher") && (
                      <button
                        className="flex h-7 w-7 items-center justify-center rounded-xs border border-glass-border bg-surface/(--opacity-strong) text-brand transition-colors hover:bg-brand hover:text-white"
                        onClick={(event) => {
                          event.stopPropagation()
                          setAddDay(day)
                          openDialog("add")
                        }}
                      >
                        <AddIcon className="h-3.5 w-3.5" />
                      </button>
                    )}
                  </div>
                </th>
              )
            })}
          </tr>
        </thead>
        <tbody>
          {visibleRows.length === 0 ? (
            <tr>
              <td colSpan={weekdayBackend.length + 1} className="px-6 py-12">
                {!isOnline && rawSchedule.length === 0 ? (
                  <div className="flex justify-center">
                    <OfflineFallback onRetry={refresh} />
                  </div>
                ) : (
                  <p className="text-center">{t("schedule:table.noLessons")}</p>
                )}
              </td>
            </tr>
          ) : (
            visibleRows.map((row: (Lesson | null)[], rowIdx: number) => (
              <tr key={rowIdx}>
                <td className="sticky left-0 z-sticky border-r border-glass-border bg-surface/(--opacity-strong) px-4 py-3 text-center font-bold shadow-md backdrop-blur-md">
                  {rowIdx + 1}
                </td>
                {row.map((lesson: Lesson | null, colIdx: number) => {
                  const colIsToday = hasToday && colIdx === todayIdx
                  if (!lesson) {
                    return (
                      <td
                        key={`empty-${rowIdx}-${colIdx}`}
                        className={cn("p-3", colIsToday ? "bg-(--bg-surface-hover)" : "")}
                      >
                        <div className="min-h-(--h-skeleton-row) w-full animate-pulse rounded-sm bg-surface-hover/(--opacity-subtle)" />
                      </td>
                    )
                  }
                  let hasBreakBefore = false
                  if (rowIdx > 0) {
                    const prev = visibleRows[rowIdx - 1]?.[colIdx]
                    if (prev) {
                      const gap = minutesDiff(prev.end_time, lesson.start_time)
                      hasBreakBefore = gap > 0
                    }
                  }
                  const isConflict = conflictedIds.has(lesson.id)
                  return (
                    <td
                      key={lesson.id}
                      className={cn(
                        "relative overflow-visible p-3",
                        colIsToday ? "bg-brand/(--opacity-faint)" : ""
                      )}
                    >
                      {renderBreakChip(rowIdx, colIdx)}
                      <LessonCard
                        lesson={lesson}
                        isConflict={isConflict}
                        hasBreakBefore={hasBreakBefore}
                        onOpen={() => openDialog("details", lesson)}
                        onDelete={() => onDeleteLesson(lesson.id)}
                        canEdit={user?.role === "admin" || user?.role === "teacher"}
                        getLessonTypeColor={getLessonTypeColor}
                        getLessonTypeLabel={getLessonTypeLabel}
                      />
                    </td>
                  )
                })}
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  )
}
