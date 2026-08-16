import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { Activity } from "react"
import { render, renderHook } from "@testing-library/react"

import { usePushSync } from "./usePushSync"

const { mockPush, mockLogger } = vi.hoisted(() => ({
  mockPush: {
    isPushSupported: vi.fn(() => false),
    hasPushConsent: vi.fn(() => false),
    recoverPushConsentFromBrowser: vi.fn().mockResolvedValue(false),
    softSyncPushSubscription: vi.fn().mockResolvedValue(undefined),
  },
  mockLogger: {
    logWarning: vi.fn(),
    logDebug: vi.fn(),
    logError: vi.fn(),
  },
}))

vi.mock("@/push/subscribe", () => mockPush)
vi.mock("@/app/logger", () => mockLogger)

beforeEach(() => {
  vi.useFakeTimers()
  vi.clearAllMocks()

  // Setup Notification global
  vi.stubGlobal("Notification", {})
})

afterEach(() => {
  vi.runOnlyPendingTimers()
  vi.useRealTimers()
  vi.unstubAllGlobals()
})

describe("usePushSync — gating", () => {
  it("does not schedule a sync when isAuthenticated=false", () => {
    renderHook(() => usePushSync(false))
    expect(vi.getTimerCount()).toBe(0)
  })

  it("schedules a 100ms-debounced sync when isAuthenticated=true", () => {
    renderHook(() => usePushSync(true))
    expect(vi.getTimerCount()).toBe(1)
  })

  it("clears the pending timer on unmount", () => {
    const { unmount } = renderHook(() => usePushSync(true))
    expect(vi.getTimerCount()).toBe(1)
    unmount()
    expect(vi.getTimerCount()).toBe(0)
  })

  it("does not re-schedule on re-render with same auth state", async () => {
    const { rerender } = renderHook(({ auth }: { auth: boolean }) => usePushSync(auth), {
      initialProps: { auth: true },
    })
    expect(vi.getTimerCount()).toBe(1)

    await vi.runAllTimersAsync()
    expect(vi.getTimerCount()).toBe(0)

    rerender({ auth: true })
    expect(vi.getTimerCount()).toBe(0)
  })

  it("re-schedules after a logout → login cycle", async () => {
    const { rerender } = renderHook(({ auth }: { auth: boolean }) => usePushSync(auth), {
      initialProps: { auth: true },
    })
    await vi.runAllTimersAsync()

    rerender({ auth: false })
    expect(vi.getTimerCount()).toBe(0)

    rerender({ auth: true })
    expect(vi.getTimerCount()).toBe(1)
  })

  it("does not repeat a completed sync when React Activity restores effects", async () => {
    mockPush.isPushSupported.mockReturnValue(true)
    mockPush.recoverPushConsentFromBrowser.mockResolvedValue(true)
    mockPush.hasPushConsent.mockReturnValue(false)
    const Probe = () => {
      usePushSync(true)
      return null
    }
    const tree = (mode: "visible" | "hidden") => (
      <Activity mode={mode}>
        <Probe />
      </Activity>
    )

    const view = render(tree("visible"))
    await vi.runAllTimersAsync()
    expect(mockPush.softSyncPushSubscription).toHaveBeenCalledOnce()

    view.rerender(tree("hidden"))
    view.rerender(tree("visible"))
    await vi.runAllTimersAsync()

    expect(mockPush.softSyncPushSubscription).toHaveBeenCalledOnce()
  })
})

describe("usePushSync — internal flows", () => {
  it("bails out early if push is not supported", async () => {
    mockPush.isPushSupported.mockReturnValue(false)
    renderHook(() => usePushSync(true))

    await vi.runAllTimersAsync()
    expect(mockPush.recoverPushConsentFromBrowser).not.toHaveBeenCalled()
  })

  it("bails out early if Notification is undefined", async () => {
    mockPush.isPushSupported.mockReturnValue(true)
    vi.stubGlobal("Notification", undefined)

    renderHook(() => usePushSync(true))

    await vi.runAllTimersAsync()
    expect(mockPush.recoverPushConsentFromBrowser).not.toHaveBeenCalled()
  })

  it("skips soft sync if no consent is found or recovered", async () => {
    mockPush.isPushSupported.mockReturnValue(true)
    mockPush.recoverPushConsentFromBrowser.mockResolvedValue(false)
    mockPush.hasPushConsent.mockReturnValue(false)

    renderHook(() => usePushSync(true))

    await vi.runAllTimersAsync()
    expect(mockPush.softSyncPushSubscription).not.toHaveBeenCalled()
  })

  it("calls soft sync if consent is recovered", async () => {
    mockPush.isPushSupported.mockReturnValue(true)
    mockPush.recoverPushConsentFromBrowser.mockResolvedValue(true)
    mockPush.hasPushConsent.mockReturnValue(false)

    renderHook(() => usePushSync(true))

    await vi.runAllTimersAsync()
    expect(mockPush.softSyncPushSubscription).toHaveBeenCalled()
  })

  it("calls soft sync if consent exists", async () => {
    mockPush.isPushSupported.mockReturnValue(true)
    mockPush.recoverPushConsentFromBrowser.mockResolvedValue(false)
    mockPush.hasPushConsent.mockReturnValue(true)

    renderHook(() => usePushSync(true))

    await vi.runAllTimersAsync()
    expect(mockPush.softSyncPushSubscription).toHaveBeenCalled()
  })

  it("stops after consent recovery when the hook unmounts", async () => {
    let resolveRecovery!: (recovered: boolean) => void
    mockPush.isPushSupported.mockReturnValue(true)
    mockPush.recoverPushConsentFromBrowser.mockReturnValue(
      new Promise<boolean>((resolve) => {
        resolveRecovery = resolve
      })
    )
    mockPush.hasPushConsent.mockReturnValue(true)

    const { unmount } = renderHook(() => usePushSync(true))
    await vi.advanceTimersByTimeAsync(100)
    expect(mockPush.recoverPushConsentFromBrowser).toHaveBeenCalledOnce()

    unmount()
    resolveRecovery(false)
    await Promise.resolve()
    await Promise.resolve()

    expect(mockPush.hasPushConsent).not.toHaveBeenCalled()
    expect(mockPush.softSyncPushSubscription).not.toHaveBeenCalled()
  })

  it("logs warning and error if softSync fails", async () => {
    mockPush.isPushSupported.mockReturnValue(true)
    mockPush.hasPushConsent.mockReturnValue(true)
    const err = new Error("Sync failed")
    mockPush.softSyncPushSubscription.mockRejectedValue(err)

    renderHook(() => usePushSync(true))

    await vi.runAllTimersAsync()
    expect(mockLogger.logWarning).toHaveBeenCalledWith(
      "Failed to sync push subscription on app load",
      err
    )
    expect(mockLogger.logError).toHaveBeenCalledWith("[usePushSync] Error:", err)
  })
})
