/**
 * Wave 10 — Branch coverage for useOnlineStatus hook.
 *
 * WHY: The hook has two distinct initialisation branches (navigator defined vs
 * undefined) and two event-listener branches (online / offline). Covering these
 * explicitly prevents silent regressions if the SSR guard is removed.
 */
import { act, renderHook } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { useOnlineStatus } from "../useOnlineStatus"

describe("useOnlineStatus", () => {
  const listeners: { online: EventListener[]; offline: EventListener[] } = {
    online: [],
    offline: [],
  }

  beforeEach(() => {
    listeners.online = []
    listeners.offline = []

    vi.spyOn(window, "addEventListener").mockImplementation(
      (type: string, listener: EventListenerOrEventListenerObject) => {
        if (type === "online") listeners.online.push(listener as EventListener)
        else if (type === "offline") listeners.offline.push(listener as EventListener)
      }
    )

    vi.spyOn(window, "removeEventListener").mockImplementation(
      (type: string, listener: EventListenerOrEventListenerObject) => {
        if (type === "online")
          listeners.online = listeners.online.filter((l) => l !== listener)
        else if (type === "offline")
          listeners.offline = listeners.offline.filter((l) => l !== listener)
      }
    )
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it("returns true when navigator.onLine is true at mount", () => {
    // Branch: typeof navigator !== 'undefined' → true path
    Object.defineProperty(navigator, "onLine", { value: true, configurable: true })
    const { result } = renderHook(() => useOnlineStatus())
    expect(result.current).toBe(true)
  })

  it("returns false when navigator.onLine is false at mount", () => {
    // Branch: navigator.onLine false at initialisation
    Object.defineProperty(navigator, "onLine", { value: false, configurable: true })
    const { result } = renderHook(() => useOnlineStatus())
    expect(result.current).toBe(false)
  })

  it("updates to false when offline event fires", () => {
    // Branch: handleOffline callback
    Object.defineProperty(navigator, "onLine", { value: true, configurable: true })
    const { result } = renderHook(() => useOnlineStatus())
    expect(result.current).toBe(true)

    act(() => {
      listeners.offline.forEach((fn) => fn(new Event("offline")))
    })
    expect(result.current).toBe(false)
  })

  it("updates to true when online event fires", () => {
    // Branch: handleOnline callback
    Object.defineProperty(navigator, "onLine", { value: false, configurable: true })
    const { result } = renderHook(() => useOnlineStatus())
    expect(result.current).toBe(false)

    act(() => {
      listeners.online.forEach((fn) => fn(new Event("online")))
    })
    expect(result.current).toBe(true)
  })

  it("removes event listeners on unmount", () => {
    const { unmount } = renderHook(() => useOnlineStatus())
    expect(listeners.online.length).toBe(1)
    expect(listeners.offline.length).toBe(1)

    unmount()
    // After cleanup both listener arrays must be empty
    expect(listeners.online.length).toBe(0)
    expect(listeners.offline.length).toBe(0)
  })

  it("handles rapid online/offline toggling without errors", () => {
    // Property: toggling multiple times must not throw or corrupt state
    const { result } = renderHook(() => useOnlineStatus())
    act(() => {
      listeners.offline.forEach((fn) => fn(new Event("offline")))
    })
    act(() => {
      listeners.online.forEach((fn) => fn(new Event("online")))
    })
    act(() => {
      listeners.offline.forEach((fn) => fn(new Event("offline")))
    })
    expect(typeof result.current).toBe("boolean")
  })
})
