import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { renderHook } from "@testing-library/react"

import { usePushSync } from "./usePushSync"

/**
 * usePushSync — global push-subscription sync side-effect, called
 * once when the user is authenticated. Gating contract:
 *
 *  - if not authenticated → no work;
 *  - if authenticated → schedule a setTimeout(100) for the sync;
 *  - sync runs once per "auth-on" episode (re-syncs if user logs out
 *    then back in);
 *  - dynamic import of ``@/push/subscribe`` is mocked globally in
 *    setupTests.ts (recoverPushConsentFromBrowser → false,
 *    isPushSupported → false), so the real branch covered here is
 *    "isPushSupported returns false → bail out without softSync".
 */

beforeEach(() => {
  vi.useFakeTimers()
})

afterEach(() => {
  vi.runOnlyPendingTimers()
  vi.useRealTimers()
})

describe("usePushSync — gating", () => {
  it("does not schedule a sync when isAuthenticated=false", () => {
    // No timers should be scheduled — verify by counting pending timers.
    renderHook(() => usePushSync(false))
    expect(vi.getTimerCount()).toBe(0)
  })

  it("schedules a 100ms-debounced sync when isAuthenticated=true", () => {
    renderHook(() => usePushSync(true))
    // The hook calls setTimeout(... , 100).
    expect(vi.getTimerCount()).toBe(1)
  })

  it("clears the pending timer on unmount", () => {
    const { unmount } = renderHook(() => usePushSync(true))
    expect(vi.getTimerCount()).toBe(1)
    unmount()
    expect(vi.getTimerCount()).toBe(0)
  })

  it("does not re-schedule on re-render with same auth state", async () => {
    // First render schedules.
    const { rerender } = renderHook(({ auth }: { auth: boolean }) => usePushSync(auth), {
      initialProps: { auth: true },
    })
    expect(vi.getTimerCount()).toBe(1)

    // Drain the first scheduled timer so the syncedRef flag flips.
    await vi.runAllTimersAsync()
    expect(vi.getTimerCount()).toBe(0)

    // Re-render without auth-state change — no new timer.
    rerender({ auth: true })
    expect(vi.getTimerCount()).toBe(0)
  })

  it("re-schedules after a logout → login cycle", async () => {
    const { rerender } = renderHook(({ auth }: { auth: boolean }) => usePushSync(auth), {
      initialProps: { auth: true },
    })
    await vi.runAllTimersAsync() // drain initial sync

    // Log out — no sync.
    rerender({ auth: false })
    expect(vi.getTimerCount()).toBe(0)

    // Log back in — a new sync timer must be scheduled.
    rerender({ auth: true })
    expect(vi.getTimerCount()).toBe(1)
  })
})
