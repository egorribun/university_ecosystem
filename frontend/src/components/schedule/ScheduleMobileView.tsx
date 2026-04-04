import { useRef, useMemo, useCallback } from "react"
import { useTranslation } from "react-i18next"
import { Badge } from "@/components/ui"
import { DayColumn } from "@/components/schedule/DayColumn"
import { useScheduleData } from "@/hooks/useScheduleData"
import { useSchedulePage } from "@/contexts/SchedulePageContext"
import { type Lesson, getTimeStr } from "@/components/schedule/scheduleUtils"
import { useScheduleDisplayPreferences } from "@/stores/scheduleUIStore"
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
  currentLesson,
}: ScheduleMobileViewProps) {
  const { t } = useTranslation(["schedule"])
  const { openDialog, setAddDay } = useSchedulePage()
  const { compactMode } = useScheduleDisplayPreferences()
  const dayCardRefs = useRef<(HTMLDivElement | null)[]>([])

  const getLessonTypeLabel = useCallback(
    (val?: string | null) => lessonTypeLabels.get(val ?? "") ?? val ?? "",
    [lessonTypeLabels],
  )

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

  return (
    <div className="mt-2 flex w-full flex-col gap-4">
      {/* ── Day navigation chips ──────────────────────── */}
      <div
        role="tablist"
        aria-label={t("schedule:title.default")}
        className="scrollbar-hide flex gap-2 overflow-x-auto px-1 pb-2"
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
