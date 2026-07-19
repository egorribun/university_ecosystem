import { screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, it, expect, vi } from "vitest"
import { StoryViewer } from "../StoryViewer"
import type { StoryItem } from "@/types/Story"
import { renderWithRouter } from "@/tests/helpers/renderWithRouter"

// Mock translations
vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, options?: any) => {
      if (key === "stories.viewer.aria.dialog") return `Story Viewer: ${options?.title}`
      if (key === "stories.viewer.aria.close") return "Close"
      if (key === "stories.viewer.aria.next") return "Next"
      if (key === "stories.viewer.aria.prev") return "Previous"
      return key
    },
  }),
}))

// Mock useSwipe
vi.mock("@/hooks/useSwipe", () => ({
  useSwipe: () => ({
    onPointerDown: vi.fn(),
    onPointerUp: vi.fn(),
    onPointerCancel: vi.fn(),
    onPointerLeave: vi.fn(),
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

describe("StoryViewer", () => {
  const defaultProps = {
    stories: mockStories,
    activeStoryIndex: 0,
    progress: 0,
    onClose: vi.fn(),
    onNext: vi.fn(),
    onPrev: vi.fn(),
    onPause: vi.fn(),
    onResume: vi.fn(),
  }

  const renderViewer = (props = {}) => {
    const merged = { ...defaultProps, ...props }
    const Wrapped = () => <StoryViewer {...merged} />
    return renderWithRouter({ ui: Wrapped })
  }

  it("renders nothing when activeStoryIndex is null", async () => {
    const { container } = await renderViewer({ activeStoryIndex: null })
    // TanStack Router renders an <Outlet /> which wraps the ui; even when the
    // tested component returns null the container still has the router shell.
    // Assert the StoryViewer-specific dialog is absent instead.
    expect(container.querySelector("[role='dialog']")).toBeNull()
  })

  it("renders the active story", async () => {
    await renderViewer({ activeStoryIndex: 0 })
    // StoryViewer now uses aria-labelledby pointing to the heading, so the
    // dialog's accessible name is the story title rather than the mocked
    // "Story Viewer: <title>" aria-label key the test originally expected.
    expect(screen.getByRole("dialog", { name: "Story 1" })).toBeInTheDocument()
    expect(screen.getByRole("heading", { name: "Story 1" })).toBeInTheDocument()
  })

  it("calls onClose when close button clicked", async () => {
    const user = userEvent.setup()
    const handleClose = vi.fn()
    await renderViewer({ onClose: handleClose })
    await user.click(screen.getByLabelText("Close"))
    expect(handleClose).toHaveBeenCalled()
  })

  it("calls onNext when next button clicked", async () => {
    const user = userEvent.setup()
    const handleNext = vi.fn()
    await renderViewer({ onNext: handleNext })
    await user.click(screen.getByLabelText("Next"))
    expect(handleNext).toHaveBeenCalled()
  })

  it("calls onPrev when prev button clicked", async () => {
    const user = userEvent.setup()
    const handlePrev = vi.fn()
    await renderViewer({ onPrev: handlePrev })
    await user.click(screen.getByLabelText("Previous"))
    expect(handlePrev).toHaveBeenCalled()
  })
})
