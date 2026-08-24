import { fireEvent, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, it, expect, vi } from "vitest"
import { StoryViewer } from "../StoryViewer"
import type { StoryItem } from "@/types/Story"
import { renderWithRouter } from "@/tests/helpers/renderWithRouter"

const motionMocks = vi.hoisted(() => ({ prefersReducedMotion: false }))

vi.mock("@/hooks/useMediaQuery", () => ({
  default: () => motionMocks.prefersReducedMotion,
}))

vi.mock("@/hooks/useFocusTrap", () => ({
  default: ({ initialFocus }: { initialFocus?: () => unknown }) => {
    initialFocus?.()
    return { current: null }
  },
}))

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
  I18nextProvider: ({ children }: { children?: React.ReactNode }) => <>{children}</>,
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

  it("renders nothing for an out-of-range active story index", async () => {
    const { container } = await renderViewer({ activeStoryIndex: 99 })
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

  it("renders cover images and resolves internal and external CTA links", async () => {
    const { rerender } = await renderViewer({
      stories: [
        { ...mockStories[0]!, cover_url: "https://cdn.example.com/story.jpg", cta_url: "/events" },
      ],
    })
    expect(screen.getByRole("img", { name: "Story 1" })).toHaveAttribute(
      "src",
      "https://cdn.example.com/story.jpg"
    )
    expect(screen.getByRole("link", { name: "stories.viewer.openLink" })).toHaveAttribute(
      "href",
      "/events"
    )

    rerender(
      <StoryViewer
        {...defaultProps}
        stories={[
          {
            ...mockStories[0]!,
            cover_url: "https://cdn.example.com/story.jpg",
            cta_url: "https://example.com/story",
          },
        ]}
      />
    )
    const externalLink = screen.getByRole("link", { name: "stories.viewer.openLink" })
    expect(externalLink).toHaveAttribute("href", "https://example.com/story")
    expect(externalLink).toHaveAttribute("target", "_blank")
    expect(externalLink).toHaveAttribute("rel", "noreferrer")

    rerender(
      <StoryViewer
        {...defaultProps}
        stories={[{ ...mockStories[0]!, cta_url: "mailto:stories@example.com" }]}
      />
    )
    expect(screen.getByRole("link", { name: "stories.viewer.openLink" })).toHaveAttribute(
      "href",
      "mailto:stories@example.com"
    )
  })

  it("uses an aria-label when the story has no title and ignores blank CTA urls", async () => {
    await renderViewer({
      stories: [
        {
          ...mockStories[0]!,
          title: "",
          short_text: "Story without a title",
          cta_url: "   ",
        },
      ],
    })
    expect(screen.getByRole("dialog", { name: "Story Viewer:" })).toBeInTheDocument()
    expect(screen.getByText("Story without a title")).toBeInTheDocument()
    expect(screen.queryByRole("link", { name: "stories.viewer.openLink" })).not.toBeInTheDocument()
  })

  it("assigns completed, active, and pending progress values", async () => {
    const stories = [
      mockStories[0]!,
      mockStories[1]!,
      { ...mockStories[1]!, id: "3", title: "Story 3" },
    ]
    await renderViewer({ stories, activeStoryIndex: 1, progress: 42 })
    const bars = screen.getAllByRole("progressbar")
    expect(bars.map((bar) => bar.getAttribute("aria-valuenow"))).toEqual(["100", "42", "0"])
  })

  it("pauses and resumes around pointer interactions and closes on backdrop", async () => {
    const onClose = vi.fn()
    const onPause = vi.fn()
    const onResume = vi.fn()
    await renderViewer({ onClose, onPause, onResume })
    const dialog = screen.getByRole("dialog")
    const stage = dialog.querySelector('[class*="aspect-9/16"]')!

    fireEvent.pointerDown(stage)
    fireEvent.pointerUp(stage)
    fireEvent.pointerCancel(stage)
    fireEvent.pointerLeave(stage)
    expect(onPause).toHaveBeenCalledTimes(1)
    expect(onResume).toHaveBeenCalledTimes(3)

    fireEvent.click(screen.getByRole("presentation"))
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it("uses reduced-motion progress settings", async () => {
    motionMocks.prefersReducedMotion = true
    await renderViewer({ progress: 35 })
    const bar = screen.getAllByRole("progressbar")[0]!
    expect(bar.firstElementChild?.className).toContain("motion-reduce:transition-none")
  })

  it("omits the copy overlay when a story has no title, text, or CTA", async () => {
    await renderViewer({
      stories: [{ ...mockStories[0]!, title: "", short_text: "", cta_url: null }],
    })
    const dialog = screen.getByRole("dialog", { name: "Story Viewer:" })
    expect(dialog.querySelector('[class*="bottom-0"]')).not.toBeInTheDocument()
  })
})
