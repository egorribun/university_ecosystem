import { renderHook, act } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { useOnlineStatus } from "../useOnlineStatus"

describe("useOnlineStatus", () => {
  beforeEach(() => {
    // Ensure a clean baseline
    Object.defineProperty(navigator, "onLine", {
      configurable: true,
      get: () => true,
    })
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it("returns true when navigator.onLine is true", () => {
    const { result } = renderHook(() => useOnlineStatus())
    expect(result.current).toBe(true)
  })

  it("returns false when navigator.onLine is false at mount", () => {
    Object.defineProperty(navigator, "onLine", {
      configurable: true,
      get: () => false,
    })
    const { result } = renderHook(() => useOnlineStatus())
    expect(result.current).toBe(false)
  })

  it("reacts to 'offline' browser event", () => {
    const { result } = renderHook(() => useOnlineStatus())
    expect(result.current).toBe(true)

    act(() => {
      window.dispatchEvent(new Event("offline"))
    })

    expect(result.current).toBe(false)
  })

  it("reacts to 'online' browser event after going offline", () => {
    const { result } = renderHook(() => useOnlineStatus())

    act(() => {
      window.dispatchEvent(new Event("offline"))
    })
    expect(result.current).toBe(false)

    act(() => {
      window.dispatchEvent(new Event("online"))
    })
    expect(result.current).toBe(true)
  })

  it("cleans up event listeners on unmount", () => {
    const addSpy = vi.spyOn(window, "addEventListener")
    const removeSpy = vi.spyOn(window, "removeEventListener")

    const { unmount } = renderHook(() => useOnlineStatus())
    unmount()

    // Both online and offline listeners should have been removed
    expect(removeSpy).toHaveBeenCalledWith("online", expect.any(Function))
    expect(removeSpy).toHaveBeenCalledWith("offline", expect.any(Function))
    addSpy.mockRestore()
    removeSpy.mockRestore()
  })

  it("handles rapid online/offline toggling without errors", () => {
    const { result } = renderHook(() => useOnlineStatus())
    act(() => {
      window.dispatchEvent(new Event("offline"))
    })
    act(() => {
      window.dispatchEvent(new Event("online"))
    })
    act(() => {
      window.dispatchEvent(new Event("offline"))
    })
    expect(typeof result.current).toBe("boolean")
  })

  it("returns true when navigator is undefined (SSR environment)", () => {
    const originalNavigator = global.navigator
    // @ts-expect-error: delete global.navigator to mock SSR environment where navigator is undefined
    delete global.navigator

    const { result } = renderHook(() => useOnlineStatus())
    expect(result.current).toBe(true)

    // Restore original navigator
    global.navigator = originalNavigator
  })
})
