import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react"
import { useQuery, useQueryClient } from "@tanstack/react-query"
import { isAxiosError } from "axios"
import { softSyncPushSubscription, unsubscribePush } from "@/push/subscribe"
import api, { API_UNAUTHORIZED_EVENT, setAuthToken } from "../api/client"

type SetUserArg = any | ((prev: any) => any)

type AuthContextType = {
  isAuth: boolean
  login: (token: string) => Promise<void>
  logout: () => void
  user: any
  loading: boolean
  setUser: (user: SetUserArg) => void
}

export const AuthContext = createContext<AuthContextType>({
  isAuth: false,
  login: async () => {},
  logout: () => {},
  user: null,
  loading: false,
  setUser: () => {},
})

export const useAuth = () => useContext(AuthContext)

export const currentUserQueryKey = ["users", "me"] as const

const PROFILE_CACHE_KEY = "ecosystem.profile.cache.v1"

const readCachedUser = (): any | undefined => {
  try {
    const raw = localStorage.getItem(PROFILE_CACHE_KEY)
    if (!raw) return undefined
    const parsed = JSON.parse(raw)
    if (parsed && typeof parsed === "object" && "data" in parsed) {
      return (parsed as { data: unknown }).data
    }
    return parsed
  } catch {
    return undefined
  }
}

const persistUserToCache = (value: any | null) => {
  try {
    if (value != null) {
      localStorage.setItem(
        PROFILE_CACHE_KEY,
        JSON.stringify({ data: value, savedAt: new Date().toISOString() })
      )
    } else {
      localStorage.removeItem(PROFILE_CACHE_KEY)
    }
  } catch {
    /* ignore */
  }
}

const readStoredToken = () => {
  try {
    return localStorage.getItem("token")
  } catch {
    return null
  }
}

export const fetchCurrentUser = async () => {
  try {
    const res = await api.get("/users/me")
    return res.data
  } catch (error) {
    if (!isAxiosError(error) || error.response) {
      throw error
    }
    return null
  }
}

export const AuthProvider = ({ children }: { children: ReactNode }) => {
  const queryClient = useQueryClient()
  const [token, setToken] = useState<string | null>(() => readStoredToken())
  const hasToken = Boolean(token)

  const applyToken = useCallback((value: string | null) => {
    setToken(value)
    setAuthToken(value ?? undefined)
  }, [])

  const clearProfile = useCallback(() => {
    persistUserToCache(null)
    queryClient.setQueryData(currentUserQueryKey, null)
  }, [queryClient])

  const handleUnauthorized = useCallback(() => {
    void queryClient.cancelQueries({ queryKey: currentUserQueryKey })
    applyToken(null)
    clearProfile()
  }, [applyToken, clearProfile, queryClient])

  useEffect(() => {
    setAuthToken(token ?? undefined)
  }, [token])

  const userQuery = useQuery<any>({
    queryKey: currentUserQueryKey,
    queryFn: fetchCurrentUser,
    enabled: hasToken,
    initialData: readCachedUser,
    placeholderData: (previous: any) => previous,
    staleTime: 5 * 60 * 1000,
    gcTime: 60 * 60 * 1000,
    retry(failureCount: number, error: unknown) {
      if (isAxiosError(error) && error.response?.status === 401) return false
      return failureCount < 3
    },
    retryDelay: (attemptIndex: number) => Math.min(1000 * 2 ** attemptIndex, 30_000),
  })

  const { data: userData, isSuccess, isError, error, isPending } = userQuery

  useEffect(() => {
    if (isSuccess) {
      persistUserToCache(userData ?? null)
    }
  }, [isSuccess, userData])

  useEffect(() => {
    if (isError && isAxiosError(error) && error.response?.status === 401) {
      handleUnauthorized()
    }
  }, [error, handleUnauthorized, isError])

  useEffect(() => {
    if (typeof window === "undefined") return
    const onStorage = (event: StorageEvent) => {
      if (event.key === "token") {
        const stored = readStoredToken()
        if (stored) {
          applyToken(stored)
          void queryClient.invalidateQueries({ queryKey: currentUserQueryKey })
        } else {
          handleUnauthorized()
        }
      }
    }
    window.addEventListener("storage", onStorage)
    return () => window.removeEventListener("storage", onStorage)
  }, [applyToken, handleUnauthorized, queryClient])

  useEffect(() => {
    if (typeof window === "undefined") return
    const onUnauthorized = () => handleUnauthorized()
    window.addEventListener(API_UNAUTHORIZED_EVENT, onUnauthorized as EventListener)
    return () =>
      window.removeEventListener(API_UNAUTHORIZED_EVENT, onUnauthorized as EventListener)
  }, [handleUnauthorized])

  const user = userData ?? null
  const loading = hasToken && isPending
  const isAuth = Boolean(hasToken && user)

  const setUser = useCallback(
    (value: SetUserArg) => {
      queryClient.setQueryData(currentUserQueryKey, (prev: any) => {
        const previous = prev ?? null
        const next =
          typeof value === "function" ? (value as (prev: any) => any)(previous) : value
        persistUserToCache(next ?? null)
        return next ?? null
      })
    },
    [queryClient]
  )

  const login = useCallback(
    async (nextToken: string) => {
      applyToken(nextToken)
      await queryClient.cancelQueries({ queryKey: currentUserQueryKey })
      await queryClient.fetchQuery({ queryKey: currentUserQueryKey, queryFn: fetchCurrentUser })
      if (typeof window !== "undefined" && typeof Notification !== "undefined") {
        if (Notification.permission === "granted") {
          await softSyncPushSubscription()
        }
      }
    },
    [applyToken, queryClient]
  )

  const logout = useCallback(() => {
    if (typeof window === "undefined") {
      handleUnauthorized()
      return
    }

    void (async () => {
      try {
        await unsubscribePush({ preserveConsent: true })
      } catch (error) {
        console.error("Failed to unsubscribe push subscription on logout", error)
      } finally {
        handleUnauthorized()
      }
    })()
  }, [handleUnauthorized])

  const value = useMemo(
    () => ({ isAuth, login, logout, user, loading, setUser }),
    [isAuth, login, logout, user, loading, setUser]
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
