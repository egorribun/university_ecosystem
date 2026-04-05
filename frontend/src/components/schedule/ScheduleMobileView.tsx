import { useRef, useMemo, useCallback, useState } from "react"
import { useTranslation } from "react-i18next"
import { AnimatePresence, motion } from "framer-motion"
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
  | "currentLesson"
> & {
  isOnline: boolean
  onDeleteLesson: (id: string) => void
  getLessonTypeColor: (type?: string | null) => string
  getLessonTypeLabel: (val?: string | null) => string
  /** Lesson note indicators (FIX-67-02) */
  notesMap?: Map<string, boolean>
  /** All today's lessons are past (FIX-68-23) */
  todayComplete?: boolean
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
  isOnline,
  onDeleteLesson,
  getLessonTypeColor,
  getLessonTypeLabel,
  currentLesson,
  notesMap,
  todayComplete,
}: ScheduleMobileViewProps) {
  const { t } = useTranslation(["schedule"])
  const { openDialog, setAddDay } = useSchedulePage()
  const { compactMode } = useScheduleDisplayPreferences()
  const { nextWeek, previousWeek } = useScheduleUIActions()
  const dayCardRefs = useRef<(HTMLDivElement | null)[]>([])
  const [activeDayIdx, setActiveDayIdx] = useState(() => (hasToday && todayIdx >= 0 ? todayIdx : 0))

  // Swipe between weeks on mobile
  const swipeHandlers = useSwipe({
    onSwipeLeft: nextWeek,
    onSwipeRight: previousWeek,
  })

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
    setActiveDayIdx(idx)
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
      {/* ── Day navigation chips ── */}
      {/* FIX-68-26: removed left edge fade — it darkened the first tab (Пн).
          Right fade kept to indicate more tabs beyond the scroll edge. */}
      <div className="relative">
        <div className="pointer-events-none absolute inset-y-0 right-0 z-10 w-4 bg-gradient-to-l from-page to-transparent" />
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
          const isActive = i === activeDayIdx
          return (
            <Badge
              key={day}
              id={`day-tab-${day}`}
              as="button"
              role="tab"
              aria-controls={`day-panel-${day}`}
              aria-selected={isActive}
              tabIndex={isActive ? 0 : -1}
              variant={isActive ? "solid" : "outline"}
              tone={isActive ? "primary" : "default"}
              className={cn(
                "relative shrink-0 font-semibold transition-all duration-fast hover:scale-105",
                isActive ? "text-white" : "sched-badge-matte",
                isToday && !isActive && "ring-1 ring-brand/(--opacity-dim)"
              )}
              onClick={() => scrollToDay(i)}
            >
              {isActive && (
                <motion.span
                  layoutId="schedule-mobile-day"
                  className="absolute inset-0 rounded-full bg-brand shadow-glow-primary"
                  transition={{ type: "spring", stiffness: 400, damping: 30 }}
                />
              )}
              <span className="relative z-surface flex items-center gap-0.5">
                {weekdayShort[i] ?? getDayLabel(day)}
                {count > 0 && (
                  <sup className="text-[0.625rem] font-bold opacity-70">{count}</sup>
                )}
              </span>
            </Badge>
          )
        })}
        </div>
      </div>

      {/* ── Day content panels with crossfade (FIX-68-20) ── */}
      <AnimatePresence mode="wait" initial={false}>
        {weekdayBackend.map((day, dayIdx) => {
          // Only render active day panel for smooth crossfade
          if (dayIdx !== activeDayIdx) return null
          const label = weekdayLabels[dayIdx] ?? day
          const lessons = lessonsByDay.get(day) ?? []
          const isToday = hasToday && dayIdx === todayIdx

          return (
            <motion.div
              key={day}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -8 }}
              transition={{ duration: 0.15, ease: [0.25, 0.1, 0.25, 1] }}
            >
              <DayColumn
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
                dayComplete={isToday && todayComplete}
                notesMap={notesMap}
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
            </motion.div>
          )
        })}
      </AnimatePresence>
    </div>
  )
}
