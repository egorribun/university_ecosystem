import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

vi.unmock("@/push/subscribe")

import { deleteSubscription, getVapidPublicKey, saveSubscription } from "@/api/notifications"
import { withExpectedConsole } from "@/tests/strictConsole"

vi.mock("@/api/notifications", () => ({
  deleteSubscription: vi.fn(),
  getVapidPublicKey: vi.fn(),
  saveSubscription: vi.fn().mockResolvedValue({}),
}))

vi.mock("../register-sw", () => ({
  registerServiceWorker: vi.fn(),
}))

// Fake timers turn an unexpected retry back-off into a real-time hang; fail
// such a test quickly (the whole file runs in a few seconds) so a mutant that
// introduces a hang is reported as killed rather than as a Stryker timeout.
vi.setConfig({ testTimeout: 2_000 })

describe("subscribe", () => {
  let mockSWContainer: any
  let mod: any
  let storageMod: any
  let authStore: any

  beforeEach(async () => {
    localStorage.clear()
    vi.resetModules()
    vi.useFakeTimers()
    vi.clearAllMocks()
    vi.mocked(saveSubscription).mockResolvedValue({} as any)
    vi.mocked(deleteSubscription).mockResolvedValue(undefined)

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
    authStore = (await import("@/stores/useAuthStore")).useAuthStore
    // Persistence is bound to a confirmed authenticated identity.
    authStore.setState({ user: { id: "owner-a" }, loading: false })
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.unstubAllEnvs()
    vi.useRealTimers()
  })

  describe("Topic parsing and serialization", () => {
    beforeEach(() => {
      authStore.setState({ user: null, loading: false })
    })

    it("parses stored topics correctly from simple arrays and nested objects", () => {
      expect(mod.parseStoredTopics('["topicB", "topicA"]')).toEqual(["topicA", "topicB"])

      const payload = {
        version: 2,
        shared: ["sharedA"],
        perUser: {
          "user-1": ["userTopicB", "userTopicA"],
        },
      }

      authStore.setState({ user: { id: "user-1" }, loading: false })
      expect(mod.parseStoredTopics(JSON.stringify(payload))).toEqual(["userTopicA", "userTopicB"])

      authStore.setState({ user: null, loading: false })
      expect(mod.parseStoredTopics(JSON.stringify(payload))).toEqual(["sharedA"])

      expect(mod.parseStoredTopics({ shared: ["fallback"] }, { userId: "missing-user" })).toEqual([
        "fallback",
      ])
    })

    it("serializes and sets persisted topics under user namespace", () => {
      authStore.setState({ user: { id: "user-2" }, loading: false })

      mod.setPersistedTopics(["news", "events"])
      const stored: any = mod.getPersistedTopics({ userId: "user-2" })
      expect(stored).toEqual(["events", "news"])
    })

    it("uses only the confirmed authenticated user, never the profile cache, for topics", () => {
      vi.spyOn(storageMod.profileCacheStorage, "get").mockReturnValue({ data: { id: "owner-a" } })
      const topics = { shared: ["system"], perUser: { "owner-a": ["news"], "owner-b": ["events"] } }

      authStore.setState({ user: { id: "owner-b" }, loading: false })
      expect(mod.parseStoredTopics(topics)).toEqual(["events"])

      authStore.setState({ user: null, loading: false })
      expect(mod.parseStoredTopics(topics)).toEqual(["system"])

      // While auth is hydrating, neither the live placeholder nor the cached
      // profile may select a per-user namespace.
      authStore.setState({ user: { id: "owner-b" }, loading: true })
      expect(mod.parseStoredTopics(topics)).toEqual(["system"])
      authStore.setState({ user: { id: "ssr-stub" }, loading: false })
      expect(mod.parseStoredTopics(topics)).toEqual(["system"])
    })

    it("clears storage when topics are null/empty", () => {
      mod.setPersistedTopics(null)
      expect(mod.getPersistedTopics()).toBeUndefined()
    })

    it("falls back to an empty topic list for invalid runtime input", () => {
      mod.setPersistedTopics({} as unknown as string[])
      expect(mod.getPersistedTopics()).toEqual([])
    })

    it("handles malformed payloads and invalid user identifiers safely", () => {
      authStore.setState({ user: { id: {} }, loading: false })

      expect(mod.parseStoredTopics(null)).toBeUndefined()
      expect(mod.parseStoredTopics("{")).toBeUndefined()
      expect(
        mod.parseStoredTopics({ shared: undefined, topics: [" legacy ", "legacy", ""] })
      ).toEqual(["legacy"])
      expect(mod.parseStoredTopics([" topic ", null, "", "topic"])).toEqual(["topic"])
      expect(mod.parseStoredTopics(42)).toBeUndefined()
      expect(mod.parseStoredTopics({ shared: ["fallback"] }, { userId: " " })).toEqual(["fallback"])
      expect(mod.parseStoredTopics({}, { userId: {} as any })).toBeUndefined()
      expect(mod.parseStoredTopics({ topics: ["legacy"] })).toEqual(["legacy"])
    })

    it("treats only trimmed primitive identifiers as active users", () => {
      const payload = {
        perUser: {
          "[object Object]": ["private-object"],
          " ": ["private-whitespace"],
          "0": ["numeric-zero"],
        },
        shared: ["shared-fallback"],
      }

      expect(mod.parseStoredTopics(payload, { userId: {} as any })).toEqual(["shared-fallback"])
      expect(mod.parseStoredTopics(payload, { userId: " " })).toEqual(["shared-fallback"])
      expect(mod.parseStoredTopics(payload, { userId: 0 })).toEqual(["numeric-zero"])
    })

    it("ignores malformed per-user entries and falls back to shared topics", () => {
      expect(
        mod.parseStoredTopics(
          { perUser: { selected: "not-an-array" }, shared: ["shared-fallback"] },
          { userId: "selected" }
        )
      ).toEqual(["shared-fallback"])
      expect(
        mod.parseStoredTopics({ perUser: { null: ["wrong-user"] }, shared: ["shared"] })
      ).toEqual(["shared"])
    })

    it("normalizes valid per-user topics while clearing shared topics", () => {
      localStorage.setItem(
        "push:last_topics",
        JSON.stringify({
          version: 1,
          perUser: {
            "user-a": [" b ", "a", "a"],
            invalid: "not-an-array",
          },
        })
      )

      mod.setPersistedTopics(null)

      expect(JSON.parse(localStorage.getItem("push:last_topics") ?? "null")).toEqual({
        version: 2,
        perUser: { "user-a": ["a", "b"] },
      })

      localStorage.setItem("push:last_topics", JSON.stringify({ shared: ["orphaned"] }))
      mod.setPersistedTopics(null)
      expect(localStorage.getItem("push:last_topics")).toBeNull()

      localStorage.setItem("push:last_topics", JSON.stringify(["legacy"]))
      mod.setPersistedTopics(null)
      expect(localStorage.getItem("push:last_topics")).toBeNull()
    })

    it("removes unusable per-user payloads and malformed raw values", async () => {
      localStorage.setItem("push:last_topics", JSON.stringify({ perUser: { invalid: "nope" } }))
      mod.setPersistedTopics(null)
      expect(localStorage.getItem("push:last_topics")).toBeNull()

      localStorage.setItem("push:last_topics", "{")
      await withExpectedConsole("warn", '[Storage] Failed to parse key "push:last_topics"', () =>
        mod.setPersistedTopics(null)
      )
      expect(localStorage.getItem("push:last_topics")).toBeNull()

      localStorage.clear()
      mod.setPersistedTopics(null, { userId: "missing" })
      expect(localStorage.getItem("push:last_topics")).toBeNull()

      localStorage.setItem("push:last_topics", JSON.stringify(["legacy"]))
      mod.setPersistedTopics(null, { userId: "missing" })
      expect(localStorage.getItem("push:last_topics")).toBeNull()

      localStorage.setItem("push:last_topics", JSON.stringify(42))
      mod.setPersistedTopics(null, { userId: "missing" })
      expect(localStorage.getItem("push:last_topics")).toBeNull()

      localStorage.setItem("push:last_topics", JSON.stringify({ perUser: { invalid: "nope" } }))
      mod.setPersistedTopics(null, { userId: "missing" })
      expect(localStorage.getItem("push:last_topics")).toBeNull()

      localStorage.setItem("push:last_topics", "{")
      await withExpectedConsole("warn", '[Storage] Failed to parse key "push:last_topics"', () =>
        mod.setPersistedTopics(null, { userId: "missing" })
      )
      expect(localStorage.getItem("push:last_topics")).toBeNull()
    })

    it("removes only the selected user while preserving shared and other topics", () => {
      localStorage.setItem(
        "push:last_topics",
        JSON.stringify({
          version: 1,
          shared: ["topicB", "topicA", "topicA"],
          perUser: {
            keep: ["b", "a"],
            remove: ["private"],
            invalid: "not-an-array",
          },
        })
      )

      mod.setPersistedTopics(null, { userId: "remove" })

      expect(JSON.parse(localStorage.getItem("push:last_topics") ?? "null")).toEqual({
        version: 2,
        perUser: { keep: ["a", "b"] },
        shared: ["topicA", "topicB"],
      })
    })

    it("merges versioned, legacy, malformed, and shared topic payloads", async () => {
      localStorage.setItem(
        "push:last_topics",
        JSON.stringify({
          perUser: { keep: ["b"], selected: ["old"] },
          topics: ["legacyB", "legacyA"],
        })
      )

      mod.setPersistedTopics(["z", "z", " y "], { userId: "selected" })
      expect(JSON.parse(localStorage.getItem("push:last_topics") ?? "null")).toEqual({
        version: 2,
        perUser: { keep: ["b"], selected: ["y", "z"] },
        shared: ["legacyA", "legacyB"],
      })

      localStorage.setItem("push:last_topics", JSON.stringify(["oldShared"]))
      mod.setPersistedTopics(["new"], { userId: "selected" })
      expect(JSON.parse(localStorage.getItem("push:last_topics") ?? "null")).toEqual({
        version: 2,
        perUser: { selected: ["new"] },
        shared: ["oldShared"],
      })

      localStorage.setItem("push:last_topics", "{")
      await withExpectedConsole("warn", '[Storage] Failed to parse key "push:last_topics"', () =>
        mod.setPersistedTopics(["after"], { userId: "selected" })
      )
      expect(JSON.parse(localStorage.getItem("push:last_topics") ?? "null")).toEqual({
        version: 2,
        perUser: { selected: ["after"] },
      })

      localStorage.setItem("push:last_topics", JSON.stringify({ shared: ["explicit"] }))
      mod.setPersistedTopics(["next"], { userId: "selected" })
      expect(JSON.parse(localStorage.getItem("push:last_topics") ?? "null")).toEqual({
        version: 2,
        perUser: { selected: ["next"] },
        shared: ["explicit"],
      })

      localStorage.setItem("push:last_topics", JSON.stringify({ perUser: { keep: ["b"] } }))
      mod.setPersistedTopics(["shared"], { userId: null })
      expect(JSON.parse(localStorage.getItem("push:last_topics") ?? "null")).toEqual({
        version: 2,
        perUser: { keep: ["b"] },
        shared: ["shared"],
      })

      localStorage.setItem("push:last_topics", "{")
      await withExpectedConsole("warn", '[Storage] Failed to parse key "push:last_topics"', () =>
        mod.setPersistedTopics(["after-malformed"], { userId: null })
      )
      expect(JSON.parse(localStorage.getItem("push:last_topics") ?? "null")).toEqual({
        version: 2,
        shared: ["after-malformed"],
      })
    })

    it("normalizes defensive legacy topic shapes without inventing namespaces", () => {
      localStorage.setItem(
        "push:last_topics",
        JSON.stringify({ perUser: { invalid: "not-an-array" }, shared: ["shared"] })
      )
      mod.setPersistedTopics(["selected"], { userId: "selected" })
      expect(JSON.parse(localStorage.getItem("push:last_topics") ?? "null")).toEqual({
        version: 2,
        perUser: { selected: ["selected"] },
        shared: ["shared"],
      })

      localStorage.setItem("push:last_topics", JSON.stringify(42))
      mod.setPersistedTopics(["selected"], { userId: "selected" })
      expect(JSON.parse(localStorage.getItem("push:last_topics") ?? "null")).toEqual({
        version: 2,
        perUser: { selected: ["selected"] },
      })

      localStorage.setItem("push:last_topics", JSON.stringify({ shared: ["old"] }))
      mod.setPersistedTopics(["new"], { userId: null })
      expect(JSON.parse(localStorage.getItem("push:last_topics") ?? "null")).toEqual({
        version: 2,
        shared: ["new"],
      })

      localStorage.setItem(
        "push:last_topics",
        JSON.stringify({ perUser: { invalid: "not-an-array" } })
      )
      mod.setPersistedTopics(["new"], { userId: null })
      expect(JSON.parse(localStorage.getItem("push:last_topics") ?? "null")).toEqual({
        version: 2,
        shared: ["new"],
      })
    })

    it("removes the last per-user namespace while preserving shared topics", () => {
      localStorage.setItem(
        "push:last_topics",
        JSON.stringify({ shared: ["shared"], perUser: { remove: ["private"] } })
      )

      mod.setPersistedTopics(null, { userId: "remove" })

      expect(JSON.parse(localStorage.getItem("push:last_topics") ?? "null")).toEqual({
        version: 2,
        shared: ["shared"],
      })
    })

    it("handles parser failures while normalizing stored payloads", () => {
      const withSecondParseFailure = (callback: () => void) => {
        const originalParse = JSON.parse
        let parseCount = 0
        const parseSpy = vi.spyOn(JSON, "parse").mockImplementation(((raw: string) => {
          parseCount += 1
          if (parseCount === 2) {
            throw new SyntaxError("simulated parser failure")
          }
          return originalParse(raw)
        }) as typeof JSON.parse)

        try {
          callback()
        } finally {
          parseSpy.mockRestore()
        }
      }

      localStorage.setItem("push:last_topics", JSON.stringify({ perUser: { keep: ["a"] } }))
      withSecondParseFailure(() => mod.setPersistedTopics(null, { userId: null }))
      expect(localStorage.getItem("push:last_topics")).toBeNull()

      localStorage.setItem("push:last_topics", JSON.stringify({ perUser: { keep: ["a"] } }))
      withSecondParseFailure(() => mod.setPersistedTopics(null, { userId: "remove" }))
      expect(localStorage.getItem("push:last_topics")).toBeNull()

      localStorage.setItem("push:last_topics", JSON.stringify({ perUser: { keep: ["a"] } }))
      withSecondParseFailure(() => mod.setPersistedTopics(["selected"], { userId: "selected" }))
      expect(JSON.parse(localStorage.getItem("push:last_topics") ?? "null")).toEqual({
        version: 2,
        perUser: { selected: ["selected"] },
      })

      localStorage.setItem("push:last_topics", JSON.stringify({ perUser: { keep: ["a"] } }))
      withSecondParseFailure(() => mod.setPersistedTopics(["shared"], { userId: null }))
      expect(JSON.parse(localStorage.getItem("push:last_topics") ?? "null")).toEqual({
        version: 2,
        shared: ["shared"],
      })
    })

    it("swallows a storage write failure when persisting topics", () => {
      const setSpy = vi.spyOn(storageMod.StorageItem.prototype, "set").mockImplementation(() => {
        throw new Error("storage quota exceeded")
      })

      try {
        expect(() => mod.setPersistedTopics(["topic"], { userId: "user-1" })).not.toThrow()
        expect(setSpy).toHaveBeenCalled()
      } finally {
        setSpy.mockRestore()
      }
    })
  })

  describe("Consent and Browser recovery", () => {
    it("handles explicit push consent updates", () => {
      mod.setPushConsent(true)
      expect(mod.hasPushConsent()).toBe(true)

      mod.setPushConsent(false)
      expect(mod.hasPushConsent()).toBe(false)
    })

    const RECOVERY_KEY = "cmVjb3Zlcg"
    const makeRecoverableSub = (endpoint: string) => ({
      endpoint,
      options: { applicationServerKey: mod.urlBase64ToUint8Array(RECOVERY_KEY).buffer },
      toJSON: () => ({ endpoint }),
    })
    const installRecoverableRegistration = (subscription: unknown) => {
      const registration = {
        pushManager: {
          getSubscription: vi.fn().mockResolvedValue(subscription),
          subscribe: vi.fn(),
        },
      }
      mockSWContainer.getRegistration.mockResolvedValue(registration)
      vi.stubEnv("VITE_VAPID_PUBLIC_KEY", RECOVERY_KEY)
      vi.stubGlobal("Notification", { permission: "granted" })
      return registration
    }

    it("recovers consent only after the confirmed owner persisted the browser subscription", async () => {
      const subscription = makeRecoverableSub("https://fcm.googleapis.com/123")
      installRecoverableRegistration(subscription)
      const consentDuringSave: boolean[] = []
      vi.mocked(saveSubscription).mockImplementation(async () => {
        consentDuringSave.push(mod.hasPushConsent())
        return {} as any
      })

      const recovered = await mod.recoverPushConsentFromBrowser()

      expect(recovered).toBe(true)
      expect(mod.hasPushConsent()).toBe(true)
      expect(consentDuringSave).toEqual([false])
      // Recovery never chooses topics: the server binds the endpoint to the
      // caller's canonical preference.
      expect(saveSubscription).toHaveBeenCalledWith(subscription.toJSON(), undefined)
      expect(localStorage.getItem("push:last_owner")).toBe(JSON.stringify("owner-a"))
    })

    it("recovers through an explicitly supplied registration", async () => {
      const subscription = makeRecoverableSub("https://push.example.com/explicit-registration")
      const registration = installRecoverableRegistration(subscription)
      mockSWContainer.getRegistration.mockResolvedValue(null)

      await expect(mod.recoverPushConsentFromBrowser(registration)).resolves.toBe(true)
      expect(mockSWContainer.getRegistration).not.toHaveBeenCalled()
      expect(saveSubscription).toHaveBeenCalledOnce()
    })

    it("fails closed without persisting while the identity is unconfirmed", async () => {
      installRecoverableRegistration(makeRecoverableSub("https://push.example.com/cold-boot"))
      authStore.setState({ user: { id: "owner-a" }, loading: true })

      await expect(mod.recoverPushConsentFromBrowser()).resolves.toBe(false)
      expect(saveSubscription).not.toHaveBeenCalled()
      expect(mod.hasPushConsent()).toBe(false)
    })

    it("does not recover consent when the resync is rate limited", async () => {
      installRecoverableRegistration(makeRecoverableSub("https://push.example.com/recovered-rate"))
      vi.mocked(saveSubscription).mockRejectedValue({ response: { status: 429 } })

      await withExpectedConsole("warn", "Rate limited (429)", () =>
        withExpectedConsole("error", "Failed to persist push subscription", () =>
          withExpectedConsole("warn", "Failed to re-sync recovered push subscription", () =>
            expect(mod.recoverPushConsentFromBrowser()).resolves.toBe(false)
          )
        )
      )
      expect(mod.hasPushConsent()).toBe(false)
      expect(saveSubscription).toHaveBeenCalledOnce()
    })

    it("does not recover consent when resync permanently fails", async () => {
      installRecoverableRegistration(
        makeRecoverableSub("https://push.example.com/recovered-failure")
      )
      vi.mocked(saveSubscription).mockRejectedValue(new Error("server unavailable"))

      await withExpectedConsole("warn", "Failed to re-sync recovered push subscription", () =>
        withExpectedConsole(
          "error",
          "Failed to persist push subscription",
          async () => {
            const promise = mod.recoverPushConsentFromBrowser()
            await vi.runAllTimersAsync()

            await expect(promise).resolves.toBe(false)
          },
          2
        )
      )
      expect(mod.hasPushConsent()).toBe(false)
      expect(saveSubscription).toHaveBeenCalledTimes(3)
    })

    it("does not recover consent when the account changes during the server write", async () => {
      installRecoverableRegistration(makeRecoverableSub("https://push.example.com/switch"))
      vi.mocked(saveSubscription).mockImplementation(async () => {
        authStore.setState({ user: { id: "owner-b" }, loading: false })
        return {} as any
      })

      await withExpectedConsole("error", "Failed to persist push subscription", () =>
        withExpectedConsole("warn", "Failed to re-sync recovered push subscription", () =>
          expect(mod.recoverPushConsentFromBrowser()).resolves.toBe(false)
        )
      )
      expect(mod.hasPushConsent()).toBe(false)
      expect(localStorage.getItem("push:last_owner")).toBeNull()
    })

    it("returns false until browser recovery prerequisites are satisfied", async () => {
      vi.stubGlobal("Notification", { permission: "granted" })
      mod.setPushConsent(true)
      await expect(mod.recoverPushConsentFromBrowser()).resolves.toBe(false)

      mod.setPushConsent(false)
      vi.stubGlobal("Notification", { permission: "default" })
      await expect(mod.recoverPushConsentFromBrowser()).resolves.toBe(false)

      vi.stubGlobal("Notification", { permission: "granted" })
      mockSWContainer.getRegistration.mockResolvedValue(null)
      await expect(mod.recoverPushConsentFromBrowser()).resolves.toBe(false)

      const emptyReg = {
        pushManager: { getSubscription: vi.fn().mockResolvedValue(null) },
      }
      mockSWContainer.getRegistration.mockResolvedValue(emptyReg)
      await expect(mod.recoverPushConsentFromBrowser()).resolves.toBe(false)

      vi.stubGlobal("navigator", {})
      await expect(mod.recoverPushConsentFromBrowser()).resolves.toBe(false)
      expect(saveSubscription).not.toHaveBeenCalled()
      expect(mod.hasPushConsent()).toBe(false)
    })

    it("returns false when the recovered subscription cannot be re-synced", async () => {
      installRecoverableRegistration(makeRecoverableSub("https://push.example.com/no-key"))
      vi.stubEnv("VITE_VAPID_PUBLIC_KEY", "")
      vi.mocked(getVapidPublicKey).mockResolvedValue(null as any)

      await withExpectedConsole("warn", "VAPID public key is not configured", () =>
        expect(mod.recoverPushConsentFromBrowser()).resolves.toBe(false)
      )
      expect(saveSubscription).not.toHaveBeenCalled()
      expect(mod.hasPushConsent()).toBe(false)
    })

    it("returns false when browser subscription lookup throws during recovery", async () => {
      const mockReg = {
        pushManager: {
          getSubscription: vi.fn().mockRejectedValue(new Error("lookup failed")),
        },
      }
      mockSWContainer.getRegistration.mockResolvedValue(mockReg)
      vi.stubGlobal("Notification", { permission: "granted" })

      await withExpectedConsole("warn", "Failed to re-sync recovered push subscription", () =>
        expect(mod.recoverPushConsentFromBrowser()).resolves.toBe(false)
      )
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
      expect(vi.getTimerCount()).toBe(0)
    })

    it("does not auto-register a worker in Lighthouse audit builds", async () => {
      vi.stubEnv("VITE_LHCI", "true")
      const { registerServiceWorker } = await import("../register-sw")
      mockSWContainer.getRegistration.mockResolvedValue(null)
      mockSWContainer.ready = new Promise(() => {})

      await expect(mod.resolveServiceWorkerRegistration()).resolves.toBeNull()
      expect(registerServiceWorker).not.toHaveBeenCalled()
      expect(mockSWContainer.getRegistration).not.toHaveBeenCalled()
    })

    it("falls back to auto-registration when lookup and ready both fail", async () => {
      const fallbackReg: any = { active: {} }
      const { registerServiceWorker } = await import("../register-sw")
      vi.mocked(registerServiceWorker).mockResolvedValue(fallbackReg)
      mockSWContainer.getRegistration.mockRejectedValue(new Error("lookup failed"))
      mockSWContainer.ready = Promise.reject(new Error("ready failed"))

      await withExpectedConsole(
        "warn",
        /Failed to get existing service worker registration|Service worker ready promise rejected/,
        () => expect(mod.resolveServiceWorkerRegistration()).resolves.toBe(fallbackReg),
        2
      )
    })

    it("uses the final registration lookup when auto-registration fails", async () => {
      const finalReg: any = { active: {} }
      const { registerServiceWorker } = await import("../register-sw")
      vi.mocked(registerServiceWorker).mockRejectedValue(new Error("register failed"))
      mockSWContainer.ready = Promise.resolve(null)
      mockSWContainer.getRegistration.mockResolvedValueOnce(null).mockResolvedValueOnce(finalReg)

      await withExpectedConsole("warn", "Failed to auto-register service worker", () =>
        expect(mod.resolveServiceWorkerRegistration()).resolves.toBe(finalReg)
      )
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

      await withExpectedConsole("warn", "Failed to await service worker readiness", () =>
        expect(mod.resolveServiceWorkerRegistration()).resolves.toBeNull()
      )
    })

    it("returns null when the final service worker lookup throws", async () => {
      const { registerServiceWorker } = await import("../register-sw")
      vi.mocked(registerServiceWorker).mockResolvedValue(null)
      mockSWContainer.ready = Promise.resolve(null)
      mockSWContainer.getRegistration
        .mockResolvedValueOnce(null)
        .mockRejectedValueOnce(new Error("final lookup failed"))

      await withExpectedConsole(
        "warn",
        "Failed to get service worker registration after timeout",
        () => expect(mod.resolveServiceWorkerRegistration()).resolves.toBeNull()
      )
    })
  })

  describe("resolveVapidPublicKey", () => {
    it("resolves from environment variables first", async () => {
      vi.stubEnv("VITE_VAPID_PUBLIC_KEY", "env-key-123")
      const key = await mod.resolveVapidPublicKey()
      expect(key).toBe("env-key-123")
    })

    it("trims an environment VAPID key and falls back when it is undefined", async () => {
      vi.stubEnv("VITE_VAPID_PUBLIC_KEY", "  env-key-123  ")
      await expect(mod.resolveVapidPublicKey()).resolves.toBe("env-key-123")

      vi.resetModules()
      vi.stubEnv("VITE_VAPID_PUBLIC_KEY", undefined as unknown as string)
      vi.mocked(getVapidPublicKey).mockResolvedValue("api-key-456")
      const fresh = await import("../subscribe")
      await expect(fresh.resolveVapidPublicKey()).resolves.toBe("api-key-456")
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

      await withExpectedConsole("warn", "Failed to fetch VAPID public key", () =>
        expect(mod.resolveVapidPublicKey()).resolves.toBeNull()
      )
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

    it("decodes URL-safe values and applies padding for every base64 remainder", () => {
      expect(Array.from(mod.urlBase64ToUint8Array("-_8"))).toEqual([251, 255])
      expect(Array.from(mod.urlBase64ToUint8Array("AQ"))).toEqual([1])
      expect(Array.from(mod.urlBase64ToUint8Array("AQI"))).toEqual([1, 2])
      expect(Array.from(mod.urlBase64ToUint8Array("AQID"))).toEqual([1, 2, 3])
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
      vi.mocked(saveSubscription).mockResolvedValue({ topics: ["topicB", "topicA"] } as any)

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

    it("replaces an existing subscription when its application key is missing", async () => {
      const unsubscribeSpy = vi.fn().mockResolvedValue(true)
      const staleSub = {
        endpoint: "https://push.example.com/missing-key",
        unsubscribe: unsubscribeSpy,
        toJSON: () => ({ endpoint: "https://push.example.com/missing-key" }),
      }
      const freshSub = {
        endpoint: "https://push.example.com/fresh-key",
        options: { applicationServerKey: mod.urlBase64ToUint8Array("ZnJlc2g").buffer },
        toJSON: () => ({ endpoint: "https://push.example.com/fresh-key" }),
      }
      const mockReg = {
        pushManager: {
          getSubscription: vi.fn().mockResolvedValue(staleSub),
          subscribe: vi.fn().mockResolvedValue(freshSub),
        },
      }
      vi.stubGlobal("Notification", { permission: "granted" })

      await expect(
        mod.ensurePushSubscription({
          registration: mockReg,
          vapidPublicKey: "ZnJlc2g",
          requestPermission: false,
        })
      ).resolves.toBe(freshSub)
      expect(unsubscribeSpy).toHaveBeenCalledOnce()
    })

    it("reuses an unexpired subscription only when every application-key byte matches", async () => {
      const desiredKey = mod.urlBase64ToUint8Array("matching-key")
      const matchingSub = {
        endpoint: "https://push.example.com/matching-key",
        expirationTime: Date.now() + 7 * 24 * 60 * 60 * 1000,
        options: { applicationServerKey: desiredKey.buffer },
        unsubscribe: vi.fn().mockResolvedValue(true),
        toJSON: () => ({ endpoint: "https://push.example.com/matching-key" }),
      }
      const matchingReg = {
        pushManager: {
          getSubscription: vi.fn().mockResolvedValue(matchingSub),
          subscribe: vi.fn(),
        },
      }
      vi.stubGlobal("Notification", { permission: "granted" })

      await expect(
        mod.ensurePushSubscription({
          registration: matchingReg,
          vapidPublicKey: "matching-key",
          requestPermission: false,
        })
      ).resolves.toBe(matchingSub)
      expect(matchingSub.unsubscribe).not.toHaveBeenCalled()
      expect(matchingReg.pushManager.subscribe).not.toHaveBeenCalled()

      const almostMatching = {
        ...matchingSub,
        endpoint: "https://push.example.com/almost-matching",
        options: {
          applicationServerKey: (() => {
            const key = new Uint8Array(desiredKey)
            const lastIndex = key.length - 1
            const lastValue = key[lastIndex] ?? 0
            key[lastIndex] = lastValue ^ 1
            return key.buffer
          })(),
        },
      }
      const replaceReg = {
        pushManager: {
          getSubscription: vi.fn().mockResolvedValue(almostMatching),
          subscribe: vi.fn().mockResolvedValue(matchingSub),
        },
      }
      await expect(
        mod.ensurePushSubscription({
          registration: replaceReg,
          vapidPublicKey: "matching-key",
          requestPermission: false,
        })
      ).resolves.toBe(matchingSub)
      expect(almostMatching.unsubscribe).toHaveBeenCalledOnce()
      expect(replaceReg.pushManager.subscribe).toHaveBeenCalledWith({
        userVisibleOnly: true,
        applicationServerKey: desiredKey,
      })
    })

    it("replaces a subscription whose key is only a prefix of the desired key", async () => {
      const desiredKey = mod.urlBase64ToUint8Array("cHJlZml4LWtleQ")
      const replacement = {
        endpoint: "https://push.example.com/prefix-replacement",
        options: { applicationServerKey: desiredKey.buffer },
        toJSON: () => ({ endpoint: "https://push.example.com/prefix-replacement" }),
      }
      const prefixSub = {
        endpoint: "https://push.example.com/prefix",
        options: { applicationServerKey: desiredKey.slice(0, -1).buffer },
        toJSON: () => ({ endpoint: "https://push.example.com/prefix" }),
        unsubscribe: vi.fn().mockResolvedValue(true),
      }
      const registration = {
        pushManager: {
          getSubscription: vi.fn().mockResolvedValue(prefixSub),
          subscribe: vi.fn().mockResolvedValue(replacement),
        },
      }
      vi.stubGlobal("Notification", { permission: "granted" })

      await expect(
        mod.ensurePushSubscription({
          registration,
          vapidPublicKey: "cHJlZml4LWtleQ",
          requestPermission: false,
        })
      ).resolves.toBe(replacement)
      expect(prefixSub.unsubscribe).toHaveBeenCalledOnce()
    })

    it.each([
      ["one day", 24 * 60 * 60 * 1000, true],
      ["thirty days", 30 * 24 * 60 * 60 * 1000, false],
    ] as const)(
      "rotates a matching subscription that expires in %s only when inside the window",
      async (_label, remainingMs, rotates) => {
        const key = mod.urlBase64ToUint8Array("ZXhwaXJ5LXdpbmRvdw")
        const current = {
          endpoint: "https://push.example.com/expiry-window",
          expirationTime: Date.now() + remainingMs,
          options: { applicationServerKey: key.buffer },
          toJSON: () => ({ endpoint: "https://push.example.com/expiry-window" }),
          unsubscribe: vi.fn().mockResolvedValue(true),
        }
        const fresh = { ...current, endpoint: "https://push.example.com/expiry-fresh" }
        const registration = {
          pushManager: {
            getSubscription: vi.fn().mockResolvedValue(current),
            subscribe: vi.fn().mockResolvedValue(fresh),
          },
        }
        vi.stubGlobal("Notification", { permission: "granted" })

        await expect(
          mod.ensurePushSubscription({
            registration,
            vapidPublicKey: "ZXhwaXJ5LXdpbmRvdw",
            requestPermission: false,
          })
        ).resolves.toBe(rotates ? fresh : current)
        expect(current.unsubscribe).toHaveBeenCalledTimes(rotates ? 1 : 0)
      }
    )

    it("does not prompt when called without options and permission is undecided", async () => {
      const registration = {
        pushManager: { getSubscription: vi.fn(), subscribe: vi.fn() },
      }
      mockSWContainer.getRegistration.mockResolvedValue(registration)
      vi.stubGlobal("Notification", {
        permission: "default",
        requestPermission: vi.fn(),
      })

      await expect(mod.ensurePushSubscription()).resolves.toBeNull()
      expect(Notification.requestPermission).not.toHaveBeenCalled()
      expect(registration.pushManager.subscribe).not.toHaveBeenCalled()
    })

    it.each([
      [null, "null-expiration"],
      [0, "zero-expiration"],
      [-1, "negative-expiration"],
    ] as const)(
      "does not rotate a matching subscription with %s expiration",
      async (expirationTime, suffix) => {
        const key = mod.urlBase64ToUint8Array(`expiry-${suffix}`)
        const subscription = {
          endpoint: `https://push.example.com/${suffix}`,
          expirationTime,
          options: { applicationServerKey: key.buffer },
          unsubscribe: vi.fn().mockResolvedValue(true),
          toJSON: () => ({ endpoint: `https://push.example.com/${suffix}` }),
        }
        const registration = {
          pushManager: {
            getSubscription: vi.fn().mockResolvedValue(subscription),
            subscribe: vi.fn(),
          },
        }
        vi.stubGlobal("Notification", { permission: "granted" })

        await expect(
          mod.ensurePushSubscription({
            registration,
            vapidPublicKey: `expiry-${suffix}`,
            requestPermission: false,
          })
        ).resolves.toBe(subscription)
        expect(subscription.unsubscribe).not.toHaveBeenCalled()
        expect(registration.pushManager.subscribe).not.toHaveBeenCalled()
      }
    )

    it("keeps a matching subscription exactly at the expiry threshold", async () => {
      vi.setSystemTime(0)
      const key = mod.urlBase64ToUint8Array("expiry-threshold")
      const subscription = {
        endpoint: "https://push.example.com/threshold-expiration",
        expirationTime: 3 * 24 * 60 * 60 * 1000,
        options: { applicationServerKey: key.buffer },
        unsubscribe: vi.fn().mockResolvedValue(true),
        toJSON: () => ({ endpoint: "https://push.example.com/threshold-expiration" }),
      }
      const registration = {
        pushManager: {
          getSubscription: vi.fn().mockResolvedValue(subscription),
          subscribe: vi.fn(),
        },
      }
      vi.stubGlobal("Notification", { permission: "granted" })

      await expect(
        mod.ensurePushSubscription({
          registration,
          vapidPublicKey: "expiry-threshold",
          requestPermission: false,
        })
      ).resolves.toBe(subscription)
      expect(subscription.unsubscribe).not.toHaveBeenCalled()
      expect(registration.pushManager.subscribe).not.toHaveBeenCalled()
    })

    it("requires an explicit permission request and safely handles omitted options", async () => {
      const registration = {
        pushManager: {
          getSubscription: vi.fn().mockResolvedValue(null),
          subscribe: vi.fn(),
        },
      }
      vi.stubEnv("VITE_VAPID_PUBLIC_KEY", "omitted-options")
      vi.stubGlobal("Notification", {
        permission: "default",
        requestPermission: vi.fn().mockResolvedValue("granted"),
      })

      await expect(mod.ensurePushSubscription({ registration })).resolves.toBeNull()
      expect(Notification.requestPermission).not.toHaveBeenCalled()
      expect(registration.pushManager.subscribe).not.toHaveBeenCalled()

      vi.stubGlobal("Notification", { permission: "granted" })
      const subscription = {
        endpoint: "https://push.example.com/omitted-options",
        options: {
          applicationServerKey: mod.urlBase64ToUint8Array("omitted-options").buffer,
        },
        toJSON: () => ({ endpoint: "https://push.example.com/omitted-options" }),
      }
      registration.pushManager.getSubscription.mockResolvedValue(subscription)
      await expect(mod.ensurePushSubscription({ registration })).resolves.toBe(subscription)
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

    it("joins an in-flight implicit sync for the same owner", async () => {
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
      expect(saveSubscription).toHaveBeenCalledOnce()
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

      await withExpectedConsole("warn", "Failed to unsubscribe push subscription", () =>
        expect(
          mod.ensurePushSubscription({
            registration: mockReg,
            vapidPublicKey: "ZnJlc2g",
            requestPermission: false,
          })
        ).resolves.toBe(freshSub)
      )
      expect(staleSub.unsubscribe).toHaveBeenCalledOnce()
      expect(mockReg.pushManager.subscribe).toHaveBeenCalledOnce()
    })

    it("keeps stale-unsubscribe diagnostics disabled outside development", async () => {
      vi.stubEnv("DEV", false)
      const staleSub = {
        options: { applicationServerKey: new Uint8Array([0]).buffer },
        unsubscribe: vi.fn().mockRejectedValue(new Error("unsubscribe failed")),
      }
      const freshSub = {
        endpoint: "https://push.example.com/fresh-production",
        options: { applicationServerKey: mod.urlBase64ToUint8Array("ZnJlc2g").buffer },
        toJSON: () => ({ endpoint: "https://push.example.com/fresh-production" }),
      }
      const mockReg = {
        pushManager: {
          getSubscription: vi.fn().mockResolvedValue(staleSub),
          subscribe: vi.fn().mockResolvedValue(freshSub),
        },
      }
      vi.stubGlobal("Notification", { permission: "granted" })

      await expect(
        mod.ensurePushSubscription({
          registration: mockReg,
          vapidPublicKey: "ZnJlc2g",
          requestPermission: false,
        })
      ).resolves.toBe(freshSub)
      expect(staleSub.unsubscribe).toHaveBeenCalledOnce()
    })

    it("does not retry persistence after a 429 response", async () => {
      vi.mocked(saveSubscription).mockRejectedValue({
        isAxiosError: true,
        response: { status: 429 },
      })
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

      await withExpectedConsole("warn", "Rate limited (429)", () =>
        withExpectedConsole("error", "Failed to persist push subscription", () =>
          expect(mod.ensurePushSubscription({ requestPermission: false })).rejects.toEqual({
            isAxiosError: true,
            response: { status: 429 },
          })
        )
      )
      expect(saveSubscription).toHaveBeenCalledOnce()
      expect(mod.hasPushConsent()).toBe(false)
      expect(localStorage.getItem("push:last_payload")).toBeNull()
    })

    it("refreshes the local sync timestamp when persistence is already current", async () => {
      const { useAuthStore } = await import("@/stores/useAuthStore")
      useAuthStore.setState({ user: { id: "owner-a" } as any })
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
      await mod.ensurePushSubscription({ registration: mockReg, requestPermission: false })

      expect(saveSubscription).toHaveBeenCalledOnce()
    })

    it("rebinds a legacy cached endpoint when the authenticated account changes", async () => {
      const { useAuthStore } = await import("@/stores/useAuthStore")
      const mockSub = {
        endpoint: "https://push.example.com/shared-browser",
        options: { applicationServerKey: mod.urlBase64ToUint8Array("b3duZXI").buffer },
        toJSON: () => ({ endpoint: "https://push.example.com/shared-browser" }),
      }
      const mockReg = {
        pushManager: {
          getSubscription: vi.fn().mockResolvedValue(mockSub),
          subscribe: vi.fn(),
        },
      }
      vi.stubGlobal("Notification", { permission: "granted" })
      useAuthStore.setState({ user: { id: "owner-a" } as any })

      await mod.ensurePushSubscription({
        registration: mockReg,
        vapidPublicKey: "b3duZXI",
        requestPermission: false,
      })
      // Older clients cached topics as a plain array, which previously made
      // the second call skip POST even though the server still owned user A.
      localStorage.setItem("push:last_topics", "[]")
      useAuthStore.setState({ user: { id: "owner-b" } as any })

      await mod.ensurePushSubscription({
        registration: mockReg,
        vapidPublicKey: "b3duZXI",
        requestPermission: false,
      })

      expect(saveSubscription).toHaveBeenCalledTimes(2)
      expect(saveSubscription).toHaveBeenNthCalledWith(2, mockSub.toJSON(), undefined)
      expect(localStorage.getItem("push:last_owner")).toBe(JSON.stringify("owner-b"))
    })

    it("does not cache ownership if the account changes during the server write", async () => {
      const { useAuthStore } = await import("@/stores/useAuthStore")
      useAuthStore.setState({ user: { id: "owner-a" } as any })
      vi.mocked(saveSubscription).mockImplementation(async () => {
        useAuthStore.setState({ user: { id: "owner-b" } as any })
        return {} as any
      })
      const mockSub = {
        endpoint: "https://push.example.com/in-flight-account-change",
        options: { applicationServerKey: mod.urlBase64ToUint8Array("a2V5").buffer },
        toJSON: () => ({ endpoint: "https://push.example.com/in-flight-account-change" }),
      }
      const mockReg = {
        pushManager: {
          getSubscription: vi.fn().mockResolvedValue(mockSub),
          subscribe: vi.fn(),
        },
      }
      vi.stubGlobal("Notification", { permission: "granted" })

      await withExpectedConsole("error", "Failed to persist push subscription", () =>
        expect(
          mod.ensurePushSubscription({
            registration: mockReg,
            vapidPublicKey: "a2V5",
            requestPermission: false,
          })
        ).rejects.toMatchObject({ name: "PushIdentityUnconfirmedError" })
      )
      expect(saveSubscription).toHaveBeenCalledOnce()
      expect(localStorage.getItem("push:last_owner")).toBeNull()
      expect(localStorage.getItem("push:last_payload")).toBeNull()
    })

    it("persists a changed topic set when the subscription payload is unchanged", async () => {
      const mockSub = {
        endpoint: "https://push.example.com/topic-change",
        options: { applicationServerKey: mod.urlBase64ToUint8Array("dG9waWM").buffer },
        expirationTime: null,
        toJSON: () => ({ endpoint: "https://push.example.com/topic-change" }),
      }
      const mockReg = {
        pushManager: {
          getSubscription: vi.fn().mockResolvedValue(mockSub),
          subscribe: vi.fn(),
        },
      }
      vi.stubGlobal("Notification", { permission: "granted" })

      await mod.ensurePushSubscription({
        registration: mockReg,
        vapidPublicKey: "dG9waWM",
        topics: ["news"],
        requestPermission: false,
      })
      vi.mocked(saveSubscription).mockClear()

      await mod.ensurePushSubscription({
        registration: mockReg,
        vapidPublicKey: "dG9waWM",
        topics: ["events"],
        requestPermission: false,
      })

      expect(saveSubscription).toHaveBeenCalledOnce()
      expect(saveSubscription).toHaveBeenCalledWith(expect.anything(), ["events"])
    })

    it("accepts omitted options when browser permission is already granted", async () => {
      const mockSub = {
        endpoint: "https://push.example.com/omitted-options",
        options: { applicationServerKey: mod.urlBase64ToUint8Array("omitted-key").buffer },
        toJSON: () => ({ endpoint: "https://push.example.com/omitted-options" }),
      }
      const mockReg = {
        pushManager: {
          getSubscription: vi.fn().mockResolvedValue(null),
          subscribe: vi.fn().mockResolvedValue(mockSub),
        },
      }
      mockSWContainer.getRegistration.mockResolvedValue(mockReg)
      vi.stubGlobal("Notification", { permission: "granted" })
      vi.stubEnv("VITE_VAPID_PUBLIC_KEY", "omitted-key")

      await expect(mod.ensurePushSubscription()).resolves.toBe(mockSub)
      expect(mockReg.pushManager.subscribe).toHaveBeenCalledOnce()
    })

    it("propagates a permanent persistence failure after bounded retries", async () => {
      const persistenceError = new Error("permanent failure")
      vi.mocked(saveSubscription).mockRejectedValue(persistenceError)
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

      await withExpectedConsole(
        "error",
        "Failed to persist push subscription",
        async () => {
          const promise = mod.ensurePushSubscription({ requestPermission: false })
          const settled = promise.then(
            (value: unknown) => ({ value }),
            (error: unknown) => ({ error })
          )
          await vi.runAllTimersAsync()

          await expect(settled).resolves.toEqual({ error: persistenceError })
        },
        2
      )
      expect(saveSubscription).toHaveBeenCalledTimes(3)
    })

    it("retries a rejection that carries no response at all", async () => {
      vi.mocked(saveSubscription).mockRejectedValue(null)
      const mockSub = {
        endpoint: "https://push.example.com/null-rejection",
        options: { applicationServerKey: mod.urlBase64ToUint8Array("bnVsbA").buffer },
        toJSON: () => ({ endpoint: "https://push.example.com/null-rejection" }),
      }
      mockSWContainer.getRegistration.mockResolvedValue({
        pushManager: {
          getSubscription: vi.fn().mockResolvedValue(null),
          subscribe: vi.fn().mockResolvedValue(mockSub),
        },
      })
      vi.stubEnv("VITE_VAPID_PUBLIC_KEY", "bnVsbA")
      vi.stubGlobal("Notification", { permission: "granted" })

      await withExpectedConsole(
        "error",
        "Failed to persist push subscription",
        async () => {
          const settled = mod.ensurePushSubscription({ requestPermission: false }).then(
            (value: unknown) => ({ value }),
            (error: unknown) => ({ error })
          )
          await vi.runAllTimersAsync()

          await expect(settled).resolves.toEqual({ error: null })
        },
        2
      )
      expect(saveSubscription).toHaveBeenCalledTimes(3)
    })

    it("uses the bounded exponential retry schedule including jitter", async () => {
      const retryError = new Error("retryable failure")
      vi.mocked(saveSubscription).mockRejectedValue(retryError)
      const mockSub = {
        endpoint: "https://push.example.com/retry-schedule",
        options: { applicationServerKey: mod.urlBase64ToUint8Array("cmV0cnk").buffer },
        toJSON: () => ({ endpoint: "https://push.example.com/retry-schedule" }),
      }
      const mockReg = {
        pushManager: {
          getSubscription: vi.fn().mockResolvedValue(null),
          subscribe: vi.fn().mockResolvedValue(mockSub),
        },
      }
      const randomSpy = vi.spyOn(Math, "random").mockReturnValue(1)
      vi.stubGlobal("Notification", { permission: "granted" })

      try {
        await withExpectedConsole(
          "error",
          "Failed to persist push subscription",
          async () => {
            const promise = mod.ensurePushSubscription({
              registration: mockReg,
              vapidPublicKey: "cmV0cnk",
              requestPermission: false,
            })
            const settled = promise.then(
              (value: unknown) => ({ value }),
              (error: unknown) => ({ error })
            )

            await vi.advanceTimersByTimeAsync(750)
            expect(saveSubscription).toHaveBeenCalledOnce()

            await vi.advanceTimersByTimeAsync(250)
            expect(saveSubscription).toHaveBeenCalledTimes(2)

            await vi.advanceTimersByTimeAsync(1_250)
            expect(saveSubscription).toHaveBeenCalledTimes(2)

            await vi.advanceTimersByTimeAsync(250)
            await expect(settled).resolves.toEqual({ error: retryError })
          },
          2
        )
      } finally {
        randomSpy.mockRestore()
      }
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

      await withExpectedConsole("warn", "Failed to delete push subscription on server", () =>
        expect(mod.unsubscribePush()).resolves.toBe(false)
      )
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

    it("clears local state and returns false when registration cannot be resolved", async () => {
      mockSWContainer.getRegistration.mockResolvedValue(null)
      await expect(mod.unsubscribePush()).resolves.toBe(false)
    })

    it("preserves consent on request and handles endpoint-free subscriptions", async () => {
      mod.setPushConsent(true)
      localStorage.setItem("push:last_topics", JSON.stringify(["news"]))
      const subscription = { endpoint: "", unsubscribe: vi.fn().mockResolvedValue(true) }
      const registration = {
        pushManager: { getSubscription: vi.fn().mockResolvedValue(subscription) },
      }

      await expect(
        mod.unsubscribePush({ registration, preserveConsent: true, preserveTopics: true })
      ).resolves.toBe(true)

      expect(deleteSubscription).not.toHaveBeenCalled()
      expect(mod.hasPushConsent()).toBe(true)
      expect(mod.getPersistedTopics()).toEqual(["news"])
    })
  })

  describe("softSyncPushSubscription", () => {
    it("never sends another account's cached topics during an ownership transfer", async () => {
      const { useAuthStore } = await import("@/stores/useAuthStore")
      useAuthStore.setState({ user: { id: "owner-b" } as any, loading: false })
      vi.spyOn(storageMod.profileCacheStorage, "get").mockReturnValue({ data: { id: "owner-a" } })
      localStorage.setItem("push:last_owner", JSON.stringify("owner-a"))
      localStorage.setItem(
        "push:last_topics",
        JSON.stringify({ version: 2, shared: ["news"], perUser: { "owner-a": ["news"] } })
      )
      const mockSub = {
        endpoint: "https://push.example.com/old-owner",
        options: { applicationServerKey: mod.urlBase64ToUint8Array("a2V5").buffer },
        toJSON: () => ({ endpoint: "https://push.example.com/old-owner" }),
      }
      const mockReg = {
        pushManager: { getSubscription: vi.fn().mockResolvedValue(mockSub), subscribe: vi.fn() },
      }
      vi.stubGlobal("Notification", { permission: "granted" })

      await mod.softSyncPushSubscription({ registration: mockReg, vapidPublicKey: "a2V5" })

      expect(saveSubscription).toHaveBeenCalledWith(mockSub.toJSON(), undefined)
      expect(saveSubscription).not.toHaveBeenCalledWith(expect.anything(), [])
      expect(localStorage.getItem("push:last_owner")).toBe(JSON.stringify("owner-b"))
    })

    it("avoids duplicate syncs and calls ensurePushSubscription", async () => {
      const mockReg = {
        pushManager: {
          getSubscription: vi.fn().mockResolvedValue(null),
        },
      }
      mockSWContainer.getRegistration.mockResolvedValue(mockReg)
      vi.stubGlobal("Notification", { permission: "granted" })
      vi.mocked(getVapidPublicKey).mockResolvedValue(null as any)

      await withExpectedConsole("warn", /VAPID public key is not configured/, async () => {
        const p1 = mod.softSyncPushSubscription()
        const p2 = mod.softSyncPushSubscription()

        await p1
        await p2
      })

      expect(mockSWContainer.getRegistration).toHaveBeenCalledTimes(1)
    })
  })

  describe("isPushSupported", () => {
    it("returns status of browser push manager", () => {
      vi.stubGlobal("PushManager", {})
      expect(mod.isPushSupported()).toBe(true)
    })

    it.each([
      ["window", () => vi.stubGlobal("window", undefined)],
      ["service worker", () => vi.stubGlobal("navigator", {})],
      ["PushManager", () => vi.stubGlobal("window", {})],
      ["Notification", () => vi.stubGlobal("Notification", undefined)],
    ])("fails closed when %s is unavailable", (_name, removeCapability) => {
      removeCapability()
      expect(mod.isPushSupported()).toBe(false)
    })
  })

  describe("getExistingPushSubscription", () => {
    it("returns null if not supported", async () => {
      vi.stubGlobal("navigator", {})
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

    it("returns null when service worker registration cannot be resolved", async () => {
      mockSWContainer.getRegistration.mockResolvedValue(null)
      await expect(mod.getExistingPushSubscription()).resolves.toBeNull()
    })
  })

  describe("softSyncPushSubscription", () => {
    it("returns null when the sync task fails before subscription creation", async () => {
      vi.stubGlobal("Notification", { permission: "granted" })
      const mockReg = { pushManager: { getSubscription: vi.fn() } }

      await withExpectedConsole("error", "Failed to soft sync push subscription", () =>
        expect(
          mod.softSyncPushSubscription({ registration: mockReg, vapidPublicKey: "%" })
        ).resolves.toBeNull()
      )
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

      const result = await withExpectedConsole(
        "warn",
        "VAPID public key is not configured on the server",
        () => mod.ensurePushSubscription({ requestPermission: false })
      )

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

    it("does not mark an unconfirmed 409 Conflict as persisted", async () => {
      const { saveSubscription } = await import("@/api/notifications")

      const conflictError = { response: { status: 409 } }
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

      await withExpectedConsole("warn", "Subscription conflict (409)", () =>
        withExpectedConsole("error", "Failed to persist push subscription", () =>
          expect(
            mod.ensurePushSubscription({ requestPermission: false, topics: ["news"] })
          ).rejects.toBe(conflictError)
        )
      )
      expect(saveSubscription).toHaveBeenCalledOnce()
      expect(mod.hasPushConsent()).toBe(false)
      expect(localStorage.getItem("push:last_payload")).toBeNull()
    })

    it("rejects an Axios-marked 409 conflict without recording success", async () => {
      const conflictError = {
        isAxiosError: true,
        response: { status: 409 },
      }
      vi.mocked(saveSubscription).mockRejectedValue(conflictError)
      const mockSub = {
        endpoint: "https://push.example.com/axios-conflict",
        options: { applicationServerKey: mod.urlBase64ToUint8Array("YXhpb3g").buffer },
        toJSON: () => ({ endpoint: "https://push.example.com/axios-conflict" }),
      }
      const mockReg = {
        pushManager: {
          getSubscription: vi.fn().mockResolvedValue(null),
          subscribe: vi.fn().mockResolvedValue(mockSub),
        },
      }
      vi.stubGlobal("Notification", { permission: "granted" })

      await withExpectedConsole("warn", "Subscription conflict (409)", () =>
        withExpectedConsole("error", "Failed to persist push subscription", () =>
          expect(
            mod.ensurePushSubscription({
              registration: mockReg,
              vapidPublicKey: "YXhpb3g",
              requestPermission: false,
            })
          ).rejects.toBe(conflictError)
        )
      )
      expect(saveSubscription).toHaveBeenCalledOnce()
      expect(localStorage.getItem("push:last_payload")).toBeNull()
    })

    it("caches the requested topics when the server response omits them", async () => {
      vi.mocked(saveSubscription).mockResolvedValue({} as any)
      const mockSub = {
        endpoint: "https://push.example.com/null-response",
        options: { applicationServerKey: mod.urlBase64ToUint8Array("bnVsbA").buffer },
        toJSON: () => ({ endpoint: "https://push.example.com/null-response" }),
      }
      const mockReg = {
        pushManager: {
          getSubscription: vi.fn().mockResolvedValue(null),
          subscribe: vi.fn().mockResolvedValue(mockSub),
        },
      }
      vi.stubGlobal("Notification", { permission: "granted" })

      await expect(
        mod.ensurePushSubscription({
          registration: mockReg,
          vapidPublicKey: "bnVsbA",
          topics: ["topic"],
          requestPermission: false,
        })
      ).resolves.toBe(mockSub)
      expect(mod.getPersistedTopics({ userId: "owner-a" })).toEqual(["topic"])
    })
  })

  describe("Browser missing Push API → graceful null", () => {
    it("returns null from ensurePushSubscription when PushManager is absent", async () => {
      vi.stubGlobal("PushManager", undefined)

      const result = await withExpectedConsole(
        "warn",
        "Cannot ensure push subscription without service worker registration",
        () => mod.ensurePushSubscription()
      )
      expect(result).toBeNull()
    })

    it("returns null from ensurePushSubscription when navigator.serviceWorker absent", async () => {
      vi.stubGlobal("navigator", {})

      const result = await mod.ensurePushSubscription()
      expect(result).toBeNull()
    })

    it("returns null when evaluated without browser globals", async () => {
      vi.stubGlobal("window", undefined)
      vi.stubGlobal("navigator", undefined)
      vi.stubGlobal("Notification", undefined)

      await expect(mod.ensurePushSubscription()).resolves.toBeNull()
    })

    it("returns null from softSyncPushSubscription when PushManager is absent", async () => {
      vi.stubGlobal("navigator", {})

      const result = await mod.softSyncPushSubscription()
      expect(result).toBeNull()
    })

    it("fails closed without touching Notification when the Notification API is absent", async () => {
      vi.stubGlobal("Notification", undefined)

      await expect(mod.softSyncPushSubscription()).resolves.toBeNull()
      await expect(mod.recoverPushConsentFromBrowser()).resolves.toBe(false)
      expect(saveSubscription).not.toHaveBeenCalled()
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

  describe("non-Axios persistence status contracts", () => {
    it.each([
      { status: 409, label: "conflict" },
      { status: 429, label: "rate limit" },
    ])("handles a plain-object $label response without retrying", async ({ status }) => {
      vi.mocked(saveSubscription).mockRejectedValue({ response: { status } })
      const mockSub = {
        endpoint: `https://push.example.com/plain-${status}`,
        options: { applicationServerKey: mod.urlBase64ToUint8Array("cGxhaW4").buffer },
        toJSON: () => ({ endpoint: `https://push.example.com/plain-${status}` }),
      }
      const mockReg = {
        pushManager: {
          getSubscription: vi.fn().mockResolvedValue(null),
          subscribe: vi.fn().mockResolvedValue(mockSub),
        },
      }

      vi.stubGlobal("Notification", { permission: "granted" })

      const outcome = vi.fn()
      await withExpectedConsole(
        "warn",
        status === 409 ? "Subscription conflict (409)" : "Rate limited (429)",
        () =>
          withExpectedConsole("error", "Failed to persist push subscription", async () => {
            void mod
              .ensurePushSubscription({
                registration: mockReg,
                vapidPublicKey: "cGxhaW4",
                requestPermission: false,
              })
              .then(
                (value: unknown) => outcome({ value }),
                (error: unknown) => outcome({ error })
              )
            // Without advancing fake timers: a retry would still be sleeping.
            for (let index = 0; index < 50; index += 1) await Promise.resolve()
            expect(outcome).toHaveBeenCalledWith({ error: { response: { status } } })
          })
      )
      expect(saveSubscription).toHaveBeenCalledOnce()
      expect(localStorage.getItem("push:last_payload")).toBeNull()
    })
  })

  describe("identity-bound persistence (ADR-041)", () => {
    const KEY = "aWRlbnRpdHk"
    const ENDPOINT = "https://push.example.com/shared-device"
    const makeSub = (endpoint = ENDPOINT) => ({
      endpoint,
      options: { applicationServerKey: mod.urlBase64ToUint8Array(KEY).buffer },
      expirationTime: null,
      toJSON: () => ({ endpoint, keys: { p256dh: "p256dh-key", auth: "auth-key" } }),
    })
    const makeReg = (subscription: unknown = makeSub()) => ({
      pushManager: {
        getSubscription: vi.fn().mockResolvedValue(subscription),
        subscribe: vi.fn().mockResolvedValue(subscription),
      },
    })
    const ensure = (registration: unknown, options: Record<string, unknown> = {}) =>
      mod.ensurePushSubscription({
        registration,
        vapidPublicKey: KEY,
        requestPermission: false,
        ...options,
      })
    const setIdentity = (id: unknown, loading = false) =>
      authStore.setState({ user: id === null ? null : { id }, loading })
    const deferred = <T>() => {
      let resolve!: (value: T) => void
      let reject!: (reason: unknown) => void
      const promise = new Promise<T>((res, rej) => {
        resolve = res
        reject = rej
      })
      return { promise, resolve, reject }
    }
    const flushMicrotasks = async () => {
      for (let index = 0; index < 50; index += 1) await Promise.resolve()
    }
    const storedOwner = () => localStorage.getItem("push:last_owner")

    beforeEach(() => {
      vi.stubGlobal("Notification", { permission: "granted" })
    })

    describe("fail-closed identity", () => {
      it("does not persist during cold boot even when a cached profile names an owner", async () => {
        setIdentity(null, true)
        vi.spyOn(storageMod.profileCacheStorage, "get").mockReturnValue({
          data: { id: "owner-a" },
        })
        const registration = makeReg()

        await expect(ensure(registration)).resolves.toBeNull()

        expect(registration.pushManager.getSubscription).not.toHaveBeenCalled()
        expect(saveSubscription).not.toHaveBeenCalled()
        expect(storedOwner()).toBeNull()
      })

      it("does not persist while a real user is still loading", async () => {
        setIdentity("owner-a", true)
        const registration = makeReg()

        await expect(ensure(registration)).resolves.toBeNull()
        await expect(
          mod.softSyncPushSubscription({ registration, vapidPublicKey: KEY })
        ).resolves.toBeNull()

        expect(saveSubscription).not.toHaveBeenCalled()
      })

      it.each(["ssr-stub", "-1", "lhci-mock-user"])(
        "does not persist for the settled %s placeholder identity",
        async (placeholder) => {
          setIdentity(placeholder)
          const registration = makeReg()

          await expect(ensure(registration)).resolves.toBeNull()
          await expect(
            mod.softSyncPushSubscription({ registration, vapidPublicKey: KEY })
          ).resolves.toBeNull()

          expect(registration.pushManager.getSubscription).not.toHaveBeenCalled()
          expect(saveSubscription).not.toHaveBeenCalled()
        }
      )
    })

    describe("ownership transfer", () => {
      it("rebinds an A-owned endpoint to B without ever sending topics implicitly", async () => {
        const subscription = makeSub()
        const registration = makeReg(subscription)
        setIdentity("owner-a")
        await ensure(registration, { topics: ["news"] })
        expect(mod.getPersistedTopics({ userId: "owner-a" })).toEqual(["news"])

        setIdentity("owner-b")
        await expect(
          mod.softSyncPushSubscription({ registration, vapidPublicKey: KEY })
        ).resolves.toBe(subscription)

        expect(saveSubscription).toHaveBeenCalledTimes(2)
        expect(saveSubscription).toHaveBeenLastCalledWith(subscription.toJSON(), undefined)
        expect(storedOwner()).toBe(JSON.stringify("owner-b"))
        expect(mod.getPersistedTopics({ userId: "owner-b" })).toBeUndefined()
      })

      it("skips the POST only when both the payload and the owner are unchanged", async () => {
        const first = makeSub()
        const registration = makeReg(first)
        setIdentity("owner-a")

        await ensure(registration)
        await ensure(registration)
        expect(saveSubscription).toHaveBeenCalledOnce()

        localStorage.removeItem("push:last_owner")
        await ensure(registration)
        expect(saveSubscription).toHaveBeenCalledTimes(2)

        const rotated = makeSub("https://push.example.com/rotated-endpoint")
        registration.pushManager.getSubscription.mockResolvedValue(rotated)
        await ensure(registration)
        expect(saveSubscription).toHaveBeenCalledTimes(3)
        expect(saveSubscription).toHaveBeenLastCalledWith(rotated.toJSON(), undefined)

        localStorage.removeItem("push:last_payload")
        await ensure(registration)
        expect(saveSubscription).toHaveBeenCalledTimes(4)

        await ensure(registration, { topics: [] })
        expect(saveSubscription).toHaveBeenCalledTimes(5)
        expect(saveSubscription).toHaveBeenLastCalledWith(rotated.toJSON(), [])
      })

      it("aborts without caching anything when the identity changes during the server write", async () => {
        const registration = makeReg()
        setIdentity("owner-a")
        vi.mocked(saveSubscription).mockImplementation(async () => {
          setIdentity("owner-b")
          return { topics: ["news"] } as any
        })

        await withExpectedConsole("error", "Failed to persist push subscription", () =>
          expect(ensure(registration, { topics: ["news"] })).rejects.toMatchObject({
            name: "PushIdentityUnconfirmedError",
          })
        )

        expect(saveSubscription).toHaveBeenCalledOnce()
        expect(storedOwner()).toBeNull()
        expect(localStorage.getItem("push:last_payload")).toBeNull()
        expect(localStorage.getItem("push:last_topics")).toBeNull()
        expect(mod.hasPushConsent()).toBe(false)
      })

      it("aborts when auth starts reloading during the server write", async () => {
        const registration = makeReg()
        setIdentity("owner-a")
        vi.mocked(saveSubscription).mockImplementation(async () => {
          setIdentity("owner-a", true)
          return {} as any
        })

        await withExpectedConsole("error", "Failed to persist push subscription", () =>
          expect(ensure(registration)).rejects.toMatchObject({
            name: "PushIdentityUnconfirmedError",
            message: "Push identity is not confirmed for this account",
          })
        )
        expect(storedOwner()).toBeNull()
      })

      it("does not retry for a different account after the back-off delay", async () => {
        const registration = makeReg()
        setIdentity("owner-a")
        vi.mocked(saveSubscription).mockRejectedValueOnce(new Error("temporary outage"))

        await withExpectedConsole("error", "Failed to persist push subscription", async () => {
          const pending = ensure(registration)
          const assertion = expect(pending).rejects.toMatchObject({
            name: "PushIdentityUnconfirmedError",
          })
          await vi.waitFor(() => expect(saveSubscription).toHaveBeenCalledOnce())
          setIdentity("owner-b")
          await vi.runAllTimersAsync()
          await assertion
        })
        expect(saveSubscription).toHaveBeenCalledOnce()
        expect(storedOwner()).toBeNull()
      })
    })

    describe("serialized sync queue", () => {
      it("lets B wait for A's in-flight sync and then send its own POST", async () => {
        const subscription = makeSub()
        const registration = makeReg(subscription)
        const firstWrite = deferred<unknown>()
        vi.mocked(saveSubscription).mockImplementationOnce(() => firstWrite.promise as any)
        setIdentity("owner-a")

        await withExpectedConsole("error", "Failed to persist push subscription", async () => {
          const first = ensure(registration)
          const firstOutcome = expect(first).rejects.toMatchObject({
            name: "PushIdentityUnconfirmedError",
          })
          await vi.waitFor(() => expect(saveSubscription).toHaveBeenCalledOnce())

          setIdentity("owner-b")
          const second = ensure(registration)
          await flushMicrotasks()
          expect(saveSubscription).toHaveBeenCalledOnce()
          expect(registration.pushManager.getSubscription).toHaveBeenCalledOnce()

          firstWrite.resolve({})
          await firstOutcome
          await expect(second).resolves.toBe(subscription)
        })

        expect(saveSubscription).toHaveBeenCalledTimes(2)
        expect(saveSubscription).toHaveBeenLastCalledWith(subscription.toJSON(), undefined)
        expect(storedOwner()).toBe(JSON.stringify("owner-b"))
      })

      it("does not merge an explicit topic update into an in-flight implicit sync", async () => {
        const subscription = makeSub()
        const registration = makeReg(subscription)
        const firstWrite = deferred<unknown>()
        vi.mocked(saveSubscription).mockImplementationOnce(() => firstWrite.promise as any)
        setIdentity("owner-a")

        const implicit = ensure(registration)
        await vi.waitFor(() => expect(saveSubscription).toHaveBeenCalledOnce())
        const explicit = ensure(registration, { topics: ["news"] })
        await flushMicrotasks()
        expect(saveSubscription).toHaveBeenCalledOnce()

        firstWrite.resolve({})
        await expect(implicit).resolves.toBe(subscription)
        await expect(explicit).resolves.toBe(subscription)

        expect(vi.mocked(saveSubscription).mock.calls).toEqual([
          [subscription.toJSON(), undefined],
          [subscription.toJSON(), ["news"]],
        ])
      })

      it("does not let an implicit sync join an in-flight explicit update", async () => {
        const subscription = makeSub()
        const registration = makeReg(subscription)
        const firstWrite = deferred<unknown>()
        vi.mocked(saveSubscription).mockImplementationOnce(() => firstWrite.promise as any)
        setIdentity("owner-a")

        const explicit = ensure(registration, { topics: ["news"] })
        await vi.waitFor(() => expect(saveSubscription).toHaveBeenCalledOnce())
        const implicit = ensure(registration)
        await flushMicrotasks()
        expect(registration.pushManager.getSubscription).toHaveBeenCalledOnce()

        firstWrite.resolve({ topics: ["news"] })
        await expect(explicit).resolves.toBe(subscription)
        await expect(implicit).resolves.toBe(subscription)

        // The implicit run re-read browser state after the explicit update and
        // found nothing new to persist.
        expect(registration.pushManager.getSubscription).toHaveBeenCalledTimes(2)
        expect(saveSubscription).toHaveBeenCalledOnce()
      })

      it("joins the newest queued implicit sync instead of starting a parallel one", async () => {
        const subscription = makeSub()
        const registration = makeReg(subscription)
        const explicitWrite = deferred<unknown>()
        const queuedLookup = deferred<unknown>()
        vi.mocked(saveSubscription).mockImplementationOnce(() => explicitWrite.promise as any)
        registration.pushManager.getSubscription
          .mockResolvedValueOnce(subscription)
          .mockImplementationOnce(() => queuedLookup.promise)
        setIdentity("owner-a")

        const explicit = ensure(registration, { topics: ["news"] })
        await vi.waitFor(() => expect(saveSubscription).toHaveBeenCalledOnce())
        const queued = ensure(registration)
        explicitWrite.resolve({})
        await expect(explicit).resolves.toBe(subscription)
        await vi.waitFor(() =>
          expect(registration.pushManager.getSubscription).toHaveBeenCalledTimes(2)
        )

        const joined = ensure(registration)
        await flushMicrotasks()
        expect(registration.pushManager.getSubscription).toHaveBeenCalledTimes(2)

        queuedLookup.resolve(subscription)
        await expect(queued).resolves.toBe(subscription)
        await expect(joined).resolves.toBe(subscription)
        expect(saveSubscription).toHaveBeenCalledOnce()
      })

      it("caches topics only from explicit updates, using the server response", async () => {
        const registration = makeReg()
        setIdentity("owner-a")
        vi.mocked(saveSubscription).mockResolvedValueOnce({ topics: ["events"] } as any)

        await ensure(registration)
        expect(localStorage.getItem("push:last_topics")).toBeNull()

        vi.mocked(saveSubscription).mockResolvedValueOnce({ topics: ["news", "system"] } as any)
        await ensure(registration, { topics: ["news"] })
        expect(mod.getPersistedTopics({ userId: "owner-a" })).toEqual(["news", "system"])
      })

      it("passes explicit soft-sync topics through unchanged", async () => {
        const subscription = makeSub()
        setIdentity("owner-a")

        await mod.softSyncPushSubscription({
          registration: makeReg(subscription),
          vapidPublicKey: KEY,
          topics: ["news"],
        })

        expect(saveSubscription).toHaveBeenCalledWith(subscription.toJSON(), ["news"])
      })
    })

    describe("syncPushForConfirmedIdentity", () => {
      const installBrowserSubscription = (subscription: unknown = makeSub()) => {
        const registration = makeReg(subscription)
        mockSWContainer.getRegistration.mockResolvedValue(registration)
        vi.stubEnv("VITE_VAPID_PUBLIC_KEY", KEY)
        return registration
      }
      const markOwner = (owner: string) =>
        localStorage.setItem("push:last_owner", JSON.stringify(owner))

      it("waits for a confirmed identity before touching the browser or the server", async () => {
        const subscription = makeSub()
        installBrowserSubscription(subscription)
        mod.setPushConsent(true)
        markOwner("owner-a")
        setIdentity(null, true)

        const pending = mod.syncPushForConfirmedIdentity()
        await flushMicrotasks()
        expect(mockSWContainer.getRegistration).not.toHaveBeenCalled()

        setIdentity("owner-a")

        await expect(pending).resolves.toBe(subscription)
        expect(saveSubscription).toHaveBeenCalledOnce()
        expect(saveSubscription).toHaveBeenCalledWith(subscription.toJSON(), undefined)
      })

      it("does nothing when auth settles signed out", async () => {
        installBrowserSubscription()
        mod.setPushConsent(true)
        setIdentity(null, true)

        const pending = mod.syncPushForConfirmedIdentity()
        setIdentity(null)

        await expect(pending).resolves.toBeNull()
        expect(mockSWContainer.getRegistration).not.toHaveBeenCalled()
        expect(saveSubscription).not.toHaveBeenCalled()
      })

      it("does nothing when a different account than expected is confirmed", async () => {
        installBrowserSubscription()
        mod.setPushConsent(true)
        setIdentity("owner-a")

        await expect(
          mod.syncPushForConfirmedIdentity({ expectedUserId: "owner-b" })
        ).resolves.toBeNull()
        expect(saveSubscription).not.toHaveBeenCalled()
      })

      it("syncs once the expected account is confirmed", async () => {
        const subscription = makeSub()
        installBrowserSubscription(subscription)
        mod.setPushConsent(true)
        markOwner("owner-b")
        setIdentity("owner-b")

        await expect(mod.syncPushForConfirmedIdentity({ expectedUserId: "owner-b" })).resolves.toBe(
          subscription
        )
        expect(storedOwner()).toBe(JSON.stringify("owner-b"))
      })

      it("gives up when the identity is not confirmed before the timeout", async () => {
        installBrowserSubscription()
        mod.setPushConsent(true)
        setIdentity(null, true)
        const settled = vi.fn()

        void mod.syncPushForConfirmedIdentity({ timeoutMs: 50 }).then(settled)
        await vi.advanceTimersByTimeAsync(49)
        expect(settled).not.toHaveBeenCalled()
        await vi.advanceTimersByTimeAsync(1)

        expect(settled).toHaveBeenCalledWith(null)
        expect(saveSubscription).not.toHaveBeenCalled()
      })

      it("recovers lost consent with a single implicit POST", async () => {
        const subscription = makeSub()
        installBrowserSubscription(subscription)
        markOwner("owner-a")
        setIdentity("owner-a")

        await expect(mod.syncPushForConfirmedIdentity()).resolves.toBe(subscription)

        expect(mod.hasPushConsent()).toBe(true)
        expect(saveSubscription).toHaveBeenCalledOnce()
        expect(saveSubscription).toHaveBeenCalledWith(subscription.toJSON(), undefined)
      })

      it("does not subscribe when there is neither consent nor a browser subscription", async () => {
        const registration = installBrowserSubscription(null)
        markOwner("owner-a")
        setIdentity("owner-a")

        await expect(mod.syncPushForConfirmedIdentity()).resolves.toBeNull()

        expect(registration.pushManager.subscribe).not.toHaveBeenCalled()
        expect(saveSubscription).not.toHaveBeenCalled()
        expect(mod.hasPushConsent()).toBe(false)
      })

      it("does not subscribe when browser permission is not granted", async () => {
        installBrowserSubscription()
        mod.setPushConsent(true)
        markOwner("owner-a")
        setIdentity("owner-a")
        vi.stubGlobal("Notification", { permission: "default" })

        await expect(mod.syncPushForConfirmedIdentity()).resolves.toBeNull()
        expect(saveSubscription).not.toHaveBeenCalled()
      })

      it("does nothing when push is unsupported", async () => {
        mod.setPushConsent(true)
        markOwner("owner-a")
        setIdentity("owner-a")
        vi.stubGlobal("navigator", {})

        await expect(mod.syncPushForConfirmedIdentity()).resolves.toBeNull()
        expect(saveSubscription).not.toHaveBeenCalled()
      })

      it("syncs through a supplied registration", async () => {
        const subscription = makeSub()
        const registration = makeReg(subscription)
        mockSWContainer.getRegistration.mockResolvedValue(null)
        vi.stubEnv("VITE_VAPID_PUBLIC_KEY", KEY)
        mod.setPushConsent(true)
        markOwner("owner-a")
        setIdentity("owner-a")

        await expect(mod.syncPushForConfirmedIdentity({ registration })).resolves.toBe(subscription)
        expect(mockSWContainer.getRegistration).not.toHaveBeenCalled()
      })

      it("resolves null when the consented sync fails", async () => {
        installBrowserSubscription()
        mod.setPushConsent(true)
        markOwner("owner-a")
        setIdentity("owner-a")
        vi.mocked(saveSubscription).mockRejectedValue({ response: { status: 429 } })

        await withExpectedConsole("warn", "Rate limited (429)", () =>
          withExpectedConsole("error", "Failed to persist push subscription", () =>
            withExpectedConsole("error", "Failed to soft sync push subscription", () =>
              expect(mod.syncPushForConfirmedIdentity()).resolves.toBeNull()
            )
          )
        )
      })
    })

    describe("syncPushForConfirmedIdentity account boundary", () => {
      it("never hands another account's browser consent or endpoint to a new login", async () => {
        mockSWContainer.getRegistration.mockResolvedValue(makeReg(makeSub()))
        vi.stubEnv("VITE_VAPID_PUBLIC_KEY", KEY)
        mod.setPushConsent(true)
        localStorage.setItem("push:last_owner", JSON.stringify("owner-a"))
        setIdentity("owner-b")

        await expect(mod.syncPushForConfirmedIdentity()).resolves.toBeNull()

        expect(saveSubscription).not.toHaveBeenCalled()
        expect(mockSWContainer.getRegistration).not.toHaveBeenCalled()
        expect(storedOwner()).toBe(JSON.stringify("owner-a"))
      })

      it("does not recover consent for an account that never enabled push here", async () => {
        mockSWContainer.getRegistration.mockResolvedValue(makeReg(makeSub()))
        vi.stubEnv("VITE_VAPID_PUBLIC_KEY", KEY)
        setIdentity("owner-a")

        await expect(mod.syncPushForConfirmedIdentity()).resolves.toBeNull()

        expect(saveSubscription).not.toHaveBeenCalled()
        expect(mod.hasPushConsent()).toBe(false)
      })

      it("lets the same account resume push after logging out and back in", async () => {
        const subscription = makeSub()
        const registration = makeReg(subscription)
        mockSWContainer.getRegistration.mockResolvedValue(registration)
        vi.stubEnv("VITE_VAPID_PUBLIC_KEY", KEY)
        setIdentity("owner-a")
        await ensure(registration)
        await mod.releasePushServerBinding()
        mod.setPushConsent(false)

        await expect(mod.syncPushForConfirmedIdentity()).resolves.toBe(subscription)

        expect(saveSubscription).toHaveBeenCalledTimes(2)
        expect(mod.hasPushConsent()).toBe(true)
      })
    })

    describe("getOwnedPushSubscription", () => {
      it("returns the browser subscription to the account that enabled it", async () => {
        const subscription = makeSub()
        const registration = makeReg(subscription)
        localStorage.setItem("push:last_owner", JSON.stringify("owner-a"))

        await expect(mod.getOwnedPushSubscription("owner-a", registration)).resolves.toBe(
          subscription
        )
      })

      it.each([
        ["another account", "owner-b"],
        ["no confirmed account", null],
      ])("hides the browser subscription from %s", async (_label, userId) => {
        const registration = makeReg(makeSub())
        localStorage.setItem("push:last_owner", JSON.stringify("owner-a"))

        await expect(mod.getOwnedPushSubscription(userId, registration)).resolves.toBeNull()
        expect(registration.pushManager.getSubscription).not.toHaveBeenCalled()
      })
    })

    it("does not expose a browser subscription before any account is confirmed", async () => {
      const registration = makeReg(makeSub())

      await expect(mod.getOwnedPushSubscription(null, registration)).resolves.toBeNull()
      expect(registration.pushManager.getSubscription).not.toHaveBeenCalled()
    })

    describe("releasePushServerBinding", () => {
      it("unbinds the endpoint on the server but keeps the browser subscription", async () => {
        const subscription = { ...makeSub(), unsubscribe: vi.fn() }
        const registration = makeReg(subscription)
        mockSWContainer.getRegistration.mockResolvedValue(registration)
        localStorage.setItem("push:last_owner", JSON.stringify("owner-a"))
        localStorage.setItem("push:last_payload", JSON.stringify(subscription.toJSON()))
        mod.setPersistedTopics(["news"], { userId: "owner-a" })
        mod.setPushConsent(true)

        await mod.releasePushServerBinding()

        expect(deleteSubscription).toHaveBeenCalledWith(ENDPOINT)
        expect(subscription.unsubscribe).not.toHaveBeenCalled()
        expect(storedOwner()).toBe(JSON.stringify("owner-a"))
        expect(localStorage.getItem("push:last_payload")).toBeNull()
        expect(mod.getPersistedTopics({ userId: "owner-a" })).toEqual(["news"])
        expect(mod.hasPushConsent()).toBe(true)
        expect(vi.getTimerCount()).toBe(0)
      })

      it("forces the next login to re-persist the same endpoint", async () => {
        const subscription = makeSub()
        const registration = makeReg(subscription)
        mockSWContainer.getRegistration.mockResolvedValue(registration)
        setIdentity("owner-a")
        await ensure(registration)

        await mod.releasePushServerBinding()
        await ensure(registration)

        expect(saveSubscription).toHaveBeenCalledTimes(2)
      })

      it("forgets the persisted payload even without a browser subscription", async () => {
        localStorage.setItem("push:last_payload", JSON.stringify({ endpoint: ENDPOINT }))
        mockSWContainer.getRegistration.mockResolvedValue(makeReg(null))

        await mod.releasePushServerBinding()

        expect(deleteSubscription).not.toHaveBeenCalled()
        expect(localStorage.getItem("push:last_payload")).toBeNull()
      })

      it("tolerates a missing service-worker registration", async () => {
        mockSWContainer.getRegistration.mockResolvedValue(undefined)

        await mod.releasePushServerBinding()

        expect(deleteSubscription).not.toHaveBeenCalled()
      })

      it("does not query browser push state when push is unsupported", async () => {
        localStorage.setItem("push:last_payload", JSON.stringify({ endpoint: ENDPOINT }))
        vi.stubGlobal("navigator", {})

        await mod.releasePushServerBinding()

        expect(mockSWContainer.getRegistration).not.toHaveBeenCalled()
        expect(localStorage.getItem("push:last_payload")).toBeNull()
      })

      it("logs and swallows a failed unbind", async () => {
        mockSWContainer.getRegistration.mockResolvedValue(makeReg())
        const failure = new Error("unbind failed")
        vi.mocked(deleteSubscription).mockRejectedValue(failure)

        await withExpectedConsole("warn", "Failed to release push subscription binding", () =>
          expect(mod.releasePushServerBinding()).resolves.toBeUndefined()
        )
      })

      it("stops waiting for a hung unbind after the logout guard", async () => {
        mockSWContainer.getRegistration.mockResolvedValue(makeReg())
        vi.mocked(deleteSubscription).mockReturnValue(new Promise<void>(() => {}))
        const settled = vi.fn()

        void mod.releasePushServerBinding().then(settled)
        await vi.advanceTimersByTimeAsync(2_999)
        expect(settled).not.toHaveBeenCalled()
        await vi.advanceTimersByTimeAsync(1)

        expect(settled).toHaveBeenCalledOnce()
      })
    })
  })
})
