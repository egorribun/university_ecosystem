import { cleanup, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, describe, expect, it, vi } from "vitest"
import type { ReactNode } from "react"
import { ThemeProvider } from "@/contexts/ThemeContext"
import type { StoryItem } from "@/types/Story"
import { renderWithRouter } from "@/tests/helpers/renderWithRouter"
import DashboardStories from "../DashboardStories"

vi.mock("react-i18next", () => ({
  I18nextProvider: ({ children }: { children?: ReactNode }) => <>{children}</>,
  useTranslation: () => ({
    t: (key: string, options?: { title?: string; index?: number; total?: number }) => {
      if (key === "aria.storyItem") return `Story: ${options?.title}`
      if (key === "stories.viewer.aria.close") return "Close stories viewer"
      if (key === "stories.viewer.aria.dialog") {
        return `Story ${options?.index} of ${options?.total}: ${options?.title}`
      }
      return key
    },
  }),
}))

const stories: StoryItem[] = [
  {
    id: "story-one",
    title: "Orientation",
    short_text: "Welcome week",
    created_at: "2026-09-01T00:00:00Z",
    published_at: "2026-09-01T00:00:00Z",
    expires_at: "2026-10-01T00:00:00Z",
    is_active: true,
  },
]

describe("StoryViewer keyboard close focus", () => {
  afterEach(() => {
    cleanup()
    vi.restoreAllMocks()
  })

  it("closes on Escape and returns focus to the story trigger", async () => {
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

    const user = userEvent.setup()
    const Wrapped = () => (
      <ThemeProvider>
        <DashboardStories stories={stories} />
      </ThemeProvider>
    )
    await renderWithRouter({ ui: Wrapped })

    const trigger = await screen.findByRole("button", { name: "Story: Orientation" })
    trigger.focus()
    await user.click(trigger)

    expect(await screen.findByRole("dialog", { name: "Orientation" })).toBeInTheDocument()
    await user.keyboard("{Escape}")

    await waitFor(() => {
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
      expect(trigger).toHaveFocus()
    })
  })
})
