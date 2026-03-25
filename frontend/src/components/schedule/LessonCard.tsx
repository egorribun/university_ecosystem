import {
  Trash2 as DeleteIcon,
  Info as InfoOutlinedIcon,
  Clock as AccessTimeIcon,
  MapPin as RoomIcon,
  User as TeacherIcon,
} from "lucide-react"
import { useTranslation } from "react-i18next"
import { Badge, Tooltip, GlassCard } from "@/components/ui"
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

// PERF-27-02: Removed React.memo() — React Compiler "infer" mode handles memoization
export function LessonCard({
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
    <GlassCard
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
      intensity="elevated"
      radius="2xl"
      className={cn(
        "group flex h-full min-h-32 flex-col p-3 transition-all duration-base sm:min-h-(--h-card-lesson-min)",
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
            className="chip-type h-6 px-2.5 font-semibold text-white shadow-sm"
            style={{
              background: getLessonTypeColor(lesson.lesson_type),
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
        <h3 className="text-base font-extrabold text-text-primary line-clamp-2 leading-tight tracking-tight">
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
    </GlassCard>
  )
}

export default LessonCard
