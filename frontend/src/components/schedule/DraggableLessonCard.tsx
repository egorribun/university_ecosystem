/**
 * DraggableLessonCard — @dnd-kit wrapper for admin drag-and-drop.
 * Wave 66 (Idea #18). Only renders drag handle when canEdit is true.
 */
import { memo } from "react"
import { useSortable } from "@dnd-kit/sortable"
import { CSS } from "@dnd-kit/utilities"
import { GripVertical } from "lucide-react"
import { useTranslation } from "react-i18next"
import { cn } from "@/utils/cn"
import { LessonCard, type LessonCardProps } from "./LessonCard"

interface DraggableLessonCardProps extends LessonCardProps {
  /** Unique ID for dnd-kit (typically lessonId) */
  dragId: string
  /** Whether drag-and-drop is enabled (admin/teacher only) */
  dragEnabled?: boolean
}

export const DraggableLessonCard = memo(function DraggableLessonCard({
  dragId,
  dragEnabled = false,
  ...cardProps
}: DraggableLessonCardProps) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({
    id: dragId,
    disabled: !dragEnabled,
  })

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
  }

  const { t } = useTranslation(["schedule"])

  if (!dragEnabled) {
    return <LessonCard {...cardProps} />
  }

  return (
    <div ref={setNodeRef} style={style} className={cn("relative", isDragging && "sched-dragging")}>
      {/* Drag handle — top-left grip icon */}
      <button
        type="button"
        {...attributes}
        {...listeners}
        className="absolute -left-1 top-1/2 -translate-y-1/2 z-10 flex h-6 w-4 items-center justify-center rounded text-text-secondary opacity-0 transition-opacity group-hover:opacity-60 hover:!opacity-100 cursor-grab active:cursor-grabbing focus-visible:ring-2 focus-visible:ring-brand"
        aria-label={t("schedule:drag.handle")}
        tabIndex={-1}
      >
        <GripVertical size={12} aria-hidden="true" />
      </button>
      <LessonCard {...cardProps} />
    </div>
  )
})

export default DraggableLessonCard
