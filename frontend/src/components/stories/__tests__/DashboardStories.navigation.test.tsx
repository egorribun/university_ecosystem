import { act, cleanup, fireEvent, render, screen } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { AppShellProvider } from "@/contexts/AppShellContext"
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

let now = 0
let nextFrameId = 0
const frames = new Map<number, FrameRequestCallback>()

function renderStories(onStoryOpen = vi.fn()) {
  const ui = (collection: StoryItem[]) => (
    <AppShellProvider>
      <DashboardStories stories={collection} onStoryOpen={onStoryOpen} />
    </AppShellProvider>
  )
  const view = render(ui(stories))
  return {
    ...view,
    onStoryOpen,
    replaceStories: (collection: StoryItem[]) => view.rerender(ui(collection)),
  }
}

function openLastStory() {
  fireEvent.click(screen.getByRole("button", { name: "Story: Three" }))
  expect(screen.getByRole("dialog", { name: "Three" })).toBeInTheDocument()
}

function pressKey(key: string) {
  const event = new KeyboardEvent("keydown", { key, bubbles: true, cancelable: true })
  act(() => window.dispatchEvent(event))
  return event
}

describe("DashboardStories real-viewer navigation boundaries", () => {
  beforeEach(() => {
    now = 0
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
      const id = nextFrameId++
      frames.set(id, callback)
      return id
    })
    vi.spyOn(window, "cancelAnimationFrame").mockImplementation((id) => {
      frames.delete(id)
    })
  })

  afterEach(() => {
    cleanup()
    vi.restoreAllMocks()
  })

  it("closes after Next on the final real viewer without reopening another story", () => {
    const { onStoryOpen } = renderStories()
    openLastStory()
    fireEvent.click(screen.getByRole("button", { name: "stories.viewer.aria.next" }))
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
    expect(onStoryOpen).toHaveBeenCalledExactlyOnceWith(stories[2])
    expect(frames.size).toBe(0)
  })

  it("closes at the final keyboard boundary and releases shortcut ownership", () => {
    const { onStoryOpen } = renderStories()
    openLastStory()
    expect(pressKey("ArrowRight").defaultPrevented).toBe(true)
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
    expect(pressKey("ArrowLeft").defaultPrevented).toBe(false)
    expect(onStoryOpen).toHaveBeenCalledExactlyOnceWith(stories[2])
    expect(frames.size).toBe(0)
  })

  it("closes when the final story completes and ignores its captured stale frame", () => {
    const { onStoryOpen } = renderStories()
    openLastStory()
    expect(frames.size).toBe(1)
    const [id, callback] = [...frames.entries()][0]!
    frames.delete(id)
    now = 6_500
    act(() => callback(now))
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
    expect(frames.size).toBe(0)
    now = 13_000
    act(() => callback(now))
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
    expect(onStoryOpen).toHaveBeenCalledExactlyOnceWith(stories[2])
    expect(frames.size).toBe(0)
  })

  it.each([
    { label: "empty", collection: [] },
    { label: "shorter", collection: stories.slice(0, 1) },
  ])("closes an invalidated real viewer when its collection becomes $label", ({ collection }) => {
    const { replaceStories, onStoryOpen } = renderStories()
    openLastStory()
    replaceStories(collection)
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
    expect(pressKey("ArrowLeft").defaultPrevented).toBe(false)
    expect(onStoryOpen).toHaveBeenCalledExactlyOnceWith(stories[2])
    expect(frames.size).toBe(0)
  })

  it("releases keyboard and frame ownership when an open real viewer unmounts", () => {
    const { unmount, onStoryOpen } = renderStories()
    openLastStory()
    unmount()
    expect(pressKey("ArrowRight").defaultPrevented).toBe(false)
    expect(onStoryOpen).toHaveBeenCalledExactlyOnceWith(stories[2])
    expect(frames.size).toBe(0)
  })
})
