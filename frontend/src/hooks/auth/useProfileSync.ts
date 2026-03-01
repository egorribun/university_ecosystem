import { useCallback, useEffect, useRef, useState } from "react"
import { useQueryClient } from "@tanstack/react-query"
import { isAxiosError } from "axios"
import { hmac } from "@noble/hashes/hmac"
import { sha256 } from "@noble/hashes/sha256"

import api, { resetEtagCache, type ApiRequestConfig } from "@/api/client"
import type { User } from "@/types/User"
import type { PendingMfaState, SetUserArg, UserState } from "@/types/Auth"
import { clearAccessToken } from "./tokenStorage"
import { logError, logWarning } from "@/app/logger"
import { extractApiError } from "@/utils/error"
import { useAuthStore } from "@/stores/useAuthStore"

const PROFILE_CACHE_BASE_KEY = "ecosystem.profile.cache"
const PROFILE_CACHE_SCHEMA_VERSION = 7
export const PROFILE_CACHE_STORAGE_KEY = `${PROFILE_CACHE_BASE_KEY}.v${PROFILE_CACHE_SCHEMA_VERSION}`
const PROFILE_CACHE_VERSION_KEY = `${PROFILE_CACHE_BASE_KEY}.version`
const LEGACY_PROFILE_CACHE_KEYS = [
  "ecosystem.profile.cache.v1",
  "ecosystem.profile.cache.v4",
  "ecosystem.profile.cache.v5",
]
const PROFILE_CACHE_TTL_MS = 5 * 60 * 1000
const PROFILE_BROADCAST_CHANNEL = "ecosystem.profile.sync"
const PROFILE_CACHE_HEADER = "X-Profile-Cache-Envelope"

export const currentUserQueryKey = ["users", "me"] as const

type CachedUserSnapshot = Pick<
  User,
  | "id"
  | "email"
  | "full_name"
  | "role"
  | "group_id"
  | "avatar_url"
  | "cover_url"
  | "is_active"
  | "spotify_connected"
> &
  Partial<
    Pick<User, "mfa_required" | "mfa_default_method" | "mfa_last_verified_at" | "totp_enrollments">
  > & {
    profile_detail?: User["profile_detail"]
    education_path?: User["education_path"]
    preferences?: User["preferences"]
  }

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
    if (!areDeepEqual((a as Record<string, unknown>)[key], (b as Record<string, unknown>)[key]))
      return false
  }
  return true
}

const createOptimisticUser = (snapshot: CachedUserSnapshot): User => ({
  id: snapshot.id,
  email: snapshot.email,
  full_name: snapshot.full_name,
  role: snapshot.role,
  group_id: snapshot.group_id,
  avatar_url: snapshot.avatar_url,
  cover_url: snapshot.cover_url,
  spotify_connected: snapshot.spotify_connected,
  profile_detail: snapshot.profile_detail,
  education_path: snapshot.education_path,
  preferences: snapshot.preferences,
  is_active: false,
  mfa_required: Boolean(snapshot.mfa_required),
  mfa_default_method: snapshot.mfa_default_method ?? null,
  mfa_last_verified_at: snapshot.mfa_last_verified_at ?? null,
  totp_enrollments: snapshot.totp_enrollments ?? [],
  mfa_challenges: [],
  recovery_codes_left: 0,
  avatar_url_optimized: null,
  cover_url_optimized: null,
})

const clearProfileCacheStorage = () => {
  if (typeof localStorage === "undefined") return
  try {
    logWarning("profile_cache.cleared", { reason: "parse_error" })
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
      salt: salt as BufferSource,
      iterations: 600000,
      hash: "SHA-256",
    },
    keyMaterial,
    { name: "AES-GCM", length: 256 },
    false,
    ["encrypt", "decrypt"]
  )
}

/** Convert a Uint8Array to a base64 string without using spread arguments.
 * btoa(String.fromCharCode(...array)) risks a stack overflow for arrays > ~65k bytes.
 * This loop-based version avoids the call-stack issue entirely.
 */
const uint8ToBase64 = (bytes: Uint8Array): string => {
  let binary = ""
  for (let i = 0; i < bytes.byteLength; i++) {
    binary += String.fromCharCode(bytes[i])
  }
  return btoa(binary)
}

/** Constant-time string comparison — avoids early-exit timing leaks in the sync path.
 * Both strings must have equal length; the function always iterates the full length.
 */
const timingSafeEqual = (a: string, b: string): boolean => {
  if (a.length !== b.length) return false
  let result = 0
  for (let i = 0; i < a.length; i++) {
    result |= a.charCodeAt(i) ^ b.charCodeAt(i)
  }
  return result === 0
}

/** Constant-time HMAC-SHA256 verification using Web Crypto subtle.verify.
 * Preferred over re-computing the HMAC and comparing with === or timingSafeEqual,
 * because crypto.subtle.verify is mandated by the W3C spec to be constant-time.
 */
const verifyHmacAsync = async (
  payload: CacheSignaturePayload,
  signature: string,
  signingKey: string
): Promise<boolean> => {
  const subtle = getCrypto()
  if (!subtle) return false
  try {
    const enc = new TextEncoder()
    const key = await subtle.importKey(
      "raw",
      enc.encode(signingKey),
      { name: "HMAC", hash: "SHA-256" },
      false,
      ["verify"]
    )
    const sigBytes = Uint8Array.from(atob(signature), (c) => c.charCodeAt(0))
    return await subtle.verify("HMAC", key, sigBytes, enc.encode(JSON.stringify(payload)))
  } catch {
    return false
  }
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
    const ciphertextBase64 = uint8ToBase64(new Uint8Array(ciphertext))

    return `${saltHex}:${ivHex}:${ciphertextBase64}`
  } catch (e) {
    logError("Encryption failed", { error: e })
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
  } catch (_e) {
    // Decryption failed (wrong key or tampering)
    return null
  }
}

// HMAC Signature using noble hashes (consistent with sync version and works in JSDOM)
const signPayload = async (payload: CacheSignaturePayload, signingKey: string): Promise<string> => {
  try {
    const enc = new TextEncoder()
    const signatureBytes = hmac(
      sha256,
      enc.encode(signingKey),
      enc.encode(JSON.stringify(payload))
    )
    return uint8ToBase64(signatureBytes)
  } catch {
    return ""
  }
}

const verifySignatureSync = (
  payload: CacheSignaturePayload,
  signature: string,
  signingKey: string
): boolean => {
  try {
    const enc = new TextEncoder()
    const signatureBytes = hmac(sha256, enc.encode(signingKey), enc.encode(JSON.stringify(payload)))
    const expected = uint8ToBase64(signatureBytes)
    return timingSafeEqual(signature, expected)
  } catch {
    return false
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

  // Verify signature — use crypto.subtle.verify for constant-time HMAC comparison.
  const payload: CacheSignaturePayload = {
    version: candidate.version,
    expiresAt: candidate.expiresAt,
    data: candidate.data,
  }
  const signatureValid = await verifyHmacAsync(payload, candidate.signature, signingKey)
  if (!signatureValid) {
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

  if (!snapshotData || typeof snapshotData.id !== "string") {
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
        email: value.email,
        full_name: value.full_name,
        role: value.role,
        group_id: value.group_id,
        avatar_url: value.avatar_url,
        cover_url: value.cover_url,
        spotify_connected: value.spotify_connected,
        profile_detail: value.profile_detail,
        education_path: value.education_path,
        preferences: value.preferences,
        is_active: value.is_active,
        mfa_required: value.mfa_required,
        mfa_default_method: value.mfa_default_method,
        mfa_last_verified_at: value.mfa_last_verified_at,
        totp_enrollments: value.totp_enrollments ?? [],
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
    } as ApiRequestConfig)
    return response.data
  } catch (error) {
    if (cachedEnvelope && isAxiosError(error) && !signal?.aborted && error.response) {
      // If the cached envelope causes the request to fail (even with a 500),
      // drop it and retry once without the header to recover gracefully.
      clearProfileCacheStorage()
      const retry = await api.get<User>("/users/me", {
        signal,
        skipRateLimitQueue: true,
      } as ApiRequestConfig)
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
  updateSessionSigningKey: (key: string | null) => void,
  sessionSigningKeyPromiseRef: React.MutableRefObject<Promise<string | null> | null>,
  ensureSessionSigningKey: () => Promise<string | null>
) => {
  const queryClient = useQueryClient()
  const [userState, setUserState] = useState<UserState>(() => {
    if (typeof window === "undefined") return null
    const signingKey = sessionStorage.getItem(`${PROFILE_CACHE_BASE_KEY}.sessionKey`)
    if (!signingKey) return null
    const candidate = readCachedEnvelope()
    if (!candidate) return null
    if (candidate.version !== PROFILE_CACHE_SCHEMA_VERSION) return null
    if (candidate.expiresAt <= Date.now()) return null

    const payload: CacheSignaturePayload = {
      version: candidate.version,
      expiresAt: candidate.expiresAt,
      data: candidate.data,
    }

    if (verifySignatureSync(payload, candidate.signature, signingKey)) {
      if (typeof candidate.data !== "string") {
        // Legacy v3 format with unencrypted object data
        return createOptimisticUser(candidate.data)
      }
      // v4 format: data is encrypted string, cannot decrypt synchronously
      // Return a minimal placeholder user to prevent null state during async decryption
      // The async init useEffect will replace this with the fully decrypted user
      // We set a marker ID of -1 to indicate this is a placeholder pending async restore
      return {
        id: "-1", // Placeholder ID, will be replaced by async init
        email: "",
        full_name: "",
        role: "student",
        group_id: null,
        avatar_url: null,
        cover_url: null,
        spotify_connected: false,
        profile_detail: undefined,
        education_path: undefined,
        preferences: undefined,
        is_active: false,
        mfa_required: false,
        mfa_default_method: null,
        mfa_last_verified_at: null,
        totp_enrollments: [],
        mfa_challenges: [],
        recovery_codes_left: 0,
        avatar_url_optimized: null,
        cover_url_optimized: null,
      } as User
    }
    return null
  })
  const [pendingMfaState, setPendingMfaState] = useState<PendingMfaState | null>(null)
  const cachedUserRef = useRef<UserState>(userState)
  const userStateRef = useRef<UserState>(userState)
  const pendingMfaRef = useRef<PendingMfaState | null>(pendingMfaState)
  const [initializing, setInitializing] = useState<boolean>(() => {
    if (typeof window === "undefined") return true
    if (userState !== null) return false
    const hasKey = !!sessionStorage.getItem(`${PROFILE_CACHE_BASE_KEY}.sessionKey`)
    const hasCache = !!readCachedEnvelope()
    // If we have a potential session or cache, we must wait for verification
    return hasKey || hasCache
  })
  const [authOperation, setAuthOperation] = useState(false)
  const activeRequestRef = useRef<AbortController | null>(null)

  useEffect(() => {
    let mounted = true
    const init = async () => {
      if (typeof window === "undefined") return
      try {
        migrateProfileCache()
      } catch {
        // ignore
      }

      const signingKey = readStoredSessionSigningKey()
      if (signingKey) {
        const cached = await readCachedUserAsync(signingKey)
        if (mounted && cached) {
          setUserState(cached)
        }
      }
      // If we didn't have a cache, initializing was already true, now we set it to false
      // If we DID have a cache, initializing was already false, setting it to false is fine
      if (mounted) setInitializing(false)
    }
    init()
    return () => {
      mounted = false
    }
  }, [])

  const broadcastProfileEvent = useCallback((message: ProfileBroadcastMessage) => {
    if (typeof window === "undefined") return
    if (!("BroadcastChannel" in window)) return
    try {
      const channel = new BroadcastChannel(PROFILE_BROADCAST_CHANNEL)
      channel.postMessage(message)
      channel.close()
    } catch (_error) {
      if (import.meta.env.DEV) {
        logWarning("Failed to broadcast profile event", { error: _error })
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
      clearAccessToken()
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
          return {
            ...prev,
            id: cached.id,
            full_name: cached.full_name,
            avatar_url: cached.avatar_url,
            mfa_required: cached.mfa_required,
            mfa_default_method: cached.mfa_default_method,
            mfa_last_verified_at: cached.mfa_last_verified_at,
            totp_enrollments: cached.totp_enrollments ?? prev.totp_enrollments,
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
      } catch (_error) {
        if (import.meta.env.DEV) {
          logWarning("Failed to subscribe to profile broadcast channel", { error: _error })
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
    const hasCache = !!localStorage.getItem(PROFILE_CACHE_STORAGE_KEY)
    if (userStateRef.current == null && !hasCache) {
      setInitializing(true)
    }
    ;(async () => {
      try {
        const profile = await fetchCurrentUser({ signal: controller.signal })
        try {
          await ensureSessionSigningKey()
        } catch (_error) {
          if (!controller.signal.aborted && import.meta.env.DEV) {
            logWarning("Failed to obtain session signing key", { error: _error })
          }
        }
        if (!areDeepEqual(userStateRef.current, profile)) {
          setUser(profile as User)
        }
      } catch (error) {
        if (controller.signal.aborted) return null
        if (isAxiosError(error) && error.response?.status === 401) {
          handleUnauthorized()
          return
        }
        const apiError = extractApiError(error)
        logError("Failed to fetch current user", {
          message: apiError.message,
          status: apiError.status,
          details: apiError.details,
          traceId: apiError.traceId
        })
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

  useEffect(() => {
    useAuthStore.setState({
      user: userState,
      loading: initializing || authOperation,
      pendingMfa: pendingMfaState,
      authOperation,
      setUser,
      setLoading: setInitializing,
      setPendingMfa: setPendingMfaState,
      setAuthOperation,
    });
  }, [userState, initializing, authOperation, pendingMfaState, setUser, setInitializing, setPendingMfaState, setAuthOperation]);

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
