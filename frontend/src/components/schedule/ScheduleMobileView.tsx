import { useRef, useMemo, useCallback } from "react"
import { Badge } from "@/components/ui"
import { DayColumn } from "@/components/schedule/DayColumn"
import { useScheduleData } from "@/hooks/useScheduleData"
import { useSchedulePage } from "@/contexts/SchedulePageContext"
import { type Lesson, getTimeStr } from "@/components/schedule/scheduleUtils"

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
}: ScheduleMobileViewProps) {
  const { openDialog, setAddDay } = useSchedulePage()
  const dayCardRefs = useRef<(HTMLDivElement | null)[]>([])

  const getLessonTypeLabel = useCallback(
    (val?: string | null) => lessonTypeLabels.get(val ?? "") ?? val ?? "",
    [lessonTypeLabels]
  )

  const lessonsByDay = useMemo(() => {
    const map = new Map<string, Lesson[]>()
    for (const day of weekdayBackend) {
      map.set(
        day,
        schedule
          .filter((l) => l.weekday === day)
          .sort((a, b) => getTimeStr(a).localeCompare(getTimeStr(b)))
      )
    }
    return map
  }, [schedule, weekdayBackend])

  return (
    <div className="mt-2 flex w-full flex-col gap-6">
      <div className="scrollbar-hide flex gap-2 overflow-x-auto px-1 pb-2">
        {weekdayBackend.map((day, i) => (
          <Badge
            key={day}
            as="button"
            variant={hasToday && i === todayIdx ? "solid" : "outline"}
            tone={hasToday && i === todayIdx ? "primary" : "default"}
            className="chip-day shrink-0 font-semibold transition-all duration-fast hover:scale-105"
            onClick={() =>
              dayCardRefs.current[i]?.scrollIntoView({ behavior: "smooth", block: "start" })
            }
          >
            {weekdayShort[i] ?? getDayLabel(day)}
          </Badge>
        ))}
      </div>

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
