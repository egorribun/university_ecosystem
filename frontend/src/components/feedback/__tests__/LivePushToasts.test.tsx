import { act, render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

vi.mock("framer-motion", async () =>
  (await import("@/tests/helpers/framerMotionMock")).framerMotionMock()
)
vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => key,
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
    window.localStorage.clear()
    installFakeServiceWorker()
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

    expect(await screen.findByText("Saved")).toBeInTheDocument()
    expect(screen.getByText("Your changes were saved")).toBeInTheDocument()
  })

  it("renders an info toast for an unknown/missing severity (default branch)", async () => {
    render(<LivePushToasts />)

    await dispatchSwMessage({
      type: "PUSH_NOTIFICATION",
      toast: { id: "t-info", title: "Heads up", body: "Something happened" },
    })

    expect(await screen.findByText("Heads up")).toBeInTheDocument()
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

    expect(await screen.findByText("Careful")).toBeInTheDocument()
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

    expect(await screen.findByText("Failed")).toBeInTheDocument()
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

    expect(await screen.findByText("notifications:sync.title")).toBeInTheDocument()
    expect(screen.getByText("notifications:sync.body")).toBeInTheDocument()
  })

  it("dismisses the current toast when the close button is clicked", async () => {
    const user = userEvent.setup()
    render(<LivePushToasts />)

    await dispatchSwMessage({
      type: "PUSH_NOTIFICATION",
      toast: { id: "t-close", title: "Closable", body: "Tap to close" },
    })

    expect(await screen.findByText("Closable")).toBeInTheDocument()

    await user.click(screen.getByRole("button", { name: "common:buttons.close" }))

    await waitFor(() => {
      expect(screen.queryByText("Closable")).not.toBeInTheDocument()
    })
  })

  it("renders an action button when the toast carries a safe URL, and opening it dismisses the toast", async () => {
    const user = userEvent.setup()
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

    const actionButton = await screen.findByText("notifications:toast.open")
    expect(actionButton).toBeInTheDocument()

    await user.click(actionButton)

    expect(openSpy).toHaveBeenCalled()
    await waitFor(() => {
      expect(screen.queryByText("Open me")).not.toBeInTheDocument()
    })

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

    expect(await screen.findByText("No link")).toBeInTheDocument()
    expect(screen.queryByText("notifications:toast.open")).not.toBeInTheDocument()
  })

  it("auto-dismisses the toast after TOAST_LONG via the timeout", async () => {
    vi.useFakeTimers()
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

    // The mount-time visibilitychange handler fires synchronously; the toast
    // surfaces once the queue→current effect runs.
    expect(await screen.findByText("Buffered")).toBeInTheDocument()
    // Buffer is consumed (cleared) after flushing.
    expect(window.localStorage.getItem(BUFFER_STORAGE_KEY)).toBe("[]")
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

  it("ignores unrelated service-worker message types", async () => {
    render(<LivePushToasts />)

    await dispatchSwMessage({ type: "SOME_OTHER_TYPE" })

    expect(screen.queryByRole("heading", { level: 4 })).not.toBeInTheDocument()
  })
})
