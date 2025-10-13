import {
  createContext,
  type Dispatch,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
  type SetStateAction,
} from "react"
import { useQueryClient } from "@tanstack/react-query"
import { isAxiosError } from "axios"
import {
  hasPushConsent,
  softSyncPushSubscription,
  unsubscribePush,
} from "@/push/subscribe"
import api, { API_UNAUTHORIZED_EVENT } from "../api/client"
import { SPOTIFY_REAUTH_EVENT } from "@/hooks/useNowPlaying"
import type { User } from "@/types/User"

type UserState = User | null

type SetUserArg = SetStateAction<UserState>

type AuthContextType = {
  isAuth: boolean
  login: (email: string, password: string) => Promise<void>
  logout: () => Promise<void>
  user: UserState
  loading: boolean
  setUser: Dispatch<SetUserArg>
  refresh: () => Promise<void>
}

const noopSetUser: Dispatch<SetUserArg> = (_value) => {
  if (import.meta.env.DEV) {
    console.warn("AuthContext setUser called outside provider")
  }
}

export const AuthContext = createContext<AuthContextType>({
  isAuth: false,
  login: async () => {},
  logout: async () => {},
  user: null,
  loading: false,
  setUser: noopSetUser,
  refresh: async () => {},
})

export const useAuth = () => useContext(AuthContext)

export const currentUserQueryKey = ["users", "me"] as const

const PROFILE_CACHE_KEY = "ecosystem.profile.cache.v1"
const PROFILE_CACHE_MIGRATION_KEY = `${PROFILE_CACHE_KEY}:cookie-auth`

const isUser = (value: unknown): value is User => {
  if (!value || typeof value !== "object") return false
  const candidate = value as Partial<User>
  return typeof candidate.id === "number" && typeof candidate.email === "string"
}

const migrateProfileCache = () => {
  if (typeof localStorage === "undefined") return
  try {
    const migrated = localStorage.getItem(PROFILE_CACHE_MIGRATION_KEY)
    if (!migrated) {
      localStorage.removeItem(PROFILE_CACHE_KEY)
      localStorage.setItem(PROFILE_CACHE_MIGRATION_KEY, new Date().toISOString())
    }
  } catch {
    /* ignore */
  }
}

const readCachedUser = (): User | undefined => {
  if (typeof localStorage === "undefined") return undefined
  try {
    const raw = localStorage.getItem(PROFILE_CACHE_KEY)
    if (!raw) return undefined
    const parsed = JSON.parse(raw) as unknown
    if (parsed && typeof parsed === "object" && "data" in parsed) {
      const data = (parsed as { data: unknown }).data
      return isUser(data) ? data : undefined
    }
    return isUser(parsed) ? parsed : undefined
  } catch {
    return undefined
  }
}

const persistUserToCache = (value: User | null) => {
  if (typeof localStorage === "undefined") return
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

type FetchCurrentUserOptions = {
  signal?: AbortSignal
}

export const fetchCurrentUser = async ({ signal }: FetchCurrentUserOptions = {}) => {
  const response = await api.get<User>("/users/me", { signal })
  return response.data
}

const initializeCachedUser = (): UserState => {
  if (typeof window === "undefined") return null
  migrateProfileCache()
  return readCachedUser() ?? null
}

export const AuthProvider = ({ children }: { children: ReactNode }) => {
  const queryClient = useQueryClient()
  const [userState, setUserState] = useState<UserState>(initializeCachedUser)
  const cachedUserRef = useRef<UserState>(userState)
  const [initializing, setInitializing] = useState<boolean>(true)
  const [authOperation, setAuthOperation] = useState(false)
  const activeRequestRef = useRef<AbortController | null>(null)

  const setUser = useCallback(
    (value: SetUserArg) => {
      setUserState((prev: UserState) => {
        const next =
          typeof value === "function"
            ? (value as (prev: UserState) => UserState)(prev)
            : value
        const normalized: UserState = next ?? null
        persistUserToCache(normalized)
        queryClient.setQueryData<UserState>(currentUserQueryKey, normalized)
        return normalized
      })
    },
    [queryClient]
  )

  useEffect(() => {
    if (cachedUserRef.current !== null) {
      queryClient.setQueryData<UserState>(currentUserQueryKey, cachedUserRef.current)
      cachedUserRef.current = null
    }
  }, [queryClient])

  const clearProfile = useCallback(() => {
    const controller = activeRequestRef.current
    controller?.abort()
    activeRequestRef.current = null
    setUser(null)
    cachedUserRef.current = null
  }, [setUser])

  const handleUnauthorized = useCallback(() => {
    clearProfile()
    setAuthOperation(false)
    setInitializing(false)
  }, [clearProfile])

  useEffect(() => {
    if (typeof window === "undefined") {
      setInitializing(false)
      return
    }

    const controller = new AbortController()
    activeRequestRef.current?.abort()
    activeRequestRef.current = controller
    setInitializing(true)

    ;(async () => {
      try {
        const profile = await fetchCurrentUser({ signal: controller.signal })
        setUser(profile)
      } catch (error) {
        if (controller.signal.aborted) return
        if (isAxiosError(error) && error.response?.status === 401) {
          handleUnauthorized()
          return
        }
        console.error("Failed to fetch current user", error)
      } finally {
        if (!controller.signal.aborted && activeRequestRef.current === controller) {
          activeRequestRef.current = null
        }
        if (!controller.signal.aborted) {
          setInitializing(false)
        }
      }
    })()

    return () => {
      controller.abort()
    }
  }, [handleUnauthorized, setUser])

  const refresh = useCallback(async () => {
    const controller = new AbortController()
    activeRequestRef.current?.abort()
    activeRequestRef.current = controller

    try {
      setInitializing(true)
      const profile = await fetchCurrentUser({ signal: controller.signal })
      setUser(profile)
    } catch (error) {
      if (controller.signal.aborted) return
      if (isAxiosError(error) && error.response?.status === 401) {
        handleUnauthorized()
        return
      }
      throw error
    } finally {
      if (!controller.signal.aborted && activeRequestRef.current === controller) {
        activeRequestRef.current = null
      }
      if (!controller.signal.aborted) {
        setInitializing(false)
      }
    }
  }, [handleUnauthorized, setUser])

  useEffect(() => {
    if (typeof window === "undefined") return
    const onUnauthorized = () => handleUnauthorized()
    window.addEventListener(API_UNAUTHORIZED_EVENT, onUnauthorized as EventListener)
    return () =>
      window.removeEventListener(API_UNAUTHORIZED_EVENT, onUnauthorized as EventListener)
  }, [handleUnauthorized])

  useEffect(() => {
    if (typeof window === "undefined") return
    const onSpotifyReauth = () => {
      setUser((prev: UserState) => {
        if (!prev) return prev
        if (!prev.spotify_connected && !prev.spotify_is_connected) return prev
        return {
          ...prev,
          spotify_connected: false,
          spotify_is_connected: false,
          spotify_display_name: null,
        }
      })
      void queryClient.invalidateQueries({ queryKey: currentUserQueryKey })
    }
    window.addEventListener(SPOTIFY_REAUTH_EVENT, onSpotifyReauth as EventListener)
    return () =>
      window.removeEventListener(SPOTIFY_REAUTH_EVENT, onSpotifyReauth as EventListener)
  }, [queryClient, setUser])

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
        setInitializing(true)
        await api.post("/auth/login", payload, {
          headers: { "Content-Type": "application/x-www-form-urlencoded" },
          signal: controller.signal,
        })

        if (controller.signal.aborted) return

        const profile = await fetchCurrentUser({ signal: controller.signal })
        setUser(profile)

        if (typeof window !== "undefined" && typeof Notification !== "undefined") {
          if (Notification.permission === "granted" && hasPushConsent()) {
            void (async () => {
              try {
                await softSyncPushSubscription()
              } catch (error) {
                console.warn("Failed to sync push subscription", error)
              }
            })()
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
        if (activeRequestRef.current === controller) {
          activeRequestRef.current = null
        }
        setAuthOperation(false)
        if (!controller.signal.aborted) {
          setInitializing(false)
        }
      }
    },
    [handleUnauthorized, setUser]
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
        await unsubscribePush({ preserveConsent: true, preserveTopics: true })
      } catch (error) {
        console.error("Failed to unsubscribe push subscription on logout", error)
      } finally {
        handleUnauthorized()
        setAuthOperation(false)
      }
    }
  }, [handleUnauthorized])

  const user = userState
  const isAuth = Boolean(user)
  const loading = initializing || authOperation

  const value = useMemo(
    () => ({ isAuth, login, logout, user, loading, setUser, refresh }),
    [isAuth, login, logout, user, loading, setUser, refresh]
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
