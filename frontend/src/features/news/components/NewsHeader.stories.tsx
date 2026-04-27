import type { Meta, StoryObj } from "@storybook/react-vite"
import { NewsHeader } from "./NewsHeader"

const meta: Meta<typeof NewsHeader> = {
  title: "Features/News/NewsHeader",
  component: NewsHeader,
  parameters: {
    layout: "fullscreen",
  },
  decorators: [
    (Story) => (
      <div className="p-4 sm:p-8 bg-background min-h-[300px]">
        <Story />
      </div>
    ),
  ],
  tags: ["autodocs"],
}

export default meta
type Story = StoryObj<typeof NewsHeader>

const baseArgs = {
  onAddClick: () => console.warn("Add click"),
  isAdmin: false,
  newsCount: 42,
  searchQuery: "",
  onSearchChange: (q: string) => console.warn("Search:", q),
  activeCategory: "all" as const,
  onCategoryChange: (c: string) => console.warn("Category:", c),
  sortMode: "newest" as const,
  onSortChange: (s: string) => console.warn("Sort:", s),
  bookmarkCount: 0,
}

export const Default: Story = {
  args: baseArgs,
}

export const Admin: Story = {
  args: {
    ...baseArgs,
    isAdmin: true,
  },
}

export const WithBookmarks: Story = {
  args: {
    ...baseArgs,
    bookmarkCount: 5,
    activeCategory: "saved",
  },
}

export const Searching: Story = {
  args: {
    ...baseArgs,
    searchQuery: "University",
  },
}

export const CategoryActive: Story = {
  args: {
    ...baseArgs,
    activeCategory: "campus",
  },
}
