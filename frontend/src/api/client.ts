import axios, { AxiosHeaders, type AxiosRequestConfig } from "axios"
import { client as generatedClient } from "@/api/generated/client.gen"
import { applyLanguageHeader } from "./interceptors/language"
import { updateTraceContext } from "./interceptors/traceContext"
import {
  applyEtagHeader,
  handleEtagResponse,
  etagCache,
  responseCache,
  registerSigningKeyAccessor,
} from "./interceptors/etagCache"

export { registerSigningKeyAccessor }
import {
  waitForClientQueueSlot,
  releaseClientQueueSlot,
  isRateLimited,
  waitForRateLimitWindow,
  scheduleRateLimitWindow,
  RATE_LIMIT_MAX_RETRY,
} from "./interceptors/rateLimit"

export const API_UNAUTHORIZED_EVENT = "auth:unauthorized"
export const SKIP_UNAUTHORIZED_HEADER = "X-Client-Skip-Unauthorized"
const API_TIMEOUT_MS = 8000

/**
 * Endpoints that are allowed to bypass the client-side rate-limit queue.
 * Only add paths whose latency is directly user-visible during auth flows.
 * Any other endpoint with skipRateLimitQueue=true will be demoted to the queue.
 */
const RATE_LIMIT_SKIP_ALLOWLIST = new Set([
  "/auth/session/signing-key",
  "/users/me",
  "/auth/refresh",
  "/auth/token",
])

const devBase = ""
const prodBase = `${import.meta.env.VITE_BACKEND_ORIGIN || ""}/api/v1`

export type ApiRequestConfig<D = unknown> = AxiosRequestConfig<D> & {
  signal?: AbortSignal
  skipRateLimitQueue?: boolean
  __rateLimitRetryCount?: number
  __clientRateLimitAcquired?: boolean
  etagCacheKey?: string
}

export type TypedRequestOptions<_T extends string, _M extends string = "get"> = ApiRequestConfig

const api = axios.create({
  baseURL: import.meta.env.DEV ? devBase : prodBase,
  withCredentials: true,
  timeout: API_TIMEOUT_MS,
  xsrfCookieName: "csrf_token",
  xsrfHeaderName: "X-CSRF-Token",
  headers: {
    Accept: "application/json",
    "Content-Type": "application/json",
    "X-Requested-With": "XMLHttpRequest",
  },
})

if (import.meta.env.VITE_LHCI === "true") {
  api.defaults.adapter = async (config) => {
    return {
      data: { items: [] }, // Provide a safe default object/array combo
      status: 200,
      statusText: "OK",
      headers: new AxiosHeaders(),
      config,
      request: {},
    }
  }
}

// Hook the generated client to our customized axios instance
generatedClient.setConfig({
  axios: api,
})

export const resetEtagCache = () => {
  etagCache.clear()
  responseCache.clear()
}

const isAbortError = (error: unknown) => {
  if (!error) return false
  if (error instanceof DOMException) return error.name === "AbortError"
  if (typeof error === "object" && "name" in error) {
    const name = (error as { name?: string }).name
    return name === "CanceledError" || name === "AbortError"
  }
  return false
}

// TD-14-04 (audit Wave 14): Extracted — was hardcoded as 2000 in three places.
const DEFAULT_RETRY_AFTER_MS = 2000

const getRetryDelay = (headers: Record<string, unknown> | undefined) => {
  if (!headers) return DEFAULT_RETRY_AFTER_MS
  const header = headers["retry-after"] ?? headers["Retry-After"]
  if (typeof header !== "string") return DEFAULT_RETRY_AFTER_MS
  const numeric = Number.parseFloat(header)
  return Number.isFinite(numeric) ? Math.max(0, numeric * 1000) : DEFAULT_RETRY_AFTER_MS
}

// PERF-14-05 (audit Wave 14): Client-side mutation deduplication.
// TanStack Query deduplicates queries but not mutations.  If a user double-clicks
// before UI debounce fires, two identical POST requests go out.  The backend
// idempotency key handles this server-side, but the duplicate still wastes bandwidth.
// We suppress the duplicate on the client by tracking in-flight Idempotency-Keys.
const _inflightIdempotencyKeys = new Set<string>()

// TD-31-04: Synchronize in-flight idempotency keys across tabs via BroadcastChannel.
// Prevents duplicate mutations when two tabs submit the same form simultaneously.
// Server-side idempotency key is the authoritative check — this is defense-in-depth.
let _dedupeChannel: BroadcastChannel | null = null
try {
  if (typeof BroadcastChannel !== "undefined") {
    _dedupeChannel = new BroadcastChannel("ecosystem.idempotency.dedup")
    _dedupeChannel.addEventListener(
      "message",
      (e: MessageEvent<{ key: string; action: "add" | "delete" }>) => {
        if (e.data.action === "add") _inflightIdempotencyKeys.add(e.data.key)
        else _inflightIdempotencyKeys.delete(e.data.key)
      }
    )
  }
} catch {
  // BroadcastChannel not available (SSR, old browsers, Web Workers).
}

api.interceptors.request.use(async (config) => {
  const candidate = config as ApiRequestConfig

  // FIX-44-01: Normalize doubled /api/v1 prefix.
  // The @hey-api/client-axios `buildUrl()` reads our axios instance's baseURL ("/api/v1")
  // and prepends it to the SDK URL (also "/api/v1/..."), producing "/api/v1/api/v1/...".
  // It then passes `baseURL: ""` to axios, so we detect the doubled prefix in the URL itself.
  const _url = config.url ?? ""
  if (_url.startsWith("/api/v1/api/v1/")) {
    config.url = _url.slice("/api/v1".length)
  } else if (_url.startsWith("/api/v1/") && config.baseURL?.includes("/api/v1")) {
    config.url = _url.slice("/api/v1".length)
  }

  // Mutation dedup: reject duplicate in-flight requests with the same Idempotency-Key.
  if (config.method && ["post", "put", "patch", "delete"].includes(config.method)) {
    const idempotencyKey =
      config.headers instanceof AxiosHeaders
        ? (config.headers.get("Idempotency-Key") as string | undefined)
        : undefined
    if (idempotencyKey && _inflightIdempotencyKeys.has(idempotencyKey)) {
      return Promise.reject(new axios.Cancel("Duplicate mutation suppressed (client-side dedup)"))
    }
    if (idempotencyKey) {
      _inflightIdempotencyKeys.add(idempotencyKey)
      _dedupeChannel?.postMessage({ key: idempotencyKey, action: "add" })
    }
  }

  // Guard the bypass flag: only allowlisted URLs may skip the rate-limit queue.
  if (candidate.skipRateLimitQueue) {
    const url = candidate.url ?? ""
    if (!RATE_LIMIT_SKIP_ALLOWLIST.has(url)) {
      if (import.meta.env.DEV) {
        console.warn(`[rateLimit] skipRateLimitQueue=true for non-allowlisted URL: ${url}`)
      }
      candidate.skipRateLimitQueue = false
    }
  }

  if (!candidate.skipRateLimitQueue) {
    // @ts-expect-error - axios config bridge
    await waitForClientQueueSlot(candidate)
  }

  if (isRateLimited()) {
    await waitForRateLimitWindow()
  }

  applyLanguageHeader(config)

  if (candidate.etagCacheKey) {
    applyEtagHeader(config, candidate.etagCacheKey)
  }

  // Wave 133 SW1 — SSR cookie forwarding. On Node SSR runtime, the
  // `access_token_v2` HttpOnly cookie isn't auto-forwarded by axios
  // (`withCredentials: true` only applies in browsers). `frontend/src/server.ts`
  // stashes the raw incoming `Cookie` header in `requestCookieStorage` per-
  // request; we read it via the globalThis getter and set it on the outgoing
  // config. Browser path is provably unaffected: `typeof window === "undefined"`
  // is statically false in client bundles, so the branch dead-codes out of
  // browser tree-shake (Vite environments build keeps cookie-forwarding logic
  // in the server chunk only). NEVER log or surface the raw cookie value — it
  // contains the access_token_v2 HttpOnly cookie.
  if (typeof window === "undefined") {
    const cookie =
      typeof globalThis !== "undefined" ? globalThis.__ssrCookieGetter__?.() : undefined
    if (cookie && cookie.length > 0) {
      const headers = AxiosHeaders.from(config.headers ?? {})
      headers.set("Cookie", cookie)
      config.headers = headers
    }
  }

  if (config.data instanceof FormData) {
    const headers = AxiosHeaders.from(config.headers ?? {})
    headers.delete("Content-Type")
    config.headers = headers
  }

  return config
})

// PERF-14-05: Helper to clean up in-flight idempotency key tracking.
const _cleanupIdempotencyKey = (config: ApiRequestConfig | undefined) => {
  if (!config?.headers) return
  const key =
    config.headers instanceof AxiosHeaders
      ? (config.headers.get("Idempotency-Key") as string | undefined)
      : undefined
  if (key) {
    _inflightIdempotencyKeys.delete(key)
    _dedupeChannel?.postMessage({ key, action: "delete" })
  }
}

api.interceptors.response.use(
  async (response) => {
    const config = response.config as ApiRequestConfig | undefined
    _cleanupIdempotencyKey(config)
    if (config?.etagCacheKey) {
      await handleEtagResponse(response, config.etagCacheKey)
    }
    updateTraceContext(response.headers as AxiosHeaders)
    // @ts-expect-error - axios config bridge
    releaseClientQueueSlot(config)
    return response
  },
  async (error) => {
    const config = error?.config as ApiRequestConfig | undefined
    _cleanupIdempotencyKey(config)
    // @ts-expect-error - axios config bridge
    releaseClientQueueSlot(config)

    if (error?.response?.headers) {
      updateTraceContext(error.response.headers as AxiosHeaders)
    }

    if (config?.etagCacheKey && error?.response?.status >= 400 && error.response.status !== 304) {
      etagCache.delete(config.etagCacheKey)
    }

    if (error?.response?.status === 429 && config && !config.skipRateLimitQueue) {
      const delay = getRetryDelay(error.response?.headers)
      scheduleRateLimitWindow(delay)

      const retryCount = config.__rateLimitRetryCount ?? 0
      if (retryCount < RATE_LIMIT_MAX_RETRY && !config.signal?.aborted && !isAbortError(error)) {
        config.__rateLimitRetryCount = retryCount + 1
        // RZ-31-04: Propagate AbortSignal so navigation cancels the wait.
        await waitForRateLimitWindow(config.signal)
        if (config.signal?.aborted) return Promise.reject(new DOMException("Aborted", "AbortError"))
        return api.request(config)
      }
    }

    if (error?.response?.status === 401) {
      const headers = (config?.headers ?? {}) as Record<string, unknown>
      if (headers[SKIP_UNAUTHORIZED_HEADER]) {
        delete headers[SKIP_UNAUTHORIZED_HEADER]
        return Promise.reject(error)
      }
      // DEBT-02: Removed legacy `window.dispatchEvent` workaround.
      // 401s are now handled via declarative error boundaries and React Query conventions.
    }
    return Promise.reject(error)
  }
)

/**
 * DEPRECATED: Use the generated SDK from @/api/generated instead.
 * This manual TypedApiClient is kept for backward compatibility during migration.
 */
export const apiClient = {
  get: <T = unknown>(url: string, config?: AxiosRequestConfig) => api.get<T>(url, config),
  post: <T = unknown>(url: string, data?: unknown, config?: AxiosRequestConfig) =>
    api.post<T>(url, data, config),
  put: <T = unknown>(url: string, data?: unknown, config?: AxiosRequestConfig) =>
    api.put<T>(url, data, config),
  patch: <T = unknown>(url: string, data?: unknown, config?: AxiosRequestConfig) =>
    api.patch<T>(url, data, config),
  delete: (url: string, config?: AxiosRequestConfig) => api.delete(url, config),
  request: (config: AxiosRequestConfig) => api.request(config),
}

export default api
