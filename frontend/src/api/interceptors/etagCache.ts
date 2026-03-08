import { AxiosHeaders } from "axios"
import type { AxiosResponse, InternalAxiosRequestConfig } from "axios"
import { logWarning } from "@/app/logger"

// ETag strings are persisted to localStorage for cross-reload cache hits.
// Response payloads stay in memory only (RZ-NEW-04: no sensitive data in localStorage).
const ETAG_CACHE_KEY = "ue:etag-cache"
const MAX_CACHE_ENTRIES = 50

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
  let result = 0
  for (let i = 0; i < a.length; i++) {
    result |= a.charCodeAt(i) ^ b.charCodeAt(i)
  }
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
  _flushTimer = setTimeout(() => {
    _flushTimer = null
    flushEtagCache()
  }, 500)
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
      for (let i = 0; i < evictCount; i++) _etagMap.delete(entries[i][0])
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
  for (let i = 0; i < sorted.length - MAX_CACHE_ENTRIES; i++) {
    cache.delete(sorted[i][0])
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
  for (let i = 0; i < sorted.length - MAX_CACHE_ENTRIES; i++) {
    _responseMap.delete(sorted[i][0])
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
        // Sign and store the response — HMAC guards against in-memory poisoning
        const payload = JSON.stringify(response.data)
        const hmac = await computeHmac(payload, signingKey)
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
