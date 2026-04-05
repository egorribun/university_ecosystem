import { forwardRef, useMemo, useRef, useState, useEffect } from "react"
import { useTranslation } from "react-i18next"
import { DndContext, closestCenter, type DragEndEvent } from "@dnd-kit/core"
import { SortableContext, verticalListSortingStrategy } from "@dnd-kit/sortable"
import { Plus as AddIcon, CalendarOff as EmptyDayIcon } from "lucide-react"
import { cn } from "@/utils/cn"
import { Badge } from "@/components/ui"
import { EmptyState } from "@/components/ui/EmptyState"
import OfflineFallback from "@/components/feedback/OfflineFallback"

import { type Lesson, minutesDiff } from "./scheduleUtils"
import { DraggableLessonCard } from "./DraggableLessonCard"

/** Heatmap thresholds for day load intensity (lesson count) */
const HEAT_THRESHOLDS = { heavy: 5, medium: 3, light: 1 } as const

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
  /** All today's lessons are past — triggers celebration (FIX-68-23) */
  dayComplete?: boolean
  /** Map of lessonId → hasNote for note indicators (FIX-67-02) */
  notesMap?: Map<string, boolean>
  /** Called when a lesson is reordered via drag-drop (FIX-67-DND) */
  onLessonReorder?: (lessonId: string, newIndex: number) => void
  onAdd: () => void
  onLessonDelete: (id: string) => void
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
      compact = false,
      currentLessonId,
      dayComplete = false,
      notesMap,
      onLessonReorder,
      onAdd,
      onLessonDelete,
      onRetry,
      getLessonTypeColor,
      getLessonTypeLabel,
    },
    ref,
  ) => {
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

    const handleDragEnd = useMemo(() => {
      if (!onLessonReorder) return undefined
      return (event: DragEndEvent) => {
        const { active, over } = event
        if (!over || active.id === over.id) return
        const newIdx = lessons.findIndex((l) => l.id === over.id)
        if (newIdx >= 0) onLessonReorder(String(active.id), newIdx)
      }
    }, [lessons, onLessonReorder])

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
            <div className="pointer-events-none absolute inset-0 z-10 overflow-hidden" aria-hidden="true">
              {[0, 1, 2, 3, 4, 5].map((i) => (
                <span key={i} className="sched-confetti-dot" style={{ "--_i": i } as React.CSSProperties} />
              ))}
            </div>
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
              id={`add-lesson-${day}`}
              className="ml-auto flex h-7 w-7 items-center justify-center rounded-lg border border-brand/(--opacity-dim) bg-brand/(--opacity-subtle) text-brand transition-all duration-fast hover:border-brand hover:bg-brand hover:text-white hover:shadow-sm hover:scale-110 focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-1"
              onClick={(e) => {
                e.stopPropagation()
                onAdd()
              }}
              aria-label={t("schedule:aria.addLesson", { day: label })}
            >
              <AddIcon size={14} aria-hidden="true" />
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
                title={t("schedule:mobile.noLessons")}
                className="max-w-[16rem] border-none bg-transparent py-6 shadow-none backdrop-blur-none"
              />
            )}
          </div>
        ) : (
          <DndContext collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
            <SortableContext items={lessonIds} strategy={verticalListSortingStrategy}>
              <div className="flex flex-col gap-3.5">
                {lessons.map((lesson, idx) => {
                  const prev = lessons[idx - 1]
                  const gap = prev ? minutesDiff(prev.end_time, lesson.start_time) : 0
                  const isConflict = conflictedIds.has(lesson.id)
                  const isCurrent = lesson.id === currentLessonId

                  return (
                    <div key={lesson.id}>
                      {/* ── Break timeline connector ────────────── */}
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
                      <DraggableLessonCard
                        dragId={lesson.id}
                        dragEnabled={canEdit}
                        lesson={lesson}
                        isConflict={isConflict}
                        isCurrent={isCurrent}
                        index={idx}
                        compact={compact}
                        hasNote={notesMap?.get(lesson.id) ?? false}
                        onDelete={() => onLessonDelete(lesson.id)}
                        canEdit={canEdit}
                        getLessonTypeColor={getLessonTypeColor}
                        getLessonTypeLabel={getLessonTypeLabel}
                      />
                    </div>
                  )
                })}
              </div>
            </SortableContext>
          </DndContext>
        )}
      </div>
    )
  },
)

DayColumn.displayName = "DayColumn"
