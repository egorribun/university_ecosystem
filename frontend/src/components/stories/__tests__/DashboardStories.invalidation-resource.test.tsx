import { StrictMode } from "react"
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { AppShellProvider } from "@/contexts/AppShellContext"
import { collectWindowErrors } from "@/tests/helpers/windowErrors"
import type { StoryItem } from "@/types/Story"
import DashboardStories from "../DashboardStories"

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, options?: { title?: string }) =>
      key === "aria.storyItem" ? `Story: ${options?.title}` : key,
  }),
}))

const stories: StoryItem[] = ["One", "Two"].map((title) => ({
  id: title.toLowerCase(),
  title,
  short_text: title,
  created_at: "2026-09-01T00:00:00Z",
  published_at: "2026-09-01T00:00:00Z",
  expires_at: "2026-10-01T00:00:00Z",
  is_active: true,
}))

const frames = new Map<number, FrameRequestCallback>()
let nextFrameId = 0

describe("DashboardStories invalidated playback acquisition", () => {
  beforeEach(() => {
    nextFrameId = 0
    frames.clear()
    vi.spyOn(performance, "now").mockReturnValue(5_000)
    vi.spyOn(document, "visibilityState", "get").mockReturnValue("visible")
    vi.spyOn(window, "matchMedia").mockImplementation(
      (query) =>
        ({
          matches: false,
          media: query,
          onchange: null,
          addEventListener: vi.fn(),
          removeEventListener: vi.fn(),
          addListener: vi.fn(),
          removeListener: vi.fn(),
          dispatchEvent: vi.fn(),
        }) as MediaQueryList
    )
    vi.spyOn(window, "requestAnimationFrame").mockImplementation((callback) => {
      const id = nextFrameId++
      frames.set(id, callback)
      return id
    })
    vi.spyOn(window, "cancelAnimationFrame").mockImplementation((id) => {
      frames.delete(Number(id) >>> 0)
    })
  })

  afterEach(() => {
    cleanup()
    vi.restoreAllMocks()
  })

  it.each([
    { label: "shorter", remaining: stories.slice(0, 1) },
    { label: "empty", remaining: [] },
  ])("does not acquire playback for a $label collection with no active story", ({ remaining }) => {
    const outsideCallback = vi.fn()
    const outsideFrame = window.requestAnimationFrame(outsideCallback)
    const onStoryOpen = vi.fn()
    const ui = (collection: StoryItem[]) => (
      <StrictMode>
        <AppShellProvider>
          <DashboardStories stories={collection} onStoryOpen={onStoryOpen} />
        </AppShellProvider>
      </StrictMode>
    )
    const { rerender, unmount } = render(ui(stories))
    // Only overlay registration is used; no app-shell scroll/restore request.
    expect([...frames.keys()]).toEqual([outsideFrame])
    expect(
      collectWindowErrors(() => {
        fireEvent.click(screen.getByRole("button", { name: "Story: Two" }))
      })
    ).toEqual([])
    expect(screen.getByRole("dialog", { name: "Two" })).toBeInTheDocument()
    expect(frames.size).toBe(2)
    const [playbackFrame, stalePlayback] = [...frames.entries()].find(
      ([id]) => id !== outsideFrame
    )!

    vi.mocked(window.requestAnimationFrame).mockClear()
    vi.mocked(window.cancelAnimationFrame).mockClear()
    rerender(ui(remaining))

    // Allocation history matters: scheduling and immediately cancelling an
    // invalid story's frame would still leave the settled queue looking empty.
    expect(window.requestAnimationFrame).not.toHaveBeenCalled()
    expect(window.cancelAnimationFrame).toHaveBeenCalledWith(playbackFrame)
    expect(window.cancelAnimationFrame).not.toHaveBeenCalledWith(outsideFrame)
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
    for (const item of remaining) {
      expect(screen.getByRole("button", { name: `Story: ${item.title}` })).not.toHaveAttribute(
        "data-active"
      )
    }
    expect([...frames.keys()]).toEqual([outsideFrame])

    act(() => stalePlayback(11_500))
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
    expect(onStoryOpen).toHaveBeenCalledExactlyOnceWith(stories[1])
    expect(window.requestAnimationFrame).not.toHaveBeenCalled()
    expect([...frames.keys()]).toEqual([outsideFrame])
    unmount()
    expect([...frames.keys()]).toEqual([outsideFrame])
    frames.delete(outsideFrame)
    act(() => outsideCallback(11_500))
    expect(outsideCallback).toHaveBeenCalledExactlyOnceWith(11_500)
  })
})
