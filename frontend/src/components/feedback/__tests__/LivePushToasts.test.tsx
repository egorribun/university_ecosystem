import { act, render, screen, fireEvent } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

type CapturedMotionProps = Record<string, unknown> & { children?: unknown }

const motionCapture = vi.hoisted(() => ({
  divProps: [] as CapturedMotionProps[],
}))

vi.mock("framer-motion", async () => {
  const base = (await import("@/tests/helpers/framerMotionMock")).framerMotionMock()
  const motion = new Proxy(base.m, {
    get(target, key, receiver) {
      const component = Reflect.get(target, key, receiver)
      if (key !== "div" || typeof component !== "function") return component
      return (props: CapturedMotionProps) => {
        motionCapture.divProps.push(props)
        return component(props)
      }
    },
  })
  return { ...base, m: motion, motion }
})
const translationState = vi.hoisted(() => ({ emptySync: false }))

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) =>
      translationState.emptySync && key.startsWith("notifications:sync.") ? "" : key,
    i18n: { language: "en", changeLanguage: () => Promise.resolve() },
  }),
}))

import LivePushToasts from "@/components/feedback/LivePushToasts"

const BUFFER_STORAGE_KEY = "livePushToastBuffer"

type SwMessageHandler = (event: MessageEvent) => void

let messageHandler: SwMessageHandler | null = null

/** Install a fake navigator.serviceWorker that captures the message handler. */
function installFakeServiceWorker() {
  messageHandler = null
  Object.defineProperty(navigator, "serviceWorker", {
    configurable: true,
    value: {
      addEventListener: (type: string, handler: SwMessageHandler) => {
        if (type === "message") messageHandler = handler
      },
      removeEventListener: (type: string, handler: SwMessageHandler) => {
        if (type === "message" && messageHandler === handler) messageHandler = null
      },
    },
  })
}

/** Dispatch a service-worker message through the captured handler. */
async function dispatchSwMessage(data: unknown) {
  await act(async () => {
    messageHandler?.({ data } as MessageEvent)
    await Promise.resolve()
  })
}

describe("LivePushToasts", () => {
  beforeEach(() => {
    translationState.emptySync = false
    motionCapture.divProps.length = 0
    window.localStorage.clear()
    installFakeServiceWorker()
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.clearAllTimers()
    vi.useRealTimers()
    window.localStorage.clear()
  })

  it("renders nothing initially (no queued toasts)", () => {
    render(<LivePushToasts />)
    expect(screen.queryByRole("heading", { level: 4 })).not.toBeInTheDocument()
  })

  it("keeps toast entrance motion compositor-safe and bounded", async () => {
    render(<LivePushToasts />)

    await dispatchSwMessage({
      type: "PUSH_NOTIFICATION",
      toast: {
        id: "t-motion",
        title: "Motion contract",
        body: "Only opacity and transform should animate",
      },
    })

    const toastMotion = motionCapture.divProps.find((props) => {
      const initial = props.initial
      return (
        typeof initial === "object" && initial !== null && "opacity" in initial && "y" in initial
      )
    })
    expect(toastMotion).toBeDefined()
    expect(toastMotion).toEqual(
      expect.objectContaining({
        initial: { opacity: 0, y: -20 },
        animate: { opacity: 1, y: 0 },
        exit: { opacity: 0, y: -10 },
        transition: { duration: 0.2, ease: "easeOut" },
      })
    )
    for (const phase of ["initial", "animate", "exit"] as const) {
      expect(Object.keys(toastMotion?.[phase] as object)).toEqual(
        expect.arrayContaining(["opacity", "y"])
      )
      expect(Object.keys(toastMotion?.[phase] as object)).not.toContain("filter")
    }
    expect((toastMotion?.transition as Record<string, unknown>).type).toBeUndefined()
  })

  it("subscribes to the service-worker message channel on mount", () => {
    render(<LivePushToasts />)
    expect(messageHandler).toBeTypeOf("function")
  })

  it("renders safely when service-worker messaging is unavailable", () => {
    const serviceWorker = navigator.serviceWorker
    Object.defineProperty(navigator, "serviceWorker", {
      configurable: true,
      value: undefined,
    })

    try {
      render(<LivePushToasts />)
      expect(messageHandler).toBeNull()
      expect(screen.queryByRole("heading", { level: 4 })).not.toBeInTheDocument()
    } finally {
      Object.defineProperty(navigator, "serviceWorker", {
        configurable: true,
        value: serviceWorker,
      })
    }
  })

  it("renders a success toast (CheckCircle icon) from a PUSH_NOTIFICATION message", async () => {
    render(<LivePushToasts />)

    await dispatchSwMessage({
      type: "PUSH_NOTIFICATION",
      toast: {
        id: "t-success",
        title: "Saved",
        body: "Your changes were saved",
        data: { severity: "success" },
      },
    })

    act(() => {
      vi.advanceTimersByTime(0)
    })

    expect(screen.getByText("Saved")).toBeInTheDocument()
    expect(screen.getByText("Your changes were saved")).toBeInTheDocument()
    expect(screen.getByRole("status")).toHaveClass("border-l-success-border")
  })

  it("renders an info toast for an unknown/missing severity (default branch)", async () => {
    render(<LivePushToasts />)

    await dispatchSwMessage({
      type: "PUSH_NOTIFICATION",
      toast: { id: "t-info", title: "Heads up", body: "Something happened" },
    })

    act(() => {
      vi.advanceTimersByTime(0)
    })

    expect(screen.getByText("Heads up")).toBeInTheDocument()
    expect(screen.getByRole("status")).toHaveClass("border-l-brand")
  })

  it("normalizes severity casing and surrounding whitespace", async () => {
    render(<LivePushToasts />)

    await dispatchSwMessage({
      type: "PUSH_NOTIFICATION",
      toast: {
        id: "normalized-severity",
        title: "Normalized warning",
        body: "Severity is case-insensitive",
        data: { severity: "  WARNING  " },
      },
    })
    act(() => {
      vi.advanceTimersByTime(0)
    })

    expect(screen.getByRole("status")).toHaveClass("border-l-warning-border")
  })

  it("falls back to a finite timestamp when id metadata has the wrong type", async () => {
    render(<LivePushToasts />)

    const message = {
      type: "PUSH_NOTIFICATION",
      toast: {
        id: 123,
        tag: { unexpected: true },
        timestamp: 0,
        title: "Timestamp identity",
        body: "Zero is still a valid finite timestamp",
      },
    }
    await dispatchSwMessage(message)
    await dispatchSwMessage(message)
    act(() => {
      vi.advanceTimersByTime(0)
    })

    expect(screen.getAllByText("Timestamp identity")).toHaveLength(1)
    fireEvent.click(screen.getByRole("button", { name: "common:buttons.close" }))
    act(() => {
      vi.advanceTimersByTime(300)
    })
    expect(screen.queryByText("Timestamp identity")).not.toBeInTheDocument()
  })

  it("deduplicates repeated visible notifications by their canonical id", async () => {
    render(<LivePushToasts />)

    const message = {
      type: "PUSH_NOTIFICATION",
      toast: { id: "duplicate-visible", title: "Only once", body: "Do not replay" },
    }
    await dispatchSwMessage(message)
    await dispatchSwMessage(message)
    act(() => {
      vi.advanceTimersByTime(0)
    })

    expect(screen.getAllByText("Only once")).toHaveLength(1)
    fireEvent.click(screen.getByRole("button", { name: "common:buttons.close" }))
    act(() => {
      vi.advanceTimersByTime(300)
    })
    expect(screen.queryByText("Only once")).not.toBeInTheDocument()
  })

  it("falls back for non-string and unknown severity values", async () => {
    render(<LivePushToasts />)

    await dispatchSwMessage({
      type: "PUSH_NOTIFICATION",
      toast: {
        id: "t-invalid-severity",
        title: "Invalid severity",
        body: "Falls back to info",
        data: { severity: 42 },
      },
    })
    act(() => {
      vi.advanceTimersByTime(0)
    })
    expect(screen.getByText("Invalid severity")).toBeInTheDocument()

    fireEvent.click(screen.getByRole("button", { name: "common:buttons.close" }))
    act(() => {
      vi.advanceTimersByTime(300)
    })

    await dispatchSwMessage({
      type: "PUSH_NOTIFICATION",
      toast: {
        id: "t-unknown-severity",
        title: "Unknown severity",
        body: "Also falls back",
        data: { severity: "not-a-severity" },
      },
    })
    act(() => {
      vi.advanceTimersByTime(0)
    })
    expect(screen.getByText("Unknown severity")).toBeInTheDocument()
  })

  it("generates a stable-enough fallback id when push metadata has no id", async () => {
    render(<LivePushToasts />)

    await dispatchSwMessage({
      type: "PUSH_NOTIFICATION",
      toast: { title: "Generated id", body: "No id, tag, or timestamp" },
    })

    act(() => {
      vi.advanceTimersByTime(0)
    })
    expect(screen.getByText("Generated id")).toBeInTheDocument()
  })

  it("renders a warning toast", async () => {
    render(<LivePushToasts />)

    await dispatchSwMessage({
      type: "PUSH_NOTIFICATION",
      toast: {
        id: "t-warn",
        title: "Careful",
        body: "Low disk space",
        data: { severity: "warning" },
      },
    })

    act(() => {
      vi.advanceTimersByTime(0)
    })

    expect(screen.getByText("Careful")).toBeInTheDocument()
    expect(screen.getByRole("status")).toHaveClass("border-l-warning-border")
  })

  it("renders an error toast", async () => {
    render(<LivePushToasts />)

    await dispatchSwMessage({
      type: "PUSH_NOTIFICATION",
      toast: {
        id: "t-error",
        title: "Failed",
        body: "Upload failed",
        data: { severity: "error" },
      },
    })

    act(() => {
      vi.advanceTimersByTime(0)
    })

    expect(screen.getByText("Failed")).toBeInTheDocument()
    expect(screen.getByRole("status")).toHaveClass("border-l-error-border")
  })

  it("announces visible toasts and keeps action targets touch accessible", async () => {
    render(<LivePushToasts />)

    await dispatchSwMessage({
      type: "PUSH_NOTIFICATION",
      toast: {
        id: "a11y-toast",
        title: "Accessible notification",
        body: "Assistive technology should announce this",
        url: "/events/1",
      },
    })
    act(() => {
      vi.advanceTimersByTime(0)
    })

    const toast = screen.getByRole("status")
    expect(toast).toHaveAttribute("aria-live", "polite")
    expect(toast).toHaveAttribute("aria-atomic", "true")
    expect(screen.getByRole("button", { name: "common:buttons.close" })).toHaveClass(
      "min-h-11",
      "min-w-11"
    )
    expect(screen.getByRole("button", { name: "notifications:toast.open" })).toHaveClass("min-h-11")
  })

  it("ignores a PUSH_NOTIFICATION with no content (empty title and body)", async () => {
    render(<LivePushToasts />)

    await dispatchSwMessage({
      type: "PUSH_NOTIFICATION",
      toast: { id: "blank", title: "", body: "" },
    })

    expect(screen.queryByRole("heading", { level: 4 })).not.toBeInTheDocument()
  })

  it("ignores a PUSH_NOTIFICATION message without a toast payload", async () => {
    render(<LivePushToasts />)

    await dispatchSwMessage({ type: "PUSH_NOTIFICATION" })

    expect(screen.queryByRole("heading", { level: 4 })).not.toBeInTheDocument()
  })

  it("ignores push payloads with malformed field types without throwing", async () => {
    render(<LivePushToasts />)

    await expect(
      dispatchSwMessage({
        type: "PUSH_NOTIFICATION",
        toast: {
          id: 123,
          tag: { unexpected: true },
          title: 456,
          body: { unexpected: true },
          url: { unexpected: true },
        },
      })
    ).resolves.toBeUndefined()

    expect(screen.queryByRole("heading", { level: 4 })).not.toBeInTheDocument()
  })

  it("ignores non-object toast payloads without rendering or throwing", async () => {
    render(<LivePushToasts />)

    await dispatchSwMessage({ type: "PUSH_NOTIFICATION", toast: "not-an-object" })
    await dispatchSwMessage({ type: "PUSH_NOTIFICATION", toast: [] })

    expect(screen.queryByRole("heading", { level: 4 })).not.toBeInTheDocument()
  })

  it("uses localized defaults for omitted title or body", async () => {
    render(<LivePushToasts />)

    await dispatchSwMessage({
      type: "PUSH_NOTIFICATION",
      toast: { id: "missing-title", body: "Body without a title" },
    })
    act(() => {
      vi.advanceTimersByTime(0)
    })
    expect(screen.getByText("notifications:defaultTitle")).toBeInTheDocument()
    expect(screen.getByText("Body without a title")).toBeInTheDocument()

    fireEvent.click(screen.getByRole("button", { name: "common:buttons.close" }))
    act(() => {
      vi.advanceTimersByTime(300)
    })

    await dispatchSwMessage({
      type: "PUSH_NOTIFICATION",
      toast: { id: "missing-body", title: "Title without a body" },
    })
    act(() => {
      vi.advanceTimersByTime(0)
    })
    expect(screen.getByText("Title without a body")).toBeInTheDocument()
    expect(screen.getByText("notifications:defaultBody")).toBeInTheDocument()
  })

  it("renders a sync-complete toast from a SYNC_COMPLETE message (i18n keys)", async () => {
    render(<LivePushToasts />)

    await dispatchSwMessage({ type: "SYNC_COMPLETE" })

    act(() => {
      vi.advanceTimersByTime(0)
    })

    expect(screen.getByText("notifications:sync.title")).toBeInTheDocument()
    expect(screen.getByText("notifications:sync.body")).toBeInTheDocument()
  })

  it("ignores an empty localized sync-complete toast", async () => {
    translationState.emptySync = true
    render(<LivePushToasts />)

    await dispatchSwMessage({ type: "SYNC_COMPLETE" })
    act(() => {
      vi.advanceTimersByTime(0)
    })

    expect(screen.queryByRole("heading", { level: 4 })).not.toBeInTheDocument()
  })

  it("dismisses the current toast when the close button is clicked", async () => {
    render(<LivePushToasts />)

    await dispatchSwMessage({
      type: "PUSH_NOTIFICATION",
      toast: { id: "t-close", title: "Closable", body: "Tap to close" },
    })

    act(() => {
      vi.advanceTimersByTime(0)
    })

    expect(screen.getByText("Closable")).toBeInTheDocument()

    fireEvent.click(screen.getByRole("button", { name: "common:buttons.close" }))

    act(() => {
      vi.advanceTimersByTime(300)
    })

    expect(screen.queryByText("Closable")).not.toBeInTheDocument()
  })

  it("does not let repeated close actions clear the next queued toast", async () => {
    render(<LivePushToasts />)

    await dispatchSwMessage({
      type: "PUSH_NOTIFICATION",
      toast: { id: "first-close", title: "First toast", body: "Dismiss me" },
    })
    await dispatchSwMessage({
      type: "PUSH_NOTIFICATION",
      toast: { id: "second-close", title: "Second toast", body: "Keep me visible" },
    })
    act(() => {
      vi.advanceTimersByTime(0)
    })

    const closeButton = screen.getByRole("button", { name: "common:buttons.close" })
    fireEvent.click(closeButton)
    // A rapid second click can target the exiting DOM node before the animation completes.
    fireEvent.click(closeButton)

    act(() => {
      vi.advanceTimersByTime(300)
    })
    expect(screen.getByText("Second toast")).toBeInTheDocument()

    act(() => {
      vi.advanceTimersByTime(300)
    })
    expect(screen.getByText("Second toast")).toBeInTheDocument()
  })

  it("replaces an active close timer when close is invoked twice in one interaction", async () => {
    render(<LivePushToasts />)

    await dispatchSwMessage({
      type: "PUSH_NOTIFICATION",
      toast: { id: "double-close", title: "Double close", body: "Reset the timer" },
    })
    act(() => {
      vi.advanceTimersByTime(0)
    })

    const closeButton = screen.getByRole("button", { name: "common:buttons.close" })
    act(() => {
      // Keep both events in the same React batch so the second event reaches
      // the still-mounted control before the exit state commits.
      closeButton.dispatchEvent(new MouseEvent("click", { bubbles: true }))
      closeButton.dispatchEvent(new MouseEvent("click", { bubbles: true }))
    })

    expect(vi.getTimerCount()).toBe(1)
  })

  it("evicts the oldest seen id after the deduplication window is full", () => {
    render(<LivePushToasts />)

    act(() => {
      for (let index = 0; index <= 256; index += 1) {
        messageHandler?.({
          data: {
            type: "PUSH_NOTIFICATION",
            toast: { id: `seen-${index}`, title: `Toast ${index}`, body: "Seen window" },
          },
        } as MessageEvent)
      }
    })
    act(() => {
      vi.advanceTimersByTime(0)
    })

    expect(screen.getByText("Toast 0")).toBeInTheDocument()
  })

  it("cleans up the deferred close timer when the toast unmounts", async () => {
    const { unmount } = render(<LivePushToasts />)

    await dispatchSwMessage({
      type: "PUSH_NOTIFICATION",
      toast: { id: "unmount-close", title: "Unmount me", body: "No timer leak" },
    })
    act(() => {
      vi.advanceTimersByTime(0)
    })

    fireEvent.click(screen.getByRole("button", { name: "common:buttons.close" }))
    expect(vi.getTimerCount()).toBe(1)

    unmount()
    expect(vi.getTimerCount()).toBe(0)
  })

  it("renders an action button when the toast carries a safe URL, and opening it dismisses the toast", async () => {
    const openSpy = vi.spyOn(window, "open").mockReturnValue(null)
    render(<LivePushToasts />)

    await dispatchSwMessage({
      type: "PUSH_NOTIFICATION",
      toast: {
        id: "t-url",
        title: "Open me",
        body: "Has a link",
        url: "https://example.com/path",
      },
    })

    act(() => {
      vi.advanceTimersByTime(0)
    })

    const actionButton = screen.getByText("notifications:toast.open")
    expect(actionButton).toBeInTheDocument()

    fireEvent.click(actionButton)

    expect(openSpy).toHaveBeenCalled()

    act(() => {
      vi.advanceTimersByTime(300)
    })

    expect(screen.queryByText("Open me")).not.toBeInTheDocument()

    openSpy.mockRestore()
  })

  it("falls back to a new-tab open when the initial action open throws", async () => {
    const openSpy = vi
      .spyOn(window, "open")
      .mockImplementationOnce(() => {
        throw new Error("popup blocked")
      })
      .mockReturnValue(null)
    render(<LivePushToasts />)

    await dispatchSwMessage({
      type: "PUSH_NOTIFICATION",
      toast: {
        id: "t-url-fallback",
        title: "Fallback open",
        body: "Browser blocks the first attempt",
        url: "https://example.com/path",
      },
    })

    act(() => {
      vi.advanceTimersByTime(0)
    })
    fireEvent.click(screen.getByText("notifications:toast.open"))

    expect(openSpy).toHaveBeenCalledTimes(2)
    act(() => {
      vi.advanceTimersByTime(300)
    })
    expect(screen.queryByText("Fallback open")).not.toBeInTheDocument()
    openSpy.mockRestore()
  })

  it("opens a same-origin action in the current tab", async () => {
    const openSpy = vi.spyOn(window, "open").mockReturnValue(null)
    render(<LivePushToasts />)

    await dispatchSwMessage({
      type: "PUSH_NOTIFICATION",
      toast: {
        id: "t-same-origin",
        title: "Open internally",
        body: "Same-origin action",
        url: "/events/42",
      },
    })
    act(() => {
      vi.advanceTimersByTime(0)
    })

    fireEvent.click(screen.getByText("notifications:toast.open"))

    expect(openSpy).toHaveBeenCalledWith(`${window.location.origin}/events/42`, "_self", undefined)
    openSpy.mockRestore()
  })

  it("strips an unsafe (non-http) URL so no action button is shown", async () => {
    render(<LivePushToasts />)

    await dispatchSwMessage({
      type: "PUSH_NOTIFICATION",
      toast: {
        id: "t-bad-url",
        title: "No link",
        body: "Unsafe scheme",
        url: "javascript:alert(1)",
      },
    })

    act(() => {
      vi.advanceTimersByTime(0)
    })

    expect(screen.getByText("No link")).toBeInTheDocument()
    expect(screen.queryByText("notifications:toast.open")).not.toBeInTheDocument()
  })

  it("auto-dismisses the toast after TOAST_LONG via the timeout", async () => {
    render(<LivePushToasts />)

    act(() => {
      messageHandler?.({
        data: {
          type: "PUSH_NOTIFICATION",
          toast: { id: "t-auto", title: "Auto", body: "Goes away" },
        },
      } as MessageEvent)
    })
    // flush the enqueue microtask + the queue→current effect
    act(() => {
      vi.advanceTimersByTime(0)
    })

    expect(screen.getByText("Auto")).toBeInTheDocument()

    // TOAST_LONG (6000) + the 300ms handleClose unmount delay.
    act(() => {
      vi.advanceTimersByTime(6000 + 300)
    })

    expect(screen.queryByText("Auto")).not.toBeInTheDocument()
  })

  it("flushes buffered toasts from localStorage on a visibility change to visible", async () => {
    // Seed a buffered toast directly into storage (as if it arrived while hidden).
    window.localStorage.setItem(
      BUFFER_STORAGE_KEY,
      JSON.stringify([{ id: "buffered-1", title: "Buffered", body: "From storage" }])
    )

    render(<LivePushToasts />)

    act(() => {
      vi.advanceTimersByTime(0)
    })

    expect(screen.getByText("Buffered")).toBeInTheDocument()
    // Buffer is consumed (cleared) after flushing.
    expect(window.localStorage.getItem(BUFFER_STORAGE_KEY)).toBe("[]")
  })

  it("restores tag/timestamp ids and filters malformed buffered entries", () => {
    window.localStorage.setItem(
      BUFFER_STORAGE_KEY,
      JSON.stringify([
        null,
        42,
        {},
        { tag: "buffer-tag", title: "Tagged", body: "Tag id" },
        { timestamp: 1700000000000, title: "Timestamped", body: "Timestamp id" },
      ])
    )

    render(<LivePushToasts />)
    act(() => {
      vi.advanceTimersByTime(0)
    })

    expect(screen.getByText("Tagged")).toBeInTheDocument()
    expect(screen.queryByText("Timestamped")).not.toBeInTheDocument()
    expect(window.localStorage.getItem(BUFFER_STORAGE_KEY)).toBe("[]")
  })

  it("ignores a non-array persisted buffer", () => {
    window.localStorage.setItem(BUFFER_STORAGE_KEY, JSON.stringify({ unexpected: true }))

    render(<LivePushToasts />)

    expect(screen.queryByRole("heading", { level: 4 })).not.toBeInTheDocument()
  })

  it("ignores a storage read failure while flushing the buffer", () => {
    const getItemSpy = vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("storage unavailable")
    })

    render(<LivePushToasts />)

    expect(screen.queryByRole("heading", { level: 4 })).not.toBeInTheDocument()
    getItemSpy.mockRestore()
  })

  it("buffers a PUSH_NOTIFICATION when the document is hidden instead of showing it", async () => {
    const visibilitySpy = vi.spyOn(document, "visibilityState", "get").mockReturnValue("hidden")
    render(<LivePushToasts />)

    await dispatchSwMessage({
      type: "PUSH_NOTIFICATION",
      toast: { id: "hidden-1", title: "Hidden push", body: "Should buffer" },
    })

    // Not rendered while hidden …
    expect(screen.queryByText("Hidden push")).not.toBeInTheDocument()
    // … but written to the buffer for later flush.
    const raw = window.localStorage.getItem(BUFFER_STORAGE_KEY)
    expect(raw).toContain("hidden-1")

    visibilitySpy.mockRestore()
  })

  it("ignores a storage write failure while buffering a hidden push", async () => {
    const visibilitySpy = vi.spyOn(document, "visibilityState", "get").mockReturnValue("hidden")
    const setItemSpy = vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("storage unavailable")
    })
    render(<LivePushToasts />)

    await dispatchSwMessage({
      type: "PUSH_NOTIFICATION",
      toast: { id: "hidden-write-failure", title: "Hidden push", body: "Should be ignored" },
    })

    expect(screen.queryByText("Hidden push")).not.toBeInTheDocument()
    setItemSpy.mockRestore()
    visibilitySpy.mockRestore()
  })

  it("ignores unrelated service-worker message types", async () => {
    render(<LivePushToasts />)

    await dispatchSwMessage({ type: "SOME_OTHER_TYPE" })

    expect(screen.queryByRole("heading", { level: 4 })).not.toBeInTheDocument()
  })
})
