import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, it, expect, vi } from "vitest"
import { StoryList } from "../StoryList"
import type { StoryItem } from "@/types/Story"

// Mock translations
vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, options?: any) => {
      if (key === "aria.storyItem") return `Story: ${options?.title}`
      if (key === "stories.heading") return "Stories"
      return key
    },
  }),
}))

const mockStories: StoryItem[] = [
  {
    id: "1",
    title: "Story 1",
    created_at: "2023-01-01",
    expires_at: "2023-01-02",
    published_at: "2023-01-01",
    is_active: true,
    cover_url_optimized: null,
    short_text: "Story 1",
  },
  {
    id: "2",
    title: "Story 2",
    created_at: "2023-01-02",
    expires_at: "2023-01-03",
    published_at: "2023-01-02",
    is_active: true,
    cover_url_optimized: null,
    short_text: "Story 2",
  },
]

describe("StoryList", () => {
  it("renders nothing when empty and not loading", () => {
    const { container } = render(<StoryList stories={[]} loading={false} onOpenStory={vi.fn()} />)
    expect(container).toBeEmptyDOMElement()
  })

  it("renders skeletons when loading", () => {
    const { container } = render(<StoryList stories={[]} loading={true} onOpenStory={vi.fn()} />)
    expect(container.getElementsByClassName("animate-pulse").length).toBeGreaterThan(0)
  })

  it("renders stories when provided", () => {
    render(<StoryList stories={mockStories} onOpenStory={vi.fn()} />)
    expect(screen.getByLabelText("Story: Story 1")).toBeInTheDocument()
    expect(screen.getByLabelText("Story: Story 2")).toBeInTheDocument()
  })

  it("calls onOpenStory when a story is clicked", async () => {
    const user = userEvent.setup()
    const handleOpen = vi.fn()
    render(<StoryList stories={mockStories} onOpenStory={handleOpen} />)

    await user.click(screen.getByLabelText("Story: Story 1"))
    expect(handleOpen).toHaveBeenCalledWith(mockStories[0], 0)
  })

  it("calls onPrefetch on hover", async () => {
    const user = userEvent.setup()
    const handlePrefetch = vi.fn()
    render(<StoryList stories={mockStories} onOpenStory={vi.fn()} onPrefetch={handlePrefetch} />)

    await user.hover(screen.getByLabelText("Story: Story 1"))
    expect(handlePrefetch).toHaveBeenCalled()
  })
})
