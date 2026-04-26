import type { Meta, StoryObj } from "@storybook/react-vite"
import { StoryList } from "./StoryList"
import type { StoryItem } from "@/types/Story"

const meta: Meta<typeof StoryList> = {
  title: "Components/Stories/StoryList",
  component: StoryList,
  tags: ["autodocs"],
  parameters: {
    layout: "padded",
  },
}

export default meta
type Story = StoryObj<typeof StoryList>

const mockStories: StoryItem[] = [
  {
    id: "1",
    title: "Campus Life",
    cover_url:
      "https://images.unsplash.com/photo-1523050854058-8df90110c9f1?w=800&auto=format&fit=crop",
    created_at: new Date().toISOString(),
    expires_at: new Date(Date.now() + 86400000).toISOString(),
    published_at: new Date().toISOString(),
    is_active: true,
    cover_url_optimized: null,
    short_text: "Campus Life",
  },
  {
    id: "2",
    title: "Research",
    cover_url:
      "https://images.unsplash.com/photo-1532094349884-543bc11b234d?w=800&auto=format&fit=crop",
    created_at: new Date().toISOString(),
    expires_at: new Date(Date.now() + 86400000).toISOString(),
    published_at: new Date().toISOString(),
    is_active: true,
    cover_url_optimized: null,
    short_text: "Research",
  },
  {
    id: "3",
    title: "Sports",
    cover_url: "", // No image, should show initials
    created_at: new Date().toISOString(),
    expires_at: new Date(Date.now() + 86400000).toISOString(),
    published_at: new Date().toISOString(),
    is_active: true,
    cover_url_optimized: null,
    short_text: "Sports",
  },
]

export const Default: Story = {
  args: {
    stories: mockStories,
    loading: false,
    activeStoryId: undefined,
  },
}

export const Loading: Story = {
  args: {
    stories: [],
    loading: true,
  },
}

export const Empty: Story = {
  args: {
    stories: [],
    loading: false,
  },
}

export const WithActiveStory: Story = {
  args: {
    stories: mockStories,
    loading: false,
    activeStoryId: "2",
  },
}
