import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

vi.unmock("@/push/subscribe")

import { deleteSubscription, getVapidPublicKey, saveSubscription } from "@/api/notifications"

vi.mock("@/api/notifications", () => ({
  deleteSubscription: vi.fn(),
  getVapidPublicKey: vi.fn(),
  saveSubscription: vi.fn().mockResolvedValue({}),
}))

vi.mock("../register-sw", () => ({
  registerServiceWorker: vi.fn(),
}))

describe("subscribe", () => {
  let mockSWContainer: any
  let mod: any
  let storageMod: any

  beforeEach(async () => {
    localStorage.clear()
    vi.resetModules()
    vi.useFakeTimers()
    vi.clearAllMocks()

    mockSWContainer = {
      getRegistration: vi.fn().mockResolvedValue(null),
      ready: Promise.resolve(null),
      addEventListener: vi.fn(),
    }

    vi.stubGlobal("navigator", {
      serviceWorker: mockSWContainer,
    })

    vi.stubGlobal("PushManager", class {})

    vi.stubGlobal("Notification", {
      permission: "default",
      requestPermission: vi.fn().mockResolvedValue("granted"),
    })

    mod = await import("../subscribe")
    storageMod = await import("@/utils/storage")
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.unstubAllEnvs()
    vi.useRealTimers()
  })

  describe("Topic parsing and serialization", () => {
    it("parses stored topics correctly from simple arrays and nested objects", () => {
      expect(mod.parseStoredTopics('["topicB", "topicA"]')).toEqual(["topicA", "topicB"])

      const payload = {
        version: 2,
        shared: ["sharedA"],
        perUser: {
          "user-1": ["userTopicB", "userTopicA"],
        },
      }

      vi.spyOn(storageMod.profileCacheStorage, "get").mockReturnValue({ data: { id: "user-1" } })
      expect(mod.parseStoredTopics(JSON.stringify(payload))).toEqual(["userTopicA", "userTopicB"])

      vi.spyOn(storageMod.profileCacheStorage, "get").mockReturnValue(null)
      expect(mod.parseStoredTopics(JSON.stringify(payload))).toEqual(["sharedA"])
    })

    it("serializes and sets persisted topics under user namespace", () => {
      vi.spyOn(storageMod.profileCacheStorage, "get").mockReturnValue({ data: { id: "user-2" } })

      mod.setPersistedTopics(["news", "events"])
      const stored: any = mod.getPersistedTopics({ userId: "user-2" })
      expect(stored).toEqual(["events", "news"])
    })

    it("clears storage when topics are null/empty", () => {
      mod.setPersistedTopics(null)
      expect(mod.getPersistedTopics()).toBeUndefined()
    })
  })

  describe("Consent and Browser recovery", () => {
    it("handles explicit push consent updates", () => {
      mod.setPushConsent(true)
      expect(mod.hasPushConsent()).toBe(true)

      mod.setPushConsent(false)
      expect(mod.hasPushConsent()).toBe(false)
    })

    it("recovers consent from browser pushManager subscription", async () => {
      const mockSubscription = {
        toJSON: () => ({ endpoint: "https://fcm.googleapis.com/123" }),
      }
      const mockReg = {
        pushManager: {
          getSubscription: vi.fn().mockResolvedValue(mockSubscription),
        },
      }
      mockSWContainer.getRegistration.mockResolvedValue(mockReg)
      vi.stubGlobal("Notification", { permission: "granted" })

      const recovered = await mod.recoverPushConsentFromBrowser()
      expect(recovered).toBe(true)
      expect(mod.hasPushConsent()).toBe(true)
      expect(saveSubscription).toHaveBeenCalled()
    })

    it("keeps recovered consent when the resync is rate limited", async () => {
      const mockSubscription = {
        toJSON: () => ({ endpoint: "https://push.example.com/recovered-rate" }),
      }
      const mockReg = {
        pushManager: {
          getSubscription: vi.fn().mockResolvedValue(mockSubscription),
        },
      }
      mockSWContainer.getRegistration.mockResolvedValue(mockReg)
      vi.mocked(saveSubscription).mockRejectedValue({ response: { status: 429 } })
      vi.stubGlobal("Notification", { permission: "granted" })

      await expect(mod.recoverPushConsentFromBrowser()).resolves.toBe(true)
      expect(mod.hasPushConsent()).toBe(true)
    })

    it("returns false when browser subscription lookup throws during recovery", async () => {
      const mockReg = {
        pushManager: {
          getSubscription: vi.fn().mockRejectedValue(new Error("lookup failed")),
        },
      }
      mockSWContainer.getRegistration.mockResolvedValue(mockReg)
      vi.stubGlobal("Notification", { permission: "granted" })

      await expect(mod.recoverPushConsentFromBrowser()).resolves.toBe(false)
      expect(mod.hasPushConsent()).toBe(false)
    })
  })

  describe("resolveServiceWorkerRegistration", () => {
    it("returns immediate registration if provided", async () => {
      const dummyReg: any = {}
      const res = await mod.resolveServiceWorkerRegistration(dummyReg)
      expect(res).toBe(dummyReg)
    })

    it("queries service worker container ready promise", async () => {
      const dummyReg: any = { active: {} }
      mockSWContainer.ready = Promise.resolve(dummyReg)

      const res = await mod.resolveServiceWorkerRegistration()
      expect(res).toBe(dummyReg)
    })

    it("falls back to auto-registration when lookup and ready both fail", async () => {
      const fallbackReg: any = { active: {} }
      const { registerServiceWorker } = await import("../register-sw")
      vi.mocked(registerServiceWorker).mockResolvedValue(fallbackReg)
      mockSWContainer.getRegistration.mockRejectedValue(new Error("lookup failed"))
      mockSWContainer.ready = Promise.reject(new Error("ready failed"))

      await expect(mod.resolveServiceWorkerRegistration()).resolves.toBe(fallbackReg)
    })

    it("uses the final registration lookup when auto-registration fails", async () => {
      const finalReg: any = { active: {} }
      const { registerServiceWorker } = await import("../register-sw")
      vi.mocked(registerServiceWorker).mockRejectedValue(new Error("register failed"))
      mockSWContainer.ready = Promise.resolve(null)
      mockSWContainer.getRegistration.mockResolvedValueOnce(null).mockResolvedValueOnce(finalReg)

      await expect(mod.resolveServiceWorkerRegistration()).resolves.toBe(finalReg)
      expect(mockSWContainer.getRegistration).toHaveBeenCalledTimes(2)
    })

    it("returns null when the browser has no service worker API", async () => {
      vi.stubGlobal("navigator", {})

      await expect(mod.resolveServiceWorkerRegistration()).resolves.toBeNull()
    })

    it("handles an exception while awaiting service worker readiness", async () => {
      const { registerServiceWorker } = await import("../register-sw")
      vi.mocked(registerServiceWorker).mockResolvedValue(null)
      mockSWContainer.getRegistration.mockResolvedValue(null)
      Object.defineProperty(mockSWContainer, "ready", {
        configurable: true,
        get: () => {
          throw new Error("ready getter failed")
        },
      })

      await expect(mod.resolveServiceWorkerRegistration()).resolves.toBeNull()
    })

    it("returns null when the final service worker lookup throws", async () => {
      const { registerServiceWorker } = await import("../register-sw")
      vi.mocked(registerServiceWorker).mockResolvedValue(null)
      mockSWContainer.ready = Promise.resolve(null)
      mockSWContainer.getRegistration
        .mockResolvedValueOnce(null)
        .mockRejectedValueOnce(new Error("final lookup failed"))

      await expect(mod.resolveServiceWorkerRegistration()).resolves.toBeNull()
    })
  })

  describe("resolveVapidPublicKey", () => {
    it("resolves from environment variables first", async () => {
      vi.stubEnv("VITE_VAPID_PUBLIC_KEY", "env-key-123")
      const key = await mod.resolveVapidPublicKey()
      expect(key).toBe("env-key-123")
    })

    it("resolves from API if environment variable is missing", async () => {
      vi.stubEnv("VITE_VAPID_PUBLIC_KEY", "")
      vi.mocked(getVapidPublicKey).mockResolvedValue("api-key-456")

      const key = await mod.resolveVapidPublicKey()
      expect(key).toBe("api-key-456")
    })

    it("caches a null result when the VAPID API fails", async () => {
      vi.stubEnv("VITE_VAPID_PUBLIC_KEY", "")
      vi.mocked(getVapidPublicKey).mockRejectedValue(new Error("vapid unavailable"))

      await expect(mod.resolveVapidPublicKey()).resolves.toBeNull()
      await expect(mod.resolveVapidPublicKey()).resolves.toBeNull()
      expect(getVapidPublicKey).toHaveBeenCalledTimes(1)
    })
  })

  describe("urlBase64ToUint8Array", () => {
    it("converts base64 url-safe strings to correct Uint8Array bytes", () => {
      const b64 = "YmFzZTY0"
      const bytes = mod.urlBase64ToUint8Array(b64)
      expect(new TextDecoder().decode(bytes)).toBe("base64")
    })
  })

  describe("ensurePushSubscription", () => {
    it("registers and subscribes via PushManager", async () => {
      const mockSub = {
        endpoint: "http://endpoint",
        options: {
          applicationServerKey: mod.urlBase64ToUint8Array("abc").buffer,
        },
        toJSON: () => ({ endpoint: "http://endpoint" }),
      }
      const mockReg = {
        pushManager: {
          getSubscription: vi.fn().mockResolvedValue(null),
          subscribe: vi.fn().mockResolvedValue(mockSub),
        },
      }
      mockSWContainer.getRegistration.mockResolvedValue(mockReg)
      vi.stubEnv("VITE_VAPID_PUBLIC_KEY", "abc")

      const sub = await mod.ensurePushSubscription({ requestPermission: true })
      expect(sub).toBe(mockSub)
      expect(mockReg.pushManager.subscribe).toHaveBeenCalled()
      expect(saveSubscription).toHaveBeenCalled()
    })

    it("unsubscribes and resubscribes if keys mismatch or expiring soon", async () => {
      const unsubscribeSpy = vi.fn().mockResolvedValue(true)
      const mockSub = {
        endpoint: "http://endpoint",
        expirationTime: Date.now() + 1000,
        options: {
          applicationServerKey: mod.urlBase64ToUint8Array("old-key").buffer,
        },
        unsubscribe: unsubscribeSpy,
        toJSON: () => ({ endpoint: "http://endpoint" }),
      }

      const mockReg = {
        pushManager: {
          getSubscription: vi.fn().mockResolvedValue(mockSub),
          subscribe: vi.fn().mockResolvedValue(mockSub),
        },
      }
      mockSWContainer.getRegistration.mockResolvedValue(mockReg)
      vi.stubEnv("VITE_VAPID_PUBLIC_KEY", "new-key")

      await mod.ensurePushSubscription({ requestPermission: true })
      expect(unsubscribeSpy).toHaveBeenCalled()
    })

    it("returns null when the user declines the default permission prompt", async () => {
      const mockReg = {
        pushManager: {
          getSubscription: vi.fn().mockResolvedValue(null),
          subscribe: vi.fn(),
        },
      }
      mockSWContainer.getRegistration.mockResolvedValue(mockReg)
      vi.stubGlobal("Notification", {
        permission: "default",
        requestPermission: vi.fn().mockResolvedValue("denied"),
      })

      const result = await mod.ensurePushSubscription({ requestPermission: true })

      expect(result).toBeNull()
      expect(Notification.requestPermission).toHaveBeenCalledOnce()
      expect(mockReg.pushManager.subscribe).not.toHaveBeenCalled()
    })

    it("returns null when the default permission is not requested", async () => {
      const mockReg = { pushManager: { getSubscription: vi.fn() } }
      vi.stubGlobal("Notification", {
        permission: "default",
        requestPermission: vi.fn(),
      })

      await expect(
        mod.ensurePushSubscription({ registration: mockReg, requestPermission: false })
      ).resolves.toBeNull()
      expect(Notification.requestPermission).not.toHaveBeenCalled()
    })

    it("reuses the in-flight ensure lock for concurrent callers", async () => {
      let resolveLookup: ((value: null) => void) | undefined
      const lookup = new Promise<null>((resolve) => {
        resolveLookup = resolve
      })
      const mockSub = {
        endpoint: "https://push.example.com/locked",
        options: { applicationServerKey: mod.urlBase64ToUint8Array("lock-key").buffer },
        toJSON: () => ({ endpoint: "https://push.example.com/locked" }),
      }
      const mockReg = {
        pushManager: {
          getSubscription: vi.fn().mockReturnValue(lookup),
          subscribe: vi.fn().mockResolvedValue(mockSub),
        },
      }
      vi.mocked(saveSubscription).mockResolvedValue({} as any)
      vi.stubGlobal("Notification", { permission: "granted" })

      const first = mod.ensurePushSubscription({
        registration: mockReg,
        vapidPublicKey: "lock-key",
        requestPermission: false,
      })
      const second = mod.ensurePushSubscription({
        registration: mockReg,
        vapidPublicKey: "lock-key",
        requestPermission: false,
      })
      resolveLookup?.(null)

      await expect(first).resolves.toBe(mockSub)
      await expect(second).resolves.toBe(mockSub)
      expect(mockReg.pushManager.getSubscription).toHaveBeenCalledOnce()
    })

    it("continues with a new subscription when stale unsubscribe fails", async () => {
      const staleSub = {
        options: { applicationServerKey: new Uint8Array([0]).buffer },
        unsubscribe: vi.fn().mockRejectedValue(new Error("unsubscribe failed")),
      }
      const freshSub = {
        endpoint: "https://push.example.com/fresh",
        options: { applicationServerKey: mod.urlBase64ToUint8Array("ZnJlc2g").buffer },
        toJSON: () => ({ endpoint: "https://push.example.com/fresh" }),
      }
      const mockReg = {
        pushManager: {
          getSubscription: vi.fn().mockResolvedValue(staleSub),
          subscribe: vi.fn().mockResolvedValue(freshSub),
        },
      }
      vi.mocked(saveSubscription).mockResolvedValue({} as any)
      vi.stubGlobal("Notification", { permission: "granted" })

      await expect(
        mod.ensurePushSubscription({
          registration: mockReg,
          vapidPublicKey: "ZnJlc2g",
          requestPermission: false,
        })
      ).resolves.toBe(freshSub)
      expect(staleSub.unsubscribe).toHaveBeenCalledOnce()
      expect(mockReg.pushManager.subscribe).toHaveBeenCalledOnce()
    })

    it("does not retry persistence after a 429 response", async () => {
      vi.mocked(saveSubscription).mockRejectedValue({ response: { status: 429 } })
      const mockSub = {
        endpoint: "https://push.example.com/rate-limited",
        options: { applicationServerKey: mod.urlBase64ToUint8Array("rate-key").buffer },
        toJSON: () => ({ endpoint: "https://push.example.com/rate-limited" }),
      }
      const mockReg = {
        pushManager: {
          getSubscription: vi.fn().mockResolvedValue(null),
          subscribe: vi.fn().mockResolvedValue(mockSub),
        },
      }
      mockSWContainer.getRegistration.mockResolvedValue(mockReg)
      vi.stubEnv("VITE_VAPID_PUBLIC_KEY", "rate-key")
      vi.stubGlobal("Notification", { permission: "granted" })

      await expect(mod.ensurePushSubscription({ requestPermission: false })).resolves.toBe(mockSub)
      expect(saveSubscription).toHaveBeenCalledOnce()
    })

    it("refreshes the local sync timestamp when persistence is already current", async () => {
      vi.mocked(saveSubscription).mockResolvedValue({} as any)
      const mockSub = {
        endpoint: "https://push.example.com/already-current",
        options: { applicationServerKey: mod.urlBase64ToUint8Array("current-key").buffer },
        toJSON: () => ({ endpoint: "https://push.example.com/already-current" }),
      }
      const mockReg = {
        pushManager: {
          getSubscription: vi.fn().mockResolvedValue(mockSub),
          subscribe: vi.fn(),
        },
      }
      vi.stubEnv("VITE_VAPID_PUBLIC_KEY", "current-key")
      vi.stubGlobal("Notification", { permission: "granted" })

      await mod.ensurePushSubscription({ registration: mockReg, requestPermission: false })
      // Legacy clients stored the topic list as a plain array. Keep that
      // representation here to exercise the no-op persistence fast path.
      localStorage.setItem("push:last_topics", "[]")
      await mod.ensurePushSubscription({ registration: mockReg, requestPermission: false })

      expect(saveSubscription).toHaveBeenCalledOnce()
    })

    it("swallows a permanent persistence failure after bounded retries", async () => {
      vi.mocked(saveSubscription).mockRejectedValue(new Error("permanent failure"))
      const mockSub = {
        endpoint: "https://push.example.com/permanent-failure",
        options: { applicationServerKey: mod.urlBase64ToUint8Array("failure-key").buffer },
        toJSON: () => ({ endpoint: "https://push.example.com/permanent-failure" }),
      }
      const mockReg = {
        pushManager: {
          getSubscription: vi.fn().mockResolvedValue(null),
          subscribe: vi.fn().mockResolvedValue(mockSub),
        },
      }
      mockSWContainer.getRegistration.mockResolvedValue(mockReg)
      vi.stubEnv("VITE_VAPID_PUBLIC_KEY", "failure-key")
      vi.stubGlobal("Notification", { permission: "granted" })

      const promise = mod.ensurePushSubscription({ requestPermission: false })
      await vi.runAllTimersAsync()

      await expect(promise).resolves.toBe(mockSub)
      expect(saveSubscription).toHaveBeenCalledTimes(3)
    })
  })

  describe("unsubscribePush", () => {
    it("unsubscribes and cleans up local storage flags", async () => {
      const unsubscribeSpy = vi.fn().mockResolvedValue(true)
      const mockSub = {
        endpoint: "http://endpoint",
        unsubscribe: unsubscribeSpy,
      }
      const mockReg = {
        pushManager: {
          getSubscription: vi.fn().mockResolvedValue(mockSub),
        },
      }
      mockSWContainer.getRegistration.mockResolvedValue(mockReg)

      const result = await mod.unsubscribePush()
      expect(result).toBe(true)
      expect(deleteSubscription).toHaveBeenCalledWith("http://endpoint")
      expect(unsubscribeSpy).toHaveBeenCalled()
      expect(mod.hasPushConsent()).toBe(false)
    })

    it("still unsubscribes locally when server deletion fails", async () => {
      const unsubscribeSpy = vi.fn().mockResolvedValue(true)
      const mockSub = {
        endpoint: "http://endpoint",
        unsubscribe: unsubscribeSpy,
      }
      const mockReg = {
        pushManager: {
          getSubscription: vi.fn().mockResolvedValue(mockSub),
        },
      }
      mockSWContainer.getRegistration.mockResolvedValue(mockReg)
      vi.mocked(deleteSubscription).mockRejectedValue(new Error("server unavailable"))

      await expect(mod.unsubscribePush()).resolves.toBe(false)
      expect(unsubscribeSpy).toHaveBeenCalledOnce()
    })

    it("clears local state and returns false when service workers are unavailable", async () => {
      vi.stubGlobal("navigator", {})

      await expect(mod.unsubscribePush()).resolves.toBe(false)
    })

    it("clears local state and returns true when no active subscription exists", async () => {
      const mockReg = {
        pushManager: {
          getSubscription: vi.fn().mockResolvedValue(null),
        },
      }

      await expect(mod.unsubscribePush({ registration: mockReg })).resolves.toBe(true)
    })
  })

  describe("softSyncPushSubscription", () => {
    it("avoids duplicate syncs and calls ensurePushSubscription", async () => {
      const mockReg = {
        pushManager: {
          getSubscription: vi.fn().mockResolvedValue(null),
        },
      }
      mockSWContainer.getRegistration.mockResolvedValue(mockReg)
      vi.stubGlobal("Notification", { permission: "granted" })

      const p1 = mod.softSyncPushSubscription()
      const p2 = mod.softSyncPushSubscription()

      await p1
      await p2

      expect(mockSWContainer.getRegistration).toHaveBeenCalledTimes(1)
    })
  })

  describe("isPushSupported", () => {
    it("returns status of browser push manager", () => {
      vi.stubGlobal("PushManager", {})
      expect(mod.isPushSupported()).toBe(true)
    })
  })

  describe("getExistingPushSubscription", () => {
    it("returns null if not supported", async () => {
      vi.stubGlobal("PushManager", undefined)
      expect(await mod.getExistingPushSubscription()).toBeNull()
    })

    it("returns null when the browser rejects getSubscription", async () => {
      const mockReg = {
        pushManager: {
          getSubscription: vi.fn().mockRejectedValue(new Error("browser failure")),
        },
      }
      mockSWContainer.getRegistration.mockResolvedValue(mockReg)

      expect(await mod.getExistingPushSubscription()).toBeNull()
    })

    it("returns the active subscription when browser lookup succeeds", async () => {
      const mockSub = { endpoint: "https://push.example.com/existing" }
      const mockReg = {
        pushManager: {
          getSubscription: vi.fn().mockResolvedValue(mockSub),
        },
      }

      await expect(mod.getExistingPushSubscription(mockReg)).resolves.toBe(mockSub)
    })
  })

  describe("softSyncPushSubscription", () => {
    it("returns null when the sync task fails before subscription creation", async () => {
      vi.stubGlobal("Notification", { permission: "granted" })
      const mockReg = { pushManager: { getSubscription: vi.fn() } }

      await expect(
        mod.softSyncPushSubscription({ registration: mockReg, vapidPublicKey: "%" })
      ).resolves.toBeNull()
    })
  })

  // ─── W16 extended coverage ──────────────────────────────────────────────────

  describe("Notification permission denied → early return", () => {
    it("returns null without touching pushManager when permission is denied", async () => {
      const subscribeSpy = vi.fn()
      const mockReg = {
        pushManager: {
          getSubscription: vi.fn().mockResolvedValue(null),
          subscribe: subscribeSpy,
        },
      }
      mockSWContainer.getRegistration.mockResolvedValue(mockReg)
      vi.stubEnv("VITE_VAPID_PUBLIC_KEY", "abc")
      vi.stubGlobal("Notification", {
        permission: "denied",
        requestPermission: vi.fn(),
      })

      const result = await mod.ensurePushSubscription({ requestPermission: true })

      expect(result).toBeNull()
      // Subscribe must NOT be called — we bail out before reaching pushManager
      expect(subscribeSpy).not.toHaveBeenCalled()
    })
  })

  describe("VAPID key missing / invalid → graceful null", () => {
    it("returns null when both env var and API return empty/null VAPID key", async () => {
      const mockReg = {
        pushManager: {
          getSubscription: vi.fn().mockResolvedValue(null),
          subscribe: vi.fn(),
        },
      }
      mockSWContainer.getRegistration.mockResolvedValue(mockReg)
      // Empty env var
      vi.stubEnv("VITE_VAPID_PUBLIC_KEY", "")
      // API returns null
      const { getVapidPublicKey } = await import("@/api/notifications")
      vi.mocked(getVapidPublicKey).mockResolvedValue(null as any)

      vi.stubGlobal("Notification", {
        permission: "granted",
        requestPermission: vi.fn(),
      })

      const result = await mod.ensurePushSubscription({ requestPermission: false })

      expect(result).toBeNull()
    })

    it("returns null when vapidPublicKey option is an empty string", async () => {
      const mockReg = {
        pushManager: {
          getSubscription: vi.fn().mockResolvedValue(null),
          subscribe: vi.fn(),
        },
      }
      mockSWContainer.getRegistration.mockResolvedValue(mockReg)
      vi.stubGlobal("Notification", { permission: "granted" })

      const result = await mod.ensurePushSubscription({
        requestPermission: false,
        vapidPublicKey: "   ", // whitespace-only — normalised to empty
      })

      expect(result).toBeNull()
    })
  })

  describe("pushManager.subscribe throws → retry logic (persistSubscriptionWithBackoff)", () => {
    it("retries saveSubscription up to PERSIST_MAX_ATTEMPTS before throwing", async () => {
      const { saveSubscription } = await import("@/api/notifications")

      const networkError = new Error("network error")
      vi.mocked(saveSubscription)
        .mockRejectedValueOnce(networkError)
        .mockRejectedValueOnce(networkError)
        .mockResolvedValue({} as any)

      const mockSub = {
        endpoint: "https://push.example.com/sub",
        options: { applicationServerKey: mod.urlBase64ToUint8Array("validkey123").buffer },
        toJSON: () => ({
          endpoint: "https://push.example.com/sub",
          keys: { p256dh: "pk", auth: "ak" },
        }),
      }
      const mockReg = {
        pushManager: {
          getSubscription: vi.fn().mockResolvedValue(null),
          subscribe: vi.fn().mockResolvedValue(mockSub),
        },
      }
      mockSWContainer.getRegistration.mockResolvedValue(mockReg)
      vi.stubEnv("VITE_VAPID_PUBLIC_KEY", "validkey123")
      vi.stubGlobal("Notification", { permission: "granted" })

      // Run timers so sleep(delay) resolves immediately
      const result = await Promise.race([
        mod.ensurePushSubscription({ requestPermission: false }),
        // Fast-forward fake timers while awaiting
        new Promise<null>((resolve) => {
          vi.runAllTimersAsync().then(() => resolve(null))
        }),
      ])

      // saveSubscription succeeded on third attempt; sub should be returned
      expect(saveSubscription).toHaveBeenCalledTimes(3)
      expect(result).toBe(mockSub)
    })

    it("handles 409 Conflict from saveSubscription as success (no throw)", async () => {
      const { saveSubscription } = await import("@/api/notifications")

      const conflictError = new Error("409 Conflict")
      vi.mocked(saveSubscription).mockRejectedValue(conflictError)

      const mockSub = {
        endpoint: "https://push.example.com/sub",
        options: { applicationServerKey: mod.urlBase64ToUint8Array("key").buffer },
        toJSON: () => ({ endpoint: "https://push.example.com/sub" }),
      }
      const mockReg = {
        pushManager: {
          getSubscription: vi.fn().mockResolvedValue(null),
          subscribe: vi.fn().mockResolvedValue(mockSub),
        },
      }
      mockSWContainer.getRegistration.mockResolvedValue(mockReg)
      vi.stubEnv("VITE_VAPID_PUBLIC_KEY", "key")
      vi.stubGlobal("Notification", { permission: "granted" })

      // Does NOT throw — 409 is treated as success internally
      await expect(
        mod.ensurePushSubscription({ requestPermission: false, topics: ["news"] })
      ).resolves.toBeDefined()
    })
  })

  describe("Browser missing Push API → graceful null", () => {
    it("returns null from ensurePushSubscription when PushManager is absent", async () => {
      vi.stubGlobal("PushManager", undefined)

      const result = await mod.ensurePushSubscription()
      expect(result).toBeNull()
    })

    it("returns null from ensurePushSubscription when navigator.serviceWorker absent", async () => {
      vi.stubGlobal("navigator", {})

      const result = await mod.ensurePushSubscription()
      expect(result).toBeNull()
    })

    it("returns null from softSyncPushSubscription when PushManager is absent", async () => {
      vi.stubGlobal("PushManager", undefined)

      const result = await mod.softSyncPushSubscription()
      expect(result).toBeNull()
    })

    it("returns null from softSyncPushSubscription when Notification permission is not granted", async () => {
      vi.stubGlobal("PushManager", class {})
      vi.stubGlobal("Notification", { permission: "default" })

      const result = await mod.softSyncPushSubscription()
      expect(result).toBeNull()
    })
  })

  describe("Subscription serialization (endpoint, p256dh, auth)", () => {
    it("passes serialized subscription fields to saveSubscription", async () => {
      const { saveSubscription } = await import("@/api/notifications")
      vi.mocked(saveSubscription).mockResolvedValue({} as any)

      const rawP256dh = "BNcRdreALRFXTkOOUHK1EtK2wtwe4Ou2BrqZNnq73Ps" // pragma: allowlist secret
      const rawAuth = "tBHItJI5svbpez7KI4CCXg"

      const mockSub = {
        endpoint: "https://fcm.googleapis.com/fcm/send/unique-token",
        options: { applicationServerKey: mod.urlBase64ToUint8Array("testkey").buffer },
        expirationTime: null,
        toJSON: () => ({
          endpoint: "https://fcm.googleapis.com/fcm/send/unique-token",
          expirationTime: null,
          keys: {
            p256dh: rawP256dh,
            auth: rawAuth,
          },
        }),
      }
      const mockReg = {
        pushManager: {
          getSubscription: vi.fn().mockResolvedValue(null),
          subscribe: vi.fn().mockResolvedValue(mockSub),
        },
      }
      mockSWContainer.getRegistration.mockResolvedValue(mockReg)
      vi.stubEnv("VITE_VAPID_PUBLIC_KEY", "testkey")
      vi.stubGlobal("Notification", { permission: "granted" })

      await mod.ensurePushSubscription({ requestPermission: false })

      expect(saveSubscription).toHaveBeenCalledWith(
        expect.objectContaining({
          endpoint: "https://fcm.googleapis.com/fcm/send/unique-token",
          keys: expect.objectContaining({
            p256dh: rawP256dh,
            auth: rawAuth,
          }),
        }),
        undefined
      )
    })
  })
})
