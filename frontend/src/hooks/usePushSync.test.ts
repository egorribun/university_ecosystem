import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { renderHook } from "@testing-library/react"

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
