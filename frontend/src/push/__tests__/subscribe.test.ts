/* eslint-disable @typescript-eslint/no-explicit-any */
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
  })
})
