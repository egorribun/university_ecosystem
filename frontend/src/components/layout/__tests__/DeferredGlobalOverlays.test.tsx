import { render, screen, waitFor } from "@testing-library/react"
import { renderToString } from "react-dom/server"
import { useEffect, useState } from "react"
import { afterEach, describe, expect, it, vi } from "vitest"
import { DeferredGlobalOverlays } from "../DeferredGlobalOverlays"

function MockOfflineIndicator() {
  const [mounted, setMounted] = useState(false)
  useEffect(() => setMounted(true), [])
  return mounted ? <div data-testid="deferred-offline" /> : null
}

vi.mock("@/components/search/SearchDialog", () => ({
  SearchDialog: () => <div data-testid="deferred-search" />,
}))
vi.mock("@/components/feedback/LivePushToasts", () => ({
  default: () => <div data-testid="deferred-live-push" />,
}))
vi.mock("@/components/feedback/OfflineIndicator", () => ({
  default: MockOfflineIndicator,
}))
vi.mock("@/components/pwa/InstallPrompt", () => ({
  default: () => <div data-testid="deferred-install" />,
}))

describe("DeferredGlobalOverlays", () => {
  afterEach(() => {
    vi.useRealTimers()
  })

  it("keeps the server and first client render empty, then mounts every overlay", async () => {
    expect(renderToString(<DeferredGlobalOverlays />)).toBe("")

    render(<DeferredGlobalOverlays />)
    expect(screen.queryByTestId("deferred-search")).not.toBeInTheDocument()

    await waitFor(() => {
      expect(screen.getByTestId("deferred-search")).toBeInTheDocument()
      expect(screen.getByTestId("deferred-live-push")).toBeInTheDocument()
      expect(screen.getByTestId("deferred-offline")).toBeInTheDocument()
      expect(screen.getByTestId("deferred-install")).toBeInTheDocument()
    })
  })

  it("mounts the offline indicator before deferred convenience overlays", () => {
    render(<DeferredGlobalOverlays />)

    // Offline/online transitions are browser events and can fire in the same
    // task as the first authenticated navigation. The indicator must be
    // subscribed before the optional search, push, and install surfaces are
    // ready so an early `offline` event cannot be lost.
    expect(screen.getByTestId("deferred-offline")).toBeInTheDocument()
    expect(screen.queryByTestId("deferred-search")).not.toBeInTheDocument()
  })

  it("cancels the deferred task when the tree unmounts", () => {
    vi.useFakeTimers()
    const clearTimeout = vi.spyOn(window, "clearTimeout")
    const { unmount } = render(<DeferredGlobalOverlays />)

    unmount()
    vi.runOnlyPendingTimers()

    expect(clearTimeout).toHaveBeenCalled()
    expect(screen.queryByTestId("deferred-search")).not.toBeInTheDocument()
    clearTimeout.mockRestore()
  })
})
