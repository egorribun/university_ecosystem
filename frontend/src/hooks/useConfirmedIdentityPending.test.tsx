import { renderHook } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"

import { useConfirmedIdentityPending } from "@/hooks/useConfirmedIdentityPending"
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
})
