import { act, renderHook } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"

const auth = vi.hoisted(() => ({
  user: null as { id: string } | null,
  loading: true,
}))

vi.mock("@/contexts/AuthContext", () => ({ useAuth: () => auth }))

import { useProfileSessionGuard } from "@/hooks/useProfileSessionGuard"
import {
  acceptBrowserSessionGeneration,
  establishBrowserSession,
  getBrowserSessionGeneration,
  invalidateSessionEpoch,
  rotateBrowserSession,
} from "@/stores/sessionEpoch"

const generationKey = "ecosystem.session.generation.v1"

beforeEach(() => {
  rotateBrowserSession()
  auth.user = null
  auth.loading = true
})

describe("profile session guard identity publication", () => {
  it("updates the capture after bootstrap changes the epoch before the user settles", () => {
    const { result, rerender } = renderHook(() => useProfileSessionGuard())
    const oldCapture = result.current
    const oldReceipt = oldCapture()
    expect(oldReceipt()).toBe(false)

    act(() => {
      invalidateSessionEpoch()
      auth.user = { id: "account-a" }
      auth.loading = false
      rerender()
    })

    expect(oldCapture()()).toBe(false)
    expect(oldReceipt()).toBe(false)
    expect(result.current()()).toBe(true)
  })

  it("invalidates old captures immediately and publishes the new same-account epoch", async () => {
    auth.user = { id: "account-a" }
    auth.loading = false
    const { result } = renderHook(() => useProfileSessionGuard())
    const oldCapture = result.current
    const oldReceipt = oldCapture()
    expect(oldReceipt()).toBe(true)

    await act(async () => {
      invalidateSessionEpoch()
      expect(oldReceipt()).toBe(false)
      expect(oldCapture()()).toBe(false)
      await Promise.resolve()
    })

    expect(result.current).not.toBe(oldCapture)
    expect(result.current()()).toBe(true)
  })

  it("reacts to generation replacement even when the epoch is unchanged", async () => {
    auth.user = { id: "account-a" }
    auth.loading = false
    const currentGeneration = getBrowserSessionGeneration()
    const firstGeneration = establishBrowserSession("first-hash", currentGeneration)
    expect(firstGeneration).not.toBeNull()
    const { result } = renderHook(() => useProfileSessionGuard())
    const oldCapture = result.current
    const oldReceipt = oldCapture()

    await act(async () => {
      expect(establishBrowserSession("second-hash", firstGeneration)).not.toBe(firstGeneration)
      expect(oldReceipt()).toBe(false)
      expect(oldCapture()()).toBe(false)
      await Promise.resolve()
    })
    expect(result.current()()).toBe(true)
  })

  it("fails closed on a cross-tab generation until the new binding is accepted", async () => {
    auth.user = { id: "account-a" }
    auth.loading = false
    const { result } = renderHook(() => useProfileSessionGuard())
    const oldCapture = result.current
    const oldReceipt = oldCapture()
    expect(oldReceipt()).toBe(true)

    await act(async () => {
      localStorage.setItem(generationKey, JSON.stringify({ nonce: "remote-session", hash: null }))
      expect(oldReceipt()).toBe(false)
      window.dispatchEvent(new StorageEvent("storage", { key: generationKey }))
      await Promise.resolve()
    })
    expect(result.current()()).toBe(false)

    await act(async () => {
      acceptBrowserSessionGeneration()
      await Promise.resolve()
    })
    expect(result.current()()).toBe(true)
    expect(oldReceipt()).toBe(false)
  })

  it("keeps the same capture across a same-session loading pause", () => {
    auth.user = { id: "account-a" }
    auth.loading = false
    const { result, rerender } = renderHook(() => useProfileSessionGuard())
    const capture = result.current
    const receipt = capture()

    auth.loading = true
    rerender()
    expect(result.current).toBe(capture)
    expect(capture()()).toBe(false)
    expect(receipt()).toBe(true)

    auth.loading = false
    rerender()
    expect(result.current).toBe(capture)
    expect(capture()()).toBe(true)
  })
})
