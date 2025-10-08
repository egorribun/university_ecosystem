import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react"
import { useQueryClient } from "@tanstack/react-query"
import { isAxiosError } from "axios"
import { softSyncPushSubscription, unsubscribePush } from "@/push/subscribe"
import api, { API_UNAUTHORIZED_EVENT, setAuthToken } from "../api/client"

type SetUserArg = any | ((prev: any) => any)

type AuthContextType = {
  isAuth: boolean
  login: (email: string, password: string) => Promise<void>
  logout: () => Promise<void>
  user: any
  loading: boolean
  setUser: (user: SetUserArg) => void
  refresh: () => Promise<void>
}

export const AuthContext = createContext<AuthContextType>({
  isAuth: false,
  login: async () => {},
  logout: async () => {},
  user: null,
  loading: false,
  setUser: () => {},
  refresh: async () => {},
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

type FetchCurrentUserOptions = {
  signal?: AbortSignal
}

export const fetchCurrentUser = async ({ signal }: FetchCurrentUserOptions = {}) => {
  const response = await api.get("/users/me", { signal })
  return response.data
}

export const AuthProvider = ({ children }: { children: ReactNode }) => {
  const queryClient = useQueryClient()
  const cachedUserRef = useRef<any | null>(readCachedUser() ?? null)
  const [token, setToken] = useState<string | null>(() => readStoredToken())
  const [userState, setUserState] = useState<any | null>(cachedUserRef.current)
  const [initializing, setInitializing] = useState<boolean>(
    () => Boolean(cachedUserRef.current || token)
  )
  const [authOperation, setAuthOperation] = useState(false)
  const bootstrapSkipRef = useRef(false)
  const activeRequestRef = useRef<AbortController | null>(null)

  const applyToken = useCallback((value: string | null) => {
    setToken(value)
    setAuthToken(value ?? undefined)
  }, [])

  useEffect(() => {
    setAuthToken(token ?? undefined)
  }, [token])

  const setUser = useCallback(
    (value: SetUserArg) => {
      setUserState((prev) => {
        const previous = prev ?? null
        const next =
          typeof value === "function" ? (value as (prev: any) => any)(previous) : value
        const normalized = next ?? null
        persistUserToCache(normalized)
        queryClient.setQueryData(currentUserQueryKey, normalized)
        return normalized
      })
    },
    [queryClient]
  )

  useEffect(() => {
    if (cachedUserRef.current !== null) {
      queryClient.setQueryData(currentUserQueryKey, cachedUserRef.current)
      cachedUserRef.current = null
    }
  }, [queryClient])

  const clearProfile = useCallback(() => {
    activeRequestRef.current?.abort()
    setUser(null)
    cachedUserRef.current = null
  }, [setUser])

  const handleUnauthorized = useCallback(() => {
    activeRequestRef.current?.abort()
    applyToken(null)
    clearProfile()
    setInitializing(false)
  }, [applyToken, clearProfile])

  useEffect(() => {
    if (!token) {
      clearProfile()
      setInitializing(false)
      return
    }

    if (bootstrapSkipRef.current) {
      bootstrapSkipRef.current = false
      return
    }

    const controller = new AbortController()
    activeRequestRef.current?.abort()
    activeRequestRef.current = controller
    setInitializing(true)

    ;(async () => {
      try {
        const profile = await fetchCurrentUser({ signal: controller.signal })
        setUser(profile ?? null)
      } catch (error) {
        if (controller.signal.aborted) return
        if (isAxiosError(error) && error.response?.status === 401) {
          handleUnauthorized()
          return
        }
        console.error("Failed to fetch current user", error)
      } finally {
        if (!controller.signal.aborted) {
          setInitializing(false)
          if (activeRequestRef.current === controller) {
            activeRequestRef.current = null
          }
        }
      }
    })()

    return () => {
      controller.abort()
    }
  }, [clearProfile, handleUnauthorized, setUser, token])

  const refresh = useCallback(async () => {
    if (!token) {
      clearProfile()
      setInitializing(false)
      return
    }

    const controller = new AbortController()
    activeRequestRef.current?.abort()
    activeRequestRef.current = controller

    try {
      setInitializing(true)
      const profile = await fetchCurrentUser({ signal: controller.signal })
      setUser(profile ?? null)
    } catch (error) {
      if (controller.signal.aborted) return
      if (isAxiosError(error) && error.response?.status === 401) {
        handleUnauthorized()
        return
      }
      throw error
    } finally {
      if (!controller.signal.aborted) {
        setInitializing(false)
        if (activeRequestRef.current === controller) {
          activeRequestRef.current = null
        }
      }
    }
  }, [clearProfile, handleUnauthorized, setUser, token])

  useEffect(() => {
    if (typeof window === "undefined") return
    const onStorage = (event: StorageEvent) => {
      if (event.key === "token") {
        const stored = readStoredToken()
        if (stored) {
          applyToken(stored)
        } else {
          handleUnauthorized()
        }
      }
    }
    window.addEventListener("storage", onStorage)
    return () => window.removeEventListener("storage", onStorage)
  }, [applyToken, handleUnauthorized])

  useEffect(() => {
    if (typeof window === "undefined") return
    const onUnauthorized = () => handleUnauthorized()
    window.addEventListener(API_UNAUTHORIZED_EVENT, onUnauthorized as EventListener)
    return () =>
      window.removeEventListener(API_UNAUTHORIZED_EVENT, onUnauthorized as EventListener)
  }, [handleUnauthorized])

  const login = useCallback(
    async (email: string, password: string) => {
      const payload = new URLSearchParams()
      payload.append("username", email.trim())
      payload.append("password", password)

      const controller = new AbortController()
      activeRequestRef.current?.abort()
      activeRequestRef.current = controller

      try {
        setAuthOperation(true)
        const { data } = await api.post("/auth/login", payload, {
          headers: { "Content-Type": "application/x-www-form-urlencoded" },
          signal: controller.signal,
        })

        const nextToken: string | undefined =
          data?.access_token ?? data?.accessToken ?? data?.token ?? undefined

        if (!nextToken) {
          throw new Error("Не удалось получить токен авторизации")
        }

        bootstrapSkipRef.current = true
        applyToken(nextToken)

        const profile = await fetchCurrentUser({ signal: controller.signal })
        setUser(profile ?? null)

        if (typeof window !== "undefined" && typeof Notification !== "undefined") {
          if (Notification.permission === "granted") {
            try {
              await softSyncPushSubscription()
            } catch (error) {
              console.warn("Failed to sync push subscription", error)
            }
          }
        }
      } catch (error) {
        if (!controller.signal.aborted) {
          handleUnauthorized()
        }

        if (isAxiosError(error)) {
          const message =
            typeof error.response?.data?.detail === "string"
              ? error.response.data.detail
              : "Не удалось войти"
          throw new Error(message)
        }

        if (error instanceof Error) {
          throw error
        }

        throw new Error("Не удалось войти")
      } finally {
        if (!controller.signal.aborted) {
          setAuthOperation(false)
          setInitializing(false)
          if (activeRequestRef.current === controller) {
            activeRequestRef.current = null
          }
        }
      }
    },
    [applyToken, handleUnauthorized, setUser]
  )

  const logout = useCallback(async () => {
    activeRequestRef.current?.abort()
    setAuthOperation(true)

    try {
      await api.post("/auth/logout")
    } catch (error) {
      if (import.meta.env.DEV) {
        console.warn("Logout request failed", error)
      }
    } finally {
      try {
        await unsubscribePush({ preserveConsent: true })
      } catch (error) {
        console.error("Failed to unsubscribe push subscription on logout", error)
      } finally {
        handleUnauthorized()
        setAuthOperation(false)
      }
    }
  }, [handleUnauthorized])

  const user = userState ?? null
  const isAuth = Boolean(token && user)
  const loading = initializing || authOperation

  const value = useMemo(
    () => ({ isAuth, login, logout, user, loading, setUser, refresh }),
    [isAuth, login, logout, user, loading, setUser, refresh]
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
