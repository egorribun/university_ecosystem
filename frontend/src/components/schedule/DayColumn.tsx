import { forwardRef } from "react"
import { useTranslation } from "react-i18next"
import { Plus as AddIcon, CalendarOff as EmptyDayIcon } from "lucide-react"
import { cn } from "@/utils/cn"
import { Badge } from "@/components/ui"
import { EmptyState } from "@/components/ui/EmptyState"
import OfflineFallback from "@/components/feedback/OfflineFallback"

import { type Lesson, minutesDiff } from "./scheduleUtils"
import { LessonCard } from "./LessonCard"

interface DayColumnProps {
  day: string
  label: string
  lessons: Lesson[]
  isToday: boolean
  isOnline: boolean
  hasSchedule: boolean
  userRole?: string
  conflictedIds: Set<string>
  compact?: boolean
  currentLessonId?: string
  onAdd: () => void
  onLessonOpen: (lesson: Lesson) => void
  onLessonDelete: (id: string) => void
  onRetry: () => void
  getLessonTypeColor: (val?: string | null) => string
  getLessonTypeLabel: (val?: string | null) => string
}

export const DayColumn = forwardRef<HTMLDivElement, DayColumnProps>(
  (
    {
      day,
      label,
      lessons,
      isToday,
      isOnline,
      hasSchedule,
      userRole,
      conflictedIds,
      compact = false,
      currentLessonId,
      onAdd,
      onLessonOpen,
      onLessonDelete,
      onRetry,
      getLessonTypeColor,
      getLessonTypeLabel,
    },
    ref,
  ) => {
    const { t } = useTranslation(["schedule", "common"])

    // Heatmap: color intensity based on lesson count
    const heatClass =
      lessons.length >= 5
        ? "sched-heat-heavy"
        : lessons.length >= 3
          ? "sched-heat-medium"
          : lessons.length >= 1
            ? "sched-heat-light"
            : ""

    return (
      <div
        ref={ref}
        className={cn(
          "group relative isolate mb-2 rounded-2xl border border-glass-border shadow-premium backdrop-blur-md glass-noise transition-all duration-base",
          "[content-visibility:auto] [contain-intrinsic-size:auto_12rem]",
          compact ? "p-3 sm:p-4" : "p-4 sm:p-6",
          isToday
            ? "sched-today-col ring-2 ring-brand/(--opacity-dim)"
            : "bg-(--bg-surface)/(--opacity-hover) dark:bg-(--bg-surface)/(--opacity-heavy) shadow-md dark:shadow-xl",
          !isToday && heatClass
        )}
      >
        {/* ── Day header ──────────────────────────────────── */}
        <div className="mb-4 flex items-center gap-2">
          <h3
            className={cn(
              "text-lg font-extrabold tracking-tight text-text-primary transition-colors duration-fast",
              isToday && "text-brand"
            )}
          >
            {label}
          </h3>
          {lessons.length > 0 && (
            <Badge size="xs" variant="outline" className="font-medium opacity-70">
              {lessons.length}
            </Badge>
          )}
          {(userRole === "admin" || userRole === "teacher") && (
            <button
              id={`add-lesson-${day}`}
              className="ml-auto flex h-7 w-7 items-center justify-center rounded-lg border border-brand/(--opacity-dim) bg-brand/(--opacity-subtle) text-brand transition-all duration-fast hover:border-brand hover:bg-brand hover:text-white hover:shadow-sm hover:scale-110 focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-1"
              onClick={(e) => {
                e.stopPropagation()
                onAdd()
              }}
              aria-label={t("schedule:aria.addLesson", { day: label })}
            >
              <AddIcon size={14} aria-hidden="true" />
            </button>
          )}
        </div>

        {/* ── Lessons list or empty state ──────────────── */}
        {lessons.length === 0 ? (
          <div className="flex justify-center py-6">
            {!isOnline && !hasSchedule ? (
              <OfflineFallback onRetry={onRetry} />
            ) : (
              <EmptyState
                icon={
                  <div className="sched-empty-icon relative">
                    <EmptyDayIcon size={24} />
                    <div className="sched-empty-ring" />
                  </div>
                }
                title={t("schedule:mobile.noLessons")}
                className="max-w-[16rem] border-none bg-transparent py-6 shadow-none backdrop-blur-none"
              />
            )}
          </div>
        ) : (
          <div className="flex flex-col gap-3">
            {lessons.map((lesson, idx) => {
              const prev = lessons[idx - 1]
              const gap = prev ? minutesDiff(prev.end_time, lesson.start_time) : 0
              const isConflict = conflictedIds.has(lesson.id)
              const isCurrent = lesson.id === currentLessonId

              return (
                <div key={lesson.id}>
                  {/* ── Break timeline connector ────────────── */}
                  {idx > 0 && gap > 0 && (
                    <div className="mb-2 flex items-center gap-2 px-2">
                      <div className="sched-timeline-dot" />
                      <div className="sched-timeline-line h-px flex-1" />
                      <Badge
                        size="xs"
                        className="chip-break font-medium bg-warning-bg/(--opacity-dim) border border-warning-border/(--opacity-soft) text-warning-text"
                      >
                        {t("schedule:break", { minutes: gap })}
                      </Badge>
                      <div className="sched-timeline-line h-px flex-1" />
                      <div className="sched-timeline-dot" />
                    </div>
                  )}
                  <LessonCard
                    lesson={lesson}
                    isConflict={isConflict}
                    isCurrent={isCurrent}
                    index={idx}
                    compact={compact}
                    onOpen={() => onLessonOpen(lesson)}
                    onDelete={() => onLessonDelete(lesson.id)}
                    canEdit={userRole === "admin" || userRole === "teacher"}
                    getLessonTypeColor={getLessonTypeColor}
                    getLessonTypeLabel={getLessonTypeLabel}
                  />
                </div>
              )
            })}
          </div>
        )}
      </div>
    )
  },
)

DayColumn.displayName = "DayColumn"
