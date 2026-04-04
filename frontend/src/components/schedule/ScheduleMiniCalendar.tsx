import { useMemo } from "react"
import { useTranslation } from "react-i18next"
import { ChevronLeft, ChevronRight } from "lucide-react"
import { cn } from "@/utils/cn"

interface ScheduleMiniCalendarProps {
  /** Days that have lessons (0-based day-of-month) */
  lessonDays?: Set<number>
  /** Current month to display (default: now) */
  month?: Date
  onMonthChange?: (date: Date) => void
  className?: string
}

const WEEKDAY_LABELS = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]

export function ScheduleMiniCalendar({
  lessonDays = new Set(),
  month,
  onMonthChange,
  className,
}: ScheduleMiniCalendarProps) {
  const { t } = useTranslation(["common"])
  const now = new Date()
  const displayMonth = month ?? now

  const year = displayMonth.getFullYear()
  const monthIdx = displayMonth.getMonth()

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

  const monthLabel = displayMonth.toLocaleDateString("ru-RU", {
    month: "long",
    year: "numeric",
  })

  const goPrev = () => {
    const prev = new Date(year, monthIdx - 1, 1)
    onMonthChange?.(prev)
  }

  const goNext = () => {
    const next = new Date(year, monthIdx + 1, 1)
    onMonthChange?.(next)
  }

  return (
    <div
      className={cn(
        "rounded-xl border border-glass-border bg-surface/(--opacity-medium) p-4 shadow-glass backdrop-blur-md glass-noise",
        className,
      )}
    >
      {/* ── Month navigation ──────────────────────────── */}
      <div className="mb-3 flex items-center justify-between">
        <button
          onClick={goPrev}
          aria-label={t("common:prev", { defaultValue: "Previous" })}
          className="flex h-7 w-7 items-center justify-center rounded-lg text-text-secondary transition-colors hover:bg-surface-elevated/(--opacity-dim) hover:text-text-primary"
        >
          <ChevronLeft size={14} aria-hidden="true" />
        </button>
        <span className="text-sm font-semibold capitalize text-text-primary">
          {monthLabel}
        </span>
        <button
          onClick={goNext}
          aria-label={t("common:next", { defaultValue: "Next" })}
          className="flex h-7 w-7 items-center justify-center rounded-lg text-text-secondary transition-colors hover:bg-surface-elevated/(--opacity-dim) hover:text-text-primary"
        >
          <ChevronRight size={14} aria-hidden="true" />
        </button>
      </div>

      {/* ── Weekday headers ───────────────────────────── */}
      <div className="mb-1 grid grid-cols-7 gap-0.5">
        {WEEKDAY_LABELS.map((label) => (
          <div
            key={label}
            className="flex h-6 items-center justify-center text-[0.625rem] font-medium text-text-secondary"
          >
            {label}
          </div>
        ))}
      </div>

      {/* ── Day grid ──────────────────────────────────── */}
      <div className="grid grid-cols-7 gap-0.5">
        {/* Empty cells for offset */}
        {Array.from({ length: firstDayOffset }).map((_, i) => (
          <div key={`empty-${i}`} className="h-8" />
        ))}
        {/* Day cells */}
        {days.map((day) => (
          <div
            key={day}
            className="sched-cal-day text-text-primary"
            data-today={isCurrentMonth && day === todayDate ? "true" : undefined}
            data-has-lessons={lessonDays.has(day) ? "true" : undefined}
          >
            {day}
          </div>
        ))}
      </div>
    </div>
  )
}
