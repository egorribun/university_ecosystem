import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import {
  acceptBrowserSessionGeneration,
  captureSessionEpoch,
  establishBrowserSession,
  getBrowserSessionGeneration,
  getSessionEpoch,
  invalidateSessionEpoch,
  isCurrentBrowserSession,
  matchesBrowserSession,
  rotateBrowserSession,
} from "../sessionEpoch"

const KEY = "ecosystem.session.generation.v1"
beforeEach(() => {
  localStorage.clear()
  acceptBrowserSessionGeneration()
})
afterEach(() => {
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
  localStorage.clear()
  acceptBrowserSessionGeneration()
})

describe("account lifetime epochs", () => {
  it("invalidates already-started work without changing its browser generation", () => {
    const before = getSessionEpoch()
    const owns = captureSessionEpoch()
    expect(owns()).toBe(true)
    invalidateSessionEpoch()
    expect(getSessionEpoch()).toBe(before + 1)
    expect(owns()).toBe(false)
    expect(getBrowserSessionGeneration()).toBeNull()
  })

  it("captures an explicit render epoch and keeps no-argument captures current", () => {
    invalidateSessionEpoch()
    const observedEpoch = getSessionEpoch()
    expect(observedEpoch).toBeGreaterThan(0)

    const existingWork = captureSessionEpoch(observedEpoch)
    expect(existingWork()).toBe(true)
    const futureExpected = captureSessionEpoch(observedEpoch + 1)
    expect(futureExpected()).toBe(false)

    invalidateSessionEpoch()
    expect(existingWork()).toBe(false)
    expect(captureSessionEpoch(observedEpoch)()).toBe(false)
    expect(futureExpected()).toBe(false)

    const currentEpoch = getSessionEpoch()
    expect(captureSessionEpoch()()).toBe(true)
    expect(captureSessionEpoch(currentEpoch)()).toBe(true)
  })

  it("shares a confirmed generation across matching keys and rotates for a new session", () => {
    const nonce = establishBrowserSession("key-A-hash", null)!
    expect(matchesBrowserSession("key-A-hash", nonce)).toBe(true)
    expect(establishBrowserSession("key-A-hash", nonce)).toBe(nonce)
    const old = captureSessionEpoch()
    const next = establishBrowserSession("key-B-hash", nonce)
    expect(next).not.toBe(nonce)
    expect(old()).toBe(false)
    expect(matchesBrowserSession("key-A-hash", nonce)).toBe(false)
    expect(isCurrentBrowserSession()).toBe(true)
  })

  it("cannot overwrite a generation created while an old request was awaiting", () => {
    rotateBrowserSession()
    const nonce = getBrowserSessionGeneration()
    expect(establishBrowserSession("stale-key", null)).toBeNull()
    expect(getBrowserSessionGeneration()).toBe(nonce)
    expect(establishBrowserSession("verified-key", nonce)).toBe(nonce)
  })

  it("rejects old tabs and their newly-started work before any cross-tab event arrives", () => {
    const nonce = establishBrowserSession("key-A", null)!
    const old = captureSessionEpoch()
    localStorage.setItem(KEY, JSON.stringify({ nonce: "other-tab-generation", hash: "key-B" }))
    expect(old()).toBe(false)
    expect(captureSessionEpoch()()).toBe(false)
    expect(isCurrentBrowserSession()).toBe(false)
    expect(matchesBrowserSession("key-A", nonce)).toBe(false)
    // Only a verified profile/key publication may bind the new generation.
    acceptBrowserSessionGeneration()
    expect(captureSessionEpoch()()).toBe(true)
  })

  it.each(["not-json", "{}", '{"nonce":"","hash":null}', '{"nonce":"valid","hash":42}'])(
    "ignores malformed generation metadata %s",
    (value) => {
      localStorage.setItem(KEY, value)
      expect(getBrowserSessionGeneration()).toBeNull()
      expect(matchesBrowserSession("key", "nonce")).toBe(false)
    }
  )

  it("keeps live network authentication available when storage is blocked, without an offline identity", () => {
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new DOMException("blocked", "SecurityError")
    })
    rotateBrowserSession()
    expect(captureSessionEpoch()()).toBe(true)
    expect(establishBrowserSession("key", null)).toBeNull()
    expect(getBrowserSessionGeneration()).toBeNull()
  })

  it("fails closed on unreadable storage", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new DOMException("blocked", "SecurityError")
    })
    expect(getBrowserSessionGeneration()).toBeNull()
  })

  it("handles runtimes without browser storage", () => {
    vi.stubGlobal("localStorage", undefined)
    rotateBrowserSession()
    expect(getBrowserSessionGeneration()).toBeNull()
    expect(establishBrowserSession("key", null)).toBeNull()
  })
})
