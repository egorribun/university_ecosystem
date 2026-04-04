import {
  Trash2 as DeleteIcon,
  Clock as AccessTimeIcon,
  MapPin as RoomIcon,
  User as TeacherIcon,
  AlertTriangle as ConflictIcon,
} from "lucide-react"
import { useTranslation } from "react-i18next"
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
      aria-current={isCurrent ? "time" : undefined}
      className={cn(
        "sched-card-matte sched-card-item sched-lesson-card group relative flex h-full min-w-0 cursor-pointer flex-col overflow-hidden glass-noise",
        accentClass,
        compact ? "gap-1 p-2.5" : "gap-1.5 p-3",
        hasBreakBefore && "mt-5",
        isCurrent && "sched-current-glow",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-2 focus-visible:ring-offset-page"
      )}
      style={{ "--sched-stagger-i": index } as React.CSSProperties}
      title={isConflict ? t("schedule:lesson.conflict") : undefined}
    >
      {/* ── Type badge ─────────────────────────────────── */}
      <div className="flex min-w-0 items-center gap-1.5">
        <span
          className="sched-type-badge shrink-0"
          style={{ background: getLessonTypeColor(lesson.lesson_type) }}
        >
          {getLessonTypeLabel(lesson.lesson_type)}
        </span>
        <span className="sched-time-badge ml-auto shrink-0">
          <AccessTimeIcon size={10} aria-hidden="true" className="opacity-50" />
          {`${getTimeStr(lesson)}–${getEndTimeStr(lesson)}`}
        </span>
      </div>

      {/* ── Subject ─────────────────────────────────────── */}
      <h3
        className={cn(
          "sched-card-title min-w-0 font-bold text-text-primary leading-snug tracking-tight",
          compact ? "text-xs line-clamp-1" : "text-sm line-clamp-2"
        )}
      >
        {lesson.subject}
      </h3>

      {/* ── Details row (hidden in compact mode) ────────── */}
      {!compact && (
        <div className="mt-auto flex min-w-0 flex-wrap items-center gap-x-2 gap-y-0.5 text-[0.6875rem] text-text-secondary">
          {lesson.teacher && (
            <span className="inline-flex min-w-0 items-center gap-1">
              <TeacherIcon size={10} className="shrink-0 text-brand opacity-60" aria-hidden="true" />
              <span className="truncate">{lesson.teacher}</span>
            </span>
          )}
          {lesson.room && (
            <span className="sched-grid-room inline-flex items-center gap-1">
              <RoomIcon size={10} className="shrink-0 text-brand opacity-60" aria-hidden="true" />
              <span>{lesson.room}</span>
            </span>
          )}
        </div>
      )}

      {/* ── Conflict indicator ──────────────────────────── */}
      {isConflict && (
        <div className="flex items-center gap-1 text-[0.625rem] font-semibold text-error">
          <ConflictIcon size={10} aria-hidden="true" />
          <span>{t("schedule:lesson.conflict")}</span>
        </div>
      )}

      {/* ── Delete button (hover reveal) ────────────────── */}
      {canEdit && (
        <button
          id={`delete-lesson-${lesson.id}`}
          aria-label={t("schedule:aria.deleteLesson")}
          onClick={(e) => {
            e.stopPropagation()
            onDelete()
          }}
          className="absolute right-1.5 top-1.5 flex h-5 w-5 items-center justify-center rounded bg-surface/(--opacity-strong) text-text-secondary opacity-0 shadow-sm transition-all duration-fast hover:bg-error hover:text-white group-hover:opacity-100 focus-visible:opacity-100 focus-visible:ring-2 focus-visible:ring-brand"
        >
          <DeleteIcon size={11} aria-hidden="true" />
        </button>
      )}
    </div>
  )
}

export default LessonCard
