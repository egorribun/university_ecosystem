import { renderHook, act } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { useLocalStorage } from "../useLocalStorage"

// Suppress expected warning logs in error-path tests
vi.mock("@/app/logger", () => ({
  logWarning: vi.fn(),
}))

describe("useLocalStorage", () => {
  beforeEach(() => {
    localStorage.clear()
    vi.restoreAllMocks()
    vi.clearAllMocks()
  })

  afterEach(() => {
    localStorage.clear()
  })

  // ---------------------------------------------------------------------------
  // Initial value
  // ---------------------------------------------------------------------------
  it("returns the initialValue when no stored value exists", () => {
    const { result } = renderHook(() => useLocalStorage("test-key", "default"))
    const [value] = result.current
    expect(value).toBe("default")
  })

  it("reads an existing stored value on mount", () => {
    localStorage.setItem("pre-key", JSON.stringify(42))
    const { result } = renderHook(() => useLocalStorage("pre-key", 0))
    const [value] = result.current
    expect(value).toBe(42)
  })

  it("accepts an initializer function", () => {
    const { result } = renderHook(() => useLocalStorage("fn-key", () => "lazy"))
    const [value] = result.current
    expect(value).toBe("lazy")
  })

  it("skips localStorage read when initializeWithValue=false", () => {
    localStorage.setItem("skip-key", JSON.stringify("stored"))
    const { result } = renderHook(() =>
      useLocalStorage("skip-key", "fallback", { initializeWithValue: false })
    )
    expect(result.current[0]).toBe("fallback")
  })

  it("uses a lazy initializer when initialization is deferred and a key is cleared", () => {
    const initializer = vi.fn(() => "lazy-fallback")
    const { result } = renderHook(() =>
      useLocalStorage("deferred-key", initializer, { initializeWithValue: false })
    )

    expect(result.current[0]).toBe("lazy-fallback")

    act(() => {
      window.dispatchEvent(
        new StorageEvent("storage", {
          key: "deferred-key",
          newValue: null,
        })
      )
    })

    expect(result.current[0]).toBe("lazy-fallback")
    expect(initializer).toHaveBeenCalled()

    act(() => result.current[2]())
    expect(result.current[0]).toBe("lazy-fallback")
  })

  // ---------------------------------------------------------------------------
  // setValue
  // ---------------------------------------------------------------------------
  it("updates state and persists to localStorage", () => {
    const { result } = renderHook(() => useLocalStorage("count-key", 0))

    act(() => {
      const [, setValue] = result.current
      setValue(10)
    })

    const [value] = result.current
    expect(value).toBe(10)
    expect(JSON.parse(localStorage.getItem("count-key")!)).toBe(10)
  })

  it("accepts a function updater (like useState)", () => {
    const { result } = renderHook(() => useLocalStorage("fn-update-key", 5))

    act(() => {
      const [, setValue] = result.current
      setValue((prev) => prev + 1)
    })

    const [value] = result.current
    expect(value).toBe(6)
  })

  it("dispatches a StorageEvent on setValue for cross-tab sync", () => {
    const { result } = renderHook(() => useLocalStorage("event-key", ""))
    const events: StorageEvent[] = []
    const handler = (e: StorageEvent) => events.push(e)
    window.addEventListener("storage", handler)

    act(() => {
      const [, setValue] = result.current
      setValue("new-val")
    })

    window.removeEventListener("storage", handler)
    const storageEvent = events.find((e) => e.key === "event-key")
    expect(storageEvent).toBeDefined()
    expect(storageEvent?.newValue).toBe(JSON.stringify("new-val"))
  })

  // ---------------------------------------------------------------------------
  // removeValue
  // ---------------------------------------------------------------------------
  it("removes the key from localStorage and resets state to initialValue", () => {
    const { result } = renderHook(() => useLocalStorage("rm-key", "initial"))

    act(() => {
      const [, setValue] = result.current
      setValue("changed")
    })

    act(() => {
      const [, , removeValue] = result.current
      removeValue()
    })

    const [value] = result.current
    expect(value).toBe("initial")
    expect(localStorage.getItem("rm-key")).toBeNull()
  })

  // ---------------------------------------------------------------------------
  // Cross-tab sync via StorageEvent
  // ---------------------------------------------------------------------------
  it("reacts to external StorageEvent with a new value", () => {
    const { result } = renderHook(() => useLocalStorage("sync-key", "old"))

    act(() => {
      window.dispatchEvent(
        new StorageEvent("storage", {
          key: "sync-key",
          newValue: JSON.stringify("from-other-tab"),
        })
      )
    })

    const [value] = result.current
    expect(value).toBe("from-other-tab")
  })

  it("resets to initialValue when StorageEvent newValue is null (key cleared)", () => {
    const { result } = renderHook(() => useLocalStorage("cleared-key", "fallback"))

    act(() => {
      const [, setValue] = result.current
      setValue("something")
    })

    act(() => {
      window.dispatchEvent(
        new StorageEvent("storage", {
          key: "cleared-key",
          newValue: null,
        })
      )
    })

    const [value] = result.current
    expect(value).toBe("fallback")
  })

  it("ignores StorageEvent for a different key", () => {
    const { result } = renderHook(() => useLocalStorage("my-key", "original"))

    act(() => {
      window.dispatchEvent(
        new StorageEvent("storage", {
          key: "other-key",
          newValue: JSON.stringify("unrelated"),
        })
      )
    })

    const [value] = result.current
    expect(value).toBe("original")
  })

  // ---------------------------------------------------------------------------
  // Custom serializer / deserializer
  // ---------------------------------------------------------------------------
  it("uses a custom serializer and deserializer", () => {
    const { result } = renderHook(() =>
      useLocalStorage<number[]>("custom-key", [], {
        serializer: (arr) => arr.join(","),
        deserializer: (str) => str.split(",").map(Number),
      })
    )

    act(() => {
      const [, setValue] = result.current
      setValue([1, 2, 3])
    })

    expect(localStorage.getItem("custom-key")).toBe("1,2,3")
    const [value] = result.current
    expect(value).toEqual([1, 2, 3])
  })

  // ---------------------------------------------------------------------------
  // Error handling branches
  // ---------------------------------------------------------------------------
  it("gracefully catches read errors and logs them", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("Simulated localStorage read failure")
    })
    const { result } = renderHook(() => useLocalStorage("fail-read-key", "fallback"))
    expect(result.current[0]).toBe("fallback")
  })

  it("gracefully catches write errors in setValue", () => {
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("Simulated localStorage write failure")
    })
    const { result } = renderHook(() => useLocalStorage("fail-write-key", "initial"))
    act(() => {
      result.current[1]("updated")
    })
    // State should still be updated locally even if localStorage save fails
    expect(result.current[0]).toBe("updated")
  })

  it("gracefully catches errors in removeValue", () => {
    vi.spyOn(Storage.prototype, "removeItem").mockImplementation(() => {
      throw new Error("Simulated localStorage remove failure")
    })
    const { result } = renderHook(() => useLocalStorage("fail-rm-key", "initial"))
    act(() => {
      result.current[2]()
    })
    expect(result.current[0]).toBe("initial")
  })

  it("handles deserialization undefined string", () => {
    localStorage.setItem("undef-key", "undefined")
    const { result } = renderHook(() => useLocalStorage("undef-key", "fallback"))
    expect(result.current[0]).toBeUndefined()
  })

  it("logs sync error during storage event if JSON parsing fails", () => {
    const { result } = renderHook(() => useLocalStorage<string | null>("sync-err-key", "initial"))
    act(() => {
      window.dispatchEvent(
        new StorageEvent("storage", {
          key: "sync-err-key",
          newValue: "invalid { json",
        })
      )
    })
    // State remains unchanged on sync failure
    expect(result.current[0]).toBe("initial")
  })
})
