import { useMemo, useState, useCallback } from "react"
import { useTranslation } from "react-i18next"
import { ChevronLeft, ChevronRight } from "lucide-react"
import { cn } from "@/utils/cn"

interface ScheduleMiniCalendarProps {
  /** Days that have lessons (0-based day-of-month) */
  lessonDays?: Set<number>
  /** Current month to display (default: now) */
  month?: Date
  onMonthChange?: (date: Date) => void
  /** Called when a day is clicked */
  onDayClick?: (date: Date) => void
  /** Show loading skeleton (FIX-67-07) */
  isLoading?: boolean
  className?: string
}

export function ScheduleMiniCalendar({
  lessonDays = new Set(),
  month,
  onMonthChange,
  onDayClick,
  isLoading = false,
  className,
}: ScheduleMiniCalendarProps) {
  const { t, i18n } = useTranslation(["common"])
  // CQ-71-04: stable reference — avoid new Date() on every render
  const [now] = useState(() => new Date())

  // Controlled + uncontrolled month support
  const [internalMonth, setInternalMonth] = useState(() => month ?? now)
  const displayMonth = month ?? internalMonth

  const year = displayMonth.getFullYear()
  const monthIdx = displayMonth.getMonth()

  // i18n weekday labels (Mon-Sun) — no hardcoded Russian
  const weekdayLabels = useMemo(() => {
    const formatter = new Intl.DateTimeFormat(i18n.language, { weekday: "narrow" })
    // Jan 6 2025 is a Monday — generate Mon→Sun labels
    return Array.from({ length: 7 }, (_, i) => formatter.format(new Date(2025, 0, 6 + i)))
  }, [i18n.language])

  const { days, firstDayOffset } = useMemo(() => {
    const daysInMonth = new Date(year, monthIdx + 1, 0).getDate()
    // Monday = 0, Sunday = 6
    const firstDay = new Date(year, monthIdx, 1).getDay()
    const offset = firstDay === 0 ? 6 : firstDay - 1 // shift to Monday-start

    const result: number[] = []
    for (let d = 1; d <= daysInMonth; d++) result.push(d)
    return { days: result, firstDayOffset: offset }
  }, [year, monthIdx])

  const todayDate = now.getDate()
  const isCurrentMonth = now.getFullYear() === year && now.getMonth() === monthIdx

  // Locale-aware month label
  const monthLabel = displayMonth.toLocaleDateString(i18n.language, {
    month: "long",
    year: "numeric",
  })

  const changeMonth = useCallback(
    (delta: number) => {
      const next = new Date(year, monthIdx + delta, 1)
      setInternalMonth(next)
      onMonthChange?.(next)
    },
    [year, monthIdx, onMonthChange]
  )

  const handleDayClick = useCallback(
    (day: number) => {
      onDayClick?.(new Date(year, monthIdx, day))
    },
    [year, monthIdx, onDayClick]
  )

  // Date formatter for day aria-labels
  const dayFormatter = useMemo(
    () => new Intl.DateTimeFormat(i18n.language, { dateStyle: "long" }),
    [i18n.language]
  )

  return (
    <div className={cn("sched-matte-card rounded-xl p-4", className)}>
      {/* ── Month navigation ──────────────────────────── */}
      <div className="mb-3 flex items-center justify-between">
        <button
          type="button"
          onClick={() => changeMonth(-1)}
          aria-label={t("common:prev", { defaultValue: "Previous" })}
          className="flex h-7 w-7 items-center justify-center rounded-lg text-text-secondary transition-colors hover:bg-surface-elevated/(--opacity-dim) hover:text-text-primary focus-visible:ring-2 focus-visible:ring-brand"
        >
          <ChevronLeft size={14} aria-hidden="true" />
        </button>
        <span className="text-sm font-semibold capitalize text-text-primary">{monthLabel}</span>
        {/* FEAT-71-05: quick-return to current month when navigated away */}
        {!isCurrentMonth && (
          <button
            type="button"
            onClick={() => {
              const today = new Date()
              setInternalMonth(today)
              onMonthChange?.(today)
            }}
            className="ml-1 rounded-md bg-brand px-2 py-0.5 text-[0.5625rem] font-bold text-[var(--sched-on-accent)] transition-colors hover:bg-brand-hover focus-visible:ring-2 focus-visible:ring-brand"
          >
            {t("common:today", { defaultValue: "Today" })}
          </button>
        )}
        <button
          type="button"
          onClick={() => changeMonth(1)}
          aria-label={t("common:next", { defaultValue: "Next" })}
          className="flex h-7 w-7 items-center justify-center rounded-lg text-text-secondary transition-colors hover:bg-surface-elevated/(--opacity-dim) hover:text-text-primary focus-visible:ring-2 focus-visible:ring-brand"
        >
          <ChevronRight size={14} aria-hidden="true" />
        </button>
      </div>

      {/* ── Weekday headers ───────────────────────────── */}
      <div className="mb-1 grid grid-cols-7 gap-0.5">
        {weekdayLabels.map((label, i) => (
          <div
            key={i}
            className="flex h-6 items-center justify-center text-[0.625rem] font-medium text-text-secondary"
          >
            {label}
          </div>
        ))}
      </div>

      {/* ── Day grid ──────────────────────────────────────────────────
          Wave 120 SW3 (a11y/ARIA): added `role="row"` week wrappers (with
          `display: contents` so CSS Grid layout is preserved) + `role="gridcell"`
          on all cells. ARIA grid pattern requires row containers; date-picker
          variant per WAI-ARIA APG. `aria-busy="true"` during loading
          suppresses aria-required-children check while skeleton renders.
          Closes axe `aria-required-children` on monthLabel grid.
      */}
      <div
        className="grid grid-cols-7 gap-0.5"
        role="grid"
        aria-label={monthLabel}
        aria-busy={isLoading ? "true" : undefined}
      >
        {isLoading
          ? Array.from({ length: 35 }).map((_, i) => (
              <div
                key={`skel-${i}`}
                className="flex h-8 items-center justify-center"
                role="presentation"
              >
                {/* THEME-71-03: use sched-skeleton-shimmer instead of Tailwind animate-pulse */}
                <div className="h-6 w-6 sched-skeleton-shimmer rounded-full" />
              </div>
            ))
          : (() => {
              // Build flat cell array (offset + days), then chunk into weeks
              type Cell = { kind: "empty"; key: string } | { kind: "day"; day: number }
              const cells: Cell[] = []
              for (let i = 0; i < firstDayOffset; i++) {
                cells.push({ kind: "empty", key: `offset-${i}` })
              }
              for (const day of days) {
                cells.push({ kind: "day", day })
              }
              // Chunk into weeks of 7 (last week may be partial; that's OK
              // per ARIA grid spec — rows can have variable cell counts).
              const weeks: Cell[][] = []
              for (let i = 0; i < cells.length; i += 7) {
                weeks.push(cells.slice(i, i + 7))
              }
              return weeks.map((week, weekI) => (
                <div
                  key={`week-${weekI}`}
                  role="row"
                  aria-rowindex={weekI + 1}
                  style={{ display: "contents" }}
                >
                  {week.map((cell, colI) => {
                    if (cell.kind === "empty") {
                      return (
                        <div
                          key={cell.key}
                          role="gridcell"
                          aria-colindex={colI + 1}
                          className="h-8"
                        />
                      )
                    }
                    const day = cell.day
                    const isToday = isCurrentMonth && day === todayDate
                    const fullDate = new Date(year, monthIdx, day)
                    return (
                      <div key={day} role="gridcell" aria-colindex={colI + 1}>
                        <button
                          type="button"
                          className="sched-cal-day text-text-primary"
                          data-today={isToday ? "true" : undefined}
                          data-has-lessons={lessonDays.has(day) ? "true" : undefined}
                          aria-label={dayFormatter.format(fullDate)}
                          aria-current={isToday ? "date" : undefined}
                          onClick={() => handleDayClick(day)}
                        >
                          {day}
                        </button>
                      </div>
                    )
                  })}
                </div>
              ))
            })()}
      </div>
    </div>
  )
}
