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

const story: StoryItem = {
  id: "release-story",
  title: "Release story",
  short_text: "Playback belongs to active pause owners",
  created_at: "2026-09-01T00:00:00Z",
  published_at: "2026-09-01T00:00:00Z",
  expires_at: "2026-10-01T00:00:00Z",
  is_active: true,
}

let now = 5_000
let hidden = false
let nextFrameId = 0
const frames = new Map<number, FrameRequestCallback>()

function openStory() {
  render(
    <StrictMode>
      <AppShellProvider>
        <DashboardStories stories={[story]} />
      </AppShellProvider>
    </StrictMode>
  )
  fireEvent.click(screen.getByRole("button", { name: "Story: Release story" }))
  expect(screen.getByRole("dialog", { name: "Release story" })).toBeInTheDocument()
}

function pointer(type: "down" | "up" | "leave" | "cancel") {
  const target = screen.getByRole("heading", { name: "Release story" })
  const errors = collectWindowErrors(() => {
    const event = { pointerId: 1, pointerType: "touch", clientX: 100, clientY: 100 }
    if (type === "down") fireEvent.pointerDown(target, event)
    if (type === "up") fireEvent.pointerUp(target, event)
    if (type === "leave") fireEvent.pointerLeave(target, event)
    if (type === "cancel") fireEvent.pointerCancel(target, event)
  })
  expect(errors).toEqual([])
}

function visibility(value: boolean, timestamp: number) {
  hidden = value
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
  expect(Number(screen.getByRole("progressbar").getAttribute("aria-valuenow"))).toBeCloseTo(value)
}

describe("DashboardStories real-viewer interaction release ownership", () => {
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
    vi.spyOn(window, "cancelAnimationFrame").mockImplementation((id) => frames.delete(id))
  })

  afterEach(() => {
    cleanup()
    vi.restoreAllMocks()
  })

  it.each(["leave", "up", "cancel"] as const)(
    "keeps the visible playback epoch when pointer %s has no interaction pause owner",
    (release) => {
      openStory()
      tick(6_300)
      expectProgress(20)
      now = 7_000
      pointer(release)
      tick(7_600)
      expectProgress(40)
      expect(screen.getByRole("dialog", { name: "Release story" })).toBeInTheDocument()
    }
  )

  it("preserves newly earned elapsed time through two complete interaction pause cycles", () => {
    openStory()
    tick(6_300)
    pointer("down")
    expect(frames.size).toBe(0)
    now = 9_000
    pointer("up")
    tick(9_650)
    expectProgress(30)
    pointer("down")
    expect(frames.size).toBe(0)
    now = 12_000
    pointer("up")
    tick(12_650)
    expectProgress(40)
  })

  it("keeps hidden elapsed frozen through repeated releases without an interaction owner", () => {
    openStory()
    tick(6_300)
    visibility(true, 6_300)
    now = 8_000
    pointer("up")
    now = 9_000
    pointer("leave")
    now = 10_000
    pointer("down")
    visibility(false, 11_000)
    expect(frames.size).toBe(0)
    now = 12_000
    pointer("up")
    tick(12_650)
    expectProgress(30)
  })

  it("does not count hidden time when an already-hidden viewer gains an interaction owner", () => {
    hidden = true
    openStory()
    expect(frames.size).toBe(0)
    now = 9_000
    pointer("down")
    visibility(false, 10_000)
    expect(frames.size).toBe(0)
    now = 11_000
    pointer("up")
    tick(11_650)
    expectProgress(10)
  })
})
