import { createContext, useContext, useMemo } from "react"
import { resetEtagCache } from "@/api/client"
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
    updateSessionSigningKey,
    sessionSigningKeyPromiseRef,
    ensureSessionSigningKey,
  } = useSessionCrypto()

  const {
    user,
    setUser,
    updatePendingMfa,
    handleUnauthorized,
    authOperation,
    setAuthOperation,
  } = useProfileSync(
    sessionSigningKey,
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
