/**
 * @fileoverview Background user-profile fetch + cache-versioned localStorage.
 *
 * Owns three concerns that AuthContext delegates here:
 *
 * 1. **Background sync** — on mount + on auth-state change, fetches
 *    ``/me/profile`` via TanStack Query and pushes the result into the
 *    Zustand auth store (``useAuthStore.setState``).
 * 2. **Versioned local cache** — profile snapshot is persisted to
 *    ``localStorage`` under ``ecosystem.profile.cache.v{N}`` so the UI
 *    can render immediately on cold load. ``PROFILE_CACHE_SCHEMA_VERSION``
 *    is bumped whenever the shape changes — older keys
 *    (``LEGACY_PROFILE_CACHE_KEYS``) are evicted on upgrade so stale PII
 *    cannot linger.
 * 3. **VITE_LHCI bypass** — when ``import.meta.env.VITE_LHCI === "true"``
 *    the hook synthesises a mock user (``id: "lhci-mock-user"``) so
 *    Lighthouse can score authenticated routes without a real backend.
 *    This branch is tree-shaken from prod builds (``VITE_LHCI`` is
 *    rewritten to ``"false"`` at build time).
 *
 * Cache TTL: 5 minutes — refetch happens in the background; the cached
 * snapshot serves the first paint.
 */
import { useCallback, useEffect, useRef, useState } from "react"
import { useQueryClient } from "@tanstack/react-query"
import { isAxiosError, isCancel } from "axios"
import { hmac } from "@noble/hashes/hmac"
import { sha256 } from "@noble/hashes/sha256"

import api, { resetEtagCache, type ApiRequestConfig } from "@/api/client"
import { clearCachesOnLogout } from "@/api/interceptors/etagCache"
import { currentUserQueryOptions } from "@/api/hooks/users"
import type { User } from "@/types/User"
import type { UserRole } from "@/api/generated"
import type { PendingMfaState, SetUserArg, UserState } from "@/types/Auth"
import { clearAccessToken } from "./tokenStorage"
import { logError, logWarning } from "@/app/logger"
import { extractApiError } from "@/utils/error"
import { useAuthStore } from "@/stores/useAuthStore"

const PROFILE_CACHE_BASE_KEY = "ecosystem.profile.cache"
// TD-14-07 (2026-03-18): Bumped from v7 → v8 to force-evict any previously
// cached entries that contained PII fields (email, role, profile_detail,
// education_path). On first load after upgrade, migrateProfileCache() will
// remove the v7 entry so no sensitive data remains in localStorage.
export const PROFILE_CACHE_SCHEMA_VERSION = 8
export const PROFILE_CACHE_STORAGE_KEY = `${PROFILE_CACHE_BASE_KEY}.v${PROFILE_CACHE_SCHEMA_VERSION}`
const PROFILE_CACHE_VERSION_KEY = `${PROFILE_CACHE_BASE_KEY}.version`
const LEGACY_PROFILE_CACHE_KEYS = [
  "ecosystem.profile.cache.v1",
  "ecosystem.profile.cache.v4",
  "ecosystem.profile.cache.v5",
  "ecosystem.profile.cache.v7", // TD-14-07: v7 may contain PII (email, role) — evict on upgrade
]
const PROFILE_CACHE_TTL_MS = 5 * 60 * 1000
const PROFILE_BROADCAST_CHANNEL = "ecosystem.profile.sync"
const PROFILE_CACHE_HEADER = "X-Profile-Cache-Envelope"

export const currentUserQueryKey = ["users", "me"] as const

// TD-14-07: Only non-PII fields may be stored here.
// NEVER add: email, phone, role, permissions, address, pending_email.
// Fields email and role were removed in TD-14-07 (2026-03-18).
// profile_detail and education_path omitted — they contain contact/academic PII
// (telegram, department, institute, program, track).
// See: OWASP WSTG-SESS-09 — sensitive data in localStorage.
export type CachedUserSnapshot = Pick<
  User,
  "id" | "full_name" | "group_id" | "avatar_url" | "cover_url" | "is_active" | "spotify_connected"
> &
  Partial<
    Pick<User, "mfa_required" | "mfa_default_method" | "mfa_last_verified_at" | "totp_enrollments">
  > & {
    preferences?: User["preferences"]
  }

type CachedProfileEnvelope = {
  version: number
  expiresAt: number
  data: CachedUserSnapshot | string // Can be encrypted string or plain object
  signature: string
}

export type CacheSignaturePayload = Pick<CachedProfileEnvelope, "version" | "expiresAt" | "data">

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
  // TD-14-07: email and role are not cached; provide safe defaults for optimistic render.
  // The authoritative values arrive from the /users/me API response shortly after mount.
  email: "",
  full_name: snapshot.full_name ?? null,
  role: "student",
  group_id: snapshot.group_id ?? null,
  avatar_url: snapshot.avatar_url ?? null,
  cover_url: snapshot.cover_url ?? null,
  spotify_connected: snapshot.spotify_connected ?? false,
  // TD-14-07: profile_detail and education_path are not cached (contain PII).
  profile_detail: undefined,
  education_path: undefined,
  preferences: snapshot.preferences ?? null,
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

const clearProfileCacheStorage = (
  reason:
    | "parse_error"
    | "invalid_signature"
    | "expired"
    | "version_mismatch"
    | "invalid_data" = "parse_error"
) => {
  if (typeof localStorage === "undefined") return
  try {
    logWarning("profile_cache.cleared", { reason })
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
    const parsed: unknown = JSON.parse(raw)
    if (!parsed || typeof parsed !== "object") {
      clearProfileCacheStorage("parse_error")
      return undefined
    }
    return parsed as CachedProfileEnvelope
  } catch (_e) {
    clearProfileCacheStorage("parse_error")
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
    binary += String.fromCharCode(bytes[i]!)
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
    const result = await subtle.verify("HMAC", key, sigBytes, enc.encode(JSON.stringify(payload)))
    return result
  } catch (_e) {
    return false
  }
}

export const encryptData = async (
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
    const [saltHex, ivHex, ciphertextBase64] = parts as [string, string, string]

    const saltMatch = saltHex.match(/.{1,2}/g)
    const ivMatch = ivHex.match(/.{1,2}/g)
    if (!saltMatch || !ivMatch) return null
    const salt = new Uint8Array(saltMatch.map((byte) => parseInt(byte, 16)))
    const iv = new Uint8Array(ivMatch.map((byte) => parseInt(byte, 16)))
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
export const signPayload = async (
  payload: CacheSignaturePayload,
  signingKey: string
): Promise<string> => {
  try {
    const enc = new TextEncoder()
    const signatureBytes = hmac(sha256, enc.encode(signingKey), enc.encode(JSON.stringify(payload)))
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
    clearProfileCacheStorage("version_mismatch")
    return undefined
  }
  if (
    typeof candidate.expiresAt !== "number" ||
    !candidate.data ||
    typeof candidate.signature !== "string"
  ) {
    clearProfileCacheStorage("invalid_data")
    return undefined
  }
  if (candidate.expiresAt <= Date.now()) {
    clearProfileCacheStorage("expired")
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
    clearProfileCacheStorage("invalid_signature")
    return undefined
  }

  let snapshotData: CachedUserSnapshot | null = null
  if (typeof candidate.data === "string") {
    snapshotData = await decryptData(candidate.data, signingKey)
  } else if (candidate.data && typeof candidate.data === "object") {
    // Legacy V3 support for unencrypted object data
    snapshotData = candidate.data as CachedUserSnapshot
  } else {
    snapshotData = null
  }

  if (!snapshotData || typeof snapshotData.id !== "string") {
    clearProfileCacheStorage("invalid_data")
    return undefined
  }
  return createOptimisticUser(snapshotData)
}

const persistUserToCacheAsync = async (
  value: User | null,
  signingKey: string | null,
  isMounted?: () => boolean
) => {
  if (typeof localStorage === "undefined") return
  try {
    if (value != null && signingKey) {
      // TD-14-07: Allowlist filter — only non-PII fields are persisted to localStorage.
      // NEVER add: email, role, phone, address, permissions, profile_detail, education_path.
      // See: OWASP WSTG-SESS-09 — sensitive data in localStorage.
      const snapshot: CachedUserSnapshot = {
        id: value.id,
        full_name: value.full_name,
        group_id: value.group_id,
        avatar_url: value.avatar_url,
        cover_url: value.cover_url,
        spotify_connected: value.spotify_connected,
        preferences: value.preferences,
        is_active: value.is_active,
        mfa_required: value.mfa_required,
        mfa_default_method: value.mfa_default_method,
        mfa_last_verified_at: value.mfa_last_verified_at,
        totp_enrollments: value.totp_enrollments ?? [],
      }

      const encryptedData = await encryptData(snapshot, signingKey)
      if (!encryptedData) return
      if (isMounted && !isMounted()) return

      const payload: CacheSignaturePayload = {
        version: PROFILE_CACHE_SCHEMA_VERSION,
        expiresAt: Date.now() + PROFILE_CACHE_TTL_MS,
        data: encryptedData,
      }

      const signature = await signPayload(payload, signingKey)
      if (isMounted && !isMounted()) return

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

/**
 * AuthContext-side profile state machine. Owns the cached user
 * snapshot, the ``loading`` / ``pendingMfa`` flags, and the
 * authoritative ``handleUnauthorized`` + ``setUser`` actions.
 *
 * Lifecycle on mount:
 *  1. Synchronous bootstrap from ``localStorage`` —
 *     ``verifySignatureSync`` (HMAC-SHA256 via @noble/hashes,
 *     constant-time compare) on the ``CachedProfileEnvelope``. If
 *     the v3 plaintext shape is present, it short-circuits to a
 *     fully populated ``User``; v4+ encrypted shapes return a
 *     placeholder with ``id: "-1"`` until the async init completes.
 *  2. Async init effect — ``readCachedUserAsync`` runs
 *     ``crypto.subtle.verify`` (constant-time) + AES-GCM decrypt of
 *     the encrypted snapshot. Replaces the placeholder with the
 *     real cached user.
 *  3. ``fetchCurrentUser({ signal })`` — calls ``/users/me`` with
 *     the previous envelope as ``X-Profile-Cache-Envelope`` header
 *     for backend-side cache validation. On 401 invokes
 *     ``handleUnauthorized``; any other error logs and leaves the
 *     cached state intact.
 *  4. ``VITE_LHCI=true`` short-circuit synthesises a mock user
 *     (``id: "lhci-mock-user"``) so Lighthouse can score
 *     authenticated routes. Tree-shaken from prod builds.
 *
 * Cross-tab sync: ``window.addEventListener("storage", …)`` mirrors
 * cache mutations + ``BroadcastChannel("ecosystem.profile.sync")``
 * propagates ``unauthorized`` / ``mfa-pending`` / ``mfa-cleared``
 * events between tabs.
 *
 * Auth-store mirror: every change pushes ``user`` / ``loading`` /
 * ``pendingMfa`` / ``authOperation`` into ``useAuthStore`` via
 * ``setState``. Components that just need to read auth state
 * subscribe to the store directly rather than threading the hook
 * return through context.
 *
 * @param updateSessionSigningKey - Provided by ``useSessionCrypto``;
 *   called from ``handleUnauthorized`` to clear the session key.
 * @param sessionSigningKeyRef - Live ref to the current key, read by
 *   the encrypted-cache verify/decrypt path without re-rendering.
 * @param sessionSigningKeyPromiseRef - Live ref to the in-flight
 *   key fetch promise, cleared on logout so the next call retries.
 * @param ensureSessionSigningKey - Lazy fetcher; called after
 *   ``/users/me`` succeeds to make sure subsequent signed mutations
 *   have a key to use.
 * @returns ``user`` snapshot + ``setUser`` setter, the combined
 *   ``loading`` flag (initialising OR mid-auth-op), the pending
 *   MFA challenge object, and the actions
 *   (``updatePendingMfa``, ``handleUnauthorized``,
 *   ``setAuthOperation``).
 */
export type SsrAuthHint = {
  isAuth: boolean
  user: { role: string } | null
}

// Wave 128 SW1 — runtime UserRole validation for ssrAuthHint.user.role
// (typed as `string` per SsrAuthState shape). Invalid roles fall back to
// "student" — same defensive pattern as ssrAuth.ts validateJwt.
const KNOWN_USER_ROLES: ReadonlyArray<UserRole> = [
  "student",
  "teacher",
  "admin",
  "superuser",
  "anonymous",
]
const coerceUserRole = (role: string): UserRole => {
  return (KNOWN_USER_ROLES as ReadonlyArray<string>).includes(role) ? (role as UserRole) : "student"
}

export const buildSsrStubUser = (role: string): User => ({
  // Wave 128 SW1 — role-only stub for server-side render. Full user
  // (name/avatar/email) hydrates from /users/me query cache after
  // SW3 loader.ensureQueryData populates it. Empty fields are safe
  // defaults: Navbar renders with placeholder, Profile menu shows
  // role-based options. No PII surfaces in SSR HTML.
  id: "ssr-stub",
  email: "",
  full_name: "",
  role: coerceUserRole(role),
  group_id: null,
  avatar_url: null,
  cover_url: null,
  spotify_connected: false,
  profile_detail: undefined,
  education_path: undefined,
  preferences: undefined,
  is_active: true,
  mfa_required: false,
  mfa_default_method: null,
  mfa_last_verified_at: null,
  totp_enrollments: [],
  mfa_challenges: [],
  recovery_codes_left: 0,
  avatar_url_optimized: null,
  cover_url_optimized: null,
})

/**
 * Wave 128 SW1 — pure helper for SSR initial userState resolution.
 * Returns the SSR stub User if the hint indicates an authenticated
 * server-side render; otherwise null. Extracted from useProfileSync's
 * useState initFn to enable direct unit testing without window-mocking
 * (jsdom always defines window in test env).
 */
export const resolveSsrInitialUserState = (hint: SsrAuthHint | undefined): UserState => {
  if (hint?.isAuth && hint.user) {
    return buildSsrStubUser(hint.user.role)
  }
  return null
}

/**
 * Wave 128 SW1 — pure helper for SSR initial `initializing` flag.
 * Returns false when SSR hint resolved an authenticated user (init
 * complete); true otherwise (client-side init useEffect will resolve).
 */
export const resolveSsrInitialInitializing = (hint: SsrAuthHint | undefined): boolean => {
  return !hint?.isAuth
}

export const useProfileSync = (
  updateSessionSigningKey: (key: string | null) => void,
  sessionSigningKeyRef: React.MutableRefObject<string | null>,
  sessionSigningKeyPromiseRef: React.MutableRefObject<Promise<string | null> | null>,
  ensureSessionSigningKey: () => Promise<string | null>,
  ssrAuthHint?: SsrAuthHint | undefined
) => {
  const queryClient = useQueryClient()
  const [userState, setUserState] = useState<UserState>(() => {
    if (typeof window === "undefined") {
      // Wave 128 SW1 Strategy A — see resolveSsrInitialUserState helper.
      // Returns role-only stub when ssrAuthHint indicates authenticated
      // server-side render (JWT cookie validated by server.ts W126 SW3).
      // Full user hydrates from /users/me cache or client-side useEffect.
      return resolveSsrInitialUserState(ssrAuthHint)
    }
    const signingKey = sessionSigningKeyRef.current
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
        if (!candidate.data || typeof candidate.data.id !== "string") {
          clearProfileCacheStorage("invalid_data")
          return null
        }
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
    if (typeof window === "undefined") {
      // Wave 128 SW1 — see resolveSsrInitialInitializing helper.
      return resolveSsrInitialInitializing(ssrAuthHint)
    }
    if (userState !== null) return false
    const hasKey = !!sessionSigningKeyRef.current
    const hasCache = !!readCachedEnvelope()
    // If we have a potential session or cache, we must wait for verification
    return hasKey || hasCache
  })
  const [authOperation, setAuthOperation] = useState(false)
  // Wave 135 SW1 — `activeRequestRef` (AbortController for the /users/me
  // fetch) was removed alongside the controller pattern in the auto-fetch
  // effect. Cancellation is now handled exclusively via
  // `queryClient.cancelQueries({ queryKey: currentUserQueryKey })` —
  // introduced in W134 SW1 alongside the controller, now the sole path.
  // Closes W134 §Honesty #3.
  const autoFetchAttemptedRef = useRef(false)
  const initializingRef = useRef(initializing)
  const mountedRef = useRef(true)

  useEffect(() => {
    mountedRef.current = true
    return () => {
      mountedRef.current = false
    }
  }, [])

  useEffect(() => {
    let mounted = true
    const init = async () => {
      if (typeof window === "undefined") return
      try {
        migrateProfileCache()
      } catch {
        // ignore
      }

      // Read from the ref for initialization
      const signingKey = sessionSigningKeyRef.current
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
  }, [sessionSigningKeyRef])

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

        userStateRef.current = normalized
        if (persist) {
          const key = sessionSigningKeyRef.current
          persistUserToCacheAsync(normalized, key, () => mountedRef.current)
        }
        queryClient.setQueryData<UserState>(currentUserQueryKey, normalized)
        return normalized
      })
    },
    [queryClient, sessionSigningKeyRef]
  )

  const setUser = useCallback(
    (value: SetUserArg) => {
      applyUserState(value, { persist: true })
    },
    [applyUserState]
  )

  const clearProfile = useCallback(
    ({ persist = true }: { persist?: boolean } = {}) => {
      // Wave 135 SW1 — replace AbortController.abort() with
      // queryClient.cancelQueries. Was: `controller?.abort()` cancelling
      // the activeRequestRef-tracked controller. Now: the bridged
      // fetchQuery's internal signal receives the cancellation via
      // queryClient + axios interceptor → request rejects with
      // CanceledError, swallowed by the auto-fetch catch block (isCancel
      // guard).
      queryClient.cancelQueries({ queryKey: currentUserQueryKey }).catch(() => undefined)
      applyUserState(() => null, { persist })
      cachedUserRef.current = null
    },
    [applyUserState, queryClient]
  )

  const handleUnauthorized = useCallback(
    ({ broadcast = true, persist = true }: HandleUnauthorizedOptions = {}) => {
      // RED-02 (audit Wave 11): clearCachesOnLogout atomically increments the
      // session epoch AND clears both response/etag caches.  The epoch increment
      // races any in-flight async HMAC computations from the outgoing session,
      // ensuring they discard their results and cannot pollute the next session.
      // Must be called BEFORE updateSessionSigningKey(null) so that the epoch
      // change is visible to any awaiting HMAC tasks before the key is cleared.
      clearCachesOnLogout()
      resetEtagCache() // belt-and-suspenders: also clear module-level copies in client.ts
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
    const cachedUser = cachedUserRef.current
    if (cachedUser !== null) {
      // The encrypted-cache bootstrap uses id "-1" as a render-only
      // placeholder. It must not become fresh authoritative /users/me data,
      // otherwise fetchQuery() returns the placeholder and never reaches the
      // backend for the real profile.
      if (cachedUser.id !== "-1") {
        queryClient.setQueryData<UserState>(currentUserQueryKey, cachedUser)
      }
      cachedUserRef.current = null
    }
  }, [queryClient])

  useEffect(() => {
    if (typeof window === "undefined") return

    const syncFromCache = async () => {
      const key = sessionSigningKeyRef.current
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
  }, [applyUserState, handleUnauthorized, queryClient, sessionSigningKeyRef, updatePendingMfa])

  useEffect(() => {
    userStateRef.current = userState
  }, [userState])

  useEffect(() => {
    // Wave 116 SW3 — LHCI auth mock. scripts/run-lhci.mjs builds with
    // VITE_LHCI=true and needs authenticated routes (/dashboard, /news,
    // /events, /schedule, /activity, /map) to render their real content
    // for Lighthouse a11y/perf scoring. Skip the /users/me API call and
    // populate the store with a synthetic user so _auth.tsx beforeLoad
    // sees isAuth=true. Tree-shakes in prod (CI builds without the flag).
    if (import.meta.env.VITE_LHCI === "true") {
      setUser({
        id: "lhci-mock-user",
        email: "",
        full_name: "LHCI Test User",
        role: "student",
        group_id: null,
        avatar_url: null,
        cover_url: null,
        spotify_connected: false,
        profile_detail: undefined,
        education_path: undefined,
        preferences: null,
        is_active: true,
        mfa_required: false,
        mfa_default_method: null,
        mfa_last_verified_at: null,
        totp_enrollments: [],
        mfa_challenges: [],
        recovery_codes_left: 0,
        avatar_url_optimized: null,
        cover_url_optimized: null,
      } as User)
      setInitializing(false)
      return
    }

    // Wave 135 SW1 — AbortController removed (was `const controller = new
    // AbortController(); activeRequestRef.current?.abort();
    // activeRequestRef.current = controller`). queryClient.cancelQueries
    // is the sole cancellation mechanism: it fires the internal AbortSignal
    // attached to the queryFn, which the factory's queryFn → fetchCurrentUser
    // → axios respects via the standard `signal` config. Concurrent
    // auto-fetch effect runs (e.g. handleUnauthorized → setUser → effect
    // re-fires) call cancelQueries here, cancelling the prior in-flight
    // fetch before initiating the new one. Closes W134 §Honesty #3.
    queryClient.cancelQueries({ queryKey: currentUserQueryKey }).catch(() => undefined)
    // RZ-31-03: Safari private browsing throws SecurityError on localStorage access.
    // Every other localStorage call in this file is wrapped — this was a missed spot.
    let hasCache = false
    try {
      hasCache = !!localStorage.getItem(PROFILE_CACHE_STORAGE_KEY)
    } catch {
      // Incognito/privacy mode — proceed without cache.
    }
    if (
      userStateRef.current == null &&
      !hasCache &&
      !initializingRef.current &&
      !autoFetchAttemptedRef.current
    ) {
      autoFetchAttemptedRef.current = true
      setInitializing(true)
    } else if (autoFetchAttemptedRef.current && !initializingRef.current) {
      // Already tried or have data, nothing to do
      return
    }
    ;(async () => {
      try {
        // Wave 134 SW1 — Bridge: route through queryClient.fetchQuery so the
        // SSR loader's ensureQueryData(currentUserQueryOptions()) and this
        // auto-fetch effect share a single cache slot. Returns cached data
        // if fresh (within factory's staleTime: 60_000), invokes the
        // factory's queryFn → fetchCurrentUser({signal}) if stale, dedups
        // concurrent calls. The factory's queryFn preserves
        // fetchCurrentUser's bespoke retry-on-500-with-cleared-cache logic.
        // Closes W133 §Honesty #3+#4 — duplicated network calls between SSR
        // loader and useProfileSync's auto-fetch are eliminated.
        //
        // retry: false override — preserves pre-W134 single-attempt semantics
        // for the auto-fetch path. useProfileSync's outer catch handles 401
        // directly via handleUnauthorized; React Query's default retry would
        // delay 401 propagation by retryDelay × 2 (~3 s) and break the
        // expected loading-flag transition timing for AuthContext consumers.
        const profile = await queryClient.fetchQuery({
          ...currentUserQueryOptions(),
          retry: false,
        })
        try {
          await ensureSessionSigningKey()
        } catch (_error) {
          // Wave 135 SW1 — drop `!controller.signal.aborted` guard (the
          // controller was retired). ensureSessionSigningKey is its own
          // request not bound to the bridged fetchQuery's signal, so a
          // cancellation upstream doesn't propagate here anyway.
          if (import.meta.env.DEV) {
            logWarning("Failed to obtain session signing key", { error: _error })
          }
        }
        if (!areDeepEqual(userStateRef.current, profile)) {
          setUser(profile as User)
        }
      } catch (error) {
        // Wave 135 SW1 — replace `controller.signal.aborted` check with
        // axios's `isCancel`. queryClient.cancelQueries triggers the
        // internal signal → axios CanceledError (code "ERR_CANCELED") →
        // isCancel returns true. Silent skip preserves the pre-W135
        // behaviour where a cancelled fetch did not log "Failed to fetch
        // current user" noise on logout / auto-fetch effect re-runs.
        if (isCancel(error)) return null
        if (isAxiosError(error) && error.response?.status === 401) {
          handleUnauthorized()
          return
        }
        const apiError = extractApiError(error)
        logError("Failed to fetch current user", {
          message: apiError.message,
          status: apiError.status,
          details: apiError.details,
          traceId: apiError.traceId,
        })
      } finally {
        // Wave 135 SW1 — controller-tracked finally collapsed to
        // unconditional setInitializing(false). React's batching makes
        // back-to-back calls idempotent; if a cancellation fired upstream
        // the loading flag was already going to be reset by the next
        // auto-fetch effect run.
        setInitializing(false)
      }
    })()
    // Wave 134 SW1 — `queryClient` added to deps because the bridged
    // auto-fetch now calls queryClient.cancelQueries + queryClient.fetchQuery.
    // The reference is stable via useQueryClient (Provider-level memoised),
    // so adding it does not re-fire the effect on every render.
  }, [ensureSessionSigningKey, handleUnauthorized, setUser, queryClient])

  useEffect(() => {
    initializingRef.current = initializing
  }, [initializing])

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
    })
  }, [
    userState,
    initializing,
    authOperation,
    pendingMfaState,
    setUser,
    setInitializing,
    setPendingMfaState,
    setAuthOperation,
  ])

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
