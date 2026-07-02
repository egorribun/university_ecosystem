import { describe, expect, it, vi, beforeEach, afterEach } from "vitest"

const mocks = vi.hoisted(() => ({
  logWarning: vi.fn(),
}))

vi.mock("@/app/logger", () => ({
  logWarning: mocks.logWarning,
}))

import { StorageItem, IS_BROWSER, pushConsentStorage, profileCacheStorage } from "@/utils/storage"

beforeEach(() => {
  vi.clearAllMocks()
  localStorage.clear()
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe("storage utilities", () => {
  describe("IS_BROWSER", () => {
    it("is true in jsdom environment", () => {
      expect(IS_BROWSER).toBe(true)
    })
  })

  describe("StorageItem", () => {
    describe("get()", () => {
      it("returns fallback when key does not exist", () => {
        const item = new StorageItem<string>("nonexistent", "default")
        expect(item.get()).toBe("default")
      })

      it("returns null fallback by default", () => {
        const item = new StorageItem<string>("nonexistent")
        expect(item.get()).toBeNull()
      })

      it("returns parsed JSON value from localStorage", () => {
        localStorage.setItem("test-key", JSON.stringify({ name: "Alice" }))
        const item = new StorageItem<{ name: string }>("test-key")
        expect(item.get()).toEqual({ name: "Alice" })
      })

      it("returns string value from localStorage", () => {
        localStorage.setItem("test-string", JSON.stringify("hello"))
        const item = new StorageItem<string>("test-string")
        expect(item.get()).toBe("hello")
      })

      it("returns number value from localStorage", () => {
        localStorage.setItem("test-num", JSON.stringify(42))
        const item = new StorageItem<number>("test-num")
        expect(item.get()).toBe(42)
      })

      it("returns boolean value from localStorage", () => {
        localStorage.setItem("test-bool", JSON.stringify(true))
        const item = new StorageItem<boolean>("test-bool")
        expect(item.get()).toBe(true)
      })

      it("returns fallback on JSON parse error", () => {
        localStorage.setItem("bad-json", "{invalid json")
        const item = new StorageItem<object>("bad-json", { fallback: true })
        expect(item.get()).toEqual({ fallback: true })
      })

      it("logs warning on parse error", () => {
        localStorage.setItem("bad-json", "not-json")
        const item = new StorageItem<string>("bad-json")
        item.get()
        // logWarning called once with descriptive message
        expect(mocks.logWarning).toHaveBeenCalled()
      })
    })

    describe("set()", () => {
      it("writes JSON-serialized value to localStorage", () => {
        const item = new StorageItem<{ count: number }>("test-set")
        item.set({ count: 5 })
        expect(JSON.parse(localStorage.getItem("test-set")!)).toEqual({ count: 5 })
      })

      it("returns true on success", () => {
        const item = new StorageItem<string>("test-success")
        expect(item.set("value")).toBe(true)
      })

      it("dispatches StorageEvent for same-tab sync", () => {
        const listener = vi.fn()
        window.addEventListener("storage", listener)

        const item = new StorageItem<string>("test-event")
        item.set("hello")

        expect(listener).toHaveBeenCalledWith(
          expect.objectContaining({
            key: "test-event",
            newValue: JSON.stringify("hello"),
          })
        )

        window.removeEventListener("storage", listener)
      })

      it("returns false on QuotaExceededError", () => {
        vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
          throw new DOMException("Quota exceeded", "QuotaExceededError")
        })

        const item = new StorageItem<string>("quota-fail")
        expect(item.set("data")).toBe(false)
      })

      it("dispatches StorageEvent with null newValue on QuotaExceededError", () => {
        vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
          throw new DOMException("Quota exceeded", "QuotaExceededError")
        })

        const listener = vi.fn()
        window.addEventListener("storage", listener)

        const item = new StorageItem<string>("quota-event")
        item.set("data")

        expect(listener).toHaveBeenCalledWith(
          expect.objectContaining({
            key: "quota-event",
            newValue: null,
          })
        )

        window.removeEventListener("storage", listener)
      })

      it("logs warning on error", () => {
        vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
          throw new Error("Storage error")
        })

        const item = new StorageItem<string>("error-log")
        item.set("data")
        expect(mocks.logWarning).toHaveBeenCalled()
      })
    })

    describe("remove()", () => {
      it("removes item from localStorage", () => {
        localStorage.setItem("to-remove", JSON.stringify("val"))
        const item = new StorageItem<string>("to-remove")
        item.remove()
        expect(localStorage.getItem("to-remove")).toBeNull()
      })

      it("dispatches StorageEvent with null newValue", () => {
        localStorage.setItem("to-remove-event", JSON.stringify("val"))
        const listener = vi.fn()
        window.addEventListener("storage", listener)

        const item = new StorageItem<string>("to-remove-event")
        item.remove()

        expect(listener).toHaveBeenCalledWith(
          expect.objectContaining({
            key: "to-remove-event",
            newValue: null,
          })
        )

        window.removeEventListener("storage", listener)
      })

      it("handles error gracefully", () => {
        vi.spyOn(Storage.prototype, "removeItem").mockImplementation(() => {
          throw new Error("Remove failed")
        })

        const item = new StorageItem<string>("remove-error")
        // Should not throw
        expect(() => item.remove()).not.toThrow()
        expect(mocks.logWarning).toHaveBeenCalled()
      })
    })

    describe("exists()", () => {
      it("returns true when key exists", () => {
        localStorage.setItem("exists-key", "value")
        const item = new StorageItem<string>("exists-key")
        expect(item.exists()).toBe(true)
      })

      it("returns false when key does not exist", () => {
        const item = new StorageItem<string>("missing-key")
        expect(item.exists()).toBe(false)
      })
    })
  })

  describe("pre-defined storage instances", () => {
    it("pushConsentStorage has correct key", () => {
      pushConsentStorage.set("granted")
      expect(localStorage.getItem("push-notification-consent")).toBe(JSON.stringify("granted"))
    })

    it("profileCacheStorage has correct key", () => {
      const data = { name: "test" }
      profileCacheStorage.set(data)
      expect(localStorage.getItem("sub-profile-cache")).toBe(JSON.stringify(data))
    })
  })
})
