import React, { forwardRef } from "react"
import { useTranslation } from "react-i18next"
import { Plus as AddIcon } from "lucide-react"
import { cn } from "@/utils/cn"
import { Badge } from "@/components/ui"
import OfflineFallback from "@/components/OfflineFallback"

import { type Lesson, minutesDiff, getTimeStr } from "./scheduleUtils"
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
          "group relative isolate mb-2 rounded-2xl border border-glass-border p-4 sm:p-6 shadow-premium [content-visibility:auto] [contain-intrinsic-size:400px] transition-all duration-300",
          isToday
            ? "bg-primary-main/5 ring-2 ring-primary-main/20 dark:bg-primary-main/10 dark:ring-primary-main/30"
            : "bg-(--bg-surface)/80 dark:bg-(--bg-surface)/90 shadow-md dark:shadow-xl",
          "backdrop-blur-md"
        )}
      >
        <div className="mb-4 flex items-center gap-2">
          <h3
            className={cn(
              "text-lg font-extrabold tracking-tight text-(--text-primary) transition-colors duration-200",
              isToday && "text-primary-main dark:text-primary-light"
            )}
          >
            {label}
          </h3>
          {(userRole === "admin" || userRole === "teacher") && (
            <button
              className="ml-auto flex h-7 w-7 items-center justify-center rounded-lg border border-primary-main/20 bg-primary-main/10 text-primary-main transition-all duration-200 hover:border-primary-main hover:bg-primary-main hover:text-white hover:shadow-[0_4px_12px_rgba(59,130,246,0.25)] hover:scale-110"
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
              <p className="text-[color-mix(in_srgb,var(--text-secondary)_65%,transparent)] text-sm font-medium dark:text-[color-mix(in_srgb,var(--text-secondary)_75%,transparent)]">
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
                      className="chip-break mb-2 font-medium bg-amber-500/10 border border-amber-500/20 text-amber-700 dark:text-amber-400 shadow-sm"
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





