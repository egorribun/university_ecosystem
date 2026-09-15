import { render, waitFor } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"

const mocks = vi.hoisted(() => ({
  registerSigningKeyAccessor: vi.fn(),
  resetEtagCache: vi.fn(),
  signingKeyRef: { current: "initial-signing-key" as string | null },
  updateSessionSigningKey: vi.fn(),
  ensureSessionSigningKey: vi.fn(async () => "initial-signing-key"),
  profileSync: {
    user: null,
    setUser: vi.fn(),
    updatePendingMfa: vi.fn(),
    handleUnauthorized: vi.fn(),
    authOperation: false,
    setAuthOperation: vi.fn(),
  },
  authApi: {
    login: vi.fn(),
    logout: vi.fn(),
    submitMfaChallenge: vi.fn(),
    requireMfa: vi.fn(),
    refresh: vi.fn(),
  },
}))

vi.mock("@/api/client", () => ({
  registerSigningKeyAccessor: mocks.registerSigningKeyAccessor,
  resetEtagCache: mocks.resetEtagCache,
}))

vi.mock("@/hooks/auth/useSessionCrypto", () => ({
  useSessionCrypto: () => ({
    sessionSigningKey: mocks.signingKeyRef.current,
    sessionSigningKeyRef: mocks.signingKeyRef,
    updateSessionSigningKey: mocks.updateSessionSigningKey,
    sessionSigningKeyPromiseRef: { current: null },
    ensureSessionSigningKey: mocks.ensureSessionSigningKey,
  }),
}))

vi.mock("@/hooks/auth/useProfileSync", () => ({
  PROFILE_CACHE_STORAGE_KEY: "ecosystem.profile.cache",
  currentUserQueryKey: ["users", "me"],
  fetchCurrentUser: vi.fn(),
  useProfileSync: () => mocks.profileSync,
}))

vi.mock("@/hooks/auth/ssrAuthHint", () => ({
  readSsrAuthHint: () => undefined,
}))

vi.mock("@/hooks/auth/useAuthApi", () => ({
  useAuthApi: () => mocks.authApi,
}))

import { AuthProvider, useAuth } from "@/contexts/AuthContext"

const Probe = ({ onValue }: { onValue: (value: ReturnType<typeof useAuth>) => void }) => {
  onValue(useAuth())
  return null
}

afterEach(() => {
  vi.clearAllMocks()
  mocks.signingKeyRef.current = "initial-signing-key"
  mocks.authApi = {
    login: vi.fn(),
    logout: vi.fn(),
    submitMfaChallenge: vi.fn(),
    requireMfa: vi.fn(),
    refresh: vi.fn(),
  }
  mocks.profileSync.setUser = vi.fn()
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

  it("re-registers the accessor when the signing-key ref identity changes", async () => {
    const { rerender } = render(
      <AuthProvider>
        <div>child</div>
      </AuthProvider>
    )

    await waitFor(() => expect(mocks.registerSigningKeyAccessor).toHaveBeenCalledOnce())
    const initialAccessor = mocks.registerSigningKeyAccessor.mock.calls[0]![0]

    mocks.signingKeyRef = { current: "replacement-signing-key" }
    rerender(
      <AuthProvider>
        <div>child</div>
      </AuthProvider>
    )

    await waitFor(() => expect(mocks.registerSigningKeyAccessor).toHaveBeenCalledTimes(2))
    const replacementAccessor = mocks.registerSigningKeyAccessor.mock.calls[1]![0]
    expect(replacementAccessor).not.toBe(initialAccessor)
    expect(replacementAccessor()).toBe("replacement-signing-key")
  })

  it("refreshes every memoized action when its implementation changes", () => {
    const observed = vi.fn<(value: ReturnType<typeof useAuth>) => void>()
    const { rerender } = render(
      <AuthProvider>
        <Probe onValue={observed} />
      </AuthProvider>
    )

    const actionNames = [
      "login",
      "logout",
      "setUser",
      "refresh",
      "submitMfaChallenge",
      "requireMfa",
    ] as const

    for (const actionName of actionNames) {
      const replacement = vi.fn()
      if (actionName === "setUser") {
        mocks.profileSync.setUser = replacement
      } else {
        mocks.authApi = { ...mocks.authApi, [actionName]: replacement }
      }
      rerender(
        <AuthProvider>
          <Probe onValue={observed} />
        </AuthProvider>
      )
      expect(observed.mock.lastCall?.[0][actionName]).toBe(replacement)
    }
  })
})
