import { AxiosHeaders } from "axios"
import type { AxiosResponse, InternalAxiosRequestConfig } from "axios"
import { logWarning } from "@/app/logger"

// localStorage-backed ETag cache for persistence across page reloads
const ETAG_CACHE_KEY = "ue:etag-cache"
const RESPONSE_CACHE_KEY = "ue:response-cache"
const MAX_CACHE_ENTRIES = 50

/**
 * Signed cache entry — all stored responses are HMAC-SHA256 signed.
 * The signing key lives ONLY in memory (useSessionCrypto), so an XSS attacker
 * cannot forge a valid MAC without also controlling JS execution context.
 */
type SignedCacheEntry = {
  data: unknown
  hmac: string  // HMAC-SHA256(JSON.stringify(data), sessionSigningKey) — hex string
  ts: number    // Unix timestamp (ms) for future TTL enforcement
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

const loadCache = <T>(storageKey: string): Map<string, T> => {
  if (typeof window === "undefined") return new Map()
  try {
    const stored = localStorage.getItem(storageKey)
    if (stored) {
      const entries: [string, T][] = JSON.parse(stored)
      return new Map(entries)
    }
  } catch (_error) {
    logWarning(`Failed to load ${storageKey}`, _error)
  }
  return new Map()
}

const saveCache = <T>(storageKey: string, cache: Map<string, T>) => {
  if (typeof window === "undefined") return
  try {
    if (cache.size > MAX_CACHE_ENTRIES) {
      const deleteCount = cache.size - MAX_CACHE_ENTRIES
      const keys = cache.keys()
      for (let i = 0; i < deleteCount; i++) {
        const key = keys.next().value
        if (key) cache.delete(key)
      }
    }
    const entries = Array.from(cache.entries())
    localStorage.setItem(storageKey, JSON.stringify(entries))
  } catch (_error) {
    logWarning(`Failed to save ${storageKey}`, _error)
  }
}

export const etagCache = {
  get(key: string): string | undefined {
    return loadCache<string>(ETAG_CACHE_KEY).get(key)
  },
  set(key: string, value: string) {
    const cache = loadCache<string>(ETAG_CACHE_KEY)
    cache.set(key, value)
    saveCache(ETAG_CACHE_KEY, cache)
  },
  delete(key: string) {
    const cache = loadCache<string>(ETAG_CACHE_KEY)
    cache.delete(key)
    saveCache(ETAG_CACHE_KEY, cache)
  },
  clear() {
    if (typeof window !== "undefined") {
      try {
        localStorage.removeItem(ETAG_CACHE_KEY)
      } catch (_error) {
        logWarning("Failed to remove etag cache", _error)
      }
    }
  },
}

export const responseCache = {
  get(key: string): SignedCacheEntry | undefined {
    return loadCache<SignedCacheEntry>(RESPONSE_CACHE_KEY).get(key)
  },
  set(key: string, value: SignedCacheEntry) {
    const cache = loadCache<SignedCacheEntry>(RESPONSE_CACHE_KEY)
    cache.set(key, value)
    saveCache(RESPONSE_CACHE_KEY, cache)
  },
  delete(key: string) {
    const cache = loadCache<SignedCacheEntry>(RESPONSE_CACHE_KEY)
    cache.delete(key)
    saveCache(RESPONSE_CACHE_KEY, cache)
  },
  clear() {
    if (typeof window !== "undefined") {
      try {
        localStorage.removeItem(RESPONSE_CACHE_KEY)
      } catch (_error) {
        logWarning("Failed to remove response cache", _error)
      }
    }
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
        // Sign and store the response — HMAC guards against localStorage poisoning
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
        // HMAC mismatch: localStorage was tampered — evict and force a fresh request
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
