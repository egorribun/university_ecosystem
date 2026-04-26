import type { Meta, StoryObj } from "@storybook/react-vite"
import { EventCategoryBadge } from "./EventCategoryBadge"
import { ALL_EVENT_CATEGORIES } from "@/features/events/categories"

const meta: Meta<typeof EventCategoryBadge> = {
  title: "Events/EventCategoryBadge",
  component: EventCategoryBadge,
  tags: ["autodocs"],
  argTypes: {
    category: {
      control: "select",
      options: ALL_EVENT_CATEGORIES.map((c) => c.id),
    },
    size: {
      control: "radio",
      options: ["sm", "md"],
    },
  },
}

export default meta
type Story = StoryObj<typeof EventCategoryBadge>

export const Conference: Story = {
  args: {
    category: "conference",
    size: "md",
  },
}

export const Workshop: Story = {
  args: {
    category: "workshop",
    size: "sm",
  },
}

export const Social: Story = {
  args: {
    category: "social",
    size: "md",
  },
}

export const Lecture: Story = {
  args: {
    category: "lecture",
    size: "sm",
  },
}
