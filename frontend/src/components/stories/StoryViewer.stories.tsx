import type { Meta, StoryObj } from "@storybook/react-vite"
import { StoryViewer } from "./StoryViewer"
import type { StoryItem } from "@/types/Story"

const meta: Meta<typeof StoryViewer> = {
  title: "Components/Stories/StoryViewer",
  component: StoryViewer,
  tags: ["autodocs"],
  parameters: {
    layout: "fullscreen",
  },
  decorators: [
    (Story) => (
      <div className="min-h-screen bg-gray-900">
        <Story />
      </div>
    ),
  ],
}

export default meta
type Story = StoryObj<typeof StoryViewer>

const mockStories: StoryItem[] = [
  {
    id: "1",
    title: "Welcome to University",
    short_text: "Discover our vibrant campus life and opportunities.",
    cover_url:
      "https://images.unsplash.com/photo-1541339907198-e08756dedf3f?w=800&auto=format&fit=crop",
    created_at: new Date().toISOString(),
    expires_at: new Date(Date.now() + 86400000).toISOString(),
    published_at: new Date().toISOString(),
    is_active: true,
    cover_url_optimized: null,
  },
]

export const Default: Story = {
  args: {
    stories: mockStories,
    activeStoryIndex: 0,
    progress: 30,
    onClose: () => {},
    onNext: () => {},
    onPrev: () => {},
    onPause: () => {},
    onResume: () => {},
  },
}

export const WithCTA: Story = {
  args: {
    stories: [
      {
        ...mockStories[0]!,
        cta_url: "https://example.com/apply",
      },
    ],
    activeStoryIndex: 0,
    progress: 50,
  },
}

export const NoImage: Story = {
  args: {
    stories: [
      {
        id: "2",
        title: "Just Text",
        short_text: "This story has no background image, should show fallback.",
        cover_url: "",
        created_at: new Date().toISOString(),
        expires_at: new Date(Date.now() + 86400000).toISOString(),
        published_at: new Date().toISOString(),
        is_active: true,
        cover_url_optimized: null,
      },
    ],
    activeStoryIndex: 0,
    progress: 10,
  },
}
