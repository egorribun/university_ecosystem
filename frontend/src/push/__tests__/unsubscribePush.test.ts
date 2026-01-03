import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { unsubscribePush } from "@/push/subscribe"

const CONSENT_KEY = "push:consent"
const LAST_SYNC_KEY = "push:last_sync"
const SUB_KEY = "push:last_payload"
const TOPICS_KEY = "push:last_topics"

describe("unsubscribePush", () => {
  beforeEach(() => {
    vi.useFakeTimers()
    localStorage.clear()
  })

  afterEach(() => {
    vi.useRealTimers()
    try {
      delete (navigator as any).serviceWorker
    } catch {
      /* ignore */
    }
  })

  it("resolves when the service worker never becomes ready", async () => {
    localStorage.setItem(CONSENT_KEY, "granted")
    localStorage.setItem(LAST_SYNC_KEY, "123")
    localStorage.setItem(SUB_KEY, "{}")
    localStorage.setItem(TOPICS_KEY, "[]")

    const neverReady = new Promise<ServiceWorkerRegistration>(() => {})
    const getRegistration = vi.fn().mockResolvedValue(undefined)

    Object.defineProperty(navigator, "serviceWorker", {
      configurable: true,
      value: {
        ready: neverReady,
        getRegistration,
      },
    })

    const resultPromise = unsubscribePush()

    await vi.advanceTimersByTimeAsync(2100)

    const result = await resultPromise
    expect(result).toBe(false)

    expect(localStorage.getItem(CONSENT_KEY)).toBeNull()
    expect(localStorage.getItem(LAST_SYNC_KEY)).toBeNull()
    expect(localStorage.getItem(SUB_KEY)).toBeNull()
    expect(localStorage.getItem(TOPICS_KEY)).toBeNull()
  })

  it("keeps stored topics when preserveTopics is requested", async () => {
    localStorage.setItem(CONSENT_KEY, "granted")
    localStorage.setItem(LAST_SYNC_KEY, "123")
    localStorage.setItem(SUB_KEY, "{}")
    localStorage.setItem(TOPICS_KEY, '["news"]')

    const neverReady = new Promise<ServiceWorkerRegistration>(() => {})
    const getRegistration = vi.fn().mockResolvedValue(undefined)

    Object.defineProperty(navigator, "serviceWorker", {
      configurable: true,
      value: {
        ready: neverReady,
        getRegistration,
      },
    })

    const resultPromise = unsubscribePush({ preserveTopics: true })

    await vi.advanceTimersByTimeAsync(2100)

    const result = await resultPromise
    expect(result).toBe(false)

    expect(localStorage.getItem(CONSENT_KEY)).toBeNull()
    expect(localStorage.getItem(LAST_SYNC_KEY)).toBeNull()
    expect(localStorage.getItem(SUB_KEY)).toBeNull()
    expect(localStorage.getItem(TOPICS_KEY)).toBe('["news"]')
  })
})
