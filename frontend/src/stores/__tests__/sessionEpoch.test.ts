import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import {
  acceptBrowserSessionGeneration,
  beginBrowserSessionTransition,
  captureSessionEpoch,
  establishBrowserSession,
  getBrowserSessionGeneration,
  getSessionEpoch,
  hasFailedBrowserSessionRotation,
  hasStaleBrowserSessionBinding,
  invalidateSessionEpoch,
  isCurrentBrowserSession,
  matchesBrowserSession,
  rotateBrowserSession,
} from "../sessionEpoch"

const KEY = "ecosystem.session.generation.v1"
const resetBrowserSessionState = () => {
  localStorage.clear()
  rotateBrowserSession()
  localStorage.clear()
  acceptBrowserSessionGeneration()
}
beforeEach(resetBrowserSessionState)
afterEach(() => {
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
  resetBrowserSessionState()
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

  it("distinguishes failed rotation from a later remote generation", () => {
    localStorage.setItem(KEY, JSON.stringify({ nonce: "prior-generation", hash: "prior-profile" }))
    acceptBrowserSessionGeneration()
    const storageWrite = vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new DOMException("blocked", "SecurityError")
    })

    try {
      rotateBrowserSession()
      expect(getBrowserSessionGeneration()).toBe("prior-generation")
      expect(isCurrentBrowserSession()).toBe(false)
      expect(hasStaleBrowserSessionBinding()).toBe(false)

      storageWrite.mockRestore()
      localStorage.setItem(
        KEY,
        JSON.stringify({ nonce: "remote-generation", hash: "remote-profile" })
      )
      expect(hasStaleBrowserSessionBinding()).toBe(true)
    } finally {
      storageWrite.mockRestore()
    }
  })

  it("clears failed-rotation state after a successful retry", () => {
    localStorage.setItem(KEY, JSON.stringify({ nonce: "prior-generation", hash: "prior-profile" }))
    acceptBrowserSessionGeneration()
    const storageWrite = vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new DOMException("blocked", "SecurityError")
    })

    try {
      rotateBrowserSession()
      expect(hasFailedBrowserSessionRotation()).toBe(true)
      expect(hasStaleBrowserSessionBinding()).toBe(false)

      storageWrite.mockRestore()
      rotateBrowserSession()
      expect(hasFailedBrowserSessionRotation()).toBe(false)
      expect(hasStaleBrowserSessionBinding()).toBe(false)
      expect(getBrowserSessionGeneration()).not.toBe("prior-generation")
      expect(JSON.parse(localStorage.getItem(KEY) ?? "null")).toEqual({
        nonce: getBrowserSessionGeneration(),
        hash: null,
      })
      expect(isCurrentBrowserSession()).toBe(true)
    } finally {
      storageWrite.mockRestore()
    }
  })
  it("keeps a prior stale binding stale when rotation storage write fails", () => {
    localStorage.setItem(KEY, JSON.stringify({ nonce: "tab-a-generation", hash: "profile-a" }))
    acceptBrowserSessionGeneration()
    localStorage.setItem(KEY, JSON.stringify({ nonce: "tab-b-generation", hash: "profile-b" }))
    expect(hasStaleBrowserSessionBinding()).toBe(true)

    const storageWrite = vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new DOMException("blocked", "SecurityError")
    })
    try {
      rotateBrowserSession()
      expect(hasFailedBrowserSessionRotation()).toBe(true)
      expect(getBrowserSessionGeneration()).toBe("tab-b-generation")
      expect(hasStaleBrowserSessionBinding()).toBe(true)
    } finally {
      storageWrite.mockRestore()
    }
  })

  it("preserves a stale binding when generation storage becomes unreadable after failed rotation", () => {
    localStorage.setItem(KEY, JSON.stringify({ nonce: "tab-a-generation", hash: "profile-a" }))
    acceptBrowserSessionGeneration()
    localStorage.setItem(KEY, JSON.stringify({ nonce: "tab-b-generation", hash: "profile-b" }))
    const storageWrite = vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new DOMException("blocked", "SecurityError")
    })

    let restoreStorageRead: (() => void) | undefined
    try {
      rotateBrowserSession()
      expect(hasStaleBrowserSessionBinding()).toBe(true)
      const storageRead = vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
        throw new DOMException("blocked", "SecurityError")
      })
      restoreStorageRead = () => storageRead.mockRestore()
      expect(getBrowserSessionGeneration()).toBeNull()
      expect(hasStaleBrowserSessionBinding()).toBe(true)

      storageRead.mockRestore()
      restoreStorageRead = undefined
      localStorage.removeItem(KEY)
      expect(getBrowserSessionGeneration()).toBeNull()
      expect(hasStaleBrowserSessionBinding()).toBe(true)
    } finally {
      storageWrite.mockRestore()
      restoreStorageRead?.()
    }
  })
  it("fails closed on unreadable storage", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new DOMException("blocked", "SecurityError")
    })
    expect(getBrowserSessionGeneration()).toBeNull()
  })

  it("fails closed on null/null captures after a prior-generation rotation becomes unreadable or absent", () => {
    localStorage.setItem(KEY, JSON.stringify({ nonce: "prior-generation", hash: "prior-profile" }))
    acceptBrowserSessionGeneration()
    const storageWrite = vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new DOMException("blocked", "SecurityError")
    })

    try {
      rotateBrowserSession()
      storageWrite.mockRestore()

      const storageRead = vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
        throw new DOMException("blocked", "SecurityError")
      })
      try {
        expect(isCurrentBrowserSession()).toBe(false)
        expect(captureSessionEpoch()()).toBe(false)
      } finally {
        storageRead.mockRestore()
      }

      localStorage.removeItem(KEY)
      expect(isCurrentBrowserSession()).toBe(false)
      expect(captureSessionEpoch()()).toBe(false)
    } finally {
      storageWrite.mockRestore()
    }
  })

  it.each(["absent", "invalid", "unavailable"] as const)(
    "does not let generation acceptance erase a prior failed-rotation marker when storage becomes %s",
    (storageState) => {
      localStorage.setItem(
        KEY,
        JSON.stringify({ nonce: "prior-generation", hash: "prior-profile" })
      )
      acceptBrowserSessionGeneration()
      const storageWrite = vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
        throw new DOMException("blocked", "SecurityError")
      })
      let restoreStorageRead: (() => void) | undefined

      try {
        rotateBrowserSession()
        expect(hasFailedBrowserSessionRotation()).toBe(true)
        storageWrite.mockRestore()

        if (storageState === "absent") {
          localStorage.removeItem(KEY)
        } else if (storageState === "invalid") {
          localStorage.setItem(KEY, "not-json")
        } else {
          const storageRead = vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
            throw new DOMException("blocked", "SecurityError")
          })
          restoreStorageRead = () => storageRead.mockRestore()
        }

        acceptBrowserSessionGeneration()
        expect(isCurrentBrowserSession()).toBe(false)
        expect(captureSessionEpoch()()).toBe(false)

        if (storageState !== "absent") {
          restoreStorageRead?.()
          restoreStorageRead = undefined
          localStorage.removeItem(KEY)
          expect(isCurrentBrowserSession()).toBe(false)
          expect(captureSessionEpoch()()).toBe(false)
        }
      } finally {
        storageWrite.mockRestore()
        restoreStorageRead?.()
      }
    }
  )

  it.each(["absent", "invalid", "unavailable", "foreign"] as const)(
    "does not let a second failed legacy rotation erase a prior marker when storage is %s",
    (storageState) => {
      localStorage.setItem(
        KEY,
        JSON.stringify({ nonce: "prior-generation", hash: "prior-profile" })
      )
      acceptBrowserSessionGeneration()
      const initialWrite = vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
        throw new DOMException("blocked", "SecurityError")
      })
      let restoreStorageRead: (() => void) | undefined

      try {
        rotateBrowserSession()
        expect(hasFailedBrowserSessionRotation()).toBe(true)
        initialWrite.mockRestore()

        if (storageState === "absent") {
          localStorage.removeItem(KEY)
        } else if (storageState === "invalid") {
          localStorage.setItem(KEY, "not-json")
        } else if (storageState === "foreign") {
          localStorage.setItem(
            KEY,
            JSON.stringify({ nonce: "foreign-generation", hash: "foreign" })
          )
        } else {
          const storageRead = vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
            throw new DOMException("blocked", "SecurityError")
          })
          restoreStorageRead = () => storageRead.mockRestore()
        }

        const noOpWrite = vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {})
        try {
          rotateBrowserSession()
          expect(hasFailedBrowserSessionRotation()).toBe(true)
          expect(isCurrentBrowserSession()).toBe(false)
          expect(captureSessionEpoch()()).toBe(false)
        } finally {
          noOpWrite.mockRestore()
        }

        if (storageState === "invalid" || storageState === "unavailable") {
          restoreStorageRead?.()
          restoreStorageRead = undefined
          localStorage.removeItem(KEY)
          expect(isCurrentBrowserSession()).toBe(false)
          expect(captureSessionEpoch()()).toBe(false)
        }
      } finally {
        initialWrite.mockRestore()
        restoreStorageRead?.()
      }
    }
  )

  it("does not let establishment publish an offline identity after an unresolved prior rotation", () => {
    localStorage.setItem(KEY, JSON.stringify({ nonce: "prior-generation", hash: "prior-profile" }))
    acceptBrowserSessionGeneration()
    const blockedWrite = vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new DOMException("blocked", "SecurityError")
    })

    try {
      rotateBrowserSession()
      blockedWrite.mockRestore()
      const establishmentWrite = vi.spyOn(Storage.prototype, "setItem")

      try {
        expect(establishBrowserSession("new-profile-hash", "prior-generation")).toBeNull()
        expect(establishmentWrite).not.toHaveBeenCalled()
        expect(isCurrentBrowserSession()).toBe(false)
        expect(captureSessionEpoch()()).toBe(false)
        expect(localStorage.getItem(KEY)).toEqual(
          JSON.stringify({ nonce: "prior-generation", hash: "prior-profile" })
        )
      } finally {
        establishmentWrite.mockRestore()
      }
    } finally {
      blockedWrite.mockRestore()
    }
  })

  it.each(["same-nonce-hash", "foreign", "absent", "unavailable"] as const)(
    "latches a %s snapshot observed by acceptance and denies online fallback after storage returns to the saved snapshot",
    (storageState) => {
      const original = JSON.stringify({ nonce: "prior-generation", hash: null })
      localStorage.setItem(KEY, original)
      acceptBrowserSessionGeneration()
      const initialWrite = vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
        throw new DOMException("blocked", "SecurityError")
      })
      let restoreStorageRead: (() => void) | undefined

      try {
        rotateBrowserSession()
        initialWrite.mockRestore()

        if (storageState === "same-nonce-hash") {
          localStorage.setItem(
            KEY,
            JSON.stringify({ nonce: "prior-generation", hash: "different-profile" })
          )
        } else if (storageState === "foreign") {
          localStorage.setItem(
            KEY,
            JSON.stringify({ nonce: "foreign-generation", hash: "profile-foreign" })
          )
        } else if (storageState === "absent") {
          localStorage.removeItem(KEY)
        } else {
          const storageRead = vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
            throw new DOMException("blocked", "SecurityError")
          })
          restoreStorageRead = () => storageRead.mockRestore()
        }

        acceptBrowserSessionGeneration()
        restoreStorageRead?.()
        restoreStorageRead = undefined
        localStorage.setItem(KEY, original)

        const retryWrite = vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
          throw new DOMException("blocked", "SecurityError")
        })
        try {
          const transition = beginBrowserSessionTransition("login")
          expect(transition.status).toBe("denied")
          expect(transition.isCurrent()).toBe(false)
          expect(hasStaleBrowserSessionBinding()).toBe(true)
          expect(captureSessionEpoch()()).toBe(false)
        } finally {
          retryWrite.mockRestore()
        }
      } finally {
        initialWrite.mockRestore()
        restoreStorageRead?.()
      }
    }
  )
  it("handles runtimes without browser storage", () => {
    vi.stubGlobal("localStorage", undefined)
    rotateBrowserSession()
    expect(getBrowserSessionGeneration()).toBeNull()
    expect(establishBrowserSession("key", null)).toBeNull()
  })

  it("keeps online ownership only while an exact owned snapshot remains after a failed write", () => {
    localStorage.setItem(KEY, JSON.stringify({ nonce: "owned-generation", hash: "profile-owned" }))
    acceptBrowserSessionGeneration()
    const storageWrite = vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new DOMException("blocked", "SecurityError")
    })

    try {
      const transition = beginBrowserSessionTransition("login")
      expect(transition.status).toBe("online-only")
      expect(transition.isCurrent()).toBe(true)

      storageWrite.mockRestore()
      localStorage.setItem(KEY, JSON.stringify({ nonce: "foreign-generation", hash: "profile-b" }))
      expect(transition.isCurrent()).toBe(false)
    } finally {
      storageWrite.mockRestore()
    }
  })

  it("allows network-only ownership only for confirmed absence after a failed write", () => {
    const storageWrite = vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new DOMException("blocked", "SecurityError")
    })

    try {
      const transition = beginBrowserSessionTransition("logout")
      expect(transition.status).toBe("online-only")
      expect(transition.isCurrent()).toBe(true)
      expect(localStorage.getItem(KEY)).toBeNull()
    } finally {
      storageWrite.mockRestore()
    }
  })

  it("allows stale takeover only for a login with an exact verified fresh generation", () => {
    localStorage.setItem(KEY, JSON.stringify({ nonce: "tab-a", hash: "profile-a" }))
    acceptBrowserSessionGeneration()
    localStorage.setItem(KEY, JSON.stringify({ nonce: "tab-b", hash: "profile-b" }))

    const transition = beginBrowserSessionTransition("login")

    expect(transition.status).toBe("verified")
    expect(transition.isCurrent()).toBe(true)
    expect(getBrowserSessionGeneration()).not.toBe("tab-b")
    expect(JSON.parse(localStorage.getItem(KEY) ?? "null")).toEqual({
      nonce: getBrowserSessionGeneration(),
      hash: null,
    })
  })

  it.each(["logout", "unauthenticated-mfa"] as const)(
    "does not rotate a stale generation for %s",
    (operation) => {
      localStorage.setItem(KEY, JSON.stringify({ nonce: "tab-a", hash: "profile-a" }))
      acceptBrowserSessionGeneration()
      localStorage.setItem(KEY, JSON.stringify({ nonce: "tab-b", hash: "profile-b" }))
      const storageWrite = vi.spyOn(Storage.prototype, "setItem")

      try {
        const transition = beginBrowserSessionTransition(operation)
        expect(transition.status).toBe("denied")
        expect(transition.isCurrent()).toBe(false)
        expect(storageWrite).not.toHaveBeenCalled()
        expect(localStorage.getItem(KEY)).toContain("tab-b")
      } finally {
        storageWrite.mockRestore()
      }
    }
  )

  it.each(["not-json", '{"nonce":"bad","hash":42}'])(
    "denies login transition when generation metadata is invalid: %s",
    (value) => {
      localStorage.setItem(KEY, value)
      const storageWrite = vi.spyOn(Storage.prototype, "setItem")

      try {
        const transition = beginBrowserSessionTransition("login")
        expect(transition.status).toBe("denied")
        expect(storageWrite).not.toHaveBeenCalled()
      } finally {
        storageWrite.mockRestore()
      }
    }
  )

  it("denies login when the initial storage snapshot is unavailable", () => {
    const storageRead = vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new DOMException("blocked", "SecurityError")
    })
    const storageWrite = vi.spyOn(Storage.prototype, "setItem")

    try {
      const transition = beginBrowserSessionTransition("login")
      expect(transition.status).toBe("denied")
      expect(storageWrite).not.toHaveBeenCalled()
    } finally {
      storageWrite.mockRestore()
      storageRead.mockRestore()
    }
  })

  it("rejects a successful storage call whose readback does not match the requested nonce", () => {
    localStorage.setItem(KEY, JSON.stringify({ nonce: "owned-generation", hash: "profile-a" }))
    acceptBrowserSessionGeneration()
    const originalSetItem = Storage.prototype.setItem.bind(localStorage)
    const storageWrite = vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      originalSetItem(KEY, JSON.stringify({ nonce: "foreign-generation", hash: "profile-b" }))
    })

    try {
      const transition = beginBrowserSessionTransition("logout")
      expect(transition.status).toBe("denied")
      expect(transition.isCurrent()).toBe(false)
      expect(localStorage.getItem(KEY)).toContain("foreign-generation")
    } finally {
      storageWrite.mockRestore()
    }
  })

  it("supersedes an earlier transition receipt with a later transition", () => {
    const first = beginBrowserSessionTransition("login")
    expect(first.status).toBe("verified")
    expect(first.isCurrent()).toBe(true)

    const second = beginBrowserSessionTransition("login")

    expect(second.status).toBe("verified")
    expect(second.isCurrent()).toBe(true)
    expect(first.isCurrent()).toBe(false)
  })

  it("denies a transition when browser storage is unavailable before ownership can be read", () => {
    vi.stubGlobal("localStorage", undefined)
    const storageWrite = vi.spyOn(Storage.prototype, "setItem")

    try {
      const transition = beginBrowserSessionTransition("login")

      expect(transition.status).toBe("denied")
      expect(transition.isCurrent()).toBe(false)
      expect(storageWrite).not.toHaveBeenCalled()
    } finally {
      storageWrite.mockRestore()
    }
  })

  it("leaves an owned session current when transition nonce generation fails", () => {
    const nonce = establishBrowserSession("current-profile-hash", null)!
    const storedBefore = localStorage.getItem(KEY)
    const epochBefore = getSessionEpoch()
    const randomUuid = vi.spyOn(crypto, "randomUUID").mockImplementation(() => {
      throw new Error("random source unavailable")
    })
    const storageWrite = vi.spyOn(Storage.prototype, "setItem")

    try {
      const transition = beginBrowserSessionTransition("logout")

      expect(transition.status).toBe("denied")
      expect(transition.isCurrent()).toBe(false)
      expect(getSessionEpoch()).toBe(epochBefore)
      expect(getBrowserSessionGeneration()).toBe(nonce)
      expect(localStorage.getItem(KEY)).toBe(storedBefore)
      expect(hasFailedBrowserSessionRotation()).toBe(false)
      expect(isCurrentBrowserSession()).toBe(true)
      expect(captureSessionEpoch()()).toBe(true)
      expect(storageWrite).not.toHaveBeenCalled()
    } finally {
      storageWrite.mockRestore()
      randomUuid.mockRestore()
    }
  })

  it("records a failed legacy rotation without changing the mirror when nonce generation fails", () => {
    const prior = { nonce: "prior-generation", hash: "prior-profile" }
    localStorage.setItem(KEY, JSON.stringify(prior))
    acceptBrowserSessionGeneration()
    const epochBefore = getSessionEpoch()
    const randomUuid = vi.spyOn(crypto, "randomUUID").mockImplementation(() => {
      throw new Error("random source unavailable")
    })
    const storageWrite = vi.spyOn(Storage.prototype, "setItem")

    try {
      rotateBrowserSession()

      expect(getSessionEpoch()).toBe(epochBefore + 1)
      expect(getBrowserSessionGeneration()).toBe(prior.nonce)
      expect(JSON.parse(localStorage.getItem(KEY) ?? "null")).toEqual(prior)
      expect(hasFailedBrowserSessionRotation()).toBe(true)
      expect(hasStaleBrowserSessionBinding()).toBe(false)
      expect(isCurrentBrowserSession()).toBe(false)
      expect(storageWrite).not.toHaveBeenCalled()
    } finally {
      storageWrite.mockRestore()
      randomUuid.mockRestore()
    }
  })

  it("denies a transition when storage disappears after its owned snapshot is read", () => {
    establishBrowserSession("current-profile-hash", null)
    const epochBefore = getSessionEpoch()
    const randomUuid = vi.spyOn(crypto, "randomUUID").mockImplementation(() => {
      vi.stubGlobal("localStorage", undefined)
      return "00000000-0000-4000-8000-000000000041"
    })
    const storageWrite = vi.spyOn(Storage.prototype, "setItem")

    try {
      const transition = beginBrowserSessionTransition("logout")

      expect(randomUuid).toHaveBeenCalledTimes(1)
      expect(transition.status).toBe("denied")
      expect(transition.isCurrent()).toBe(false)
      expect(getSessionEpoch()).toBe(epochBefore + 1)
      expect(hasFailedBrowserSessionRotation()).toBe(true)
      expect(isCurrentBrowserSession()).toBe(false)
      expect(captureSessionEpoch()()).toBe(false)
      expect(storageWrite).not.toHaveBeenCalled()
    } finally {
      storageWrite.mockRestore()
      randomUuid.mockRestore()
    }
  })

  it.each(["invalid", "unavailable"] as const)(
    "retains fail-closed ownership after accepting %s metadata with a prior bound session",
    (storageState) => {
      const nonce = establishBrowserSession("prior-profile-hash", null)
      const storageRead =
        storageState === "unavailable"
          ? vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
              throw new DOMException("blocked", "SecurityError")
            })
          : undefined

      try {
        if (storageState === "invalid") localStorage.setItem(KEY, "not-json")
        acceptBrowserSessionGeneration()

        expect(nonce).not.toBeNull()
        expect(hasFailedBrowserSessionRotation()).toBe(true)
        expect(hasStaleBrowserSessionBinding()).toBe(true)
        expect(isCurrentBrowserSession()).toBe(false)
        expect(captureSessionEpoch()()).toBe(false)
      } finally {
        storageRead?.mockRestore()
      }
    }
  )

  it.each(["absent", "foreign-nonce", "same-nonce-wrong-hash"] as const)(
    "does not establish a requested profile hash after a %s readback",
    (readbackState) => {
      const priorNonce = establishBrowserSession("prior-profile-hash", null)!
      const requestedNonce = "00000000-0000-4000-8000-000000000042"
      const randomUuid = vi.spyOn(crypto, "randomUUID").mockReturnValue(requestedNonce)
      const originalSetItem = Storage.prototype.setItem.bind(localStorage)
      const originalRemoveItem = Storage.prototype.removeItem.bind(localStorage)
      const storageWrite = vi
        .spyOn(Storage.prototype, "setItem")
        .mockImplementation((key, value) => {
          if (key !== KEY) {
            originalSetItem(key, value)
          } else if (readbackState === "absent") {
            originalRemoveItem(KEY)
          } else if (readbackState === "foreign-nonce") {
            originalSetItem(
              KEY,
              JSON.stringify({ nonce: "foreign-generation", hash: "foreign-hash" })
            )
          } else {
            originalSetItem(KEY, JSON.stringify({ nonce: requestedNonce, hash: "competing-hash" }))
          }
        })

      try {
        expect(establishBrowserSession("requested-profile-hash", priorNonce)).toBeNull()
        expect(storageWrite).toHaveBeenCalledTimes(1)
        expect(matchesBrowserSession("requested-profile-hash", requestedNonce)).toBe(false)
        expect(isCurrentBrowserSession()).toBe(false)

        const actual = localStorage.getItem(KEY)
        if (readbackState === "absent") {
          expect(actual).toBeNull()
        } else if (readbackState === "foreign-nonce") {
          expect(JSON.parse(actual ?? "null")).toEqual({
            nonce: "foreign-generation",
            hash: "foreign-hash",
          })
        } else {
          expect(JSON.parse(actual ?? "null")).toEqual({
            nonce: requestedNonce,
            hash: "competing-hash",
          })
        }
      } finally {
        storageWrite.mockRestore()
        randomUuid.mockRestore()
      }
    }
  )

  it("keeps a present online-only receipt retryable only for the unchanged owned snapshot", () => {
    const original = JSON.stringify({ nonce: "owned-generation", hash: "profile-owned" })
    localStorage.setItem(KEY, original)
    acceptBrowserSessionGeneration()
    const storageWrite = vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new DOMException("blocked", "SecurityError")
    })

    try {
      const first = beginBrowserSessionTransition("login")
      expect(first.status).toBe("online-only")
      expect(first.isCurrent()).toBe(true)

      const second = beginBrowserSessionTransition("login")

      expect(second.status).toBe("online-only")
      expect(second.isCurrent()).toBe(true)
      expect(first.isCurrent()).toBe(false)
      expect(hasStaleBrowserSessionBinding()).toBe(false)
      expect(localStorage.getItem(KEY)).toBe(original)
    } finally {
      storageWrite.mockRestore()
    }
  })

  it("keeps confirmed-absent online-only ownership retryable across a second failed write", () => {
    const storageWrite = vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new DOMException("blocked", "SecurityError")
    })

    try {
      const first = beginBrowserSessionTransition("logout")
      expect(first.status).toBe("online-only")
      expect(first.isCurrent()).toBe(true)

      const second = beginBrowserSessionTransition("logout")

      expect(second.status).toBe("online-only")
      expect(second.isCurrent()).toBe(true)
      expect(first.isCurrent()).toBe(false)
      expect(getBrowserSessionGeneration()).toBeNull()
      expect(hasStaleBrowserSessionBinding()).toBe(false)
      expect(localStorage.getItem(KEY)).toBeNull()
    } finally {
      storageWrite.mockRestore()
    }
  })

  it("latches a same-nonce hash change observed during a repeated failed legacy rotation", () => {
    const prior = { nonce: "prior-generation", hash: "prior-profile" }
    localStorage.setItem(KEY, JSON.stringify(prior))
    acceptBrowserSessionGeneration()
    const initialWrite = vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new DOMException("blocked", "SecurityError")
    })

    try {
      rotateBrowserSession()
      expect(hasFailedBrowserSessionRotation()).toBe(true)
      expect(hasStaleBrowserSessionBinding()).toBe(false)
    } finally {
      initialWrite.mockRestore()
    }

    const originalSetItem = Storage.prototype.setItem.bind(localStorage)
    const competingWrite = vi
      .spyOn(Storage.prototype, "setItem")
      .mockImplementation((key, value) => {
        if (key === KEY) {
          originalSetItem(KEY, JSON.stringify({ nonce: prior.nonce, hash: "competing-profile" }))
        } else {
          originalSetItem(key, value)
        }
      })

    try {
      rotateBrowserSession()

      expect(competingWrite).toHaveBeenCalledTimes(1)
      expect(JSON.parse(localStorage.getItem(KEY) ?? "null")).toEqual({
        nonce: prior.nonce,
        hash: "competing-profile",
      })
      expect(hasFailedBrowserSessionRotation()).toBe(true)
      expect(hasStaleBrowserSessionBinding()).toBe(true)
      expect(isCurrentBrowserSession()).toBe(false)
      expect(captureSessionEpoch()()).toBe(false)
    } finally {
      competingWrite.mockRestore()
    }

    localStorage.setItem(KEY, JSON.stringify(prior))
    expect(hasStaleBrowserSessionBinding()).toBe(true)
    expect(isCurrentBrowserSession()).toBe(false)
  })

  it.each(["invalid", "unavailable"] as const)(
    "keeps confirmed-absent failed rotation sticky when a repeated rotation sees %s storage",
    (storageState) => {
      const initialWrite = vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
        throw new DOMException("blocked", "SecurityError")
      })

      try {
        const transition = beginBrowserSessionTransition("logout")
        expect(transition.status).toBe("online-only")
        expect(transition.isCurrent()).toBe(true)
      } finally {
        initialWrite.mockRestore()
      }

      if (storageState === "invalid") localStorage.setItem(KEY, "not-json")
      const storageRead =
        storageState === "unavailable"
          ? vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
              throw new DOMException("blocked", "SecurityError")
            })
          : undefined
      const noOpWrite = vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {})

      try {
        rotateBrowserSession()

        expect(hasFailedBrowserSessionRotation()).toBe(true)
        expect(hasStaleBrowserSessionBinding()).toBe(true)
        expect(isCurrentBrowserSession()).toBe(false)
        expect(captureSessionEpoch()()).toBe(false)
      } finally {
        noOpWrite.mockRestore()
        storageRead?.mockRestore()
      }
    }
  )
})
