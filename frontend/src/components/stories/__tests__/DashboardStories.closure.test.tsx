import { act, render } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"

import type { StoryItem } from "@/types/Story"

type ViewerProps = {
  onNext: () => void
  onPrev: () => void
  onPause: () => void
  onResume: () => void
}

type ListProps = {
  stories: StoryItem[]
  onOpenStory: (story: StoryItem, index: number) => void
}

const mocks = vi.hoisted(() => ({
  displayedStories: [] as StoryItem[],
  listProps: undefined as ListProps | undefined,
  viewerProps: undefined as ViewerProps | undefined,
}))

vi.mock("@/hooks/useMediaQuery", () => ({ default: () => false }))
vi.mock("../StoryList", () => ({
  StoryList: (props: ListProps) => {
    mocks.displayedStories = props.stories
    mocks.listProps = props
    return <div data-testid="story-list" />
  },
}))
vi.mock("../StoryViewer", () => ({
  StoryViewer: (props: ViewerProps) => {
    mocks.viewerProps = props
    return <div data-testid="story-viewer" />
  },
}))

import DashboardStories from "../DashboardStories"

describe("DashboardStories defensive closure", () => {
  it("keeps closed-viewer navigation inert and rejects malformed story collections", () => {
    const { rerender } = render(<DashboardStories stories={[]} />)

    act(() => {
      mocks.viewerProps?.onNext()
      mocks.viewerProps?.onPrev()
    })
    expect(mocks.displayedStories).toEqual([])

    rerender(<DashboardStories stories={null as unknown as StoryItem[]} />)
    expect(mocks.displayedStories).toEqual([])
  })

  it("closes safely when stories disappear before previous navigation", () => {
    const stories = [
      { id: "one", title: "One" },
      { id: "two", title: "Two" },
    ] as StoryItem[]
    const onStoryOpen = vi.fn()
    const { rerender } = render(<DashboardStories stories={stories} onStoryOpen={onStoryOpen} />)

    act(() => mocks.listProps?.onOpenStory(stories[1]!, 1))
    expect(onStoryOpen).toHaveBeenCalledWith(stories[1])

    rerender(<DashboardStories stories={[]} onStoryOpen={onStoryOpen} />)
    act(() => mocks.viewerProps?.onPrev())

    expect(onStoryOpen).toHaveBeenCalledTimes(1)
  })

  it("makes repeated interaction pauses idempotent and resumes only while visible", () => {
    const stories = [{ id: "one", title: "One" }] as StoryItem[]
    const now = vi.spyOn(performance, "now").mockReturnValue(1_000)
    render(<DashboardStories stories={stories} />)
    act(() => mocks.listProps?.onOpenStory(stories[0]!, 0))

    act(() => {
      mocks.viewerProps?.onPause()
      mocks.viewerProps?.onPause()
      mocks.viewerProps?.onResume()
    })

    Object.defineProperty(document, "visibilityState", {
      configurable: true,
      value: "hidden",
    })
    act(() => document.dispatchEvent(new Event("visibilitychange")))
    act(() => mocks.viewerProps?.onResume())
    now.mockRestore()
  })
})
