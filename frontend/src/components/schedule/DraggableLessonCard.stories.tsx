import type { Meta, StoryObj, Decorator } from "@storybook/react-vite"
import { DndContext } from "@dnd-kit/core"
import { SortableContext } from "@dnd-kit/sortable"
import { DraggableLessonCard } from "./DraggableLessonCard"

// Wave 199 SW1 — DraggableLessonCard Storybook fixture (CONTEXT-tier, no infra).
//
// @dnd-kit wrapper around LessonCard. `useSortable` runs on every render (before
// the dragEnabled early-return), so it needs a DndContext + SortableContext
// ancestor — supplied by the harness. When dragEnabled=false it renders a bare
// LessonCard; when true it adds the grip handle (visible on group-hover). No
// network. Mirrors the existing LessonCard.stories fixture + helpers; wrapped in
// `.schedule-theme` for the lesson-type accent tokens.
//
// Variants: Static (dragEnabled=false) / Draggable (dragEnabled=true) / DarkMode.

const mockLesson = {
  id: "lesson-1",
  subject: "Высшая математика",
  teacher: "Доц. Смирнов",
  room: "ГУК-305",
  lesson_type: "lecture",
  start_time: "09:00:00",
  end_time: "10:30:00",
  weekday: "Monday",
  parity: "both" as const,
}

const getLessonTypeColor = (type?: string | null) => {
  switch (type?.toLowerCase()) {
    case "lecture":
      return "var(--lt-lecture-accent)"
    case "practice":
      return "var(--lt-practice-accent)"
    case "lab":
      return "var(--lt-lab-accent)"
    default:
      return "var(--lesson-type-default)"
  }
}
const getLessonTypeLabel = (type?: string | null) => type || "Lesson"

const themed = (dark: boolean): Decorator => {
  // eslint-disable-next-line react/display-name -- Storybook decorator, not a render component
  return (Story) => (
    <div className={dark ? "dark" : undefined}>
      <div className="schedule-theme" style={{ background: "var(--bg-page)", padding: "2rem" }}>
        <Story />
      </div>
    </div>
  )
}

const meta: Meta<typeof DraggableLessonCard> = {
  title: "Schedule/DraggableLessonCard",
  component: DraggableLessonCard,
  parameters: { layout: "centered" },
  tags: ["autodocs"],
  args: {
    dragId: "lesson-1",
    lesson: mockLesson,
    isConflict: false,
    onDelete: () => {},
    getLessonTypeColor,
    getLessonTypeLabel,
  },
  render: (args) => (
    <DndContext>
      <SortableContext items={[args.dragId]}>
        <div className="group" style={{ width: 340 }}>
          <DraggableLessonCard {...args} />
        </div>
      </SortableContext>
    </DndContext>
  ),
}

export default meta
type Story = StoryObj<typeof DraggableLessonCard>

export const Static: Story = {
  args: { dragEnabled: false },
  decorators: [themed(false)],
}

export const Draggable: Story = {
  args: { dragEnabled: true, canEdit: true },
  decorators: [themed(false)],
}

export const DarkMode: Story = {
  args: { dragEnabled: true, canEdit: true },
  decorators: [themed(true)],
  parameters: { backgrounds: { default: "dark" } },
}
