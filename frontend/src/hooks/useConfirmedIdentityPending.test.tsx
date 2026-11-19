import { act, renderHook } from "@testing-library/react"
import { renderToString } from "react-dom/server"
import { describe, expect, it, vi } from "vitest"

import { useConfirmedIdentityPending } from "@/hooks/useConfirmedIdentityPending"
import { acceptBrowserSessionGeneration, rotateBrowserSession } from "@/stores/sessionEpoch"
import type { UserState } from "@/types/Auth"

const auth = vi.hoisted(() => ({
  user: null as UserState,
  loading: false,
}))

vi.mock("@/contexts/AuthContext", () => ({ useAuth: () => auth }))

describe("useConfirmedIdentityPending", () => {
  it.each(["ssr-stub", "-1", -1, "lhci-user"])("waits for a real identity after %s", (id) => {
    auth.user = { id } as unknown as UserState
    auth.loading = false
    const { result, rerender } = renderHook(() => useConfirmedIdentityPending())
    expect(result.current).toBe(true)

    auth.user = { id: "user-1" } as UserState
    rerender()
    expect(result.current).toBe(false)
  })

  it("waits while loading or signed out", () => {
    auth.user = { id: "user-1" } as UserState
    auth.loading = true
    const { result, rerender } = renderHook(() => useConfirmedIdentityPending())
    expect(result.current).toBe(true)

    auth.user = null
    auth.loading = false
    rerender()
    expect(result.current).toBe(true)
  })

  it("tracks a cross-tab mismatch and accepted binding without an auth rerender", async () => {
    rotateBrowserSession()
    auth.user = { id: "user-1" } as UserState
    auth.loading = false
    const { result } = renderHook(() => useConfirmedIdentityPending())
    expect(result.current).toBe(false)

    const generationKey = "ecosystem.session.generation.v1"
    await act(async () => {
      localStorage.setItem(generationKey, JSON.stringify({ nonce: "remote-session", hash: null }))
      window.dispatchEvent(new StorageEvent("storage", { key: generationKey }))
      await Promise.resolve()
    })
    expect(result.current).toBe(true)

    await act(async () => {
      acceptBrowserSessionGeneration()
      await Promise.resolve()
    })
    expect(result.current).toBe(false)
  })

  it("does not confirm a server-rendered identity without browser storage", () => {
    auth.user = { id: "user-1" } as UserState
    auth.loading = false
    const Identity = () => <output>{useConfirmedIdentityPending() ? "pending" : "ready"}</output>
    vi.stubGlobal("localStorage", undefined)
    try {
      expect(renderToString(<Identity />)).toContain("pending")
    } finally {
      vi.unstubAllGlobals()
    }
  })
})
