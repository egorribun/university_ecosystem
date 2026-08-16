import { act, render } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"

import type { StoryItem } from "@/types/Story"

type ViewerProps = {
  onNext: () => void
  onPrev: () => void
}

const mocks = vi.hoisted(() => ({
  displayedStories: [] as StoryItem[],
  viewerProps: undefined as ViewerProps | undefined,
}))

vi.mock("@/hooks/useMediaQuery", () => ({ default: () => false }))
vi.mock("../StoryList", () => ({
  StoryList: ({ stories }: { stories: StoryItem[] }) => {
    mocks.displayedStories = stories
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
})
