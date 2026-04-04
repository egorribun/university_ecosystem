import {
  Trash2 as DeleteIcon,
  Info as InfoOutlinedIcon,
  Clock as AccessTimeIcon,
  MapPin as RoomIcon,
  User as TeacherIcon,
  AlertTriangle as ConflictIcon,
} from "lucide-react"
import { useTranslation } from "react-i18next"
import { Badge, Tooltip, GlassCard } from "@/components/ui"
import { cn } from "@/utils/cn"
import { type Lesson, getTimeStr, getEndTimeStr } from "./scheduleUtils"

/* ── Lesson-type → CSS accent class mapping ─────────── */
const ACCENT_MAP: Record<string, string> = {
  lecture: "sched-accent-lecture",
  practice: "sched-accent-practice",
  lab: "sched-accent-lab",
  project: "sched-accent-project",
}

function getAccentClass(lessonType?: string | null): string {
  if (!lessonType) return "sched-accent-default"
  const key = lessonType.toLowerCase()
  for (const [k, cls] of Object.entries(ACCENT_MAP)) {
    if (key.includes(k)) return cls
  }
  return "sched-accent-default"
}

export interface LessonCardProps {
  lesson: Lesson
  isConflict: boolean
  isCurrent?: boolean
  index?: number
  compact?: boolean
  onDelete: () => void
  onOpen: () => void
  hasBreakBefore?: boolean
  getLessonTypeColor: (value?: string | null) => string
  getLessonTypeLabel: (value?: string | null) => string
  canEdit?: boolean
}

// PERF-27-02: Removed React.memo() — React Compiler "infer" mode handles memoization
export function LessonCard({
  lesson,
  isConflict,
  isCurrent = false,
  index = 0,
  compact = false,
  onDelete,
  onOpen,
  hasBreakBefore = false,
  getLessonTypeColor,
  getLessonTypeLabel,
  canEdit = false,
}: LessonCardProps) {
  const { t } = useTranslation(["schedule"])

  const accentClass = isConflict ? "sched-conflict" : getAccentClass(lesson.lesson_type)

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
      aria-current={isCurrent ? "time" : undefined}
      className={cn(
        "sched-card-item group relative flex h-full flex-col transition-all duration-base",
        "glass-noise dash-border-shimmer",
        accentClass,
        compact ? "min-h-16 gap-1 p-2" : "min-h-32 gap-2 p-3 sm:min-h-(--h-card-lesson-min)",
        hasBreakBefore && "mt-6",
        isCurrent && "sched-current-glow",
        "hover:-translate-y-1 hover:shadow-glass hover:border-brand-subtle",
        "dark:shadow-premium dark:hover:shadow-glass-strong",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-2 focus-visible:ring-offset-page"
      )}
      style={{ "--sched-stagger-i": index } as React.CSSProperties}
      title={isConflict ? t("schedule:lesson.conflict") : undefined}
    >
      {/* ── Top row: type badge + time ──────────────────── */}
      <div className="flex items-center justify-between gap-2">
        <Badge
          size="xs"
          className="chip-type h-6 px-2.5 font-semibold text-white shadow-sm"
          style={{ background: getLessonTypeColor(lesson.lesson_type) }}
        >
          {getLessonTypeLabel(lesson.lesson_type)}
        </Badge>
        <Badge
          size="xs"
          variant="outline"
          className="chip-time font-medium"
          leadingIcon={<AccessTimeIcon size={14} aria-hidden="true" />}
        >
          {`${getTimeStr(lesson)}–${getEndTimeStr(lesson)}`}
        </Badge>
      </div>

      {/* ── Subject ─────────────────────────────────────── */}
      <h3
        className={cn(
          "sched-card-title font-extrabold text-text-primary leading-tight tracking-tight",
          compact ? "text-sm line-clamp-1" : "text-base line-clamp-2"
        )}
      >
        {lesson.subject}
      </h3>

      {/* ── Details row (hidden in compact mode) ────────── */}
      {!compact && (
        <div className="flex flex-wrap gap-2">
          <Badge
            size="xs"
            variant="outline"
            leadingIcon={<TeacherIcon size={14} className="text-(--primary-main)" aria-hidden="true" />}
            className="badge-glass"
          >
            {lesson.teacher || "—"}
          </Badge>
          <Badge
            size="xs"
            variant="outline"
            leadingIcon={<RoomIcon size={14} className="text-(--primary-main) sched-grid-room" aria-hidden="true" />}
            className="badge-glass sched-grid-room"
          >
            {lesson.room || "—"}
          </Badge>
        </div>
      )}

      {/* ── Conflict indicator ──────────────────────────── */}
      {isConflict && (
        <div className="mt-auto flex items-center gap-1 text-xs font-semibold text-error">
          <ConflictIcon size={14} aria-hidden="true" />
          <span>{t("schedule:lesson.conflict")}</span>
        </div>
      )}

      {/* ── Info icon (hover reveal) ───────────────────── */}
      <Tooltip content={t("schedule:lesson.details")}>
        <InfoOutlinedIcon
          size={18}
          aria-hidden="true"
          className="absolute bottom-3 right-3 text-text-muted-subtle opacity-0 transition-opacity duration-fast group-hover:opacity-100"
        />
      </Tooltip>

      {/* ── Delete button (hover reveal) ────────────────── */}
      {canEdit && (
        <button
          id={`delete-lesson-${lesson.id}`}
          aria-label={t("schedule:aria.deleteLesson")}
          onClick={(e) => {
            e.stopPropagation()
            onDelete()
          }}
          className="button-icon-glass absolute right-3 top-3 opacity-0 transition-opacity duration-fast group-hover:opacity-100"
        >
          <DeleteIcon size={16} aria-hidden="true" />
        </button>
      )}
    </GlassCard>
  )
}

export default LessonCard
