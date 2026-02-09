import { createContext, useContext, useMemo } from "react"
import { resetEtagCache } from "@/api/client"
import { useSessionCrypto } from "@/hooks/auth/useSessionCrypto"
import { useProfileSync, fetchCurrentUser, currentUserQueryKey } from "@/hooks/auth/useProfileSync"
import { useAuthApi } from "@/hooks/auth/useAuthApi"
import type { AuthContextType } from "@/types/Auth"
import { ChallengeLockedError } from "@/types/Auth"

const noopSetUser = () => {
  if (import.meta.env.DEV) {
    console.warn("AuthContext setUser called outside provider")
  }
}

export const AuthContext = createContext<AuthContextType>({
  isAuth: false,
  login: async () => null,
  logout: async () => {},
  user: null,
  loading: false,
  setUser: noopSetUser,
  refresh: async () => {},
  pendingMfa: null,
  submitMfaChallenge: async () => {},
  requireMfa: async () => null,
  loginWithPasskey: async () => {},
  resetEtagCache,
})

export const useAuth = () => useContext(AuthContext)
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
    loading,
    pendingMfa,
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
      isAuth: user !== null,
      login,
      logout,
      user,
      loading,
      setUser,
      refresh,
      pendingMfa,
      submitMfaChallenge,
      requireMfa,
      loginWithPasskey,
      resetEtagCache,
    }),
    [
      user,
      login,
      logout,
      loading,
      setUser,
      refresh,
      pendingMfa,
      submitMfaChallenge,
      requireMfa,
      loginWithPasskey,
    ]
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
