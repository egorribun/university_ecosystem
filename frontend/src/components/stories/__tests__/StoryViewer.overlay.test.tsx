import { render, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"

import type { StoryItem } from "@/types/Story"

const shell = vi.hoisted(() => ({ setOverlayState: vi.fn() }))

vi.mock("@/contexts/AppShellContext", () => ({
  useAppShell: () => ({ setOverlayState: shell.setOverlayState }),
}))
vi.mock("@/hooks/useMediaQuery", () => ({ default: () => false }))
vi.mock("@/hooks/useFocusTrap", () => ({ default: () => ({ current: null }) }))
vi.mock("@/hooks/useSwipe", () => ({ useSwipe: () => ({}) }))
vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}))

import { StoryViewer } from "../StoryViewer"

const story: StoryItem = {
  id: "story-overlay",
  title: "Overlay story",
  created_at: "2026-01-01",
  expires_at: "2026-01-02",
  published_at: "2026-01-01",
  is_active: true,
  cover_url_optimized: null,
  short_text: "Overlay story",
}

const props = {
  stories: [story],
  progress: 0,
  onClose: vi.fn(),
  onNext: vi.fn(),
  onPrev: vi.fn(),
  onPause: vi.fn(),
  onResume: vi.fn(),
}

describe("StoryViewer app-shell overlay registration", () => {
  it("locks scrolling without blurring the page while open and releases it on close", () => {
    const { rerender } = render(<StoryViewer {...props} activeStoryIndex={0} />)

    expect(shell.setOverlayState).toHaveBeenCalledExactlyOnceWith("story-viewer", {
      blurred: false,
      scrollLocked: true,
    })

    rerender(<StoryViewer {...props} activeStoryIndex={null} />)

    expect(shell.setOverlayState).toHaveBeenLastCalledWith("story-viewer", null)
  })

  it("announces the auto-advance hint to screen readers", () => {
    render(<StoryViewer {...props} activeStoryIndex={0} />)
    expect(screen.getByText("stories.viewer.hints.auto")).toBeInTheDocument()
  })
})
