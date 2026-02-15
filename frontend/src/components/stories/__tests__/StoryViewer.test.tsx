/* eslint-disable @typescript-eslint/no-explicit-any */
import { render, screen, fireEvent } from "@testing-library/react"
import { describe, it, expect, vi } from "vitest"
import { StoryViewer } from "../StoryViewer"
import type { StoryItem } from "@/types/Story"
import { BrowserRouter } from "react-router-dom"

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

  const renderViewer = (props = {}) =>
    render(
      <BrowserRouter>
        <StoryViewer {...defaultProps} {...props} />
      </BrowserRouter>
    )

  it("renders nothing when activeStoryIndex is null", () => {
    const { container } = renderViewer({ activeStoryIndex: null })
    expect(container).toBeEmptyDOMElement()
  })

  it("renders the active story", () => {
    renderViewer({ activeStoryIndex: 0 })
    expect(screen.getByRole("dialog", { name: /Story Viewer: Story 1/i })).toBeInTheDocument()
    expect(screen.getByRole("heading", { name: "Story 1" })).toBeInTheDocument()
  })

  it("calls onClose when close button clicked", () => {
    const handleClose = vi.fn()
    renderViewer({ onClose: handleClose })
    fireEvent.click(screen.getByLabelText("Close"))
    expect(handleClose).toHaveBeenCalled()
  })

  it("calls onNext when next button clicked", () => {
    const handleNext = vi.fn()
    renderViewer({ onNext: handleNext })
    fireEvent.click(screen.getByLabelText("Next"))
    expect(handleNext).toHaveBeenCalled()
  })

  it("calls onPrev when prev button clicked", () => {
    const handlePrev = vi.fn()
    renderViewer({ onPrev: handlePrev })
    fireEvent.click(screen.getByLabelText("Previous"))
    expect(handlePrev).toHaveBeenCalled()
  })
})
