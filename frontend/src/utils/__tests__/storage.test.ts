import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { StorageItem, IS_BROWSER } from "../storage"

// ---------------------------------------------------------------------------
// Helpers — jsdom provides localStorage, so we can spy on it directly
// ---------------------------------------------------------------------------

describe("IS_BROWSER", () => {
  it("is true in a jsdom environment", () => {
    expect(IS_BROWSER).toBe(true)
  })
})

describe("StorageItem", () => {
  beforeEach(() => {
    localStorage.clear()
    vi.spyOn(console, "warn").mockImplementation(() => {})
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  // ---------------------------------------------------------------------------
  // get()
  // ---------------------------------------------------------------------------
  describe("get()", () => {
    it("returns null (fallback) when key is not set", () => {
      const item = new StorageItem<string>("test-key")
      expect(item.get()).toBeNull()
    })

    it("returns provided fallback when key is not set", () => {
      const item = new StorageItem<string>("missing-key", "default")
      expect(item.get()).toBe("default")
    })

    it("returns parsed value when key exists", () => {
      localStorage.setItem("my-key", JSON.stringify({ count: 42 }))
      const item = new StorageItem<{ count: number }>("my-key")
      expect(item.get()).toEqual({ count: 42 })
    })

    it("returns fallback and does not throw when stored JSON is corrupt", () => {
      localStorage.setItem("bad-json", "not-valid-json{{{")
      const item = new StorageItem<string>("bad-json", "fallback")
      expect(item.get()).toBe("fallback")
    })
  })

  // ---------------------------------------------------------------------------
  // set()
  // ---------------------------------------------------------------------------
  describe("set()", () => {
    it("stores the value and returns true", () => {
      const item = new StorageItem<number>("count-key")
      const result = item.set(7)
      expect(result).toBe(true)
      expect(JSON.parse(localStorage.getItem("count-key")!)).toBe(7)
    })

    it("dispatches a StorageEvent with the new serialized value", () => {
      const item = new StorageItem<string>("event-key")
      const events: StorageEvent[] = []
      window.addEventListener("storage", (e) => events.push(e))
      item.set("hello")
      window.removeEventListener("storage", (e) => events.push(e))

      const storageEvent = events.find((e) => e.key === "event-key")
      expect(storageEvent).toBeDefined()
      expect(storageEvent?.newValue).toBe(JSON.stringify("hello"))
    })

    it("overwrites a previously stored value", () => {
      const item = new StorageItem<number>("overwrite-key")
      item.set(1)
      item.set(2)
      expect(item.get()).toBe(2)
    })

    it("stores complex objects with JSON serialization", () => {
      const item = new StorageItem<{ a: number; b: string }>("obj-key")
      item.set({ a: 1, b: "two" })
      expect(item.get()).toEqual({ a: 1, b: "two" })
    })
  })

  // ---------------------------------------------------------------------------
  // remove()
  // ---------------------------------------------------------------------------
  describe("remove()", () => {
    it("removes an existing key", () => {
      const item = new StorageItem<string>("rm-key")
      item.set("value")
      item.remove()
      expect(localStorage.getItem("rm-key")).toBeNull()
    })

    it("does not throw when removing a non-existent key", () => {
      const item = new StorageItem<string>("nonexistent")
      expect(() => item.remove()).not.toThrow()
    })

    it("dispatches a StorageEvent with newValue=null on removal", () => {
      const item = new StorageItem<string>("rm-event-key")
      item.set("data")

      const events: StorageEvent[] = []
      window.addEventListener("storage", (e) => events.push(e))
      item.remove()
      window.removeEventListener("storage", (e) => events.push(e))

      const storageEvent = events.find((e) => e.key === "rm-event-key")
      expect(storageEvent).toBeDefined()
      expect(storageEvent?.newValue).toBeNull()
    })
  })

  // ---------------------------------------------------------------------------
  // exists()
  // ---------------------------------------------------------------------------
  describe("exists()", () => {
    it("returns false when key is not set", () => {
      expect(new StorageItem<string>("absent").exists()).toBe(false)
    })

    it("returns true when key is set", () => {
      const item = new StorageItem<string>("present")
      item.set("value")
      expect(item.exists()).toBe(true)
    })

    it("returns false after removing the key", () => {
      const item = new StorageItem<string>("was-present")
      item.set("v")
      item.remove()
      expect(item.exists()).toBe(false)
    })
  })
})
