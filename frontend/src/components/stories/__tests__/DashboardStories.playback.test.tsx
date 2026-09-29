import { act, cleanup, fireEvent, render, screen } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import type { StoryItem } from "@/types/Story"

const media = vi.hoisted(() => ({ reduced: false }))
vi.mock("@/hooks/useMediaQuery", () => ({ default: () => media.reduced }))
vi.mock("../StoryList", () => ({
  StoryList: ({
    stories,
    onOpenStory,
  }: {
    stories: StoryItem[]
    onOpenStory: (story: StoryItem, index: number) => void
  }) => (
    <>
      {stories.map((story, index) => (
        <button key={story.id} onClick={() => onOpenStory(story, index)}>
          Open {story.title}
        </button>
      ))}
    </>
  ),
}))
vi.mock("../StoryViewer", () => ({
  StoryViewer: ({
    stories,
    activeStoryIndex,
    progress,
    onClose,
    onPause,
    onResume,
    onNext,
    onPrev,
  }: {
    stories: StoryItem[]
    activeStoryIndex: number | null
    progress: number
    onClose: () => void
    onPause: () => void
    onResume: () => void
    onNext: () => void
    onPrev: () => void
  }) =>
    activeStoryIndex === null ? null : (
      <section aria-label="Playback">
        <h2>{stories[activeStoryIndex]?.title ?? "Missing story"}</h2>
        <output aria-label="Playback progress">{progress}</output>
        <button onClick={onClose}>Close</button>
        <button onClick={onPause}>Pause</button>
        <button onClick={onResume}>Resume</button>
        <button onClick={onNext}>Next</button>
        <button onClick={onPrev}>Previous</button>
      </section>
    ),
}))

import DashboardStories from "../DashboardStories"

const stories = [
  { id: "one", title: "One" },
  { id: "two", title: "Two" },
] as StoryItem[]

describe("DashboardStories playback ownership", () => {
  let now = 0
  let hidden = false
  let nextFrame = 0
  let frames: Map<number, FrameRequestCallback>
  let cancelFrame: ReturnType<typeof vi.spyOn>

  beforeEach(() => {
    now = 0
    hidden = false
    nextFrame = 0
    media.reduced = false
    frames = new Map()
    vi.spyOn(performance, "now").mockImplementation(() => now)
    vi.spyOn(document, "visibilityState", "get").mockImplementation(() =>
      hidden ? "hidden" : "visible"
    )
    vi.spyOn(window, "requestAnimationFrame").mockImplementation((callback) => {
      const id = nextFrame++
      frames.set(id, callback)
      return id
    })
    cancelFrame = vi.spyOn(window, "cancelAnimationFrame").mockImplementation((id) => {
      frames.delete(id)
    })
  })

  afterEach(() => {
    cleanup()
    vi.restoreAllMocks()
  })

  const click = (name: string) => fireEvent.click(screen.getByRole("button", { name }))
  const tick = (timestamp: number) => {
    now = timestamp
    const [id, callback] = frames.entries().next().value!
    frames.delete(id)
    act(() => callback(timestamp))
  }
  const visibility = (isHidden: boolean, timestamp: number) => {
    hidden = isHidden
    now = timestamp
    act(() => document.dispatchEvent(new Event("visibilitychange")))
  }

  it("owns no automatic frames while closed or when reduced motion is requested", () => {
    const { rerender } = render(<DashboardStories stories={stories} />)
    expect(frames.size).toBe(0)
    media.reduced = true
    rerender(<DashboardStories stories={stories} />)
    click("Open One")
    expect(screen.getByRole("heading", { name: "One" })).toBeInTheDocument()
    expect(frames.size).toBe(0)
    click("Next")
    expect(screen.getByRole("heading", { name: "Two" })).toBeInTheDocument()
    expect(frames.size).toBe(0)
  })

  it.each(["close", "unmount"])("cancels a valid zero frame ID on %s", (end) => {
    const { unmount } = render(<DashboardStories stories={stories} />)
    click("Open One")
    expect(frames.has(0)).toBe(true)
    if (end === "close") click("Close")
    else unmount()
    expect(cancelFrame).toHaveBeenCalledWith(0)
    expect(frames.size).toBe(0)
  })

  it("ignores a stale completed frame after the viewer closes", () => {
    const onStoryOpen = vi.fn()
    render(<DashboardStories stories={stories} onStoryOpen={onStoryOpen} />)
    click("Open One")
    const staleFrame = frames.get(0)!
    click("Close")
    now = 7_000
    act(() => staleFrame(now))
    expect(screen.queryByRole("region", { name: "Playback" })).not.toBeInTheDocument()
    expect(onStoryOpen).toHaveBeenCalledTimes(1)
    expect(frames.size).toBe(0)
  })

  it("releases playback when the open story disappears from a shorter collection", () => {
    const { rerender } = render(<DashboardStories stories={stories} />)
    click("Open Two")
    rerender(<DashboardStories stories={[stories[0]!]} />)
    expect(screen.queryByRole("region", { name: "Playback" })).not.toBeInTheDocument()
    expect(frames.size).toBe(0)
  })

  it("restarts elapsed playback when the story at the active index is replaced", () => {
    const { rerender } = render(<DashboardStories stories={stories} />)
    click("Open One")
    tick(3_250)
    expect(screen.getByLabelText("Playback progress")).toHaveTextContent("50")
    rerender(
      <DashboardStories stories={[{ ...stories[0]!, id: "new", title: "New" }, stories[1]!]} />
    )
    expect(screen.getByRole("heading", { name: "New" })).toBeInTheDocument()
    expect(Number(screen.getByLabelText("Playback progress").textContent)).toBe(0)
    tick(4_550)
    expect(Number(screen.getByLabelText("Playback progress").textContent)).toBeCloseTo(20)
  })

  it("resumes only after both visibility and interaction pauses are released", () => {
    render(<DashboardStories stories={stories} />)
    click("Open One")
    tick(1_300)
    click("Pause")
    visibility(true, 2_000)
    visibility(false, 9_000)
    expect(frames.size).toBe(0)
    click("Resume")
    tick(10_300)
    expect(Number(screen.getByLabelText("Playback progress").textContent)).toBeCloseTo(40)
  })

  it.each(["visible", "interaction paused", "hidden"])(
    "restarts the first story's clock on Previous while %s",
    (state) => {
      render(<DashboardStories stories={stories} />)
      click("Open One")
      tick(3_250)
      expect(Number(screen.getByLabelText("Playback progress").textContent)).toBe(50)
      if (state === "interaction paused") click("Pause")
      if (state === "hidden") visibility(true, 3_250)

      click("Previous")
      expect(Number(screen.getByLabelText("Playback progress").textContent)).toBe(0)
      expect(screen.getByRole("heading", { name: "One" })).toBeInTheDocument()
      if (state === "visible") {
        tick(3_900)
      } else {
        expect(frames.size).toBe(0)
        now = 9_000
        if (state === "interaction paused") click("Resume")
        else visibility(false, now)
        tick(9_650)
      }
      expect(Number(screen.getByLabelText("Playback progress").textContent)).toBeCloseTo(10)
    }
  )

  it("keeps a reopened viewer's playback separate from a queued frame of its closed predecessor", () => {
    const onStoryOpen = vi.fn()
    render(<DashboardStories stories={stories} onStoryOpen={onStoryOpen} />)
    click("Open One")
    const staleFrame = frames.get(0)!
    click("Close")
    now = 7_000
    click("Open Two")
    act(() => staleFrame(now))
    expect(screen.getByRole("heading", { name: "Two" })).toBeInTheDocument()
    expect(Number(screen.getByLabelText("Playback progress").textContent)).toBe(0)
    expect(onStoryOpen).toHaveBeenCalledTimes(2)
    expect(frames.size).toBe(1)
    tick(7_650)
    expect(Number(screen.getByLabelText("Playback progress").textContent)).toBeCloseTo(10)
  })

  it("ignores a queued frame owned by a story replaced in the collection", () => {
    const { rerender } = render(<DashboardStories stories={stories} />)
    click("Open One")
    tick(3_250)
    const staleFrame = frames.values().next().value!
    rerender(
      <DashboardStories stories={[{ ...stories[0]!, id: "new", title: "New" }, stories[1]!]} />
    )
    act(() => staleFrame(now))
    expect(screen.getByRole("heading", { name: "New" })).toBeInTheDocument()
    expect(Number(screen.getByLabelText("Playback progress").textContent)).toBe(0)
    expect(frames.size).toBe(1)
    tick(3_900)
    expect(Number(screen.getByLabelText("Playback progress").textContent)).toBeCloseTo(10)
  })

  it("leaves the first story in place and closes after advancing past the last story", () => {
    const onStoryOpen = vi.fn()
    render(<DashboardStories stories={stories} onStoryOpen={onStoryOpen} />)
    click("Open One")
    click("Previous")
    expect(screen.getByRole("heading", { name: "One" })).toBeInTheDocument()
    expect(onStoryOpen).toHaveBeenCalledTimes(1)
    click("Next")
    expect(screen.getByRole("heading", { name: "Two" })).toBeInTheDocument()
    click("Next")
    expect(screen.queryByRole("region", { name: "Playback" })).not.toBeInTheDocument()
    expect(onStoryOpen).toHaveBeenCalledTimes(2)
    expect(frames.size).toBe(0)
  })
})
