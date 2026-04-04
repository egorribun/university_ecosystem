import { useRef, useMemo, useCallback } from "react"
import { useTranslation } from "react-i18next"
import { Badge } from "@/components/ui"
import { DayColumn } from "@/components/schedule/DayColumn"
import { useScheduleData } from "@/hooks/useScheduleData"
import { useSchedulePage } from "@/contexts/SchedulePageContext"
import { type Lesson, getTimeStr } from "@/components/schedule/scheduleUtils"
import { useScheduleDisplayPreferences, useScheduleUIActions } from "@/stores/scheduleUIStore"
import { useSwipe } from "@/hooks/useSwipe"
import { cn } from "@/utils/cn"

type ScheduleMobileViewProps = Pick<
  ReturnType<typeof useScheduleData>,
  | "schedule"
  | "weekdayBackend"
  | "weekdayLabels"
  | "weekdayShort"
  | "hasToday"
  | "todayIdx"
  | "getDayLabel"
  | "rawSchedule"
  | "refresh"
  | "user"
  | "conflictedIds"
  | "lessonTypeLabels"
  | "currentLesson"
> & {
  isOnline: boolean
  onDeleteLesson: (id: string) => void
  getLessonTypeColor: (type?: string | null) => string
  getLessonTypeLabel?: (val?: string | null) => string
}

export function ScheduleMobileView({
  schedule,
  weekdayBackend,
  weekdayLabels,
  weekdayShort,
  hasToday,
  todayIdx,
  getDayLabel,
  rawSchedule,
  refresh,
  user,
  conflictedIds,
  lessonTypeLabels,
  isOnline,
  onDeleteLesson,
  getLessonTypeColor,
  getLessonTypeLabel: getLessonTypeLabelProp,
  currentLesson,
}: ScheduleMobileViewProps) {
  const { t } = useTranslation(["schedule"])
  const { openDialog, setAddDay } = useSchedulePage()
  const { compactMode } = useScheduleDisplayPreferences()
  const { nextWeek, previousWeek } = useScheduleUIActions()
  const dayCardRefs = useRef<(HTMLDivElement | null)[]>([])

  // Swipe between weeks on mobile
  const swipeHandlers = useSwipe({
    onSwipeLeft: nextWeek,
    onSwipeRight: previousWeek,
  })

  // Use prop if provided, otherwise compute from lessonTypeLabels map
  const getLessonTypeLabelFallback = useCallback(
    (val?: string | null) => lessonTypeLabels.get(val ?? "") ?? val ?? "",
    [lessonTypeLabels],
  )
  const getLessonTypeLabel = getLessonTypeLabelProp ?? getLessonTypeLabelFallback

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

  /* ── Scroll to day section ───────────────────────────── */
  const scrollToDay = useCallback((idx: number) => {
    dayCardRefs.current[idx]?.scrollIntoView({ behavior: "smooth", block: "start" })
  }, [])

  // Arrow key navigation between day tabs
  const handleTabKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (e.key === "ArrowRight" || e.key === "ArrowLeft") {
      e.preventDefault()
      const tabs = e.currentTarget.querySelectorAll<HTMLElement>('[role="tab"]')
      const current = document.activeElement
      const idx = Array.from(tabs).indexOf(current as HTMLElement)
      if (idx < 0) return
      const next =
        e.key === "ArrowRight"
          ? (idx + 1) % tabs.length
          : (idx - 1 + tabs.length) % tabs.length
      tabs[next]?.focus()
      scrollToDay(next)
    }
  }, [scrollToDay])

  return (
    <div className="mt-2 flex w-full flex-col gap-4" {...swipeHandlers}>
      {/* ── Day navigation chips ──────────────────────── */}
      {/* eslint-disable-next-line jsx-a11y/interactive-supports-focus -- focus managed via child tab buttons */}
      <div
        role="tablist"
        aria-label={t("schedule:title.default")}
        className="scrollbar-hide flex gap-2 overflow-x-auto px-1 pb-2"
        onKeyDown={handleTabKeyDown}
      >
        {weekdayBackend.map((day, i) => {
          const count = lessonsByDay.get(day)?.length ?? 0
          const isToday = hasToday && i === todayIdx
          return (
            <Badge
              key={day}
              as="button"
              role="tab"
              aria-controls={`day-panel-${day}`}
              variant={isToday ? "solid" : "outline"}
              tone={isToday ? "primary" : "default"}
              className={cn(
                "sched-badge-matte shrink-0 font-semibold transition-all duration-fast hover:scale-105",
                isToday && "shadow-glow-primary"
              )}
              onClick={() => scrollToDay(i)}
            >
              {weekdayShort[i] ?? getDayLabel(day)}
              {count > 0 && (
                <sup className="ml-0.5 text-[0.625rem] font-bold opacity-70">{count}</sup>
              )}
            </Badge>
          )
        })}
      </div>

      {/* ── Day content panels ────────────────────────── */}
      {weekdayBackend.map((day, dayIdx) => {
        const label = weekdayLabels[dayIdx] ?? day
        const lessons = lessonsByDay.get(day) ?? []
        const isToday = hasToday && dayIdx === todayIdx

        return (
          <DayColumn
            key={day}
            ref={(el) => {
              dayCardRefs.current[dayIdx] = el
            }}
            day={day}
            label={label}
            lessons={lessons}
            isToday={isToday}
            isOnline={isOnline}
            hasSchedule={rawSchedule.length > 0}
            userRole={user?.role}
            conflictedIds={conflictedIds}
            compact={compactMode}
            currentLessonId={currentLesson?.id}
            onAdd={() => {
              setAddDay(day)
              openDialog("add")
            }}
            onLessonOpen={(l) => openDialog("details", l)}
            onLessonDelete={onDeleteLesson}
            onRetry={refresh}
            getLessonTypeColor={getLessonTypeColor}
            getLessonTypeLabel={getLessonTypeLabel}
          />
        )
      })}
    </div>
  )
}
