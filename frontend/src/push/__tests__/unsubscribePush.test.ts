import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { unsubscribePush } from "@/push/subscribe"

const CONSENT_KEY = "push-notification-consent"
const LAST_SYNC_KEY = "push:last_sync"
const SUB_KEY = "push:last_payload"
const TOPICS_KEY = "push:last_topics"

vi.mock("@/push/register-sw", () => ({
  registerServiceWorker: vi.fn().mockResolvedValue(null),
}))

vi.mock("@/push/subscribe", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/push/subscribe")>()
  return {
    ...actual,
    unsubscribePush: actual.unsubscribePush,
  }
})

describe("unsubscribePush", () => {
  beforeEach(() => {
    vi.useFakeTimers()
    localStorage.clear()
    vi.clearAllMocks()
  })

  afterEach(() => {
    vi.useRealTimers()
    try {
      delete (navigator as any).serviceWorker
    } catch {
      /* ignore */
    }
  })

  const setupMockSW = (readyDelay = 3000) => {
    const getRegistration = vi.fn().mockResolvedValue(undefined)
    const readyPromise = new Promise<ServiceWorkerRegistration>((resolve) => {
      setTimeout(() => {
        resolve(mockRegistration as any)
      }, readyDelay)
    })

    const mockRegistration = {
      ready: readyPromise,
      getRegistration,
      register: vi.fn().mockImplementation(async () => mockRegistration),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      pushManager: {
        getSubscription: vi.fn().mockResolvedValue(null),
      },
    }

    Object.defineProperty(navigator, "serviceWorker", {
      configurable: true,
      value: mockRegistration,
    })

    return { mockRegistration, getRegistration }
  }

  it("resolves when the service worker never becomes ready", async () => {
    localStorage.setItem(CONSENT_KEY, "granted")
    localStorage.setItem(LAST_SYNC_KEY, "123")
    localStorage.setItem(SUB_KEY, "{}")
    localStorage.setItem(TOPICS_KEY, "[]")

    setupMockSW(10000) // Slow ready

    const resultPromise = unsubscribePush()

    // Advance enough to trigger the 2000ms timeout in resolveServiceWorkerRegistration
    // and let the mocked registerServiceWorker (which returns null) finish.
    await vi.advanceTimersByTimeAsync(3000)

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

    setupMockSW(10000)

    const resultPromise = unsubscribePush({ preserveTopics: true })

    await vi.advanceTimersByTimeAsync(3000)

    const result = await resultPromise
    expect(result).toBe(false)

    expect(localStorage.getItem(CONSENT_KEY)).toBeNull()
    expect(localStorage.getItem(TOPICS_KEY)).toBe('["news"]')
  })
})
