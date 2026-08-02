import { useRef, useMemo, useCallback, useState } from "react"
import { useTranslation } from "react-i18next"
import { AnimatePresence, m } from "framer-motion"
import useMediaQuery from "@/hooks/useMediaQuery"
import { Badge } from "@/components/ui"
import { DayColumn } from "@/components/schedule/DayColumn"
import { useScheduleData } from "@/hooks/useScheduleData"
import { useSchedulePage } from "@/contexts/SchedulePageContext"
import { buildLessonsByDay } from "@/components/schedule/scheduleUtils"
import {
  useScheduleDisplayPreferences,
  useScheduleUIActions,
  useWeekOffset,
} from "@/stores/scheduleUIStore"
import { useSwipe } from "@/hooks/useSwipe"
import { cn } from "@/utils/cn"

/**
 * ScheduleMobileView — Swipeable day carousel for mobile viewports.
 *
 * Renders horizontally-scrollable day chips (tab bar) with a Framer Motion
 * layoutId pill indicator. Supports left/right swipe gestures (via useSwipe)
 * for week navigation with directional slide animation, arrow-key tab
 * switching for a11y, and delegates each day's content to DayColumn.
 * Only one day visible at a time.
 */
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
  | "currentProgress"
> & {
  isOnline: boolean
  onDeleteLesson: (id: string) => void
  getLessonTypeColor: (type?: string | null) => string
  getLessonTypeLabel: (val?: string | null) => string
  /** Lesson note indicators (FIX-67-02). CQ-71-06: non-optional */
  notesMap: Map<string, boolean>
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
  currentProgress,
  notesMap,
  todayComplete,
}: ScheduleMobileViewProps) {
  const { t } = useTranslation(["schedule"])
  const { openDialog, setAddDay } = useSchedulePage()
  const { compactMode } = useScheduleDisplayPreferences()
  const prefersReduced = useMediaQuery("(prefers-reduced-motion: reduce)")
  const { nextWeek, previousWeek } = useScheduleUIActions()
  const weekOffset = useWeekOffset()
  const dayCardRefs = useRef<(HTMLDivElement | null)[]>([])
  const [activeDayIdx, setActiveDayIdx] = useState(() => (hasToday && todayIdx >= 0 ? todayIdx : 0))

  /* ── Week swipe direction tracking (FIX-70-SWIPE) ────
     React-safe derived state pattern: setState during render is allowed
     when conditional (React docs: "Adjusting state during rendering").
     This ensures direction is correct on the FIRST frame — unlike useEffect
     which fires after paint, causing wrong-direction flicker. ──────────── */
  const [swipeDir, setSwipeDir] = useState<1 | -1>(1)
  const [prevWeek, setPrevWeek] = useState(weekOffset)

  if (weekOffset !== prevWeek) {
    setSwipeDir(weekOffset > prevWeek ? 1 : -1)
    setPrevWeek(weekOffset)
  }

  const handleSwipeLeft = useCallback(() => {
    setSwipeDir(1) // content slides left → new week from right
    nextWeek()
  }, [nextWeek])

  const handleSwipeRight = useCallback(() => {
    setSwipeDir(-1) // content slides right → new week from left
    previousWeek()
  }, [previousWeek])

  const swipeHandlers = useSwipe({
    onSwipeLeft: handleSwipeLeft,
    onSwipeRight: handleSwipeRight,
  })

  // CQ-71-05: shared utility (also used by ScheduleListView)
  const lessonsByDay = useMemo(
    () => buildLessonsByDay(schedule, weekdayBackend),
    [schedule, weekdayBackend]
  )

  /* ── Scroll to day section ───────────────────────────── */
  const scrollToDay = useCallback((idx: number) => {
    setActiveDayIdx(idx)
    dayCardRefs.current[idx]?.scrollIntoView({ behavior: "smooth", block: "start" })
  }, [])

  // Arrow key navigation between day tabs
  const handleTabKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === "ArrowRight" || e.key === "ArrowLeft") {
        e.preventDefault()
        const tabs = e.currentTarget.querySelectorAll<HTMLElement>('[role="tab"]')
        const current = document.activeElement
        const idx = Array.from(tabs).indexOf(current as HTMLElement)
        if (idx < 0) return
        const next =
          e.key === "ArrowRight" ? (idx + 1) % tabs.length : (idx - 1 + tabs.length) % tabs.length
        tabs[next]?.focus()
        scrollToDay(next)
      }
    },
    [scrollToDay]
  )

  /* ── Animation variants for week/day transitions ── */
  const slideX = 100 // px — wide enough to clearly show direction
  const panelVariants = {
    enter: (d: number) =>
      prefersReduced ? { opacity: 0 } : { opacity: 0, x: d * slideX, scale: 0.97 },
    center: { opacity: 1, x: 0, scale: 1 },
    exit: (d: number) =>
      prefersReduced ? { opacity: 0 } : { opacity: 0, x: d * -slideX, scale: 0.97 },
  }

  return (
    <div className="mt-2 flex w-full flex-col gap-4" {...swipeHandlers}>
      {/* ── Day navigation chips ── */}
      {/* FEAT-71-06: scroll fade masks on edges */}
      <div className="relative sched-chip-scroll">
        {/* eslint-disable-next-line jsx-a11y/interactive-supports-focus -- focus managed via child tab buttons */}
        <div
          role="tablist"
          aria-label={t("schedule:title.default")}
          className="scrollbar-hide flex gap-2 overflow-x-auto px-3 pb-2"
          onKeyDown={handleTabKeyDown}
        >
          {weekdayBackend.map((day, i) => {
            // buildLessonsByDay initializes an entry for every weekdayBackend item.
            const count = lessonsByDay.get(day)!.length
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
                  isActive ? "text-[var(--sched-on-accent)]" : "sched-badge-matte",
                  isToday && !isActive && "ring-1 ring-brand/(--opacity-dim)"
                )}
                onClick={() => scrollToDay(i)}
              >
                {isActive && (
                  <m.span
                    layoutId="schedule-mobile-day"
                    className="absolute inset-0 rounded-full bg-brand shadow-glow-primary"
                    transition={
                      prefersReduced
                        ? { duration: 0 }
                        : { type: "spring", stiffness: 400, damping: 30 }
                    }
                  />
                )}
                <span className="relative z-surface flex items-center gap-0.5">
                  {weekdayShort[i] ?? getDayLabel(day)}
                  {count > 0 && <sup className="text-[0.625rem] font-bold opacity-70">{count}</sup>}
                </span>
              </Badge>
            )
          })}
        </div>
      </div>

      {/* ── Active day panel — directional horizontal slide on week/day switch ──
           PERF-71-01: AnimatePresence with key-swap is acceptable here (unlike desktop PERF-70-01)
           because mobile shows only 1 DayColumn at a time — single remount is cheap. ──── */}
      <AnimatePresence mode="wait" initial={false} custom={swipeDir}>
        <m.div
          key={`${weekOffset}-${weekdayBackend[activeDayIdx] ?? activeDayIdx}`}
          custom={swipeDir}
          variants={panelVariants}
          initial="enter"
          animate="center"
          exit="exit"
          transition={
            prefersReduced
              ? { duration: 0 }
              : { type: "spring", stiffness: 260, damping: 26, mass: 0.9 }
          }
        >
          {(() => {
            const activeDay = weekdayBackend[activeDayIdx]!
            const activeLabel = weekdayLabels[activeDayIdx] ?? activeDay
            return (
              <DayColumn
                ref={(el) => {
                  dayCardRefs.current[activeDayIdx] = el
                }}
                day={activeDay}
                label={activeLabel}
                lessons={lessonsByDay.get(activeDay) ?? []}
                isToday={hasToday && activeDayIdx === todayIdx}
                isOnline={isOnline}
                hasSchedule={rawSchedule.length > 0}
                userRole={user?.role}
                conflictedIds={conflictedIds}
                compact={compactMode}
                currentLessonId={currentLesson?.id}
                currentProgress={currentProgress}
                dayComplete={hasToday && activeDayIdx === todayIdx && todayComplete}
                notesMap={notesMap}
                onAdd={() => {
                  setAddDay(activeDay)
                  openDialog("add")
                }}
                onLessonDelete={onDeleteLesson}
                onRetry={refresh}
                getLessonTypeColor={getLessonTypeColor}
                getLessonTypeLabel={getLessonTypeLabel}
              />
            )
          })()}
        </m.div>
      </AnimatePresence>
    </div>
  )
}
