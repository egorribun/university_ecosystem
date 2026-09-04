import { AxiosHeaders } from "axios"
import type { AxiosResponse, InternalAxiosRequestConfig } from "axios"
import { logWarning } from "@/app/logger"

// ETag strings are persisted to localStorage for cross-reload cache hits.
// Response payloads stay in memory only (RZ-NEW-04: no sensitive data in localStorage).
//
// DEBT-02 (audit Wave 11): versioned key so stale localStorage entries from
// previous schema versions are ignored automatically after deployment.
// Increment VITE_API_SCHEMA_VERSION in .env when making breaking API schema changes.
const _API_SCHEMA_VERSION = (import.meta.env.VITE_API_SCHEMA_VERSION as string | undefined) ?? "1"
const ETAG_CACHE_KEY = `ue:etag-cache:v${_API_SCHEMA_VERSION}`
// PERF-14-01 (audit 2026-03-23): Increased from 50 → 200.
// A power-user with 10 open chats + feed + schedule + profile needs 17+ URLs.
// At 50 entries, frequently-accessed ETags were evicted by low-frequency ones,
// causing unnecessary full-payload responses instead of 304 Not Modified.
// 200 entries × ~200 bytes ≈ 40 KB in memory — negligible on any modern device.
const MAX_CACHE_ENTRIES = 200

// RED-02 (audit Wave 11): session epoch prevents cross-session data leakage.
// Monotonically incremented on each login; captured before async HMAC computation
// and re-checked after — if the epoch changed (logout→login during the await),
// the result is discarded so user A's response is never stored under user B's session.
let _sessionEpoch = 0

/**
 * Increment the session epoch on login. Must be called AFTER the new signing key
 * is registered so any in-flight async HMAC computations from the previous session
 * detect the epoch change and discard their results.
 */
export const incrementSessionEpoch = (): void => {
  _sessionEpoch++
}

/**
 * Clear all cache state on logout. Call this BEFORE clearing the signing key so
 * that in-flight requests (which captured the old key) cannot store data after clear.
 */
export const clearCachesOnLogout = (): void => {
  _sessionEpoch++ // invalidate any in-flight async computations first
  responseCache.clear()
  etagCache.clear()
}

/**
 * Signed cache entry — all stored responses are HMAC-SHA256 signed.
 * The signing key lives ONLY in memory (useSessionCrypto), so an XSS attacker
 * cannot forge a valid MAC without also controlling JS execution context.
 */
type SignedCacheEntry = {
  data: unknown
  hmac: string // HMAC-SHA256(JSON.stringify(data), sessionSigningKey) — hex string
  ts: number // Unix timestamp (ms) for LRU eviction
}

type EtagEntry = {
  tag: string
  lastUsed: number // Unix timestamp (ms) — used for LRU ordering
}

/**
 * Runtime signing key accessor — injected by useSessionCrypto after key is fetched.
 * Returns null during cold start (before /auth/session/signing-key response).
 */
let _getSigningKey: (() => string | null) | null = null

export const registerSigningKeyAccessor = (accessor: () => string | null) => {
  _getSigningKey = accessor
}

const getSigningKey = (): string | null => _getSigningKey?.() ?? null

/** Compute HMAC-SHA256 over payload using the session signing key. Returns hex string. */
const computeHmac = async (payload: string, key: string): Promise<string> => {
  const enc = new TextEncoder()
  const cryptoKey = await crypto.subtle.importKey(
    "raw",
    enc.encode(key),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"]
  )
  const sig = await crypto.subtle.sign("HMAC", cryptoKey, enc.encode(payload))
  return Array.from(new Uint8Array(sig))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("")
}

/** Constant-time hex comparison to prevent timing attacks. */
const timingSafeEqual = (a: string, b: string): boolean => {
  if (a.length !== b.length) return false
  const result = Array.from({ length: a.length }, (_, index) => index).reduce(
    (accumulator, index) => accumulator | (a.charCodeAt(index) ^ b.charCodeAt(index)),
    0
  )
  return result === 0
}

// ── ETag cache — in-memory primary, debounced localStorage flush ─────────────
//
// TD-NEW-01 + TD-NEW-02 (audit 2026-03):
//   Old impl called loadCache() (full JSON.parse of localStorage) on every
//   get/set/delete — O(N) per call with FIFO eviction.
//   New impl hydrates once on first access, keeps an in-memory Map as the
//   primary store, and debounces the persistence flush to 500ms. Eviction is
//   LRU by lastUsed timestamp instead of FIFO by Map insertion order.

let _etagMap: Map<string, EtagEntry> | null = null // null = not yet hydrated
let _flushTimer: ReturnType<typeof setTimeout> | null = null

function getEtagMap(): Map<string, EtagEntry> {
  if (_etagMap !== null) return _etagMap

  // Hydrate exactly once from localStorage on first access.
  _etagMap = new Map()
  if (typeof window === "undefined") return _etagMap
  try {
    const raw = localStorage.getItem(ETAG_CACHE_KEY)
    if (raw) {
      const entries = JSON.parse(raw) as [string, EtagEntry][]
      _etagMap = new Map(entries)
    }
  } catch (_err) {
    logWarning("Failed to hydrate etag cache", _err)
  }
  return _etagMap
}

function scheduleFlush(): void {
  if (typeof window === "undefined") return
  if (_flushTimer !== null) clearTimeout(_flushTimer)
  // PERF-01 (audit Wave 11): Increased from 500ms to 30s to reduce GC pressure on
  // mobile devices — 500ms caused O(entries) JSON serialization every half-second
  // during active API usage (≈20KB/s write throughput on localStorage).
  // A guaranteed flush on visibilitychange (tab hide) prevents data loss.
  _flushTimer = setTimeout(() => {
    _flushTimer = null
    flushEtagCache()
  }, 30_000)
}

// PERF-01: Flush immediately when the page is hidden (tab switch, app background).
// Registered once at module load — covers browser close and navigation away.
if (typeof document !== "undefined") {
  document.addEventListener(
    "visibilitychange",
    () => {
      if (document.visibilityState === "hidden") flushEtagCache()
    },
    { passive: true }
  )
}

// DEBT-02: Evict stale cache entries from previous schema versions on startup.
// Old keys matching "ue:etag-cache" (without version) or prior versions are orphaned
// and would grow unboundedly; this cleans them up once per page load.
if (typeof window !== "undefined") {
  try {
    const staleKeys = Array.from({ length: localStorage.length }, (_, index) =>
      localStorage.key(index)
    ).filter(
      (key): key is string =>
        typeof key === "string" && key.startsWith("ue:etag-cache") && key !== ETAG_CACHE_KEY
    )
    for (const key of staleKeys) {
      localStorage.removeItem(key)
    }
  } catch {
    // Ignore quota/security errors during cleanup
  }
}

function flushEtagCache(): void {
  if (!_etagMap || typeof window === "undefined") return
  try {
    localStorage.setItem(ETAG_CACHE_KEY, JSON.stringify(Array.from(_etagMap.entries())))
  } catch (err) {
    // P-04 (audit 2026-03-08): On QuotaExceededError, evict the oldest 50% of
    // entries and retry once.  If it still fails, in-memory cache stays intact
    // (acceptable graceful degradation — cache is rebuilt on next page load).
    if (err instanceof DOMException && err.name === "QuotaExceededError") {
      const entries = Array.from(_etagMap.entries()).sort((a, b) => a[1].lastUsed - b[1].lastUsed)
      const evictCount = Math.ceil(_etagMap.size / 2)
      for (const [key] of entries.slice(0, evictCount)) _etagMap.delete(key)
      try {
        localStorage.setItem(ETAG_CACHE_KEY, JSON.stringify(Array.from(_etagMap.entries())))
      } catch {
        // Still over quota — accept in-memory-only mode until next eviction cycle
      }
    } else {
      logWarning("Failed to flush etag cache to localStorage", err)
    }
  }
}

/** Remove least-recently-used entries when the cache exceeds MAX_CACHE_ENTRIES. */
function evictLruEtag(cache: Map<string, EtagEntry>): void {
  if (cache.size <= MAX_CACHE_ENTRIES) return
  const sorted = Array.from(cache.entries()).sort((a, b) => a[1].lastUsed - b[1].lastUsed)
  for (const [key] of sorted.slice(0, sorted.length - MAX_CACHE_ENTRIES)) {
    cache.delete(key)
  }
}

export const etagCache = {
  get(key: string): string | undefined {
    const cache = getEtagMap()
    const entry = cache.get(key)
    if (entry) {
      entry.lastUsed = Date.now() // LRU touch — update in-place
    }
    return entry?.tag
  },
  set(key: string, value: string) {
    const cache = getEtagMap()
    cache.set(key, { tag: value, lastUsed: Date.now() })
    evictLruEtag(cache)
    scheduleFlush()
  },
  delete(key: string) {
    const cache = getEtagMap()
    if (cache.has(key)) {
      cache.delete(key)
      scheduleFlush()
    }
  },
  clear() {
    _etagMap = new Map()
    if (_flushTimer !== null) {
      clearTimeout(_flushTimer)
      _flushTimer = null
    }
    if (typeof window !== "undefined") {
      try {
        localStorage.removeItem(ETAG_CACHE_KEY)
      } catch (_err) {
        logWarning("Failed to remove etag cache", _err)
      }
    }
  },
}

// ── Response cache — purely in-memory ───────────────────────────────────────
//
// RZ-NEW-04 (audit 2026-03): Sensitive API response payloads were previously
// stored in localStorage under RESPONSE_CACHE_KEY. An attacker with filesystem
// or extension access could read that key. The HMAC provided integrity, not
// confidentiality. Moving to a pure in-memory Map eliminates the exposure —
// data lives only in the JS heap and is naturally cleared on page unload.
// LRU eviction by entry.ts prevents unbounded memory growth.

const _responseMap = new Map<string, SignedCacheEntry>()

function evictLruResponse(): void {
  if (_responseMap.size <= MAX_CACHE_ENTRIES) return
  const sorted = Array.from(_responseMap.entries()).sort((a, b) => a[1].ts - b[1].ts)
  for (const [key] of sorted.slice(0, sorted.length - MAX_CACHE_ENTRIES)) {
    _responseMap.delete(key)
  }
}

export const responseCache = {
  get(key: string): SignedCacheEntry | undefined {
    return _responseMap.get(key)
  },
  set(key: string, value: SignedCacheEntry) {
    _responseMap.set(key, value)
    evictLruResponse()
  },
  delete(key: string) {
    _responseMap.delete(key)
  },
  clear() {
    _responseMap.clear()
  },
}

export const applyEtagHeader = (config: InternalAxiosRequestConfig, etagKey: string) => {
  const headers = AxiosHeaders.from(config.headers ?? {})
  if (!headers.has("if-none-match")) {
    const cachedTag = etagCache.get(etagKey)
    if (cachedTag) {
      headers.set("If-None-Match", cachedTag)
    }
  }
  config.headers = headers
}

export const handleEtagResponse = async (response: AxiosResponse, etagKey: string) => {
  const responseHeaders = AxiosHeaders.from(
    (response.headers ?? undefined) as AxiosHeaders | string | undefined
  )
  const tag = responseHeaders.get("etag") ?? responseHeaders.get("ETag")

  if (typeof tag === "string" && tag.trim()) {
    etagCache.set(etagKey, tag)
    // Only cache JSON responses — caching HTML error pages or other content types
    // can corrupt the response cache and break the app on 304 cache hit.
    const contentType = (responseHeaders.get("content-type") as string | null) ?? ""
    const isJson = contentType.includes("application/json")

    if (response.status === 200 && response.data && isJson) {
      const signingKey = getSigningKey()
      if (signingKey) {
        // RED-02 (audit Wave 11): capture epoch BEFORE the async HMAC computation.
        // If a logout→login occurs during the await, _sessionEpoch changes and we
        // discard the result — preventing user A's data from being stored under
        // user B's session (account confusion on shared devices).
        const epochSnapshot = _sessionEpoch
        const payload = JSON.stringify(response.data)
        const hmac = await computeHmac(payload, signingKey)
        if (_sessionEpoch !== epochSnapshot) {
          // Session changed during async computation — discard stale result
          return
        }
        responseCache.set(etagKey, { data: response.data, hmac, ts: Date.now() })
      } else {
        // No signing key yet (cold start) — do not cache unsigned data
        responseCache.delete(etagKey)
      }
    }
  } else {
    etagCache.delete(etagKey)
    responseCache.delete(etagKey)
  }

  if (response.status === 304) {
    const signingKey = getSigningKey()
    const entry = responseCache.get(etagKey)

    if (entry && signingKey) {
      // Verify HMAC before serving cached data
      const expected = await computeHmac(JSON.stringify(entry.data), signingKey)
      if (timingSafeEqual(entry.hmac, expected)) {
        response.data = entry.data
        response.status = 200
      } else {
        // HMAC mismatch: in-memory entry was corrupted — evict and force fresh request
        logWarning("[etagCache] HMAC mismatch for key:", etagKey)
        etagCache.delete(etagKey)
        responseCache.delete(etagKey)
        // response.status stays 304; axios will re-issue the request on next call
      }
    } else {
      // No signing key or no cache entry — fall through (axios will handle 304 gracefully)
      etagCache.delete(etagKey)
      responseCache.delete(etagKey)
    }
  }
}
