import { renderHook, act } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { useLocalStorage } from "../useLocalStorage"

describe("useLocalStorage", () => {
  beforeEach(() => {
    localStorage.clear()
    vi.spyOn(console, "warn").mockImplementation(() => {})
  })

  afterEach(() => {
    vi.restoreAllMocks()
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
})
