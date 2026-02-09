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
          "group relative isolate mb-2 rounded-2xl border border-(--glass-border) p-4 sm:p-6 shadow-premium [content-visibility:auto] [contain-intrinsic-size:400px] transition-all duration-300",
          isToday
            ? "bg-(--nav-link)/5 ring-2 ring-(--nav-link)/20 dark:bg-(--nav-link)/10 dark:ring-(--nav-link)/30"
            : "bg-(--card-bg)/80 dark:bg-(--card-bg)/90 shadow-md dark:shadow-xl",
          "backdrop-blur-md"
        )}
      >
        <div className="mb-4 flex items-center gap-2">
          <h3
            className={cn(
              "text-lg font-extrabold tracking-tight text-(--page-text) transition-colors duration-200",
              isToday &&
                "text-(--nav-link) dark:text-[color-mix(in_srgb,var(--nav-link)_95%,white_5%)]"
            )}
          >
            {label}
          </h3>
          {(userRole === "admin" || userRole === "teacher") && (
            <button
              className="ml-auto flex h-7 w-7 items-center justify-center rounded-lg border border-[color-mix(in_srgb,white_14%,var(--nav-link)_86%)] bg-[color-mix(in_srgb,var(--card-bg)_92%,var(--nav-link)_8%)] text-(--nav-link) transition-all duration-200 hover:border-(--nav-link) hover:bg-(--nav-link) hover:text-white hover:shadow-[0_4px_12px_color-mix(in_srgb,var(--nav-link)_25%,transparent)] hover:scale-110 dark:border-[color-mix(in_srgb,white_10%,var(--nav-link)_90%)] dark:bg-[color-mix(in_srgb,var(--card-bg)_88%,var(--nav-link)_12%)] dark:hover:shadow-[0_6px_16px_color-mix(in_srgb,var(--nav-link)_32%,transparent)]"
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
              <p className="text-[color-mix(in_srgb,var(--secondary-text)_65%,transparent)] text-sm font-medium dark:text-[color-mix(in_srgb,var(--secondary-text)_75%,transparent)]">
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
