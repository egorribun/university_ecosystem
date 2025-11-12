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
import type { components } from "@/api/generated/schema"
import { SPOTIFY_REAUTH_EVENT } from "@/hooks/useNowPlaying"
import type { PendingMfaResponse, MfaMethod, MfaVerifyPayload } from "@/types/Mfa"
import type { User } from "@/types/User"

type UserState = User | null

type SetUserArg = SetStateAction<UserState>

export type PendingMfaState = PendingMfaResponse & { reason: "login" | "step-up" }

export type SubmitMfaChallengePayload =
  | {
      method: Extract<MfaMethod, "totp" | "recovery">
      code: string
      challengeToken?: string
    }
  | {
      method: Extract<MfaMethod, "webauthn">
      credential: Record<string, unknown>
      challengeToken?: string
    }

type AuthContextType = {
  isAuth: boolean
  login: (email: string, password: string) => Promise<PendingMfaState | null>
  logout: () => Promise<void>
  user: UserState
  loading: boolean
  setUser: Dispatch<SetUserArg>
  refresh: () => Promise<void>
  pendingMfa: PendingMfaState | null
  submitMfaChallenge: (payload: SubmitMfaChallengePayload) => Promise<void>
  requireMfa: () => Promise<PendingMfaState | null>
}

const noopSetUser: Dispatch<SetUserArg> = (_value) => {
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

const isAscii = (value: string) => {
  for (let index = 0; index < value.length; index += 1) {
    if (value.charCodeAt(index) > 0x7f) {
      return false
    }
  }

  return true
}

type CachedUserSnapshot = Pick<User, "id" | "full_name" | "avatar_url"> &
  Partial<
    Pick<
      User,
      | "mfa_required"
      | "mfa_default_method"
      | "mfa_last_verified_at"
      | "mfa_recovery_codes_generated_at"
    >
  >

type CachedProfileEnvelope = {
  version: number
  expiresAt: number
  data: CachedUserSnapshot
  signature: string
}

type CacheSignaturePayload = Pick<CachedProfileEnvelope, "version" | "expiresAt" | "data">

type SessionSigningKeyResponse = components["schemas"]["SessionSigningKeyOut"]

type TokenWithProfileResponse = {
  access_token: string
  token_type: string
  user?: User
  session?: SessionSigningKeyResponse | null
}

const extractSigningKey = (value: TokenWithProfileResponse | undefined | null): string | null => {
  if (!value) return null
  const key = value.session?.signing_key
  return typeof key === "string" && key.length > 0 ? key : null
}

const isTokenWithProfileResponse = (
  value: unknown
): value is TokenWithProfileResponse & { user: User } => {
  if (!value || typeof value !== "object") {
    return false
  }
  const candidate = value as Record<string, unknown>
  if (typeof candidate.access_token !== "string") {
    return false
  }
  if (!candidate.user || typeof candidate.user !== "object") {
    return false
  }
  return true
}

type ProfileBroadcastMessage =
  | { type: "unauthorized" }
  | { type: "mfa-pending"; payload: PendingMfaState }
  | { type: "mfa-cleared" }

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
  role: "student",
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
  mfa_required: Boolean(snapshot.mfa_required),
  mfa_default_method: snapshot.mfa_default_method ?? null,
  mfa_last_verified_at: snapshot.mfa_last_verified_at ?? null,
  mfa_recovery_codes_generated_at: snapshot.mfa_recovery_codes_generated_at ?? null,
  totp_enrollments: [],
  webauthn_credentials: [],
  recovery_codes: [],
  mfa_challenges: [],
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
        mfa_required: value.mfa_required,
        mfa_default_method: value.mfa_default_method,
        mfa_last_verified_at: value.mfa_last_verified_at,
        mfa_recovery_codes_generated_at: value.mfa_recovery_codes_generated_at,
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
    if (isAscii(cachedEnvelope)) {
      headers = { [PROFILE_CACHE_HEADER]: cachedEnvelope }
    } else {
      clearProfileCacheStorage()
    }
  }
  try {
    const response = await api.get<User>("/users/me", {
      signal,
      headers,
      skipRateLimitQueue: true,
    })
    return response.data
  } catch (error) {
    if (
      cachedEnvelope &&
      isAxiosError(error) &&
      error.response?.status === 400 &&
      !signal?.aborted
    ) {
      clearProfileCacheStorage()
      const retry = await api.get<User>("/users/me", {
        signal,
        skipRateLimitQueue: true,
      })
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
  const [pendingMfaState, setPendingMfaState] = useState<PendingMfaState | null>(null)
  const cachedUserRef = useRef<UserState>(userState)
  const userStateRef = useRef<UserState>(userState)
  const sessionSigningKeyRef = useRef<string | null>(sessionSigningKey)
  const sessionSigningKeyPromiseRef = useRef<Promise<string | null> | null>(null)
  const pendingMfaRef = useRef<PendingMfaState | null>(pendingMfaState)
  const [initializing, setInitializing] = useState<boolean>(() => userState == null)
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
        const response = await api.get<SessionSigningKeyResponse>("/auth/session/signing-key", {
          skipRateLimitQueue: true,
        })
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

  const updatePendingMfa = useCallback(
    (value: PendingMfaState | null, { broadcast = true }: { broadcast?: boolean } = {}) => {
      const previous = pendingMfaRef.current
      pendingMfaRef.current = value
      setPendingMfaState(value)
      if (!broadcast) return
      if (!previous && !value) return
      if (value) {
        broadcastProfileEvent({ type: "mfa-pending", payload: value })
      } else {
        broadcastProfileEvent({ type: "mfa-cleared" })
      }
    },
    [broadcastProfileEvent]
  )

  const applyUserState = useCallback(
    (value: SetUserArg, { persist }: { persist: boolean }) => {
      setUserState((prev: UserState) => {
        const next =
          typeof value === "function" ? (value as (prev: UserState) => UserState)(prev) : value
        const normalized: UserState = next ?? null
        userStateRef.current = normalized
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
      updatePendingMfa(null, { broadcast })
      setAuthOperation(false)
      setInitializing(false)
      if (broadcast) {
        broadcastProfileEvent({ type: "unauthorized" })
      }
    },
    [broadcastProfileEvent, clearProfile, updatePendingMfa, updateSessionSigningKey]
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
        return
      }

      if (data.type === "mfa-pending" && data.payload) {
        updatePendingMfa(data.payload, { broadcast: false })
        return
      }

      if (data.type === "mfa-cleared") {
        updatePendingMfa(null, { broadcast: false })
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
  }, [applyUserState, handleUnauthorized, updatePendingMfa])

  useEffect(() => {
    if (typeof window === "undefined") {
      setInitializing(false)
      return
    }

    const controller = new AbortController()
    activeRequestRef.current?.abort()
    activeRequestRef.current = controller
    if (userStateRef.current == null) {
      setInitializing(true)
    }
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
        if (controller.signal.aborted) return null
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
    if (pendingMfaRef.current) {
      return
    }
    const controller = new AbortController()
    activeRequestRef.current?.abort()
    activeRequestRef.current = controller

    try {
      if (userStateRef.current == null) {
        setInitializing(true)
      }
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
  }, [ensureSessionSigningKey, handleUnauthorized, pendingMfaRef, setUser])

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

  const finalizeAuthenticatedSession = useCallback(
    async (
      controller: AbortController,
      {
        skipPushSync = false,
        profile,
        signingKey,
      }: {
        skipPushSync?: boolean
        profile?: User | null
        signingKey?: string | null
      } = {}
    ) => {
      let resolvedProfile: User | null = profile ?? null
      let signingKeyPromise: Promise<string | null> | null = null

      if (typeof signingKey === "string" && signingKey.length > 0) {
        updateSessionSigningKey(signingKey)
      } else {
        signingKeyPromise = ensureSessionSigningKey()
      }

      if (!resolvedProfile) {
        resolvedProfile = await fetchCurrentUser({ signal: controller.signal })
      }

      if (signingKeyPromise) {
        try {
          await signingKeyPromise
        } catch (error) {
          if (!controller.signal.aborted && import.meta.env.DEV) {
            console.warn("Failed to obtain session signing key", error)
          }
        }
      }

      if (controller.signal.aborted) {
        return
      }

      if (resolvedProfile) {
        setUser(resolvedProfile)
      }

      if (!skipPushSync && typeof window !== "undefined" && typeof Notification !== "undefined") {
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
    },
    [ensureSessionSigningKey, setUser, updateSessionSigningKey]
  )

  const login = useCallback(
    async (email: string, password: string): Promise<PendingMfaState | null> => {
      const payload = new URLSearchParams()
      payload.append("username", email.trim())
      payload.append("password", password)

      const controller = new AbortController()
      activeRequestRef.current?.abort()
      activeRequestRef.current = controller

      try {
        setAuthOperation(true)
        setInitializing(true)
        const response = await api.post<PendingMfaResponse | TokenWithProfileResponse>(
          "/auth/login",
          payload,
          {
            headers: { "Content-Type": "application/x-www-form-urlencoded" },
            signal: controller.signal,
          }
        )

        if (controller.signal.aborted) return null

        if (response.status === 202) {
          const data = response.data as PendingMfaResponse
          const challenge: PendingMfaState = { ...data, reason: "login" }
          updatePendingMfa(challenge)
          return challenge
        }

        updatePendingMfa(null)
        if (isTokenWithProfileResponse(response.data)) {
          const success = response.data
          await finalizeAuthenticatedSession(controller, {
            profile: success.user,
            signingKey: extractSigningKey(success),
          })
        } else {
          await finalizeAuthenticatedSession(controller)
        }
        return null
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
    [finalizeAuthenticatedSession, handleUnauthorized, t, updatePendingMfa]
  )

  const submitMfaChallenge = useCallback(
    async (payload: SubmitMfaChallengePayload) => {
      const pending = pendingMfaRef.current
      if (!pending) {
        throw new Error(t("login.error"))
      }

      const controller = new AbortController()
      activeRequestRef.current?.abort()
      activeRequestRef.current = controller

      const shouldToggleInitializing = pending.reason === "login"

      try {
        setAuthOperation(true)
        if (shouldToggleInitializing) {
          setInitializing(true)
        }

        const token =
          payload.challengeToken ??
          pending.methods.find((entry) => entry.method === (payload.method as MfaMethod))
            ?.challenge_token

        if (!token) {
          throw new Error(t("login.error"))
        }

        let requestPayload: MfaVerifyPayload
        if (payload.method === "webauthn") {
          requestPayload = {
            method: payload.method,
            challenge_token: token,
            credential: payload.credential,
          }
        } else {
          requestPayload = {
            method: payload.method,
            challenge_token: token,
            code: payload.code,
          }
        }

        const skipPushSync = Boolean(pending.session_id)
        const response = await api.post<TokenWithProfileResponse | undefined>(
          "/auth/mfa/verify",
          requestPayload,
          { signal: controller.signal }
        )

        if (controller.signal.aborted) {
          return
        }

        updatePendingMfa(null)
        if (isTokenWithProfileResponse(response.data)) {
          const success = response.data
          await finalizeAuthenticatedSession(controller, {
            skipPushSync,
            profile: success.user,
            signingKey: extractSigningKey(success),
          })
        } else {
          await finalizeAuthenticatedSession(controller, {
            skipPushSync,
          })
        }
      } catch (error) {
        if (controller.signal.aborted) {
          return
        }

        if (isAxiosError(error)) {
          if (error.response?.status === 401) {
            handleUnauthorized()
            return
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
        if (shouldToggleInitializing && !controller.signal.aborted) {
          setInitializing(false)
        }
      }
    },
    [finalizeAuthenticatedSession, handleUnauthorized, pendingMfaRef, t, updatePendingMfa]
  )

  const requireMfa = useCallback(async (): Promise<PendingMfaState | null> => {
    const controller = new AbortController()
    activeRequestRef.current?.abort()
    activeRequestRef.current = controller

    try {
      const response = await api.post<PendingMfaResponse>("/auth/mfa/step-up", undefined, {
        signal: controller.signal,
      })

      if (controller.signal.aborted) {
        return null
      }

      if (response.status === 202) {
        const challenge: PendingMfaState = { ...response.data, reason: "step-up" }
        updatePendingMfa(challenge)
        return challenge
      }

      updatePendingMfa(null)
      return null
    } catch (error) {
      if (controller.signal.aborted) {
        return null
      }

      if (isAxiosError(error)) {
        if (error.response?.status === 401) {
          handleUnauthorized()
          return null
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
    }
  }, [handleUnauthorized, t, updatePendingMfa])

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
  const pendingMfa = pendingMfaState

  const value = useMemo(
    () => ({
      isAuth,
      login,
      logout,
      user,
      loading,
      setUser,
      refresh,
      pendingMfa,
      submitMfaChallenge,
      requireMfa,
    }),
    [
      isAuth,
      login,
      logout,
      user,
      loading,
      setUser,
      refresh,
      pendingMfa,
      submitMfaChallenge,
      requireMfa,
    ]
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
