import type { Meta, StoryObj } from "@storybook/react-vite"
import { NewsCategoryBadge } from "./NewsCategoryBadge"
import { ALL_CATEGORIES } from "@/features/news/categories"

const meta: Meta<typeof NewsCategoryBadge> = {
  title: "News/NewsCategoryBadge",
  component: NewsCategoryBadge,
  tags: ["autodocs"],
  argTypes: {
    category: {
      control: "select",
      options: ALL_CATEGORIES.map((c) => c.id),
    },
    size: {
      control: "radio",
      options: ["sm", "md"],
    },
  },
}

export default meta
type Story = StoryObj<typeof NewsCategoryBadge>

export const Announcement: Story = {
  args: {
    category: "general",
    size: "md",
  },
}

export const Academic: Story = {
  args: {
    category: "education",
    size: "sm",
  },
}

export const Research: Story = {
  args: {
    category: "science",
    size: "md",
  },
}

export const Campus: Story = {
  args: {
    category: "campus",
    size: "sm",
  },
}
