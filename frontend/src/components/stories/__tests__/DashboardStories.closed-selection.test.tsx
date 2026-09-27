import { StrictMode } from "react"
import { cleanup, fireEvent, render, screen } from "@testing-library/react"
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

function story(title: string): StoryItem {
  return {
    id: title.toLowerCase(),
    title,
    short_text: title,
    created_at: "2026-09-01T00:00:00Z",
    published_at: "2026-09-01T00:00:00Z",
    expires_at: "2026-10-01T00:00:00Z",
    is_active: true,
  }
}

function click(name: string) {
  const errors = collectWindowErrors(() => {
    fireEvent.click(screen.getByRole("button", { name }))
  })
  expect(errors).toEqual([])
}

describe("DashboardStories defensive closed selection boundary", () => {
  beforeEach(() => {
    vi.spyOn(window, "matchMedia").mockImplementation(
      (query) =>
        ({
          matches: query === "(prefers-reduced-motion: reduce)",
          media: query,
          onchange: null,
          addEventListener: vi.fn(),
          removeEventListener: vi.fn(),
          addListener: vi.fn(),
          removeListener: vi.fn(),
          dispatchEvent: vi.fn(),
        }) as MediaQueryList
    )
  })

  afterEach(() => {
    cleanup()
    vi.restoreAllMocks()
  })

  it.each(["initial render", "after close"])(
    "does not resolve a closed viewer index or expose a dialog on %s",
    (phase) => {
      const one = story("One")
      const two = story("Two")
      let closedIndexReads = 0
      class StoryCollection extends Array<StoryItem> {
        get "-1"(): StoryItem {
          closedIndexReads += 1
          return one
        }
      }
      const collection: StoryItem[] = new StoryCollection(one, two)
      const onStoryOpen = vi.fn()
      const previousOverflow = document.body.style.overflow

      render(
        <StrictMode>
          <AppShellProvider>
            <DashboardStories stories={collection} onStoryOpen={onStoryOpen} />
          </AppShellProvider>
        </StrictMode>
      )

      if (phase === "after close") {
        click("Story: One")
        expect(screen.getByRole("dialog", { name: "One" })).toBeInTheDocument()
        expect(onStoryOpen.mock.calls).toEqual([[one]])
        expect(document.body.style.overflow).toBe("hidden")
        closedIndexReads = 0
        click("stories.viewer.aria.close")
      }

      expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
      expect(closedIndexReads).toBe(0)
      expect(document.body.style.overflow).toBe(previousOverflow)
      expect(screen.getByRole("button", { name: "Story: One" })).not.toHaveAttribute("data-active")
      expect(screen.getByRole("button", { name: "Story: Two" })).not.toHaveAttribute("data-active")
    }
  )

  it("keeps a closed viewer unselected even when a typed array inherits a null accessor", () => {
    const one = story("One")
    const two = story("Two")
    // Array subclass species survives filter/slice. This remains a typed
    // StoryItem[] without changing Array.prototype or supplying nullable items.
    class StoryCollection extends Array<StoryItem> {
      get null(): StoryItem {
        return one
      }
    }
    const collection: StoryItem[] = new StoryCollection(one, two)
    const onStoryOpen = vi.fn()

    render(
      <StrictMode>
        <AppShellProvider>
          <DashboardStories stories={collection} onStoryOpen={onStoryOpen} />
        </AppShellProvider>
      </StrictMode>
    )

    const firstCircle = screen.getByRole("button", { name: "Story: One" })
    const secondCircle = screen.getByRole("button", { name: "Story: Two" })
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
    expect(firstCircle).not.toHaveAttribute("data-active")
    expect(secondCircle).not.toHaveAttribute("data-active")

    click("Story: One")
    expect(screen.getByRole("dialog", { name: "One" })).toBeInTheDocument()
    expect(firstCircle).toHaveAttribute("data-active", "true")
    expect(secondCircle).not.toHaveAttribute("data-active")
    click("stories.viewer.aria.next")
    expect(screen.getByRole("dialog", { name: "Two" })).toBeInTheDocument()
    expect(firstCircle).not.toHaveAttribute("data-active")
    expect(secondCircle).toHaveAttribute("data-active", "true")
    click("stories.viewer.aria.close")
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
    expect(firstCircle).not.toHaveAttribute("data-active")
    expect(secondCircle).not.toHaveAttribute("data-active")
    expect(onStoryOpen.mock.calls).toEqual([[one], [two]])
  })
})
