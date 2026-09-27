import { StrictMode } from "react"
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

const story: StoryItem = {
  id: "clock-story",
  title: "Clock story",
  short_text: "A story opened after the application has already been running",
  created_at: "2026-09-01T00:00:00Z",
  published_at: "2026-09-01T00:00:00Z",
  expires_at: "2026-10-01T00:00:00Z",
  is_active: true,
}

let now = 5_000
let hidden = false
let nextFrameId = 0
const frames = new Map<number, FrameRequestCallback>()

function renderStories() {
  return render(
    <StrictMode>
      <AppShellProvider>
        <DashboardStories stories={[story]} />
      </AppShellProvider>
    </StrictMode>
  )
}

function openStory() {
  fireEvent.click(screen.getByRole("button", { name: "Story: Clock story" }))
  expect(screen.getByRole("dialog", { name: "Clock story" })).toBeInTheDocument()
}

function pointerDown(pointerId = 1) {
  fireEvent.pointerDown(screen.getByRole("heading", { name: "Clock story" }), {
    pointerId,
    pointerType: "touch",
    clientX: 100,
    clientY: 100,
  })
}

function pointerUp(pointerId = 1) {
  fireEvent.pointerUp(screen.getByRole("heading", { name: "Clock story" }), {
    pointerId,
    pointerType: "touch",
    clientX: 100,
    clientY: 100,
  })
}

function visibility(isHidden: boolean, timestamp: number) {
  hidden = isHidden
  now = timestamp
  act(() => document.dispatchEvent(new Event("visibilitychange")))
}

function tick(timestamp: number) {
  now = timestamp
  expect(frames.size).toBe(1)
  const [id, callback] = [...frames.entries()][0]!
  frames.delete(id)
  act(() => callback(timestamp))
}

function expectProgress(value: number) {
  expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", String(value))
}

describe("DashboardStories real-viewer clock and frame ownership", () => {
  beforeEach(() => {
    now = 5_000
    hidden = false
    nextFrameId = 0
    frames.clear()
    vi.spyOn(performance, "now").mockImplementation(() => now)
    vi.spyOn(document, "visibilityState", "get").mockImplementation(() =>
      hidden ? "hidden" : "visible"
    )
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
      // The browser's unsigned-long handle conversion makes null cancel handle 0.
      // Model it so cleanup cannot accidentally cancel another provider's frame.
      frames.delete(Number(id) >>> 0)
    })
  })

  afterEach(() => {
    cleanup()
    vi.restoreAllMocks()
  })

  it("preserves a nonzero opening epoch across repeated interaction pauses", () => {
    renderStories()
    openStory()
    tick(6_300)
    expectProgress(20)
    pointerDown()
    expect(frames.size).toBe(0)
    now = 9_000
    pointerDown(2)
    now = 9_500
    pointerUp(2)
    tick(10_150)
    expectProgress(30)
    expect(screen.getByRole("dialog", { name: "Clock story" })).toBeInTheDocument()
  })

  it("starts an already-hidden viewer paused and resumes its own zero elapsed time", () => {
    hidden = true
    renderStories()
    openStory()
    expect(frames.size).toBe(0)
    expectProgress(0)
    visibility(false, 9_000)
    tick(9_650)
    expectProgress(10)
  })

  it("retains interaction ownership through hidden and visible transitions before another press", () => {
    renderStories()
    openStory()
    tick(6_300)
    pointerDown()
    visibility(true, 7_000)
    visibility(false, 9_000)
    expect(frames.size).toBe(0)
    expectProgress(20)
    now = 10_000
    pointerDown(2)
    now = 11_000
    pointerUp(2)
    tick(11_650)
    expectProgress(30)
  })

  it.each([false, true])(
    "preserves another owner's frame during cleanup with viewer open=%s",
    (open) => {
      const outsideCallback = vi.fn()
      const outsideFrame = window.requestAnimationFrame(outsideCallback)
      const { unmount } = renderStories()
      if (open) openStory()
      unmount()
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
      expect([...frames.keys()]).toEqual([outsideFrame])
      const callback = frames.get(outsideFrame)!
      frames.delete(outsideFrame)
      act(() => callback(6_500))
      expect(outsideCallback).toHaveBeenCalledExactlyOnceWith(6_500)
      expect(frames.size).toBe(0)
    }
  )
})
