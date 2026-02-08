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
        "group relative cursor-pointer rounded-xl border border-[color-mix(in_srgb,white_10%,var(--nav-link)_90%)] bg-[color-mix(in_srgb,var(--card-bg)_96%,white_4%)] shadow-[0_4px_16px_rgba(0,0,0,0.08),0_2px_6px_rgba(0,0,0,0.04)] transition-all duration-300",
        hasBreakBefore ? "mt-6" : "",
        "hover:-translate-y-1 hover:shadow-[0_12px_32px_rgba(0,0,0,0.12),0_4px_12px_rgba(0,0,0,0.08)] hover:border-[color-mix(in_srgb,white_16%,var(--nav-link)_84%)]",
        "dark:border-[color-mix(in_srgb,white_8%,var(--nav-link)_92%)] dark:bg-[color-mix(in_srgb,var(--card-bg)_94%,transparent_6%)] dark:shadow-[0_6px_20px_rgba(0,0,0,0.16),0_2px_8px_rgba(0,0,0,0.08)]",
        "dark:hover:shadow-[0_16px_40px_rgba(0,0,0,0.24),0_6px_16px_rgba(0,0,0,0.12)] dark:hover:border-[color-mix(in_srgb,white_12%,var(--nav-link)_88%)]",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-(--nav-link) focus-visible:ring-offset-2 focus-visible:ring-offset-(--card-bg)"
      )}
      style={{ minHeight: lessonCardHeight, padding: "12px" }}
      title={isConflict ? t("schedule:lesson.conflict") : undefined}
    >
      <div className="flex flex-col gap-2">
        <div className="flex items-center justify-between gap-2">
          <Badge
            size="xs"
            className="chip-type font-semibold shadow-[0_2px_6px_rgba(0,0,0,0.12)] dark:shadow-[0_4px_10px_rgba(0,0,0,0.24)]"
            style={{
              background: getLessonTypeColor(lesson.lesson_type),
              color: "#fff",
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
            className="chip-time font-medium border-[color-mix(in_srgb,white_14%,var(--nav-link)_86%)] bg-[color-mix(in_srgb,var(--card-bg)_92%,white_8%)] text-[color-mix(in_srgb,var(--page-text)_88%,var(--nav-link)_12%)] dark:border-[color-mix(in_srgb,white_10%,var(--nav-link)_90%)] dark:bg-[color-mix(in_srgb,var(--card-bg)_90%,transparent_10%)] dark:text-[color-mix(in_srgb,var(--page-text)_92%,var(--nav-link)_8%)]"
            leadingIcon={<AccessTimeIcon size={15} />}
          >
            {`${getTimeStr(lesson)}–${getEndTimeStr(lesson)}`}
          </Badge>
        </div>
        <h3
          className="text-base font-extrabold text-(--page-text) line-clamp-2 leading-tight tracking-tight"
          style={{ fontSize: "1rem" }}
        >
          {lesson.subject}
        </h3>
        <div className="flex flex-wrap gap-2">
          <Badge
            size="xs"
            variant="outline"
            leadingIcon={<SchoolIcon size={15} className="text-(--nav-link)" />}
            className="font-medium text-[color-mix(in_srgb,var(--page-text)_88%,var(--nav-link)_12%)] border-[color-mix(in_srgb,white_12%,var(--nav-link)_88%)] bg-[color-mix(in_srgb,var(--card-bg)_94%,white_6%)] dark:text-[color-mix(in_srgb,var(--page-text)_90%,var(--nav-link)_10%)] dark:border-[color-mix(in_srgb,white_8%,var(--nav-link)_92%)] dark:bg-[color-mix(in_srgb,var(--card-bg)_92%,transparent_8%)]"
          >
            {lesson.teacher}
          </Badge>
          <Badge
            size="xs"
            variant="outline"
            leadingIcon={<RoomIcon size={15} className="text-(--nav-link)" />}
            className="font-medium text-[color-mix(in_srgb,var(--page-text)_88%,var(--nav-link)_12%)] border-[color-mix(in_srgb,white_12%,var(--nav-link)_88%)] bg-[color-mix(in_srgb,var(--card-bg)_94%,white_6%)] dark:text-[color-mix(in_srgb,var(--page-text)_90%,var(--nav-link)_10%)] dark:border-[color-mix(in_srgb,white_8%,var(--nav-link)_92%)] dark:bg-[color-mix(in_srgb,var(--card-bg)_92%,transparent_8%)]"
          >
            {lesson.room}
          </Badge>
        </div>
      </div>
      <Tooltip content={t("schedule:lesson.details")}>
        <InfoOutlinedIcon size={18} className="absolute bottom-3 right-3 text-[color-mix(in_srgb,var(--secondary-text)_60%,transparent)] opacity-0 transition-opacity duration-200 group-hover:opacity-100 dark:text-[color-mix(in_srgb,var(--secondary-text)_70%,transparent)]" />
      </Tooltip>
      {canEdit && (
        <button
          aria-label={t("schedule:aria.deleteLesson")}
          onClick={(e) => {
            e.stopPropagation()
            onDelete()
          }}
          className={cn(
            "absolute top-2 right-2 z-10 flex h-7 w-7 items-center justify-center rounded-lg opacity-0 transition-all duration-200",
            "bg-[color-mix(in_srgb,var(--card-bg)_90%,#D14343_10%)] text-[#D14343]",
            "border border-[color-mix(in_srgb,#D14343_30%,transparent)]",
            "shadow-[0_2px_8px_rgba(209,67,67,0.16)]",
            "hover:bg-[color-mix(in_srgb,var(--card-bg)_80%,#D14343_20%)] hover:shadow-[0_4px_12px_rgba(209,67,67,0.24)]",
            "group-hover:opacity-100",
            "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#D14343]/40"
          )}
        >
          <DeleteIcon size={16} />
        </button>
      )}
    </div>
  )
}

export default LessonCard
