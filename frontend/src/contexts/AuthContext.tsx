import { createContext, useContext, useEffect, useMemo } from "react"
import { resetEtagCache, registerSigningKeyAccessor } from "@/api/client"
import { useSessionCrypto } from "@/hooks/auth/useSessionCrypto"
import { useProfileSync, fetchCurrentUser, currentUserQueryKey } from "@/hooks/auth/useProfileSync"
import { readSsrAuthHint } from "@/hooks/auth/ssrAuthHint"
import { useAuthApi } from "@/hooks/auth/useAuthApi"
import type { AuthContextType } from "@/types/Auth"
import { ChallengeLockedError } from "@/types/Auth"
import { logWarning } from "@/app/logger"
import {
  useAuthUser,
  useAuthLoading,
  useAuthPendingMfa,
  useAuthActions,
} from "@/stores/useAuthStore"

interface AuthContextActions {
  login: AuthContextType["login"]
  logout: AuthContextType["logout"]
  setUser: AuthContextType["setUser"]
  refresh: AuthContextType["refresh"]
  submitMfaChallenge: AuthContextType["submitMfaChallenge"]
  requireMfa: AuthContextType["requireMfa"]
  resetEtagCache: typeof resetEtagCache
  authOperation: boolean
}

const noopSetUser = () => {
  logWarning("AuthContext setUser called outside provider")
}

export const AuthContext = createContext<AuthContextActions>({
  login: async () => null,
  logout: async () => {},
  setUser: noopSetUser,
  refresh: async () => {},
  submitMfaChallenge: async () => {},
  requireMfa: async () => null,
  resetEtagCache,
  authOperation: false,
} as AuthContextActions)

export const useAuth = (): AuthContextType => {
  const user = useAuthUser()
  const storeLoading = useAuthLoading()
  const pendingMfa = useAuthPendingMfa()
  const storeActions = useAuthActions()
  const contextActions = useContext(AuthContext)

  // Derive loading from both initial synchronization and active operations
  const loading = storeLoading || contextActions.authOperation

  // TD-NEW-002 (audit 2026-03-19): Explicit structure without "as unknown as".
  // Type is structurally inferred to be strictly compatible with AuthContextType.
  const result: AuthContextType = {
    user,
    loading,
    pendingMfa,
    isAuth: user !== null,
    ...storeActions,
    ...contextActions,
  }
  return result
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

  // Wave 128 SW1 Strategy A — read SSR auth hint from globalThis getter
  // (populated by src/server.ts via AsyncLocalStorage on server; undefined
  // on client). useProfileSync's useState initFn uses this to populate a
  // role-only stub User on SSR when JWT cookie was validated. On client,
  // hint is undefined → existing localStorage/Zustand path takes over.
  // readSsrAuthHint is a plain function (NOT a React hook) — name avoids
  // the `use` prefix so the React Compiler doesn't apply hook rules.
  const ssrAuthHint = readSsrAuthHint()

  const { user, setUser, updatePendingMfa, handleUnauthorized, authOperation, setAuthOperation } =
    useProfileSync(
      updateSessionSigningKey,
      sessionSigningKeyRef,
      sessionSigningKeyPromiseRef,
      ensureSessionSigningKey,
      ssrAuthHint
    )

  const { login, logout, submitMfaChallenge, requireMfa, refresh } = useAuthApi(
    user,
    setUser,
    updatePendingMfa,
    handleUnauthorized,
    updateSessionSigningKey,
    authOperation,
    setAuthOperation,
    resetEtagCache
  )

  // PERF-NEW-003 (audit 2026-03-19): Separate stable module-level references
  // from useMemo deps array.
  const STABLE_API_UTILS = useMemo(() => ({ resetEtagCache }), [])

  const actionsValue = useMemo(
    () => ({
      login,
      logout,
      setUser,
      refresh,
      submitMfaChallenge,
      requireMfa,
    }),
    [login, logout, setUser, refresh, submitMfaChallenge, requireMfa]
  )

  const value = useMemo(
    () => ({ ...actionsValue, ...STABLE_API_UTILS, authOperation }),
    [actionsValue, STABLE_API_UTILS, authOperation]
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
