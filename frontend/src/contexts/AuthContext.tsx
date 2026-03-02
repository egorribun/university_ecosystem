import { createContext, useContext, useEffect, useMemo } from "react"
import { resetEtagCache, registerSigningKeyAccessor } from "@/api/client"
import { useSessionCrypto } from "@/hooks/auth/useSessionCrypto"
import { useProfileSync, fetchCurrentUser, currentUserQueryKey } from "@/hooks/auth/useProfileSync"
import { useAuthApi } from "@/hooks/auth/useAuthApi"
import type { AuthContextType } from "@/types/Auth"
import { ChallengeLockedError } from "@/types/Auth"
import { logWarning } from "@/app/logger"
import { useAuthStore } from "@/stores/useAuthStore"

const noopSetUser = () => {
  logWarning("AuthContext setUser called outside provider")
}

export const AuthContext = createContext<Omit<AuthContextType, "user" | "loading" | "pendingMfa" | "isAuth" | "authOperation">>({
  login: async () => null,
  logout: async () => {},
  setUser: noopSetUser,
  refresh: async () => {},
  submitMfaChallenge: async () => {},
  requireMfa: async () => null,
  loginWithPasskey: async () => {},
  resetEtagCache,
} as unknown as Omit<AuthContextType, "user" | "loading" | "pendingMfa" | "isAuth" | "authOperation">)

export const useAuth = (): AuthContextType => {
  const store = useAuthStore()
  const actions = useContext(AuthContext)
  return {
    ...store,
    ...actions,
    isAuth: store.user !== null,
  }
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

  const {
    user,
    setUser,
    updatePendingMfa,
    handleUnauthorized,
    authOperation,
    setAuthOperation,
  } = useProfileSync(
    updateSessionSigningKey,
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
    [login, logout, setUser, refresh, submitMfaChallenge, requireMfa, loginWithPasskey]
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
