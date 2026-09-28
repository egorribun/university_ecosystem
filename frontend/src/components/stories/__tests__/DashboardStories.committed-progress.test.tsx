import { StrictMode, useLayoutEffect, useState } from "react"
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

const stories: StoryItem[] = ["One", "Two"].map((title) => ({
  id: title.toLowerCase(),
  title,
  short_text: title,
  created_at: "2026-09-01T00:00:00Z",
  published_at: "2026-09-01T00:00:00Z",
  expires_at: "2026-10-01T00:00:00Z",
  is_active: true,
}))

// A public callback consumer reads the committed view in its layout integration.
// It neither dispatches navigation from an effect nor observes private hook state.
function OpenedViewConsumer() {
  const [openedStory, setOpenedStory] = useState<{ story: StoryItem; revision: number } | null>(
    null
  )
  const [announcement, setAnnouncement] = useState("")
  useLayoutEffect(() => {
    if (!openedStory) return
    const activeProgress = document.querySelector(
      '[role="dialog"] [role="progressbar"][aria-live="polite"]'
    )
    setAnnouncement(`${openedStory.story.title}: ${activeProgress?.getAttribute("aria-valuenow")}`)
  }, [openedStory])
  return (
    <>
      <output aria-label="Opened view progress">{announcement}</output>
      <DashboardStories
        stories={stories}
        onStoryOpen={(story) =>
          setOpenedStory((previous) => ({ story, revision: (previous?.revision ?? 0) + 1 }))
        }
      />
    </>
  )
}

let now = 5_000
let nextFrameId = 0
const frames = new Map<number, FrameRequestCallback>()

function tick(timestamp: number) {
  now = timestamp
  expect(frames.size).toBe(1)
  const [id, callback] = [...frames.entries()][0]!
  frames.delete(id)
  act(() => callback(timestamp))
}

describe("DashboardStories public opened-view commit contract", () => {
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
      const id = nextFrameId++
      frames.set(id, callback)
      return id
    })
    vi.spyOn(window, "cancelAnimationFrame").mockImplementation((id) => frames.delete(id))
  })

  afterEach(() => {
    try {
      cleanup()
    } finally {
      vi.restoreAllMocks()
      frames.clear()
    }
  })

  it("publishes zero committed progress to a parent consumer during real viewer navigation", () => {
    const { unmount } = render(
      <StrictMode>
        <AppShellProvider>
          <OpenedViewConsumer />
        </AppShellProvider>
      </StrictMode>
    )
    fireEvent.click(screen.getByRole("button", { name: "Story: One" }))
    expect(screen.getByLabelText("Opened view progress")).toHaveTextContent("One: 0")
    tick(7_600)
    const activeProgress = () =>
      document.querySelector('[role="dialog"] [role="progressbar"][aria-live="polite"]')
    expect(activeProgress()).toHaveAttribute("aria-valuenow", "40")

    fireEvent.click(screen.getByRole("button", { name: "stories.viewer.aria.next" }))
    expect(screen.getByRole("dialog", { name: "Two" })).toBeInTheDocument()
    expect(screen.getByLabelText("Opened view progress")).toHaveTextContent("Two: 0")
    expect(activeProgress()).toHaveAttribute("aria-valuenow", "0")
    tick(8_900)
    expect(activeProgress()).toHaveAttribute("aria-valuenow", "20")
    fireEvent.click(screen.getByRole("button", { name: "stories.viewer.aria.prev" }))
    expect(screen.getByRole("dialog", { name: "One" })).toBeInTheDocument()
    expect(screen.getByLabelText("Opened view progress")).toHaveTextContent("One: 0")
    expect(activeProgress()).toHaveAttribute("aria-valuenow", "0")
    unmount()
    expect(frames.size).toBe(0)
  })

  it("publishes zero committed progress when reopening a played story", () => {
    const { unmount } = render(
      <StrictMode>
        <AppShellProvider>
          <OpenedViewConsumer />
        </AppShellProvider>
      </StrictMode>
    )
    fireEvent.click(screen.getByRole("button", { name: "Story: One" }))
    tick(7_600)
    expect(
      document.querySelector('[role="dialog"] [role="progressbar"][aria-live="polite"]')
    ).toHaveAttribute("aria-valuenow", "40")

    fireEvent.click(screen.getByRole("button", { name: "stories.viewer.aria.close" }))
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole("button", { name: "Story: One" }))
    expect(screen.getByRole("dialog", { name: "One" })).toBeInTheDocument()
    expect(screen.getByLabelText("Opened view progress")).toHaveTextContent("One: 0")
    unmount()
    expect(frames.size).toBe(0)
  })
})
