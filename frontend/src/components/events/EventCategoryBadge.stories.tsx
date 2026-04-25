import type { Meta, StoryObj } from "@storybook/react-vite"
import { EventCategoryBadge } from "./EventCategoryBadge"
import { EVENT_CATEGORIES } from "@/features/events/categories"

const meta: Meta<typeof EventCategoryBadge> = {
  title: "Events/EventCategoryBadge",
  component: EventCategoryBadge,
  tags: ["autodocs"],
  argTypes: {
    category: {
      control: "select",
      options: EVENT_CATEGORIES,
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

export const Hackathon: Story = {
  args: {
    category: "hackathon",
    size: "md",
  },
}

export const Lecture: Story = {
  args: {
    category: "lecture",
    size: "sm",
  },
}
