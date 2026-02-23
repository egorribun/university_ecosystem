import { AxiosHeaders } from "axios"
import type { AxiosResponse, InternalAxiosRequestConfig } from "axios"
import { logWarning } from "@/app/logger"

// localStorage-backed ETag cache for persistence across page reloads
const ETAG_CACHE_KEY = "ue:etag-cache"
const RESPONSE_CACHE_KEY = "ue:response-cache"
const MAX_CACHE_ENTRIES = 50

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
  get(key: string): unknown | undefined {
    return loadCache<unknown>(RESPONSE_CACHE_KEY).get(key)
  },
  set(key: string, value: unknown) {
    const cache = loadCache<unknown>(RESPONSE_CACHE_KEY)
    cache.set(key, value)
    saveCache(RESPONSE_CACHE_KEY, cache)
  },
  delete(key: string) {
    const cache = loadCache<unknown>(RESPONSE_CACHE_KEY)
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

export const handleEtagResponse = (response: AxiosResponse, etagKey: string) => {
  const responseHeaders = AxiosHeaders.from(
    (response.headers ?? undefined) as AxiosHeaders | string | undefined
  )
  const tag = responseHeaders.get("etag") ?? responseHeaders.get("ETag")

  if (typeof tag === "string" && tag.trim()) {
    etagCache.set(etagKey, tag)
    if (response.status === 200 && response.data) {
      responseCache.set(etagKey, response.data)
    }
  } else {
    etagCache.delete(etagKey)
    responseCache.delete(etagKey)
  }

  if (response.status === 304) {
    const cachedData = responseCache.get(etagKey)
    if (cachedData) {
      response.data = cachedData
      response.status = 200
    }
  }
}
