/**
 * Wave 10 — Branch coverage for useLocalStorage hook.
 *
 * WHY: useLocalStorage is a critical cross-cutting concern — it manages dark
 * mode, language preferences, and persisted UI state. It has 9+ distinct
 * branches (initializeWithValue, IS_BROWSER, function-as-value, error paths,
 * storage-event sync). Without test coverage, a regression in any branch
 * silently corrupts user preferences.
 */
import { act, renderHook } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { useLocalStorage } from "../useLocalStorage"

// Suppress expected warning logs in error-path tests
vi.mock("@/app/logger", () => ({
  logWarning: vi.fn(),
}))

describe("useLocalStorage", () => {
  beforeEach(() => {
    localStorage.clear()
    vi.clearAllMocks()
  })

  afterEach(() => {
    localStorage.clear()
  })

  // ── read paths ──────────────────────────────────────────────────────────────

  it("returns the initial value when storage is empty", () => {
    // Branch: raw === null → return initial
    const { result } = renderHook(() => useLocalStorage("test-key", "default"))
    expect(result.current[0]).toBe("default")
  })

  it("reads an existing value from localStorage on mount", () => {
    // Branch: raw !== null → deserialize
    localStorage.setItem("test-key", JSON.stringify("persisted"))
    const { result } = renderHook(() => useLocalStorage("test-key", "default"))
    expect(result.current[0]).toBe("persisted")
  })

  it("accepts a factory function as initialValue", () => {
    // Branch: initialValue instanceof Function → call it
    const { result } = renderHook(() => useLocalStorage("fac-key", () => "from-factory"))
    expect(result.current[0]).toBe("from-factory")
  })

  it("skips localStorage read when initializeWithValue=false", () => {
    // Branch: !initializeWithValue → use initial value without reading storage
    localStorage.setItem("skip-key", JSON.stringify("stored"))
    const { result } = renderHook(() =>
      useLocalStorage("skip-key", "fallback", { initializeWithValue: false })
    )
    // Must return the initialValue, not the stored value
    expect(result.current[0]).toBe("fallback")
  })

  // ── write paths ──────────────────────────────────────────────────────────────

  it("persists a new value to localStorage via setValue", () => {
    // Branch: setValue with plain value → serialise and store
    const { result } = renderHook(() => useLocalStorage("write-key", "initial"))
    act(() => result.current[1]("updated"))
    expect(localStorage.getItem("write-key")).toBe(JSON.stringify("updated"))
    expect(result.current[0]).toBe("updated")
  })

  it("accepts a function updater in setValue", () => {
    // Branch: value instanceof Function in setValue → call value(storedValue)
    const { result } = renderHook(() => useLocalStorage("upd-key", 0))
    act(() => result.current[1]((prev: number) => prev + 1))
    expect(result.current[0]).toBe(1)
  })

  // ── remove path ──────────────────────────────────────────────────────────────

  it("removes the key from localStorage via removeValue", () => {
    // Branch: removeValue → removeItem + reset state to initial
    localStorage.setItem("rem-key", JSON.stringify("value"))
    const { result } = renderHook(() => useLocalStorage("rem-key", "default"))
    act(() => result.current[2]())
    expect(localStorage.getItem("rem-key")).toBeNull()
    expect(result.current[0]).toBe("default")
  })

  // ── cross-tab sync ───────────────────────────────────────────────────────────

  it("updates state when storage event fires with a new value", () => {
    // Branch: handleStorageChange with e.newValue !== null → deserialize
    const { result } = renderHook(() => useLocalStorage("sync-key", "initial"))
    act(() => {
      window.dispatchEvent(
        new StorageEvent("storage", {
          key: "sync-key",
          newValue: JSON.stringify("from-other-tab"),
        })
      )
    })
    expect(result.current[0]).toBe("from-other-tab")
  })

  it("resets to initial when storage event fires with null (key cleared)", () => {
    // Branch: handleStorageChange with e.newValue === null → reset to initial
    localStorage.setItem("clear-key", JSON.stringify("had-value"))
    const { result } = renderHook(() => useLocalStorage("clear-key", "default"))
    act(() => {
      window.dispatchEvent(new StorageEvent("storage", { key: "clear-key", newValue: null }))
    })
    expect(result.current[0]).toBe("default")
  })

  it("ignores storage events for different keys", () => {
    // Branch: e.key !== key → no state update
    const { result } = renderHook(() => useLocalStorage("my-key", "original"))
    act(() => {
      window.dispatchEvent(
        new StorageEvent("storage", { key: "other-key", newValue: JSON.stringify("ignored") })
      )
    })
    expect(result.current[0]).toBe("original")
  })

  // ── custom serialiser/deserialiser ──────────────────────────────────────────

  it("uses a custom serializer when provided", () => {
    // Branch: options.serializer defined → use it instead of JSON.stringify
    const serializer = (v: string) => `PREFIX:${v}`
    const { result } = renderHook(() => useLocalStorage("custom-key", "value", { serializer }))
    act(() => result.current[1]("hello"))
    expect(localStorage.getItem("custom-key")).toBe("PREFIX:hello")
  })

  it("uses a custom deserializer when provided", () => {
    // Branch: options.deserializer defined → use it instead of JSON.parse
    localStorage.setItem("deser-key", "PREFIX:world")
    const deserializer = (v: string) => v.replace("PREFIX:", "")
    const { result } = renderHook(() => useLocalStorage("deser-key", "default", { deserializer }))
    expect(result.current[0]).toBe("world")
  })
})
