import type { PropsWithChildren } from "react"
import { renderHook } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"

import { AuthContext, useAuth } from "@/contexts/AuthContext"
import { useAuthStore } from "@/stores/useAuthStore"
import type { PendingMfaState, UserState } from "@/types/Auth"

const storeUser: UserState = {
  id: "store-user",
  email: "store@example.com",
  full_name: "Store User",
  role: "student",
  is_active: true,
  avatar_url: null,
  group_id: null,
}

const contextUser: UserState = {
  ...storeUser,
  id: "context-user",
  email: "context@example.com",
  full_name: "Context User",
}

const pending: PendingMfaState = {
  reason: "login",
  user_id: "mfa-user",
  methods: [],
}

const actionSet = () => ({
  login: vi.fn(async () => null),
  logout: vi.fn(async () => undefined),
  setUser: vi.fn(),
  refresh: vi.fn(async () => undefined),
  submitMfaChallenge: vi.fn(async () => undefined),
  requireMfa: vi.fn(async () => null),
  resetEtagCache: vi.fn(),
  authOperation: false,
})

afterEach(() => {
  useAuthStore.setState({
    user: null,
    loading: true,
    pendingMfa: null,
    authOperation: false,
  })
})

describe("useAuth context/store selection", () => {
  it("prefers explicitly provided context state over the Zustand fallback", () => {
    useAuthStore.setState({ user: null, pendingMfa: null, loading: true, authOperation: false })
    const contextValue = {
      ...actionSet(),
      user: contextUser,
      pendingMfa: pending,
      loading: false,
    }
    const wrapper = ({ children }: PropsWithChildren) => (
      <AuthContext.Provider value={contextValue}>{children}</AuthContext.Provider>
    )

    const { result } = renderHook(() => useAuth(), { wrapper })

    expect(result.current.user).toBe(contextUser)
    expect(result.current.pendingMfa).toBe(pending)
    expect(result.current.loading).toBe(false)
    expect(result.current.isAuth).toBe(true)
  })

  it("falls back to Zustand state when context leaves optional state undefined", () => {
    useAuthStore.setState({
      user: storeUser,
      pendingMfa: pending,
      loading: false,
      authOperation: false,
    })
    const contextValue = actionSet()
    const wrapper = ({ children }: PropsWithChildren) => (
      <AuthContext.Provider value={contextValue}>{children}</AuthContext.Provider>
    )

    const { result } = renderHook(() => useAuth(), { wrapper })

    expect(result.current.user).toBe(storeUser)
    expect(result.current.pendingMfa).toBe(pending)
    expect(result.current.loading).toBe(false)
    expect(result.current.isAuth).toBe(true)
  })

  it("includes an active context operation in the loading state", () => {
    useAuthStore.setState({ user: null, pendingMfa: null, loading: false, authOperation: false })
    const contextValue = { ...actionSet(), loading: false, authOperation: true }
    const wrapper = ({ children }: PropsWithChildren) => (
      <AuthContext.Provider value={contextValue}>{children}</AuthContext.Provider>
    )

    const { result } = renderHook(() => useAuth(), { wrapper })

    expect(result.current.loading).toBe(true)
    expect(result.current.isAuth).toBe(false)
  })
})
