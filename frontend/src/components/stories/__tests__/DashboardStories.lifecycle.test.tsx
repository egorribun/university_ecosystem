import { StrictMode } from "react"
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

const stories: StoryItem[] = [
  {
    id: "lifecycle-one",
    title: "Lifecycle one",
    short_text: "First lifecycle story",
    created_at: "2026-09-01T00:00:00Z",
    published_at: "2026-09-01T00:00:00Z",
    expires_at: "2026-10-01T00:00:00Z",
    is_active: true,
  },
]

const observedEvents = new Set([
  "click",
  "focusin",
  "keydown",
  "mousedown",
  "touchstart",
  "visibilitychange",
])
type Listener = EventListenerOrEventListenerObject
type ActiveListeners = Map<EventTarget, Map<string, Map<Listener, Set<boolean>>>>

let activeListeners: ActiveListeners
let frames: Map<number, FrameRequestCallback>
let nextFrameId: number
let mediaLists: Array<Set<(event: MediaQueryListEvent) => void>>

function captureValue(options?: boolean | AddEventListenerOptions): boolean {
  return typeof options === "boolean" ? options : Boolean(options?.capture)
}

function updateListenerLedger(
  action: "add" | "remove",
  target: EventTarget,
  type: string,
  listener: Listener | null,
  options?: boolean | AddEventListenerOptions
) {
  if (!listener || !observedEvents.has(type) || (target !== document && target !== window)) return

  let byType = activeListeners.get(target)
  if (!byType) {
    byType = new Map()
    activeListeners.set(target, byType)
  }
  let byListener = byType.get(type)
  if (!byListener) {
    byListener = new Map()
    byType.set(type, byListener)
  }

  const captures = byListener.get(listener) ?? new Set<boolean>()
  if (action === "add") {
    captures.add(captureValue(options))
    byListener.set(listener, captures)
    return
  }

  captures.delete(captureValue(options))
  if (captures.size === 0) byListener.delete(listener)
}

function listenerSnapshot(): Record<string, number> {
  const snapshot: Record<string, number> = {}
  for (const [targetName, target] of [
    ["document", document],
    ["window", window],
  ] as const) {
    const byType = activeListeners.get(target)
    for (const type of observedEvents) {
      const byListener = byType?.get(type)
      snapshot[`${targetName}.${type}`] = byListener
        ? [...byListener.values()].reduce((count, captures) => count + captures.size, 0)
        : 0
    }
  }
  return snapshot
}

function activeMediaSubscriptionCount(): number {
  return mediaLists.reduce((count, listeners) => count + listeners.size, 0)
}

describe("DashboardStories repeated viewer lifecycle", () => {
  beforeEach(() => {
    activeListeners = new Map()
    frames = new Map()
    nextFrameId = 0
    mediaLists = []

    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] })
    vi.spyOn(performance, "now").mockReturnValue(5_000)
    vi.spyOn(document, "visibilityState", "get").mockReturnValue("visible")

    vi.spyOn(window, "matchMedia").mockImplementation((query) => {
      const listeners = new Set<(event: MediaQueryListEvent) => void>()
      mediaLists.push(listeners)
      return {
        matches: false,
        media: query,
        onchange: null,
        addEventListener: (_type: string, listener: (event: MediaQueryListEvent) => void) => {
          listeners.add(listener)
        },
        removeEventListener: (_type: string, listener: (event: MediaQueryListEvent) => void) => {
          listeners.delete(listener)
        },
        addListener: vi.fn(),
        removeListener: vi.fn(),
        dispatchEvent: vi.fn(),
      } as MediaQueryList
    })

    vi.spyOn(window, "requestAnimationFrame").mockImplementation((callback) => {
      const id = nextFrameId++
      frames.set(id, callback)
      return id
    })
    vi.spyOn(window, "cancelAnimationFrame").mockImplementation((id) => {
      frames.delete(Number(id) >>> 0)
    })

    const originalWindowAdd = window.addEventListener.bind(window)
    const originalWindowRemove = window.removeEventListener.bind(window)
    vi.spyOn(window, "addEventListener").mockImplementation((type, listener, options) => {
      updateListenerLedger("add", window, type, listener, options)
      return originalWindowAdd(type, listener, options)
    })
    vi.spyOn(window, "removeEventListener").mockImplementation((type, listener, options) => {
      updateListenerLedger("remove", window, type, listener, options)
      return originalWindowRemove(type, listener, options)
    })

    const originalDocumentAdd = document.addEventListener.bind(document)
    const originalDocumentRemove = document.removeEventListener.bind(document)
    vi.spyOn(document, "addEventListener").mockImplementation((type, listener, options) => {
      updateListenerLedger("add", document, type, listener, options)
      return originalDocumentAdd(type, listener, options)
    })
    vi.spyOn(document, "removeEventListener").mockImplementation((type, listener, options) => {
      updateListenerLedger("remove", document, type, listener, options)
      return originalDocumentRemove(type, listener, options)
    })
  })

  afterEach(() => {
    cleanup()
    vi.runOnlyPendingTimers()
    vi.useRealTimers()
    vi.restoreAllMocks()
  })

  it("returns timers, animation frames and global listeners to baseline after twenty cycles", () => {
    const beforeMount = listenerSnapshot()
    const { unmount } = render(
      <StrictMode>
        <AppShellProvider>
          <DashboardStories stories={stories} />
        </AppShellProvider>
      </StrictMode>
    )
    const mountedBaseline = listenerSnapshot()
    const trigger = screen.getByRole("button", { name: "Story: Lifecycle one" })

    expect(mountedBaseline["document.visibilitychange"]).toBe(1)
    expect(activeMediaSubscriptionCount()).toBe(2)
    expect(frames.size).toBe(0)
    expect(vi.getTimerCount()).toBe(0)

    for (let cycle = 0; cycle < 20; cycle += 1) {
      fireEvent.click(trigger)
      expect(screen.getByRole("dialog", { name: "Lifecycle one" })).toBeInTheDocument()
      expect(listenerSnapshot()["window.keydown"]).toBe(mountedBaseline["window.keydown"]! + 1)
      expect(activeMediaSubscriptionCount()).toBe(2)
      expect(frames.size).toBe(1)
      expect(vi.getTimerCount()).toBeGreaterThan(0)

      fireEvent.keyDown(window, { key: "Escape", cancelable: true })
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
      expect(listenerSnapshot()).toEqual(mountedBaseline)
      expect(activeMediaSubscriptionCount()).toBe(2)
      expect(frames.size).toBe(0)
      act(() => vi.runOnlyPendingTimers())
      expect(vi.getTimerCount()).toBe(0)
    }

    unmount()
    act(() => vi.runOnlyPendingTimers())
    expect(listenerSnapshot()).toEqual(beforeMount)
    expect(activeMediaSubscriptionCount()).toBe(0)
    expect(frames.size).toBe(0)
    expect(vi.getTimerCount()).toBe(0)
  })
})
