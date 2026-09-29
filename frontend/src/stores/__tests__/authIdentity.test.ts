import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import {
  ENCRYPTED_CACHE_PLACEHOLDER_USER_ID,
  LHCI_USER_ID_PREFIX,
  SSR_STUB_USER_ID,
  getConfirmedUserId,
  waitForConfirmedUserId,
} from "../authIdentity"
import { useAuthStore } from "../useAuthStore"
import type { UserState } from "@/types/Auth"

const asUser = (id: unknown) => ({ id }) as unknown as UserState

const setAuth = (user: UserState, loading: boolean) => {
  useAuthStore.setState({ user, loading })
}

describe("authIdentity", () => {
  beforeEach(() => {
    setAuth(null, true)
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.restoreAllMocks()
    setAuth(null, true)
  })

  describe("placeholder constants", () => {
    it("names every synthetic identity the auth bootstrap can publish", () => {
      expect(SSR_STUB_USER_ID).toBe("ssr-stub")
      expect(ENCRYPTED_CACHE_PLACEHOLDER_USER_ID).toBe("-1")
      expect(LHCI_USER_ID_PREFIX).toBe("lhci-")
    })
  })

  describe("getConfirmedUserId", () => {
    it("is null while auth is still loading, even with a real id", () => {
      expect(getConfirmedUserId({ user: asUser("user-a"), loading: true })).toBeNull()
    })

    it("is null for a settled signed-out state", () => {
      expect(getConfirmedUserId({ user: null, loading: false })).toBeNull()
    })

    it.each([
      ["SSR stub", "ssr-stub"],
      ["encrypted-cache placeholder", "-1"],
      ["LHCI synthetic user", "lhci-mock-user"],
      ["another LHCI synthetic user", "lhci-"],
    ])("rejects the %s placeholder once loading has settled", (_label, id) => {
      expect(getConfirmedUserId({ user: asUser(id), loading: false })).toBeNull()
    })

    it("rejects a numeric encrypted-cache placeholder", () => {
      expect(getConfirmedUserId({ user: asUser(-1), loading: false })).toBeNull()
    })

    it("returns the trimmed id of a real user", () => {
      expect(getConfirmedUserId({ user: asUser("  user-a  "), loading: false })).toBe("user-a")
    })

    it("accepts numeric ids and ids that merely contain a placeholder prefix", () => {
      expect(getConfirmedUserId({ user: asUser(42), loading: false })).toBe("42")
      expect(getConfirmedUserId({ user: asUser("user-lhci-1"), loading: false })).toBe(
        "user-lhci-1"
      )
    })

    it.each([
      ["blank", "   "],
      ["empty", ""],
      ["object", { id: "user-a" }],
      ["missing", undefined],
      ["null", null],
    ])("rejects a %s id", (_label, id) => {
      expect(getConfirmedUserId({ user: asUser(id), loading: false })).toBeNull()
    })
  })

  // A mutant that never settles must fail fast instead of hanging the run.
  describe("waitForConfirmedUserId", { timeout: 2_000 }, () => {
    let active = 0
    const listenerCount = () => active

    beforeEach(() => {
      active = 0
      const original = useAuthStore.subscribe
      vi.spyOn(useAuthStore, "subscribe").mockImplementation((listener) => {
        active += 1
        const unsubscribe = original(listener)
        let released = false
        return () => {
          if (!released) {
            released = true
            active -= 1
          }
          unsubscribe()
        }
      })
    })

    it("resolves immediately when the identity is already confirmed", async () => {
      setAuth(asUser("user-a"), false)

      await expect(waitForConfirmedUserId()).resolves.toBe("user-a")
      expect(listenerCount()).toBe(0)
    })

    it("resolves immediately with the expected confirmed identity", async () => {
      setAuth(asUser("user-a"), false)

      await expect(waitForConfirmedUserId({ expectedUserId: "user-a" })).resolves.toBe("user-a")
    })

    it("resolves null immediately for a settled signed-out state", async () => {
      setAuth(null, false)

      await expect(waitForConfirmedUserId()).resolves.toBeNull()
      expect(listenerCount()).toBe(0)
    })

    it("resolves null immediately when a different identity is already confirmed", async () => {
      setAuth(asUser("user-a"), false)

      await expect(waitForConfirmedUserId({ expectedUserId: "user-b" })).resolves.toBeNull()
    })

    it("waits through loading and placeholder identities until the real user settles", async () => {
      const waiting = waitForConfirmedUserId()
      const settled = vi.fn()
      void waiting.then(settled)

      setAuth(asUser("ssr-stub"), false)
      await Promise.resolve()
      setAuth(asUser("-1"), false)
      await Promise.resolve()
      setAuth(asUser("user-a"), true)
      await Promise.resolve()
      expect(settled).not.toHaveBeenCalled()
      expect(listenerCount()).toBe(1)

      setAuth(asUser("user-a"), false)

      await expect(waiting).resolves.toBe("user-a")
      expect(listenerCount()).toBe(0)
    })

    it("resolves null once loading settles as signed out", async () => {
      const waiting = waitForConfirmedUserId()

      setAuth(null, false)

      await expect(waiting).resolves.toBeNull()
      expect(listenerCount()).toBe(0)
    })

    it("resolves null when a different user is confirmed than expected", async () => {
      const waiting = waitForConfirmedUserId({ expectedUserId: "user-b" })

      setAuth(asUser("user-a"), false)

      await expect(waiting).resolves.toBeNull()
      expect(listenerCount()).toBe(0)
    })

    it("resolves the expected user when it settles after loading", async () => {
      const waiting = waitForConfirmedUserId({ expectedUserId: "user-b" })

      setAuth(asUser("user-b"), false)

      await expect(waiting).resolves.toBe("user-b")
    })

    it("resolves null exactly at the default timeout", async () => {
      vi.useFakeTimers()
      const settled = vi.fn()
      void waitForConfirmedUserId().then(settled)

      await vi.advanceTimersByTimeAsync(14_999)
      expect(settled).not.toHaveBeenCalled()

      await vi.advanceTimersByTimeAsync(1)
      expect(settled).toHaveBeenCalledWith(null)
      expect(listenerCount()).toBe(0)
      expect(vi.getTimerCount()).toBe(0)
    })

    it("honours a custom timeout", async () => {
      vi.useFakeTimers()
      const settled = vi.fn()
      void waitForConfirmedUserId({ timeoutMs: 250 }).then(settled)

      await vi.advanceTimersByTimeAsync(249)
      expect(settled).not.toHaveBeenCalled()

      await vi.advanceTimersByTimeAsync(1)
      expect(settled).toHaveBeenCalledWith(null)
      expect(listenerCount()).toBe(0)
    })

    it("clears the timer and ignores later store updates after settling", async () => {
      vi.useFakeTimers()
      const waiting = waitForConfirmedUserId({ timeoutMs: 250 })

      setAuth(asUser("user-a"), false)
      await expect(waiting).resolves.toBe("user-a")
      expect(vi.getTimerCount()).toBe(0)
      expect(listenerCount()).toBe(0)

      setAuth(asUser("user-b"), false)
      await vi.advanceTimersByTimeAsync(1_000)
      await expect(waiting).resolves.toBe("user-a")
    })
  })
})
