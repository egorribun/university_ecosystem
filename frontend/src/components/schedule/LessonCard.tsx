import { memo } from "react"
import {
  Trash2 as DeleteIcon,
  Info as InfoOutlinedIcon,
  Clock as AccessTimeIcon,
  MapPin as RoomIcon,
  User as TeacherIcon,
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

export const LessonCard = memo(function LessonCard({
  lesson,
  isConflict,
  onDelete,
  onOpen,
  hasBreakBefore = false,
  getLessonTypeColor,
  getLessonTypeLabel,
  canEdit = false,
}: LessonCardProps) {
  const { t } = useTranslation(["schedule"])

  return (
    <div
      id={`lesson-card-${lesson.id}`}
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
        "group relative flex h-full min-h-32 flex-col overflow-hidden rounded-2xl border border-glass-border-subtle bg-glass-elevated p-3 shadow-premium transition-all duration-base sm:min-h-(--h-card-lesson-min)",
        hasBreakBefore ? "mt-6" : "",
        "hover:-translate-y-1 hover:shadow-glass hover:border-brand-subtle",
        "dark:shadow-premium dark:hover:shadow-glass-strong",
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
            className="chip-time"
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
            leadingIcon={<TeacherIcon size={14} className="text-(--primary-main)" />}
            className="badge-glass"
          >
            {lesson.teacher || "—"}
          </Badge>
          <Badge
            size="xs"
            variant="outline"
            leadingIcon={<RoomIcon size={15} className="text-(--primary-main)" />}
            className="badge-glass"
          >
            {lesson.room || "—"}
          </Badge>
        </div>
      </div>
      <Tooltip content={t("schedule:lesson.details")}>
        <InfoOutlinedIcon
          size={18}
          className="absolute bottom-3 right-3 text-text-muted-subtle opacity-0 transition-opacity duration-fast group-hover:opacity-100"
        />
      </Tooltip>
      {canEdit && (
        <button
          id={`delete-lesson-${lesson.id}`}
          aria-label={t("schedule:aria.deleteLesson")}
          onClick={(e) => {
            e.stopPropagation()
            onDelete()
          }}
          className={cn("button-icon-glass")}
        >
          <DeleteIcon size={16} />
        </button>
      )}
    </div>
  )
})

export default LessonCard
