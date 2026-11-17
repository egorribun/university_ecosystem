import { renderToString } from "react-dom/server"
import { describe, expect, it, vi } from "vitest"
import { useSessionIdentity } from "@/hooks/useSessionIdentity"
import { invalidateSessionEpoch, subscribeSessionIdentity } from "@/stores/sessionEpoch"

describe("session identity subscription", () => {
  it("coalesces local changes, observes relevant storage events, and stops after unsubscribe", async () => {
    const listener = vi.fn()
    const unsubscribe = subscribeSessionIdentity(listener)
    invalidateSessionEpoch()
    invalidateSessionEpoch()
    expect(listener).not.toHaveBeenCalled()
    await Promise.resolve()
    expect(listener).toHaveBeenCalledOnce()

    window.dispatchEvent(new StorageEvent("storage", { key: "unrelated" }))
    await Promise.resolve()
    expect(listener).toHaveBeenCalledOnce()

    window.dispatchEvent(new StorageEvent("storage", { key: null }))
    await Promise.resolve()
    expect(listener).toHaveBeenCalledTimes(2)

    unsubscribe()
    invalidateSessionEpoch()
    await Promise.resolve()
    expect(listener).toHaveBeenCalledTimes(2)
  })

  it("provides an unknown server snapshot and supports subscription without a window", () => {
    const ServerIdentity = () => <output>{JSON.stringify(useSessionIdentity())}</output>
    expect(renderToString(<ServerIdentity />)).toContain("[0,null,null]")

    vi.stubGlobal("window", undefined)
    try {
      const unsubscribe = subscribeSessionIdentity(vi.fn())
      unsubscribe()
    } finally {
      vi.unstubAllGlobals()
    }
  })
})
