import { forwardRef } from "react"
import { useTranslation } from "react-i18next"
import { Plus as AddIcon } from "lucide-react"
import { cn } from "@/utils/cn"
import { Badge } from "@/components/ui"
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
      onAdd,
      onLessonOpen,
      onLessonDelete,
      onRetry,
      getLessonTypeColor,
      getLessonTypeLabel,
    },
    ref
  ) => {
    const { t } = useTranslation(["schedule", "common"])

    return (
      <div
        ref={ref}
        className={cn(
          "group relative isolate mb-2 rounded-2xl border border-glass-border p-4 sm:p-6 shadow-premium [content-visibility:auto] [contain-intrinsic-size:var(--h-news-card-mobile)] transition-all duration-base",
          isToday
            ? "bg-primary-main/(--opacity-faint) ring-2 ring-primary-main/(--opacity-dim) dark:bg-primary-main/(--opacity-subtle) dark:ring-primary-main/(--opacity-soft)"
            : "bg-(--bg-surface)/(--opacity-hover) dark:bg-(--bg-surface)/(--opacity-heavy) shadow-md dark:shadow-xl",
          "backdrop-blur-md"
        )}
      >
        <div className="mb-4 flex items-center gap-2">
          <h3
            className={cn(
              "text-lg font-extrabold tracking-tight text-text-primary transition-colors duration-fast",
              isToday && "text-primary-main dark:text-primary-light"
            )}
          >
            {label}
          </h3>
          {(userRole === "admin" || userRole === "teacher") && (
            <button
              id={`add-lesson-${day}`}
              className="ml-auto flex h-7 w-7 items-center justify-center rounded-lg border border-brand/(--opacity-dim) bg-brand/(--opacity-subtle) text-brand transition-all duration-fast hover:border-brand hover:bg-brand hover:text-white hover:shadow-glass hover:scale-110"
              onClick={(e) => {
                e.stopPropagation()
                onAdd()
              }}
              aria-label={t("schedule:aria.addLesson", { day: label })}
            >
              <AddIcon size={14} />
            </button>
          )}
        </div>
        {lessons.length === 0 ? (
          <div className="py-8">
            {!isOnline && !hasSchedule ? (
              <OfflineFallback onRetry={onRetry} />
            ) : (
              <p className="text-(--text-caption) text-sm font-medium">
                {t("schedule:mobile.noLessons")}
              </p>
            )}
          </div>
        ) : (
          <div className="flex flex-col gap-3">
            {lessons.map((lesson, idx) => {
              const prev = lessons[idx - 1]
              const gap = prev ? minutesDiff(prev.end_time, lesson.start_time) : 0
              const isConflict = conflictedIds.has(lesson.id)
              return (
                <div key={lesson.id}>
                  {idx > 0 && gap > 0 && (
                    <Badge
                      size="xs"
                      className="chip-break mb-2 font-medium bg-warning-bg/(--opacity-dim) border border-warning-border/(--opacity-soft) text-warning-text"
                    >
                      {t("schedule:break", { minutes: gap })}
                    </Badge>
                  )}
                  <LessonCard
                    lesson={lesson}
                    isConflict={isConflict}
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
  }
)

DayColumn.displayName = "DayColumn"
