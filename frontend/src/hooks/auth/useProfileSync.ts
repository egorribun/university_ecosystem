import { useCallback, useEffect, useRef, useState } from "react"
import { useQueryClient } from "@tanstack/react-query"
import { isAxiosError } from "axios"

import api, { resetEtagCache } from "@/api/client"
import type { User } from "@/types/User"
import { signSnapshot } from "./useSessionCrypto"
import type { PendingMfaState, SetUserArg, UserState } from "@/types/Auth"

const PROFILE_CACHE_BASE_KEY = "ecosystem.profile.cache"
const PROFILE_CACHE_SCHEMA_VERSION = 4
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
  avatar_url_optimized: null,
  cover_url_optimized: null,
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

const getCrypto = () => {
  if (typeof window !== "undefined" && window.crypto && window.crypto.subtle) {
    return window.crypto.subtle
  }
  return null
}

const importKey = async (password: string) => {
  const subtle = getCrypto()
  if (!subtle) return null
  const enc = new TextEncoder()
  return subtle.importKey("raw", enc.encode(password), { name: "PBKDF2" }, false, ["deriveKey"])
}

const deriveKey = async (keyMaterial: CryptoKey, salt: Uint8Array) => {
  const subtle = getCrypto()
  if (!subtle) return null
  return subtle.deriveKey(
    {
      name: "PBKDF2",
      salt: salt as any,
      iterations: 600000,
      hash: "SHA-256",
    },
    keyMaterial,
    { name: "AES-GCM", length: 256 },
    false,
    ["encrypt", "decrypt"]
  )
}

const encryptData = async (
  data: CachedUserSnapshot,
  signingKey: string
): Promise<string | null> => {
  const subtle = getCrypto()
  if (!subtle) return null
  try {
    const keyMaterial = await importKey(signingKey)
    if (!keyMaterial) return null

    const salt = window.crypto.getRandomValues(new Uint8Array(16))
    const key = await deriveKey(keyMaterial, salt)
    if (!key) return null

    const iv = window.crypto.getRandomValues(new Uint8Array(12))
    const encodedData = new TextEncoder().encode(JSON.stringify(data))

    const ciphertext = await subtle.encrypt({ name: "AES-GCM", iv }, key, encodedData)

    // Format: hex(salt):hex(iv):base64(ciphertext)
    const saltHex = Array.from(salt)
      .map((b) => b.toString(16).padStart(2, "0"))
      .join("")
    const ivHex = Array.from(iv)
      .map((b) => b.toString(16).padStart(2, "0"))
      .join("")
    const ciphertextBase64 = btoa(String.fromCharCode(...new Uint8Array(ciphertext)))

    return `${saltHex}:${ivHex}:${ciphertextBase64}`
  } catch (e) {
    console.error("Encryption failed", e)
    return null
  }
}

const decryptData = async (
  encryptedString: string,
  signingKey: string
): Promise<CachedUserSnapshot | null> => {
  const subtle = getCrypto()
  if (!subtle) return null
  try {
    const parts = encryptedString.split(":")
    if (parts.length !== 3) return null
    const [saltHex, ivHex, ciphertextBase64] = parts

    const salt = new Uint8Array(saltHex.match(/.{1,2}/g)!.map((byte) => parseInt(byte, 16)))
    const iv = new Uint8Array(ivHex.match(/.{1,2}/g)!.map((byte) => parseInt(byte, 16)))
    const ciphertext = Uint8Array.from(atob(ciphertextBase64), (c) => c.charCodeAt(0))

    const keyMaterial = await importKey(signingKey)
    if (!keyMaterial) return null
    const key = await deriveKey(keyMaterial, salt)
    if (!key) return null

    const decrypted = await subtle.decrypt({ name: "AES-GCM", iv }, key, ciphertext)
    const decoded = new TextDecoder().decode(decrypted)
    return JSON.parse(decoded) as CachedUserSnapshot
  } catch (e) {
    // Decryption failed (wrong key or tampering)
    return null
  }
}

// HMAC Signature using Web Crypto
const signPayload = async (payload: CacheSignaturePayload, signingKey: string): Promise<string> => {
  const subtle = getCrypto()
  if (!subtle) return ""
  try {
    const enc = new TextEncoder()
    const keyMaterial = await subtle.importKey(
      "raw",
      enc.encode(signingKey),
      { name: "HMAC", hash: "SHA-256" },
      false,
      ["sign"]
    )
    const signature = await subtle.sign("HMAC", keyMaterial, enc.encode(JSON.stringify(payload)))
    return btoa(String.fromCharCode(...new Uint8Array(signature)))
  } catch {
    return ""
  }
}

const readCachedUserAsync = async (signingKey: string | null): Promise<User | undefined> => {
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

  // Verify signature
  const payload: CacheSignaturePayload = {
    version: candidate.version,
    expiresAt: candidate.expiresAt,
    data: candidate.data,
  }
  const expectedSignature = await signPayload(payload, signingKey)
  if (candidate.signature !== expectedSignature) {
    clearProfileCacheStorage()
    return undefined
  }

  let snapshotData: CachedUserSnapshot | null = null
  if (typeof candidate.data === "string") {
    snapshotData = await decryptData(candidate.data, signingKey)
  } else {
    // Legacy support or fallback? strictly string for v4
    snapshotData = null
  }

  if (!snapshotData || typeof snapshotData.id !== "number") {
    clearProfileCacheStorage()
    return undefined
  }
  return createOptimisticUser(snapshotData)
}

const persistUserToCacheAsync = async (value: User | null, signingKey: string | null) => {
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

      const encryptedData = await encryptData(snapshot, signingKey)
      if (!encryptedData) return

      const payload: CacheSignaturePayload = {
        version: PROFILE_CACHE_SCHEMA_VERSION,
        expiresAt: Date.now() + PROFILE_CACHE_TTL_MS,
        data: encryptedData,
      }

      const signature = await signPayload(payload, signingKey)

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

export const useProfileSync = (
  sessionSigningKey: string | null,
  updateSessionSigningKey: (key: string | null) => void,
  sessionSigningKeyPromiseRef: React.MutableRefObject<Promise<string | null> | null>,
  ensureSessionSigningKey: () => Promise<string | null>
) => {
  const queryClient = useQueryClient()
  const [userState, setUserState] = useState<UserState>(null)
  const [pendingMfaState, setPendingMfaState] = useState<PendingMfaState | null>(null)
  const cachedUserRef = useRef<UserState>(userState)
  const userStateRef = useRef<UserState>(userState)
  const pendingMfaRef = useRef<PendingMfaState | null>(pendingMfaState)
  const [initializing, setInitializing] = useState<boolean>(true)
  const [authOperation, setAuthOperation] = useState(false)
  const activeRequestRef = useRef<AbortController | null>(null)

  useEffect(() => {
    let mounted = true
    const init = async () => {
      if (typeof window === "undefined") return
      try { migrateProfileCache() } catch {}

      const signingKey = readStoredSessionSigningKey()
      if (signingKey) {
        const cached = await readCachedUserAsync(signingKey)
        if (mounted && cached) {
          setUserState(cached)
        }
      }
      if (mounted) setInitializing(false)
    }
    init()
    return () => { mounted = false }
  }, [])

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

        // Removed side effect: userStateRef.current = normalized
        if (persist) {
          const key = readStoredSessionSigningKey()
          persistUserToCacheAsync(normalized, key)
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
      persistUserToCacheAsync(userState, sessionSigningKey)
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

    const syncFromCache = async () => {
      const key = readStoredSessionSigningKey()
      const cached = await readCachedUserAsync(key)
      if (!cached) {
        // Cache was deleted or is invalid - clear user state
        applyUserState(() => null, { persist: false })
        queryClient.setQueryData<UserState>(currentUserQueryKey, null)
        return
      }

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
        if (!areDeepEqual(userStateRef.current, profile)) {
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
