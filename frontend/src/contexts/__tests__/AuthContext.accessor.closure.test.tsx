import { render, waitFor } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"

const mocks = vi.hoisted(() => ({
  registerSigningKeyAccessor: vi.fn(),
  resetEtagCache: vi.fn(),
  signingKeyRef: { current: "initial-signing-key" as string | null },
}))

vi.mock("@/api/client", () => ({
  registerSigningKeyAccessor: mocks.registerSigningKeyAccessor,
  resetEtagCache: mocks.resetEtagCache,
}))

vi.mock("@/hooks/auth/useSessionCrypto", () => ({
  useSessionCrypto: () => ({
    sessionSigningKey: mocks.signingKeyRef.current,
    sessionSigningKeyRef: mocks.signingKeyRef,
    updateSessionSigningKey: vi.fn(),
    sessionSigningKeyPromiseRef: { current: null },
    ensureSessionSigningKey: vi.fn(async () => mocks.signingKeyRef.current),
  }),
}))

vi.mock("@/hooks/auth/useProfileSync", () => ({
  PROFILE_CACHE_STORAGE_KEY: "ecosystem.profile.cache",
  currentUserQueryKey: ["users", "me"],
  fetchCurrentUser: vi.fn(),
  useProfileSync: () => ({
    user: null,
    setUser: vi.fn(),
    updatePendingMfa: vi.fn(),
    handleUnauthorized: vi.fn(),
    authOperation: false,
    setAuthOperation: vi.fn(),
  }),
}))

vi.mock("@/hooks/auth/ssrAuthHint", () => ({
  readSsrAuthHint: () => undefined,
}))

vi.mock("@/hooks/auth/useAuthApi", () => ({
  useAuthApi: () => ({
    login: vi.fn(),
    logout: vi.fn(),
    submitMfaChallenge: vi.fn(),
    requireMfa: vi.fn(),
    refresh: vi.fn(),
  }),
}))

import { AuthProvider } from "@/contexts/AuthContext"

afterEach(() => {
  vi.clearAllMocks()
  mocks.signingKeyRef.current = "initial-signing-key"
})

describe("AuthProvider signing-key accessor", () => {
  it("registers a live accessor that always reads the current signing-key ref", async () => {
    render(
      <AuthProvider>
        <div>child</div>
      </AuthProvider>
    )

    await waitFor(() => expect(mocks.registerSigningKeyAccessor).toHaveBeenCalledOnce())
    const accessor = mocks.registerSigningKeyAccessor.mock.calls[0]![0] as () => string | null

    expect(accessor()).toBe("initial-signing-key")
    mocks.signingKeyRef.current = "rotated-signing-key"
    expect(accessor()).toBe("rotated-signing-key")
  })
})
