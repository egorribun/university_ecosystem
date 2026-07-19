import { fireEvent, render, screen } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"
import { StoryList } from "../StoryList"
import type { StoryItem } from "@/types/Story"

// Mirror the existing StoryList.test.tsx i18n scaffold + expose the list aria-label key.
vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, options?: any) => {
      if (key === "aria.storyItem") return `Story: ${options?.title}`
      if (key === "aria.storiesList") return "Stories list"
      if (key === "stories.heading") return "Stories"
      return key
    },
  }),
}))

// A story WITH cover_url to drive the truthy <SmartImage> branch (lines 270-279)
// + the index===0 LCP eager/fetchpriority branch. cover_url is jsdom-safe — <img>
// never fetches in jsdom (no network), it just renders.
const storiesWithCover: StoryItem[] = [
  {
    id: "c1",
    title: "Cover Story",
    created_at: "2026-01-15T10:00:00.000Z",
    expires_at: "2026-01-16T10:00:00.000Z",
    published_at: "2026-01-15T10:00:00.000Z",
    is_active: true,
    cover_url: "https://picsum.photos/seed/story-cover/200/200",
    cover_url_optimized: null,
    short_text: "Cover short text",
  },
  {
    id: "c2",
    title: "Second Cover",
    created_at: "2026-01-15T10:00:00.000Z",
    expires_at: "2026-01-16T10:00:00.000Z",
    published_at: "2026-01-15T10:00:00.000Z",
    is_active: true,
    cover_url: null, // initials-span fallback branch (lines 281-287)
    cover_url_optimized: null,
    short_text: "", // empty short_text → tooltip falls back to title (line 234)
  },
]

/** Mutate jsdom layout props that default to 0 so updateScrollEdge can reach real branches. */
function setLayout(el: HTMLElement, scrollLeft: number, scrollWidth: number, clientWidth: number) {
  Object.defineProperty(el, "scrollLeft", { configurable: true, writable: true, value: scrollLeft })
  Object.defineProperty(el, "scrollWidth", { configurable: true, value: scrollWidth })
  Object.defineProperty(el, "clientWidth", { configurable: true, value: clientWidth })
}

function getList(): HTMLUListElement {
  return screen.getByRole("list") as HTMLUListElement
}

afterEach(() => {
  vi.clearAllMocks()
})

describe("StoryList branches", () => {
  it("renders the active-story boxShadow branch + cover image with LCP priority for index 0", () => {
    render(<StoryList stories={storiesWithCover} onOpenStory={vi.fn()} activeStoryId="c1" />)

    // Active story button carries data-active="true" (line 258) + the boxShadow style (262-266)
    const activeBtn = screen.getByLabelText("Story: Cover Story")
    expect(activeBtn).toHaveAttribute("data-active", "true")
    expect((activeBtn as HTMLElement).style.boxShadow).not.toBe("")

    // First story (index 0, cover_url set) → eager/fetchpriority LCP image (276-278)
    const firstImg = screen.getByAltText("Cover Story") as HTMLImageElement
    expect(firstImg).toHaveAttribute("loading", "eager")
    expect(firstImg).toHaveAttribute("fetchpriority", "high")

    // Inactive story button has no data-active attribute + no boxShadow (else branch line 267)
    const inactiveBtn = screen.getByLabelText("Story: Second Cover")
    expect(inactiveBtn).not.toHaveAttribute("data-active")
    expect((inactiveBtn as HTMLElement).style.boxShadow).toBe("")
  })

  it("renders the initials-span fallback when cover_url is null", () => {
    render(<StoryList stories={storiesWithCover} onOpenStory={vi.fn()} />)
    // Second story has no cover_url → initials span renders first 2 chars (line 285)
    expect(screen.getByText("Se")).toBeInTheDocument()
  })

  it("sets the start-edge fade mask when scrolled to start (lines 61, 165-169)", () => {
    render(<StoryList stories={storiesWithCover} onOpenStory={vi.fn()} />)
    const ul = getList()
    setLayout(ul, 0, 1000, 300) // maxScroll 700, scrollLeft 0 → atStart
    fireEvent.scroll(ul)
    expect(ul.style.maskImage).toContain("to right")
    expect(ul.style.maskImage).toContain("transparent 100%")
  })

  it("sets the middle-edge fade mask when scrolled into the middle (lines 66, 175-181)", () => {
    render(<StoryList stories={storiesWithCover} onOpenStory={vi.fn()} />)
    const ul = getList()
    setLayout(ul, 300, 1000, 300) // maxScroll 700, scrollLeft 300 → middle
    fireEvent.scroll(ul)
    expect(ul.style.maskImage).toContain("black 10%")
    expect(ul.style.maskImage).toContain("black 90%")
  })

  it("sets the end-edge fade mask when scrolled to the end (lines 65, 171-174)", () => {
    render(<StoryList stories={storiesWithCover} onOpenStory={vi.fn()} />)
    const ul = getList()
    setLayout(ul, 700, 1000, 300) // scrollLeft >= maxScroll-1 → atEnd
    fireEvent.scroll(ul)
    expect(ul.style.maskImage).toContain("to left")
  })

  it("keeps 'none' edge when content fits (maxScroll <= 1, lines 57-58)", () => {
    render(<StoryList stories={storiesWithCover} onOpenStory={vi.fn()} />)
    const ul = getList()
    setLayout(ul, 0, 300, 300) // maxScroll 0
    fireEvent.scroll(ul)
    expect(ul.style.maskImage).toBe("")
  })

  it("sets 'none' edge when both atStart and atEnd are true (line 63)", () => {
    render(<StoryList stories={storiesWithCover} onOpenStory={vi.fn()} />)
    const ul = getList()
    // maxScroll = 2 (>1 passes guard); scrollLeft 1 → atStart (1<=1) AND atEnd (1>=1) → both → "none"
    setLayout(ul, 1, 302, 300)
    fireEvent.scroll(ul)
    expect(ul.style.maskImage).toBe("")
  })

  it("performs a mouse drag-to-scroll past the threshold (lines 122-136)", () => {
    render(<StoryList stories={storiesWithCover} onOpenStory={vi.fn()} />)
    const ul = getList()
    Object.defineProperty(ul, "scrollLeft", { configurable: true, writable: true, value: 50 })

    fireEvent.pointerDown(ul, { pointerType: "mouse", button: 0, clientX: 100 })
    // dx = 40 - 100 = -60, |dx| > 5 → real drag → snap disabled + scrollLeft updated
    fireEvent.pointerMove(ul, { pointerType: "mouse", clientX: 40, pointerId: 1 })

    expect(ul.style.scrollSnapType).toBe("none")
    expect(ul).toHaveClass("cursor-grabbing")
    // scrollLeft = dragScrollLeft(50) - dx(-60) = 110
    expect((ul as HTMLElement).scrollLeft).toBe(110)

    fireEvent.pointerUp(ul, { pointerType: "mouse", pointerId: 1 })
    // snap re-enabled (cleared) + drag flag off
    expect(ul.style.scrollSnapType).toBe("")
    expect(ul).toHaveClass("cursor-grab")
  })

  it("ignores a press that never exceeds the drag threshold (line 125 false branch)", () => {
    render(<StoryList stories={storiesWithCover} onOpenStory={vi.fn()} />)
    const ul = getList()
    fireEvent.pointerDown(ul, { pointerType: "mouse", button: 0, clientX: 100 })
    // dx = 3 → below DRAG_THRESHOLD (5) → no snap change, stays grab cursor
    fireEvent.pointerMove(ul, { pointerType: "mouse", clientX: 103, pointerId: 1 })
    expect(ul.style.scrollSnapType).toBe("")
    expect(ul).toHaveClass("cursor-grab")
  })

  it("ignores non-mouse pointerdown (line 109 early return — touch)", () => {
    render(<StoryList stories={storiesWithCover} onOpenStory={vi.fn()} />)
    const ul = getList()
    fireEvent.pointerDown(ul, { pointerType: "touch", button: 0, clientX: 100 })
    // isPressedRef never set → move is a no-op (line 121 early return)
    fireEvent.pointerMove(ul, { pointerType: "touch", clientX: 40, pointerId: 1 })
    expect(ul.style.scrollSnapType).toBe("")
  })

  it("ignores a non-primary (right) mouse button on pointerdown (line 109 button branch)", () => {
    render(<StoryList stories={storiesWithCover} onOpenStory={vi.fn()} />)
    const ul = getList()
    fireEvent.pointerDown(ul, { pointerType: "mouse", button: 2, clientX: 100 })
    fireEvent.pointerMove(ul, { pointerType: "mouse", clientX: 40, pointerId: 1 })
    expect(ul.style.scrollSnapType).toBe("")
  })

  it("ignores a pointermove with no active press (line 121 early return)", () => {
    render(<StoryList stories={storiesWithCover} onOpenStory={vi.fn()} />)
    const ul = getList()
    // pointerMove without a preceding pointerDown → isPressedRef false → early return
    fireEvent.pointerMove(ul, { pointerType: "mouse", clientX: 40, pointerId: 1 })
    expect(ul.style.scrollSnapType).toBe("")
  })

  it("swallows the click that immediately follows a drag (lines 152-155)", () => {
    const handleOpen = vi.fn()
    render(<StoryList stories={storiesWithCover} onOpenStory={handleOpen} />)
    const ul = getList()
    Object.defineProperty(ul, "scrollLeft", { configurable: true, writable: true, value: 0 })
    const storyBtn = screen.getByLabelText("Story: Cover Story")

    // Drag past threshold → hasDragged.current = true. The trailing native `click`
    // (NOT a fresh pointerdown) is what production swallows — fireEvent.click avoids
    // re-running handlePointerDown the way a full userEvent pointer sequence would.
    fireEvent.pointerDown(ul, { pointerType: "mouse", button: 0, clientX: 100 })
    fireEvent.pointerMove(ul, { pointerType: "mouse", clientX: 30, pointerId: 1 })
    fireEvent.pointerUp(ul, { pointerType: "mouse", pointerId: 1 })

    fireEvent.click(storyBtn)
    expect(handleOpen).not.toHaveBeenCalled()

    // hasDragged was reset to false → a FOLLOWING click opens the story normally
    fireEvent.click(storyBtn)
    expect(handleOpen).toHaveBeenCalledWith(storiesWithCover[0]!, 0)
  })

  it("fires onPrefetch from focus-capture on the wrapper (lines around 190-191)", () => {
    const handlePrefetch = vi.fn()
    const { container } = render(
      <StoryList stories={storiesWithCover} onOpenStory={vi.fn()} onPrefetch={handlePrefetch} />
    )
    const wrapper = container.querySelector("[data-fade]") as HTMLElement
    fireEvent.focus(wrapper)
    expect(handlePrefetch).toHaveBeenCalled()
  })

  it("renders nothing when not loading and there are no stories (line 161)", () => {
    const { container } = render(<StoryList stories={[]} loading={false} onOpenStory={vi.fn()} />)
    expect(container).toBeEmptyDOMElement()
  })
})
