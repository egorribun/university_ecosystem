import React, { forwardRef } from "react"
import { useTranslation } from "react-i18next"
import AddIcon from "@mui/icons-material/Add"
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
  conflictedIds: Set<number>
  onAdd: () => void
  onLessonOpen: (lesson: Lesson) => void
  onLessonDelete: (id: number) => void
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
          "group relative isolate mb-2 rounded-2xl border border-[color:color-mix(in_srgb,white_10%,var(--nav-link)_90%)] p-4 sm:p-6 shadow-[0_8px_24px_rgba(0,0,0,0.08),0_2px_8px_rgba(0,0,0,0.04)] [content-visibility:auto] [contain-intrinsic-size:400px] transition-all duration-300",
          isToday
            ? "bg-[color:color-mix(in_srgb,var(--nav-link)_5%,var(--card-bg)_95%)] ring-2 ring-[color:color-mix(in_srgb,var(--nav-link)_22%,transparent)] dark:bg-[color:color-mix(in_srgb,var(--nav-link)_7%,var(--card-bg)_93%)] dark:ring-[color:color-mix(in_srgb,var(--nav-link)_24%,transparent)]"
            : "bg-[color:color-mix(in_srgb,var(--card-bg)_96%,white_4%)] dark:bg-[color:color-mix(in_srgb,var(--card-bg)_94%,transparent_6%)] dark:shadow-[0_16px_48px_rgba(0,0,0,0.16),0_6px_20px_rgba(0,0,0,0.08)]",
          "backdrop-blur-sm [-webkit-backdrop-filter:blur(12px)]"
        )}
      >
        <div className="mb-4 flex items-center gap-2">
          <h3
            className={cn(
              "text-lg font-extrabold tracking-tight text-[color:var(--page-text)] transition-colors duration-200",
              isToday &&
                "text-[color:var(--nav-link)] dark:text-[color:color-mix(in_srgb,var(--nav-link)_95%,white_5%)]"
            )}
          >
            {label}
          </h3>
          {(userRole === "admin" || userRole === "teacher") && (
            <button
              className="ml-auto flex h-7 w-7 items-center justify-center rounded-lg border border-[color:color-mix(in_srgb,white_14%,var(--nav-link)_86%)] bg-[color:color-mix(in_srgb,var(--card-bg)_92%,var(--nav-link)_8%)] text-[color:var(--nav-link)] transition-all duration-200 hover:border-[color:var(--nav-link)] hover:bg-[color:var(--nav-link)] hover:text-white hover:shadow-[0_4px_12px_color-mix(in_srgb,var(--nav-link)_25%,transparent)] hover:scale-110 dark:border-[color:color-mix(in_srgb,white_10%,var(--nav-link)_90%)] dark:bg-[color:color-mix(in_srgb,var(--card-bg)_88%,var(--nav-link)_12%)] dark:hover:shadow-[0_6px_16px_color-mix(in_srgb,var(--nav-link)_32%,transparent)]"
              onClick={(e) => {
                e.stopPropagation()
                onAdd()
              }}
              aria-label={t("schedule:aria.addLesson", { day: label })}
            >
              <AddIcon className="text-[14px]" />
            </button>
          )}
        </div>
        {lessons.length === 0 ? (
          <div className="py-8">
            {!isOnline && !hasSchedule ? (
              <OfflineFallback onRetry={onRetry} />
            ) : (
              <p className="text-[color:color-mix(in_srgb,var(--secondary-text)_65%,transparent)] text-sm font-medium dark:text-[color:color-mix(in_srgb,var(--secondary-text)_75%,transparent)]">
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
                      className="chip-break mb-2 font-medium bg-[color:color-mix(in_srgb,var(--card-bg)_92%,yellow_8%)] border-[color:color-mix(in_srgb,var(--nav-link)_22%,transparent)] text-[color:color-mix(in_srgb,var(--page-text)_88%,yellow_12%)] shadow-[0_4px_12px_rgba(0,0,0,0.1)] dark:bg-[color:color-mix(in_srgb,var(--card-bg)_88%,yellow_12%)] dark:border-[color:color-mix(in_srgb,var(--nav-link)_28%,transparent)] dark:text-[color:color-mix(in_srgb,var(--page-text)_92%,yellow_8%)] dark:shadow-[0_6px_16px_rgba(0,0,0,0.24)]"
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
