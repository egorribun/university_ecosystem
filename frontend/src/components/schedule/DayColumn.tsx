import { useCallback, useMemo, useRef, useState, useEffect } from "react"
import { useTranslation } from "react-i18next"
import { DndContext, closestCenter, type DragEndEvent } from "@dnd-kit/core"
import { SortableContext, verticalListSortingStrategy } from "@dnd-kit/sortable"
import { Plus as AddIcon, CalendarOff as EmptyDayIcon } from "lucide-react"
import { cn } from "@/utils/cn"
import { Badge } from "@/components/ui"
import { EmptyState } from "@/components/ui/EmptyState"
import OfflineFallback from "@/components/feedback/OfflineFallback"

import { type Lesson, minutesDiff } from "./scheduleUtils"
import { LessonCard } from "./LessonCard"
import { DraggableLessonCard } from "./DraggableLessonCard"

/** Heatmap thresholds for day load intensity (lesson count) */
const HEAT_THRESHOLDS = { heavy: 5, medium: 3, light: 1 } as const

/** PERF-70-06: extracted so DndContext only mounts when canEdit */
function LessonList({
  lessons,
  canEdit,
  compact,
  conflictedIds,
  currentLessonId,
  currentProgress,
  notesMap,
  onLessonDelete,
  getLessonTypeColor,
  getLessonTypeLabel,
  handleDragEnd,
  lessonIds,
}: {
  lessons: Lesson[]
  canEdit: boolean
  compact: boolean
  conflictedIds: Set<string>
  currentLessonId?: string
  /** FIX-71-02: current lesson progress 0-100 for glow urgency */
  currentProgress?: number
  notesMap: Map<string, boolean>
  onLessonDelete: (id: string) => void
  getLessonTypeColor: (val?: string | null) => string
  getLessonTypeLabel: (val?: string | null) => string
  handleDragEnd: (event: DragEndEvent) => void
  lessonIds: string[]
}) {
  // CQ-71-03: useTranslation directly instead of accepting unstable `t` prop
  const { t } = useTranslation(["schedule"])
  const cardElements = lessons.map((lesson, idx) => {
    const prev = lessons[idx - 1]
    const gap = prev ? minutesDiff(prev.end_time, lesson.start_time) : 0
    const isConflict = conflictedIds.has(lesson.id)
    const isCurrent = lesson.id === currentLessonId
    const sharedProps = {
      lesson,
      isConflict,
      isCurrent,
      currentProgress: isCurrent ? (currentProgress ?? 0) : 0, // FIX-71-02
      index: idx,
      compact,
      hasNote: notesMap.get(lesson.id) ?? false,
      onDelete: () => onLessonDelete(lesson.id),
      canEdit,
      getLessonTypeColor,
      getLessonTypeLabel,
    }

    return (
      <div key={lesson.id}>
        {idx > 0 && gap > 0 && (
          <div className="mb-2.5 flex items-center gap-2 px-1">
            <div className="sched-timeline-dot" />
            <div className="sched-timeline-line flex-1" />
            <span className="sched-break-pill">
              {t("schedule:break", { minutes: gap })}
            </span>
            <div className="sched-timeline-line flex-1" />
            <div className="sched-timeline-dot" />
          </div>
        )}
        {canEdit ? (
          <DraggableLessonCard dragId={lesson.id} dragEnabled {...sharedProps} />
        ) : (
          <LessonCard {...sharedProps} />
        )}
      </div>
    )
  })

  if (!canEdit) {
    return <div className="flex flex-col gap-3.5">{cardElements}</div>
  }

  return (
    <DndContext collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
      <SortableContext items={lessonIds} strategy={verticalListSortingStrategy}>
        <div className="flex flex-col gap-3.5">{cardElements}</div>
      </SortableContext>
    </DndContext>
  )
}

/**
 * DayColumn — Single-day vertical card stack for mobile schedule view.
 *
 * Renders lesson cards with @dnd-kit drag-to-reorder support, timeline
 * connectors between lessons showing break duration, heatmap background
 * based on lesson count, and a confetti burst when all lessons are past.
 * Wraps each lesson in DraggableLessonCard for drag handle support.
 */
interface DayColumnProps {
  day: string
  label: string
  lessons: Lesson[]
  isToday: boolean
  isOnline: boolean
  hasSchedule: boolean
  userRole?: string
  conflictedIds: Set<string>
  compact?: boolean
  currentLessonId?: string
  /** FIX-71-02: current lesson progress 0-100 for glow urgency */
  currentProgress?: number
  /** All today's lessons are past — triggers celebration (FIX-68-23) */
  dayComplete?: boolean
  /** Map of lessonId → hasNote for note indicators (FIX-67-02) */
  notesMap: Map<string, boolean>
  /** Called when a lesson is reordered via drag-drop (FIX-67-DND) */
  onLessonReorder?: (lessonId: string, newIndex: number) => void
  onAdd: () => void
  onLessonDelete: (id: string) => void
  onRetry: () => void
  getLessonTypeColor: (val?: string | null) => string
  getLessonTypeLabel: (val?: string | null) => string
  /** CQ-71-02: React 19 ref-as-prop (forwardRef is legacy) */
  ref?: React.Ref<HTMLDivElement>
}

// CQ-71-02: React 19 supports ref as regular prop — forwardRef is legacy
export function DayColumn({
  day,
  label,
  lessons,
  isToday,
  isOnline,
  hasSchedule,
  userRole,
  conflictedIds,
  compact = false,
  currentLessonId,
  currentProgress,
  dayComplete = false,
  notesMap,
  onLessonReorder,
  onAdd,
  onLessonDelete,
  onRetry,
  getLessonTypeColor,
  getLessonTypeLabel,
  ref,
}: DayColumnProps) {
  const { t } = useTranslation(["schedule", "common"])

  const canEdit = userRole === "admin" || userRole === "teacher"
  const lessonIds = useMemo(() => lessons.map((l) => l.id), [lessons])

  // Celebration: show confetti once when today's lessons are all done (FIX-68-23)
  const celebratedRef = useRef(false)
  const [showConfetti, setShowConfetti] = useState(false)
  useEffect(() => {
    if (dayComplete && isToday && !celebratedRef.current && lessons.length > 0) {
      celebratedRef.current = true
      setShowConfetti(true)
      const timer = setTimeout(() => setShowConfetti(false), 2000)
      return () => clearTimeout(timer)
    }
  }, [dayComplete, isToday, lessons.length])

  // FIX-70-01: useCallback (not useMemo) — correct hook for function identity
  const handleDragEnd = useCallback(
    (event: DragEndEvent) => {
      if (!onLessonReorder) return
      const { active, over } = event
      if (!over || active.id === over.id) return
      const newIdx = lessons.findIndex((l) => l.id === over.id)
      if (newIdx >= 0) onLessonReorder(String(active.id), newIdx)
    },
    [lessons, onLessonReorder],
  )

  // Heatmap: color intensity based on lesson count
  const heatClass =
    lessons.length >= HEAT_THRESHOLDS.heavy
      ? "sched-heat-heavy"
      : lessons.length >= HEAT_THRESHOLDS.medium
        ? "sched-heat-medium"
        : lessons.length >= HEAT_THRESHOLDS.light
          ? "sched-heat-light"
          : ""

  return (
    <div
      ref={ref}
      id={`day-panel-${day}`}
      role="tabpanel"
      aria-labelledby={`day-tab-${day}`}
      className={cn(
        "sched-card-matte sched-day-column-container group relative isolate mb-3 glass-noise",
        compact ? "p-4 sm:p-5" : "p-5 sm:p-6",
        isToday && "sched-today-col ring-2 ring-brand/(--opacity-dim)",
        !isToday && heatClass
      )}
    >
      {/* ── Day header ──────────────────────────────────── */}
      <div className="mb-4 flex items-center gap-2">
        {/* Confetti burst (FIX-68-23) */}
        {showConfetti && (
          <>
            <div className="pointer-events-none absolute inset-0 z-10 overflow-hidden" aria-hidden="true">
              {[0, 1, 2, 3, 4, 5].map((i) => (
                <span key={i} className="sched-confetti-dot" style={{ "--_i": i } as React.CSSProperties} />
              ))}
            </div>
            {/* A11Y-71-03: screen reader announcement for day completion */}
            <div className="sr-only" role="status" aria-live="assertive">
              {t("schedule:dayComplete", { defaultValue: "All lessons for today are complete!" })}
            </div>
          </>
        )}
        <h3
          className={cn(
            "text-lg font-extrabold tracking-tight text-text-primary transition-colors duration-fast",
            isToday && "text-brand"
          )}
        >
          {label}
        </h3>
        {lessons.length > 0 && (
          <Badge size="xs" variant="outline" className="font-medium opacity-70">
            {lessons.length}
          </Badge>
        )}
        {(userRole === "admin" || userRole === "teacher") && (
          <button
            type="button"
            id={`add-lesson-${day}`}
            className="ml-auto flex h-9 w-9 min-h-[44px] min-w-[44px] items-center justify-center rounded-lg border border-brand/(--opacity-dim) bg-brand/(--opacity-subtle) text-brand transition-all duration-fast hover:border-brand hover:bg-brand hover:text-[var(--sched-on-accent)] hover:shadow-sm hover:scale-110 focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-1"
            onClick={(e) => {
              e.stopPropagation()
              onAdd()
            }}
            aria-label={t("schedule:aria.addLesson", { day: label })}
          >
            <AddIcon size={16} aria-hidden="true" />
          </button>
        )}
      </div>

      {/* ── Lessons list or empty state ──────────────── */}
      {lessons.length === 0 ? (
        <div className="flex justify-center py-6">
          {!isOnline && !hasSchedule ? (
            <OfflineFallback onRetry={onRetry} />
          ) : (
            <EmptyState
              icon={
                <div className="sched-empty-icon relative">
                  <EmptyDayIcon size={24} />
                  <div className="sched-empty-ring" />
                </div>
              }
              title={t("schedule:mobile.noLessons", { defaultValue: "No lessons" })}
              className="max-w-[16rem] border-none bg-transparent py-6 shadow-none backdrop-blur-none"
            />
          )}
        </div>
      ) : (
        /* PERF-70-06: DndContext only rendered when canEdit — avoids pointer listeners + collision setup for viewers */
        <LessonList
          lessons={lessons}
          canEdit={canEdit}
          compact={compact}
          conflictedIds={conflictedIds}
          currentLessonId={currentLessonId}
          currentProgress={currentProgress}
          notesMap={notesMap}
          onLessonDelete={onLessonDelete}
          getLessonTypeColor={getLessonTypeColor}
          getLessonTypeLabel={getLessonTypeLabel}
          handleDragEnd={handleDragEnd}
          lessonIds={lessonIds}
        />
      )}
    </div>
  )
}
