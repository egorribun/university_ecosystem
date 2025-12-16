import { useCallback, useEffect, useRef, useState } from "react"
import { useQueryClient } from "@tanstack/react-query"
import { isAxiosError } from "axios"
import CryptoJS from "crypto-js"

import api, { resetEtagCache } from "@/api/client"
import type { User } from "@/types/User"
import { signSnapshot } from "./useSessionCrypto"
import type { PendingMfaState, SetUserArg, UserState } from "@/types/Auth"

const PROFILE_CACHE_BASE_KEY = "ecosystem.profile.cache"
const PROFILE_CACHE_SCHEMA_VERSION = 2
export const PROFILE_CACHE_STORAGE_KEY = `${PROFILE_CACHE_BASE_KEY}.v${PROFILE_CACHE_SCHEMA_VERSION}`
const PROFILE_CACHE_VERSION_KEY = `${PROFILE_CACHE_BASE_KEY}.version`
const LEGACY_PROFILE_CACHE_KEYS = ["ecosystem.profile.cache.v1"]
const PROFILE_CACHE_TTL_MS = 5 * 60 * 1000
const PROFILE_BROADCAST_CHANNEL = "ecosystem.profile.sync"
const PROFILE_CACHE_HEADER = "X-Profile-Cache-Envelope"

export const currentUserQueryKey = ["users", "me"] as const

type CachedUserSnapshot = Pick<User, "id" | "full_name" | "avatar_url"> &
  Partial<Pick<User, "mfa_required" | "mfa_default_method" | "mfa_last_verified_at">>

type CachedProfileEnvelope = {
  version: number
  expiresAt: number
  data: CachedUserSnapshot | string // Can be encrypted string or plain object
  signature: string
}

type CacheSignaturePayload = Pick<CachedProfileEnvelope, "version" | "expiresAt" | "data">

type ProfileBroadcastMessage =
  | { type: "unauthorized" }
  | { type: "mfa-pending"; payload: PendingMfaState }
  | { type: "mfa-cleared" }

type HandleUnauthorizedOptions = {
  broadcast?: boolean
  persist?: boolean
}

const isAscii = (value: string) => {
  for (let index = 0; index < value.length; index += 1) {
    if (value.charCodeAt(index) > 0x7f) {
      return false
    }
  }

  return true
}

const areDeepEqual = (a: unknown, b: unknown): boolean => {
  if (a === b) return true
  if (typeof a !== "object" || a === null || typeof b !== "object" || b === null) return false
  const keysA = Object.keys(a)
  const keysB = Object.keys(b)
  if (keysA.length !== keysB.length) return false
  for (const key of keysA) {
    if (!keysB.includes(key)) return false
    if (!areDeepEqual((a as any)[key], (b as any)[key])) return false
  }
  return true
}

const debugDeepEqual = (a: unknown, b: unknown, path = ""): boolean => {
  if (a === b) return true
  if (typeof a !== "object" || a === null || typeof b !== "object" || b === null) {
    console.warn(`DeepEqual mismatch at ${path}:`, a, "!==", b)
    return false
  }
  const keysA = Object.keys(a)
  const keysB = Object.keys(b)
  if (keysA.length !== keysB.length) {
    console.warn(`DeepEqual key length mismatch at ${path}:`, keysA, keysB)
    return false
  }
  for (const key of keysA) {
    if (!keysB.includes(key)) {
      console.warn(`DeepEqual missing key at ${path}:`, key)
      return false
    }
    if (!debugDeepEqual((a as any)[key], (b as any)[key], `${path}.${key}`)) return false
  }
  return true
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
  totp_enrollments: [],
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
  // Data should be encrypted string
  let snapshotData: CachedUserSnapshot
  if (typeof candidate.data === "string") {
    try {
      const bytes = CryptoJS.AES.decrypt(candidate.data, signingKey)
      const decrypted = bytes.toString(CryptoJS.enc.Utf8)
      snapshotData = JSON.parse(decrypted) as CachedUserSnapshot
    } catch {
      clearProfileCacheStorage()
      return undefined
    }
  } else {
    // Fallback for legacy plain object data (optional, or just clear it)
    snapshotData = candidate.data as CachedUserSnapshot
  }

  const payload: CacheSignaturePayload = {
    version: candidate.version,
    expiresAt: candidate.expiresAt,
    data: candidate.data,
  }

  // Verify signature to detect tampering
  const expectedSignature = CryptoJS.HmacSHA256(JSON.stringify(payload), signingKey).toString(
    CryptoJS.enc.Base64
  )

  if (candidate.signature !== expectedSignature) {
    // Signature mismatch - cache has been tampered with
    clearProfileCacheStorage()
    return undefined
  }

  const snapshot = snapshotData
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
      }

      // Encrypt the data to prevent clear text storage of sensitive information
      const encryptedData = CryptoJS.AES.encrypt(JSON.stringify(snapshot), signingKey).toString()

      const payload: CacheSignaturePayload = {
        version: PROFILE_CACHE_SCHEMA_VERSION,
        expiresAt: Date.now() + PROFILE_CACHE_TTL_MS,
        data: encryptedData,
      }

      // Generate HMAC signature for integrity check
      const signature = CryptoJS.HmacSHA256(JSON.stringify(payload), signingKey).toString(
        CryptoJS.enc.Base64
      )

      const envelope: CachedProfileEnvelope = {
        ...payload,
        signature,
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
    if (cachedEnvelope && isAxiosError(error) && !signal?.aborted && error.response) {
      // If the cached envelope causes the request to fail (even with a 500),
      // drop it and retry once without the header to recover gracefully.
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

const readStoredSessionSigningKey = (): string | null => {
  // This is duplicated from useSessionCrypto to avoid circular dependency or extra export
  // But ideally we should pass the key in.
  // Actually we pass the key in to useProfileSync.
  // But initializeCachedUser needs it.
  // We can read it from sessionStorage directly here as well.
  if (typeof sessionStorage === "undefined") return null
  try {
    // We need the key name from useSessionCrypto but we can't import it if it causes issues?
    // Actually we can import the constant.
    // But let's just use the hardcoded string or import it.
    // I'll import it.
    return sessionStorage.getItem(`${PROFILE_CACHE_BASE_KEY}.sessionKey`)
  } catch {
    return null
  }
}

const initializeCachedUser = (): UserState => {
  if (typeof window === "undefined") return null
  migrateProfileCache()
  const signingKey = readStoredSessionSigningKey()
  return readCachedUser(signingKey) ?? null
}

export const useProfileSync = (
  sessionSigningKey: string | null,
  updateSessionSigningKey: (key: string | null) => void,
  sessionSigningKeyPromiseRef: React.MutableRefObject<Promise<string | null> | null>,
  ensureSessionSigningKey: () => Promise<string | null>
) => {
  const queryClient = useQueryClient()
  const [userState, setUserState] = useState<UserState>(initializeCachedUser)
  const [pendingMfaState, setPendingMfaState] = useState<PendingMfaState | null>(null)
  const cachedUserRef = useRef<UserState>(userState)
  const userStateRef = useRef<UserState>(userState)
  const pendingMfaRef = useRef<PendingMfaState | null>(pendingMfaState)
  const [initializing, setInitializing] = useState<boolean>(() => userState == null)
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

        if (import.meta.env.DEV && normalized) {
          const keys = Object.keys(normalized)
          console.log(`setUserState called. Keys: ${keys.length}. Source trace:`, new Error().stack)
        }

        // Removed side effect: userStateRef.current = normalized
        if (persist) {
          const key = readStoredSessionSigningKey()
          persistUserToCache(normalized, key)
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
      resetEtagCache()
      // We need to clear session signing key too.
      // We need to call updateSessionSigningKey(null)
      // But we also need to clear the promise ref.
      if (sessionSigningKeyPromiseRef) {
        sessionSigningKeyPromiseRef.current = null
      }
      updateSessionSigningKey(null)
      clearProfile({ persist })
      updatePendingMfa(null, { broadcast })
      setAuthOperation(false)
      setInitializing(false)
      if (broadcast) {
        broadcastProfileEvent({ type: "unauthorized" })
      }
    },
    [
      broadcastProfileEvent,
      clearProfile,
      updatePendingMfa,
      updateSessionSigningKey,
      sessionSigningKeyPromiseRef,
    ]
  )

  useEffect(() => {
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

  useEffect(() => {
    if (typeof window === "undefined") return

    const syncFromCache = () => {
      const key = readStoredSessionSigningKey()
      const cached = readCachedUser(key)
      if (!cached) return

      applyUserState(
        (prev) => {
          if (!prev) return cached
          // If we have a full user object, don't overwrite it with a skeleton from cache
          // Only update the fields that are actually in the cache snapshot.
          console.log("Syncing from cache, merging fields...")
          return {
            ...prev,
            id: cached.id,
            full_name: cached.full_name,
            avatar_url: cached.avatar_url,
            mfa_required: cached.mfa_required,
            mfa_default_method: cached.mfa_default_method,
            mfa_last_verified_at: cached.mfa_last_verified_at,
          }
        },
        { persist: false }
      )
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
    userStateRef.current = userState
  }, [userState])

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
        if (!debugDeepEqual(userStateRef.current, profile)) {
          setUser(profile)
        }
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
  }, [ensureSessionSigningKey, handleUnauthorized, setUser])

  return {
    user: userState,
    setUser,
    loading: initializing || authOperation,
    pendingMfa: pendingMfaState,
    updatePendingMfa,
    handleUnauthorized,
    authOperation,
    setAuthOperation,
  }
}
