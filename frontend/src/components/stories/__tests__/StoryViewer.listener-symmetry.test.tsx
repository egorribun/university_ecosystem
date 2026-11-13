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

type TrackedListener = {
  type: string
  capture: boolean
  listener: EventListenerOrEventListenerObject
}

/**
 * Records every listener registered on the given targets and removes it from the
 * ledger when the same listener object is unregistered with the same type and capture
 * flag. The ledger is therefore the set of listeners that are still attached.
 */
function trackListeners(targets: EventTarget[]) {
  const ledger = new Map<EventTarget, Map<string, TrackedListener>>()
  const keyOf = (type: string, capture: boolean, listener: EventListenerOrEventListenerObject) =>
    `${type}|${capture ? "capture" : "bubble"}|${listener === null ? "null" : listener}`
  const addSpy = vi.spyOn(EventTarget.prototype, "addEventListener")
  const removeSpy = vi.spyOn(EventTarget.prototype, "removeEventListener")
  addSpy.mockImplementation(function (this: EventTarget, type, listener, options) {
    if (targets.includes(this) && listener) {
      const capture = typeof options === "boolean" ? options : Boolean(options?.capture)
      const map = ledger.get(this) ?? new Map<string, TrackedListener>()
      map.set(keyOf(type, capture, listener), { type, capture, listener })
      ledger.set(this, map)
    }
    return undefined
  })
  removeSpy.mockImplementation(function (this: EventTarget, type, listener, options) {
    if (targets.includes(this) && listener) {
      const capture = typeof options === "boolean" ? options : Boolean(options?.capture)
      ledger.get(this)?.delete(keyOf(type, capture, listener))
    }
    return undefined
  })
  return {
    snapshot: () =>
      Object.fromEntries(
        targets.map((target, index) => [
          index,
          [...(ledger.get(target)?.values() ?? [])]
            .map((entry) => `${entry.type}|${entry.capture ? "capture" : "bubble"}`)
            .sort(),
        ])
      ),
    restore: () => {
      addSpy.mockRestore()
      removeSpy.mockRestore()
    },
  }
}

describe("StoryViewer listener symmetry", () => {
  afterEach(() => {
    cleanup()
    vi.restoreAllMocks()
  })

  it("leaves no document, window or body listeners behind after repeated open/close cycles", async () => {
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

    const tracker = trackListeners([window, document, document.body])
    const openAndClose = async () => {
      await user.click(trigger)
      expect(await screen.findByRole("dialog", { name: "Orientation" })).toBeInTheDocument()
      await user.keyboard("{Escape}")
      await waitFor(() => {
        expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
      })
    }

    try {
      // Warm-up cycle: lazily registered, one-time listeners are allowed to settle first.
      await openAndClose()
      const warm = tracker.snapshot()

      for (let cycle = 0; cycle < 4; cycle += 1) {
        await openAndClose()
        expect(tracker.snapshot()).toEqual(warm)
      }
    } finally {
      tracker.restore()
    }
  })
})
