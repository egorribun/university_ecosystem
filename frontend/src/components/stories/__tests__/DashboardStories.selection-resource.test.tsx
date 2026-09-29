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

const stories: StoryItem[] = ["One", "Two", "Three"].map((title) => ({
  id: title.toLowerCase(),
  title,
  short_text: title,
  created_at: "2026-09-01T00:00:00Z",
  published_at: "2026-09-01T00:00:00Z",
  expires_at: "2026-10-01T00:00:00Z",
  is_active: true,
}))

let now = 5_000
let nextFrameId = 0
const frames = new Map<number, FrameRequestCallback>()

function renderStories() {
  const onStoryOpen = vi.fn()
  const view = render(
    <StrictMode>
      <AppShellProvider>
        <DashboardStories stories={stories} onStoryOpen={onStoryOpen} />
      </AppShellProvider>
    </StrictMode>
  )
  return { ...view, onStoryOpen }
}

function click(name: string) {
  const errors = collectWindowErrors(() => {
    fireEvent.click(screen.getByRole("button", { name }))
  })
  expect(errors).toEqual([])
}

function expectSelected(title: string | null) {
  for (const story of stories) {
    const circle = screen.getByRole("button", { name: `Story: ${story.title}` })
    if (story.title === title) expect(circle).toHaveAttribute("data-active", "true")
    else expect(circle).not.toHaveAttribute("data-active")
  }
}

describe("DashboardStories real-child selection and resource boundaries", () => {
  beforeEach(() => {
    now = 5_000
    nextFrameId = 0
    frames.clear()
    vi.spyOn(performance, "now").mockImplementation(() => now)
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
      const id = nextFrameId
      nextFrameId = (nextFrameId + 1) >>> 0
      frames.set(id, callback)
      return id
    })
    vi.spyOn(window, "cancelAnimationFrame").mockImplementation((id) => {
      // Match the browser's unsigned-long conversion: null cancels handle zero.
      frames.delete(Number(id) >>> 0)
    })
  })

  afterEach(() => {
    cleanup()
    vi.restoreAllMocks()
  })

  it("keeps the real circle selection synchronized with navigation, close and reopen", () => {
    const { onStoryOpen } = renderStories()
    expectSelected(null)
    click("Story: One")
    expect(screen.getByRole("dialog", { name: "One" })).toBeInTheDocument()
    expectSelected("One")
    click("stories.viewer.aria.next")
    expect(screen.getByRole("dialog", { name: "Two" })).toBeInTheDocument()
    expectSelected("Two")
    click("stories.viewer.aria.prev")
    expect(screen.getByRole("dialog", { name: "One" })).toBeInTheDocument()
    expectSelected("One")
    click("stories.viewer.aria.close")
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
    expectSelected(null)
    click("Story: Three")
    expect(screen.getByRole("dialog", { name: "Three" })).toBeInTheDocument()
    expectSelected("Three")
    expect(onStoryOpen.mock.calls).toEqual([[stories[0]], [stories[1]], [stories[0]], [stories[2]]])
  })

  it("preserves another owner's zero frame after the last story completes", () => {
    // Model unsigned handle wrap: playback acquires the last handle first,
    // then another owner acquires zero, preserving registration order.
    nextFrameId = 0xffff_ffff
    const { onStoryOpen, unmount } = renderStories()
    click("Story: Three")
    expect(screen.getByRole("dialog", { name: "Three" })).toBeInTheDocument()
    expect(frames.size).toBe(1)
    const outsideCallback = vi.fn()
    const outsideFrame = window.requestAnimationFrame(outsideCallback)
    expect(outsideFrame).toBe(0)
    now = 11_500
    // Browser frame processing snapshots callbacks in registration order and
    // skips entries canceled before their turn; do not run foreign work first.
    const pendingFrame = [...frames.entries()]
    for (const [id, callback] of pendingFrame) {
      if (!frames.has(id)) continue
      frames.delete(id)
      act(() => callback(now))
    }
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
    expect(onStoryOpen).toHaveBeenCalledExactlyOnceWith(stories[2])
    expect(outsideCallback).toHaveBeenCalledExactlyOnceWith(now)
    expect(frames.size).toBe(0)
    unmount()
    expect(frames.size).toBe(0)
  })
})
