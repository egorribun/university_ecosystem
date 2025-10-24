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
import type { TFunction } from "i18next"
import { hmac } from "@noble/hashes/hmac"
import { sha256 } from "@noble/hashes/sha256"
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
const PROFILE_BROADCAST_CHANNEL = "ecosystem.profile.sync"
const PROFILE_CACHE_HEADER = "X-Profile-Cache-Envelope"
const SESSION_SIGNING_KEY_STORAGE_KEY = `${PROFILE_CACHE_BASE_KEY}.sessionKey`

type CachedUserSnapshot = Pick<User, "id" | "full_name" | "avatar_url">

type CachedProfileEnvelope = {
  version: number
  expiresAt: number
  data: CachedUserSnapshot
  signature: string
}

type CacheSignaturePayload = Pick<CachedProfileEnvelope, "version" | "expiresAt" | "data">

type SessionSigningKeyResponse = {
  signing_key: string
}

type ProfileBroadcastMessage = { type: "unauthorized" }

type HandleUnauthorizedOptions = {
  broadcast?: boolean
  persist?: boolean
}

const formatLockoutDuration = (
  seconds: number | null | undefined,
  t: TFunction<"auth">
): string | null => {
  if (typeof seconds !== "number" || !Number.isFinite(seconds) || seconds <= 0) {
    return null
  }

  if (seconds < 60) {
    const value = Math.max(1, Math.ceil(seconds))
    return t("login.duration.seconds", { count: value })
  }

  if (seconds < 3600) {
    const value = Math.max(1, Math.ceil(seconds / 60))
    return t("login.duration.minutes", { count: value })
  }

  const value = Math.max(1, Math.ceil(seconds / 3600))
  return t("login.duration.hours", { count: value })
}

const bytesToBase64 = (bytes: Uint8Array): string => {
  const maybeBuffer =
    typeof globalThis !== "undefined" &&
    typeof (globalThis as { Buffer?: unknown }).Buffer === "function"
      ? (globalThis as { Buffer?: { from?: unknown } }).Buffer
      : undefined

  if (
    maybeBuffer &&
    typeof maybeBuffer === "function" &&
    typeof (maybeBuffer as { from?: unknown }).from === "function"
  ) {
    return (
      maybeBuffer as {
        from: (
          input: Uint8Array | string,
          encoding?: string
        ) => {
          toString: (encoding: string) => string
        }
      }
    )
      .from(bytes)
      .toString("base64")
  }

  let binary = ""
  for (const byte of bytes) {
    binary += String.fromCharCode(byte)
  }

  if (typeof globalThis !== "undefined" && typeof globalThis.btoa === "function") {
    return globalThis.btoa(binary)
  }

  if (
    maybeBuffer &&
    typeof maybeBuffer === "function" &&
    typeof (maybeBuffer as { from?: unknown }).from === "function"
  ) {
    return (
      maybeBuffer as {
        from: (
          input: Uint8Array | string,
          encoding?: string
        ) => {
          toString: (encoding: string) => string
        }
      }
    )
      .from(binary, "binary")
      .toString("base64")
  }

  return binary
}

const utf8 = new TextEncoder()

const signSnapshot = (payload: CacheSignaturePayload, key: string): string => {
  const json = JSON.stringify(payload)
  const signature = hmac(sha256, utf8.encode(key), utf8.encode(json))
  return bytesToBase64(signature)
}

const readStoredSessionSigningKey = (): string | null => {
  if (typeof sessionStorage === "undefined") return null
  try {
    return sessionStorage.getItem(SESSION_SIGNING_KEY_STORAGE_KEY)
  } catch {
    return null
  }
}

const persistSessionSigningKey = (value: string | null) => {
  if (typeof sessionStorage === "undefined") return
  try {
    if (value) {
      sessionStorage.setItem(SESSION_SIGNING_KEY_STORAGE_KEY, value)
    } else {
      sessionStorage.removeItem(SESSION_SIGNING_KEY_STORAGE_KEY)
    }
  } catch {
    /* ignore */
  }
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

const clearProfileCacheStorage = () => {
  if (typeof localStorage === "undefined") return
  try {
    localStorage.removeItem(PROFILE_CACHE_STORAGE_KEY)
    localStorage.removeItem(PROFILE_CACHE_VERSION_KEY)
  } catch {
    /* ignore */
  }
}

const readCachedEnvelope = (): CachedProfileEnvelope | undefined => {
  if (typeof localStorage === "undefined") return undefined
  try {
    const raw = localStorage.getItem(PROFILE_CACHE_STORAGE_KEY)
    if (!raw) return undefined
    const parsed = JSON.parse(raw) as unknown
    if (!parsed || typeof parsed !== "object") return undefined
    return parsed as CachedProfileEnvelope
  } catch {
    clearProfileCacheStorage()
    return undefined
  }
}

const getCachedEnvelopeHeader = (): string | null => {
  if (typeof localStorage === "undefined") return null
  try {
    return localStorage.getItem(PROFILE_CACHE_STORAGE_KEY)
  } catch {
    return null
  }
}

const readCachedUser = (signingKey: string | null): User | undefined => {
  if (!signingKey) {
    clearProfileCacheStorage()
    return undefined
  }
  const candidate = readCachedEnvelope()
  if (!candidate) return undefined
  if (candidate.version !== PROFILE_CACHE_SCHEMA_VERSION) {
    clearProfileCacheStorage()
    return undefined
  }
  if (
    typeof candidate.expiresAt !== "number" ||
    !candidate.data ||
    typeof candidate.signature !== "string"
  ) {
    clearProfileCacheStorage()
    return undefined
  }
  if (candidate.expiresAt <= Date.now()) {
    clearProfileCacheStorage()
    return undefined
  }
  const payload: CacheSignaturePayload = {
    version: candidate.version,
    expiresAt: candidate.expiresAt,
    data: candidate.data as CachedUserSnapshot,
  }
  const expectedSignature = signSnapshot(payload, signingKey)
  if (candidate.signature !== expectedSignature) {
    clearProfileCacheStorage()
    return undefined
  }
  const snapshot = candidate.data as CachedUserSnapshot
  if (!snapshot || typeof snapshot.id !== "number") {
    clearProfileCacheStorage()
    return undefined
  }
  return createOptimisticUser(snapshot)
}

const persistUserToCache = (value: User | null, signingKey: string | null) => {
  if (typeof localStorage === "undefined") return
  try {
    if (value != null && signingKey) {
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
        signature: signSnapshot(payload, signingKey),
      }
      localStorage.setItem(PROFILE_CACHE_STORAGE_KEY, JSON.stringify(envelope))
      localStorage.setItem(PROFILE_CACHE_VERSION_KEY, String(PROFILE_CACHE_SCHEMA_VERSION))
    } else {
      clearProfileCacheStorage()
    }
  } catch {
    /* ignore */
  }
}

type FetchCurrentUserOptions = {
  signal?: AbortSignal
}

export const fetchCurrentUser = async ({ signal }: FetchCurrentUserOptions = {}) => {
  const cachedEnvelope = getCachedEnvelopeHeader()
  let headers: Record<string, string> | undefined
  if (cachedEnvelope) {
    if (/^[\x00-\x7F]*$/.test(cachedEnvelope)) {
      headers = { [PROFILE_CACHE_HEADER]: cachedEnvelope }
    } else {
      clearProfileCacheStorage()
    }
  }
  try {
    const response = await api.get<User>("/users/me", { signal, headers })
    return response.data
  } catch (error) {
    if (
      cachedEnvelope &&
      isAxiosError(error) &&
      error.response?.status === 400 &&
      !signal?.aborted
    ) {
      clearProfileCacheStorage()
      const retry = await api.get<User>("/users/me", { signal })
      return retry.data
    }
    throw error
  }
}

const initializeCachedUser = (): UserState => {
  if (typeof window === "undefined") return null
  migrateProfileCache()
  const signingKey = readStoredSessionSigningKey()
  return readCachedUser(signingKey) ?? null
}

export const AuthProvider = ({ children }: { children: ReactNode }) => {
  const queryClient = useQueryClient()
  const { t } = useTranslation("auth")
  const [sessionSigningKey, setSessionSigningKeyState] = useState<string | null>(() =>
    readStoredSessionSigningKey()
  )
  const [userState, setUserState] = useState<UserState>(initializeCachedUser)
  const cachedUserRef = useRef<UserState>(userState)
  const sessionSigningKeyRef = useRef<string | null>(sessionSigningKey)
  const sessionSigningKeyPromiseRef = useRef<Promise<string | null> | null>(null)
  const [initializing, setInitializing] = useState<boolean>(true)
  const [authOperation, setAuthOperation] = useState(false)
  const activeRequestRef = useRef<AbortController | null>(null)

  const updateSessionSigningKey = useCallback((value: string | null) => {
    sessionSigningKeyRef.current = value
    setSessionSigningKeyState(value)
    persistSessionSigningKey(value)
  }, [])

  const ensureSessionSigningKey = useCallback(async () => {
    if (sessionSigningKeyRef.current) {
      return sessionSigningKeyRef.current
    }
    if (sessionSigningKeyPromiseRef.current) {
      return sessionSigningKeyPromiseRef.current
    }
    const promise = (async () => {
      try {
        const response = await api.get<SessionSigningKeyResponse>("/auth/session/signing-key")
        const key = response.data.signing_key
        updateSessionSigningKey(key)
        return key
      } finally {
        sessionSigningKeyPromiseRef.current = null
      }
    })()
    sessionSigningKeyPromiseRef.current = promise
    return promise
  }, [updateSessionSigningKey])

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
          persistUserToCache(normalized, sessionSigningKeyRef.current)
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
    if (sessionSigningKeyRef.current !== sessionSigningKey) {
      sessionSigningKeyRef.current = sessionSigningKey
    }
    if (sessionSigningKey && userState) {
      persistUserToCache(userState, sessionSigningKey)
    }
  }, [sessionSigningKey, userState])

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
      sessionSigningKeyPromiseRef.current = null
      updateSessionSigningKey(null)
      clearProfile({ persist })
      setAuthOperation(false)
      setInitializing(false)
      if (broadcast) {
        broadcastProfileEvent({ type: "unauthorized" })
      }
    },
    [broadcastProfileEvent, clearProfile, updateSessionSigningKey]
  )

  useEffect(() => {
    if (typeof window === "undefined") return

    const syncFromCache = () => {
      applyUserState(() => readCachedUser(sessionSigningKeyRef.current) ?? null, { persist: false })
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
        try {
          await ensureSessionSigningKey()
        } catch (error) {
          if (!controller.signal.aborted && import.meta.env.DEV) {
            console.warn("Failed to obtain session signing key", error)
          }
        }
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
  }, [ensureSessionSigningKey, handleUnauthorized, setUser])

  const refresh = useCallback(async () => {
    const controller = new AbortController()
    activeRequestRef.current?.abort()
    activeRequestRef.current = controller

    try {
      setInitializing(true)
      const profile = await fetchCurrentUser({ signal: controller.signal })
      try {
        await ensureSessionSigningKey()
      } catch (error) {
        if (!controller.signal.aborted && import.meta.env.DEV) {
          console.warn("Failed to obtain session signing key", error)
        }
      }
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
  }, [ensureSessionSigningKey, handleUnauthorized, setUser])

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

        const signingKeyPromise = ensureSessionSigningKey()
        const profile = await fetchCurrentUser({ signal: controller.signal })
        try {
          await signingKeyPromise
        } catch (error) {
          if (!controller.signal.aborted && import.meta.env.DEV) {
            console.warn("Failed to obtain session signing key", error)
          }
        }
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
          if (error.response?.status === 423) {
            const retryAfterHeader = error.response.headers?.["retry-after"]
            const retryValue = Array.isArray(retryAfterHeader)
              ? retryAfterHeader[0]
              : retryAfterHeader
            const parsedSeconds =
              typeof retryValue === "string" ? Number.parseInt(retryValue, 10) : Number.NaN

            let detail =
              typeof error.response.data?.detail === "string"
                ? error.response.data.detail
                : t("login.locked")

            const durationText = formatLockoutDuration(parsedSeconds, t)
            if (durationText) {
              const retryText = t("login.lockedRetry", { duration: durationText })
              if (!detail.includes(retryText)) {
                detail = `${detail} ${retryText}`.trim()
              }
            }

            throw new Error(detail)
          }

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
    [ensureSessionSigningKey, handleUnauthorized, setUser, t]
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
