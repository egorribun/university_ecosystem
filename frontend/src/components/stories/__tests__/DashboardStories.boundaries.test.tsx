import { act, cleanup, fireEvent, render, screen } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import type { StoryItem } from "@/types/Story"

// Keep Dashboard's collection, media subscription, navigation and clock real.
// Child render adapters expose its public props without duplicating viewer UI tests.
vi.mock("../StoryList", () => ({
  StoryList: ({
    stories,
    loading,
    onOpenStory,
    onPrefetch,
  }: {
    stories: StoryItem[]
    loading: boolean
    onOpenStory: (story: StoryItem, index: number) => void
    onPrefetch?: () => void
  }) => (
    <section aria-label="Available stories" aria-busy={loading}>
      <button onClick={onPrefetch}>Prefetch stories</button>
      {stories.map((story, index) => (
        <button key={story.id} onClick={() => onOpenStory(story, index)}>
          Open {story.title}
        </button>
      ))}
    </section>
  ),
}))
vi.mock("../StoryViewer", () => ({
  StoryViewer: ({
    stories,
    activeStoryIndex,
    progress,
    onPause,
    onResume,
    onClose,
    onNext,
  }: {
    stories: StoryItem[]
    activeStoryIndex: number | null
    progress: number
    onPause: () => void
    onResume: () => void
    onClose: () => void
    onNext: () => void
  }) =>
    activeStoryIndex === null ? null : (
      <section aria-label="Playback">
        <h2>{stories[activeStoryIndex]?.title}</h2>
        <output aria-label="Playback progress">{progress}</output>
        <button onClick={onPause}>Pause</button>
        <button onClick={onResume}>Resume</button>
        <button onClick={onClose}>Close</button>
        <button onClick={onNext}>Next</button>
      </section>
    ),
}))

import DashboardStories from "../DashboardStories"

const story = (id: string): StoryItem => ({
  id,
  title: id,
  short_text: id,
  published_at: "2026-09-27T12:00:00Z",
  expires_at: "2026-09-28T12:00:00Z",
  created_at: "2026-09-27T12:00:00Z",
  is_active: true,
})
const stories = [story("One"), story("Two"), story("Three")]
const click = (name: string) => fireEvent.click(screen.getByRole("button", { name }))
const progress = () => Number(screen.getByLabelText("Playback progress").textContent)
const key = (value: string) => {
  const event = new KeyboardEvent("keydown", { key: value, cancelable: true })
  act(() => window.dispatchEvent(event))
  return event
}

describe("DashboardStories collection and input boundaries", () => {
  let now = 0
  let hidden = false
  let reduced = false
  let nextFrame = 0
  let frames: Map<number, FrameRequestCallback>
  let mediaListeners: Set<(event: MediaQueryListEvent) => void>

  beforeEach(() => {
    now = 0
    hidden = false
    reduced = false
    nextFrame = 0
    frames = new Map()
    mediaListeners = new Set()
    vi.spyOn(performance, "now").mockImplementation(() => now)
    vi.spyOn(document, "visibilityState", "get").mockImplementation(() =>
      hidden ? "hidden" : "visible"
    )
    vi.spyOn(window, "requestAnimationFrame").mockImplementation((callback) => {
      const id = nextFrame++
      frames.set(id, callback)
      return id
    })
    vi.spyOn(window, "cancelAnimationFrame").mockImplementation((id) => {
      frames.delete(id)
    })
    vi.spyOn(window, "matchMedia").mockImplementation(
      (query) =>
        ({
          get matches() {
            return query === "(prefers-reduced-motion: reduce)" && reduced
          },
          media: query,
          onchange: null,
          addEventListener: (_type: string, listener: (event: MediaQueryListEvent) => void) => {
            mediaListeners.add(listener)
          },
          removeEventListener: (_type: string, listener: (event: MediaQueryListEvent) => void) => {
            mediaListeners.delete(listener)
          },
          addListener: () => undefined,
          removeListener: () => undefined,
          dispatchEvent: () => true,
        }) as MediaQueryList
    )
  })

  afterEach(() => {
    cleanup()
    vi.restoreAllMocks()
  })

  const tick = (timestamp: number) => {
    const entry = frames.entries().next().value
    expect(entry, "an owned animation frame must exist").toBeDefined()
    const [id, callback] = entry!
    now = timestamp
    frames.delete(id)
    act(() => callback(timestamp))
  }
  const visibility = (value: boolean, timestamp: number) => {
    hidden = value
    now = timestamp
    act(() => document.dispatchEvent(new Event("visibilitychange")))
  }

  it("defaults to twelve stories and recomputes the visible collection when its limit changes", () => {
    const collection = Array.from({ length: 15 }, (_, index) => story(`Story ${index + 1}`))
    const { rerender } = render(<DashboardStories stories={collection} />)
    expect(screen.getAllByRole("button", { name: /^Open / })).toHaveLength(12)
    expect(screen.getByRole("button", { name: "Open Story 12" })).toBeInTheDocument()
    expect(screen.queryByRole("button", { name: "Open Story 13" })).not.toBeInTheDocument()
    rerender(<DashboardStories stories={collection} maxVisibleStories={3} />)
    expect(screen.getAllByRole("button", { name: /^Open / })).toHaveLength(3)
    expect(screen.queryByRole("button", { name: "Open Story 4" })).not.toBeInTheDocument()
  })

  it.each([0, -4])("keeps the first story selectable for nonpositive limit %s", (limit) => {
    const onStoryOpen = vi.fn()
    render(
      <DashboardStories stories={stories} maxVisibleStories={limit} onStoryOpen={onStoryOpen} />
    )
    expect(screen.getAllByRole("button", { name: /^Open / })).toHaveLength(1)
    click("Open One")
    expect(onStoryOpen).toHaveBeenCalledExactlyOnceWith(stories[0])
    expect(screen.getByRole("heading", { name: "One" })).toBeInTheDocument()
  })

  it("defaults loading to false and forwards explicit loading and the latest prefetch callback", () => {
    const first = vi.fn()
    const latest = vi.fn()
    const { rerender } = render(<DashboardStories stories={stories} onPrefetch={first} />)
    expect(screen.getByRole("region", { name: "Available stories" })).toHaveAttribute(
      "aria-busy",
      "false"
    )
    click("Prefetch stories")
    expect(first).toHaveBeenCalledOnce()
    rerender(<DashboardStories stories={stories} loading onPrefetch={latest} />)
    expect(screen.getByRole("region", { name: "Available stories" })).toHaveAttribute(
      "aria-busy",
      "true"
    )
    click("Prefetch stories")
    expect(latest).toHaveBeenCalledOnce()
    expect(first).toHaveBeenCalledOnce()
  })

  it("honors the real reduced-motion query at mount and its change subscription", () => {
    reduced = true
    const { unmount } = render(<DashboardStories stories={stories} />)
    click("Open One")
    expect(frames.size).toBe(0)
    expect(progress()).toBe(0)
    reduced = false
    act(() => {
      for (const listener of mediaListeners) listener({ matches: false } as MediaQueryListEvent)
    })
    expect(frames.size).toBe(1)
    tick(650)
    expect(progress()).toBeCloseTo(10)
    reduced = true
    act(() => {
      for (const listener of mediaListeners) listener({ matches: true } as MediaQueryListEvent)
    })
    expect(frames.size).toBe(0)
    click("Next")
    expect(screen.getByRole("heading", { name: "Two" })).toBeInTheDocument()
    expect(frames.size).toBe(0)
    unmount()
    expect(mediaListeners.size).toBe(0)
  })

  it("retains the visibility pause when interaction resumes while the document is still hidden", () => {
    render(<DashboardStories stories={stories} />)
    click("Open One")
    tick(1300)
    visibility(true, 1300)
    now = 2600
    click("Pause")
    now = 9000
    click("Resume")
    expect(frames.size).toBe(0)
    expect(progress()).toBeCloseTo(20)
    visibility(false, 10000)
    tick(10650)
    expect(progress()).toBeCloseTo(30)
  })

  it("preserves elapsed playback for same-ID content updates and navigates using the latest collection and callback", () => {
    const initialOpen = vi.fn()
    const latestOpen = vi.fn()
    const { rerender } = render(<DashboardStories stories={stories} onStoryOpen={initialOpen} />)
    click("Open One")
    tick(1300)
    const updated = [{ ...stories[0]!, title: "One updated" }, story("Two updated")]
    rerender(<DashboardStories stories={updated} onStoryOpen={latestOpen} />)
    expect(screen.getByRole("heading", { name: "One updated" })).toBeInTheDocument()
    tick(1950)
    expect(progress()).toBeCloseTo(30)
    expect(key("ArrowRight").defaultPrevented).toBe(true)
    expect(screen.getByRole("heading", { name: "Two updated" })).toBeInTheDocument()
    expect(latestOpen).toHaveBeenCalledExactlyOnceWith(updated[1])
    expect(initialOpen).toHaveBeenCalledTimes(1)
  })

  it("closes the viewer when a changed visibility limit excludes its active story", () => {
    const { rerender } = render(<DashboardStories stories={stories} />)
    click("Open Three")
    rerender(<DashboardStories stories={stories} maxVisibleStories={2} />)
    expect(screen.queryByRole("region", { name: "Playback" })).not.toBeInTheDocument()
    expect(frames.size).toBe(0)
    expect(key("ArrowRight").defaultPrevented).toBe(false)
  })

  it("prevents defaults only for active shortcuts and removes listeners after close, reopen and unmount", () => {
    const onStoryOpen = vi.fn()
    const { unmount } = render(<DashboardStories stories={stories} onStoryOpen={onStoryOpen} />)
    expect(key("ArrowRight").defaultPrevented).toBe(false)
    click("Open One")
    expect(key("Home").defaultPrevented).toBe(false)
    expect(key("ArrowRight").defaultPrevented).toBe(true)
    expect(screen.getByRole("heading", { name: "Two" })).toBeInTheDocument()
    expect(key("ArrowLeft").defaultPrevented).toBe(true)
    expect(screen.getByRole("heading", { name: "One" })).toBeInTheDocument()
    expect(key("Escape").defaultPrevented).toBe(true)
    expect(screen.queryByRole("region", { name: "Playback" })).not.toBeInTheDocument()
    expect(key("ArrowRight").defaultPrevented).toBe(false)
    click("Open Two")
    expect(key("ArrowRight").defaultPrevented).toBe(true)
    expect(screen.getByRole("heading", { name: "Three" })).toBeInTheDocument()
    expect(onStoryOpen).toHaveBeenCalledTimes(5)
    unmount()
    expect(key("Escape").defaultPrevented).toBe(false)
    expect(key("ArrowRight").defaultPrevented).toBe(false)
    expect(onStoryOpen).toHaveBeenCalledTimes(5)
  })
})
