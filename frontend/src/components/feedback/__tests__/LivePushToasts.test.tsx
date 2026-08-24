import { act, render, screen, fireEvent } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

vi.mock("framer-motion", async () =>
  (await import("@/tests/helpers/framerMotionMock")).framerMotionMock()
)
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
