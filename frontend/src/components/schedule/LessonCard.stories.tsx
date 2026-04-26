import type { Meta, StoryObj } from "@storybook/react-vite-vite"
import { LessonCard } from "./LessonCard"

const mockLesson = {
  id: "lesson-1",
  subject: "Advanced Mathematics",
  teacher: "Dr. Smith",
  room: "Building A, Room 101",
  lesson_type: "lecture",
  start_time: "09:00:00",
  end_time: "10:30:00",
  weekday: "Monday",
  parity: "both" as const,
}

const meta: Meta<typeof LessonCard> = {
  title: "Schedule/LessonCard",
  component: LessonCard,
  tags: ["autodocs"],
  argTypes: {
    lesson: { control: "object" },
    isConflict: { control: "boolean" },
    isCurrent: { control: "boolean" },
    compact: { control: "boolean" },
    canEdit: { control: "boolean" },
    hasNote: { control: "boolean" },
  },
  args: {
    lesson: mockLesson,
    isConflict: false,
    isCurrent: false,
    compact: false,
    onDelete: () => console.warn("Delete clicked"),
    onOpen: () => console.warn("Card clicked"),
    getLessonTypeColor: (type) => {
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
    },
    getLessonTypeLabel: (type) => type || "Lesson",
  },
}

export default meta
type Story = StoryObj<typeof LessonCard>

export const Default: Story = {}

export const Practice: Story = {
  args: {
    lesson: {
      ...mockLesson,
      subject: "Physics Lab",
      lesson_type: "practice",
    },
  },
}

export const Current: Story = {
  args: {
    isCurrent: true,
    currentProgress: 65,
  },
}

export const Conflict: Story = {
  args: {
    isConflict: true,
  },
}

export const Compact: Story = {
  args: {
    compact: true,
  },
}

export const Editable: Story = {
  args: {
    canEdit: true,
  },
}

export const WithNote: Story = {
  args: {
    hasNote: true,
  },
}
