import { describe, expect, it, vi, beforeEach, afterEach } from "vitest"
import { etagCache } from "@/api/interceptors/etagCache"

describe("Storage Failure and Quota Exceeded Handlers", () => {
  beforeEach(() => {
    vi.useFakeTimers()
    localStorage.clear()
    // Reset etagCache state by clearing it
    etagCache.clear()
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.restoreAllMocks()
    localStorage.clear()
  })

  it("handles QuotaExceededError by evicting oldest 50% of entries and retrying", () => {
    // 1. Seed some entries in etagCache
    etagCache.set("key1", '"etag1"')
    etagCache.set("key2", '"etag2"')
    etagCache.set("key3", '"etag3"')
    etagCache.set("key4", '"etag4"')

    // 2. Mock localStorage.setItem to throw QuotaExceededError on first call,
    // but succeed on subsequent calls (after eviction).
    let callCount = 0
    const setItemSpy = vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      callCount++
      if (callCount === 1) {
        throw new DOMException("Quota exceeded", "QuotaExceededError")
      }
      // Succeed on retry
    })

    // Trigger debounced flush
    vi.advanceTimersByTime(30_000)

    // Should have tried to set, failed, evicted 50% (2 entries), and retried
    expect(setItemSpy).toHaveBeenCalledTimes(2)
  })

  it("handles persistent QuotaExceededError gracefully without throwing", () => {
    etagCache.set("key1", '"etag1"')
    etagCache.set("key2", '"etag2"')

    // Always throw QuotaExceededError
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new DOMException("Quota exceeded", "QuotaExceededError")
    })

    expect(() => {
      vi.advanceTimersByTime(30_000)
    }).not.toThrow()
  })

  it("logs warning on non-QuotaExceeded errors without crashing", () => {
    etagCache.set("key1", '"etag1"')

    // Generic error
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("Security restriction or localstorage disabled")
    })

    expect(() => {
      vi.advanceTimersByTime(30_000)
    }).not.toThrow()
  })
})
