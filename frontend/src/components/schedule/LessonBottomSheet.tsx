/**
 * LessonBottomSheet — Mobile-only lesson detail sheet.
 * Slides up from bottom, drag-to-dismiss, max 70vh.
 * Reuses LessonSlideOver content layout in bottom-sheet format.
 * Wave 68 (FIX-68-22).
 */
import { useState, useCallback, useEffect, useRef } from "react"
import useFocusTrap from "@/hooks/useFocusTrap"
import { useTranslation } from "react-i18next"
import {
  X as CloseIcon,
  Clock as ClockIcon,
  MapPin as RoomIcon,
  User as TeacherIcon,
  Pencil as EditIcon,
  Trash2 as DeleteIcon,
} from "lucide-react"
import { Badge, Button } from "@/components/ui"
import { type Lesson, getTimeStr, getEndTimeStr } from "./scheduleUtils"

interface LessonBottomSheetProps {
  lesson: Lesson | null
  open: boolean
  onClose: () => void
  onEdit?: () => void
  onDelete?: () => void
  canEdit?: boolean
  getLessonTypeColor: (type?: string | null) => string
  getLessonTypeLabel: (type?: string | null) => string
}

export function LessonBottomSheet({
  lesson,
  open,
  onClose,
  onEdit,
  onDelete,
  canEdit = false,
  getLessonTypeColor,
  getLessonTypeLabel,
}: LessonBottomSheetProps) {
  const { t } = useTranslation(["schedule", "common"])
  const [isClosing, setIsClosing] = useState(false)
  const [lastLesson, setLastLesson] = useState<Lesson | null>(null)
  const [dragY, setDragY] = useState(0)
  const dragStartRef = useRef<number | null>(null)
  const closeTimerRef = useRef<ReturnType<typeof setTimeout>>(undefined)

  useEffect(() => {
    if (lesson) setLastLesson(lesson)
  }, [lesson])

  // Cleanup exit-animation timer on unmount (FIX-69-01)
  useEffect(() => () => clearTimeout(closeTimerRef.current), [])

  const displayLesson = lesson ?? lastLesson

  const handleClose = useCallback(() => {
    setIsClosing(true)
    setDragY(0)
    closeTimerRef.current = setTimeout(() => {
      setIsClosing(false)
      onClose()
    }, 250)
  }, [onClose])

  const panelRef = useFocusTrap<HTMLDivElement>({
    active: open && !!displayLesson,
    onDeactivate: handleClose,
  })

  // Drag-to-dismiss
  const onPointerDown = useCallback((e: React.PointerEvent) => {
    // Only start drag from the handle area (top 40px)
    const rect = (e.currentTarget as HTMLElement).getBoundingClientRect()
    if (e.clientY - rect.top > 40) return
    dragStartRef.current = e.clientY
  }, [])

  const onPointerMove = useCallback((e: React.PointerEvent) => {
    if (dragStartRef.current === null) return
    const dy = Math.max(0, e.clientY - dragStartRef.current)
    setDragY(dy)
  }, [])

  const onPointerUp = useCallback(() => {
    if (dragStartRef.current === null) return
    dragStartRef.current = null
    if (dragY > 100) {
      handleClose()
    } else {
      setDragY(0)
    }
  }, [dragY, handleClose])

  if ((!open && !isClosing) || !displayLesson) return null

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 z-overlay bg-[var(--sched-overlay-bg)] backdrop-blur-sm"
        onClick={handleClose}
        aria-hidden="true"
        style={{ opacity: dragY > 0 ? Math.max(0.2, 1 - dragY / 200) : undefined }}
      />

      {/* Bottom Sheet */}
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="bottomsheet-title"
        data-closing={isClosing || undefined}
        className="sched-bottom-sheet border-t border-glass-border bg-surface/(--opacity-heavy) shadow-glass-strong backdrop-blur-xl glass-noise"
        style={{
          transform: dragY > 0 ? `translateY(${dragY}px)` : undefined,
          transition: dragY === 0 ? "transform 0.3s cubic-bezier(0.34, 1.56, 0.64, 1)" : "none",
        }}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerCancel={() => { dragStartRef.current = null; setDragY(0) }}
      >
        {/* Handle bar */}
        <div className="flex justify-center pb-2 pt-3" aria-hidden="true">
          <div className="h-1 w-10 rounded-full bg-text-secondary/30" />
        </div>

        {/* Header */}
        <div className="flex items-center justify-between px-5 pb-3">
          <h3
            id="bottomsheet-title"
            className="text-base font-extrabold text-text-primary tracking-tight truncate flex-1"
          >
            {displayLesson.subject || "—"}
          </h3>
          <button
            onClick={handleClose}
            aria-label={t("common:buttons.close", { defaultValue: "Close" })}
            className="ml-2 flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-text-secondary transition-colors hover:bg-surface-elevated/(--opacity-dim) focus-visible:ring-2 focus-visible:ring-brand"
          >
            <CloseIcon size={14} aria-hidden="true" />
          </button>
        </div>

        {/* Content */}
        {/* FIX-69-02: min(80vh, 600px) for landscape usability; safe-area for notched devices */}
        <div className="overflow-y-auto px-5 pb-5 space-y-3" style={{ maxHeight: "min(80vh, 600px)", paddingBottom: "max(1.25rem, env(safe-area-inset-bottom))" }}>
          {/* Type + Time row */}
          <div className="flex items-center gap-2">
            <Badge
              className="font-semibold text-xs"
              style={{ background: getLessonTypeColor(displayLesson.lesson_type) }}
            >
              {getLessonTypeLabel(displayLesson.lesson_type)}
            </Badge>
            <span className="flex items-center gap-1 text-xs text-text-secondary">
              <ClockIcon size={12} aria-hidden="true" />
              {`${getTimeStr(displayLesson)} – ${getEndTimeStr(displayLesson)}`}
            </span>
          </div>

          {/* Teacher */}
          {displayLesson.teacher && (
            <div className="flex items-center gap-2 text-sm text-text-primary">
              <TeacherIcon size={14} className="shrink-0 text-brand opacity-60" aria-hidden="true" />
              <span>{displayLesson.teacher}</span>
            </div>
          )}

          {/* Room */}
          {displayLesson.room && (
            <div className="flex items-center gap-2 text-sm text-text-primary">
              <RoomIcon size={14} className="shrink-0 text-brand opacity-60" aria-hidden="true" />
              <span>{displayLesson.room}</span>
            </div>
          )}
        </div>

        {/* Actions */}
        {canEdit && (
          <div className="flex gap-2 border-t border-glass-border px-5 py-3">
            <Button variant="outline" size="sm" onClick={onEdit} className="flex-1 gap-1.5">
              <EditIcon size={13} aria-hidden="true" />
              {t("schedule:buttons.edit")}
            </Button>
            <Button
              variant="ghost"
              size="sm"
              onClick={onDelete}
              aria-label={t("schedule:aria.deleteLesson")}
              className="text-error hover:bg-error/(--opacity-subtle)"
            >
              <DeleteIcon size={13} aria-hidden="true" />
            </Button>
          </div>
        )}
      </div>
    </>
  )
}
