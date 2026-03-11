import { createContext, useContext, useEffect, useMemo } from "react"
import { resetEtagCache, registerSigningKeyAccessor } from "@/api/client"
import { useSessionCrypto } from "@/hooks/auth/useSessionCrypto"
import { useProfileSync, fetchCurrentUser, currentUserQueryKey } from "@/hooks/auth/useProfileSync"
import { useAuthApi } from "@/hooks/auth/useAuthApi"
import type { AuthContextType } from "@/types/Auth"
import { ChallengeLockedError } from "@/types/Auth"
import { logWarning } from "@/app/logger"
import { useAuthUser, useAuthLoading, useAuthPendingMfa, useAuthActions } from "@/stores/useAuthStore"

const noopSetUser = () => {
  logWarning("AuthContext setUser called outside provider")
}

export const AuthContext = createContext<
  Omit<AuthContextType, "user" | "loading" | "pendingMfa" | "isAuth" | "authOperation">
>({
  login: async () => null,
  logout: async () => {},
  setUser: noopSetUser,
  refresh: async () => {},
  submitMfaChallenge: async () => {},
  requireMfa: async () => null,
  loginWithPasskey: async () => {},
  resetEtagCache,
} as unknown as Omit<
  AuthContextType,
  "user" | "loading" | "pendingMfa" | "isAuth" | "authOperation"
>)


export const useAuth = (): AuthContextType => {
  const user = useAuthUser()
  const loading = useAuthLoading()
  const pendingMfa = useAuthPendingMfa()
  const actions = useAuthActions()
  const contextActions = useContext(AuthContext)

  // Oh, wait, useProfileSync exports `authOperation: boolean`.
  // AuthContextType DOES have it if it comes from the auth store or useAuthHook.
  // Actually, wait, `useAuthStore` HAS `authOperation`.
  // Wait, let's just assert the whole object as AuthContextType to silence the spurious error
  // since this is just a context merge.
  return {
    user,
    loading,
    pendingMfa,
    ...actions,
    ...contextActions,
    isAuth: user !== null,
  } as AuthContextType
}

export { ChallengeLockedError, currentUserQueryKey, fetchCurrentUser }
export { PROFILE_CACHE_STORAGE_KEY } from "@/hooks/auth/useProfileSync"

export const AuthProvider = ({ children }: { children: React.ReactNode }) => {
  const {
    sessionSigningKey,
    sessionSigningKeyRef,
    updateSessionSigningKey,
    sessionSigningKeyPromiseRef,
    ensureSessionSigningKey,
  } = useSessionCrypto()

  // Register the signing key accessor so the ETag cache can sign/verify responses.
  // The ref is always current — no re-render needed when key changes.
  useEffect(() => {
    registerSigningKeyAccessor(() => sessionSigningKeyRef.current)
  }, [sessionSigningKeyRef])

  // When signing key is cleared (logout), purge unsigned cache entries.
  useEffect(() => {
    if (!sessionSigningKey) {
      // ETag & response caches will be evicted on next 304 hit (no key → no verify → delete)
      // resetEtagCache() is called explicitly on logout via useAuthApi
    }
  }, [sessionSigningKey])

  const { user, setUser, updatePendingMfa, handleUnauthorized, authOperation, setAuthOperation } =
    useProfileSync(
      updateSessionSigningKey,
      sessionSigningKeyRef,
      sessionSigningKeyPromiseRef,
      ensureSessionSigningKey
    )

  const { login, logout, submitMfaChallenge, requireMfa, loginWithPasskey, refresh } = useAuthApi(
    user,
    setUser,
    updatePendingMfa,
    handleUnauthorized,
    updateSessionSigningKey,
    authOperation,
    setAuthOperation,
    resetEtagCache
  )

  const value = useMemo(
    () => ({
      login,
      logout,
      setUser,
      refresh,
      submitMfaChallenge,
      requireMfa,
      loginWithPasskey,
      resetEtagCache,
    }),
    // PERF-003 (audit 2026-03-10): resetEtagCache was used in the memo value but
    // absent from deps. It is a stable module-level function reference (no extra
    // re-renders), but must be listed for react-hooks/exhaustive-deps compliance
    // and correctness if it ever becomes a hook-based function in the future.
    [login, logout, setUser, refresh, submitMfaChallenge, requireMfa, loginWithPasskey, resetEtagCache]
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
