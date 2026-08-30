import { act, render, screen } from "@testing-library/react"
import { renderToString } from "react-dom/server"
import { useEffect, useState } from "react"
import { afterEach, describe, expect, it, vi } from "vitest"
import { DEFERRED_OVERLAY_DELAY_MS, DeferredGlobalOverlays } from "../DeferredGlobalOverlays"

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

    vi.useFakeTimers()
    render(<DeferredGlobalOverlays />)
    expect(screen.queryByTestId("deferred-search")).not.toBeInTheDocument()

    await act(async () => {
      vi.advanceTimersByTime(DEFERRED_OVERLAY_DELAY_MS)
      await Promise.resolve()
      await Promise.resolve()
    })
    expect(screen.getByTestId("deferred-search")).toBeInTheDocument()
    expect(screen.getByTestId("deferred-live-push")).toBeInTheDocument()
    expect(screen.getByTestId("deferred-offline")).toBeInTheDocument()
    expect(screen.getByTestId("deferred-install")).toBeInTheDocument()
  })

  it("promotes optional overlays immediately after an explicit interaction", async () => {
    vi.useFakeTimers()
    render(<DeferredGlobalOverlays />)

    await act(async () => {
      window.dispatchEvent(new Event("keydown"))
      await Promise.resolve()
    })

    expect(screen.getByTestId("deferred-search")).toBeInTheDocument()
    expect(screen.getByTestId("deferred-live-push")).toBeInTheDocument()
    expect(screen.getByTestId("deferred-install")).toBeInTheDocument()
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

  it("uses requestIdleCallback when the browser provides it", async () => {
    vi.useFakeTimers()
    let idleCallback: (() => void) | undefined
    const requestIdleCallback = vi.fn((callback: () => void) => {
      idleCallback = callback
      return 17
    })
    const cancelIdleCallback = vi.fn()
    Object.defineProperty(window, "requestIdleCallback", {
      configurable: true,
      value: requestIdleCallback,
    })
    Object.defineProperty(window, "cancelIdleCallback", {
      configurable: true,
      value: cancelIdleCallback,
    })

    try {
      render(<DeferredGlobalOverlays />)

      await act(async () => {
        vi.advanceTimersByTime(DEFERRED_OVERLAY_DELAY_MS)
        await Promise.resolve()
      })

      expect(requestIdleCallback).toHaveBeenCalledWith(expect.any(Function), { timeout: 2_000 })
      expect(screen.queryByTestId("deferred-search")).not.toBeInTheDocument()

      await act(async () => {
        idleCallback?.()
        await Promise.resolve()
      })
      expect(screen.getByTestId("deferred-search")).toBeInTheDocument()
      expect(cancelIdleCallback).not.toHaveBeenCalled()
    } finally {
      delete (window as Window & { requestIdleCallback?: unknown }).requestIdleCallback
      delete (window as Window & { cancelIdleCallback?: unknown }).cancelIdleCallback
    }
  })

  it("cancels a pending idle callback when interaction promotes the overlays", async () => {
    vi.useFakeTimers()
    let idleCallback: (() => void) | undefined
    const requestIdleCallback = vi.fn((callback: () => void) => {
      idleCallback = callback
      return 23
    })
    const cancelIdleCallback = vi.fn()
    Object.defineProperty(window, "requestIdleCallback", {
      configurable: true,
      value: requestIdleCallback,
    })
    Object.defineProperty(window, "cancelIdleCallback", {
      configurable: true,
      value: cancelIdleCallback,
    })

    try {
      const { unmount } = render(<DeferredGlobalOverlays />)
      await act(async () => {
        vi.advanceTimersByTime(DEFERRED_OVERLAY_DELAY_MS)
        await Promise.resolve()
      })

      await act(async () => {
        window.dispatchEvent(new Event("pointerdown"))
        await Promise.resolve()
      })

      expect(cancelIdleCallback).toHaveBeenCalledWith(23)
      expect(screen.getByTestId("deferred-search")).toBeInTheDocument()
      // A cancelled callback must be harmless if a browser races delivery
      // with cancellation; the mounted guard keeps this idempotent.
      await act(async () => {
        idleCallback?.()
        await Promise.resolve()
      })
      expect(screen.getByTestId("deferred-search")).toBeInTheDocument()
      unmount()
      await act(async () => {
        idleCallback?.()
        await Promise.resolve()
      })
    } finally {
      delete (window as Window & { requestIdleCallback?: unknown }).requestIdleCallback
      delete (window as Window & { cancelIdleCallback?: unknown }).cancelIdleCallback
    }
  })

  it("does not promote after an unmounted timer callback races cleanup", () => {
    vi.useFakeTimers()
    const setTimeoutSpy = vi.spyOn(window, "setTimeout")
    const { unmount } = render(<DeferredGlobalOverlays />)
    const timerCall = setTimeoutSpy.mock.calls.find(
      ([, delay]) => delay === DEFERRED_OVERLAY_DELAY_MS
    )
    const timerCallback = timerCall?.[0] as (() => void) | undefined

    unmount()
    timerCallback?.()

    expect(screen.queryByTestId("deferred-search")).not.toBeInTheDocument()
    setTimeoutSpy.mockRestore()
  })

  it("ignores a late interaction callback after unmount", () => {
    const addEventListenerSpy = vi.spyOn(window, "addEventListener")
    const { unmount } = render(<DeferredGlobalOverlays />)
    const keydownCall = addEventListenerSpy.mock.calls.find(
      ([eventName]) => eventName === "keydown"
    )
    const promoteOnInteraction = keydownCall?.[1] as EventListener | undefined

    unmount()
    promoteOnInteraction?.(new Event("keydown"))

    expect(screen.queryByTestId("deferred-search")).not.toBeInTheDocument()
    addEventListenerSpy.mockRestore()
  })

  it("cancels a pending idle callback during unmount cleanup", async () => {
    vi.useFakeTimers()
    let idleCallback: (() => void) | undefined
    const requestIdleCallback = vi.fn((callback: () => void) => {
      idleCallback = callback
      return 31
    })
    const cancelIdleCallback = vi.fn()
    Object.defineProperty(window, "requestIdleCallback", {
      configurable: true,
      value: requestIdleCallback,
    })
    Object.defineProperty(window, "cancelIdleCallback", {
      configurable: true,
      value: cancelIdleCallback,
    })

    try {
      const { unmount } = render(<DeferredGlobalOverlays />)
      await act(async () => {
        vi.advanceTimersByTime(DEFERRED_OVERLAY_DELAY_MS)
        await Promise.resolve()
      })

      unmount()
      expect(cancelIdleCallback).toHaveBeenCalledWith(31)
      await act(async () => {
        idleCallback?.()
        await Promise.resolve()
      })
    } finally {
      delete (window as Window & { requestIdleCallback?: unknown }).requestIdleCallback
      delete (window as Window & { cancelIdleCallback?: unknown }).cancelIdleCallback
    }
  })
})
