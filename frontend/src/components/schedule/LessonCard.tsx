/**
 * LessonCard Component
 *
 * A card component for displaying a lesson in the schedule.
 * Used in both desktop table and mobile card views.
 */
import React from "react"
import {
  Trash2 as DeleteIcon,
  Info as InfoOutlinedIcon,
  Clock as AccessTimeIcon,
  GraduationCap as SchoolIcon,
  MapPin as RoomIcon,
} from "lucide-react"
import { useTranslation } from "react-i18next"
import { Badge, Tooltip } from "@/components/ui"
import { cn } from "@/utils/cn"
import { type Lesson, getTimeStr, getEndTimeStr } from "./scheduleUtils"

export interface LessonCardProps {
  lesson: Lesson
  isConflict: boolean
  onDelete: () => void
  onOpen: () => void
  hasBreakBefore?: boolean
  lessonCardHeight?: number
  getLessonTypeColor: (value?: string | null) => string
  getLessonTypeLabel: (value?: string | null) => string
  canEdit?: boolean
}

export function LessonCard({
  lesson,
  isConflict,
  onDelete,
  onOpen,
  hasBreakBefore = false,
  lessonCardHeight = 148,
  getLessonTypeColor,
  getLessonTypeLabel,
  canEdit = false,
}: LessonCardProps) {
  const { t } = useTranslation(["schedule"])

  return (
    <div
      onClick={onOpen}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault()
          onOpen()
        }
      }}
      role="button"
      tabIndex={0}
      className={cn(
        "group relative flex h-full min-h-32 flex-col overflow-hidden rounded-2xl border border-glass-border-subtle bg-glass-elevated p-3 shadow-premium transition-all duration-300 sm:min-h-[130px]",
        hasBreakBefore ? "mt-6" : "",
        "hover:-translate-y-1 hover:shadow-glass hover:border-brand-subtle",
        "dark:shadow-premium-dark dark:hover:shadow-glass-strong-dark",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-2 focus-visible:ring-offset-page"
      )}
      title={isConflict ? t("schedule:lesson.conflict") : undefined}
    >
      <div className="flex flex-col gap-2">
        <div className="flex items-center justify-between gap-2">
          <Badge
            size="xs"
            className="chip-type font-semibold shadow-sm"
            style={{
              background: getLessonTypeColor(lesson.lesson_type),
              color: "white",
              height: "24px",
              paddingLeft: "10px",
              paddingRight: "10px",
            }}
          >
            {getLessonTypeLabel(lesson.lesson_type)}
          </Badge>
          <Badge
            size="xs"
            variant="outline"
            className="chip-time font-medium border-brand/20 bg-brand-subtle-bg text-brand dark:border-brand/30 dark:bg-brand-subtle-bg/80"
            leadingIcon={<AccessTimeIcon size={15} />}
          >
            {`${getTimeStr(lesson)}–${getEndTimeStr(lesson)}`}
          </Badge>
        </div>
        <h3 className="text-base font-extrabold text-(--text-primary) line-clamp-2 leading-tight tracking-tight">
          {lesson.subject}
        </h3>
        <div className="flex flex-wrap gap-2">
          <Badge
            size="xs"
            variant="outline"
            className="font-medium text-(--text-primary)/80 border-(--glass-border) bg-(--bg-surface)/40 dark:text-(--text-primary)/90 dark:bg-(--bg-surface)/60"
          >
            {lesson.teacher}
          </Badge>
          <Badge
            size="xs"
            variant="outline"
            leadingIcon={<RoomIcon size={15} className="text-(--primary-main)" />}
            className="font-medium text-(--text-primary)/80 border-(--glass-border) bg-(--bg-surface)/40 dark:text-(--text-primary)/90 dark:bg-(--bg-surface)/60"
          >
            {lesson.room}
          </Badge>
        </div>
      </div>
      <Tooltip content={t("schedule:lesson.details")}>
        <InfoOutlinedIcon
          size={18}
          className="absolute bottom-3 right-3 text-text-muted-subtle opacity-0 transition-opacity duration-200 group-hover:opacity-100"
        />
      </Tooltip>
      {canEdit && (
        <button
          aria-label={t("schedule:aria.deleteLesson")}
          onClick={(e) => {
            e.stopPropagation()
            onDelete()
          }}
          className={cn(
            "absolute top-2 right-2 z-(--z-surface) flex h-7 w-7 items-center justify-center rounded-lg opacity-0 transition-premium",
            "bg-(--error-bg) text-(--error-text)",
            "border border-(--error-text)/30",
            "shadow-sm",
            "hover:bg-(--error-text)/20 hover:shadow-md",
            "group-hover:opacity-100",
            "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-(--error-text)/40"
          )}
        >
          <DeleteIcon size={16} />
        </button>
      )}
    </div>
  )
}

export default LessonCard




