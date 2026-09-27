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

describe("DashboardStories defensive sparse collection boundary", () => {
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

  it("compacts before limiting and keeps real navigation densely indexed", () => {
    const one = story("One")
    const two = story("Two")
    const three = story("Three")
    // Preserve the component's existing defensive runtime contract; API
    // payloads normally arrive as dense arrays. No nullable item cast is needed.
    const collection: StoryItem[] = []
    collection[1] = one
    collection[3] = two
    collection[5] = three
    const onStoryOpen = vi.fn()

    render(
      <StrictMode>
        <AppShellProvider>
          <DashboardStories stories={collection} maxVisibleStories={2} onStoryOpen={onStoryOpen} />
        </AppShellProvider>
      </StrictMode>
    )

    expect(screen.getAllByRole("button", { name: /^Story: / })).toHaveLength(2)
    expect(screen.getByRole("button", { name: "Story: One" })).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Story: Two" })).toBeInTheDocument()
    expect(screen.queryByRole("button", { name: "Story: Three" })).not.toBeInTheDocument()

    click("Story: One")
    expect(screen.getByRole("dialog", { name: "One" })).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Story: One" })).toHaveAttribute(
      "data-active",
      "true"
    )
    click("stories.viewer.aria.next")
    expect(screen.getByRole("dialog", { name: "Two" })).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Story: Two" })).toHaveAttribute(
      "data-active",
      "true"
    )
    click("stories.viewer.aria.next")
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
    expect(onStoryOpen.mock.calls).toEqual([[one], [two]])
  })
})
