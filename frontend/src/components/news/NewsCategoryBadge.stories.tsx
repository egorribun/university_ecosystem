import type { Meta, StoryObj } from "@storybook/react-vite-vite"
import { NewsCategoryBadge } from "./NewsCategoryBadge"
import { NEWS_CATEGORIES } from "@/features/news/categories"

const meta: Meta<typeof NewsCategoryBadge> = {
  title: "News/NewsCategoryBadge",
  component: NewsCategoryBadge,
  tags: ["autodocs"],
  argTypes: {
    category: {
      control: "select",
      options: NEWS_CATEGORIES,
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
    category: "announcement",
    size: "md",
  },
}

export const Academic: Story = {
  args: {
    category: "academic",
    size: "sm",
  },
}

export const Research: Story = {
  args: {
    category: "research",
    size: "md",
  },
}

export const CampusLife: Story = {
  args: {
    category: "campus_life",
    size: "sm",
  },
}
