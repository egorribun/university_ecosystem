import { afterEach, describe, expect, it, vi } from "vitest"
import { prefetchRouteModules } from "../prefetchRoutes"

const loader = () => vi.fn().mockResolvedValue({})

describe("prefetchRouteModules", () => {
  afterEach(() => {
    vi.useRealTimers()
    vi.unstubAllGlobals()
  })

  it("schedules loading in an idle callback bounded by the timeout", () => {
    vi.useFakeTimers()
    const requestIdleCallback = vi.fn()
    vi.stubGlobal("requestIdleCallback", requestIdleCallback)
    const first = loader()

    prefetchRouteModules([first], { timeoutMs: 250 })

    expect(requestIdleCallback).toHaveBeenCalledExactlyOnceWith(expect.any(Function), {
      timeout: 250,
    })
    vi.advanceTimersByTime(1_000)
    expect(first).not.toHaveBeenCalled()

    requestIdleCallback.mock.calls[0]![0]()
    expect(first).toHaveBeenCalledOnce()
  })

  it("does not schedule anything when every loader was already prefetched", () => {
    const requestIdleCallback = vi.fn()
    vi.stubGlobal("requestIdleCallback", requestIdleCallback)
    const first = loader()

    prefetchRouteModules([first])
    prefetchRouteModules([first])

    expect(requestIdleCallback).toHaveBeenCalledOnce()
  })
})
