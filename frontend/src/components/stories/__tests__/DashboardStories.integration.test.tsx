import { describe, it, expect, beforeEach, afterEach, vi } from "vitest"
import { act, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { ThemeProvider } from "@/contexts/ThemeContext"
import type { ComponentProps, ReactNode } from "react"

import DashboardStories from "../DashboardStories"
import type { StoryItem } from "@/types/Story"
import { renderWithRouter } from "@/tests/helpers/renderWithRouter"

vi.mock("@/components/media/SmartImage", () => ({
  default: ({ alt }: { alt?: string }) => <img alt={alt ?? ""} data-testid="smart-image" />,
}))

const translations: Record<string, string> = {
  "dashboard:aria.storiesList": "Stories carousel",
  "dashboard:aria.storyItem": "Story: {{title}}",
  "dashboard:stories.empty": "No stories yet",
  "dashboard:stories.emptyDescription": "Stories will be published soon.",
  "dashboard:stories.subheading": "Latest campus highlights.",
  "dashboard:stories.heading": "Stories",
  "dashboard:stories.viewer.openLink": "Open link",
  "dashboard:stories.viewer.aria.dialog": "Story {{index}} of {{total}}: {{title}}",
  "dashboard:stories.viewer.aria.close": "Close stories viewer",
  "dashboard:stories.viewer.aria.next": "Next story",
  "dashboard:stories.viewer.aria.prev": "Previous story",
  "dashboard:stories.viewer.aria.progress": "Progress for {{title}}",
  "dashboard:stories.viewer.aria.instructions":
    "Use the arrow keys or swipe to move between stories.",
  "dashboard:stories.viewer.hints.auto": "Stories advance automatically.",
  "dashboard:stories.viewer.hints.keyboard": "Use the left and right arrow keys to navigate.",
  "dashboard:stories.viewer.hints.swipe": "Swipe left or right to switch stories.",
  "dashboard:stories.viewer.hints.tap":
    "Tap the right side to skip ahead and the left side to go back.",
}

vi.mock("react-i18next", () => ({
  I18nextProvider: ({ children }: { children?: ReactNode }) => <>{children}</>,
  useTranslation: () => ({
    t: (key: string, options: Record<string, unknown> = {}) => {
      const namespaced = key.includes(":") ? key : `dashboard:${key}`
      const template = translations[namespaced] ?? namespaced
      return template.replace(/{{\s*(\w+)\s*}}/g, (_, token) => {
        const value = options[token]
        return value === undefined || value === null ? "" : String(value)
      })
    },
  }),
}))

const stories: StoryItem[] = [
  {
    id: "uuid-1",
    title: "Orientation",
    short_text: "Welcome week",
    cover_url: null,
    cover_url_optimized: null,
    cta_url: "/events",
    published_at: new Date(Date.now() - 3600_000).toISOString(),
    expires_at: new Date(Date.now() + 86_400_000).toISOString(),
    is_active: true,
    created_at: new Date().toISOString(),
    title_en: "Orientation",
    short_text_en: "Welcome week",
    created_by: "user-1",
  },
  {
    id: "uuid-2",
    title: "Clubs fair",
    short_text: "Meet the student clubs",
    cover_url: null,
    cover_url_optimized: null,
    cta_url: "/clubs",
    published_at: new Date(Date.now() - 1800_000).toISOString(),
    expires_at: new Date(Date.now() + 86_400_000).toISOString(),
    is_active: true,
    created_at: new Date().toISOString(),
    title_en: "Clubs fair",
    short_text_en: "Meet the student clubs",
    created_by: "user-1",
  },
]

type RenderOptions = {
  user?: ReturnType<typeof userEvent.setup>
}

async function renderStories(
  overrides: Partial<ComponentProps<typeof DashboardStories>> = {},
  options: RenderOptions = {}
) {
  const props: ComponentProps<typeof DashboardStories> = {
    stories,
    loading: false,
    onPrefetch: vi.fn(),
    onStoryOpen: vi.fn(),
    maxVisibleStories: 12,
    ...overrides,
  }

  const user = options.user ?? userEvent.setup()

  const Wrapped = () => (
    <ThemeProvider>
      <DashboardStories {...props} />
    </ThemeProvider>
  )

  const result = await renderWithRouter({ ui: Wrapped })

  return { user, props, ...result }
}

function setupMatchMedia({ mobile = false, reducedMotion = false } = {}) {
  vi.spyOn(window, "matchMedia").mockImplementation(
    (query: string) =>
      ({
        matches: query.includes("max-width")
          ? mobile
          : query.includes("prefers-reduced-motion")
            ? reducedMotion
            : false,
        media: query,
        onchange: null,
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        addListener: vi.fn(),
        removeListener: vi.fn(),
        dispatchEvent: vi.fn(),
      }) as unknown as MediaQueryList
  )
}

describe("DashboardStories", () => {
  beforeEach(() => {
    setupMatchMedia()
  })

  afterEach(() => {
    vi.restoreAllMocks()
    vi.useRealTimers()
  })

  it("opens a story and allows navigation via buttons", async () => {
    const onStoryOpen = vi.fn()
    const { user } = await renderStories({ onStoryOpen })

    const storyTrigger = await screen.findByRole("button", { name: "Story: Orientation" })
    await user.click(storyTrigger)

    expect(onStoryOpen).toHaveBeenCalledWith(stories[0])
    expect(await screen.findByRole("heading", { name: "Orientation" })).toBeInTheDocument()
    expect(screen.getByText("Stories advance automatically.")).toBeInTheDocument()

    await user.click(screen.getByLabelText("Next story"))

    expect(onStoryOpen).toHaveBeenLastCalledWith(stories[1])
    expect(await screen.findByRole("heading", { name: "Clubs fair" })).toBeInTheDocument()

    await user.click(screen.getByLabelText("Previous story"))
    expect(await screen.findByRole("heading", { name: "Orientation" })).toBeInTheDocument()
  })

  it("auto-advances stories after the progress completes", async () => {
    let now = 0
    vi.spyOn(performance, "now").mockImplementation(() => now)

    let frameCallback: FrameRequestCallback | null = null
    vi.spyOn(window, "requestAnimationFrame").mockImplementation(
      (callback: FrameRequestCallback) => {
        frameCallback = callback
        return 1
      }
    )
    vi.spyOn(window, "cancelAnimationFrame").mockImplementation(() => {
      frameCallback = null
    })

    const user = userEvent.setup()
    await renderStories({}, { user })

    const storyTrigger = await screen.findByRole("button", { name: "Story: Orientation" })
    await user.click(storyTrigger)

    await screen.findByRole("heading", { name: "Orientation" })

    expect(frameCallback).toBeTruthy()

    await act(async () => {
      now = 7_000
      frameCallback?.(now)
    })

    expect(await screen.findByRole("heading", { name: "Clubs fair" })).toBeInTheDocument()

    await user.keyboard("{Escape}")
  })

  it("responds to keyboard shortcuts", async () => {
    const { user } = await renderStories()

    const storyTrigger = await screen.findByRole("button", { name: "Story: Orientation" })
    await user.click(storyTrigger)

    await user.keyboard("{ArrowRight}")
    expect(await screen.findByRole("heading", { name: "Clubs fair" })).toBeInTheDocument()

    await user.keyboard("{ArrowLeft}")
    expect(await screen.findByRole("heading", { name: "Orientation" })).toBeInTheDocument()

    await user.keyboard("{Escape}")
    await waitFor(() => {
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
    })
  })

  it("handles navigation at both story boundaries", async () => {
    const { user } = await renderStories()

    await user.click(await screen.findByRole("button", { name: "Story: Orientation" }))
    await user.click(screen.getByLabelText("Previous story"))
    expect(await screen.findByRole("heading", { name: "Orientation" })).toBeInTheDocument()

    await user.click(screen.getByLabelText("Next story"))
    expect(await screen.findByRole("heading", { name: "Clubs fair" })).toBeInTheDocument()
    await user.click(screen.getByLabelText("Next story"))

    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument())
  })

  it("renders an honest empty state when there are no stories", async () => {
    await renderStories({ stories: [] })

    expect(screen.getByRole("heading", { name: "Stories" })).toBeInTheDocument()
    expect(screen.getByRole("status")).toHaveTextContent(
      "No stories yetStories will be published soon."
    )
  })
})
