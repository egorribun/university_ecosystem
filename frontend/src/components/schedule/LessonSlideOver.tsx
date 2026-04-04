import { useEffect, useRef, useState, useCallback } from "react"
import { useTranslation } from "react-i18next"
import {
  X as CloseIcon,
  Clock as ClockIcon,
  MapPin as RoomIcon,
  User as TeacherIcon,
  Pencil as EditIcon,
  Trash2 as DeleteIcon,
  BookOpen as SubjectIcon,
} from "lucide-react"
import { Badge, Button } from "@/components/ui"
import { type Lesson, getTimeStr, getEndTimeStr } from "./scheduleUtils"

interface LessonSlideOverProps {
  lesson: Lesson | null
  open: boolean
  onClose: () => void
  onEdit?: () => void
  onDelete?: () => void
  canEdit?: boolean
  getLessonTypeColor: (type?: string | null) => string
  getLessonTypeLabel: (type?: string | null) => string
}

export function LessonSlideOver({
  lesson,
  open,
  onClose,
  onEdit,
  onDelete,
  canEdit = false,
  getLessonTypeColor,
  getLessonTypeLabel,
}: LessonSlideOverProps) {
  const { t } = useTranslation(["schedule", "common"])
  const panelRef = useRef<HTMLDivElement>(null)
  const closeRef = useRef<HTMLButtonElement>(null)
  const [isClosing, setIsClosing] = useState(false)

  const handleClose = useCallback(() => {
    setIsClosing(true)
    setTimeout(() => {
      setIsClosing(false)
      onClose()
    }, 250)
  }, [onClose])

  // Focus trap + Escape
  useEffect(() => {
    if (!open) return
    closeRef.current?.focus()

    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault()
        handleClose()
      }
    }
    document.addEventListener("keydown", handler)
    return () => document.removeEventListener("keydown", handler)
  }, [open, handleClose])

  if (!open || !lesson) return null

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 z-overlay bg-black/30 backdrop-blur-sm"
        onClick={handleClose}
        aria-hidden="true"
      />

      {/* Panel */}
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="slideover-title"
        data-closing={isClosing || undefined}
        className="sched-slideover flex flex-col border-l border-glass-border bg-surface/(--opacity-heavy) shadow-glass-strong backdrop-blur-xl glass-noise"
      >
        {/* ── Header ──────────────────────────────────── */}
        <div className="flex items-center justify-between border-b border-glass-border px-6 py-4">
          <h2
            id="slideover-title"
            className="text-lg font-bold text-text-primary tracking-tight"
          >
            {t("schedule:lesson.details")}
          </h2>
          <button
            ref={closeRef}
            onClick={handleClose}
            aria-label={t("common:buttons.close", { defaultValue: "Close" })}
            className="flex h-8 w-8 items-center justify-center rounded-lg text-text-secondary transition-colors hover:bg-surface-elevated/(--opacity-dim) hover:text-text-primary focus-visible:ring-2 focus-visible:ring-brand"
          >
            <CloseIcon size={16} aria-hidden="true" />
          </button>
        </div>

        {/* ── Content ─────────────────────────────────── */}
        <div className="flex-1 overflow-y-auto px-6 py-6 space-y-6">
          {/* Subject */}
          <div>
            <div className="mb-2 flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-text-secondary">
              <SubjectIcon size={14} aria-hidden="true" />
              {t("schedule:form.subject")}
            </div>
            <h3 className="text-xl font-extrabold text-text-primary tracking-tight">
              {lesson.subject || "—"}
            </h3>
          </div>

          {/* Type badge */}
          <div>
            <div className="mb-2 text-xs font-bold uppercase tracking-wider text-text-secondary">
              {t("schedule:dialog.typeLabel")}
            </div>
            <Badge
              className="text-white font-semibold shadow-sm"
              style={{ background: getLessonTypeColor(lesson.lesson_type) }}
            >
              {getLessonTypeLabel(lesson.lesson_type)}
            </Badge>
          </div>

          {/* Time */}
          <div className="rounded-xl border border-glass-border/(--opacity-soft) bg-surface/(--opacity-dim) p-4">
            <div className="flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-full bg-brand/(--opacity-subtle) text-brand">
                <ClockIcon size={18} aria-hidden="true" />
              </div>
              <div>
                <div className="text-xs font-medium text-text-secondary">
                  {t("schedule:dialog.timeLabel")}
                </div>
                <div className="text-base font-bold text-text-primary">
                  {`${getTimeStr(lesson)} – ${getEndTimeStr(lesson)}`}
                </div>
              </div>
            </div>
          </div>

          {/* Teacher */}
          {lesson.teacher && (
            <div className="rounded-xl border border-glass-border/(--opacity-soft) bg-surface/(--opacity-dim) p-4">
              <div className="flex items-center gap-3">
                <div className="flex h-10 w-10 items-center justify-center rounded-full bg-brand/(--opacity-subtle) text-brand">
                  <TeacherIcon size={18} aria-hidden="true" />
                </div>
                <div>
                  <div className="text-xs font-medium text-text-secondary">
                    {t("schedule:dialog.teacherLabel")}
                  </div>
                  <div className="text-base font-bold text-text-primary">
                    {lesson.teacher}
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Room */}
          {lesson.room && (
            <div className="rounded-xl border border-glass-border/(--opacity-soft) bg-surface/(--opacity-dim) p-4">
              <div className="flex items-center gap-3">
                <div className="flex h-10 w-10 items-center justify-center rounded-full bg-brand/(--opacity-subtle) text-brand">
                  <RoomIcon size={18} aria-hidden="true" />
                </div>
                <div>
                  <div className="text-xs font-medium text-text-secondary">
                    {t("schedule:dialog.roomLabel")}
                  </div>
                  <div className="text-base font-bold text-text-primary">
                    {lesson.room}
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>

        {/* ── Footer actions ──────────────────────────── */}
        {canEdit && (
          <div className="flex gap-3 border-t border-glass-border px-6 py-4">
            <Button
              variant="outline"
              size="sm"
              onClick={onEdit}
              className="flex-1 gap-1.5"
            >
              <EditIcon size={14} aria-hidden="true" />
              {t("schedule:buttons.edit")}
            </Button>
            <Button
              variant="ghost"
              size="sm"
              onClick={onDelete}
              className="text-error hover:bg-error/(--opacity-subtle)"
            >
              <DeleteIcon size={14} aria-hidden="true" />
            </Button>
          </div>
        )}
      </div>
    </>
  )
}
