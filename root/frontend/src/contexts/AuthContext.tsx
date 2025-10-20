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
import { useTranslation } from "react-i18next"
import { hasPushConsent, softSyncPushSubscription, unsubscribePush } from "@/push/subscribe"
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

const PROFILE_CACHE_BASE_KEY = "ecosystem.profile.cache"
const PROFILE_CACHE_SCHEMA_VERSION = 2
export const PROFILE_CACHE_STORAGE_KEY = `${PROFILE_CACHE_BASE_KEY}.v${PROFILE_CACHE_SCHEMA_VERSION}`
const PROFILE_CACHE_VERSION_KEY = `${PROFILE_CACHE_BASE_KEY}.version`
const LEGACY_PROFILE_CACHE_KEYS = ["ecosystem.profile.cache.v1"]
const PROFILE_CACHE_TTL_MS = 5 * 60 * 1000
const PROFILE_CACHE_SIGNING_SALT = "ecosystem-profile-cache-salt"
const PROFILE_BROADCAST_CHANNEL = "ecosystem.profile.sync"

type CachedUserSnapshot = Pick<User, "id" | "full_name" | "avatar_url">

type CachedProfileEnvelope = {
  version: number
  expiresAt: number
  data: CachedUserSnapshot
  signature: string
}

type CacheSignaturePayload = Pick<CachedProfileEnvelope, "version" | "expiresAt" | "data">

type ProfileBroadcastMessage = { type: "unauthorized" }

type HandleUnauthorizedOptions = {
  broadcast?: boolean
  persist?: boolean
}

const encodeBase64 = (value: string): string => {
  if (typeof globalThis === "undefined") return value
  const encoder = globalThis.btoa
  if (typeof encoder !== "function") return value
  try {
    const utf8 = encodeURIComponent(value).replace(/%([0-9A-F]{2})/g, (_, hex) =>
      String.fromCharCode(Number.parseInt(hex, 16))
    )
    return encoder(utf8)
  } catch {
    return value
  }
}

const signSnapshot = (payload: CacheSignaturePayload): string => {
  const json = JSON.stringify(payload)
  return encodeBase64(`${PROFILE_CACHE_SIGNING_SALT}:${json}`)
}

const migrateProfileCache = () => {
  if (typeof localStorage === "undefined") return
  try {
    const storedVersion = localStorage.getItem(PROFILE_CACHE_VERSION_KEY)
    if (storedVersion !== String(PROFILE_CACHE_SCHEMA_VERSION)) {
      for (const legacyKey of LEGACY_PROFILE_CACHE_KEYS) {
        localStorage.removeItem(legacyKey)
      }
      if (storedVersion && storedVersion !== String(PROFILE_CACHE_SCHEMA_VERSION)) {
        localStorage.removeItem(`${PROFILE_CACHE_BASE_KEY}.v${storedVersion}`)
      }
      localStorage.removeItem(PROFILE_CACHE_STORAGE_KEY)
      localStorage.setItem(PROFILE_CACHE_VERSION_KEY, String(PROFILE_CACHE_SCHEMA_VERSION))
    }
  } catch {
    /* ignore */
  }
}

const createOptimisticUser = (snapshot: CachedUserSnapshot): User => ({
  id: snapshot.id,
  email: "",
  full_name: snapshot.full_name,
  role: null,
  group_id: null,
  avatar_url: snapshot.avatar_url,
  cover_url: null,
  about: null,
  record_book_number: null,
  status: null,
  institute: null,
  course: null,
  education_level: null,
  track: null,
  program: null,
  telegram: null,
  achievements: null,
  department: null,
  position: null,
  spotify_connected: false,
  spotify_display_name: null,
  spotify_is_connected: null,
  dnd_enabled: false,
  dnd_start: null,
  dnd_end: null,
  is_active: false,
})

const readCachedUser = (): User | undefined => {
  if (typeof localStorage === "undefined") return undefined
  try {
    const raw = localStorage.getItem(PROFILE_CACHE_STORAGE_KEY)
    if (!raw) return undefined
    const parsed = JSON.parse(raw) as CachedProfileEnvelope | unknown
    if (!parsed || typeof parsed !== "object") return undefined
    const candidate = parsed as Partial<CachedProfileEnvelope>
    if (candidate.version !== PROFILE_CACHE_SCHEMA_VERSION) {
      localStorage.removeItem(PROFILE_CACHE_STORAGE_KEY)
      return undefined
    }
    if (
      typeof candidate.expiresAt !== "number" ||
      !candidate.data ||
      typeof candidate.signature !== "string"
    ) {
      localStorage.removeItem(PROFILE_CACHE_STORAGE_KEY)
      return undefined
    }
    if (candidate.expiresAt <= Date.now()) {
      localStorage.removeItem(PROFILE_CACHE_STORAGE_KEY)
      return undefined
    }
    const payload: CacheSignaturePayload = {
      version: candidate.version,
      expiresAt: candidate.expiresAt,
      data: candidate.data as CachedUserSnapshot,
    }
    const expectedSignature = signSnapshot(payload)
    if (candidate.signature !== expectedSignature) {
      localStorage.removeItem(PROFILE_CACHE_STORAGE_KEY)
      return undefined
    }
    const snapshot = candidate.data as CachedUserSnapshot
    if (!snapshot || typeof snapshot.id !== "number") {
      localStorage.removeItem(PROFILE_CACHE_STORAGE_KEY)
      return undefined
    }
    return createOptimisticUser(snapshot)
  } catch {
    localStorage.removeItem(PROFILE_CACHE_STORAGE_KEY)
    return undefined
  }
}

const persistUserToCache = (value: User | null) => {
  if (typeof localStorage === "undefined") return
  try {
    if (value != null) {
      const snapshot: CachedUserSnapshot = {
        id: value.id,
        full_name: value.full_name,
        avatar_url: value.avatar_url,
      }
      const payload: CacheSignaturePayload = {
        version: PROFILE_CACHE_SCHEMA_VERSION,
        expiresAt: Date.now() + PROFILE_CACHE_TTL_MS,
        data: snapshot,
      }
      const envelope: CachedProfileEnvelope = {
        ...payload,
        signature: signSnapshot(payload),
      }
      localStorage.setItem(PROFILE_CACHE_STORAGE_KEY, JSON.stringify(envelope))
      localStorage.setItem(PROFILE_CACHE_VERSION_KEY, String(PROFILE_CACHE_SCHEMA_VERSION))
    } else {
      localStorage.removeItem(PROFILE_CACHE_STORAGE_KEY)
      localStorage.removeItem(PROFILE_CACHE_VERSION_KEY)
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
  const { t } = useTranslation("auth")
  const [userState, setUserState] = useState<UserState>(initializeCachedUser)
  const cachedUserRef = useRef<UserState>(userState)
  const [initializing, setInitializing] = useState<boolean>(true)
  const [authOperation, setAuthOperation] = useState(false)
  const activeRequestRef = useRef<AbortController | null>(null)

  const broadcastProfileEvent = useCallback((message: ProfileBroadcastMessage) => {
    if (typeof window === "undefined") return
    if (!("BroadcastChannel" in window)) return
    try {
      const channel = new BroadcastChannel(PROFILE_BROADCAST_CHANNEL)
      channel.postMessage(message)
      channel.close()
    } catch (error) {
      if (import.meta.env.DEV) {
        console.warn("Failed to broadcast profile event", error)
      }
    }
  }, [])

  const applyUserState = useCallback(
    (value: SetUserArg, { persist }: { persist: boolean }) => {
      setUserState((prev: UserState) => {
        const next =
          typeof value === "function" ? (value as (prev: UserState) => UserState)(prev) : value
        const normalized: UserState = next ?? null
        if (persist) {
          persistUserToCache(normalized)
        }
        queryClient.setQueryData<UserState>(currentUserQueryKey, normalized)
        return normalized
      })
    },
    [queryClient]
  )

  const setUser = useCallback(
    (value: SetUserArg) => {
      applyUserState(value, { persist: true })
    },
    [applyUserState]
  )

  useEffect(() => {
    if (cachedUserRef.current !== null) {
      queryClient.setQueryData<UserState>(currentUserQueryKey, cachedUserRef.current)
      cachedUserRef.current = null
    }
  }, [queryClient])

  const clearProfile = useCallback(
    ({ persist = true }: { persist?: boolean } = {}) => {
      const controller = activeRequestRef.current
      controller?.abort()
      activeRequestRef.current = null
      applyUserState(() => null, { persist })
      cachedUserRef.current = null
    },
    [applyUserState]
  )

  const handleUnauthorized = useCallback(
    ({ broadcast = true, persist = true }: HandleUnauthorizedOptions = {}) => {
      clearProfile({ persist })
      setAuthOperation(false)
      setInitializing(false)
      if (broadcast) {
        broadcastProfileEvent({ type: "unauthorized" })
      }
    },
    [broadcastProfileEvent, clearProfile]
  )

  useEffect(() => {
    if (typeof window === "undefined") return

    const syncFromCache = () => {
      applyUserState(() => readCachedUser() ?? null, { persist: false })
    }

    const onStorage = (event: StorageEvent) => {
      if (event.key === PROFILE_CACHE_STORAGE_KEY || event.key === PROFILE_CACHE_VERSION_KEY) {
        syncFromCache()
      }
    }

    window.addEventListener("storage", onStorage)

    let channel: BroadcastChannel | null = null

    const onBroadcastMessage = (event: MessageEvent<ProfileBroadcastMessage>) => {
      const { data } = event
      if (!data || typeof data !== "object" || !("type" in data)) {
        return
      }

      if (data.type === "unauthorized") {
        handleUnauthorized({ broadcast: false, persist: false })
      }
    }

    if ("BroadcastChannel" in window) {
      try {
        channel = new BroadcastChannel(PROFILE_BROADCAST_CHANNEL)
        channel.addEventListener("message", onBroadcastMessage as EventListener)
      } catch (error) {
        if (import.meta.env.DEV) {
          console.warn("Failed to subscribe to profile broadcast channel", error)
        }
      }
    }

    return () => {
      window.removeEventListener("storage", onStorage)
      if (channel) {
        channel.removeEventListener("message", onBroadcastMessage as EventListener)
        channel.close()
      }
    }
  }, [applyUserState, handleUnauthorized])

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
    return () => window.removeEventListener(API_UNAUTHORIZED_EVENT, onUnauthorized as EventListener)
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
    return () => window.removeEventListener(SPOTIFY_REAUTH_EVENT, onSpotifyReauth as EventListener)
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
              : t("login.error")
          throw new Error(message)
        }

        if (error instanceof Error) {
          throw error
        }

        throw new Error(t("login.error"))
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
    [handleUnauthorized, setUser, t]
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
